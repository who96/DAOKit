from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class WorkspaceEscapeError(ValueError):
    """Raised when a path escapes the configured workspace root."""


@dataclass(frozen=True)
class Workspace:
    root: Path

    def resolve(self, relative_path: str) -> Path:
        resolved = (self.root / relative_path).resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise WorkspaceEscapeError(f"path escapes workspace: {relative_path}")
        return resolved

    def ensure_parent(self, resolved: Path) -> None:
        resolved.parent.mkdir(parents=True, exist_ok=True)


def create_dispatch_workspace(
    base_dir: str | Path,
    task_id: str,
    run_id: str,
    step_id: str,
) -> Workspace:
    root = Path(base_dir) / task_id / run_id / step_id / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return Workspace(root=root)
