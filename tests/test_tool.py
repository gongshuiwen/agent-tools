"""Tool contracts, metadata, input schema and validation tests."""

from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel, Field, ValidationError
from typing import Annotated

from agent_tools import Tool, ToolDefinitionError, ToolRegistry, tool


class Payload(BaseModel):
    value: int = Field(ge=1, description="Positive numeric value")


def test_decorator_preserves_original_function_and_has_no_registry_side_effects():
    def add(a: int, b: int = 5) -> int:
        """Add two integers."""
        return a + b

    original = add
    decorated = tool(add)
    assert decorated is original
    assert inspect.isfunction(decorated)
    assert decorated(3) == 8
    assert ToolRegistry().list_tools() == []
    definition = ToolRegistry().register(decorated)
    assert definition.name == "add"
    assert definition.description == "Add two integers."
    assert definition.is_async is False
    assert definition.input_schema["required"] == ["a"]
    assert definition.input_schema["additionalProperties"] is False


def test_named_decorator_and_annotated_pydantic_metadata():
    @tool(name="data.normalize", description="Normalize a numeric payload")
    def normalize(
        payload: Payload,
        factor: Annotated[int, Field(ge=1, le=9, description="Scale factor")] = 2,
    ) -> int:
        """Ignored description."""
        assert isinstance(payload, Payload)
        return payload.value * factor

    definition = ToolRegistry().register(normalize)
    assert definition.name == "data.normalize"
    assert definition.description == "Normalize a numeric payload"
    schema = definition.input_schema
    assert schema["properties"]["factor"]["description"] == "Scale factor"
    assert schema["properties"]["factor"]["minimum"] == 1
    assert schema["$defs"]["Payload"]["properties"]["value"]["description"] == (
        "Positive numeric value"
    )
    validated = definition.validate_arguments({"payload": {"value": 3}})
    assert isinstance(validated["payload"], Payload)
    assert validated["factor"] == 2
    assert normalize(**validated) == 6


def test_explicit_from_callable_without_decorator():
    def multiply(left: int, right: int) -> int:
        """Multiply two integers."""
        return left * right

    definition = Tool.from_callable(multiply, name="math.multiply")
    assert definition.name == "math.multiply"
    assert definition.validate_arguments({"left": 3, "right": 4}) == {
        "left": 3,
        "right": 4,
    }


def test_rejects_unsupported_signatures_and_missing_contracts():
    def missing_type(x):
        """Missing type."""
        return x

    def args_only(*args: int) -> int:
        """Variadic function."""
        return 1

    def positional_only(a: int, /) -> int:
        """Positional-only function."""
        return a

    def no_description(value: int) -> int:
        return value

    for function in [missing_type, args_only, positional_only, no_description]:
        with pytest.raises(ToolDefinitionError):
            Tool.from_callable(function)

    with pytest.raises(ToolDefinitionError, match="Invalid tool name"):
        Tool.from_callable(positional_only, name="has space")


def test_rejects_bad_schema_at_registration_time():
    class Unknown:
        pass

    def unsupported(value: Unknown) -> str:
        """Schema cannot express custom class."""
        return str(value)

    # Supply a global annotation to avoid relying on local forward references.
    unsupported.__annotations__["value"] = Unknown
    with pytest.raises(ToolDefinitionError, match="Cannot generate input schema"):
        Tool.from_callable(unsupported)


def test_strict_types_and_forbidden_extra_properties():
    def power(value: int) -> int:
        """Return the input."""
        return value

    definition = Tool.from_callable(power)
    with pytest.raises(ValidationError):
        definition.validate_arguments({"value": "3"})
    with pytest.raises(ValidationError):
        definition.validate_arguments({"value": 3, "unexpected": True})
