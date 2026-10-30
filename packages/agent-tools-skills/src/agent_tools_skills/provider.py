"""Expose ordinary Agent Skills directories through the Tool interface."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from agent_tools import Tool

_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RESOURCE_FOLDERS = {"assets", "references", "scripts"}
_MAX_TEXT_BYTES = 1024 * 1024


def _read_text(path: Path) -> str:
    if path.stat().st_size > _MAX_TEXT_BYTES:
        raise ValueError(f"Skill file is too large: {path}")
    return path.read_text(encoding="utf-8")


def _read_skill(path: Path) -> tuple[str, str, str]:
    if not path.resolve().is_relative_to(path.parent.resolve()):
        raise ValueError(f"Skill instructions escape their directory: {path}")
    text = _read_text(path).replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError(f"Skill must begin with YAML frontmatter: {path}")
    frontmatter, separator, body = text[4:].partition("\n---\n")
    if not separator:
        raise ValueError(f"Skill has no closing frontmatter delimiter: {path}")
    data = yaml.safe_load(frontmatter)
    if not isinstance(data, dict):
        raise ValueError(f"Skill frontmatter must be a mapping: {path}")
    name, description = data.get("name"), data.get("description")
    if not isinstance(name, str) or len(name) > 64 or not _SKILL_NAME.fullmatch(name):
        raise ValueError(f"Invalid skill name: {name!r}")
    if name != path.parent.name:
        raise ValueError(f"Skill name must match directory name: {path}")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        raise ValueError(f"Invalid skill description: {path}")
    return name, description.strip(), body.strip()


def _read_resource(root: Path, resource: str) -> str:
    # Never open paths outside the skill's resource directories. Symlinks are
    # checked after resolution; scripts are only read as text, never executed.
    parts = resource.split("/")
    if (
        not resource
        or "\\" in resource
        or len(parts) < 2
        or parts[0] not in _RESOURCE_FOLDERS
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise ValueError("Resource must be a relative path under references/, scripts/ or assets/")
    resolved_root = root.resolve()
    target = (resolved_root / resource).resolve()
    if not target.is_relative_to(resolved_root) or not target.is_file():
        raise ValueError("Resource is missing or escapes the skill directory")
    return _read_text(target)


def _make_loader(root: Path):
    def load_skill(resource: str | None = None) -> dict[str, str]:
        """Load a skill's instructions, or one bundled UTF-8 resource."""
        if resource is None:
            name, _, instructions = _read_skill(root / "SKILL.md")
            return {"name": name, "instructions": instructions}
        return {"resource": resource, "content": _read_resource(root, resource)}

    return load_skill


@dataclass
class SkillProvider:
    """Discover skills in supplied folders; no scripts or workflows are run."""

    paths: list[str | Path]
    namespace: str

    async def discover(self) -> list[Tool]:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.namespace):
            raise ValueError(f"Invalid skill namespace: {self.namespace!r}")
        roots: list[Path] = []
        for path in self.paths:
            folder = Path(path)
            if not folder.is_dir():
                raise ValueError(f"Skill directory does not exist: {folder}")
            if (folder / "SKILL.md").is_file():
                roots.append(folder)
            else:
                roots.extend(
                    child for child in sorted(folder.iterdir())
                    if child.is_dir() and (child / "SKILL.md").is_file()
                )

        tools: list[Tool] = []
        for root in roots:
            if root.is_symlink():
                raise ValueError(f"Skill directory symlink is not allowed: {root}")
            name, description, _ = _read_skill(root / "SKILL.md")

            tools.append(
                Tool.from_callable(_make_loader(root), name=f"skills.{self.namespace}.{name}", description=description)
            )
        return tools
