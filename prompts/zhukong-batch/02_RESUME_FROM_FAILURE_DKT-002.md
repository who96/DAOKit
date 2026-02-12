你现在进入「失败恢复模式」，只处理 DKT-002 的恢复，不要启动后续任务。

【项目根目录】
/Users/huluobo/workSpace/DAOKit

【失败上下文】
- Failed Task ID: DKT-002
- Failed Run ID: DKT-002_20260211T124625Z_367c80d
- 已存在证据目录：
  - /Users/huluobo/workSpace/DAOKit/.artifacts/agent_runs/DKT-002_20260211T124625Z_367c80d/reports/DKT-002/report.md
  - /Users/huluobo/workSpace/DAOKit/.artifacts/agent_runs/DKT-002_20260211T124625Z_367c80d/reports/DKT-002/verification.log
  - /Users/huluobo/workSpace/DAOKit/.artifacts/agent_runs/DKT-002_20260211T124625Z_367c80d/reports/DKT-002/audit-summary.md

【恢复目标】
仅修复 DKT-002 的验收不通过问题，并输出最终 SUCCESS/FAILED 结论。

【恢复策略】
1) 先做一次“证据兼容性验收”：
   - verification.log 命令证据接受两种格式：
     a. `Command: <cmd>`
     b. `=== COMMAND ENTRY N START/END ===`
2) 若现有证据已满足 DKT-002 验收标准，则直接判定 SUCCESS，不做无意义重跑。
3) 若仍不满足，只允许做“单点 rework”：
   - 仅补齐日志格式（在每个 command entry 块内增加 `Command: <cmd>` 行）。
   - 禁止改动 DKT-002 任务范围外文件。
4) 若完成单点 rework，重新验收并给出结论。

【硬约束】
- 主控不得直接改文件；必须通过本地 shim 派发 subagent。
- 不允许开启 DKT-003 及后续任务。
- 最多 1 轮恢复性 rework；仍失败则返回 FAILED 并说明阻塞。

【最终输出（仅一次）】
- Task ID: DKT-002
- Status: SUCCESS | FAILED
- Recovery Action Taken
- Evidence Checked (paths)
- Verification Decision Reason
- If SUCCESS: 下一任务建议（DKT-003）

