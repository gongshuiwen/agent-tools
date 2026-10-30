"""Filesystem plugin; explicitly registered via installed entry points."""

from __future__ import annotations

from agent_tools import ToolRegistry

from .tools import list_directory, read_text


def register(registry: ToolRegistry) -> None:
    """Register this plugin's tools in a caller-owned registry."""
    registry.register(read_text)
    registry.register(list_directory)


__all__ = ["register", "read_text", "list_directory"]
