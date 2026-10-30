"""MCP tools are registered under app ownership with original remote schemas."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import BaseModel

from agent_tools import App, DuplicateToolError, ToolExecutor, ToolRegistry
from agent_tools_mcp import McpProvider


class ContentBlock(BaseModel):
    type: str = "text"
    text: str


class StubClient:
    opened = 0
    calls = []
    targets = []

    def __init__(self, target):
        self.target = target
        self.targets.append(target)

    async def __aenter__(self):
        type(self).opened += 1
        return self

    async def __aexit__(self, *args):
        pass

    async def list_tools(self, cursor=None):
        if cursor is None:
            return SimpleNamespace(tools=[SimpleNamespace(
                name="search/files", title="Search", description="Search documents", input_schema={
                    "type": "object", "properties": {"query": {"type": "string", "minLength": 2}},
                    "required": ["query"], "additionalProperties": False,
                }
            )], next_cursor="page2")
        return SimpleNamespace(tools=[SimpleNamespace(
            name="get", title=None, description="Get a record", input_schema={
                "type": "object", "properties": {"id": {"type": "integer"}},
                "required": ["id"]
            }
        )], next_cursor=None)

    async def call_tool(self, name, arguments):
        type(self).calls.append((self.target, name, arguments))
        if arguments.get("query") == "fail":
            return SimpleNamespace(content=[ContentBlock(text="not found")],
                                   structured_content=None, is_error=True)
        return SimpleNamespace(content=[ContentBlock(text="ok")],
                               structured_content={"seen": arguments}, is_error=False)


def setup_stub(monkeypatch):
    StubClient.opened = 0
    StubClient.calls = []
    StubClient.targets = []
    fake = ModuleType("mcp")
    fake.Client = StubClient
    monkeypatch.setitem(sys.modules, "mcp", fake)


def test_mcp_discovery_and_invocation_using_app_manifest(tmp_path, monkeypatch):
    setup_stub(monkeypatch)
    root = tmp_path / "github"
    root.mkdir()
    (root / "plugin.json").write_text(json.dumps({
        "name": "github", "description": "GitHub app", "version": "1.0.0"
    }))
    (root / "mcp.json").write_text(json.dumps({"mcpServers": {
        "github": {"type": "streamable-http", "url": "https://example.com/mcp"}
    }}))

    async def check():
        registry = ToolRegistry()
        assert await registry.load_app(App.from_path(root)) == [
            "mcp.github.get", "mcp.github.search_files"
        ]
        assert registry.get("mcp.github.search_files").input_schema["properties"]["query"]["minLength"] == 2
        assert len(registry.list_tools(app="github")) == 2
        executor = ToolExecutor(registry)
        bad = await executor.execute("mcp.github.search_files", {"query": "a"})
        assert bad.error.code == "validation_error"
        assert StubClient.opened == 1
        extra = await executor.execute("mcp.github.search_files", {"query": "valid", "extra": True})
        assert extra.error.code == "validation_error"
        good = await executor.execute("mcp.github.search_files", {"query": "hello"})
        assert good.ok and good.output["structured_content"] == {"seen": {"query": "hello"}}
        assert StubClient.calls[-1][1] == "search/files"
        assert StubClient.calls[-1][0] == "https://example.com/mcp"
        error = await executor.execute("mcp.github.search_files", {"query": "fail"})
        assert error.error.code == "mcp_tool_error"
        assert "not found" in str(error.error.details)
        assert (await executor.execute("mcp.github.get", {"id": 7})).ok
        assert StubClient.opened == 4

    asyncio.run(check())


def test_invalid_mcp_alias_and_duplicate_tools_are_atomic(monkeypatch):
    setup_stub(monkeypatch)
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="Invalid MCP server alias"):
        asyncio.run(registry.load_app(App("bad", "Invalid", providers=[McpProvider("bad.name", "url")])))
    assert registry.list_tools() == []
    asyncio.run(registry.load_app(App("good", "Valid", providers=[McpProvider("server", "url")])))
    with pytest.raises(DuplicateToolError):
        asyncio.run(registry.load_app(App("other", "Other", providers=[McpProvider("server", "url")])))
    assert [app.name for app in registry.list_apps()] == ["good"]


def test_mcp_stdio_configuration_uses_sdk_target(monkeypatch):
    setup_stub(monkeypatch)

    class StdioServerParameters:
        def __init__(self, *, command, args, env):
            self.command, self.args, self.env = command, args, env

    sys.modules["mcp"].StdioServerParameters = StdioServerParameters
    provider = McpProvider("local", {"type": "stdio", "command": "python", "args": ["srv.py"]})
    target = provider._client_target()
    assert target.command == "python"
    assert target.args == ["srv.py"]
    assert target.env is None
