from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from state.store import StateStore

from .evaluator import HeartbeatEvaluation, HeartbeatThresholds, evaluate_heartbeat


@dataclass(frozen=True)
class HeartbeatTickResult:
    status: str
    reason_code: str | None
    silence_seconds: int
    stale_event_emitted: bool


class HeartbeatDaemon:
    """Periodic heartbeat checker using explicit beats and artifact output mtimes."""

    def __init__(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        state_store: StateStore,
        artifact_root: str | Path,
        thresholds: HeartbeatThresholds,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self.step_id = step_id
        self.state_store = state_store
        self.artifact_root = Path(artifact_root)
        self.thresholds = thresholds
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

        # Ensure heartbeat status storage exists before the first tick.
        self.state_store.load_heartbeat_status()

    def record_explicit_heartbeat(self, at: datetime | None = None) -> dict[str, object]:
        beat_at = _normalize_datetime(at or self._now_provider())
        current = self.state_store.load_heartbeat_status()
        payload = {
            "schema_version": "1.0.0",
            "status": "RUNNING",
            "last_heartbeat_at": beat_at.isoformat(),
            "reason_code": None,
            "warning_after_seconds": self.thresholds.warning_after_seconds,
            "stale_after_seconds": self.thresholds.stale_after_seconds,
            "last_escalation_at": current.get("last_escalation_at"),
        }
        return self.state_store.save_heartbeat_status(payload)

    def tick(self) -> HeartbeatTickResult:
        now = _normalize_datetime(self._now_provider())
        current = self.state_store.load_heartbeat_status()
        explicit = _parse_optional_datetime(current.get("last_heartbeat_at"))
        implicit = latest_artifact_mtime(self.artifact_root)

        evaluation = evaluate_heartbeat(
            now=now,
            execution_active=True,
            thresholds=self.thresholds,
            explicit_heartbeat_at=explicit,
            implicit_output_at=implicit,
        )
        persisted_status = _to_persisted_status(evaluation.status)

        stale_event = None
        stale_dedup_key = None
        if persisted_status == "STALE" and current.get("status") != "STALE":
            stale_dedup_key = self._stale_dedup_key(evaluation)
            stale_event = self.state_store.append_event(
                task_id=self.task_id,
                run_id=self.run_id,
                step_id=self.step_id,
                event_type="HEARTBEAT_STALE",
                severity="WARN",
                payload={
                    "reason_code": evaluation.reason_code,
                    "silence_seconds": evaluation.silence_seconds,
                    "stale_after_seconds": self.thresholds.stale_after_seconds,
                    "effective_signal_at": _format_optional_datetime(
                        evaluation.effective_signal_at
                    ),
                },
                dedup_key=stale_dedup_key,
            )

        self.state_store.save_heartbeat_status(
            {
                "schema_version": "1.0.0",
                "status": persisted_status,
                "last_heartbeat_at": _format_optional_datetime(
                    evaluation.effective_signal_at
                ),
                "reason_code": evaluation.reason_code,
                "warning_after_seconds": self.thresholds.warning_after_seconds,
                "stale_after_seconds": self.thresholds.stale_after_seconds,
                "last_escalation_at": (
                    stale_event["timestamp"]
                    if stale_event is not None
                    else current.get("last_escalation_at")
                ),
            }
        )

        return HeartbeatTickResult(
            status=evaluation.status,
            reason_code=evaluation.reason_code,
            silence_seconds=evaluation.silence_seconds,
            stale_event_emitted=stale_event is not None,
        )

    def _stale_dedup_key(self, evaluation: HeartbeatEvaluation) -> str:
        signal_component = _format_optional_datetime(evaluation.effective_signal_at) or "none"
        reason = evaluation.reason_code or "UNKNOWN"
        return (
            f"heartbeat-stale:{self.task_id}:{self.run_id}:{self.step_id}:"
            f"{reason}:{signal_component}"
        )


def latest_artifact_mtime(artifact_root: str | Path) -> datetime | None:
    root = Path(artifact_root)
    if not root.exists():
        return None

    latest: float | None = None
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        stat = candidate.stat()
        if latest is None or stat.st_mtime > latest:
            latest = stat.st_mtime

    if latest is None:
        return None
    return datetime.fromtimestamp(latest, tz=timezone.utc)


def _to_persisted_status(status: str) -> str:
    mapping = {
        "IDLE": "IDLE",
        "ACTIVE": "RUNNING",
        "WARNING": "WARNING",
        "STALE": "STALE",
    }
    try:
        return mapping[status]
    except KeyError as exc:
        raise ValueError(f"unknown heartbeat status '{status}'") from exc


def _parse_optional_datetime(raw: object) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("expected heartbeat timestamp as ISO datetime string")
    parsed = datetime.fromisoformat(raw)
    return _normalize_datetime(parsed)


def _format_optional_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _normalize_datetime(value).isoformat()


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
