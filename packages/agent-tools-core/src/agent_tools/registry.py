"""Explicit tool registration and opt-in discovery of installed plugins."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any, Callable, Iterable

from .errors import DuplicateToolError, PluginLoadError, ToolNotFoundError
from .spec import BoundTool, ToolProvider
from .tool import Tool, as_tool

PLUGIN_GROUP = "agent_tools.plugins"


class ToolRegistry:
    """An isolated registry, with no global state or import-time plugin loading."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool | BoundTool] = {}
        self._loaded_plugins: set[str] = set()

    def register(self, value: Tool | Callable[..., Any]) -> Tool:
        """Register a tool, rejecting names that already exist."""
        definition = as_tool(value)
        if definition.name in self._tools:
            raise DuplicateToolError(f"Tool {definition.name!r} is already registered")
        self._tools[definition.name] = definition
        return definition

    async def mount(self, provider: ToolProvider) -> list[str]:
        """Discover and atomically register tools from an active provider."""
        specs = list(await provider.discover())
        names = [spec.name for spec in specs]
        if len(names) != len(set(names)) or any(name in self._tools for name in names):
            raise DuplicateToolError("Provider has duplicate or already registered tool names")
        for spec in specs:
            self._tools[spec.name] = BoundTool(spec, provider)
        return names

    def unmount(self, provider: ToolProvider) -> None:
        """Unregister a provider's tools before closing its connection."""
        for name, value in list(self._tools.items()):
            if isinstance(value, BoundTool) and value.provider is provider:
                del self._tools[name]

    def get(self, name: str) -> Tool | BoundTool:
        """Return a registered tool, or raise ToolNotFoundError."""
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"Unknown tool: {name!r}") from exc

    def list_tools(self) -> list[Tool | BoundTool]:
        """Return registered tools in a stable name-sorted order."""
        return [self._tools[name] for name in sorted(self._tools)]

    def load_plugins(self, names: Iterable[str] | None = None) -> list[str]:
        """Load installed plugin entry points into this registry on demand.

        Each entry point must be a synchronous ``register(registry)`` function.
        Registration is atomic per plugin: failing plugins leave no tools behind.
        Loading a plugin executes third-party Python code; only load trusted
        packages. No security sandbox is provided.
        """
        requested = set(names) if names is not None else None
        discovered = {}
        for entry_point in entry_points(group=PLUGIN_GROUP):
            if entry_point.name in discovered:
                raise PluginLoadError(f"Duplicate plugin entry point: {entry_point.name!r}")
            discovered[entry_point.name] = entry_point

        if requested is not None:
            missing = requested - discovered.keys()
            if missing:
                raise PluginLoadError(f"Unknown plugin(s): {', '.join(sorted(missing))}")

        loaded: list[str] = []
        for plugin_name in sorted(discovered):
            if plugin_name in self._loaded_plugins:
                continue
            if requested is not None and plugin_name not in requested:
                continue

            snapshot = self._tools.copy()
            try:
                register = discovered[plugin_name].load()
                if not callable(register):
                    raise TypeError("Plugin entry point must resolve to register(registry)")
                register(self)
            except Exception as exc:
                self._tools.clear()
                self._tools.update(snapshot)
                raise PluginLoadError(f"Failed to load plugin {plugin_name!r}: {exc}") from exc

            self._loaded_plugins.add(plugin_name)
            loaded.append(plugin_name)
        return loaded
