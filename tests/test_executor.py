"""Sync/async invocation, error handling and JSON-safe results."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from agent_tools import ToolExecutor, ToolRegistry, tool


@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@tool
async def greet(name: str) -> dict[str, str]:
    """Greet someone asynchronously."""
    await asyncio.sleep(0)
    return {"message": f"Hello {name}"}


def make_executor() -> ToolExecutor:
    registry = ToolRegistry()
    registry.register(add)
    registry.register(greet)
    return ToolExecutor(registry)


def test_sync_and_async_functions_work_through_async_boundary():
    async def check():
        executor = make_executor()
        a = await executor.execute("add", {"a": 7, "b": 9})
        b = await executor.execute("greet", {"name": "Ada"})
        assert a.ok and a.output == 16
        assert b.ok and b.output == {"message": "Hello Ada"}
        assert json.loads(json.dumps(a.to_dict())) == a.to_dict()

    asyncio.run(check())


def test_sync_convenience_api():
    result = make_executor().run("add", {"a": 2, "b": 3})
    assert result.ok and result.output == 5


def test_unknown_tool_and_validation_errors_do_not_raise():
    executor = make_executor()
    missing = executor.run("unknown", {})
    assert not missing.ok and missing.error.code == "tool_not_found"
    wrong_type = executor.run("add", {"a": "2", "b": 1})
    assert not wrong_type.ok and wrong_type.error.code == "validation_error"
    assert wrong_type.error.details[0]["loc"] == ["a"]
    assert "input" not in wrong_type.error.details[0]
    unexpected = executor.run("add", {"a": 2, "b": 3, "c": 1})
    assert not unexpected.ok and unexpected.error.code == "validation_error"
    not_a_mapping = executor.run("add", [1, 2])  # type: ignore[arg-type]
    assert not not_a_mapping.ok and not_a_mapping.error.code == "validation_error"


def test_tool_errors_are_captured_as_structured_results():
    @tool
    def broken() -> None:
        """Deliberately fail."""
        raise ValueError("invalid remote response")

    registry = ToolRegistry()
    registry.register(broken)
    result = ToolExecutor(registry).run("broken", {})
    assert not result.ok
    assert result.error.code == "execution_error"
    assert "ValueError" in result.error.message


def test_pydantic_and_datetime_outputs_are_serialized():
    class Response(BaseModel):
        when: datetime
        count: int

    @tool
    def emit() -> Response:
        """Return a typed response."""
        return Response(when=datetime(2026, 1, 2, tzinfo=timezone.utc), count=3)

    registry = ToolRegistry()
    registry.register(emit)
    result = ToolExecutor(registry).run("emit", {})
    assert result.ok
    assert result.output == {"when": "2026-01-02T00:00:00Z", "count": 3}
    json.dumps(result.to_dict())


def test_non_serializable_results_return_error():
    @tool
    def emit() -> object:
        """Return an opaque object."""
        return object()

    registry = ToolRegistry()
    registry.register(emit)
    result = ToolExecutor(registry).run("emit", {})
    assert not result.ok and result.error.code == "serialization_error"


def test_cancellation_is_not_caught():
    @tool
    async def cancelled() -> None:
        """Cancel the caller."""
        raise asyncio.CancelledError

    registry = ToolRegistry()
    registry.register(cancelled)

    async def invoke() -> None:
        with pytest.raises(asyncio.CancelledError):
            await ToolExecutor(registry).execute("cancelled", {})

    asyncio.run(invoke())


def test_run_must_not_be_used_inside_event_loop():
    async def invoke():
        with pytest.raises(RuntimeError, match="await executor.execute"):
            make_executor().run("add", {"a": 1, "b": 2})

    asyncio.run(invoke())


def test_non_finite_float_is_not_reported_as_json_compatible():
    @tool
    def emit() -> float:
        """Return a non-finite value."""
        return float("nan")

    registry = ToolRegistry()
    registry.register(emit)
    result = ToolExecutor(registry).run("emit", {})
    assert not result.ok and result.error.code == "serialization_error"


def test_execution_error_redacts_sensitive_message():
    @tool
    def broken() -> str:
        """Raise a sensitive error."""
        raise ValueError("API_TOKEN=SHOULD_NOT_APPEAR")

    registry = ToolRegistry()
    registry.register(broken)
    result = ToolExecutor(registry).run("broken", {})
    assert result.error.code == "execution_error"
    assert "SHOULD_NOT_APPEAR" not in json.dumps(result.to_dict())


def test_authorization_denies_and_fails_closed():
    calls = []

    @tool
    def read(path: str) -> str:
        """Read only an authorized path."""
        calls.append(path)
        return path

    registry = ToolRegistry()
    registry.register(read)
    deny = ToolExecutor(registry, authorize=lambda name, args: False)
    assert deny.run("read", {"path": "private"}).error.code == "permission_denied"

    def broken(name, args):
        raise ValueError("AUTH_SECRET")

    error = ToolExecutor(registry, authorize=broken).run("read", {"path": "private"})
    assert error.error.code == "permission_denied"
    assert "AUTH_SECRET" not in str(error.to_dict())
    assert calls == []

    async def permit(name, args):
        return args["path"] == "public"

    executor = ToolExecutor(registry, authorize=permit)
    assert executor.run("read", {"path": "public"}).output == "public"
    assert executor.run("read", {"path": "private"}).error.code == "permission_denied"
    assert calls == ["public"]


def test_authorizer_preserves_cancellation():
    async def cancelled(name, args):
        raise asyncio.CancelledError()

    async def check():
        with pytest.raises(asyncio.CancelledError):
            await ToolExecutor(make_executor().registry, authorize=cancelled).execute(
                "add", {"a": 1, "b": 2}
            )

    asyncio.run(check())
