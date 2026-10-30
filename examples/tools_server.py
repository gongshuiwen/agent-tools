"""Export a selected Python tool and an imported MCP tool in-process."""

import asyncio

from mcp import Client
from mcp.server import MCPServer

from agent_tools import ToolRegistry, tool
from agent_tools_mcp import MCPProvider, create_tools_server


@tool(name="math.add")
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


upstream = MCPServer("upstream")


@upstream.tool()
def echo(message: str) -> str:
    """Echo a message."""
    return message


async def main():
    registry = ToolRegistry()
    registry.register(add)

    async with MCPProvider("upstream", upstream) as provider:
        await registry.mount(provider)
        server = create_tools_server(
            registry, include=["math.add", "mcp.upstream.echo"]
        )
        async with Client(server) as client:
            print([tool.name for tool in (await client.list_tools()).tools])
            print((await client.call_tool("math.add", {"a": 2, "b": 3})).content)
            print((await client.call_tool("mcp.upstream.echo", {"message": "hi"})).content)
        registry.unmount(provider)


if __name__ == "__main__":
    asyncio.run(main())
