from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from state.store import create_state_backend

_DEFAULT_EVENTS_LIMIT = 50
_DEFAULT_SNAPSHOTS_LIMIT = 20


def _load_project_env(state_root: Path) -> None:
    """Load .env from state_root ancestors so subprocess inherits LLM config."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for parent in (state_root, *state_root.resolve().parents):
        candidate = parent / ".env"
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return


def create_app(state_root: Path) -> FastAPI:
    _load_project_env(state_root)
    backend = create_state_backend(state_root)
    app = FastAPI(title="DAOKit Dashboard", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
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

    @app.get("/api/sessions", response_model=None)
    def get_sessions() -> Any:
        try:
            return backend.list_sessions()
        except Exception as exc:  # pragma: no cover - boundary guard
            return _error_response(exc)

    @app.get("/api/events", response_model=None)
    def get_events(
        limit: int = _DEFAULT_EVENTS_LIMIT,
        task_id: str | None = None,
    ) -> Any:
        try:
            if task_id:
                return backend.list_events_by_task(task_id, limit=max(limit, 1))
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

    @app.post("/api/message", response_model=None)
    async def post_message(request: Request) -> Any:
        try:
            body = await request.json()
            message = body.get("message", "").strip()
            if not message:
                return JSONResponse({"error": "message is required"}, status_code=400)
            state = backend.load_state()
            explicit_task_id = body.get("task_id")
            event = backend.append_event(
                task_id=str(explicit_task_id or state.get("task_id") or "unknown"),
                run_id=str(state.get("run_id") or "unknown"),
                step_id=body.get("step_id"),
                event_type="HUMAN",
                severity="INFO",
                payload={"message": message, "sender": "human"},
            )
            return event
        except Exception as exc:
            return _error_response(exc)

    @app.post("/api/run", response_model=None)
    async def post_run(request: Request) -> Any:
        try:
            body = await request.json()
            goal = body.get("goal", "").strip()
            if not goal:
                return JSONResponse({"error": "goal is required"}, status_code=400)
            task_id = body.get("task_id") or f"DKT-DASH-{int(time.time())}"
            root = state_root.parent
            subprocess.Popen(
                [
                    sys.executable, "-m", "cli", "run",
                    "--root", str(root),
                    "--task-id", task_id,
                    "--goal", goal,
                    "--no-lease",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"task_id": task_id, "status": "started"}
        except Exception as exc:
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
