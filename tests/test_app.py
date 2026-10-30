"""Portable application bundle layout, metadata and lazy context reads."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_tools import App, ToolExecutor, ToolRegistry
from agent_tools_mcp import McpProvider
from agent_tools_skills import SkillProvider

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "apps"


def make_bundle(tmp_path, name="example"):
    root = tmp_path / name
    root.mkdir()
    (root / "plugin.json").write_text(json.dumps({
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": name,
        "version": "1.2.3",
        "description": "Example app",
    }), encoding="utf-8")
    return root


def test_portable_app_parses_and_loads_skill_tools():
    app = App.from_path(EXAMPLES / "reviewer")
    assert (app.name, app.description, app.version) == (
        "reviewer", "Local code-review workflows and reference material", "0.3.0"
    )
    assert len(app.providers) == 1
    assert isinstance(app.providers[0], SkillProvider)
    assert app.list_prompts() == ["review-summary"]
    assert "Reviewer application" in app.read_instructions()
    assert "Summarize" in app.read_prompt("review-summary")
    assert "read-only" in app.read_resource("README.md")

    registry = ToolRegistry()
    assert asyncio.run(registry.load_app(app)) == ["skills.reviewer.review-changes"]
    result = ToolExecutor(registry).run("skills.reviewer.review-changes", {})
    assert result.ok and "# Review changes" in result.output["instructions"]


def test_github_bundle_contains_mcp_and_skills_without_connecting():
    app = App.from_path(EXAMPLES / "github")
    assert app.name == "github"
    assert len(app.providers) == 2
    assert isinstance(app.providers[0], McpProvider)
    assert app.providers[0].name == "github"
    assert app.providers[0].target["type"] == "streamable-http"
    assert isinstance(app.providers[1], SkillProvider)
    assert "GitHub MCP" in app.read_instructions()
    assert app.list_prompts() == ["triage"]


def test_application_context_is_read_on_demand(tmp_path):
    root = make_bundle(tmp_path)
    (root / "instructions.md").write_text("First version")
    (root / "prompts").mkdir()
    (root / "prompts" / "triage.md").write_text("First prompt")
    app = App.from_path(root)
    (root / "instructions.md").write_text("Updated version")
    (root / "prompts" / "triage.md").write_text("Updated prompt")
    assert app.read_instructions() == "Updated version"
    assert app.read_prompt("triage") == "Updated prompt"
    assert app.list_prompts() == ["triage"]


def test_programmatic_app_can_have_inline_instructions():
    app = App(name="python", description="Python tools", instructions="Use native tools")
    assert app.read_instructions() == "Use native tools"
    assert app.list_prompts() == []


def test_invalid_manifest_and_mcp_configuration(tmp_path):
    root = make_bundle(tmp_path)
    (root / "plugin.json").write_text(json.dumps({"name": "BAD NAME", "description": "yes"}))
    with pytest.raises(ValueError, match="Invalid application name"):
        App.from_path(root)
    (root / "plugin.json").write_text(json.dumps({"name": "example", "description": "yes"}))
    (root / "mcp.json").write_text(json.dumps({"mcpServers": {"github": {
        "type": "streamable-http", "url": "ftp://unsafe"
    }}}))
    with pytest.raises(ValueError, match="HTTP"):
        App.from_path(root)
    (root / "mcp.json").write_text(json.dumps({"mcpServers": {"github": {
        "type": "socket", "url": "https://example.com"
    }}}))
    with pytest.raises(ValueError, match="Unsupported MCP transport"):
        App.from_path(root)
    (root / "mcp.json").write_text(json.dumps({"mcpServers": {"local": {
        "type": "stdio", "command": "python", "args": ["server.py"]
    }}}))
    app = App.from_path(root)
    assert app.providers[0].target["args"] == ["server.py"]


def test_prompt_and_resource_file_traversal_and_symlink_escape(tmp_path):
    root = make_bundle(tmp_path)
    (root / "prompts").mkdir()
    (root / "resources").mkdir()
    secret = tmp_path / "secret.md"
    secret.write_text("SECRET")
    (root / "prompts" / "leak.md").symlink_to(secret)
    (root / "resources" / "leak.md").symlink_to(secret)
    (root / "instructions.md").symlink_to(secret)
    app = App.from_path(root)
    assert app.list_prompts() == []
    with pytest.raises(ValueError):
        app.read_prompt("../secret")
    with pytest.raises(ValueError):
        app.read_prompt("leak")
    with pytest.raises(ValueError):
        app.read_resource("../secret.md")
    with pytest.raises(ValueError):
        app.read_resource("leak.md")
    with pytest.raises(ValueError):
        app.read_instructions()


def test_disallowed_symlink_skills_dir(tmp_path):
    root = make_bundle(tmp_path)
    external = tmp_path / "outside"
    external.mkdir()
    (root / "skills").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        App.from_path(root)


def test_large_text_file_is_rejected(tmp_path):
    root = make_bundle(tmp_path)
    (root / "instructions.md").write_bytes(b"a" * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        App.from_path(root).read_instructions()
