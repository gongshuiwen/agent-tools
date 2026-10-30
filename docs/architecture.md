# 设计约束（v0.2）

```text
Python @tool ───────┐
                    ├── ToolRegistry ── ToolExecutor ── ToolResult
MCPProvider ─ ToolSpec┘

SkillCatalog ── skills.list / skills.load / skills.read_resource
```

1. **Tool 是可执行能力**：本地函数保留 Pydantic 输入模型；远程 Tool 保留来源提供的 JSON Schema。二者通过同一 Registry 和 Executor 调用。
2. **Provider 有生命周期**：`async with MCPProvider(...)` 建立连接，`mount` 发现工具，关闭连接前 `unmount`。重复名称直接报错，不重命名已有工具。
3. **Skill 不是 Tool**：Catalog 仅管理元数据、说明和文本资源；可选地将读取操作注册成三个普通 Tool。运行 Skill 内脚本不在范围内。
4. **结果语义**：`ok=False` 不代表 Python 异常必须向 Agent 抛出。MCP 工具错误保留内容块；连接/协议异常作为执行错误处理，调用取消原样传播。
5. **安全分层**：工具名、Schema 和 Skill 描述不是授权凭证；权限、沙箱、联网和审计由宿主系统负责。Skill 内容是不可信输入。

**后续可选**：MCP Skills 扩展（SEP-2640）桥接、MCP Server 导出、权限与审计。核心包不直接依赖 MCP 或 PyYAML。
