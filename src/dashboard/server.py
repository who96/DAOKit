from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from state.store import create_state_backend

_DEFAULT_EVENTS_LIMIT = 50
_DEFAULT_SNAPSHOTS_LIMIT = 20


def create_app(state_root: Path) -> FastAPI:
    backend = create_state_backend(state_root)
    app = FastAPI(title="DAOKit Dashboard", version="0.1.0")
    static_root = Path(__file__).parent / "static"

    @app.get("/api/state", response_model=None)
    def get_state() -> Any:
        try:
            return backend.load_state()
        except Exception as exc:  # pragma: no cover - boundary guard
            return _error_response(exc)

    @app.get("/api/heartbeat", response_model=None)
    def get_heartbeat() -> Any:
        try:
            return backend.load_heartbeat_status()
        except Exception as exc:  # pragma: no cover - boundary guard
            return _error_response(exc)

    @app.get("/api/leases", response_model=None)
    def get_leases() -> Any:
        try:
            return backend.load_leases()
        except Exception as exc:  # pragma: no cover - boundary guard
            return _error_response(exc)

    @app.get("/api/events", response_model=None)
    def get_events(limit: int = _DEFAULT_EVENTS_LIMIT) -> Any:
        try:
            return _read_events_tail(backend.events_path, limit=max(limit, 1))
        except Exception as exc:  # pragma: no cover - boundary guard
            return _error_response(exc)

    @app.get("/api/snapshots", response_model=None)
    def get_snapshots(limit: int = _DEFAULT_SNAPSHOTS_LIMIT) -> Any:
        try:
            snapshots = backend.list_snapshots()
            normalized_limit = max(limit, 1)
            return snapshots[-normalized_limit:]
        except Exception as exc:  # pragma: no cover - boundary guard
            return _error_response(exc)

    @app.get("/", response_model=None)
    def get_index() -> Any:
        try:
            index_path = static_root / "index.html"
            return FileResponse(index_path)
        except Exception as exc:  # pragma: no cover - boundary guard
            return _error_response(exc)

    return app


def _read_events_tail(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []

    entries: list[dict[str, Any]] = []
    for raw_line in reversed(lines):
        stripped = raw_line.strip()
        if not stripped:
            continue
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError("events entry must be a JSON object")
        entries.append(parsed)
        if len(entries) >= limit:
            break
    entries.sort(key=_event_sort_key, reverse=True)
    return entries


def _event_sort_key(event: dict[str, Any]) -> str:
    timestamp = event.get("timestamp")
    if isinstance(timestamp, str):
        return timestamp
    return ""


def _error_response(exc: Exception) -> JSONResponse:
    return JSONResponse(
        content={"error": str(exc)},
        status_code=500,
    )
