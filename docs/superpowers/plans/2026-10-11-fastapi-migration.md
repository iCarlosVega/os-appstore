# FastAPI backend correction

The owner explicitly requires FastAPI. Keep the existing Next.js UI and move backend ownership into `backend/app/` without further approval gates.

## Contract

- FastAPI owns persistence, GitHub OAuth, owner authorization, approvals, downloads/requests, search, provider calls, cost guards, and worker jobs.
- Next.js renders the existing UI and forwards `/api/*` requests to FastAPI. It must not access the database or provider secrets.
- Preserve the existing SQLite/PostgreSQL schema and camelCase JSON records; no data deletion or destructive migration.
- Keep the existing candidate revision guards, manual overrides, rejected IDs, cost reservations, and interrupted-run checkpoints.
- Fix the reported empty donation URL validator exception. Empty optional URLs must not throw during validation.
- Provide local two-service commands and Vercel frontend/Railway FastAPI + worker deployment and Compose.
- No application tests unless requested, per session instructions; use Python syntax/import checks and TypeScript/build compilation, and explicitly report live integration limits.

## Steps

- [x] Fix shared URL validation.
- [x] Add Python settings/models and compatible SQLite/PostgreSQL persistence.
- [x] Port search, budget/provider adapters, catalog administration, authentication, discovery, maintenance, backups, and durable jobs.
- [x] Replace Next.js backend implementation with an HTTP client and same-origin proxy; retain the UI.
- [x] Update dependencies, environment examples, containers, and documentation.
- [x] Compile, review once, fix material findings, and report actual validation results.

## Review and validation

One independent read-only review found two important issues and one minor issue. Fixed all three: resolve relative database/backup paths against the repository root, strictly validate Jev provider responses before releasing cost reservations, and load root `.env` before constructing launcher environments while preserving shell overrides.

After those fixes, Python compilation and FastAPI import, both Node launcher syntax checks, `npm run db:migrate`, `npm run typecheck`, and `npm run build` all exited successfully. The migration command ran against the existing local SQLite database. No application tests or provider calls were run. Live HTTP/OAuth, PostgreSQL execution, Docker builds, and deployment networking remain unverified; this environment restricts service listeners.

## Rollout and rollback

Stop the old TypeScript worker before starting the Python worker. Both schemas are identical; data stays at `.data/store.sqlite` locally or the same PostgreSQL URL. Preserve original source in a migration archive for rollback. To roll back, restore the archived TypeScript backend and old deployment configuration and stop the Python services first. Do not run old and new writers during a rollout. Backend code remains unpublished until owner deployment.
