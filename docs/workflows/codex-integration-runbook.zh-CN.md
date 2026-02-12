# Codex 集成运行手册（后端可复现）

语言： [English](codex-integration-runbook.en.md) | **中文**

## 1. 目的

本手册用于让后端工程师可复现 integrated 运行路径：
由 LangGraph 控制生命周期，LangChain 负责编排工具/检索，RAG 提供建议性上下文，Codex shim 负责分发执行。

## 2. 前置条件

1. 仓库已初始化，依赖可用。
2. 所有命令在仓库根目录执行。
3. Python 模块命令使用 `PYTHONPATH=src`。
4. 不修改 CLI 对外参数名。

## 3. 可复现命令流程

### Step 1：创建本次演练的沙箱目录

```bash
RUN_ROOT=.artifacts/manual_runs/codex_integration_demo
mkdir -p "$RUN_ROOT"
```

预期：目录已创建且可写。

### Step 2：执行 integrated reliability 恢复链脚本

```bash
bash examples/cli/integrated_reliability_recovery_chain.sh \
  "$RUN_ROOT/scenario" \
  "$RUN_ROOT/integrated-reliability-summary.json"
```

预期输出包含：

- `Integrated reliability recovery scenario completed:`
- 以 `integrated-reliability-summary.json` 结尾的 JSON 路径

### Step 3：从 summary JSON 校验运行时角色关键点

```bash
python3 - <<'PY'
import json
from pathlib import Path

p = Path('.artifacts/manual_runs/codex_integration_demo/integrated-reliability-summary.json')
data = json.loads(p.read_text())
keys = [
    'runtime_mode',
    'resolved_runtime_engine',
    'runtime_class',
]
for k in keys:
    print(f"{k}={data.get(k)}")
print("takeover.handoff_applied=", data.get('takeover', {}).get('handoff_applied'))
print("checks.status_replay_consistent_after_recovery=", data.get('checks', {}).get('status_replay_consistent_after_recovery'))
print("final_state.status=", data.get('status_final', {}).get('pipeline_state', {}).get('status'))
PY
```

预期值：

- `runtime_mode=integrated`
- `resolved_runtime_engine=langgraph`
- `runtime_class=LangGraphOrchestratorRuntime`
- `takeover.handoff_applied=True`
- `checks.status_replay_consistent_after_recovery=True`
- `final_state.status=DONE`

### Step 4：查看同一运行的状态与事件

```bash
PYTHONPATH=src python3 -m cli status \
  --root "$RUN_ROOT/scenario" \
  --task-id DKT-036 \
  --run-id RUN-INTEGRATED-RELIABILITY \
  --json

PYTHONPATH=src python3 -m cli replay \
  --root "$RUN_ROOT/scenario" \
  --source events \
  --limit 20
```

预期：

- `status` 输出包含契约兼容对象（`pipeline_state`、`heartbeat_status`、`leases`）。
- replay 输出非空，且与 summary 中的检查结果一致。

### Step 5：执行仓库基线验证

```bash
make lint && make test
```

预期：命令退出码为 `0`。

## 4. 已完成波次的参考证据

以下仓库内已追踪工件，证明相同流程已在 DKT-036 被验收：

- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/report.md`
- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/verification.log`
- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/integrated-reliability-summary.json`
- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/integrated-reliability-summary-from-script.json`

## 5. 命令到运行时角色映射

| 命令 / 工件 | 验证的运行时角色 |
| --- | --- |
| `integrated_reliability_recovery_chain.sh` | 触发 integrated runtime 分发与恢复动作 |
| Summary JSON 关键字段 | LangGraph 运行时主导与恢复连续性 |
| `cli status` + `cli replay` | 账本/事件一致性与可追溯性 |
| `make lint && make test` | 项目基线验证门禁 |

## 6. 兼容性护栏

- 保持 CLI 命令名与参数名不变。
- 保持 `schema_version=1.0.0` 语义不变。
- 保持 `v1.0.0-rc1` 锚点语义与 `docs/reports/final-run/` 证据结构不变。
