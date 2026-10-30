"""Native Python tools use the same App and Provider model as remote tools."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

import pytest

from agent_tools import App, PluginLoadError, PythonProvider, ToolExecutor, ToolRegistry, tool


@tool(name="native.echo")
def echo(text: str) -> str:
    """Echo text."""
    return text


@dataclass
class FakePoint:
    name: str
    factory: Callable

    def load(self):
        return self.factory


def test_native_provider_discovers_entry_points_without_global_registry(monkeypatch):
    from agent_tools import provider as provider_module

    called = []

    def factory():
        called.append("loaded")
        return [echo]

    monkeypatch.setattr(provider_module, "entry_points", lambda *, group: [FakePoint("demo", factory)])

    registry = ToolRegistry()
    assert not called
    assert asyncio.run(registry.load_app(App("demo", "Demo", providers=[PythonProvider(["demo"])]))) == [
        "native.echo"
    ]
    assert called == ["loaded"]
    result = ToolExecutor(registry).run("native.echo", {"text": "hi"})
    assert result.output == "hi"


def test_unknown_and_duplicate_python_entry_points(monkeypatch):
    from agent_tools import provider as provider_module

    point = FakePoint("demo", lambda: [echo])
    monkeypatch.setattr(provider_module, "entry_points", lambda *, group: [point])
    with pytest.raises(PluginLoadError, match="Unknown plugin"):
        asyncio.run(PythonProvider(["missing"]).discover())
    monkeypatch.setattr(provider_module, "entry_points", lambda *, group: [point, point])
    with pytest.raises(PluginLoadError, match="Duplicate plugin"):
        asyncio.run(PythonProvider().discover())


def test_failed_python_plugin_does_not_register_partial_tools(monkeypatch):
    from agent_tools import provider as provider_module

    def broken_factory():
        raise ValueError("plugin crashed")

    monkeypatch.setattr(provider_module, "entry_points",
                        lambda *, group: [FakePoint("bad", broken_factory)])
    registry = ToolRegistry()
    with pytest.raises(PluginLoadError, match="plugin crashed"):
        asyncio.run(registry.load_app(App("broken", "Broken", providers=[PythonProvider(["bad"])])))
    assert registry.list_tools() == []
    assert registry.list_apps() == []
