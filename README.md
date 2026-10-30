# Agent-Tools v0.1

**Tool First · Plugin Native · Framework Agnostic · Adapter Optional**

独立于任何 Agent 框架的 Python 工具定义、发现与执行层。第一版聚焦工具契约与插件机制，**不包含** Agent Runtime、MCP Server、权限策略、超时、审计或沙箱。

## 功能

- `@tool`：普通 Python 函数即工具，保留函数身份与直接调用能力；支持 `name` / `description` 覆盖。
- 自动 Schema：使用 Python 类型注解、Pydantic v2 和 `Field` 生成 JSON Schema；参数采用严格类型校验，拒绝额外字段。
- `ToolRegistry`：显式注册、按名称查找、冲突检测、排序列举；**不使用全局注册表**。
- 独立插件：通过标准 Python `entry_points(group="agent_tools.plugins")` 发现，显式调用 `load_plugins()` 才加载。
- `ToolExecutor`：执行同步和异步函数；将校验、执行和结果序列化错误转换为 `ToolResult`。
- CLI：`agent-tools list`、`agent-tools inspect <name>`。
- 示例插件：`agent-tools-fs`，提供 `fs.read_text` 和 `fs.list_directory`。

## 快速开始

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。进入仓库根目录（首次安装需联网解析并下载依赖，生成 `uv.lock`）：

```bash
uv sync
uv run agent-tools list
uv run agent-tools inspect fs.read_text
uv run python examples/demo.py
uv run pytest
```

如果本机没有 `.python-version` 中的 Python 3.11，可以由 `uv` 安装，也可以将 `.python-version` 修改为本机兼容的 Python 3.11+ 版本。

### 普通函数与工具共存

```python
from agent_tools import ToolRegistry, ToolExecutor, tool

@tool(name="math.add")
def add(a: int, b: int) -> int:
    """将两个整数相加。"""
    return a + b

print(add(2, 3))  # 5，依然是普通 Python 函数

registry = ToolRegistry()
registry.register(add)  # 不会因为 import / @tool 而自动全局注册

executor = ToolExecutor(registry)
result = executor.run("math.add", {"a": 2, "b": 3})
print(result.to_dict())
# {'tool': 'math.add', 'ok': True, 'output': 5, 'error': None}

print(registry.get("math.add").input_schema)
```

### 异步调用

```python
import asyncio
from agent_tools import ToolRegistry, ToolExecutor, tool

@tool
async def greet(name: str) -> str:
    """根据名称返回问候语。"""
    return f"Hello, {name}!"

async def main():
    registry = ToolRegistry()
    registry.register(greet)
    result = await ToolExecutor(registry).execute("greet", {"name": "Ada"})
    print(result.output)

asyncio.run(main())
```

普通同步函数也能通过 `await execute()` 调用，执行器会把它放到线程池中。对于在已有事件循环内运行的调用方，应使用 `await execute()`，不能调用同步快捷方法 `run()`。

### 自动发现已安装插件

```python
from agent_tools import ToolRegistry, ToolExecutor

registry = ToolRegistry()
registry.load_plugins(["filesystem"])  # 只加载指定已安装插件

result = ToolExecutor(registry).run("fs.list_directory", {"path": "."})
print(result.to_dict())
```

`uv sync` 在开发 workspace 内安装了两个成员包，所以能发现示例插件。在其他环境中，需分别安装 `agent-tools-core` 和需要的插件包。

## 如何开发自己的插件

独立 PyPI 包使用其自身 `pyproject.toml`：

```toml
[project]
name = "my-agent-tools"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["agent-tools-core>=0.1,<0.2"]

[project.entry-points."agent_tools.plugins"]
my_plugin = "my_agent_tools:register"
```

然后在 `my_agent_tools/__init__.py` 中：

```python
from agent_tools import tool

@tool(name="my_plugin.hello")
def hello(name: str) -> str:
    """返回问候语。"""
    return f"Hello, {name}!"


def register(registry):
    registry.register(hello)
```

由调用方安装插件并选择 `registry.load_plugins(["my_plugin"])`。插件导入或工具装饰不会主动注册到某个全局 registry。`load_plugins()` 在单个 registry 中重复调用不会重复加载相同 entry point，发生加载错误时会回滚当前插件的注册操作。

## 目录结构

```text
agent-tools/
├── pyproject.toml            # uv workspace, 开发依赖和工具配置
├── uv.lock                   # 首次联网 uv sync 后生成的工作区锁文件
├── packages/
│   ├── agent-tools-core/
│   │   └── src/agent_tools/
│   │       ├── tool.py       # Tool、@tool、Schema
│   │       ├── registry.py   # ToolRegistry、插件发现
│   │       ├── executor.py   # ToolExecutor、ToolResult
│   │       ├── errors.py
│   │       └── cli.py
│   └── agent-tools-fs/
│       └── src/agent_tools_fs/
├── examples/
└── tests/
```

开发 workspace 根目录不发布，两个成员包可独立打包。构建示例：

```bash
uv build --package agent-tools-core
uv build --package agent-tools-fs
```

## 工具契约约束

1. 每个工具必须有说明性 docstring，或在 `@tool(description=...)` 提供描述。
2. 所有参数必须有类型注解，并可由 Pydantic 转换为 JSON Schema。
3. 只支持命名参数；不支持位置专用参数、`*args` 或 `**kwargs`。
4. 参数输入必须是 JSON 对象；校验严格，未知字段报错。嵌套 Pydantic 模型会以对象类型传入函数，不会被展开为字典。
5. 工具执行结果需能转换为 JSON 值；不能序列化时返回 `serialization_error`。
6. `@tool` 不改变原函数的调用行为；参数校验只在执行器边界发生。

`ToolResult` 的标准结构如下：

```json
{
  "tool": "math.add",
  "ok": false,
  "output": null,
  "error": {
    "code": "validation_error",
    "message": "Invalid tool arguments",
    "details": [{ "loc": ["a"], "type": "int_type", "msg": "Input should be a valid integer" }]
  }
}
```

错误码：`tool_not_found`、`validation_error`、`execution_error`、`serialization_error`。普通工具执行异常在执行器边界被捕获；`KeyboardInterrupt`、进程退出以及 `asyncio.CancelledError` 不会被吞掉。

## 安全边界（重要）

- **插件加载会执行已安装插件的 Python 代码**，只从可信来源安装/加载插件；Entry Points 不是沙箱。
- 示例文件系统插件是只读的，但**可以读取进程有权访问的任意路径**，没有路径白名单或敏感文件保护。不要直接暴露给不可信用户/模型。
- `ToolExecutor` 没有超时、权限检查、隔离或幂等保证。同步工具在后台线程运行，取消异步等待并不会终止已经开始的线程函数。
- 执行错误包含异常类型和错误信息，可能包含文件路径等信息。对外暴露前应由上层进行错误信息脱敏。

## 暂不实现

- MCP、LangChain、CrewAI、OpenAI Agents 等适配器
- 类继承型工具、自动远程发现、Hooks 和中间件
- 超时、预算、审批、权限、文件系统隔离、幂等键
- Tracing、JSONL 审计、遥测、远程分布式执行

这些功能均应以后按实际需求增加，避免将核心库变成 Agent 框架。
