from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence


DEFAULT_TIMEOUT_SECONDS = 45


def _parse_payload(raw: str) -> dict[str, Any]:
    stripped = raw.strip()
    if not stripped:
        return {}
    parsed = json.loads(stripped)
    if not isinstance(parsed, Mapping):
        raise ValueError("shim payload must be a JSON object")
    return dict(parsed)


def _expect_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


def _build_prompt(*, action: str, payload: Mapping[str, Any]) -> str:
    request = _expect_mapping(payload.get("request"))
    title = str(request.get("step_title") or "Complete the assigned step").strip()
    goal = str(request.get("goal") or "").strip()
    acceptance = request.get("acceptance_criteria")
    criteria = []
    if isinstance(acceptance, list):
        criteria = [str(item).strip() for item in acceptance if isinstance(item, str) and item.strip()]

    lines = [
        "You are executing a single coding-agent lane dispatch task.",
        f"Action: {action}",
        f"Task ID: {request.get('task_id') or payload.get('task_id')}",
        f"Run ID: {request.get('run_id') or payload.get('run_id')}",
        f"Step ID: {request.get('step_id') or payload.get('step_id')}",
        f"Step Title: {title}",
    ]
    if goal:
        lines.append(f"Goal: {goal}")
    if criteria:
        lines.append("Acceptance Criteria:")
        lines.extend(f"- {item}" for item in criteria[:3])
    lines.extend(
        [
            "Return a concise implementation status and next action.",
            "Keep output short and actionable.",
        ]
    )
    return "\n".join(lines)


def _build_fallback_output(*, action: str, payload: Mapping[str, Any], reason: str) -> dict[str, Any]:
    request = _expect_mapping(payload.get("request"))
    title = str(request.get("step_title") or "execute step").strip()
    return {
        "status": "success",
        "action": action,
        "execution_mode": "fallback",
        "llm_invoked": False,
        "message": f"fallback execution used for {title}",
        "fallback_reason": reason,
    }


def _resolve_timeout_seconds() -> int:
    raw = os.environ.get("DAOKIT_CODEX_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        parsed = int(raw.strip())
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return parsed if parsed > 0 else DEFAULT_TIMEOUT_SECONDS


def _resolve_codex_command(prompt: str) -> list[str]:
    codex_bin = os.environ.get("DAOKIT_CODEX_BIN", "codex").strip() or "codex"
    command = [codex_bin, "exec", "--skip-git-repo-check"]
    model = os.environ.get("DAOKIT_CODEX_MODEL")
    if model is not None and model.strip():
        command.extend(["--model", model.strip()])
    return command + ["--output-last-message", "{OUTPUT_PATH}", prompt]


def _execute_codex(*, prompt: str) -> dict[str, Any]:
    timeout_seconds = _resolve_timeout_seconds()
    template_command = _resolve_codex_command(prompt)
    with tempfile.TemporaryDirectory() as tmp:
        output_path = Path(tmp) / "codex-last-message.txt"
        command = [output_path.as_posix() if token == "{OUTPUT_PATH}" else token for token in template_command]
        completed = subprocess.run(
            command,
            input=None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        last_message = ""
        if output_path.exists():
            last_message = output_path.read_text(encoding="utf-8").strip()
        if not last_message:
            last_message = (completed.stdout or "").strip()

        if completed.returncode != 0:
            stderr_text = (completed.stderr or "").strip()
            reason = f"codex exec exited with {completed.returncode}"
            if stderr_text:
                reason = f"{reason}: {stderr_text}"
            raise RuntimeError(reason)

        return {
            "status": "success",
            "execution_mode": "real_llm",
            "llm_invoked": True,
            "message": last_message or "codex execution completed",
            "command": command,
            "return_code": int(completed.returncode),
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
        }


def run_shim(argv: Sequence[str] | None = None, *, stdin_text: str | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(prog="codex-worker-shim")
    parser.add_argument("action", choices=("create", "resume", "rework"))
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    raw_payload = stdin_text if stdin_text is not None else sys.stdin.read()
    payload = _parse_payload(raw_payload)

    common_fields = {
        "action": args.action,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "step_id": args.step_id,
        "thread_id": args.thread_id,
    }
    if args.dry_run:
        return {
            **common_fields,
            "status": "success",
            "execution_mode": "dry_run",
            "llm_invoked": False,
            "message": "dry-run dispatch execution",
        }

    prompt = _build_prompt(action=args.action, payload=payload)
    try:
        codex_result = _execute_codex(prompt=prompt)
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        return {
            **common_fields,
            **_build_fallback_output(
                action=args.action,
                payload=payload,
                reason=str(exc),
            ),
        }

    return {
        **common_fields,
        **codex_result,
    }


def main(argv: Sequence[str] | None = None) -> int:
    payload = run_shim(argv)
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
