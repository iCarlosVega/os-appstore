# Weekly app requests — worktree preparation

Prepared 2026-10-12. No feature implementation or release performed.

## Artifacts

- Spec: `docs/superpowers/specs/2026-10-12-weekly-app-requests-design.md`
- Plan: `docs/superpowers/plans/2026-10-12-weekly-app-requests.md`
- Four worker handoffs plus integration handoff: `docs/superpowers/handoffs/requests-*.md`
- Copyable launch commands: `docs/superpowers/handoffs/requests-sessions.md`

## Baseline

Original checkout remains on develop at c6985896426011e6a8534f8b439371e41e1a3c61 with its original unstaged edits and untracked Telegram completion report preserved. A temporary Git index created isolated snapshot 061206cb84a59399617bb4b785e7d468edf49229 containing current tracked changes plus that report. No original index change, stash, reset, shared DB migration, service restart or live message was used.

All five feature branches start from the same snapshot plus reviewed planning documentation. Paths are under the requested project-local `.worktrees/` directory, verified Git-ignored. Existing older worktrees were preserved.

## Setup and checks

Each worktree has its own node_modules (npm ci) and backend/.venv with backend/requirements.txt installed. No env files or credentials were copied.

- Root snapshot baseline: 62 backend tests passed.
- requests/data-api: 62 backend tests passed in its installed environment.
- requests/github-search: 62 backend tests passed in its installed environment.
- requests/weekly-review: 62 backend tests passed in its installed environment.
- requests/integration: 62 backend tests and npm run typecheck passed.
- requests/ui: npm run typecheck passed.
- Tests used their existing disposable PostgreSQL/SQLite guards and mocked transports.
- Plan link/ownership/placeholder self-review completed; corrected the Dashboard owner path, frontend job-kind mirror, numeric repository identity constraint and retry cutoff contract.

## Next action

Start Sessions 1–4 in separate terminal tabs using requests-sessions.md. Start Session 5 only when all four have committed their completion reports. Implementers own their file boundaries; the integrator merges data-api → github-search → ui → weekly-review, then verifies the real combined flow.

Default selection time is Monday 00:05 in settings.timezone (currently America/New_York), using a Monday 00:00 cutoff and cumulative pending suggestions. Browser identifiers approximate distinct visitors; there is no verified-human vote guarantee. Publication still requires owner Accept.
