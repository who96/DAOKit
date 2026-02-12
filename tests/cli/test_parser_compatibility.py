from __future__ import annotations

import argparse
import unittest

from cli.main import _build_parser


EXPECTED_EXISTING_COMMANDS = (
    "init",
    "check",
    "run",
    "status",
    "replay",
    "takeover",
    "handoff",
)

EXPECTED_LONG_OPTION_DESTS: dict[str, dict[str, str]] = {
    "init": {
        "--root": "root",
    },
    "check": {
        "--root": "root",
        "--artifact-root": "artifact_root",
        "--check-interval": "check_interval",
        "--warning-after": "warning_after",
        "--stale-after": "stale_after",
        "--json": "json",
    },
    "run": {
        "--root": "root",
        "--task-id": "task_id",
        "--run-id": "run_id",
        "--goal": "goal",
        "--step-id": "step_id",
        "--lane": "lane",
        "--thread-id": "thread_id",
        "--lease-ttl": "lease_ttl",
        "--simulate-interruption": "simulate_interruption",
        "--no-lease": "no_lease",
    },
    "status": {
        "--root": "root",
        "--task-id": "task_id",
        "--run-id": "run_id",
        "--json": "json",
    },
    "replay": {
        "--root": "root",
        "--source": "source",
        "--limit": "limit",
        "--json": "json",
    },
    "takeover": {
        "--root": "root",
        "--task-id": "task_id",
        "--run-id": "run_id",
        "--successor-thread-id": "successor_thread_id",
        "--successor-pid": "successor_pid",
        "--lease-ttl": "lease_ttl",
    },
    "handoff": {
        "--root": "root",
        "--create": "create",
        "--apply": "apply",
        "--package-path": "package_path",
        "--include-accepted-steps": "include_accepted_steps",
        "--evidence-path": "evidence_path",
    },
}

EXPECTED_BUNDLE_LONG_OPTION_DESTS = {
    "--root": "root",
    "--generate": "generate",
    "--review": "review",
    "--reverify": "reverify",
    "--source-dir": "source_dir",
    "--bundle-root": "bundle_root",
    "--summary-json": "summary_json",
    "--json": "json",
}


def _subparser_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):  # type: ignore[attr-defined]
            return dict(action.choices)
    raise AssertionError("expected parser to define subcommands")


def _long_option_dest_map(parser: argparse.ArgumentParser) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for action in parser._actions:
        for option in action.option_strings:
            if option == "--help":
                continue
            if option.startswith("--"):
                mapping[option] = action.dest
    return mapping


class CliParserCompatibilityTests(unittest.TestCase):
    def test_prog_name_is_frozen(self) -> None:
        parser = _build_parser()
        self.assertEqual(parser.prog, "daokit-cli")

    def test_cli_command_names_remain_unchanged(self) -> None:
        parser = _build_parser()
        choices = _subparser_choices(parser)
        command_names = tuple(choices.keys())
        self.assertEqual(command_names[: len(EXPECTED_EXISTING_COMMANDS)], EXPECTED_EXISTING_COMMANDS)
        self.assertIn("bundle", choices)

    def test_cli_argument_names_and_destinations_remain_unchanged(self) -> None:
        parser = _build_parser()
        choices = _subparser_choices(parser)

        for command in EXPECTED_EXISTING_COMMANDS:
            self.assertIn(command, choices)
            self.assertEqual(
                _long_option_dest_map(choices[command]),
                EXPECTED_LONG_OPTION_DESTS[command],
                f"{command} parser surface changed",
            )

    def test_bundle_argument_names_are_stable(self) -> None:
        parser = _build_parser()
        choices = _subparser_choices(parser)
        self.assertIn("bundle", choices)
        self.assertEqual(_long_option_dest_map(choices["bundle"]), EXPECTED_BUNDLE_LONG_OPTION_DESTS)


if __name__ == "__main__":
    unittest.main()
