"""Run with: uv run python examples/demo.py"""

from __future__ import annotations

import asyncio
import json

from agent_tools import ToolExecutor, ToolRegistry, tool


@tool(name="math.add")
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@tool(name="text.greet")
async def greet(name: str) -> str:
    """Return a greeting asynchronously."""
    return f"Hello, {name}!"


async def main() -> None:
    registry = ToolRegistry()
    registry.register(add)
    registry.register(greet)
    registry.load_plugins(["filesystem"])

    executor = ToolExecutor(registry)
    for name, args in [
        ("math.add", {"a": 2, "b": 3}),
        ("text.greet", {"name": "Agent-Tools"}),
        ("fs.list_directory", {"path": "."}),
    ]:
        result = await executor.execute(name, args)
        print(json.dumps(result.to_dict(), ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
