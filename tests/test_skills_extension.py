"""Optional real MCP SDK Skills bridge roundtrip (requires mcp>=2)."""

from __future__ import annotations

import asyncio
import hashlib

import pytest

from agent_tools_mcp import MCPProvider, create_skills_server
from agent_tools_skills import SkillCatalog


def test_exported_local_resources_skip_hidden_symlinks(tmp_path):
    skill = tmp_path / "code-review"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: code-review\ndescription: Code reviews\n---\nReview\n", encoding="utf-8"
    )
    (skill / "references").mkdir()
    (skill / "references/check.md").write_text("Checklist", encoding="utf-8")
    (skill / ".secrets").write_text("hidden", encoding="utf-8")
    (skill / "linked.txt").symlink_to(skill / "references/check.md")
    catalog = SkillCatalog.from_paths([tmp_path])
    assert catalog.resource_paths("local:code-review") == [
        "SKILL.md", "references/check.md",
    ]


def test_real_sdk_skills_roundtrip(tmp_path):
    pytest.importorskip("mcp", minversion="2.0")
    skill = tmp_path / "code-review"
    skill.mkdir()
    data = "---\nname: code-review\ndescription: Code reviews\n---\nReview\n"
    (skill / "SKILL.md").write_text(data, encoding="utf-8")
    catalog = SkillCatalog.from_paths([tmp_path])
    server = create_skills_server(catalog)

    async def scenario():
        async with MCPProvider("catalog", server, skills=True) as provider:
            remote = provider.skills
            descriptions = await remote.list()
            assert descriptions[0]["name"] == "code-review"
            assert descriptions[0]["uri"] == "skill://code-review/SKILL.md"
            content = await remote.load("skill://code-review/SKILL.md")
            assert hashlib.sha256(content.encode()).hexdigest() == hashlib.sha256(data.encode()).hexdigest()
            assert content == data

    asyncio.run(scenario())
