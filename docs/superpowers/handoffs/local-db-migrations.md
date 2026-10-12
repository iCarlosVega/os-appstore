# Session 1 — Alembic migrations

Branch: `local-db/migrations`. Resolve your worktree and common baseline from the coordinator's preparation report; do not work in the root checkout.

Read the local-database spec and parallel plan dated 2026-10-12, then execute Task 1 with superpowers:executing-plans. The plan's global constraints, frozen interfaces and verification policy apply.

## Exclusive ownership

- `backend/app/db.py`
- New `backend/app/schema.py`
- `backend/requirements.txt`
- `backend/Dockerfile`
- New `backend/alembic.ini`, `backend/alembic/**`
- `docs/superpowers/completions/local-db-migrations.md`

Keep `store.py`, `cli.py`, config, root SQL schema, runtime/import modules and all frontend files unchanged. Report a demonstrated shared change to the coordinator instead of editing another lane.

## Deliverable

`db.migrate()` delegates to `schema.upgrade_schema() -> None`. Safely create or adopt baseline `0001_initial` on PostgreSQL and SQLite; reject incompatible/partial/unknown schemas. Use SQLAlchemy only for migrations/reflection, retaining existing app adapters and one migration connection/lock. Preserve all legacy rows, constraints and JSON payloads. Pin dependencies and package all resources in Docker. Do not connect to or stamp any existing development or production database during lane work.

## Start and finish

1. Verify your branch, clean baseline and exclusive ownership. Create your own `backend/.venv`; install this lane's pinned requirements there. Do not share the root venv or copy `.env`/`.data`.
2. Inspect initialization callers before editing. Pay special attention to SQLite auto-migration versus explicit PostgreSQL migration, password interpolation and the existing advisory lock.
3. Implement Task 1 and run only authorized syntax/safe-import/code-review gates. Do not add/run application tests, initialize databases, start workers or use paid integrations.
4. Commit owned files and completion note, listing exact checks, unverified behavioral cases and shared blockers. Do not merge, deploy or delete worktrees.
