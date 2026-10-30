"""Minimal, read-only filesystem examples (not a security sandbox)."""

from __future__ import annotations

from pathlib import Path

from agent_tools import tool


@tool(name="fs.read_text")
def read_text(path: str, encoding: str = "utf-8") -> str:
    """Read the contents of a UTF-8 (or specified encoding) text file."""
    return Path(path).read_text(encoding=encoding)


@tool(name="fs.list_directory")
def list_directory(path: str) -> list[str]:
    """List the names of immediate children of a directory, sorted by name."""
    return sorted(entry.name for entry in Path(path).iterdir())
