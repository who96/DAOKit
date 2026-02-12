# Observer Relay 优化建议与演进路径（P0）

## 1. 范围与约束

本计划只围绕已确定方案推进，不扩展新方向：
1. 对外主窗口改为 observer relay。  
2. 主控 agent 进入 subagent 链路。  
3. 主控具备自检测与自愈。  
4. 主窗口只做转发与状态可视化。  
5. 主窗口主动剔除过时/无效日志。  
6. 主窗口仅沉淀最小必要数据。

硬约束：
1. 不改 CLI 对外参数名。  
2. 不改 `schema_version=1.0.0` 契约兼容语义。  
3. 不破坏 `v1.0.0-rc1` 发布锚点与 `docs/reports/final-run/` 证据结构。

## 2. MVP（最小可行版本）改法

### 2.1 MVP 目标
在不改 public contract 的前提下，完成角色重排与自愈闭环打通。

### 2.2 MVP 改动清单（最小集）
1. 主窗口人设切换为 relay-only（提示词与操作规约层）。  
2. 主控 agent 作为 subagent 持有执行决策职责（非外窗）。  
3. 自愈 runbook 固化为四步：`check -> 判定 -> takeover -> handoff/apply`。  
4. 主窗口上下文压缩按“必保留/必剔除”规则执行。  
5. 状态展示统一走现有 `status/check/replay` 聚合视图。

### 2.3 MVP 交付验收
1. 外窗不再直接下场执行任务步骤。  
2. 心跳 `STALE` 时可通过既有 `takeover` 成功接班。  
3. handoff package 可创建并可应用恢复。  
4. 无 CLI 参数与 schema 破坏。  

## 3. 演进顺序（实施顺序）

1. **阶段 A：角色冻结（先边界，后动作）**  
   - 落地主窗口 relay-only 人设与禁止事项。  
   - 明确主控 agent 是唯一调度/接管决策者。

2. **阶段 B：自愈闭环落地（先检测，后接管）**  
   - 用现有 heartbeat/lease 信号定义告警与接管判定。  
   - 固化 `takeover` 执行路径和恢复确认输出。

3. **阶段 C：压缩策略上线（先保留，后清理）**  
   - 上线必保留五要素抽取。  
   - 上线必剔除四类噪声清理与去重规则。

4. **阶段 D：回放与审计一致性校验（最后做）**  
   - 使用 `replay/status/check` 验证可追溯性。  
   - 确认不影响 `docs/reports/final-run/` 证据结构。

## 4. 风险清单与回滚策略

配套可执行回滚步骤见：`docs/observer-relay-rollback-runbook.md`。

| 风险 | 触发信号 | 影响 | 回滚策略 |
|---|---|---|---|
| 主窗口越权执行 | 外窗出现任务分配/执行动作 | 角色边界失效 | 立即回退到 relay-only 提示词模板；禁用越权动作入口 |
| 误判导致频繁接管 | heartbeat 波动触发过多 takeover | 运行抖动 | 提高 `warning_after/stale_after`，短期切为人工确认后接管 |
| schema 兼容破坏 | 状态写入出现额外顶层字段或不合法 event_type | 旧解析器失效 | 立即停止新写入路径，恢复到仅使用既有字段/枚举 |
| 运行态与发布证据混淆 | 变更触及 `docs/reports/final-run/` 结构 | 发布锚点污染 | 回退证据目录改动；恢复 release 快照结构到 rc1 基线 |

## 5. Public Contract 兼容矩阵（不可破坏项）

| 契约面 | 当前约束 | 本方案处理 | 是否允许破坏 |
|---|---|---|---|
| CLI 子命令 | `init/check/run/status/replay/takeover/handoff` | 保持原样 | 否 |
| CLI 参数名 | 现有 `--task-id/--run-id/...` 等 | 不改名，不删参数 | 否 |
| `pipeline_state` | `schema_version=1.0.0`，顶层 `additionalProperties=false` | 仅使用既有字段（尤其 `role_lifecycle/succession`） | 否 |
| `process_leases` | `schema_version=1.0.0`，lease 记录结构固定 | 仅沿用 lane/thread/pid/status/expiry | 否 |
| `heartbeat_status` | `schema_version=1.0.0`，状态枚举固定 | 仅沿用 `IDLE/RUNNING/WARNING/STALE/BLOCKED` | 否 |
| `events` | `schema_version=1.0.0`，`event_type` 枚举固定 | 不新增枚举值；细分信息放 `payload` | 否 |
| 发布锚点 | `v1.0.0-rc1` + `docs/reports/final-run/` | 结构保持不动 | 否 |

## 6. 建议执行优先级（P0 内）

1. 先定主窗口人设与压缩规则（最快消除职责混乱）。  
2. 再打通自愈判定与 takeover runbook（保证可恢复）。  
3. 最后做兼容性回归与证据结构检查（保证不破坏外部契约）。

该顺序满足“先消除特殊情况，再收敛复杂度，再验证零破坏”的原则。
