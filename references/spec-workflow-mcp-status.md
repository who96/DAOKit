# spec-workflow MCP Availability Note

## Context
This planning batch requested `spec-workflow` MCP usage.

## Runtime Check Result
- MCP resources listing returned empty.
- MCP resource templates listing returned empty.
- No callable `spec-workflow` server/template was discoverable in this session.

## Equivalent Fallback Applied
To keep execution unblocked, DAOKit planning files were generated in equivalent spec-workflow structure:
- `requirements`: `/Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/requirements.md`
- `design`: `/Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/design.md`
- `tasks`: `/Users/huluobo/workSpace/DAOKit/specs/001-daokit-agent-platform/tasks.md`

## Compatibility
The generated tasks are already normalized for orchestrator execution:
- Goal
- Concrete Actions
- Acceptance Criteria
- Deliverables
- Dependencies

This means the current package can be executed directly by zhukong-style controller workflows even without MCP server availability.

