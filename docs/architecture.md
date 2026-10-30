# 架构约束（v0.3.0）

```text
Python @tool ───────┐
                    ├── ToolRegistry ── ToolExecutor
MCPProvider ─ ToolSpec┘

Local SkillCatalog ──┬── skills.list/load/read_resource
                     └── MCP Skills Server (SEP-2640)
MCP Skills Client ────── RemoteSkills (manifest-checked reads)
ToolRegistry ──────────── create_tools_server (allowlist → MCP Server)
```

- Core 只定义工具契约、注册与执行，不依赖 MCP 或 Skills。
- MCP Tool 保留外部 Schema；MCPProvider 持有连接，关闭前 `registry.unmount(provider)`。
- SkillCatalog 管本地技能；RemoteSkills 通过现有 MCP Client 会话按需发现、加载远程技能。Skill 不是可直接执行的 Tool。
- 双向 Skills 桥接为预览功能；PyPI MCP SDK 2.3.0 尚不包含扩展。桥接使用官方 `io.modelcontextprotocol/skills`，不实现新传输协议。静态资源校验字节数和 SHA-256，动态资源暂不读取。
- MCP Server 导出是创建时的**快照**。仅显式选择的本地目录，跳过隐藏文件与符号链接；读取限制为 UTF-8、每文件 256 KiB。
- MCP Server、Skill 文件和本地插件都应视为不可信来源；调用许可、沙箱和审批由宿主负责。此项目不会执行 Skill 指令或脚本。

完整用法见 [README](../README.md)。

- `create_tools_server(registry, include=[...])` 使用低层 MCP Server 保留 JSON Schema，明确限定导出范围；列表是快照，执行仍经 ToolExecutor，远程 Provider 需保持连接。
- 远程 MCP 内容块、`is_error`、结构化数据可透传；不代理 Resources/Prompts，也不提供 HTTP 身份验证。
