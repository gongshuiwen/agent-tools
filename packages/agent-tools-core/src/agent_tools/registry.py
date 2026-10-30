"""One registry for Python, MCP and Skill tools, grouped by application."""

from __future__ import annotations

from typing import Callable

from .app import App
from .errors import AppNotFoundError, DuplicateAppError, DuplicateToolError, ToolNotFoundError
from .tool import Tool, as_tool


class ToolRegistry:
    """Application-aware, isolated tool registry with atomic app loading."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._apps: dict[str, App] = {}
        self._app_tools: dict[str, tuple[str, ...]] = {}

    def register(self, value: Tool | Callable) -> Tool:
        """Register an ungrouped native tool explicitly."""
        definition = as_tool(value)
        if definition.name in self._tools:
            raise DuplicateToolError(f"Tool {definition.name!r} is already registered")
        self._tools[definition.name] = definition
        return definition

    async def load_app(self, app: App) -> list[str]:
        """Discover all providers before committing the app or any of its tools."""
        if app.name in self._apps:
            raise DuplicateAppError(f"Application {app.name!r} is already loaded")
        pending: dict[str, Tool] = {}
        for provider in app.providers:
            for value in await provider.discover():
                definition = as_tool(value)
                if definition.name in self._tools or definition.name in pending:
                    raise DuplicateToolError(f"Tool {definition.name!r} is already registered")
                pending[definition.name] = definition
        self._tools.update(pending)
        self._apps[app.name] = app
        self._app_tools[app.name] = tuple(sorted(pending))
        return list(self._app_tools[app.name])

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"Unknown tool: {name!r}") from exc

    def get_app(self, name: str) -> App:
        try:
            return self._apps[name]
        except KeyError as exc:
            raise AppNotFoundError(f"Unknown application: {name!r}") from exc

    def list_apps(self) -> list[App]:
        return [self._apps[name] for name in sorted(self._apps)]

    def list_tools(self, *, app: str | None = None) -> list[Tool]:
        names = sorted(self._tools) if app is None else self._app_tools[self.get_app(app).name]
        return [self._tools[name] for name in names]
