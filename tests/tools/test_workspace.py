from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.workspace import Workspace, WorkspaceEscapeError, create_dispatch_workspace


class WorkspaceTests(unittest.TestCase):
    def test_resolve_normal_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(root=Path(tmp))

            resolved = workspace.resolve("nested/file.txt")

            self.assertEqual(resolved, (Path(tmp) / "nested" / "file.txt").resolve())

    def test_resolve_escape_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(root=Path(tmp))

            with self.assertRaises(WorkspaceEscapeError):
                workspace.resolve("../outside.txt")

    def test_ensure_parent_creates_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(root=Path(tmp))
            resolved = workspace.resolve("a/b/c/data.txt")

            workspace.ensure_parent(resolved)

            self.assertTrue((Path(tmp) / "a" / "b" / "c").is_dir())

    def test_create_dispatch_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = create_dispatch_workspace(
                base_dir=Path(tmp),
                task_id="DKT-001",
                run_id="RUN-1",
                step_id="S1",
            )

            expected = Path(tmp) / "DKT-001" / "RUN-1" / "S1" / "workspace"
            self.assertEqual(workspace.root, expected)
            self.assertTrue(workspace.root.is_dir())


if __name__ == "__main__":
    unittest.main()
