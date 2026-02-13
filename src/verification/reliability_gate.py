from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_WORKING_DIRECTORY = Path(".")
DEFAULT_VERIFICATION_LOG = Path(".artifacts/reliability-gate/verification.log")
DEFAULT_SUMMARY_JSON = Path(".artifacts/reliability-gate/summary.json")
DEFAULT_COMMANDS = (
    "PYTHONPATH=src python3 -m unittest tests/verification/test_criteria_registry.py -v",
    "PYTHONPATH=src python3 -m unittest tests/reliability/test_observability_diagnostics_model.py -v",
    "PYTHONPATH=src python3 -m unittest tests/reliability/test_core_rotation_chaos_matrix.py -v",
    "PYTHONPATH=src python3 -m unittest tests/e2e/test_integrated_reliability.py -v",
)


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str


def _run_command(command: str, cwd: Path) -> CommandResult:
    completed = subprocess.run(
        ["bash", "-lc", command],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout
    if completed.stderr:
        if output and not output.endswith("\n"):
            output += "\n"
        output += completed.stderr
    return CommandResult(exit_code=completed.returncode, output=output)


def _format_command_entry(index: int, command: str, result: CommandResult) -> str:
    output = result.output.rstrip("\n")
    lines = [
        f"=== COMMAND ENTRY {index} START ===",
        f"Command: {command}",
        "--- OUTPUT START ---",
    ]
    if output:
        lines.append(output)
    lines.extend(
        [
            "--- OUTPUT END ---",
            f"Exit Code: {result.exit_code}",
            f"=== COMMAND ENTRY {index} END ===",
            "",
        ]
    )
    return "\n".join(lines)


def run_reliability_gate(
    *,
    commands: Sequence[str],
    working_directory: Path,
    verification_log: Path,
    summary_json: Path,
) -> int:
    normalized_cwd = Path(working_directory).resolve()
    verification_log.parent.mkdir(parents=True, exist_ok=True)
    summary_json.parent.mkdir(parents=True, exist_ok=True)

    entries: list[str] = []
    command_summaries: list[dict[str, object]] = []
    failed_command = None
    exit_code = 0

    for index, command in enumerate(commands, start=1):
        result = _run_command(command, normalized_cwd)
        entries.append(_format_command_entry(index, command, result))
        command_summaries.append(
            {
                "index": index,
                "command": command,
                "exit_code": result.exit_code,
                "status": "passed" if result.exit_code == 0 else "failed",
            }
        )
        if result.exit_code != 0:
            failed_command = command
            exit_code = result.exit_code
            break

    verification_log.write_text("".join(entries), encoding="utf-8")

    summary = {
        "schema_version": "1.0.0",
        "workflow": "reliability-gate",
        "status": "failed" if failed_command else "passed",
        "failed_command": failed_command,
        "deterministic_sequence": list(commands),
        "commands": command_summaries,
        "verification_log": str(verification_log),
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reliability-gate",
        description="Run deterministic reliability readiness checks required by release gates.",
    )
    parser.add_argument(
        "--working-directory",
        default=str(DEFAULT_WORKING_DIRECTORY),
    )
    parser.add_argument(
        "--verification-log",
        default=str(DEFAULT_VERIFICATION_LOG),
    )
    parser.add_argument(
        "--summary-json",
        default=str(DEFAULT_SUMMARY_JSON),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return run_reliability_gate(
        commands=DEFAULT_COMMANDS,
        working_directory=Path(args.working_directory),
        verification_log=Path(args.verification_log),
        summary_json=Path(args.summary_json),
    )


if __name__ == "__main__":
    raise SystemExit(main())
