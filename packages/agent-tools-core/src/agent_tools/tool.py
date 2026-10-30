"""A small, framework-independent contract for Python function tools."""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, TypeVar, get_type_hints, overload

from pydantic import BaseModel, ConfigDict, create_model

from .errors import ToolDefinitionError

F = TypeVar("F", bound=Callable[..., Any])
_TOOL_ATTRIBUTE = "__agent_tools_definition__"
_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


@dataclass(frozen=True, slots=True)
class Tool:
    """An immutable description of a callable and its validated parameters.

    Use :meth:`from_callable` for explicit construction, or ``@tool`` to
    attach a definition to a function while leaving it directly callable.
    """

    name: str
    description: str
    func: Callable[..., Any]
    input_model: type[BaseModel]

    @classmethod
    def from_callable(
        cls,
        func: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Tool:
        """Build a tool from an annotated Python function.

        Positional-only and variadic parameters are deliberately unsupported:
        JSON-style tool arguments are always named key-value pairs.
        """
        if not callable(func):
            raise ToolDefinitionError("A tool must be defined by a callable")

        tool_name = name if name is not None else getattr(func, "__name__", "")
        if not isinstance(tool_name, str) or not _NAME_PATTERN.fullmatch(tool_name):
            raise ToolDefinitionError(f"Invalid tool name: {tool_name!r}")

        tool_description = description if description is not None else inspect.getdoc(func)
        if not isinstance(tool_description, str) or not tool_description.strip():
            raise ToolDefinitionError(f"Tool {tool_name!r} needs a docstring or description")

        try:
            signature = inspect.signature(func)
            # The return annotation is informative only; evaluating it can fail
            # for locally defined models even when all inputs are valid.
            raw_annotations = getattr(func, "__annotations__", {})
            parameters_only = SimpleNamespace(
                __annotations__={k: v for k, v in raw_annotations.items() if k != "return"}
            )
            annotations = get_type_hints(
                parameters_only, globalns=getattr(func, "__globals__", None),
                include_extras=True,
            )
        except (TypeError, ValueError, NameError, AttributeError) as exc:
            raise ToolDefinitionError(f"Cannot inspect tool {tool_name!r}: {exc}") from exc

        fields: dict[str, Any] = {}
        for parameter in signature.parameters.values():
            if parameter.kind not in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                raise ToolDefinitionError(
                    f"Tool {tool_name!r} has unsupported parameter {parameter.name!r} "
                    "(positional-only, *args and **kwargs are not supported)"
                )
            if parameter.name not in annotations:
                raise ToolDefinitionError(
                    f"Tool {tool_name!r} parameter {parameter.name!r} needs a type annotation"
                )
            default = parameter.default
            if default is inspect.Parameter.empty:
                default = ...
            fields[parameter.name] = (annotations[parameter.name], default)

        try:
            input_model = create_model(
                f"{tool_name.replace('.', '_').replace('-', '_')}Arguments",
                __config__=ConfigDict(extra="forbid", strict=True, validate_default=True),
                **fields,
            )
            # Fail fast: some annotations can validate but cannot produce JSON Schema.
            input_model.model_json_schema()
        except Exception as exc:
            raise ToolDefinitionError(
                f"Cannot generate input schema for tool {tool_name!r}: {exc}"
            ) from exc

        return cls(
            name=tool_name,
            description=inspect.cleandoc(tool_description),
            func=func,
            input_model=input_model,
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        """The JSON Schema for named arguments (Pydantic / JSON Schema 2020-12)."""
        return self.input_model.model_json_schema()

    @property
    def is_async(self) -> bool:
        return inspect.iscoroutinefunction(self.func)

    def validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate inputs without flattening nested Pydantic models to dicts."""
        model = self.input_model.model_validate(arguments)
        return {key: getattr(model, key) for key in type(model).model_fields}


@overload
def tool(func: F, *, name: str | None = None, description: str | None = None) -> F: ...


@overload
def tool(*, name: str | None = None, description: str | None = None) -> Callable[[F], F]: ...


def tool(
    func: F | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> F | Callable[[F], F]:
    """Mark a function as a tool without wrapping it or registering globally.

    Both ``@tool`` and ``@tool(name="custom")`` are supported. Decoration
    validates its contract immediately; the original function is returned.
    """

    def decorate(function: F) -> F:
        definition = Tool.from_callable(function, name=name, description=description)
        setattr(function, _TOOL_ATTRIBUTE, definition)
        return function

    return decorate(func) if func is not None else decorate


def as_tool(value: Tool | Callable[..., Any]) -> Tool:
    """Resolve an explicit Tool, decorated function, or ordinary function."""
    if isinstance(value, Tool):
        return value
    definition = getattr(value, _TOOL_ATTRIBUTE, None)
    if isinstance(definition, Tool):
        return definition
    return Tool.from_callable(value)
