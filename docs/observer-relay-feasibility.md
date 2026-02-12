# Observer Relay 可行性报告（P0）

## 输入事实源（唯一依据）
- `/Users/huluobo/workSpace/DAOKit/窗口交接20260212102259.md`
- `/Users/huluobo/workSpace/DAOKit/README.md`
- `/Users/huluobo/workSpace/DAOKit/docs/architecture.md`
- `/Users/huluobo/workSpace/DAOKit/src/cli/main.py`
- `/Users/huluobo/workSpace/DAOKit/contracts/pipeline_state.schema.json`
- `/Users/huluobo/workSpace/DAOKit/contracts/process_leases.schema.json`
- `/Users/huluobo/workSpace/DAOKit/contracts/heartbeat_status.schema.json`
- `/Users/huluobo/workSpace/DAOKit/contracts/events.schema.json`
- `/Users/huluobo/workSpace/DAOKit/docs/extensions.md`

## 1. 核心判断

【核心判断】  
✅ 值得做。  
原因：现有 DAOKit 已具备 observer relay 所需的关键基础能力：  
1. 严格的状态账本与事件回放（`state/pipeline_state.json`、`state/events.jsonl`、`status/replay`）。  
2. 长任务连续性机制（heartbeat + lease + takeover + handoff）。  
3. 现有 CLI 已暴露 `check/status/replay/takeover/handoff` 恢复面，无需破坏参数面。

【关键洞察】  
- 数据结构：`pipeline_state + process_leases + heartbeat_status + events` 已形成完整控制面闭环。  
- 复杂度：把对外窗口降级为 relay 后，可把“执行/决策”复杂性集中到主控 agent（subagent）。  
- 风险点：若把路由元数据硬塞进 `pipeline_state` 顶层会触发 schema 破坏（`additionalProperties: false`）。

## 2. 控制流可行性

现状主流程（架构文档）：`extract -> plan -> dispatch -> verify -> transition`。  
提案后的控制流可保持不变，只调整“谁在外部窗口承担主控”：

1. 用户输入到对外主窗口（observer relay）。
2. 主窗口仅转发给主控 agent（主控也在 subagent 链路中）。
3. 主控 agent 负责 plan/dispatch/verify/transition 决策与执行编排。
4. 状态与事件落入现有 ledger（`pipeline_state/process_leases/heartbeat/events`）。
5. 主窗口通过 `status/check/replay` 做可视化回传，不直接下场执行。

结论：控制流可行，且与现有 CLI 子命令集合兼容（`init/check/run/status/replay/takeover/handoff`）。

## 3. 数据流可行性

### 3.1 建议的数据分层
- 持久层（SoT，不变）：`state/` 下四类契约文件 + handoff package。
- 会话层（主窗口最小保留）：用户目标、约束、最新指令、当前阻塞、主控路由摘要。
- 临时层（可丢弃）：执行噪声日志、重复状态播报、历史失败堆栈垃圾输出。

### 3.2 与现有契约的映射
- 主控路由与执行归属：映射到 `process_leases.leases[*]` 的 `lane/thread_id/pid/status`。
- 主控接班历史：映射到 `pipeline_state.succession.last_takeover_at`。
- 活性判定：映射到 `heartbeat_status.status/reason_code/last_heartbeat_at`。
- 状态转移与诊断：映射到 `events`（`event_type/severity/payload/dedup_key`）。

结论：无需改变 `schema_version=1.0.0`，即可承载 observer relay 模式。

## 4. 故障域分析

1. 对外主窗口故障（relay 进程/上下文丢失）  
   - 影响：仅影响“转发与展示”，不应影响执行所有权。  
   - 恢复：重建 relay 后读取 `status` 与 handoff package 即可继续。

2. 主控 agent 故障（卡死/退出/心跳中断）  
   - 影响：当前 lease 可能悬挂，执行停滞。  
   - 恢复：heartbeat 进入 `WARNING/STALE`，触发 `takeover`。

3. worker lane 故障  
   - 影响：单步执行失败或阻塞。  
   - 恢复：由主控基于 lease/event 决策重试、接管或 handoff。

4. 状态文件异常（缺失/JSON 破损）  
   - 影响：`check/status/replay` 不可用。  
   - 恢复：沿用现有 CLI 错误边界（`E_CHECK_STATE_INVALID` 等）并回退到最近可用快照/包。

## 5. 主控自愈闭环（检测/判定/接管/恢复）

### 5.1 检测（Detect）
- 心跳检测：`check` 使用 `evaluate_heartbeat(...)`，依据 `warning_after/stale_after` 给出 `RUNNING/WARNING/STALE/BLOCKED`。
- 账本检测：`status` 提供 `pipeline_state + heartbeat_status + leases + handoff_package` 聚合视图。
- 事件检测：`replay --source events` 回看 `HEARTBEAT_WARNING/HEARTBEAT_STALE/LEASE_TAKEOVER`。

### 5.2 判定（Decide）
- 当 `heartbeat.status=WARNING`：进入观察窗口，暂不接管。
- 当 `heartbeat.status=STALE` 或 lease 过期/不可续租：判定主控失活，进入接管。
- 当 handoff package 可用：优先按包恢复最小损失上下文。

### 5.3 接管（Takeover）
- 使用现有 `takeover` 子命令调用 `SuccessionManager.accept_successor(...)`。  
- 结果字段（`adopted_step_ids/failed_step_ids/takeover_at`）可直接作为恢复证据。

### 5.4 恢复（Recover）
- 可选执行 `handoff --apply`，把 package 恢复到当前 ledger。
- 继续由新主控 agent 按既有 `run`/step 流推进。
- 通过 `status/check/replay` 验证恢复后健康与一致性。

## 6. 与 lease / heartbeat / handoff 的映射关系

| 方案目标 | 现有机制 | 直接映射方式 | 兼容性判断 |
|---|---|---|---|
| 主窗口仅观察转发 | `status/check/replay` | 只读展示 pipeline/heartbeat/leases/events | 兼容 |
| 主控进入 subagent 链路 | `run + lease register/release` | 主控以 lane/thread_id 持有 lease | 兼容 |
| 主控自愈 | `check + takeover` | heartbeat/lease 触发接班 | 兼容 |
| 上下文恢复 | `handoff create/apply` | package 作为恢复输入 | 兼容 |
| 可审计回溯 | `events.jsonl` | 使用 event_type + payload + dedup_key | 兼容 |

## 7. 结论与落地边界

1. 该方案在 DAOKit 现有架构内可落地，且可做到“不改 CLI 对外参数名、不改 schema_version=1.0.0”。  
2. 关键落点不是新增协议，而是重新约束职责：外部窗口 relay-only，主控 agent 负责决策与自愈。  
3. 破坏性风险主要来自“越过现有 schema 边界扩字段”与“混淆 runtime state 与 release evidence”；两者都可通过兼容矩阵和回滚策略约束。
