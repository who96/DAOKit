# Zhukong Execution Runbook (DAOKit)

## 1. 目标
把 `/Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/tasks.md` 中的任务，按主控模式逐步派发执行，确保“主控只编排不下场实现”。

## 2. 输入材料
- 需求：`/Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/requirements.md`
- 架构：`/Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/design.md`
- 任务：`/Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/tasks.md`
- 主计划：`/Users/huluobo/workSpace/DAOKit/docs/plans/2026-02-11-daokit-implementation-plan.md`

## 3. 执行原则（强制）
1. 主控只做 plan/dispatch/verify，不直接改代码。
2. 每次只推进一个任务 ID（例如 `DKT-006`）。
3. 子任务完成判定必须依赖 artifacts 证据，不接受口头“已完成”。
4. 不满足验收标准时，必须发差分 rework，不得跳步。

## 4. 推荐执行节奏
1. 先跑 `DKT-001 ~ DKT-002` 打地基。
2. 每完成一个任务就做一次主控验收，再进入下一个任务。
3. 每 3-4 个任务做一次回归验收（状态、证据、可恢复性）。

## 5. 主控派单 Prompt 模板
将下面模板发给 `zhukong-orchestrator`，只替换尖括号内容：

```text
请按主控模式执行任务 <TASK_ID>。

上下文文件：
- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/requirements.md
- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/design.md
- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/tasks.md

本次只执行：<TASK_ID>

硬约束：
1) 主控不得直接改文件或跑有副作用命令
2) 只能通过本地 shim 派发 subagent
3) 验收只看 artifacts 证据
4) 验收失败必须给出 diff 化 rework 请求

输出要求：
- 最终只返回一次结果
- 包含：任务摘要、变更文件、验证命令与结果、风险与下一步
```

## 6. 每任务验收清单
1. 是否生成了 step report。
2. 是否有 verification log。
3. 是否有 audit summary。
4. 是否有对应 state/event 更新。
5. 是否存在越权改动（非任务范围文件）。

## 7. 中断恢复
1. 读取最新 `pipeline_state` 与 artifacts index。
2. 识别当前 `current_step` 与未完成验收项。
3. 仅恢复 `PENDING/FAILED/RUNNING`，不重跑 `DONE`。

## 8. 什么时候触发接班
- 长时间无输出超过阈值。
- 主控窗口不稳定且 lease 可接管。
- 发现状态与证据不一致，先进入治理流程再恢复执行。

