# Security Policy

## Supported Versions

| Version Line | Status |
| --- | --- |
| `v1.0.x` | Supported |
| `main` | Supported (best effort) |
| `< v1.0.0` | Not Supported |

## Reporting a Vulnerability

If you discover a security issue, do not open a public issue first.

Send a private report with the following fields:

- Affected component/file
- Impact and attack preconditions
- Reproduction steps
- Suggested mitigation (optional)

Contact channel: project maintainers security mailbox (configure in repository settings before public release).

## Disclosure Process

1. Maintainers acknowledge receipt within 3 business days.
2. Maintainers triage severity and identify impacted versions.
3. Fix is prepared with regression tests.
4. Patch release is published with security notes in `CHANGELOG.md`.
5. Public disclosure follows once fixes are available.

## Scope Notes

Primary security boundaries for DAOKit:

- Command allowlisting and input validation in tool adapters
- State and event log integrity under interruption/recovery
- Protection against unsafe skill/hook loading and execution drift

Out of scope for bounty-style claims unless explicitly enabled by maintainers:

- Local-only developer environment misconfiguration
- Findings without reproducible impact path
