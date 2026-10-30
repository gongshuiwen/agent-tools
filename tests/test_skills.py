"""Skill discovery, lazy reading, safety boundaries, and tool wrappers."""

from __future__ import annotations

import pytest

from agent_tools import ToolExecutor, ToolRegistry
from agent_tools_skills import SkillCatalog


def make_skill(tmp_path, name="code-review"):
    directory = tmp_path / name
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Review code for correctness\n---\n# Review\nRead references/checks.md\n",
        encoding="utf-8",
    )
    references = directory / "references"
    references.mkdir()
    (references / "checks.md").write_text("Check edge cases", encoding="utf-8")
    return directory


def test_skill_catalog_and_tools(tmp_path):
    make_skill(tmp_path)
    catalog = SkillCatalog.from_paths([tmp_path])
    assert [s.id for s in catalog.list()] == ["local:code-review"]
    assert "# Review" in catalog.load("local:code-review")
    assert catalog.read_resource("local:code-review", "references/checks.md") == "Check edge cases"
    registry = ToolRegistry()
    catalog.register(registry)
    executor = ToolExecutor(registry)
    listed = executor.run("skills.list", {})
    assert listed.ok and listed.output[0]["name"] == "code-review"
    assert executor.run("skills.load", {"skill_id": "local:code-review"}).ok
    assert executor.run("skills.read_resource", {
        "skill_id": "local:code-review", "path": "references/checks.md"
    }).output == "Check edge cases"


def test_skill_rejects_unsafe_resource_paths(tmp_path):
    skill = make_skill(tmp_path)
    catalog = SkillCatalog.from_paths([tmp_path])
    for path in ("../secret.txt", "/etc/passwd", "..\\secret.txt", "references/../../secret"):
        with pytest.raises(ValueError, match="Unsafe"):
            catalog.read_resource("local:code-review", path)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    (skill / "escape.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        catalog.read_resource("local:code-review", "escape.txt")


def test_rejects_invalid_frontmatter_duplicates_and_large_files(tmp_path):
    skill = make_skill(tmp_path)
    (skill / "SKILL.md").write_text("---\nname: other\ndescription: Test\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid skill name"):
        SkillCatalog.from_paths([tmp_path])
    (skill / "SKILL.md").write_text("---\nname: code-review\ndescription: Good\n---\n")
    catalog = SkillCatalog.from_paths([tmp_path])
    (skill / "large.txt").write_bytes(b"X" * (256 * 1024 + 1))
    with pytest.raises(ValueError, match="size limit"):
        catalog.read_resource("local:code-review", "large.txt")
    with pytest.raises(ValueError, match="Duplicate skill"):
        SkillCatalog.from_paths([tmp_path, skill])
