"""Framework-neutral mounted tools and JSON Schema validation."""

from __future__ import annotations

import asyncio

import pytest

from agent_tools import DuplicateToolError, ToolExecutor, ToolRegistry, ToolResult, ToolSpec


class Provider:
    def __init__(self, names=("remote.echo",)):
        self.names = names
        self.calls = []

    async def discover(self):
        return [ToolSpec(name, "Echo remote input", {
            "type": "object", "properties": {"value": {"type": "integer"}},
            "required": ["value"], "additionalProperties": False,
        }) for name in self.names]

    async def invoke(self, name, arguments):
        self.calls.append((name, arguments))
        return ToolResult(name, True, output=arguments["value"])


def test_provider_mount_validation_unmount():
    async def scenario():
        registry = ToolRegistry()
        provider = Provider()
        assert await registry.mount(provider) == ["remote.echo"]
        assert registry.get("remote.echo").is_async
        executor = ToolExecutor(registry)
        assert (await executor.execute("remote.echo", {"value": 3})).output == 3
        wrong = await executor.execute("remote.echo", {"value": "3"})
        assert wrong.error.code == "validation_error"
        assert wrong.error.details[0]["loc"] == ["value"]
        assert provider.calls == [("remote.echo", {"value": 3})]
        registry.unmount(provider)
        assert (await executor.execute("remote.echo", {"value": 3})).error.code == "tool_not_found"

    asyncio.run(scenario())


def test_mount_rejects_collisions_atomically():
    async def scenario():
        registry = ToolRegistry()
        await registry.mount(Provider())
        with pytest.raises(DuplicateToolError):
            await registry.mount(Provider(("remote.new", "remote.echo")))
        assert [t.name for t in registry.list_tools()] == ["remote.echo"]
        with pytest.raises(DuplicateToolError):
            await registry.mount(Provider(("duplicate", "duplicate")))

    asyncio.run(scenario())


def test_invalid_schema_rejected():
    from agent_tools import ToolDefinitionError
    with pytest.raises(ToolDefinitionError):
        ToolSpec("remote.error", "bad", {"type": "object", "properties": {"x": {"type": 3}}})
