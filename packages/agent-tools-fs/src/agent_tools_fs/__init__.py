"""Example native tool collection exposed through Python Entry Points."""

from .tools import list_directory, read_text


def get_tools():
    return [list_directory, read_text]


__all__ = ["get_tools", "read_text", "list_directory"]
