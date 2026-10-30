"""Registration, deterministic plugin discovery and plugin rollback tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest

from agent_tools import (
    DuplicateToolError,
    PluginLoadError,
    ToolNotFoundError,
    ToolRegistry,
    tool,
)


@tool
def echo(text: str) -> str:
    """Echo text."""
    return text


@dataclass
class FakeEntryPoint:
    name: str
    factory: Callable[..., Any]

    def load(self) -> Callable[..., Any]:
        return self.factory


def test_registry_is_explicit_and_deterministic():
    registry = ToolRegistry()
    registry.register(echo)
    assert registry.get("echo").name == "echo"
    assert [t.name for t in registry.list_tools()] == ["echo"]
    with pytest.raises(DuplicateToolError):
        registry.register(echo)
    with pytest.raises(ToolNotFoundError):
        registry.get("missing")


def test_plugins_are_discovered_on_demand_and_loaded_once(monkeypatch):
    from agent_tools import registry as registry_module

    calls: list[str] = []

    def register_b(target: ToolRegistry) -> None:
        calls.append("b")
        target.register(echo)

    def register_a(target: ToolRegistry) -> None:
        calls.append("a")
        target.register(echo)

    fake = [FakeEntryPoint("b", register_b), FakeEntryPoint("a", register_a)]
    monkeypatch.setattr(registry_module, "entry_points", lambda *, group: fake)

    registry = ToolRegistry()
    assert calls == []
    assert registry.load_plugins(names=["b"]) == ["b"]
    assert registry.load_plugins(names=["b"]) == []
    assert calls == ["b"]
    # Different plugins producing the same tool name must not silently overwrite.
    with pytest.raises(PluginLoadError, match="Failed to load plugin 'a'"):
        registry.load_plugins(names=["a"])
    assert [t.name for t in registry.list_tools()] == ["echo"]


def test_failed_plugin_rolls_back_partial_registration(monkeypatch):
    from agent_tools import registry as registry_module

    @tool
    def other(value: int) -> int:
        """Return a value."""
        return value

    def broken(registry: ToolRegistry) -> None:
        registry.register(other)
        raise RuntimeError("registration failed")

    monkeypatch.setattr(
        registry_module,
        "entry_points",
        lambda *, group: [FakeEntryPoint("broken", broken)],
    )
    registry = ToolRegistry()
    registry.register(echo)
    with pytest.raises(PluginLoadError, match="registration failed"):
        registry.load_plugins()
    assert [t.name for t in registry.list_tools()] == ["echo"]


def test_unknown_and_duplicate_plugin_entry_points(monkeypatch):
    from agent_tools import registry as registry_module

    fake = [FakeEntryPoint("same", lambda registry: None)]
    monkeypatch.setattr(registry_module, "entry_points", lambda *, group: fake)
    with pytest.raises(PluginLoadError, match="Unknown plugin"):
        ToolRegistry().load_plugins(["missing"])

    monkeypatch.setattr(registry_module, "entry_points", lambda *, group: fake + fake)
    with pytest.raises(PluginLoadError, match="Duplicate plugin"):
        ToolRegistry().load_plugins()
