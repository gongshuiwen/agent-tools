# Agent-Tools

**框架无关的 Python 工具层**：统一调用 Python 函数与 MCP Tools，按需读取 Agent Skills。不是 Agent Runtime，也不负责 LLM、审批或沙箱。

## 包

| 包 | 功能 |
| --- | --- |
| `agent-tools-core` | `@tool`、JSON Schema、注册、执行、插件发现 |
| `agent-tools-fs` | 简单只读文件系统示例插件 |
| `agent-tools-mcp` | MCP v2 Tools Client、Skills 导入与导出 |
| `agent-tools-skills` | 本地 `SKILL.md` 技能目录，按需加载内容 |

Python ≥3.11；使用 [uv](https://docs.astral.sh/uv/) 管理工作区。

```bash
uv sync
uv run pytest
uv run python examples/unified.py
uv run agent-tools list
uv run agent-tools inspect fs.read_text
```

`uv.lock` 需在可访问 PyPI 的环境首次 `uv sync` 时生成。

## Python 工具

```python
from agent_tools import ToolRegistry, ToolExecutor, tool

@tool(name="math.add")
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

registry = ToolRegistry()
registry.register(add)                       # 显式注册，不使用全局注册表
result = ToolExecutor(registry).run("math.add", {"a": 2, "b": 3})
print(result.output)                         # 5
print(registry.get("math.add").input_schema)
```

支持 `async def`；异步环境使用 `await executor.execute(name, arguments)`。输入严格校验，错误以 `ToolResult` 返回；取消不会被吞掉。

## MCP 工具

```python
from agent_tools import ToolRegistry, ToolExecutor
from agent_tools_mcp import MCPProvider

async def use_mcp():
    registry = ToolRegistry()
    provider = MCPProvider("demo", "http://localhost:8000/mcp")
    async with provider:                      # 建立并复用连接
        await registry.mount(provider)       # tools/list → mcp.demo.*
        result = await ToolExecutor(registry).execute(
            "mcp.demo.echo", {"text": "hello"}
        )
        print(result.to_dict())
        registry.unmount(provider)
```

也可通过配置显式指定 stdio/HTTP 服务器（只连接可信来源）：

```toml
[mcp_servers.local]
command = "python"
args = ["my_server.py"]

[mcp_servers.remote]
url = "https://example.com/mcp"
```

```python
provider = MCPProvider.from_config("mcp-servers.toml", "local")
```

MCP Schema 保留原样并以 JSON Schema 校验；输出优先 `structured_content`，同时在 `ToolResult.metadata.content` 保存原始内容块（含图片等非文本类型）；远程工具错误保留 `is_error`。连接关闭前应 `registry.unmount(provider)`。

## Skills

目录遵循 [Agent Skills](https://agentskills.io/specification)：`skills/code-review/SKILL.md`（YAML frontmatter 必含 `name` 与 `description`），可附带 `references/`、`scripts/` 等资源。

```python
from agent_tools import ToolRegistry, ToolExecutor
from agent_tools_skills import SkillCatalog

catalog = SkillCatalog.from_paths(["./skills"])
registry = ToolRegistry()
catalog.register(registry)       # skills.list/load/read_resource

executor = ToolExecutor(registry)
print(executor.run("skills.list", {}).output)
print(executor.run("skills.load", {"skill_id": "local:code-review"}).output)
```

仅扫描显式指定的目录；读取 UTF-8 文件时限制大小和目录逃逸。**不会执行 Skill 脚本、遵循 Skill 指令或赋予额外权限**，这些属于上层 Agent 的职责。

## MCP Skills（SEP-2640，预览）

**版本说明**：官方 Python SDK 2.3.0 尚未发布 Skills 扩展（上游主分支已实现）。以下桥接是预览接口，需安装包含 SEP-2640 的 SDK 版本；普通 `uv sync` 暂不能运行该示例。

远程 MCP Skill 需服务器声明 Skills 扩展；显式启用后可按需加载，并逐文件验证清单中的 SHA-256 与字节数：

```python
async with MCPProvider("docs", "https://example.com/mcp", skills=True) as provider:
    remote = provider.skills
    print(await remote.list())              # 仅元数据，含来源 ID 和 URI
    text = await remote.load("skill://code-review/SKILL.md")
    # remote.register(registry)              # 可选：注册 skills.mcp.docs.* 工具
```

本地 Skill 可直接作为 MCP Skills Server 暴露：

```python
from agent_tools_mcp import create_skills_server

server = create_skills_server(catalog)    # SKILL.md + 文本资源，生成完整摘要
# 使用 MCP SDK 部署 server，或作为 MCPProvider 的 in-process server
```

运行双向示例：`uv run python examples/skills_bridge.py`。

**限制**：仅导出/读取 UTF-8 小文件（每个不超过 256 KiB）；远程 `resources="dynamic"` 暂不加载，因为无法按静态摘要校验。服务器在创建时生成资源快照，修改内容后需重建。Skill 只是数据，绝不执行脚本；远程内容仍视为不可信输入。

## 扩展与边界

- 普通 Python 插件沿用 `agent_tools.plugins` Entry Points 和 `register(registry)`；见 `agent-tools-fs`。
- 外部工具使用 `ToolSpec + ToolProvider`，通过 `await registry.mount(provider)` 注册；不会改变 `@tool` 的 API。
- `ToolResult` 返回 `ok/output/error`；外部工具可额外携带 `metadata`。详细说明见 [架构说明](docs/architecture.md)。
- **安全**：插件加载会执行第三方代码；MCP stdio 会启动子进程；示例 FS 插件没有文件系统沙箱。只加载可信内容。执行器目前不提供超时、权限、审计或幂等性保证。
- v0.2.1 只导出 **Skills MCP Server**，不导出整个 ToolRegistry 为 MCP Server；不支持任意 Skill 脚本执行。