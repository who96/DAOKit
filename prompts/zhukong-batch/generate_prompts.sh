#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/tasks"
mkdir -p "$OUT"

cat <<'DATA' | while IFS='|' read -r ID TITLE GOAL ACTIONS ACS DEPS SCOPE VERIFY; do
DKT-001|Initialize repository skeleton|Create a clean, runnable DAOKit project skeleton for orchestrator-first development.|Create directories src/contracts/state/artifacts/docs/tests/examples;Add baseline files README Makefile pyproject .gitignore .env.example;Add bootstrap CLI command daokit init|daokit init creates required folders and core state files idempotently;Running bootstrap twice does not corrupt existing files;Basic lint/test command runs without fatal errors|None|README.md Makefile pyproject.toml .gitignore .env.example src/ contracts/ state/ docs/ tests/ examples/|make lint && make test (or equivalent)
DKT-002|Define canonical state contracts|Establish deterministic JSON schema contracts for state, events, heartbeat, and process leases.|Create JSON schemas for pipeline_state/events/heartbeat_status/process_leases;Add schema validator utility and CI schema checks;Version all contracts with schema_version|Invalid sample payloads are rejected by validator;Valid payloads pass schema checks;Schema files are documented with field semantics|DKT-001|contracts/ src/contracts/ tests/contracts/ .github/workflows/|make test-contracts && make ci-check
DKT-003|Implement orchestrator state machine|Build LangGraph workflow with explicit states and deterministic transitions.|Implement nodes extract/plan/dispatch/verify/transition;Persist state snapshots between node transitions;Add transition guards for forbidden jumps|Graph runs happy path end-to-end;Illegal transition attempts fail with explicit diagnostics;State is recoverable after process restart|DKT-002|src/orchestrator/ src/state/ tests/orchestrator/|make test-orchestrator
DKT-004|Implement strict plan compiler|Compile requirements into step contracts usable by subagents.|Build compiler with deterministic TASK_ID and RUN_ID;Enforce required fields goal/actions/acceptance/expected_outputs/dependencies;Add duplicate and contradiction checks|Compiler rejects malformed or under-specified steps;Output stable across repeated runs;Compiler output directly consumable by dispatch engine|DKT-003|src/planner/ src/contracts/ tests/planner/|make test-planner
DKT-005|Implement shim dispatch adapter|Provide create/resume/rework dispatch interface with artifact capture.|Implement wrapper around local shim path;Parse subagent outputs into structured result;Persist raw IO and normalized output paths|Adapter executes create and resume in dry-run;Every call writes request/output/error artifacts;Thread and run correlation stable across retries|DKT-004|src/dispatch/ src/artifacts/ tests/dispatch/|make test-dispatch
DKT-006|Build acceptance engine|Verify step completion by evidence, not text claims.|Implement criterion evaluator per acceptance rule;Add evidence resolver for required artifacts;Emit machine-readable failure reasons and rework directives|Missing evidence yields deterministic failure;Passing steps produce acceptance proof records;Rework payload references exact failed criteria|DKT-005|src/acceptance/ src/contracts/ tests/acceptance/|make test-acceptance
DKT-007|Add scope guard and diff auditor|Prevent subagents from touching unrelated files.|Implement allowed-path policy checker per step;Compare changed files against contract scope;Auto-flag unrelated changes for rework|Out-of-scope edit causes rejection;In-scope edits pass;Audit output lists violating files|DKT-006|src/audit/ src/acceptance/ tests/audit/|make test-audit
DKT-008|Implement function-calling adapter|Provide typed, validated local tool execution.|Define tool registry with JSON-schema validation;Add command wrappers and timeout handling;Log all tool invocations with correlation IDs|Invalid args rejected before execution;Timeout handled and recorded;Invocation logs include request/result/status|DKT-003|src/tools/function_calling/ src/tools/common/ tests/tools/|make test-tools-fc
DKT-009|Implement MCP adapter|Integrate external MCP tools while preserving auditability.|Add MCP server discovery and capability map;Implement call wrapper with retry and structured errors;Persist MCP request and response metadata|MCP tools can be listed and invoked;Failed MCP calls return actionable errors;Full call trace exists in artifacts|DKT-008|src/tools/mcp/ src/tools/common/ tests/tools/|make test-tools-mcp
DKT-010|Implement skill plugin and hook runtime|Support reusable workflow skills and lifecycle hooks.|Define skill manifest format and loader;Implement hooks pre-dispatch/post-accept/pre-compact/session-start;Enforce idempotency and timeout budget|Skills can be discovered and loaded;Hooks run at correct lifecycle points;Hook failure does not corrupt ledger state|DKT-009|src/skills/ src/hooks/ tests/skills/ tests/hooks/|make test-skills-hooks
DKT-011|Build RAG ingestion pipeline|Ingest project docs and run artifacts into retrievable memory index.|Implement chunking for markdown/json/log evidence;Add embeddings index and metadata storage;Tag chunks with source type and task and run lineage|New documents indexed and searchable;Retrieval can filter by task_id and run_id;Index rebuild deterministic and documented|DKT-002|src/rag/ingest/ src/rag/index/ tests/rag/|make test-rag-ingest
DKT-012|Integrate retrieval policies into orchestrator|Use RAG as advisory context without replacing ledger authority.|Add retrieval nodes for planning and troubleshooting;Enforce source attribution and confidence thresholds;Add policy switch to disable or enable retrieval per step|Retrieval includes sources and relevance scores;Disabling retrieval does not break core flow;Ledger unchanged by retrieval-only operations|DKT-011|src/rag/retrieval/ src/orchestrator/ tests/rag/ tests/orchestrator/|make test-rag-policy
DKT-013|Implement heartbeat daemon and status evaluator|Detect stalled long-running execution using explicit and implicit signals.|Implement heartbeat checker with interval/watch/stale thresholds;Use artifact mtime as implicit output signal;Emit deduplicated stale escalation events|Execution with output remains ACTIVE;Silence crossing threshold becomes STALE with reason code;Duplicate stale alerts suppressed in same streak|DKT-005|src/reliability/heartbeat/ src/state/ tests/reliability/|make test-heartbeat
DKT-014|Implement lease lifecycle and succession takeover|Enable safe controller replacement during active runs.|Implement lease register/heartbeat/renew/release/takeover;Bind lease ownership to task_id/run_id/step_id;On succession acceptance adopt only valid unexpired leases|Expired leases cannot be adopted;Valid running leases transferred to successor;Non-adopted running steps marked failed|DKT-013|src/reliability/lease/ src/reliability/succession/ tests/reliability/|make test-lease-succession
DKT-015|Implement core rotation handoff package|Provide near-lossless continuation across context or window reset.|Generate handoff package at pre-compact boundary;Load handoff package on new session start;Resume from ledger current step and open acceptance items|After rotation orchestrator resumes correct step;Accepted steps are not re-executed by default;Pending and failed steps remain resumable|DKT-014|src/reliability/handoff/ src/hooks/ tests/reliability/|make test-handoff
DKT-016|Build CLI workflow and operator runbooks|Give engineers a clear command surface to run and recover workflows.|Implement commands init/check/run/status/replay/takeover/handoff;Add error catalog and troubleshooting docs;Provide example projects and quickstart scripts|End-to-end scenario runs from CLI only;Recovery commands work after forced interruption;Docs sufficient for first-run onboarding|DKT-015|src/cli/ docs/ runbooks/ examples/ tests/cli/|make test-cli
DKT-017|End-to-end stress test and hardening|Validate stability under long-run, rework, and succession pressure.|Execute 2h+ long-run simulation with forced stale interval;Trigger at least one succession takeover and one rework loop;Verify event timeline and state consistency after chaos scenarios|System recovers without manual JSON repair;Every completed step links valid evidence artifacts;Final state and event log consistent and replayable|DKT-016|tests/e2e/ scripts/chaos/ docs/reports/|make test-e2e-stress
DKT-018|Open-source release package|Ship a credible public project for agent-engineering portfolio use.|Finalize docs architecture contribution security FAQ;Add sample workflows for backend-to-agent transition path;Publish release tag and roadmap for v1.1 and v1.2|Repository can be cloned and run using docs;Core demo shows orchestration consistency and core-rotation continuity;Contributors can extend tools and skills via docs|DKT-017|docs/ README.md CONTRIBUTING.md SECURITY.md CHANGELOG.md examples/|make release-check
DATA

  FILE="$OUT/${ID}.md"
  {
    echo "请进入主控模式，执行任务 ${ID}（${TITLE}）。"
    echo
    echo "【项目根目录】"
    echo "/Users/huluobo/workSpace/DAOKit"
    echo
    echo "【上下文文件（先读）】"
    echo "- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/requirements.md"
    echo "- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/design.md"
    echo "- /Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/tasks.md"
    echo
    echo "【任务锚点】"
    echo "- Task ID: ${ID}"
    echo "- Title: ${TITLE}"
    echo "- Dependencies: ${DEPS}"
    echo
    echo "【Goal】"
    echo "${GOAL}"
    echo
    echo "【Concrete Actions】"
    IFS=';' read -r A1 A2 A3 <<<"$ACTIONS"
    echo "1) ${A1}"
    echo "2) ${A2}"
    echo "3) ${A3}"
    echo
    echo "【Acceptance Criteria】"
    IFS=';' read -r C1 C2 C3 <<<"$ACS"
    echo "1) ${C1}"
    echo "2) ${C2}"
    echo "3) ${C3}"
    echo
    echo "【Allowed Scope（超出即拒绝）】"
    echo "- ${SCOPE}"
    echo
    echo "【Verification Baseline】"
    echo "- ${VERIFY}"
    echo
    echo "【Verification Log 格式契约】"
    echo "1) verification.log 必须有命令证据。"
    echo "2) 允许以下任一格式被验收器识别："
    echo "   - Command: <cmd>"
    echo "   - === COMMAND ENTRY N START/END ==="
    echo "3) 为避免解析器差异，建议每个 COMMAND ENTRY 块内同时写一行 Command: <cmd>。"
    echo
    echo "【硬约束】"
    echo "1) 主控不得直接改文件、不得直接执行有副作用命令。"
    echo "2) 只能通过本地 shim 派发 subagent。"
    echo "3) 验收仅基于 artifacts 与命令日志，不接受口头声明。"
    echo "4) 如不满足验收标准，必须输出差分 rework JSON 并继续迭代。"
    echo "5) 每个任务最多 3 轮 rework，超限即标记 FAILED 并报告阻塞。"
    echo "6) 如基线验证命令缺失（例如 Make target 不存在），允许等价替代命令，但必须在 verification.log 说明替代关系与覆盖范围。"
    echo
    echo "【最终输出（只输出一次）】"
    echo "- Task ID"
    echo "- Status: SUCCESS | FAILED"
    echo "- Summary"
    echo "- Files Changed"
    echo "- Commands Executed"
    echo "- Verification Results"
    echo "- Risks / Limitations"
    echo "- Next Step Suggestion"
  } > "$FILE"
done
