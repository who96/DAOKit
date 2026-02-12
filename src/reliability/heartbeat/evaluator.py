from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


class HeartbeatEvaluatorError(ValueError):
    """Raised when heartbeat evaluation input is invalid."""


@dataclass(frozen=True)
class HeartbeatThresholds:
    check_interval_seconds: int
    warning_after_seconds: int
    stale_after_seconds: int

    def __post_init__(self) -> None:
        for name in ("check_interval_seconds", "warning_after_seconds", "stale_after_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise HeartbeatEvaluatorError(f"{name} must be a positive integer")

        if self.warning_after_seconds < self.check_interval_seconds:
            raise HeartbeatEvaluatorError(
                "warning_after_seconds must be >= check_interval_seconds"
            )
        if self.stale_after_seconds < self.warning_after_seconds:
            raise HeartbeatEvaluatorError(
                "stale_after_seconds must be >= warning_after_seconds"
            )


@dataclass(frozen=True)
class HeartbeatEvaluation:
    status: str
    reason_code: str | None
    silence_seconds: int
    effective_signal_at: datetime | None


def evaluate_heartbeat(
    *,
    now: datetime,
    execution_active: bool,
    thresholds: HeartbeatThresholds,
    explicit_heartbeat_at: datetime | None,
    implicit_output_at: datetime | None,
) -> HeartbeatEvaluation:
    current_time = _normalize_datetime(now, name="now")
    explicit = _normalize_optional_datetime(explicit_heartbeat_at, name="explicit_heartbeat_at")
    implicit = _normalize_optional_datetime(implicit_output_at, name="implicit_output_at")

    if not execution_active:
        return HeartbeatEvaluation(
            status="IDLE",
            reason_code=None,
            silence_seconds=0,
            effective_signal_at=None,
        )

    effective_signal_at = _latest_signal(explicit, implicit)
    if effective_signal_at is None:
        silence_seconds = thresholds.stale_after_seconds
    else:
        silence_seconds = max(int((current_time - effective_signal_at).total_seconds()), 0)

    if silence_seconds >= thresholds.stale_after_seconds:
        return HeartbeatEvaluation(
            status="STALE",
            reason_code=silence_reason_code(thresholds.stale_after_seconds),
            silence_seconds=silence_seconds,
            effective_signal_at=effective_signal_at,
        )

    if silence_seconds >= thresholds.warning_after_seconds:
        return HeartbeatEvaluation(
            status="WARNING",
            reason_code=silence_reason_code(thresholds.warning_after_seconds),
            silence_seconds=silence_seconds,
            effective_signal_at=effective_signal_at,
        )

    return HeartbeatEvaluation(
        status="ACTIVE",
        reason_code=None,
        silence_seconds=silence_seconds,
        effective_signal_at=effective_signal_at,
    )


def silence_reason_code(threshold_seconds: int) -> str:
    if threshold_seconds % 3600 == 0:
        return f"NO_OUTPUT_{threshold_seconds // 3600}H"
    if threshold_seconds % 60 == 0:
        return f"NO_OUTPUT_{threshold_seconds // 60}M"
    return f"NO_OUTPUT_{threshold_seconds}S"


def _latest_signal(*signals: datetime | None) -> datetime | None:
    known = [signal for signal in signals if signal is not None]
    if not known:
        return None
    return max(known)


def _normalize_optional_datetime(value: datetime | None, *, name: str) -> datetime | None:
    if value is None:
        return None
    return _normalize_datetime(value, name=name)


def _normalize_datetime(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise HeartbeatEvaluatorError(f"{name} must be datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
