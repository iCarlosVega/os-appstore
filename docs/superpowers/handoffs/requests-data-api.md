# Session 1: Request persistence and submission API

Branch: `requests/data-api`. Worktree: `.worktrees/requests-data-api`.

## Required context

Read `AGENTS.md`, `docs/superpowers/specs/2026-10-12-weekly-app-requests-design.md`, then `docs/superpowers/plans/2026-10-12-weekly-app-requests.md`. The user chose separate Codex sessions in these existing worktrees. Implement only your assigned task using superpowers:executing-plans; the approved feature is GitHub suggestions with a weekly top-ten review batch. Do not restart brainstorming or implement the other lanes.

## Shared rules

- Work only on your named branch in your named worktree. Do not create another worktree.
- All sessions share one machine. Never copy root env files/tokens or connect to its current local/production DB. Never run the shared local launchers, migrate DB 55432, start a live Telegram poller or send recommendations.
- Your worktree has its own backend/.venv and node_modules. Tests use temporary SQLite/disposable PostgreSQL, synthetic secrets and mocked provider HTTP. Tests restore environment/connection/socket guards.
- Use the frozen interfaces. Missing cross-lane files are declared dependencies, not permission to invent production stubs or rename contracts. Report a shared blocker in your completion file.
- Preserve all existing candidate decisions and four-button Telegram behavior. No automatic publication, AI calls, deployment or push.
- Commit only owned files. Do not merge another branch or modify another lane's report.

## Your task

Execute **Task 1** of the plan.

Migration 0003, anonymous signed identity, atomic contribution counts, rank_pending/repository_status/mark_review_queued, POST /api/requests and aggregate admin data.

## Exclusive ownership

- `backend/alembic/versions/0003_community_requests.py`
- `backend/app/community_requests.py`
- `backend/app/request_identity.py`
- `backend/app/main.py (submission handler only)`
- `backend/app/admin.py (dashboard field only)`
- `backend/tests/test_community_requests.py`
- `docs/superpowers/completions/requests-data-api.md`

## Dependencies

No dependency on another new lane. Fetch verification through existing github.fetch_repository. Do not register the new search router; integration owns that.

## Finish

Follow the task's fail → implement → pass checks and commit. Write your completion report with branch, final commit, owned files, commands actually run, actual outcomes and remaining integration requirements. Stop after the commit; the integration session merges all lanes after they finish.
