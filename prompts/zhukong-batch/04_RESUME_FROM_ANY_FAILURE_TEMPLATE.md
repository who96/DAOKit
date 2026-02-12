你现在进入「通用失败恢复模式」，目标是从任意失败任务恢复，并在恢复成功后继续批量执行。

【项目根目录】
/Users/huluobo/workSpace/DAOKit

【先读文件】
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/01_BATCH_CONTROLLER_PROMPT.md
- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/tasks.md
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/99_BATCH_PROMPTS_INDEX.md

【失败定位输入（二选一）】
A. 手动指定（推荐）
- FAILED_TASK_ID: <例如 DKT-009>
- FAILED_RUN_ID: <例如 DKT-009_20260211TxxxxxxZ_xxxxxxx>
- CONTINUE_FROM_TASK_ID: <通常等于 FAILED_TASK_ID 的下一个任务，如 DKT-010；若仅补救当前失败任务则先留空>

B. 自动定位（若存在批量结果文件）
- 读取：`batch_results.tsv`
- 取最后一个 `FAILED` 任务作为 FAILED_TASK_ID
- 在 `.artifacts/agent_runs/` 下匹配最新 run 作为 FAILED_RUN_ID
- 自动推导 CONTINUE_FROM_TASK_ID（失败任务的下一个任务）

【恢复目标】
1) 只修复 FAILED_TASK_ID 的验收失败问题。
2) 不重做已完成任务。
3) 恢复成功后，从 CONTINUE_FROM_TASK_ID 继续串行执行到 DKT-018。

【恢复与验收策略】
1) 先进行证据再验收：
   - 必须检查 evidence trio：`report.md` / `verification.log` / `audit-summary.md`（如任务适用）。
2) verification.log 命令证据兼容规则：
   - 接受 `Command: <cmd>`
   - 或 `=== COMMAND ENTRY N START/END ===`
   - 为兼容性，若触发 rework，要求两种标识同时存在。
3) 若当前证据已满足任务验收标准，则直接判定 SUCCESS，不做无意义重跑。
4) 若不满足，只允许做“最小单点 rework”：
   - 仅补齐缺失证据或日志格式；
   - 禁止扩大改动范围到任务 scope 之外。
5) 恢复阶段最多 1 轮 rework；仍失败则停止并输出 FAILED 报告。

【续跑策略】
- 只有当 FAILED_TASK_ID 恢复为 SUCCESS 时，才允许从 CONTINUE_FROM_TASK_ID 开始续跑。
- 续跑后每个任务最多 3 轮 rework，超限即停止批量流程。

【硬约束】
1) 主控只做派发/观测/验收，不直接改代码。
2) 必须通过本地 shim 调度 subagent。
3) 验收只基于 artifacts 与命令日志，不接受口头声明。
4) 推荐验证命令不存在时，允许等价替代验证，但必须在 verification.log 中写明替代关系和覆盖范围。

【输出要求（仅一次）】
- Recovery Target: <FAILED_TASK_ID>
- Recovery Status: SUCCESS | FAILED
- Recovery Action Taken
- Evidence Checked (paths)
- Verification Decision Reason
- If Recovery SUCCESS:
  - Continue Range: <CONTINUE_FROM_TASK_ID> -> DKT-018
  - Batch Status: SUCCESS | FAILED
  - If FAILED: Failed Task ID + blocker + next options

