"""SEP-2640 imports: manifest scope, source identity and integrity checks."""

from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

import pytest

from agent_tools import ToolExecutor, ToolRegistry
from agent_tools_mcp import RemoteSkills

URI = "skill://code-review/SKILL.md"
CONTENT = "---\nname: code-review\ndescription: Check code\n---\nReview carefully\n"


class FakeSkillsExtension:
    def __init__(self, *, digest=None, size=None, resources=None):
        self.skill = SimpleNamespace(
            uri=URI,
            frontmatter={"name": "code-review", "description": "Check code"},
            resources=resources if resources is not None else [SimpleNamespace(
                uri=URI,
                digest=digest if digest is not None else "sha256:" + hashlib.sha256(CONTENT.encode()).hexdigest(),
                size=size if size is not None else len(CONTENT.encode()),
            )],
        )

    async def list_skills(self):
        return [self.skill]

    async def get_skill(self, uri):
        assert uri == URI
        return self.skill


class FakeResourceClient:
    def __init__(self, text=CONTENT, uri=URI):
        self.text, self.uri = text, uri
        self.reads = []

    async def read_resource(self, uri):
        self.reads.append(uri)
        return SimpleNamespace(contents=[SimpleNamespace(uri=self.uri, text=self.text)])


def test_remote_skills_discover_load_and_tools():
    async def scenario():
        client = FakeResourceClient()
        remote = RemoteSkills("test", client, FakeSkillsExtension())
        listed = await remote.list()
        assert listed == [{
            "id": "mcp:test:skill://code-review/SKILL.md", "name": "code-review",
            "description": "Check code", "uri": URI,
        }]
        registry = ToolRegistry()
        remote.register(registry)
        executor = ToolExecutor(registry)
        result = await executor.execute("skills.mcp.test.load", {"uri": URI})
        assert result.ok and result.output == CONTENT
        assert client.reads == [URI]
        assert [t.name for t in registry.list_tools()] == [
            "skills.mcp.test.list", "skills.mcp.test.load", "skills.mcp.test.read_resource",
        ]

    asyncio.run(scenario())


@pytest.mark.parametrize("extension,client,error", [
    (FakeSkillsExtension(digest="sha256:" + "0" * 64), FakeResourceClient(), "checksum"),
    (FakeSkillsExtension(size=1), FakeResourceClient(), "size mismatch"),
    (FakeSkillsExtension(size=256 * 1024 + 1), FakeResourceClient(), "size limit"),
    (FakeSkillsExtension(), FakeResourceClient(uri="skill://other/SKILL.md"), "Unexpected"),
    (FakeSkillsExtension(resources="dynamic"), FakeResourceClient(), "Dynamic"),
])
def test_remote_skills_fail_closed(extension, client, error):
    remote = RemoteSkills("test", client, extension)

    async def scenario():
        with pytest.raises(ValueError, match=error):
            await remote.load(URI)

    asyncio.run(scenario())


def test_remote_skills_cannot_read_undeclared_resource():
    async def scenario():
        client = FakeResourceClient()
        remote = RemoteSkills("test", client, FakeSkillsExtension())
        with pytest.raises(ValueError, match="not declared"):
            await remote.read_resource(URI, "skill://other/SKILL.md")
        assert client.reads == []

    asyncio.run(scenario())
