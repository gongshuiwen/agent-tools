"""Expose an explicit selection of registered tools as a low-level MCP Server."""

from __future__ import annotations

import inspect
import json
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Iterable

from agent_tools import ToolExecutor
from agent_tools.spec import BoundTool

if TYPE_CHECKING:
    from agent_tools import ToolRegistry, ToolResult

MCPAuthorizer = Callable[[Any, str, dict[str, Any]], bool | Awaitable[bool]]


def create_tools_server(
    registry: ToolRegistry, *, include: Iterable[str], name: str = "agent-tools",
    authorize: MCPAuthorizer | None = None, expose_remote_errors: bool = False,
):
    """Export named tools with their original schemas; never export implicitly.

    The advertised list is a snapshot. Keep mounted providers connected while
    serving, and apply authentication/authorization outside this adapter.
    """
    from mcp.server import Server
    from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

    if isinstance(include, str):
        raise TypeError("include must be a collection of tool names, not a string")
    names = tuple(include)
    if not names or len(set(names)) != len(names):
        raise ValueError("include must contain unique tool names")

    definitions = {tool_name: registry.get(tool_name) for tool_name in names}
    tools = [
        Tool(
            name=definition.name,
            description=definition.description,
            input_schema=definition.input_schema,
            **(
                {"output_schema": definition.spec.output_schema}
                if isinstance(definition, BoundTool) and definition.spec.output_schema is not None
                else {}
            ),
        )
        for definition in definitions.values()
    ]
    executor = ToolExecutor(registry)

    async def list_tools(ctx, params):
        return ListToolsResult(tools=tools)

    async def call_tool(ctx, params):
        if params.name not in definitions:
            return _error("tool_not_found: Tool is not exposed")
        arguments = params.arguments or {}
        if authorize is not None:
            try:
                allowed = authorize(ctx, params.name, arguments)
                if inspect.isawaitable(allowed):
                    allowed = await allowed
            except Exception:
                allowed = False
            if allowed is not True:
                return _error("permission_denied: Permission denied")
        return _result_to_mcp(await executor.execute(params.name, arguments))

    def _error(message: str):
        return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)

    def _result_to_mcp(result: ToolResult):
        # MCPProvider stores original MCP blocks, so images, resource links and
        # remote tool failures can pass through without losing their semantics.
        blocks = (result.metadata or {}).get("content")
        if blocks is not None and (result.ok or expose_remote_errors):
            try:
                payload = {"content": blocks, "isError": not result.ok}
                if isinstance(result.output, dict):
                    payload["structuredContent"] = result.output
                return CallToolResult.model_validate(payload)
            except (ValueError, TypeError):
                return _error("serialization_error: Invalid MCP content from provider")

        if not result.ok:
            code = result.error.code if result.error else "execution_error"
            # An untrusted provider may supply arbitrary error text and codes.
            messages = {
                "tool_not_found": "Tool unavailable",
                "validation_error": "Invalid tool arguments",
                "permission_denied": "Permission denied",
                "serialization_error": "Invalid tool result",
                "remote_tool_error": "Upstream tool failed",
                "execution_error": "Tool execution failed",
            }
            if code not in messages:
                code = "execution_error"
            return _error(f"{code}: {messages[code]}")
        output = result.output
        text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            **({"structured_content": output} if isinstance(output, dict) else {}),
        )

    return Server(name, on_list_tools=list_tools, on_call_tool=call_tool)
