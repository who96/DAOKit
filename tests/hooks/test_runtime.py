from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

from hooks.runtime import HookPoint, HookRuntime
from skills.loader import SkillLoader


def _write_skill_with_hook(root: Path) -> Path:
    skill_dir = root / "skill-with-hook"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "hook_impl.py").write_text(
        (
            "def before_dispatch(ledger_state, context):\n"
            "    ledger_state['skill_loaded'] = True\n"
            "    ledger_state['hook_context'] = context.get('flag')\n"
        ),
        encoding="utf-8",
    )
    (skill_dir / "skill.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "name": "skill-with-hook",
                "version": "0.1.0",
                "hooks": [
                    {
                        "event": "pre-dispatch",
                        "handler": "hook_impl.py:before_dispatch",
                        "timeout_seconds": 0.5,
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return skill_dir


class HookRuntimeTests(unittest.TestCase):
    def test_hooks_run_at_all_lifecycle_points(self) -> None:
        runtime = HookRuntime()
        called_points: list[str] = []

        for point in HookPoint:
            runtime.register(
                hook_point=point.value,
                hook_name=f"{point.value}-hook",
                callback=lambda ledger_state, context, point_name=point.value: (
                    called_points.append(point_name),
                    ledger_state.setdefault("order", []).append(point_name),
                ),
            )

        ledger: dict[str, object] = {}
        for point in HookPoint:
            result = runtime.run(
                hook_point=point.value,
                ledger_state=ledger,
                context={},
                idempotency_key=f"key-{point.value}",
            )
            self.assertEqual(result.status, "success")
            ledger = result.ledger_state

        self.assertEqual(called_points, [point.value for point in HookPoint])
        self.assertEqual(ledger.get("order"), [point.value for point in HookPoint])

    def test_hook_failure_rolls_back_ledger_state(self) -> None:
        runtime = HookRuntime()
        runtime.register(
            hook_point=HookPoint.PRE_DISPATCH.value,
            hook_name="mutate-and-fail",
            callback=lambda ledger_state, _context: (
                ledger_state.__setitem__("counter", 999),
                (_ for _ in ()).throw(RuntimeError("boom")),
            ),
        )

        original_ledger = {"counter": 1, "nested": {"ok": True}}
        result = runtime.run(
            hook_point=HookPoint.PRE_DISPATCH.value,
            ledger_state=original_ledger,
            context={},
            idempotency_key="rollback-case",
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.ledger_state, original_ledger)
        self.assertEqual(original_ledger, {"counter": 1, "nested": {"ok": True}})

    def test_idempotency_key_prevents_duplicate_execution(self) -> None:
        runtime = HookRuntime()
        call_counter = {"count": 0}

        def callback(ledger_state: dict[str, object], _context: dict[str, object]) -> None:
            call_counter["count"] += 1
            ledger_state["counter"] = int(ledger_state.get("counter", 0)) + 1

        runtime.register(
            hook_point=HookPoint.POST_ACCEPT.value,
            hook_name="idempotent-hook",
            callback=callback,
            idempotent=True,
        )

        first = runtime.run(
            hook_point=HookPoint.POST_ACCEPT.value,
            ledger_state={"counter": 0},
            context={},
            idempotency_key="same-key",
        )
        second = runtime.run(
            hook_point=HookPoint.POST_ACCEPT.value,
            ledger_state=first.ledger_state,
            context={},
            idempotency_key="same-key",
        )

        self.assertEqual(call_counter["count"], 1)
        self.assertEqual(first.status, "success")
        self.assertEqual(second.status, "success")
        self.assertEqual(first.ledger_state["counter"], 1)
        self.assertEqual(second.ledger_state["counter"], 1)
        self.assertEqual(second.entries[0].status, "skipped")

    def test_timeout_budget_is_enforced(self) -> None:
        runtime = HookRuntime(default_timeout_seconds=0.01)

        def slow_hook(ledger_state: dict[str, object], _context: dict[str, object]) -> None:
            time.sleep(0.03)
            ledger_state["slow"] = True

        runtime.register(
            hook_point=HookPoint.PRE_COMPACT.value,
            hook_name="slow-hook",
            callback=slow_hook,
        )

        initial = {"slow": False}
        result = runtime.run(
            hook_point=HookPoint.PRE_COMPACT.value,
            ledger_state=initial,
            context={},
            idempotency_key="timeout-key",
        )

        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.ledger_state, initial)
        self.assertIn("timeout", result.entries[0].status)

    def test_can_register_hooks_from_loaded_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_skill_with_hook(root)

            loaded_skill = SkillLoader(search_paths=[root]).load("skill-with-hook")
            runtime = HookRuntime()
            runtime.register_skill(loaded_skill)

            result = runtime.run(
                hook_point=HookPoint.PRE_DISPATCH.value,
                ledger_state={},
                context={"flag": "from-test"},
                idempotency_key="skill-hook",
            )

            self.assertEqual(result.status, "success")
            self.assertTrue(result.ledger_state["skill_loaded"])
            self.assertEqual(result.ledger_state["hook_context"], "from-test")


if __name__ == "__main__":
    unittest.main()
