"""Run offline: uv run python examples/app_demo.py"""

import asyncio
import json
from pathlib import Path

from agent_tools import App, PythonProvider, ToolExecutor, ToolRegistry


async def main() -> None:
    registry = ToolRegistry()
    await registry.load_app(App.from_path(Path(__file__).parent / "apps" / "reviewer"))
    await registry.load_app(App(
        name="filesystem",
        description="Native filesystem functions",
        providers=[PythonProvider(["filesystem"])],
    ))

    print("Apps:", [app.name for app in registry.list_apps()])
    print("Reviewer tools:", [tool.name for tool in registry.list_tools(app="reviewer")])
    print("App instructions:", registry.get_app("reviewer").read_instructions())
    print("Prompt:", registry.get_app("reviewer").read_prompt("review-summary"))

    executor = ToolExecutor(registry)
    for name, arguments in [
        ("skills.reviewer.review-changes", {}),
        ("skills.reviewer.review-changes", {"resource": "references/checklist.md"}),
        ("fs.list_directory", {"path": "examples/apps"}),
    ]:
        result = await executor.execute(name, arguments)
        print(json.dumps(result.to_dict(), ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
