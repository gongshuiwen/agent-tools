# agent-tools-fs

A deliberately small, read-only example plugin for `agent-tools-core`.

**Security:** This plugin can read any filesystem path accessible to its Python process.
It does **not** restrict paths, implement permissions or provide a sandbox. Only
use it in trusted contexts; do not expose its tools to untrusted agents or users
without an external sandbox and authorization layer.
