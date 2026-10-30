# agent-tools-mcp

MCP v2 adapters (Skills bridge requires SDK support newer than PyPI 2.3.0): import server Tools, read remote Skills, export an explicitly selected ToolRegistry as an MCP Server, and expose a SkillCatalog through SEP-2640.

- `MCPProvider(name, server, skills=True)` enables `provider.skills.list/load/read_resource`.
- `provider.skills.register(registry)` adds namespaced `skills.mcp.<name>.*` readers.
- `create_tools_server(registry, include=["..."])` exports chosen tools and exact schemas.
- `create_skills_server(catalog)` exports a snapshot of local UTF-8 resources with SHA-256 manifests.

Skill execution, authorization and sandboxing are out of scope.
See the repository [README](../../README.md).
