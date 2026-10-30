"""Tool-server export with a minimal stand-in for the optional MCP SDK."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace

import pytest

from agent_tools import ToolRegistry, ToolResult, ToolSpec, tool
from agent_tools_mcp import create_tools_server


@pytest.fixture
def fake_sdk(monkeypatch):
    mcp = ModuleType("mcp")
    server_module = ModuleType("mcp.server")
    types = ModuleType("mcp.types")

    class Server:
        def __init__(self, name, *, on_list_tools, on_call_tool):
            self.name = name
            self.list_tools = on_list_tools
            self.call_tool = on_call_tool

    @dataclass
    class Tool:
        name: str
        description: str
        input_schema: dict
        output_schema: dict | None = None

    @dataclass
    class ListToolsResult:
        tools: list

    @dataclass
    class TextContent:
        type: str
        text: str

    class CallToolResult:
        def __init__(self, *, content, is_error=False, structured_content=None):
            self.content = content
            self.is_error = is_error
            self.structured_content = structured_content

        @classmethod
        def model_validate(cls, values):
            if not isinstance(values["content"], list):
                raise ValueError("Invalid blocks")
            return cls(
                content=values["content"],
                is_error=values.get("isError", False),
                structured_content=values.get("structuredContent"),
            )

    server_module.Server = Server
    for name, cls in locals().copy().items():
        if name in ("Tool", "ListToolsResult", "TextContent", "CallToolResult"):
            setattr(types, name, cls)
    monkeypatch.setitem(sys.modules, "mcp", mcp)
    monkeypatch.setitem(sys.modules, "mcp.server", server_module)
    monkeypatch.setitem(sys.modules, "mcp.types", types)
    return types


@tool(name="math.add")
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def _call(server, name, arguments):
    return asyncio.run(server.call_tool(None, SimpleNamespace(name=name, arguments=arguments)))


def test_export_requires_explicit_selection(fake_sdk):
    registry = ToolRegistry()
    registry.register(add)
    with pytest.raises(TypeError):
        create_tools_server(registry, include="math.add")
    with pytest.raises(ValueError):
        create_tools_server(registry, include=[])
    with pytest.raises(ValueError):
        create_tools_server(registry, include=["math.add", "math.add"])
    with pytest.raises(KeyError):
        create_tools_server(registry, include=["no.such.tool"])


def test_local_schema_validation_and_whitelist(fake_sdk):
    registry = ToolRegistry()
    registry.register(add)
    server = create_tools_server(registry, include=["math.add"])
    listed = asyncio.run(server.list_tools(None, None)).tools
    assert [x.name for x in listed] == ["math.add"]
    assert listed[0].input_schema == registry.get("math.add").input_schema

    result = _call(server, "math.add", {"a": 2, "b": 3})
    assert not result.is_error and result.content[0].text == "5"
    invalid = _call(server, "math.add", {"a": "2", "b": 3})
    assert invalid.is_error and "validation_error" in invalid.content[0].text
    hidden = _call(server, "not-listed", {})
    assert hidden.is_error and "not exposed" in hidden.content[0].text


class Provider:
    async def discover(self):
        return [ToolSpec(
            name="mcp.remote.read",
            description="Read external data.",
            input_schema={"type": "object", "properties": {"id": {"type": "string"}},
                          "required": ["id"]},
            output_schema={"type": "object", "properties": {"count": {"type": "integer"}}},
        )]

    async def invoke(self, name, arguments):
        return ToolResult(
            name, ok=True, output={"count": 1},
            metadata={"content": [
                {"type": "text", "text": "found"},
                {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"},
            ]},
        )


def test_external_schema_and_content_blocks(fake_sdk):
    registry = ToolRegistry()
    asyncio.run(registry.mount(Provider()))
    server = create_tools_server(registry, include=["mcp.remote.read"])
    listed = asyncio.run(server.list_tools(None, None)).tools[0]
    assert listed.input_schema == registry.get("mcp.remote.read").input_schema
    assert listed.output_schema == registry.get("mcp.remote.read").spec.output_schema
    assert _call(server, "mcp.remote.read", {"id": 123}).is_error
    result = _call(server, "mcp.remote.read", {"id": "abc"})
    assert not result.is_error
    assert result.structured_content == {"count": 1}
    assert result.content[1]["type"] == "image"


def test_export_does_not_expose_tools_added_later(fake_sdk):
    registry = ToolRegistry()
    registry.register(add)
    server = create_tools_server(registry, include=["math.add"])

    @tool
    def later() -> str:
        """A tool added after exporting."""
        return "secret"

    registry.register(later)
    assert _call(server, "later", {}).is_error
