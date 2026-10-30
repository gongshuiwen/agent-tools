"""Minimal CLI to inspect application bundles and their registered tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .app import App
from .errors import AgentToolsError
from .registry import ToolRegistry


async def _execute(args: argparse.Namespace) -> None:
    apps = [App.from_path(path) for path in args.app]

    # App metadata and instructions can be inspected without contacting MCP.
    if args.command == "apps":
        for app in sorted(apps, key=lambda item: item.name):
            print(f"{app.name}\t{app.description}")
        return
    if args.command == "context":
        matches = [app for app in apps if app.name == args.name]
        if len(matches) != 1:
            raise ValueError(f"Expected one app named {args.name!r}; found {len(matches)}")
        app = matches[0]
        print(json.dumps({
            "name": app.name,
            "description": app.description,
            "version": app.version,
            "instructions": app.read_instructions(),
            "prompts": app.list_prompts(),
        }, ensure_ascii=False, indent=2))
        return

    registry = ToolRegistry()
    for app in apps:
        await registry.load_app(app)
    if args.command == "list":
        for definition in registry.list_tools(app=args.for_app):
            print(f"{definition.name}\t{definition.description.splitlines()[0]}")
    elif args.command == "inspect":
        definition = registry.get(args.name)
        print(json.dumps({
            "name": definition.name,
            "description": definition.description,
            "input_schema": definition.input_schema,
        }, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-tools", description="Inspect application tools")
    parser.add_argument("--app", action="append", default=[], metavar="PATH",
                        help="Load an application bundle directory (repeatable)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("apps", help="List loaded apps")
    tools_cmd = commands.add_parser("list", help="List tools")
    tools_cmd.add_argument("--for-app", help="Only show tools belonging to this app")
    inspect_cmd = commands.add_parser("inspect", help="Inspect one tool's JSON Schema")
    inspect_cmd.add_argument("name")
    context_cmd = commands.add_parser("context", help="Read application instructions and metadata")
    context_cmd.add_argument("name")
    args = parser.parse_args(argv)
    try:
        asyncio.run(_execute(args))
    except (AgentToolsError, ValueError, ImportError, OSError, RuntimeError) as exc:
        print(f"agent-tools: {exc}", file=sys.stderr)
        return 1
    return 0
