# Session 4: Weekly selection and review job

Branch: `requests/weekly-review`. Worktree: `.worktrees/requests-weekly-review`.

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

Execute **Task 4** of the plan.

Calendar/DST cutoff and catch-up, frozen ranking, maximum 30 evaluations/ten candidates, durable job lease/checkpoint, pause/failure/resume behavior and additive Telegram readiness.

## Exclusive ownership

- `backend/app/community_weekly.py`
- `backend/app/jobs.py`
- `backend/app/models.py (JOB_KINDS and failedKinds capacity only)`
- `backend/app/telegram_worker.py (schema readiness only)`
- `backend/tests/test_community_weekly.py`
- `backend/tests/test_telegram.py (readiness regressions only)`
- `src/lib/model.ts (JOB_KINDS mirror only)`
- `docs/superpowers/completions/requests-weekly-review.md`

## Dependencies

Session 1 supplies rank_pending and mark_review_queued. Begin calendar/scheduler tests and use the frozen mocked seam for promotion unit tests. Lazy-import new persistence in promote_weekly. Do not create replacement modules, merge another lane or edit its migration. Full persistence tests run after integration.

## Finish

Follow the task's fail → implement → pass checks and commit. Write your completion report with branch, final commit, owned files, commands actually run, actual outcomes and remaining integration requirements. Stop after the commit; the integration session merges all lanes after they finish.
