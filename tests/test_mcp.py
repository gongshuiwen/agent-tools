"""MCP adapter tests without network or launching a server."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_tools import ToolExecutor, ToolRegistry
from agent_tools_mcp import MCPProvider


class Block:
    def __init__(self, text):
        self.text = text

    def model_dump(self, **kwargs):
        return {"type": "text", "text": self.text}


class FakeClient:
    def __init__(self, server):
        self.server = server
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def list_tools(self, cursor=None):
        if cursor is None:
            return SimpleNamespace(tools=[SimpleNamespace(
                name="echo", title="Echo", description="", output_schema=None,
                input_schema={"type": "object", "properties": {"text": {"type": "string"}},
                              "required": ["text"], "additionalProperties": False},
            )], next_cursor="page2")
        return SimpleNamespace(tools=[SimpleNamespace(
            name="fail", title="Fail", description="Expected failure", output_schema=None,
            input_schema={"type": "object", "properties": {}},
        )], next_cursor=None)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return SimpleNamespace(content=[Block("output text")],
                               structured_content={"ok": True} if name == "echo" else None,
                               is_error=name == "fail")


def test_mcp_discovery_and_invocation():
    async def scenario():
        registry = ToolRegistry()
        provider = MCPProvider("sample", "http://localhost:8000/mcp", client_factory=FakeClient)
        async with provider:
            assert await registry.mount(provider) == ["mcp.sample.echo", "mcp.sample.fail"]
            executor = ToolExecutor(registry)
            success = await executor.execute("mcp.sample.echo", {"text": "hi"})
            assert success.ok and success.output == {"ok": True}
            assert success.metadata["content"] == [{"type": "text", "text": "output text"}]
            invalid = await executor.execute("mcp.sample.echo", {"text": 2})
            assert not invalid.ok and invalid.error.code == "validation_error"
            failed = await executor.execute("mcp.sample.fail", {})
            assert not failed.ok and failed.error.code == "remote_tool_error"
            assert failed.output == [{"type": "text", "text": "output text"}]
            assert provider._client.calls == [("echo", {"text": "hi"}), ("fail", {})]
            registry.unmount(provider)
        assert [t.name for t in registry.list_tools()] == []

    asyncio.run(scenario())


def test_mcp_provider_is_not_usable_after_close():
    async def scenario():
        provider = MCPProvider("sample", "test", client_factory=FakeClient)
        with pytest.raises(RuntimeError, match="Connect"):
            await provider.discover()
        async with provider:
            await provider.discover()
        with pytest.raises(RuntimeError, match="unavailable"):
            await provider.invoke("mcp.sample.echo", {})

    asyncio.run(scenario())


def test_mcp_config_http(tmp_path: Path):
    config = tmp_path / "servers.toml"
    config.write_text('[mcp_servers.test]\nurl = "https://example.org/mcp"\n')
    provider = MCPProvider.from_config(config, "test")
    assert provider.name == "test" and provider.server == "https://example.org/mcp"
