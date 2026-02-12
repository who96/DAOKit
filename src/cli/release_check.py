from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Callable, Sequence

DEFAULT_COMMANDS = ("make lint", "make test")
DEFAULT_VERIFICATION_LOG = Path(".artifacts/release-check/verification.log")
DEFAULT_SUMMARY_JSON = Path(".artifacts/release-check/summary.json")


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str


CommandRunner = Callable[[str, Path], CommandResult]


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


def _format_command_entry(index: int, command: str, cwd: Path, result: CommandResult) -> str:
    lines = [
        f"=== COMMAND ENTRY {index} START ===",
        f"Command: {command}",
        f"Working Directory: {cwd}",
        "--- OUTPUT START ---",
    ]
    stripped_output = result.output.rstrip("\n")
    if stripped_output:
        lines.append(stripped_output)
    lines.extend(
        [
            "--- OUTPUT END ---",
            f"Exit Code: {result.exit_code}",
            f"=== COMMAND ENTRY {index} END ===",
            "",
        ]
    )
    return "\n".join(lines)


def run_release_check(
    *,
    commands: Sequence[str] = DEFAULT_COMMANDS,
    verification_log: Path = DEFAULT_VERIFICATION_LOG,
    summary_json: Path = DEFAULT_SUMMARY_JSON,
    working_directory: Path = Path("."),
    runner: CommandRunner | None = None,
) -> int:
    normalized_commands = tuple(command.strip() for command in commands if command.strip())
    if not normalized_commands:
        raise ValueError("release-check requires at least one command")

    command_runner = runner or _run_command
    normalized_cwd = Path(working_directory)
    verification_path = Path(verification_log)
    summary_path = Path(summary_json)

    verification_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    entries: list[str] = []
    command_summaries: list[dict[str, object]] = []
    failed_command: str | None = None
    exit_code = 0

    for index, command in enumerate(normalized_commands, start=1):
        result = command_runner(command, normalized_cwd)
        entries.append(_format_command_entry(index, command, normalized_cwd, result))
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

    verification_path.write_text("".join(entries), encoding="utf-8")

    summary_payload = {
        "schema_version": "1.0.0",
        "workflow": "release-check",
        "status": "failed" if failed_command else "passed",
        "deterministic_sequence": list(normalized_commands),
        "commands": command_summaries,
        "failed_command": failed_command,
        "verification_log": str(verification_path),
    }
    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release-check",
        description="Run deterministic release verification with machine-parseable evidence.",
    )
    parser.add_argument("--verification-log", default=str(DEFAULT_VERIFICATION_LOG))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--working-directory", default=".")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return run_release_check(
        verification_log=Path(args.verification_log),
        summary_json=Path(args.summary_json),
        working_directory=Path(args.working_directory),
    )


if __name__ == "__main__":
    raise SystemExit(main())
