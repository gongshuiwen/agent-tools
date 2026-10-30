"""Tool and application registration is explicit, sorted and atomic."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from agent_tools import (
    App,
    AppNotFoundError,
    DuplicateAppError,
    DuplicateToolError,
    Tool,
    ToolNotFoundError,
    ToolRegistry,
    tool,
)


@tool(name="native.echo")
def echo(text: str) -> str:
    """Echo text."""
    return text


@dataclass
class StaticProvider:
    tools: list[Tool]

    async def discover(self) -> list[Tool]:
        return self.tools


class BrokenProvider:
    async def discover(self) -> list[Tool]:
        raise RuntimeError("remote discovery failed")


def test_explicit_tools_remain_available():
    registry = ToolRegistry()
    registry.register(echo)
    assert [t.name for t in registry.list_tools()] == ["native.echo"]
    with pytest.raises(DuplicateToolError):
        registry.register(echo)
    with pytest.raises(ToolNotFoundError):
        registry.get("unknown")
    with pytest.raises(AppNotFoundError):
        registry.get_app("unknown")


def test_app_registration_is_atomic_across_multiple_providers():
    async def check():
        registry = ToolRegistry()
        first = App(name="bad", description="bad", providers=[
            StaticProvider([Tool.from_callable(echo, name="new.echo")]), BrokenProvider(),
        ])
        with pytest.raises(RuntimeError, match="discovery failed"):
            await registry.load_app(first)
        assert registry.list_apps() == []
        assert registry.list_tools() == []

        app = App(name="good", description="Good app", providers=[
            StaticProvider([Tool.from_callable(echo, name="new.echo")]),
            StaticProvider([Tool.from_callable(echo, name="other.echo")]),
        ])
        assert await registry.load_app(app) == ["new.echo", "other.echo"]
        assert registry.get_app("good") is app
        assert [t.name for t in registry.list_tools(app="good")] == ["new.echo", "other.echo"]
        assert [app.name for app in registry.list_apps()] == ["good"]
        with pytest.raises(DuplicateAppError):
            await registry.load_app(app)

    asyncio.run(check())


def test_cross_app_and_within_app_conflicts_do_not_partially_register():
    async def check():
        registry = ToolRegistry()
        first = App("first", "First", providers=[StaticProvider([Tool.from_callable(echo, name="native.echo")])])
        await registry.load_app(first)
        second = App("second", "Second", providers=[StaticProvider([
            Tool.from_callable(echo, name="new.echo"), Tool.from_callable(echo, name="native.echo")
        ])])
        with pytest.raises(DuplicateToolError):
            await registry.load_app(second)
        duplicates = App("third", "Third", providers=[StaticProvider([
            Tool.from_callable(echo, name="third.echo"),
            Tool.from_callable(echo, name="third.echo"),
        ])])
        with pytest.raises(DuplicateToolError):
            await registry.load_app(duplicates)
        assert [a.name for a in registry.list_apps()] == ["first"]
        assert [t.name for t in registry.list_tools()] == ["native.echo"]

    asyncio.run(check())


def test_empty_app_is_valid():
    registry = ToolRegistry()
    asyncio.run(registry.load_app(App("empty", "No tools")))
    assert registry.list_tools(app="empty") == []
