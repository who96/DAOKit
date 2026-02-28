from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]
_src_dashboard = Path(__file__).resolve().parents[2] / "src" / "dashboard"
if _src_dashboard.is_dir():
    __path__.append(str(_src_dashboard))

__all__ = ["test_server"]
