"""Import remote MCP tools without implementing the MCP transport."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, Callable

from agent_tools import ToolError, ToolResult, ToolSpec


class MCPProvider:
    """A connected MCP server as a discoverable tool provider.

    Use inside ``async with``; only trusted server commands and URLs should be used.
    """

    def __init__(
        self, name: str, server: Any, *, client_factory: Callable | None = None,
        skills: bool = False,
    ):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", name):
            raise ValueError("Invalid MCP server name")
        self.name = name
        self.server = server
        self._factory = client_factory
        self._skills_enabled = skills
        self._manager: Any = None
        self._client: Any = None
        self._names: dict[str, str] = {}

    @classmethod
    def from_config(cls, path: str | Path, name: str, *, skills: bool = False) -> MCPProvider:
        """Read one explicitly named server from ``[mcp_servers.NAME]``."""
        settings = tomllib.loads(Path(path).read_text(encoding="utf-8"))["mcp_servers"][name]
        if "url" in settings:
            if "command" in settings:
                raise ValueError("Specify only url or command")
            return cls(name, settings["url"], skills=skills)
        from mcp import StdioServerParameters

        return cls(name, StdioServerParameters(
            command=settings["command"], args=settings.get("args", []),
            env=settings.get("env"),
        ), skills=skills)

    async def __aenter__(self) -> MCPProvider:
        if self._client is not None:
            raise RuntimeError("MCPProvider is already connected")
        if self._factory is None:
            from mcp import Client

            factory = Client
        else:
            factory = self._factory
        options = {}
        if self._skills_enabled:
            from mcp.client.extensions.skills import Skills

            options["extensions"] = [Skills()]
        self._manager = factory(self.server, **options)
        try:
            self._client = await self._manager.__aenter__()
        except BaseException:
            self._manager = None
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            await self._manager.__aexit__(exc_type, exc, tb)
        finally:
            self._client = None
            self._manager = None
            self._names.clear()

    @property
    def skills(self):
        """Remote Skill reader for an active, Skills-enabled connection."""
        if self._client is None or not self._skills_enabled:
            raise RuntimeError("Connect MCPProvider with skills=True to read Skills")
        from mcp.client.extensions.skills import Skills

        from .remote_skills import RemoteSkills

        return RemoteSkills(self.name, self._client, self._client.extension(Skills))

    async def discover(self) -> list[ToolSpec]:
        if self._client is None:
            raise RuntimeError("Connect MCPProvider before discovering tools")
        specs: list[ToolSpec] = []
        names: dict[str, str] = {}
        cursor = None
        seen = set()
        while True:
            page = await self._client.list_tools(cursor=cursor)
            for tool in page.tools:
                local_name = f"mcp.{self.name}.{tool.name}"
                if local_name in names:
                    raise ValueError(f"Duplicate MCP tool: {tool.name}")
                specs.append(ToolSpec(
                    name=local_name,
                    description=tool.description or tool.title or tool.name,
                    input_schema=tool.input_schema,
                    output_schema=getattr(tool, "output_schema", None),
                    source=f"mcp:{self.name}",
                ))
                names[local_name] = tool.name
            next_cursor = getattr(page, "next_cursor", None)
            if not next_cursor:
                break
            if next_cursor in seen:
                raise ValueError("Repeated MCP pagination cursor")
            seen.add(next_cursor)
            cursor = next_cursor
        self._names = names
        return specs

    async def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if self._client is None or name not in self._names:
            raise RuntimeError("MCP tool is unavailable or provider is closed")
        result = await self._client.call_tool(self._names[name], arguments)
        content = [block.model_dump(mode="json", by_alias=True, exclude_none=True)
                   for block in result.content]
        output = result.structured_content if result.structured_content is not None else content
        failed = bool(result.is_error)
        return ToolResult(
            tool=name, ok=not failed, output=output,
            error=ToolError("remote_tool_error", "MCP tool reported an error") if failed else None,
            metadata={"source": f"mcp:{self.name}", "content": content, "is_error": failed},
        )
