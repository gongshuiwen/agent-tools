"""A small application bundle: metadata, providers and lazy text context."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .provider import ToolProvider

_APP_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SERVER_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_PROMPT_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")
_MAX_TEXT_BYTES = 1024 * 1024


def _text(path: Path, root: Path) -> str:
    """Read only a small, regular UTF-8 file inside the bundle root."""
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"Invalid or out-of-bundle file: {path}")
    if resolved.stat().st_size > _MAX_TEXT_BYTES:
        raise ValueError(f"Application text file exceeds 1 MiB: {path}")
    return resolved.read_text(encoding="utf-8")


@dataclass(slots=True)
class App:
    """Group related tools, skills and context under one application identity.

    ``from_path`` understands portable ``plugin.json``, optional ``mcp.json``
    and ``skills/``. ``instructions.md``, ``prompts/`` and ``resources/`` are
    simple Agent-Tools conventions, read only when explicitly requested.
    """

    name: str
    description: str
    providers: list[ToolProvider] = field(default_factory=list)
    version: str = "0.0.0"
    root: Path | None = None
    instructions: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _APP_NAME.fullmatch(self.name):
            raise ValueError(f"Invalid application name: {self.name!r}")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Application description is required")
        if not isinstance(self.version, str) or not self.version:
            raise ValueError("Application version must be a string")
        if self.root is not None:
            self.root = Path(self.root).resolve()

    @classmethod
    def from_path(cls, path: str | Path) -> App:
        """Load a bundle without connecting to an MCP server or executing skills."""
        root = Path(path).resolve()
        manifest = json.loads(_text(root / "plugin.json", root))
        if not isinstance(manifest, dict):
            raise ValueError("plugin.json must contain a JSON object")
        name = manifest.get("name")
        description = manifest.get("description")
        version = manifest.get("version", "0.0.0")
        # Validate the app identity before building providers.
        app = cls(name=name, description=description, version=version, root=root)

        mcp_file = root / "mcp.json"
        if mcp_file.exists():
            from agent_tools_mcp import McpProvider

            config = json.loads(_text(mcp_file, root))
            servers = config.get("mcpServers") if isinstance(config, dict) else None
            if not isinstance(servers, dict):
                raise ValueError("mcp.json must declare an mcpServers object")
            for alias, server in servers.items():
                if not isinstance(alias, str) or not _SERVER_NAME.fullmatch(alias):
                    raise ValueError(f"Invalid MCP server name: {alias!r}")
                if not isinstance(server, dict):
                    raise ValueError(f"Invalid MCP configuration for {alias!r}")
                transport = server.get("type")
                if transport in ("streamable-http", "http"):
                    url = server.get("url")
                    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                        raise ValueError(f"MCP server {alias!r} requires an HTTP(S) URL")
                elif transport == "stdio":
                    if not isinstance(server.get("command"), str) or not server["command"]:
                        raise ValueError(f"MCP server {alias!r} requires a command")
                    if not isinstance(server.get("args", []), list) or not all(
                        isinstance(item, str) for item in server.get("args", [])
                    ):
                        raise ValueError(f"MCP server {alias!r} args must be strings")
                    env = server.get("env")
                    if env is not None and (
                        not isinstance(env, dict)
                        or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())
                    ):
                        raise ValueError(f"MCP server {alias!r} env must be string pairs")
                else:
                    raise ValueError(f"Unsupported MCP transport for {alias!r}: {transport!r}")
                app.providers.append(McpProvider(alias, server))

        skills_dir = root / "skills"
        if skills_dir.is_dir():
            from agent_tools_skills import SkillProvider

            if not skills_dir.resolve().is_relative_to(root):
                raise ValueError("skills/ escapes the application directory")
            app.providers.append(SkillProvider([skills_dir], namespace=app.name))
        return app

    def read_instructions(self) -> str:
        """Return application-level guidance on demand; never a system prompt."""
        if self.instructions is not None:
            return self.instructions
        if self.root is not None and (self.root / "instructions.md").exists():
            return _text(self.root / "instructions.md", self.root)
        return ""

    def list_prompts(self) -> list[str]:
        if self.root is None or not (self.root / "prompts").exists():
            return []
        folder = (self.root / "prompts").resolve()
        if not folder.is_relative_to(self.root) or not folder.is_dir():
            raise ValueError("prompts/ escapes the application directory")
        return sorted(
            path.stem for path in folder.glob("*.md")
            if _PROMPT_NAME.fullmatch(path.stem)
            and path.resolve().is_relative_to(self.root)
            and path.resolve().is_file()
        )

    def read_prompt(self, name: str) -> str:
        if not isinstance(name, str) or not _PROMPT_NAME.fullmatch(name):
            raise ValueError("Prompt name must contain only letters, numbers, '_' or '-'")
        if self.root is None:
            raise ValueError("This application has no prompt directory")
        return _text(self.root / "prompts" / f"{name}.md", self.root)

    def read_resource(self, path: str) -> str:
        """Read a bundled UTF-8 resource, but never execute it."""
        if self.root is None or not isinstance(path, str) or not path:
            raise ValueError("This application has no resources or the path is empty")
        if "\\" in path or any(part in ("", ".", "..") for part in path.split("/")):
            raise ValueError("Resource must be a relative path under resources/")
        return _text(self.root / "resources" / path, self.root)
