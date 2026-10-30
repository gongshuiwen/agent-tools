"""Errors that describe invalid tool definitions or plugin configuration."""


class AgentToolsError(Exception):
    """Base error for Agent-Tools configuration and lookup failures."""


class ToolDefinitionError(AgentToolsError, ValueError):
    """A Python callable cannot be represented as a tool."""


class DuplicateToolError(AgentToolsError, ValueError):
    """A registry already contains another tool with this name."""


class ToolNotFoundError(AgentToolsError, KeyError):
    """The requested tool has not been registered."""


class PluginLoadError(AgentToolsError, RuntimeError):
    """An installed plugin failed to load or register its tools."""
