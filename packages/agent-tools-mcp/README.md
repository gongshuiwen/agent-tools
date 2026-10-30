# agent-tools-mcp

MCP v2 adapters (Skills bridge requires SDK support newer than PyPI 2.3.0): import server Tools, read remote Skills, export an explicitly selected ToolRegistry as an MCP Server, and expose a SkillCatalog through SEP-2640.

- `MCPProvider(name, server, skills=True)` enables `provider.skills.list/load/read_resource`.
- `provider.skills.register(registry)` adds namespaced `skills.mcp.<name>.*` readers.
- `create_tools_server(registry, include=["..."])` exports chosen tools; `authorize(ctx, name, args)` can deny each call. Provider errors are masked unless `expose_remote_errors=True`.
- `create_skills_server(catalog)` exports a snapshot of local UTF-8 resources with SHA-256 manifests.

The host must provide authentication, trusted plugin configuration, and sandboxing. Authorization is an optional callback, not an identity provider.
See the repository [README](../../README.md).
