请进入主控模式，按 Observer Relay 批量任务链路执行。

【项目根目录】
/Users/huluobo/workSpace/DAOKit

【上下文文件】
- /Users/huluobo/workSpace/DAOKit/specs/002-observer-relay-bilingual-docs/requirements.md
- /Users/huluobo/workSpace/DAOKit/specs/002-observer-relay-bilingual-docs/design.md
- /Users/huluobo/workSpace/DAOKit/specs/002-observer-relay-bilingual-docs/tasks.md
- /Users/huluobo/workSpace/DAOKit/docs/observer-relay-feasibility.md
- /Users/huluobo/workSpace/DAOKit/docs/observer-relay-persona-and-compaction.md
- /Users/huluobo/workSpace/DAOKit/docs/observer-relay-optimization-plan.md

【批量任务队列】
DKT-019, DKT-020, DKT-021, DKT-022, DKT-023, DKT-024, DKT-025, DKT-026, DKT-027

【强约束】
1) 主控不直接改文件、不直接执行有副作用命令。
2) 主控仅通过本地 shim 派发 subagent。
3) 一次只推进一个任务，必须通过验收后才允许下一个任务开始。
4) 不得更改 CLI 对外参数名。
5) 不得破坏 schema_version=1.0.0 契约兼容语义。
6) 不得破坏 v1.0.0-rc1 发布锚点语义与 docs/reports/final-run/ 证据结构。
7) verification.log 命令证据兼容：
   - `Command:` 或
   - `=== COMMAND ENTRY N START/END ===`
   为避免解析差异，优先要求两种标识并存。

【执行策略】
1) 先读取对应任务 prompt 的 Goal / Concrete Actions / Acceptance Criteria。
2) 生成 step JSON（默认 S1），派发 subagent。
3) 基于 artifacts 做验收，必要时差分 rework。
4) 每个任务最多 3 轮 rework；超限则任务标记 FAILED。
5) 若推荐验证命令缺失，允许等价替代，但必须在 verification.log 说明覆盖关系。

【最终输出格式（每个任务只输出一次）】
- Task ID
- Status: SUCCESS | FAILED
- Summary
- Files Changed
- Commands Executed
- Verification Results
- Risks / Limitations
- Next Step Suggestion
