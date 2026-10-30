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


class ToolArgumentsError(AgentToolsError, ValueError):
    """An external tool's argument validation failed."""

    def __init__(self, message: str, details: list[dict] | None = None) -> None:
        super().__init__(message)
        self.details = details


class ToolInvocationError(AgentToolsError, RuntimeError):
    """A tool returned a known, structured execution failure."""

    def __init__(self, code: str, message: str, details: list[dict] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class DuplicateAppError(AgentToolsError, ValueError):
    """An application with this name has already been loaded."""


class AppNotFoundError(AgentToolsError, KeyError):
    """The requested application has not been loaded."""
