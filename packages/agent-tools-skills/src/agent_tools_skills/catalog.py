"""Local Agent Skills discovery and progressive content loading (no execution)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from agent_tools import ToolRegistry, tool

_MAX_BYTES = 256 * 1024
_MAX_FRONTMATTER = 16 * 1024
_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


@dataclass(frozen=True)
class SkillSpec:
    id: str
    name: str
    description: str
    location: Path


class SkillCatalog:
    """Only explicitly selected local skill directories are scanned."""

    def __init__(self, skills: Iterable[SkillSpec] = ()) -> None:
        self._skills: dict[str, SkillSpec] = {}
        for skill in skills:
            if skill.id in self._skills:
                raise ValueError(f"Duplicate skill: {skill.id}")
            self._skills[skill.id] = skill

    @classmethod
    def from_paths(cls, paths: Iterable[str | Path]) -> SkillCatalog:
        skills = []
        for path in paths:
            base = Path(path)
            if not base.is_dir() or base.is_symlink():
                raise ValueError(f"Invalid skill directory: {base}")
            directories = ([base] if (base / "SKILL.md").is_file()
                           else sorted(p for p in base.iterdir() if p.is_dir() and not p.is_symlink()))
            for directory in directories:
                instructions = directory / "SKILL.md"
                if not instructions.is_file() or instructions.is_symlink():
                    continue
                metadata = _frontmatter(instructions)
                name = metadata.get("name")
                description = metadata.get("description")
                if (not isinstance(name, str) or len(name) > 64
                        or not _NAME.fullmatch(name) or name != directory.name):
                    raise ValueError(f"Invalid skill name in {instructions}")
                if not isinstance(description, str) or not 0 < len(description) <= 1024:
                    raise ValueError(f"Invalid skill description in {instructions}")
                skills.append(SkillSpec(f"local:{name}", name, description, directory.resolve()))
        return cls(skills)

    def list(self) -> list[SkillSpec]:
        return [self._skills[key] for key in sorted(self._skills)]

    def load(self, skill_id: str) -> str:
        return self.read_resource(skill_id, "SKILL.md")

    def resource_paths(self, skill_id: str) -> list[str]:
        """Enumerate explicit, non-hidden regular files without following symlinks."""
        base = self._skills[skill_id].location
        return sorted(
            path.relative_to(base).as_posix()
            for path in base.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and path.resolve().is_relative_to(base)
            and not any(part.startswith(".") for part in path.relative_to(base).parts)
        )

    def read_resource(self, skill_id: str, path: str) -> str:
        """Read a small UTF-8 resource, rejecting traversal and symlink escapes."""
        base = self._skills[skill_id].location
        parts = Path(path).parts
        if (not path or "\\" in path or Path(path).is_absolute() or ".." in parts
                or any(part.startswith(".") for part in parts)):
            raise ValueError("Unsafe skill resource path")
        current = base
        for part in parts:
            current /= part
            if current.is_symlink():
                raise ValueError("Unsafe skill resource path: symlinks are not allowed")
        target = current.resolve(strict=True)
        if not target.is_relative_to(base) or not target.is_file():
            raise ValueError("Skill resource is outside its directory or not a file")
        if target.stat().st_size > _MAX_BYTES:
            raise ValueError("Skill resource exceeds size limit")
        with target.open("rb") as file:
            data = file.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise ValueError("Skill resource exceeds size limit")
        return data.decode("utf-8")

    def register(self, registry: ToolRegistry) -> None:
        """Expose three discovery/read operations as ordinary Python tools."""

        @tool(name="skills.list")
        def list_skills() -> list[dict[str, str]]:
            """List available skills by ID, name and description."""
            return [{"id": s.id, "name": s.name, "description": s.description}
                    for s in self.list()]

        @tool(name="skills.load")
        def load_skill(skill_id: str) -> str:
            """Read a skill's SKILL.md instructions when needed."""
            return self.load(skill_id)

        @tool(name="skills.read_resource")
        def read_skill_resource(skill_id: str, path: str) -> str:
            """Read a UTF-8 file relative to a selected skill directory."""
            return self.read_resource(skill_id, path)

        for definition in (list_skills, load_skill, read_skill_resource):
            registry.register(definition)


def _frontmatter(file: Path) -> dict:
    with file.open("r", encoding="utf-8") as reader:
        if reader.readline().strip() != "---":
            raise ValueError(f"Missing YAML frontmatter in {file}")
        lines = []
        size = 0
        for line in reader:
            if line.strip() == "---":
                value = yaml.safe_load("".join(lines))
                if not isinstance(value, dict):
                    raise ValueError(f"Invalid YAML frontmatter in {file}")
                return value
            size += len(line.encode("utf-8"))
            if size > _MAX_FRONTMATTER:
                raise ValueError("Skill frontmatter exceeds size limit")
            lines.append(line)
    raise ValueError(f"Unclosed YAML frontmatter in {file}")
