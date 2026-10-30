"""Integration checks with actual installed package entry points."""

from __future__ import annotations

import json

from agent_tools import ToolExecutor, ToolRegistry
from agent_tools.cli import main


def test_installed_filesystem_plugin_and_execution(tmp_path):
    file = tmp_path / "hello.txt"
    file.write_text("Hello Agent-Tools", encoding="utf-8")

    registry = ToolRegistry()
    assert registry.load_plugins(["filesystem"]) == ["filesystem"]
    assert registry.load_plugins(["filesystem"]) == []
    assert [t.name for t in registry.list_tools()] == ["fs.list_directory", "fs.read_text"]

    executor = ToolExecutor(registry)
    listed = executor.run("fs.list_directory", {"path": str(tmp_path)})
    assert listed.ok and listed.output == ["hello.txt"]
    read = executor.run("fs.read_text", {"path": str(file)})
    assert read.ok and read.output == "Hello Agent-Tools"

    missing = executor.run("fs.read_text", {"path": str(tmp_path / "missing.txt")})
    assert not missing.ok and missing.error.code == "execution_error"


def test_cli_list_and_inspect(capsys):
    assert main(["list"]) == 0
    stdout = capsys.readouterr().out
    assert "fs.read_text" in stdout
    assert "fs.list_directory" in stdout

    assert main(["inspect", "fs.read_text"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["name"] == "fs.read_text"
    assert value["input_schema"]["properties"]["path"]["type"] == "string"

    assert main(["inspect", "no.such.tool"]) == 1
    assert "Unknown tool" in capsys.readouterr().err


def test_cli_can_disable_plugin_loading(capsys):
    assert main(["--no-plugins", "list"]) == 0
    assert capsys.readouterr().out == ""
