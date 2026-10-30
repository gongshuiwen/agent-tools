"""End-to-end MCP v2 in-process tests (runs when the SDK is installed)."""

import asyncio

import pytest

from agent_tools import ToolRegistry, ToolResult, ToolSpec, tool
from agent_tools_mcp import create_tools_server


@pytest.mark.parametrize("use_remote", [False, True])
def test_client_roundtrip(use_remote):
    mcp = pytest.importorskip("mcp")

    @tool(name="math.add")
    def add(a: int, b: int) -> int:
        """Add numbers."""
        return a + b

    class Provider:
        async def discover(self):
            return [ToolSpec(
                name="mcp.example.image", description="Return structured image information.",
                input_schema={"type": "object", "properties": {"name": {"type": "string"}},
                              "required": ["name"]},
                output_schema={"type": "object", "properties": {"name": {"type": "string"}},
                               "required": ["name"]},
            )]

        async def invoke(self, name, arguments):
            return ToolResult(
                name, True, output={"name": arguments["name"]},
                metadata={"content": [
                    {"type": "text", "text": "ok"},
                    {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"},
                ]},
            )

    async def run():
        registry = ToolRegistry()
        registry.register(add)
        if use_remote:
            await registry.mount(Provider())
        names = ["math.add"] + (["mcp.example.image"] if use_remote else [])
        server = create_tools_server(registry, include=names)
        async with mcp.Client(server) as client:
            tools = (await client.list_tools()).tools
            assert [tool.name for tool in tools] == names
            assert (await client.call_tool("math.add", {"a": 2, "b": 3})).content[0].text == "5"
            invalid = await client.call_tool("math.add", {"a": "2", "b": 3})
            assert invalid.is_error
            if use_remote:
                image = await client.call_tool("mcp.example.image", {"name": "test"})
                assert image.structured_content == {"name": "test"}
                assert image.content[1].type == "image"

    asyncio.run(run())


def test_mcp_provider_can_be_reexported():
    mcp = pytest.importorskip("mcp")
    from mcp.server import MCPServer
    from agent_tools_mcp import MCPProvider

    upstream = MCPServer("upstream")

    @upstream.tool()
    def echo(message: str) -> str:
        """Echo a message."""
        return message

    async def run():
        registry = ToolRegistry()
        async with MCPProvider("upstream", upstream) as provider:
            await registry.mount(provider)
            gateway = create_tools_server(registry, include=["mcp.upstream.echo"])
            async with mcp.Client(gateway) as client:
                listed = (await client.list_tools()).tools
                assert [item.name for item in listed] == ["mcp.upstream.echo"]
                result = await client.call_tool("mcp.upstream.echo", {"message": "hello"})
                assert not result.is_error
                assert "hello" in result.content[0].text
            registry.unmount(provider)

    asyncio.run(run())
