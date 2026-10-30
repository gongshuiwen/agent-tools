"""Read SEP-2640 Skills from one connected MCP server (never execute them)."""

from __future__ import annotations

import hashlib
from typing import Any

from agent_tools import ToolRegistry, tool

_MAX_BYTES = 256 * 1024


class RemoteSkills:
    """An opt-in, server-scoped view of remote Skills and text resources."""

    def __init__(self, server_name: str, client: Any, extension: Any) -> None:
        self.server_name = server_name
        self._client = client
        self._extension = extension

    async def list(self) -> list[dict[str, str]]:
        """Discover metadata only; does not load instructions."""
        skills = await self._extension.list_skills()
        return [
            {
                "id": f"mcp:{self.server_name}:{skill.uri}",
                "name": skill.frontmatter["name"],
                "description": skill.frontmatter["description"],
                "uri": str(skill.uri),
            }
            for skill in skills
        ]

    async def load(self, uri: str) -> str:
        """Load the SKILL.md named by its URI, with integrity verification."""
        return await self.read_resource(uri, uri)

    async def read_resource(self, skill_uri: str, resource_uri: str) -> str:
        """Read only a declared UTF-8 resource; verify size and SHA-256."""
        skill = await self._extension.get_skill(skill_uri)
        if str(skill.uri) != skill_uri:
            raise ValueError("MCP Skill URI mismatch")
        if isinstance(skill.resources, str):
            raise ValueError("Dynamic MCP Skill resources cannot be verified")
        resource = next((r for r in skill.resources if str(r.uri) == resource_uri), None)
        if resource is None:
            raise ValueError("Resource is not declared by this MCP Skill")
        if resource.size > _MAX_BYTES:
            raise ValueError("MCP Skill resource exceeds size limit")
        response = await self._client.read_resource(resource_uri)
        if len(response.contents) != 1:
            raise ValueError("Expected one MCP text resource")
        content = response.contents[0]
        if str(content.uri) != resource_uri or not isinstance(getattr(content, "text", None), str):
            raise ValueError("Unexpected MCP resource URI or content type")
        data = content.text.encode("utf-8")
        if len(data) > _MAX_BYTES or len(data) != resource.size:
            raise ValueError("MCP Skill resource size mismatch")
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        if digest != resource.digest:
            raise ValueError("MCP Skill resource checksum mismatch")
        return content.text

    def register(self, registry: ToolRegistry) -> None:
        """Expose optional remote Skill readers as server-namespaced Python tools."""
        prefix = f"skills.mcp.{self.server_name}"

        @tool(name=f"{prefix}.list")
        async def list_skills() -> list[dict[str, str]]:
            """List skills offered by this MCP server."""
            return await self.list()

        @tool(name=f"{prefix}.load")
        async def load_skill(uri: str) -> str:
            """Load a remote Skill's instructions by its SKILL.md URI."""
            return await self.load(uri)

        @tool(name=f"{prefix}.read_resource")
        async def read_skill_resource(skill_uri: str, resource_uri: str) -> str:
            """Read a declared text resource belonging to a remote Skill."""
            return await self.read_resource(skill_uri, resource_uri)

        for definition in (list_skills, load_skill, read_skill_resource):
            registry.register(definition)
