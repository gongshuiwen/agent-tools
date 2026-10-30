"""Boundary for validated execution of sync and async Python tools."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

from jsonschema import Draft202012Validator, ValidationError as JSONSchemaError
from pydantic import ConfigDict, TypeAdapter, ValidationError

from .errors import ToolNotFoundError
from .registry import ToolRegistry
from .spec import BoundTool

_JSON_VALUE = TypeAdapter(Any, config=ConfigDict(ser_json_inf_nan="constants"))
Authorizer = Callable[[str, Mapping[str, Any]], bool | Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class ToolError:
    code: str
    message: str
    details: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"code": self.code, "message": self.message}
        if self.details is not None:
            result["details"] = self.details
        return result


@dataclass(frozen=True, slots=True)
class ToolResult:
    """A JSON-compatible outcome; execution errors never escape as exceptions."""

    tool: str
    ok: bool
    output: Any = None
    error: ToolError | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "tool": self.tool,
            "ok": self.ok,
            "output": self.output,
            "error": self.error.to_dict() if self.error else None,
        }
        if self.metadata is not None:
            data["metadata"] = self.metadata
        return data


class ToolExecutor:
    """Execute registered tools without relying on any Agent framework.

    Synchronous tools run in worker threads to avoid blocking async callers.
    Cancelling or timing out a thread-backed operation does *not* stop the
    underlying callable. Timeout and sandbox policies are out of v0.1 scope.
    """

    def __init__(self, registry: ToolRegistry, *, authorize: Authorizer | None = None) -> None:
        self.registry = registry
        self.authorize = authorize

    async def execute(self, name: str, arguments: Mapping[str, Any]) -> ToolResult:
        """Validate and execute a tool, returning success or a structured error."""
        try:
            definition = self.registry.get(name)
        except ToolNotFoundError:
            return ToolResult(name, False, error=ToolError("tool_not_found", "Tool not found"))

        if not isinstance(arguments, Mapping):
            return ToolResult(
                name,
                False,
                error=ToolError("validation_error", "Tool arguments must be a JSON object"),
            )

        if self.authorize is not None:
            try:
                allowed = self.authorize(name, dict(arguments))
                if inspect.isawaitable(allowed):
                    allowed = await allowed
            except Exception:
                allowed = False
            if allowed is not True:
                return ToolResult(name, False, error=ToolError("permission_denied", "Permission denied"))

        if isinstance(definition, BoundTool):
            try:
                Draft202012Validator(definition.input_schema).validate(dict(arguments))
            except JSONSchemaError as exc:
                issue = {"loc": list(exc.absolute_path), "type": "json_schema", "msg": "Invalid value"}
                return ToolResult(
                    name, False, error=ToolError("validation_error", "Invalid tool arguments", [issue])
                )
            try:
                result = await definition.provider.invoke(name, dict(arguments))
            except Exception as exc:
                return _failure(name, "execution_error", exc)
            # Preserve protocol content and status, but require JSON-safe boundaries.
            try:
                json.dumps(result.to_dict(), allow_nan=False)
            except (TypeError, ValueError) as exc:
                return _failure(name, "serialization_error", exc)
            return result

        try:
            validated = definition.validate_arguments(dict(arguments))
        except ValidationError as exc:
            issues = [
                {"loc": list(issue["loc"]), "type": issue["type"], "msg": "Invalid value"}
                for issue in exc.errors(include_url=False)
            ]
            return ToolResult(
                name, False, error=ToolError("validation_error", "Invalid tool arguments", issues)
            )

        try:
            if definition.is_async:
                output = await definition.func(**validated)
            else:
                output = await asyncio.to_thread(definition.func, **validated)
        except Exception as exc:
            return _failure(name, "execution_error", exc)

        try:
            output_json = _JSON_VALUE.dump_python(output, mode="json", warnings="error")
            # JSON itself rejects NaN and infinity; Python's json.dumps is lax by default.
            json.dumps(output_json, allow_nan=False)
        except Exception as exc:
            return _failure(name, "serialization_error", exc)
        return ToolResult(name, True, output=output_json)

    def run(self, name: str, arguments: Mapping[str, Any]) -> ToolResult:
        """Convenience entry point for synchronous callers outside event loops."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.execute(name, arguments))
        raise RuntimeError("Inside an event loop, use await executor.execute(...) instead")


def _failure(name: str, code: str, exc: Exception) -> ToolResult:
    # Never send exception messages, tracebacks, arguments or outputs to a model.
    label = "Tool execution failed" if code == "execution_error" else "Tool result is not JSON compatible"
    return ToolResult(name, False, error=ToolError(code, f"{label} ({type(exc).__name__})"))
