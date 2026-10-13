# Session 1 — Telegram review core

Branch: `telegram/review-core`. Work only in its worktree, located in `docs/superpowers/completions/telegram-approvals-preparation.md`.

Read the Telegram spec/parallel plan dated 2026-10-12 and execute Task 1 using superpowers:executing-plans. Frozen signatures/ReviewView/options/actions in the plan are your downstream contract; do not rename them independently.

## Exclusive ownership

- New `backend/app/telegram_review.py`.
- New `backend/alembic/versions/0002_telegram_reviews.py`.
- `docs/superpowers/completions/telegram-review-core.md`.

Do not modify store/admin/models, baseline/helper migrations, config, bot/runtime modules, frontend or other lane reports. Existing store validation and transactions are the authority; directly inserting apps is forbidden. Missing shared functionality is a coordinator blocker.

## Deliverable

Two additive tables and one index, durable owner-bound/versioned drafts, explicit required selections, seven-day expiry/renewal, replay-safe approval/rejection through store functions, atomic review/audit/publication, and monotonic scoped polling offsets. No network/config dependence or import-time DB work. Snapshot option indices keep Telegram callback payloads bounded. All existing optional metadata and override semantics survive approval.

Follow the frozen 22-character token representation and decimal grammar, immutable assessment snapshot/ReviewView field, and compare-and-clear `reset_delivery` contract. Distinguish outdated button version from obsolete candidate revision; a button mismatch must not invalidate a current open review.

## Verification and finish

Use your own virtualenv if dependencies are needed; never copy root env/DB/token or share environments. Authorized checks are compilation, safe imports with DB connections blocked, offline DDL compilation and code review. No tests, migrations, DB connections, services, Telegram/GitHub calls or publication.

Write a completion report with commit, files, checks actually run, limits and shared blockers. Commit only owned files. Do not merge/deploy. When a later lane is absent, use the contract in the plan, not cross-lane edits.
