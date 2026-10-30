"""Boundary for validated execution of sync and async Python tools."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import ConfigDict, TypeAdapter, ValidationError

from .errors import ToolArgumentsError, ToolInvocationError, ToolNotFoundError
from .registry import ToolRegistry

_JSON_VALUE = TypeAdapter(Any, config=ConfigDict(ser_json_inf_nan="constants"))


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "output": self.output,
            "error": self.error.to_dict() if self.error else None,
        }


class ToolExecutor:
    """Execute registered tools without relying on any Agent framework.

    Synchronous tools run in worker threads to avoid blocking async callers.
    Cancelling or timing out a thread-backed operation does *not* stop the
    underlying callable. Timeout and sandbox policies are out of scope.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute(self, name: str, arguments: Mapping[str, Any]) -> ToolResult:
        """Validate and execute a tool, returning success or a structured error."""
        try:
            definition = self.registry.get(name)
        except ToolNotFoundError as exc:
            return ToolResult(name, False, error=ToolError("tool_not_found", str(exc)))

        if not isinstance(arguments, Mapping):
            return ToolResult(
                name,
                False,
                error=ToolError("validation_error", "Tool arguments must be a JSON object"),
            )

        try:
            validated = definition.validate_arguments(dict(arguments))
        except ToolArgumentsError as exc:
            return ToolResult(name, False, error=ToolError("validation_error", str(exc), exc.details))
        except ValidationError as exc:
            # Never echo raw argument values in validation errors.
            issues = [
                {"loc": list(issue["loc"]), "type": issue["type"], "msg": issue["msg"]}
                for issue in exc.errors(include_url=False)
            ]
            return ToolResult(
                name,
                False,
                error=ToolError("validation_error", "Invalid tool arguments", issues),
            )
        except Exception as exc:
            return ToolResult(
                name, False,
                error=ToolError("validation_error", f"Validator failed: {type(exc).__name__}"),
            )

        try:
            if definition.is_async:
                output = await definition.func(**validated)
            else:
                output = await asyncio.to_thread(definition.func, **validated)
        except ToolInvocationError as exc:
            return ToolResult(name, False, error=ToolError(exc.code, str(exc), exc.details))
        except Exception as exc:
            # asyncio.CancelledError (BaseException) still propagates as expected.
            return ToolResult(
                name,
                False,
                error=ToolError("execution_error", f"{type(exc).__name__}: {exc}"),
            )

        try:
            output_json = _JSON_VALUE.dump_python(output, mode="json", warnings="error")
            # JSON itself rejects NaN and infinity; Python's json.dumps is lax by default.
            json.dumps(output_json, allow_nan=False)
        except Exception as exc:
            return ToolResult(
                name,
                False,
                error=ToolError("serialization_error", f"{type(exc).__name__}: {exc}"),
            )
        return ToolResult(name, True, output=output_json)

    def run(self, name: str, arguments: Mapping[str, Any]) -> ToolResult:
        """Convenience entry point for synchronous callers outside event loops."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.execute(name, arguments))
        raise RuntimeError("Inside an event loop, use await executor.execute(...) instead")
