"""Run with: uv run python examples/skills_bridge.py (requires MCP SDK v2)."""

import asyncio

from agent_tools_mcp import MCPProvider, create_skills_server
from agent_tools_skills import SkillCatalog


async def main() -> None:
    catalog = SkillCatalog.from_paths(["examples/skills"])
    server = create_skills_server(catalog)
    async with MCPProvider("local", server, skills=True) as provider:
        print(await provider.skills.list())
        print(await provider.skills.load("skill://code-review/SKILL.md"))


if __name__ == "__main__":
    asyncio.run(main())
