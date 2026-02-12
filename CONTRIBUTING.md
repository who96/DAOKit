# Contributing to DAOKit

Thanks for contributing to DAOKit.
This project is optimized for strict, auditable agent workflow engineering. Keep contributions deterministic, testable, and scoped.

## Development Setup

1. Clone and enter the repository.
2. Use Python 3.11+.
3. Run baseline checks before opening a pull request.

```bash
make lint
make test
```

## Branch and Commit Discipline

- Keep changes focused on one concern.
- Use clear commit messages with the affected area (`cli`, `orchestrator`, `tools`, `docs`, `examples`).
- Never mix refactors with behavior changes unless the refactor is required for the behavior change.

## Pull Request Checklist

- Include problem statement and expected behavior.
- Include verification commands and outcomes.
- Include updated docs/examples if user-facing behavior changes.
- Keep acceptance evidence explicit (`report.md`, `verification.log`, `audit-summary.md`) for orchestration tasks.

## Extension Contributions

DAOKit supports four extension paths. Follow `docs/extensions.md` for detailed examples.

- Function-calling tools: `src/tools/function_calling/`
- MCP tools: `src/tools/mcp/`
- Skills: `src/skills/`
- Lifecycle hooks: `src/hooks/`

For any extension PR:

1. Add or update tests in `tests/`.
2. Document usage and contract assumptions.
3. Keep backward compatibility for existing CLI and state contracts.

## Documentation Expectations

When adding features or changing behavior, update relevant docs in the same PR:

- `README.md` for top-level usage
- `docs/` for operational details
- `CHANGELOG.md` for release-visible changes

## Code Review Criteria

Reviewers will reject changes that:

- Break deterministic state transitions
- Skip auditability/logging for tool execution
- Introduce out-of-scope side effects in orchestration flows
- Remove compatibility without a versioned migration strategy
