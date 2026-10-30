"""Export a local SkillCatalog through the official MCP Skills extension."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from urllib.parse import quote
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_tools_skills import SkillCatalog


def create_skills_server(catalog: SkillCatalog, name: str = "agent-tools-skills"):
    """Create a snapshot MCP server for explicitly selected local text Skills."""
    from mcp.server import MCPServer
    from mcp.server.mcpserver.resources import TextResource
    from mcp.server.skills import Skills
    from mcp.shared.exceptions import MCPError
    from mcp.shared.skills import GetSkillResult, ListSkillsResult, Skill, SkillResource
    from mcp.types import INVALID_PARAMS

    entries = {}
    resources = []
    for item in catalog.list():
        manifest = []
        for path in catalog.resource_paths(item.id):
            uri = f"skill://{item.name}/{quote(path, safe='/')}"
            content = catalog.read_resource(item.id, path)
            data = content.encode("utf-8")
            manifest.append(SkillResource(
                uri=uri, digest="sha256:" + hashlib.sha256(data).hexdigest(),
                size=len(data),
            ))
            resources.append(TextResource(
                uri=uri, name=PurePosixPath(path).name,
                mime_type="text/markdown" if path.endswith(".md") else "text/plain",
                text=content,
            ))
        skill_uri = f"skill://{item.name}/SKILL.md"
        entries[skill_uri] = Skill(
            uri=skill_uri,
            frontmatter={"name": item.name, "description": item.description},
            resources=manifest,
        )

    async def list_skills(ctx, params):
        return ListSkillsResult(skills=list(entries.values()))

    async def get_skill(ctx, params):
        skill = entries.get(str(params.uri))
        if skill is None:
            raise MCPError(code=INVALID_PARAMS, message="Unknown Skill URI")
        return GetSkillResult(skill=skill)

    server = MCPServer(name, extensions=[Skills(list_skills=list_skills, get_skill=get_skill)])
    for resource in resources:
        server.add_resource(resource)
    return server
