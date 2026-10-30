"""Application-scoped Skills load instructions but never run workflows."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_tools import App, DuplicateToolError, ToolExecutor, ToolRegistry
from agent_tools_skills import SkillProvider


def make_skill(root: Path, name: str = "code-review") -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Reviews code changes using references.\n---\n"
        "# Review\n\nRead references/checklist.md\n",
        encoding="utf-8",
    )
    (skill / "references").mkdir()
    (skill / "references" / "checklist.md").write_text("Be careful.", encoding="utf-8")
    return skill


def load_skill_app(root: Path) -> ToolExecutor:
    registry = ToolRegistry()
    asyncio.run(registry.load_app(App("reviewer", "Review", providers=[
        SkillProvider([root], namespace="reviewer")
    ])))
    return ToolExecutor(registry)


def test_skill_is_scoped_to_application_and_lazy(tmp_path):
    skill = make_skill(tmp_path)
    executor = load_skill_app(tmp_path)
    name = "skills.reviewer.code-review"
    assert executor.registry.get(name).input_schema["properties"]["resource"]
    (skill / "SKILL.md").write_text((skill / "SKILL.md").read_text() + "\nUpdated instruction")
    result = executor.run(name, {})
    assert result.ok and "Updated instruction" in result.output["instructions"]
    content = executor.run(name, {"resource": "references/checklist.md"})
    assert content.ok and content.output["content"] == "Be careful."


def test_skill_resource_paths_are_confined(tmp_path):
    skill = make_skill(tmp_path)
    (skill / "references" / "escape.md").symlink_to(tmp_path / "outside.txt")
    (tmp_path / "outside.txt").write_text("SECRET", encoding="utf-8")
    executor = load_skill_app(tmp_path)
    for resource in ["../outside.txt", "/etc/passwd", "references/../outside.txt",
                     "SKILL.md", "references\\leak", "references/escape.md"]:
        result = executor.run("skills.reviewer.code-review", {"resource": resource})
        assert not result.ok and result.error.code == "execution_error", resource
        assert "SECRET" not in result.error.message


def test_no_script_execution(tmp_path):
    skill = make_skill(tmp_path)
    (skill / "scripts").mkdir()
    (skill / "scripts" / "command.sh").write_text("echo dangerous", encoding="utf-8")
    executor = load_skill_app(tmp_path)
    result = executor.run("skills.reviewer.code-review", {"resource": "scripts/command.sh"})
    assert result.ok and result.output["content"] == "echo dangerous"


def test_duplicates_and_invalid_frontmatter_fail_atomically(tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    make_skill(one)
    make_skill(two)
    registry = ToolRegistry()
    app = App("reviewer", "Review", providers=[SkillProvider([one, two], namespace="reviewer")])
    with pytest.raises(DuplicateToolError):
        asyncio.run(registry.load_app(app))
    assert registry.list_apps() == []
    (one / "code-review" / "SKILL.md").write_text(
        (one / "code-review" / "SKILL.md").read_text().replace("name: code-review", "name: Wrong")
    )
    with pytest.raises(ValueError, match="Invalid skill name"):
        asyncio.run(registry.load_app(App("reviewer", "Review", providers=[
            SkillProvider([one], namespace="reviewer")
        ])))


def test_symlinked_skill_instructions_outside_are_rejected(tmp_path):
    skill = make_skill(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("SECRET", encoding="utf-8")
    (skill / "SKILL.md").unlink()
    (skill / "SKILL.md").symlink_to(outside)
    with pytest.raises(ValueError, match="escape"):
        load_skill_app(tmp_path)
