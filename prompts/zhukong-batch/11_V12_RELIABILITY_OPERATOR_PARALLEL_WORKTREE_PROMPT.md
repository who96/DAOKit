请进入主控模式，按“波次并行 + worktree 隔离”执行 v1.2 Reliability/Operator Experience 任务。

【项目根目录】
/Users/huluobo/workSpace/DAOKit

【前置条件】
- DKT-038 ~ DKT-046 已全部验收 SUCCESS。
- v1.2 资产基线已存在：specs/005-v1-2-reliability-operator-experience/*

【上下文文件】
- /Users/huluobo/workSpace/DAOKit/docs/roadmap.md
- /Users/huluobo/workSpace/DAOKit/specs/005-v1-2-reliability-operator-experience/requirements.md
- /Users/huluobo/workSpace/DAOKit/specs/005-v1-2-reliability-operator-experience/design.md
- /Users/huluobo/workSpace/DAOKit/specs/005-v1-2-reliability-operator-experience/tasks.md
- /Users/huluobo/workSpace/DAOKit/specs/005-v1-2-reliability-operator-experience/guardrail-charter-acceptance-matrix.md
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/tasks/DKT-047.md
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/tasks/DKT-048.md
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/tasks/DKT-049.md
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/tasks/DKT-050.md
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/tasks/DKT-051.md
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/tasks/DKT-052.md
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/tasks/DKT-053.md
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/tasks/DKT-054.md
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/tasks/DKT-055.md

【执行波次（必须按波次推进）】
- Wave 0（串行）: DKT-047
- Wave 1（并行）: DKT-048 + DKT-051
- Wave 2（并行）: DKT-049 + DKT-052
- Wave 3（串行）: DKT-050
- Wave 4（串行）: DKT-053
- Wave 5（串行）: DKT-054
- Wave 6（串行）: DKT-055

【任务依赖提示】
1) DKT-049 依赖 DKT-048。
2) DKT-052 依赖 DKT-051。
3) DKT-050 依赖 DKT-049。
4) DKT-053 依赖 DKT-050 + DKT-052。
5) DKT-054 依赖 DKT-053。
6) DKT-055 依赖 DKT-054。

【worktree 并行纪律】
1) 同一波次内每个任务必须使用独立 worktree 与独立分支（建议 `codex/dkt-<id>`）。
2) 禁止多个并行任务共享同一个 worktree。
3) 同一波次全部任务 SUCCESS 后，才允许进入下一波次。
4) 若并行任务之一 FAILED，则该波次整体暂停，先修复失败任务。

【波次集成与推送策略（强制）】
1) 每个波次完成后，必须先完成该波次所有任务分支的验收汇总，再执行集成。
2) 集成顺序：将该波次任务分支逐一合并到 `main` 并解决冲突。
3) 合并完成后，必须执行一次 `push origin main`。
4) 只有当该次 push 明确成功，才允许进入下一波次。
5) 若合并或 push 失败，则本波次状态记为未完成，禁止推进下一波次。

【强约束】
1) 主控不直接改文件、不直接执行有副作用命令。
2) 主控仅通过本地 shim 派发 subagent。
3) LangGraph-only；legacy path removed from rollout plan；不再通过参数切换编排工具。
4) 不得更改 CLI 对外参数名。
5) 不得破坏 schema_version=1.0.0 契约兼容语义。
6) 不得破坏 v1.0.0-rc1 发布锚点语义与 docs/reports/final-run/ 证据结构。
7) verification.log 命令证据兼容：
   - `Command:` 或
   - `=== COMMAND ENTRY N START/END ===`
   为避免解析差异，优先要求两种标识并存。

【验收与返工】
1) 每个任务最多 3 轮 rework；超限即标记 FAILED。
2) 验收仅基于 artifacts 与命令日志，不接受口头声明。
3) 若推荐验证命令缺失，允许等价替代，但必须在 verification.log 写明覆盖关系。

【每任务最终输出格式（只输出一次）】
- Task ID
- Status: SUCCESS | FAILED
- Summary
- Files Changed
- Commands Executed
- Verification Results
- Risks / Limitations
- Next Step Suggestion

【每波次汇总输出】
- Wave ID
- Tasks in Wave
- Task Status Matrix
- Merge Status (per task branch -> main)
- Push Status (`origin/main`)
- Merge/Integration Risk Notes
- Go/No-Go for Next Wave
