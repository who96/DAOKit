from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


CORE_ROTATION_MATRIX_VERSION = "dkt-051-core-rotation-v1"
CORE_ROTATION_HIGH_RISK_PATHS = frozenset({"rotation", "takeover", "stale_lease"})
CORE_ROTATION_CONTINUITY_ASSERTION_CATALOG: dict[str, str] = {
    "CONT-001": "Takeover timestamp is synchronized into succession state.",
    "CONT-002": "Handoff applies and preserves a deterministic resume step.",
    "CONT-003": "Replay output remains event-count consistent after recovery.",
    "CONT-004": "State JSON files remain parseable without manual repair.",
    "CONT-005": "Invalid lease path escalates to takeover.",
    "CONT-006": "Stale heartbeat escalation emits only one stale event.",
    "CONT-007": "Adopted/failed step sets match fixture expectations.",
    "CONT-008": "Lease ownership after takeover matches fixture expectations.",
    "CONT-009": "Takeover, handoff, and replay continuity stay mutually consistent.",
    "CONT-010": "Replay preserves persisted event ordering for deterministic recovery.",
    "CONT-011": "Replay stream remains schema_version=1.0.0 compatible.",
}


@dataclass(frozen=True)
class DeterministicExecutionConstraints:
    seed: str
    clock_anchor_utc: str
    check_interval_seconds: int = 60
    warning_after_seconds: int = 900
    stale_after_seconds: int = 1200
    second_tick_advance_seconds: int = 120
    replay_limit: int = 500

    def resolved_clock_anchor(self) -> datetime:
        anchor = datetime.fromisoformat(self.clock_anchor_utc)
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        return anchor.astimezone(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "clock_anchor_utc": self.resolved_clock_anchor().isoformat(),
            "check_interval_seconds": self.check_interval_seconds,
            "warning_after_seconds": self.warning_after_seconds,
            "stale_after_seconds": self.stale_after_seconds,
            "second_tick_advance_seconds": self.second_tick_advance_seconds,
            "replay_limit": self.replay_limit,
        }


@dataclass(frozen=True)
class CoreRotationChaosScenarioFixture:
    scenario_id: str
    title: str
    description: str
    risk_tags: tuple[str, ...]
    continuity_assertions: tuple[str, ...]
    heartbeat_silence_seconds: int
    controller_lease_ttl_seconds: int
    lease_expiry_advance_seconds: int = 0
    include_accepted_steps_in_handoff: bool = False
    expected_takeover_action: str = "TAKEOVER"
    expected_heartbeat_status: str = "STALE"
    expected_handoff_applied: bool = True
    expected_adopted_step_ids: tuple[str, ...] = ("S1",)
    expected_failed_step_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "description": self.description,
            "risk_tags": list(self.risk_tags),
            "continuity_assertions": list(self.continuity_assertions),
            "heartbeat_silence_seconds": self.heartbeat_silence_seconds,
            "controller_lease_ttl_seconds": self.controller_lease_ttl_seconds,
            "lease_expiry_advance_seconds": self.lease_expiry_advance_seconds,
            "include_accepted_steps_in_handoff": self.include_accepted_steps_in_handoff,
            "expected_takeover_action": self.expected_takeover_action,
            "expected_heartbeat_status": self.expected_heartbeat_status,
            "expected_handoff_applied": self.expected_handoff_applied,
            "expected_adopted_step_ids": list(self.expected_adopted_step_ids),
            "expected_failed_step_ids": list(self.expected_failed_step_ids),
        }


DEFAULT_DETERMINISTIC_CONSTRAINTS = DeterministicExecutionConstraints(
    seed="DKT-051-core-rotation-chaos-matrix",
    clock_anchor_utc="2026-02-12T09:46:00+00:00",
)

