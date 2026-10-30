"""CLI and packaged native provider smoke tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agent_tools import App, PythonProvider, ToolExecutor, ToolRegistry
from agent_tools.cli import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "apps" / "reviewer"


def test_installed_native_plugin_via_app(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hello", encoding="utf-8")
    registry = ToolRegistry()
    assert asyncio.run(registry.load_app(App("fs", "Filesystem", providers=[PythonProvider(["filesystem"])]))) == [
        "fs.list_directory", "fs.read_text"
    ]
    executor = ToolExecutor(registry)
    assert executor.run("fs.read_text", {"path": str(f)}).output == "hello"
    assert executor.run("fs.list_directory", {"path": str(tmp_path)}).output == ["hello.txt"]


def test_cli_lists_apps_tools_and_context(capsys):
    base = ["--app", str(EXAMPLE)]
    assert main(base + ["apps"]) == 0
    assert "reviewer" in capsys.readouterr().out
    assert main(base + ["list", "--for-app", "reviewer"]) == 0
    assert "skills.reviewer.review-changes" in capsys.readouterr().out
    assert main(base + ["inspect", "skills.reviewer.review-changes"]) == 0
    assert json.loads(capsys.readouterr().out)["input_schema"]["type"] == "object"
    assert main(base + ["context", "reviewer"]) == 0
    context = json.loads(capsys.readouterr().out)
    assert context["prompts"] == ["review-summary"]
    assert "Reviewer application" in context["instructions"]
    assert main(base + ["inspect", "missing"]) == 1
    assert "Unknown tool" in capsys.readouterr().err


def test_cli_app_metadata_does_not_connect_to_remote_mcp(capsys):
    github = EXAMPLE.parent / "github"
    assert main(["--app", str(github), "apps"]) == 0
    assert "github" in capsys.readouterr().out
    assert main(["--app", str(github), "context", "github"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert "GitHub application" in value["instructions"]
    assert value["prompts"] == ["triage"]
