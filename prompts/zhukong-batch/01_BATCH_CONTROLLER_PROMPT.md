请进入主控模式，按 DAOKit 批量任务链路执行。

【项目根目录】
/Users/huluobo/workSpace/DAOKit

【上下文文件】
- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/requirements.md
- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/design.md
- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/tasks.md
- /Users/huluobo/workSpace/DAOKit/docs/plans/2026-02-11-daokit-implementation-plan.md

【批量任务队列】
DKT-001, DKT-002, DKT-003, DKT-004, DKT-005, DKT-006, DKT-007, DKT-008, DKT-009, DKT-010, DKT-011, DKT-012, DKT-013, DKT-014, DKT-015, DKT-016, DKT-017, DKT-018

【强约束】
1) 主控不直接改文件、不直接执行有副作用命令。
2) 主控仅通过本地 shim 派发 subagent。
3) 一次只推进一个任务，必须通过验收后才允许下一个任务开始。
4) 验收证据必须包含：
   - report.md
   - verification.log
   - audit-summary.md（如任务适用）
5) verification.log 的“命令证据”格式兼容规则：
   - 允许 `Command:` 行，或
   - 允许 `=== COMMAND ENTRY N START/END ===` 块；
   - 为避免解析器差异，优先要求 subagent 同时输出两种标识（至少在每个命令块内包含一行 `Command: <cmd>`）。
6) 若任务失败：输出失败报告并给出下一步 rework 选项，不允许伪完成。

【执行策略】
1) 先读取 tasks.md 中对应任务的 Goal / Concrete Actions / Acceptance Criteria。
2) 生成 step JSON 派发 subagent。
3) 基于 artifacts 做验收，必要时差分 rework。
4) 每个任务最多 3 轮 rework；超限则任务标记 FAILED。
5) 如果推荐验证命令不存在（例如 Make target 缺失），只要替代验证链路覆盖同等验收目标且有完整日志证据，可判定通过。

【最终输出格式（每个任务只输出一次）】
- Task ID
- Status: SUCCESS | FAILED
- Summary
- Files Changed
- Commands Executed
- Verification Results
- Risks / Limitations
- Next Step Suggestion
