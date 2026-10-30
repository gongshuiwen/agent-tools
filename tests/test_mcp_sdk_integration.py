"""Optional real MCP SDK v2 in-process integration test."""

from __future__ import annotations

import asyncio

import pytest

from agent_tools import App, ToolExecutor, ToolRegistry
from agent_tools_mcp import McpProvider


def test_in_process_official_mcp_sdk():
    pytest.importorskip("mcp")
    asyncio.run(_exercise_mcp_sdk())


async def _exercise_mcp_sdk():
    from mcp.server import MCPServer

    server = MCPServer("Agent-Tools Integration Test")

    @server.tool()
    def greet(name: str) -> str:
        """Greet a person."""
        return f"Hello {name}"

    registry = ToolRegistry()
    assert await registry.load_app(App("test", "Test app", providers=[McpProvider("local", server)])) == [
        "mcp.local.greet"
    ]
    result = await ToolExecutor(registry).execute("mcp.local.greet", {"name": "Ada"})
    assert result.ok
    assert any("Hello Ada" in part.get("text", "") for part in result.output["content"])
