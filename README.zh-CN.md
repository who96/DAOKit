# DAOKit

语言： [English](README.md) | **中文**

DAOKit 是一个面向后端团队的开源 Agent 工程工具包，适用于需要严格编排、可审计执行以及长时任务稳定连续性的场景。

## 为什么选择 DAOKit

- **Observer-relay 边界**：外部窗口仅负责转发与可视化；执行权限始终留在控制器通道。
- **证据优先验收**：每个被验收的任务都由工件支撑（`report.md`、`verification.log`、`audit-summary.md`）。
- **心跳 + 租约接替**：长时运行可识别失效所有权、触发接管并安全续跑。
- **核心轮换连续性**：交接包支持在窗口或上下文替换后近无损恢复。

## 发布锚点

最新发布快照与验收报告：

- [发布快照](docs/reports/final-run/RELEASE_SNAPSHOT.md)
- [最终验收](docs/reports/FINAL_ACCEPTANCE.md)
- [证据包](docs/reports/final-run/evidence/)
- [证据清单 SHA256](docs/reports/final-run/evidence_manifest.sha256)

## 快速开始

### 1. 克隆并进入仓库

```bash
git clone <repository-url> DAOKit
cd DAOKit
```

### 2. 创建虚拟环境并安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                # 仅核心
pip install -e ".[llm]"        # + LLM dispatch（OpenAI 兼容 API）
pip install -e ".[rag]"        # + RAG 检索（Chroma + sentence-transformers）
pip install -e ".[llm,rag]"    # 全部
```

### 3. 初始化运行目录结构

```bash
PYTHONPATH=src python3 -m cli init --root .
```

### 4. 运行一个核心工作流

```bash
PYTHONPATH=src python3 -m cli run \
  --root . \
  --task-id DKT-018-DEMO \
  --run-id RUN-README-001 \
  --goal "README demo run"
```

### 5. 查看状态、事件与健康检查

```bash
PYTHONPATH=src python3 -m cli status --root . --task-id DKT-018-DEMO --run-id RUN-README-001 --json
PYTHONPATH=src python3 -m cli replay --root . --source events --limit 10
PYTHONPATH=src python3 -m cli check --root .
```

## LLM Dispatch 后端配置

默认情况下，编排器通过外部子进程（`shim` 后端）执行步骤。
如需直接调用 LLM API（DeepSeek、OpenAI 或任何 OpenAI 兼容供应商），
在项目根目录创建 `.env` 文件并配置以下环境变量：

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
DAOKIT_DISPATCH_BACKEND=llm
DAOKIT_LLM_API_KEY=sk-your-api-key
DAOKIT_LLM_BASE_URL=https://api.deepseek.com   # 或 https://api.openai.com/v1
DAOKIT_LLM_MODEL=deepseek-chat                  # 或 gpt-4o 等
DAOKIT_LLM_MAX_TOKENS=4096
DAOKIT_LLM_TEMPERATURE=0.0
DAOKIT_LLM_TIMEOUT_SECONDS=120
```

使用 LLM 后端运行：

```bash
PYTHONPATH=src python3 -m cli run \
  --root . \
  --task-id MY-TASK-001 \
  --goal "实现一个带校验的配置解析器"
```

编排器将在 `dispatch` 阶段直接调用 LLM API。
所有请求和响应都持久化为 `artifacts/dispatch/` 下的工件文件。

| 后端 | 工作方式 | 适用场景 |
|------|---------|---------|
| `shim`（默认） | 运行 `codex-worker-shim` 子进程 | 有 Codex CLI，需要沙箱执行 |
| `llm` | 直接 HTTP 调用 LLM API | 无 Codex，轻量接入 DeepSeek/OpenAI |

## 演示工作流

- [编排一致性演示](examples/cli/quickstart.sh)
- [Observer-relay 协作恢复链演示](examples/cli/observer_relay_recovery_chain.sh)
- [Integrated 模式可靠性恢复链演示](examples/cli/integrated_reliability_recovery_chain.sh)
- [恢复演示](examples/cli/recovery.sh)
- [核心轮换连续性演示](examples/cli/core_rotation_continuity.sh)
- [后端到 Agent 迁移路径](examples/cli/backend_to_agent_path.sh)

运行演示：

```bash
bash examples/cli/quickstart.sh .
bash examples/cli/observer_relay_recovery_chain.sh .
bash examples/cli/integrated_reliability_recovery_chain.sh .artifacts/readme_demo/integrated .artifacts/readme_demo/integrated/integrated-reliability-summary.json
bash examples/cli/recovery.sh .
bash examples/cli/core_rotation_continuity.sh .
bash examples/cli/backend_to_agent_path.sh .
```

## 文档导航

- [CLI 快速上手](docs/cli-quickstart.md)
- [架构总览](docs/architecture.md)
- [扩展指南（tools/skills/hooks）](docs/extensions.md)
- [后端到 Agent 工作流](docs/backend-to-agent-workflows.md)
- [多 Agent 协作工作流（English）](docs/workflows/multi-agent-collaboration.en.md)
- [多 Agent 协作工作流（中文）](docs/workflows/multi-agent-collaboration.zh-CN.md)
- [LangChain + LangGraph + RAG 协作机制（English）](docs/workflows/langchain-langgraph-rag-cooperation.en.md)
- [LangChain + LangGraph + RAG 协作机制（中文）](docs/workflows/langchain-langgraph-rag-cooperation.zh-CN.md)
- [Codex 集成运行手册（English）](docs/workflows/codex-integration-runbook.en.md)
- [Codex 集成运行手册（中文）](docs/workflows/codex-integration-runbook.zh-CN.md)
- [Observer-relay 可行性报告](docs/observer-relay-feasibility.md)
- [Observer-relay 角色与压缩策略](docs/observer-relay-persona-and-compaction.md)
- [Observer-relay 优化计划](docs/observer-relay-optimization-plan.md)
- [Observer-relay 回滚运行手册](docs/observer-relay-rollback-runbook.md)
- [错误目录](docs/error-catalog.md)
- [常见问题](docs/faq.md)
- [路线图](docs/roadmap.md)
- [安全策略](SECURITY.md)
- [贡献指南](CONTRIBUTING.md)

## 开发验证

```bash
make lint
make test
```

若你的分支中没有 `make release-check`，最小验证基线为 `make lint && make test`，并补充执行上方演示脚本。

## 兼容性护栏

- 保持 CLI 命令名和参数名不变。
- 保持与 `schema_version=1.0.0` 兼容的契约语义。
- 保持 `v1.0.0-rc1` 发布锚点语义与 `docs/reports/final-run/` 证据结构不变。
