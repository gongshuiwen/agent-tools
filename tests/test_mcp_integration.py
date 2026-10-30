"""Optional real SDK smoke test (skipped when mcp v2 is unavailable)."""

import asyncio

import pytest


def test_real_mcp_sdk_roundtrip():
    pytest.importorskip("mcp", minversion="2.0")
    from mcp.server import MCPServer

    from agent_tools import ToolExecutor, ToolRegistry
    from agent_tools_mcp import MCPProvider

    server = MCPServer("in-process-test")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add numbers."""
        return a + b

    async def scenario():
        registry = ToolRegistry()
        provider = MCPProvider("test", server)
        async with provider:
            assert "mcp.test.add" in await registry.mount(provider)
            result = await ToolExecutor(registry).execute("mcp.test.add", {"a": 3, "b": 4})
            assert result.ok
            registry.unmount(provider)

    asyncio.run(scenario())
