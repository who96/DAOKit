# DKT-052 Continuity Assertion Soak Report

- Task ID: DKT-052
- Iterations: 3
- Scenario IDs: stale-takeover-handoff-resume, warning-invalid-lease-forced-takeover, stale-invalid-lease-core-rotation, stale-active-lease-dedup-escalation
- Matrix Version: dkt-051-core-rotation-v1
- Release Gate Status: PASS

## Gate Checks
- continuity_assertions_all_passed: True
- takeover_handoff_replay_consistent: True
- deterministic_checkpoint_hashes: True
- bounded_variance: True

## Deterministic Checkpoint Hashes
- stale-takeover-handoff-resume: 1f0470a0ff89d1524691600df6e6abc1bd8b1da588547dd43a1fafe927cf80f7
- warning-invalid-lease-forced-takeover: 9804b9b4a36bdb90b6eaa83cdbd751514b38f6d3aa6170142a409c84131c39df
- stale-invalid-lease-core-rotation: a8277594922d4c3105fad48d3c62245f569b9bc6eeca9a01663f13df4716d729
- stale-active-lease-dedup-escalation: 89c53bf8e7606daa8824cb2f7cdb9802258743e5f32fb4b36f6e463fd4e7f871

## Variance
- stale-takeover-handoff-resume: event_count_range=0 replay_count_range=0
- warning-invalid-lease-forced-takeover: event_count_range=0 replay_count_range=0
- stale-invalid-lease-core-rotation: event_count_range=0 replay_count_range=0
- stale-active-lease-dedup-escalation: event_count_range=0 replay_count_range=0
