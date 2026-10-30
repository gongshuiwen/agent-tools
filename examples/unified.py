"""Run with: uv run python examples/unified.py (optional MCP_URL environment variable)."""

import asyncio
import os

from agent_tools import ToolExecutor, ToolRegistry, tool
from agent_tools_skills import SkillCatalog


@tool(name="math.add")
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


async def main():
    registry = ToolRegistry()
    registry.register(add)
    SkillCatalog.from_paths(["examples/skills"]).register(registry)
    executor = ToolExecutor(registry)
    print((await executor.execute("math.add", {"a": 2, "b": 3})).to_dict())
    print((await executor.execute("skills.list", {})).output)

    if url := os.environ.get("MCP_URL"):
        from agent_tools_mcp import MCPProvider

        provider = MCPProvider("demo", url)
        async with provider:
            names = await registry.mount(provider)
            print("MCP tools:", names)
            registry.unmount(provider)


if __name__ == "__main__":
    asyncio.run(main())
