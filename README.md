# Agent-Tools v0.3

**App → Provider → Tool**. A small, framework-agnostic Python toolkit. An **App** bundles related MCP tools, Agent Skills, local Python tools, and optional application instructions, prompts and resources. All executable tool interfaces live in a **single `ToolRegistry`** and use a **single `ToolExecutor`**. No Agent runtime, UI, marketplace, secrets manager or dedicated skill/MCP registry.

## Design

```text
App (name, description, instructions, prompts, resources)
  └── providers: PythonProvider | McpProvider | SkillProvider
        └── ToolRegistry (one name space)
               └── ToolExecutor (one call API)

fs.read_text                    Native Python tool
mcp.github.search_repositories  Remote MCP tool (example)
skills.github.review-pr         Lazy SKILL.md loader
```

- `App.from_path(path)` reads a portable root `plugin.json`, optional `mcp.json` and `skills/`. It does not connect to MCP or run scripts.
- `await registry.load_app(app)` discovers every provider and **atomically** registers the app and all its tools; duplicate tool or app names fail without partial registration. This connects to any configured MCP servers to discover their tools.
- `registry.list_apps()`, `registry.get_app(name)`, `registry.list_tools(app=name)` expose app metadata and grouped tools.
- `app.read_instructions()`, `app.list_prompts()`, `app.read_prompt(name)` and `app.read_resource(path)` load **read-only text on demand**. They do not change an Agent's instruction hierarchy. CLI `apps` and `context` work offline without MCP discovery.
- `ToolExecutor.execute(name, arguments)` works equally for native, MCP and Skill tools and returns `ToolResult`.

### Portable app folder

```text
my-app/
  plugin.json             Required portable Agent Plugins manifest
  mcp.json                Optional portable MCP server definitions
  skills/
    review-pr/SKILL.md    Optional Agent Skills
  instructions.md         Optional Agent-Tools convention
  prompts/triage.md       Optional Agent-Tools convention
  resources/guide.md      Optional Agent-Tools convention
```

The identity fields of `plugin.json` are `name`, `description`, and `version`; optional standard fields such as `$schema`, `author`, and `extensions` may be present. This implementation **does not validate the full Agent Plugins manifest schema or implement OpenAI-specific extensions**. `instructions.md`, `prompts/`, `resources/` are local conventions, not standardized Agent Plugins fields.

The optional `mcp.json` supports named Streamable HTTP (`"type": "streamable-http"`, `"url"`) and stdio (`"type": "stdio"`, `"command"`, optional `"args"`, `"env"`) configurations. MCP client connections are opened on tool discovery and on each invocation. This deliberately prioritizes simplicity over connection reuse. Remote MCP Tools retain the original JSON input schema; MCP Resources and Prompts are not imported as tools.

Skills use the standard YAML-frontmatter `SKILL.md` format and are registered as `skills.<app>.<skill>`. An invocation with `{}` reads the skill instructions. With `{"resource":"references/checklist.md"}` it reads an allowed bundled text file. **Skill execution means loading instructions, not performing an Agent workflow**; scripts are not executed.

### Quick start

```bash
uv sync
uv run python examples/app_demo.py
uv run pytest -q

uv run agent-tools --app examples/apps/reviewer apps
uv run agent-tools --app examples/apps/reviewer list --for-app reviewer
uv run agent-tools --app examples/apps/reviewer inspect skills.reviewer.review-changes
uv run agent-tools --app examples/apps/reviewer context reviewer
```

A GitHub example is in `examples/apps/github/`. Its `mcp.json` URL is an intentional **placeholder**, so do not try to load its MCP tools until a trusted working server URL and necessary authentication are configured.

### Python API

```python
from agent_tools import App, ToolExecutor, ToolRegistry

registry = ToolRegistry()
await registry.load_app(App.from_path("./examples/apps/reviewer"))
app = registry.get_app("reviewer")
print(app.read_instructions())
print(app.read_prompt("review-summary"))
print([tool.name for tool in registry.list_tools(app="reviewer")])

result = await ToolExecutor(registry).execute("skills.reviewer.review-changes", {})
print(result.to_dict())
```

A Python-only app uses the same interface, without a separate plugin manager:

```python
from agent_tools import App, PythonProvider

await registry.load_app(App(
    name="filesystem",
    description="Native filesystem tools",
    providers=[PythonProvider(["filesystem"])],
))
```

Native tools use `@tool` as before. A Python plugin's Entry Point in the `agent_tools.plugins` group now points to a zero-argument factory returning an iterable of tools. There is no implicit or global registration.

```toml
[project.entry-points."agent_tools.plugins"]
filesystem = "agent_tools_fs:get_tools"
```

## Packages

| Distribution | Purpose | Dependencies |
| --- | --- | --- |
| `agent-tools-core` | App, Tool, Registry, Executor, PythonProvider, CLI | Pydantic v2 |
| `agent-tools-fs` | Example native tool provider | Core |
| `agent-tools-skills` | SkillProvider | Core, PyYAML |
| `agent-tools-mcp` | McpProvider | Core, MCP Python SDK v2, jsonschema |

Python 3.11+. Use `uv` for workspace dependencies and isolated builds:

```bash
uv build --package agent-tools-core
uv build --package agent-tools-fs
uv build --package agent-tools-skills
uv build --package agent-tools-mcp
```

## Security and scope

Only load trusted apps and MCP server configurations. MCP stdio can execute a subprocess. Python Entry Points execute installed Python code. Neither is sandboxed. Application instructions and skills are **untrusted text**, not system instructions or automatic authorization. Reading them never executes code. Skill, prompt and resource reads are confined to their bundle directories and limited to 1 MiB per file. The example `fs.*` tools are **not restricted to an allowed filesystem root**. Approvals, OAuth, permissions, audit, hot reload, MCP connection pooling, Agent loops and UI are intentionally out of scope.

Tests use deterministic in-process MCP client stubs, plus an optional actual MCP SDK integration test. The latter is skipped if MCP is unavailable in the test environment.
