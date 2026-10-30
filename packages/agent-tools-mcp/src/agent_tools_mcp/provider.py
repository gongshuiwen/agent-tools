"""Discover MCP Tools and expose them through the standard Tool interface."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from jsonschema import FormatChecker, validators

from agent_tools import Tool, ToolArgumentsError, ToolInvocationError

_ALIAS = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


@dataclass
class McpProvider:
    """Translate remote MCP tools to local Tool definitions.

    ``target`` accepts a URL, an MCP SDK target, or an mcp.json server
    specification. Connections are intentionally short-lived.
    """

    name: str
    target: Any

    def _client_target(self) -> Any:
        if not isinstance(self.target, dict):
            return self.target
        if self.target.get("type") in ("streamable-http", "http"):
            return self.target["url"]
        if self.target.get("type") == "stdio":
            from mcp import StdioServerParameters

            return StdioServerParameters(
                command=self.target["command"],
                args=self.target.get("args", []),
                env=self.target.get("env"),
            )
        raise ValueError("Unsupported MCP connection type")

    async def discover(self) -> list[Tool]:
        from mcp import Client

        if not _ALIAS.fullmatch(self.name):
            raise ValueError(f"Invalid MCP server alias: {self.name!r}")

        remote_tools: list[Any] = []
        async with Client(self._client_target()) as client:
            cursor: str | None = None
            while True:
                page = await client.list_tools(cursor=cursor)
                remote_tools.extend(page.tools)
                cursor = page.next_cursor
                if cursor is None:
                    break

        tools: list[Tool] = []
        for remote in remote_tools:
            original_name = remote.name
            # Some MCP servers expose '/' or ':' in names. Normalize only the
            # registry ID; always call the remote tool by its original name.
            safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", original_name)
            full_name = f"mcp.{self.name}.{safe_name}"
            schema = remote.input_schema
            schema_validator = validators.validator_for(schema)
            schema_validator.check_schema(schema)
            checker = schema_validator(schema, format_checker=FormatChecker())

            def validate(arguments: dict[str, Any], *, _checker=checker) -> dict[str, Any]:
                issues = sorted(_checker.iter_errors(arguments), key=lambda issue: issue.json_path)
                if issues:
                    raise ToolArgumentsError(
                        "Invalid tool arguments",
                        [
                            {
                                "loc": list(issue.absolute_path),
                                "type": str(issue.validator),
                                "msg": f"JSON Schema constraint {issue.validator!r} failed",
                            }
                            for issue in issues
                        ],
                    )
                return arguments

            def proxy(tool_name: str):
                async def call(**arguments: Any) -> dict[str, Any]:
                    from mcp import Client

                    async with Client(self._client_target()) as client:
                        result = await client.call_tool(tool_name, arguments)
                    content = [block.model_dump(mode="json", by_alias=True) for block in result.content]
                    output = {"content": content, "structured_content": result.structured_content}
                    if result.is_error:
                        raise ToolInvocationError(
                            "mcp_tool_error",
                            "MCP server reported a tool error",
                            [{"result": output}],
                        )
                    return output

                return call

            tools.append(
                Tool.from_schema(
                    name=full_name,
                    description=remote.description or remote.title or f"MCP tool {original_name}",
                    schema=schema,
                    func=proxy(original_name),
                    validator=validate,
                )
            )
        return tools
