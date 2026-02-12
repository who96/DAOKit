# Extension Guide: Tools, Skills, and Hooks

DAOKit is designed for extension without breaking core orchestration contracts.

## 1. Function-Calling Tools

Path: `src/tools/function_calling/adapter.py`

Use `FunctionCallingAdapter` for local deterministic tools.

```python
from tools.function_calling import FunctionCallingAdapter

adapter = FunctionCallingAdapter()
adapter.register_callable(
    name="echo_tool",
    args_schema={
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    },
    handler=lambda args: {"echo": args["message"]},
)
result = adapter.invoke(tool_name="echo_tool", arguments={"message": "hello"})
```

Rules:

- Validate JSON schema before execution.
- Keep tool handlers side-effect scoped and explicit.
- Use invocation logs for audit trails.

## 2. MCP Tools

Path: `src/tools/mcp/adapter.py`

Use `McpAdapter` to register MCP servers and invoke remote capabilities with traceable retries.

```python
from tools.mcp import McpAdapter

adapter = McpAdapter(max_retries=1)
# adapter.register_server(name="docs", client=<McpServerClient>)
# adapter.refresh_capabilities(server_name="docs")
# result = adapter.invoke(server_name="docs", tool_name="search", arguments={"q": "lease"})
```

Rules:

- Register server first, then refresh/list capabilities.
- Treat MCP failure responses as recoverable runtime events, not silent skips.
- Log request/response for replayability.

## 3. Skills

Path: `src/skills/loader.py`

Skill discovery is manifest-driven (`skill.json`) and versioned.

Required manifest fields:

- `schema_version`
- `name`
- `version`

Optional sections:

- `instructions` (list)
- `scripts` (name -> path)
- `hooks` (event, handler, timeout, idempotent)

Hook events supported:

- `pre-dispatch`
- `post-accept`
- `pre-compact`
- `session-start`

## 4. Lifecycle Hooks

Path: `src/hooks/runtime.py`

Use `HookRuntime` to register deterministic lifecycle callbacks.

```python
from hooks import HookRuntime

runtime = HookRuntime(default_timeout_seconds=2.0)
runtime.register(
    hook_point="pre-dispatch",
    hook_name="my-hook",
    callback=lambda ledger, context: ledger.update({"checked": True}),
)
result = runtime.run(hook_point="pre-dispatch", ledger_state={"status": "EXECUTE"})
```

Rules:

- Keep hooks idempotent when possible.
- Never mutate outside the provided ledger/context objects.
- Respect timeout budgets.

## 5. Contributor Contract

Every extension PR should include:

1. Tests under `tests/`.
2. Docs update for usage and safety assumptions.
3. Backward-compatible behavior for existing contracts unless versioned migration is provided.
