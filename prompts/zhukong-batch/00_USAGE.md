# Zhukong 批量派单 Prompt 包（DAOKit）

## 使用顺序
1. 先把 `01_BATCH_CONTROLLER_PROMPT.md` 整段喂给 `zhukong-orchestrator`，建立批量执行纪律。
2. 再按依赖顺序逐条喂 `tasks/` 下的任务 prompt。
3. 一次只喂一个任务文件，等验收完成后再喂下一条。

## 推荐执行顺序
- `DKT-001` -> `DKT-002` -> `DKT-003` -> `DKT-004` -> `DKT-005`
- `DKT-006` -> `DKT-007`
- `DKT-008` -> `DKT-009` -> `DKT-010`
- `DKT-011` -> `DKT-012`
- `DKT-013` -> `DKT-014` -> `DKT-015`
- `DKT-016` -> `DKT-017` -> `DKT-018`

## 输入锚点
- 需求：`/Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/requirements.md`
- 架构：`/Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/design.md`
- 任务：`/Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/tasks.md`

## 纪律（必须）
1. 主控只能派发、观测、验收；不能直接改代码。
2. 只允许走本地 shim 调度 subagent。
3. 验收只看 artifacts 和验证日志，不看口头完成声明。
4. 验收失败必须发差分 rework，不能跳过。
5. 每个任务最终只输出一次结果（成功或失败）。

## 失败恢复（推荐）
1. 如中途失败，先使用 `02_RESUME_FROM_FAILURE_DKT-002.md`（可按需改任务 ID）恢复失败任务。
2. 恢复成功后，再从下一个未完成任务继续（例如从 `DKT-003` 继续）。
3. verification.log 验收兼容 `Command:` 与 `COMMAND ENTRY`，为兼容性建议同时输出两种标识。
4. 若你不想手写恢复提示词，直接使用通用模板：`04_RESUME_FROM_ANY_FAILURE_TEMPLATE.md`。
