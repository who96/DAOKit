# LangChain + LangGraph + RAG 协作机制（作品级说明）

语言： [English](langchain-langgraph-rag-cooperation.en.md) | **中文**

## 1. 文档目的

DAOKit 在同一条生产化运行路径中联合使用 LangGraph、LangChain 与 RAG。
本文说明三者在运行时的职责边界、在生命周期各阶段的协作方式，以及 Codex 分发如何接入真实执行。

## 2. 运行时职责拆分

| 运行层 | 主职责 | 禁止事项 |
| --- | --- | --- |
| LangGraph runtime（`src/orchestrator/`） | 确定性生命周期执行：`extract -> plan -> dispatch -> verify -> transition` | 绕过账本写入或跳过状态迁移护栏 |
| LangChain orchestration（`src/tools/langchain/`） | 编排工具调用与检索调用，并保持 step/task/run 关联 | 充当状态事实源 |
| RAG retriever（`src/rag/`） | 提供带来源归因与相关性信号的建议性上下文 | 直接修改权威状态 |
| Codex shim dispatch（`src/dispatch/`） | 执行 create/resume/rework 并产出 request/output/error 证据 | 改动 CLI 对外参数契约 |
| Ledger contracts（`state/` + `contracts/`） | 持久化权威状态、事件、lease、heartbeat、succession | 接受破坏 schema 的写入 |

## 3. 按生命周期看协作

1. `extract`
- LangGraph 归一化 task/run 上下文并保持护栏约束。
- LangChain 暂不执行工具分发，仅准备后续受控调用。

2. `plan`
- LangChain 调用 RAG 检索补充建议性上下文。
- RAG 返回来源归因与相关性信号。
- 规划输出仍受契约兼容语义约束。

3. `dispatch`
- LangGraph 调用 dispatch adapter。
- Dispatch adapter 路由到 Codex shim 的 create/resume/rework。
- 过程会产出请求/输出等审计工件。

4. `verify`
- 在状态迁移前执行验收与范围检查。
- 检索与工具链路保留可审计、可关联的 trace。

5. `transition`
- LangGraph 将状态/事件写入既有 `schema_version=1.0.0` 契约。
- 更新 succession/lifecycle 元数据，同时不破坏发布锚点。

## 4. 来自已完成波次的运行证据

DKT-036 的 integrated reliability 运行证明了该协作链路已在真实执行中落地：

- 运行报告：
  - `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/report.md`
- 命令证据日志：
  - `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/verification.log`
- 机器可读摘要：
  - `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/integrated-reliability-summary.json`

该摘要中的关键证明点包括：

- `runtime_mode=integrated`
- `resolved_runtime_engine=langgraph`
- `runtime_class=LangGraphOrchestratorRuntime`
- `takeover.handoff_applied=true`
- `checks.status_replay_consistent_after_recovery=true`
- `final_state.status=DONE`

## 5. 演示命令路径

可通过以下脚本复现实战协作行为：

- integrated reliability 恢复链：
  - `examples/cli/integrated_reliability_recovery_chain.sh`
- observer-relay 恢复链：
  - `examples/cli/observer_relay_recovery_chain.sh`
- 后端到 Agent 全链路演练：
  - `examples/cli/backend_to_agent_path.sh`

## 6. 兼容性护栏

- 不得重命名/移除 CLI 命令名与现有参数名。
- 保持与 `schema_version=1.0.0` 兼容的契约语义。
- 保持 `v1.0.0-rc1` 锚点语义与 `docs/reports/final-run/` 证据目录结构不变。
