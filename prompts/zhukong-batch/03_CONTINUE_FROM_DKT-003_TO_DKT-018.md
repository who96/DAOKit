你现在进入「批量续跑模式」，起点从 DKT-003，继续执行到 DKT-018。

前置条件：DKT-002 已被判定 SUCCESS。

【项目根目录】
/Users/huluobo/workSpace/DAOKit

【上下文文件】
- /Users/huluobo/workSpace/DAOKit/prompts/zhukong-batch/01_BATCH_CONTROLLER_PROMPT.md
- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/tasks.md

【续跑队列】
DKT-003, DKT-004, DKT-005, DKT-006, DKT-007, DKT-008, DKT-009, DKT-010, DKT-011, DKT-012, DKT-013, DKT-014, DKT-015, DKT-016, DKT-017, DKT-018

【强约束】
1) 主控只做派发/观测/验收，不直接改代码。
2) verification.log 命令证据兼容：`Command:` 或 `COMMAND ENTRY`，建议同时输出两种标识。
3) 推荐命令不存在时，允许等价替代验证，但必须在日志中写明覆盖关系。
4) 每任务最多 3 轮 rework；超限即停止并返回失败报告。

【输出】
- 成功：一次性总成功报告
- 失败：一次性总失败报告（任务 ID、阻塞点、下一步建议）

