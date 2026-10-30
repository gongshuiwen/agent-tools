"""Framework-neutral descriptions and providers for non-Python tools."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, Sequence

from jsonschema import Draft202012Validator

from .errors import ToolDefinitionError
if TYPE_CHECKING:
    from .executor import ToolResult

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    source: str = "external"
    output_schema: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise ToolDefinitionError(f"Invalid tool name: {self.name!r}")
        if not isinstance(self.input_schema, dict) or self.input_schema.get("type") != "object":
            raise ToolDefinitionError("Tool input_schema must describe a JSON object")
        try:
            Draft202012Validator.check_schema(self.input_schema)
        except Exception as exc:
            raise ToolDefinitionError(f"Invalid JSON Schema for {self.name!r}: {exc}") from exc


class ToolProvider(Protocol):
    async def discover(self) -> Sequence[ToolSpec]: ...

    async def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult: ...


@dataclass(frozen=True)
class BoundTool:
    """A discovered tool bound to a provider, without a Python function."""

    spec: ToolSpec
    provider: ToolProvider

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def description(self) -> str:
        return self.spec.description

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.spec.input_schema

    @property
    def is_async(self) -> bool:
        return True
