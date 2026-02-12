from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cli.main import _build_parser, _cmd_run
from daokit.bootstrap import initialize_repository
from orchestrator.engine import RuntimeEngine, resolve_runtime_engine


class _FakeRuntime:
    def __init__(self, *, status: str = "DONE") -> None:
        self._status = status

    def run(self) -> dict[str, str]:
        return {
            "status": self._status,
            "current_step": "S1",
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


class EngineRolloutCliCompatibilityTests(unittest.TestCase):
    def _run_args(self, root: Path) -> argparse.Namespace:
        parser = _build_parser()
        return parser.parse_args(
            [
                "run",
                "--root",
                str(root),
                "--task-id",
                "DKT-035",
                "--run-id",
                "RUN-ENGINE-CONTROL",
                "--goal",
                "Validate rollout selector control",
                "--no-lease",
            ]
        )

    def test_run_parser_does_not_add_public_engine_flags(self) -> None:
        parser = _build_parser()
        run_parser = _subparser_choices(parser)["run"]
        option_map = _long_option_dest_map(run_parser)

        self.assertNotIn("--engine", option_map)
        self.assertNotIn("--runtime-engine", option_map)
        self.assertNotIn("--engine-mode", option_map)

    def test_run_forwards_optional_runtime_settings_to_engine_factory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initialize_repository(root)
            settings_path = root / "state" / "runtime_settings.json"
            settings_payload = {"runtime": {"mode": "integrated"}}
            settings_path.write_text(json.dumps(settings_payload), encoding="utf-8")

            args = self._run_args(root)
            captured: dict[str, object] = {}

            def _fake_create_runtime(**kwargs: object) -> _FakeRuntime:
                captured.update(kwargs)
                return _FakeRuntime()

            with patch("cli.main.create_runtime", side_effect=_fake_create_runtime):
                exit_code = _cmd_run(args)

            self.assertEqual(exit_code, 0)
            self.assertEqual(captured.get("config"), settings_payload)

    def test_env_selector_overrides_runtime_settings_without_new_cli_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initialize_repository(root)
            settings_path = root / "state" / "runtime_settings.json"
            settings_path.write_text(json.dumps({"runtime": {"mode": "legacy"}}), encoding="utf-8")

            args = self._run_args(root)
            captured_engine: dict[str, RuntimeEngine] = {}

            def _fake_create_runtime(**kwargs: object) -> _FakeRuntime:
                selected = resolve_runtime_engine(
                    explicit_engine=None,
                    env=kwargs.get("env"),
                    config=kwargs.get("config"),
                )
                captured_engine["selected"] = selected
                return _FakeRuntime()

            with patch.dict("cli.main.os.environ", {"DAOKIT_RUNTIME_ENGINE": "langgraph"}, clear=False):
                with patch("cli.main.create_runtime", side_effect=_fake_create_runtime):
                    exit_code = _cmd_run(args)

            self.assertEqual(exit_code, 0)
            self.assertEqual(captured_engine.get("selected"), RuntimeEngine.LANGGRAPH)


if __name__ == "__main__":
    unittest.main()
