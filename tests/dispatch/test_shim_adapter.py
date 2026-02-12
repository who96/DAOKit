from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from artifacts.dispatch_artifacts import DispatchArtifactStore
from dispatch.shim_adapter import ShimDispatchAdapter


class ShimDispatchAdapterTests(unittest.TestCase):
    def test_create_and_resume_execute_in_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = DispatchArtifactStore(root / "artifacts")
            adapter = ShimDispatchAdapter(
                shim_path="/usr/local/bin/daokit-shim",
                artifact_store=store,
            )

            create_result = adapter.create(
                task_id="DKT-005",
                run_id="DKT-005_RUN",
                step_id="S1",
                request={"task_kind": "step"},
                dry_run=True,
            )
            resume_result = adapter.resume(
                task_id="DKT-005",
                run_id="DKT-005_RUN",
                step_id="S1",
                thread_id=create_result.thread_id,
                request={"resume": True},
                dry_run=True,
            )

            self.assertEqual(create_result.action, "create")
            self.assertEqual(create_result.status, "success")
            self.assertEqual(resume_result.action, "resume")
            self.assertEqual(resume_result.status, "success")
            self.assertEqual(resume_result.thread_id, create_result.thread_id)

    def test_every_call_writes_request_output_and_error_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = DispatchArtifactStore(root / "artifacts")
            adapter = ShimDispatchAdapter(
                shim_path="/usr/local/bin/daokit-shim",
                artifact_store=store,
            )

            result = adapter.create(
                task_id="DKT-005",
                run_id="DKT-005_RUN",
                step_id="S1",
                request={"step_title": "Implement shim dispatch adapter"},
                dry_run=True,
            )

            self.assertTrue(result.artifacts.request_path.is_file())
            self.assertTrue(result.artifacts.output_path.is_file())
            self.assertTrue(result.artifacts.error_path.is_file())

            request_doc = json.loads(result.artifacts.request_path.read_text(encoding="utf-8"))
            output_doc = json.loads(result.artifacts.output_path.read_text(encoding="utf-8"))
            error_doc = json.loads(result.artifacts.error_path.read_text(encoding="utf-8"))

            self.assertEqual(request_doc["action"], "create")
            self.assertIn("--dry-run", request_doc["command"])
            self.assertIn("correlation_id", request_doc)
            self.assertIn("raw_stdout", output_doc)
            self.assertIn("parsed_output", output_doc)
            self.assertIn("correlation_id", output_doc)
            self.assertIn("normalized_output_paths", output_doc)
            self.assertEqual(error_doc["error"], None)
            self.assertIn("correlation_id", error_doc)
            self.assertIn("raw_stderr", error_doc)

    def test_thread_and_run_correlation_stable_across_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = DispatchArtifactStore(root / "artifacts")
            adapter = ShimDispatchAdapter(
                shim_path="/usr/local/bin/daokit-shim",
                artifact_store=store,
            )

            first = adapter.create(
                task_id="DKT-005",
                run_id="DKT-005_RUN",
                step_id="S1",
                request={"attempt": 1},
                retry_index=0,
                dry_run=True,
            )
            second = adapter.create(
                task_id="DKT-005",
                run_id="DKT-005_RUN",
                step_id="S1",
                request={"attempt": 2},
                retry_index=1,
                dry_run=True,
            )
            resumed = adapter.resume(
                task_id="DKT-005",
                run_id="DKT-005_RUN",
                step_id="S1",
                request={"retry": "resume"},
                retry_index=2,
                dry_run=True,
            )

            self.assertEqual(first.thread_id, second.thread_id)
            self.assertEqual(first.thread_id, resumed.thread_id)
            self.assertEqual(first.correlation_id, second.correlation_id)
            self.assertEqual(first.correlation_id, resumed.correlation_id)
            self.assertEqual(first.run_id, second.run_id)
            self.assertEqual(second.run_id, resumed.run_id)

            first_request = json.loads(first.artifacts.request_path.read_text(encoding="utf-8"))
            resumed_request = json.loads(resumed.artifacts.request_path.read_text(encoding="utf-8"))
            self.assertEqual(first_request["correlation_id"], resumed_request["correlation_id"])


if __name__ == "__main__":
    unittest.main()
