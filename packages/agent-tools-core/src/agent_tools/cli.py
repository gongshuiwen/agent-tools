"""Minimal discovery and inspection CLI for installed Agent-Tools plugins."""

from __future__ import annotations

import argparse
import json
import sys

from .errors import AgentToolsError
from .registry import ToolRegistry


def main(argv: list[str] | None = None) -> int:
    """Return a shell exit code; the console_script wrapper handles exiting."""
    parser = argparse.ArgumentParser(prog="agent-tools", description="Inspect installed tools")
    parser.add_argument(
        "--no-plugins", action="store_true", help="Do not load installed plugin entry points"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List registered tools")
    inspect_command = commands.add_parser("inspect", help="Display a tool's JSON Schema")
    inspect_command.add_argument("name", help="Tool name, e.g. fs.read_text")
    args = parser.parse_args(argv)

    registry = ToolRegistry()
    try:
        if not args.no_plugins:
            registry.load_plugins()
        if args.command == "list":
            for definition in registry.list_tools():
                summary = definition.description.splitlines()[0]
                print(f"{definition.name}\t{summary}")
        elif args.command == "inspect":
            definition = registry.get(args.name)
            print(
                json.dumps(
                    {
                        "name": definition.name,
                        "description": definition.description,
                        "input_schema": definition.input_schema,
                        "is_async": definition.is_async,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
    except AgentToolsError as exc:
        print(f"agent-tools: {exc}", file=sys.stderr)
        return 1
    return 0
