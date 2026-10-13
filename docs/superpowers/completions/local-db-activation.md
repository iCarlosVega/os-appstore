# Local database activation

Date: 2026-10-12. Status: reviewed integration landed on `develop`; root local PostgreSQL, API, frontend and worker are running.

## Authorization and integration

The owner answered “yes merge to develop” to the concrete proposal to merge, start local PostgreSQL, import the 12 published apps and restart local services. No production deployment or merge to `main` was included.

Root `develop` fast-forwarded from `5db2881` to reviewed integration `7a07368`. The integration/build/review evidence is in `local-db-integration.md`; this report records subsequent operational activation. Implementation worktrees are retained. No remote push was performed during activation.

## Local setup

- Identified the existing root API/web/worker processes and verified their working directories before stopping them. Other projects' services were not stopped.
- Backed up existing SQLite and root environment files under `.data/local-db-activation-backups/20261012T055451Z/`, with restricted permissions. Original SQLite rows and environment file contents matched the backup after activation.
- Updated the root Python virtualenv with the integrated requirements. It lacked pip, so `ensurepip` installed pip before installing Alembic/SQLAlchemy; `pip check` passed.
- Created private `.env.development.local` (0600) with generated database credentials and blank external integration credentials. No secrets were committed.
- Started healthy PostgreSQL 17 via `compose.local.yaml`, project `os-appstore-local`, persistent volume `os-appstore-local_database`, bound to `127.0.0.1:55432`.
- Ran `local:db:migrate`, reaching Alembic revision `0001_initial` and seeding local defaults/categories.
- Preview: 12 new apps, zero new categories, nine existing categories. Explicit apply inserted 12 apps. Subsequent preview reported zero new apps/categories, skipping all 12 apps and nine categories.
- Read-only local database inspection confirmed 12 apps, nine categories, zero click rows, one import audit event and AI paused.
- Installed Homebrew `libpq@17` client tools (17.11, plus krb5 dependency) for host-side worker backups. Added its bin directory to PATH in the private local environment only; no shell profile changes. Created a PostgreSQL custom-format backup and verified its archive list includes the apps table.

## Running services and verification

- Root command: `npm run local:dev`; log: `.data/local-postgres/dev.log`.
- Separate root worker: `npm run local:jobs`; log: `.data/local-postgres/worker.log`.
- Process metadata: `.data/local-processes.json` (ignored). Current launch parents were 14594 (dev) and 14595 (worker); inspect fresh process metadata/working directories before stopping them in future.
- Frontend: `http://localhost:3000`; FastAPI: `http://127.0.0.1:8000`. Both listeners bind to loopback.
- Both `/api/health` paths returned HTTP 200 with FastAPI status `ok`; both catalog endpoints returned 12 apps.
- Homepage returned HTTP 200 and rendered all 12 app names. GridCraft detail returned HTTP 200, rendered Copy for AI, and rendered GitHub README content without its unavailable fallback.
- PostgreSQL backup `.data/local-postgres/backups/store-2026-10-12T05-56-41-564Z.dump` was 23,366 bytes and readable by `pg_restore --list`.

## Limits and follow-up

These are operational activation checks, not a comprehensive application test suite. No disposable legacy-schema adoption/refusal, concurrency/rollback, local-edit preservation, process-signal cleanup or volume restart tests were run. Do not claim those cases proven by the successful fresh migration/import. Existing dependency advisories noted in the integration report remain a separate follow-up.

GitHub OAuth/owner administration, discovery and notifications require explicitly configured local credentials. AI remains paused. Original SQLite and root production/default configuration were preserved. No production database writes, paid calls, external notifications or deployments were performed.
