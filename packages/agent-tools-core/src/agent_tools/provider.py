"""Minimal protocol for discovering native or remotely provided tools."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Protocol

from .errors import PluginLoadError
from .tool import Tool, as_tool

PLUGIN_GROUP = "agent_tools.plugins"


class ToolProvider(Protocol):
    async def discover(self) -> list[Tool]: ...


@dataclass
class PythonProvider:
    """Load explicit Python Entry Points returning iterable tool definitions.

    Entry Points are trusted Python code and are never loaded at import time.
    """

    names: Sequence[str] | None = None

    async def discover(self) -> list[Tool]:
        available = {}
        for point in entry_points(group=PLUGIN_GROUP):
            if point.name in available:
                raise PluginLoadError(f"Duplicate plugin entry point: {point.name!r}")
            available[point.name] = point
        selected = set(self.names) if self.names is not None else set(available)
        missing = selected - available.keys()
        if missing:
            raise PluginLoadError(f"Unknown plugin(s): {', '.join(sorted(missing))}")
        result: list[Tool] = []
        for name in sorted(selected):
            try:
                factory = available[name].load()
                result.extend(as_tool(value) for value in factory())
            except Exception as exc:
                raise PluginLoadError(f"Failed to discover plugin {name!r}: {exc}") from exc
        return result