_CORE_ROTATION_SCENARIO_MATRIX: tuple[CoreRotationChaosScenarioFixture, ...] = (
    CoreRotationChaosScenarioFixture(
        scenario_id="stale-takeover-handoff-resume",
        title="Forced stale + takeover + handoff resume",
        description=(
            "Heartbeat crosses stale threshold while controller lease is still active, "
            "then successor takeover and handoff resume execute in the same recovery cycle."
        ),
        risk_tags=("rotation", "takeover"),
        continuity_assertions=(
            "CONT-001",
            "CONT-002",
            "CONT-003",
            "CONT-004",
            "CONT-006",
            "CONT-007",
            "CONT-008",
            "CONT-009",
            "CONT-010",
            "CONT-011",
        ),
        heartbeat_silence_seconds=2 * 3600 + 5 * 60,
        controller_lease_ttl_seconds=1200,
    ),
    CoreRotationChaosScenarioFixture(
        scenario_id="warning-invalid-lease-forced-takeover",
        title="Warning heartbeat + invalid stale lease takeover",
        description=(
            "Heartbeat remains WARNING, but expired controller lease forces takeover to "
            "exercise stale lease edge behavior under partial signal quality."
        ),
        risk_tags=("takeover", "stale_lease"),
        continuity_assertions=(
            "CONT-001",
            "CONT-002",
            "CONT-003",
            "CONT-004",
            "CONT-005",
            "CONT-007",
            "CONT-008",
            "CONT-009",
            "CONT-010",
            "CONT-011",
        ),
        heartbeat_silence_seconds=901,
        controller_lease_ttl_seconds=120,
        lease_expiry_advance_seconds=180,
        expected_heartbeat_status="WARNING",
        expected_adopted_step_ids=(),
        expected_failed_step_ids=("S1",),
    ),
    CoreRotationChaosScenarioFixture(
        scenario_id="stale-invalid-lease-core-rotation",
        title="Forced stale + expired lease takeover",
        description=(
            "Heartbeat and lease signals are both unhealthy (STALE + expired lease) "
            "to stress the highest-risk takeover path."
        ),
        risk_tags=("rotation", "takeover", "stale_lease"),
        continuity_assertions=(
            "CONT-001",
            "CONT-002",
            "CONT-003",
            "CONT-004",
            "CONT-006",
            "CONT-007",
            "CONT-008",
            "CONT-009",
            "CONT-010",
            "CONT-011",
        ),
        heartbeat_silence_seconds=1700,
        controller_lease_ttl_seconds=120,
        lease_expiry_advance_seconds=180,
        expected_adopted_step_ids=(),
        expected_failed_step_ids=("S1",),
    ),
    CoreRotationChaosScenarioFixture(
        scenario_id="stale-active-lease-dedup-escalation",
        title="Forced stale deduplicated escalation",
        description=(
            "Stale heartbeat is re-checked with deterministic clock progression to prove "
            "deduplicated stale signaling while maintaining takeover continuity."
        ),
        risk_tags=("rotation", "takeover"),
        continuity_assertions=(
            "CONT-001",
            "CONT-002",
            "CONT-003",
            "CONT-004",
            "CONT-006",
            "CONT-007",
            "CONT-008",
            "CONT-009",
            "CONT-010",
            "CONT-011",
        ),
        heartbeat_silence_seconds=2 * 3600 + 30,
        controller_lease_ttl_seconds=900,
        include_accepted_steps_in_handoff=True,
    ),
)


def list_core_rotation_chaos_scenarios() -> tuple[CoreRotationChaosScenarioFixture, ...]:
    return _CORE_ROTATION_SCENARIO_MATRIX


def get_default_core_rotation_chaos_scenario() -> CoreRotationChaosScenarioFixture:
    return _CORE_ROTATION_SCENARIO_MATRIX[0]


def get_core_rotation_chaos_scenario(scenario_id: str) -> CoreRotationChaosScenarioFixture:
    normalized = scenario_id.strip()
    for fixture in _CORE_ROTATION_SCENARIO_MATRIX:
        if fixture.scenario_id == normalized:
            return fixture
    known_ids = ", ".join(fixture.scenario_id for fixture in _CORE_ROTATION_SCENARIO_MATRIX)
    raise ValueError(f"unknown scenario id: {scenario_id!r}; expected one of: {known_ids}")


def summarize_core_rotation_chaos_matrix() -> dict[str, Any]:
    fixtures = list_core_rotation_chaos_scenarios()
    covered_paths = sorted({path for fixture in fixtures for path in fixture.risk_tags})
    missing_paths = sorted(path for path in CORE_ROTATION_HIGH_RISK_PATHS if path not in covered_paths)
    assertion_ids = sorted({assertion for fixture in fixtures for assertion in fixture.continuity_assertions})
    unknown_assertions = sorted(
        assertion for assertion in assertion_ids if assertion not in CORE_ROTATION_CONTINUITY_ASSERTION_CATALOG
    )
    return {
        "matrix_version": CORE_ROTATION_MATRIX_VERSION,
        "scenario_ids": [fixture.scenario_id for fixture in fixtures],
        "scenario_count": len(fixtures),
        "high_risk_paths_required": sorted(CORE_ROTATION_HIGH_RISK_PATHS),
        "high_risk_paths_covered": covered_paths,
        "missing_high_risk_paths": missing_paths,
        "assertion_catalog_ids": sorted(CORE_ROTATION_CONTINUITY_ASSERTION_CATALOG),
        "assertion_ids_in_matrix": assertion_ids,
        "unknown_assertion_ids": unknown_assertions,
        "checks": {
            "high_risk_paths_covered": len(missing_paths) == 0,
            "assertion_mapping_complete": len(unknown_assertions) == 0
            and all(len(fixture.continuity_assertions) > 0 for fixture in fixtures),
        },
    }
