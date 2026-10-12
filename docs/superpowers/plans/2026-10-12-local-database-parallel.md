# Local Database and Catalog Snapshot Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for your assigned lane. The owner will open three separate Codex sessions. Do not launch another implementer or edit another lane. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Develop locally against PostgreSQL 17 populated from the store's public catalog, with versioned schema migrations and no production writes.

**Architecture:** Host Next.js, FastAPI and an explicit worker connect to a dedicated Docker PostgreSQL instance. Alembic adopts the existing schema safely; a separate insert-only importer reads public production HTTP endpoints. Each lane has exclusive file ownership and integrates through the contracts below.

**Tech Stack:** Python/FastAPI/Pydantic, psycopg/sqlite3, Alembic/SQLAlchemy for migrations, Docker Compose/PostgreSQL 17, existing Node/Next launchers.

**Spec:** `docs/superpowers/specs/2026-10-12-local-database-design.md`.

## Global constraints

- No production writes, credential exports, Railway tunnels, paid calls, external notifications, automatic publication or deployment.
- PostgreSQL image `postgres:17-bookworm`; project `os-appstore-local`; loopback port `55432`; database `os_appstore_development`. Keep production Compose unchanged.
- Local importer requires `STORE_LOCAL=1`, development mode, and a PostgreSQL URL with literal loopback host, port 55432 and exact database name. Reject everything else before any initialization, fetch or write; reject multihost/service/socket URL overrides too.
- Local environment file `.env.development.local` is ignored; example `.env.development.example` is tracked. Do not read production fallback env files in explicit local mode or inherit provider credentials silently.
- Preserve database query/transaction contracts, SQLite fallback, camelCase JSON metadata, manual overrides, approved identities and existing data. No ORM conversion.
- Default import previews only. `--apply` inserts missing records; never replace, reset or delete existing local data. Keep production click totals out of local counters.
- Existing verification policy: no application tests unless owner requests them. Use syntax/import/configuration checks and code review; do not call compilation behavioral proof. Proposed DB/HTTP checks below require separate authorization.
- No new schema tables beyond `alembic_version`; no frontend/API changes are required. Keep dependencies worktree-local and avoid shared databases, environment files, ports and mutable virtualenvs during lane work.

## Review focus

1. Legacy/partial schema and concurrent migrators: verify before adoption, preserve rows and serialize migration on one connection (migration lane).
2. Shell, dotenv and Next env precedence: local API/worker/web must not inherit Railway URLs or paid/external credentials (runtime lane).
3. Snapshot inconsistency, malformed identities, cyclic categories and destination collisions: fail before mutation, with bounded responses (import lane).
4. Repeated import and locally edited/unpublished apps: preserve all existing local values, skip matching identities, reject conflicting identities (import lane).
5. Interrupted import/startup, occupied ports and persistent volumes: transactional import, useful startup failures, retained local data and separate worker lifecycle (import/runtime lanes).

## Worktree/session ownership

All sessions begin at the same clean planning commit on `develop`; preparation records actual paths and SHA in `docs/superpowers/completions/local-database-preparation.md` after native worktree creation. Do not rebase onto a moving `develop`.

| Session | Branch | Exclusive production ownership | Handoff |
| --- | --- | --- | --- |
| 1: migrations | `local-db/migrations` | `backend/app/db.py`, new `backend/app/schema.py`, `backend/requirements.txt`, `backend/Dockerfile`, new `backend/alembic.ini`, new `backend/alembic/**` | `docs/superpowers/handoffs/local-db-migrations.md` |
| 2: catalog import | `local-db/catalog-import` | new `backend/app/catalog_import.py` | `docs/superpowers/handoffs/local-db-catalog-import.md` |
| 3: local runtime | `local-db/runtime` | new `compose.local.yaml`, new `scripts/local.mjs`, `scripts/dev.mjs`, `scripts/backend.mjs`, `backend/app/config.py`, `package.json`, new `.env.development.example`, `.gitignore`, `README.md` | `docs/superpowers/handoffs/local-db-runtime.md` |

Each session also owns only its `docs/superpowers/completions/local-db-<lane>.md`. The coordinator owns plan/spec/handoffs and final integration. Keep `compose.yaml`, root `migrations/001_initial.sql`, `store.py`, `cli.py`, models, API, scheduler and frontend source unchanged unless a demonstrated shared blocker is handed to the coordinator.

## Frozen integration contracts

- Keep `config.database_url`, `sqlite_path`, `backup_dir`, `production`, `db.query(sql, values=())`, `db.transaction()`, `db.migrate()` and `store.initialize(migration=False)` signatures/behavioral roles. `db.migrate()` delegates to new `schema.upgrade_schema() -> None`. No Alembic imports/connections at module-import time.
- `schema.upgrade_schema()` constructs migration configuration from ROOT and existing config, supports PostgreSQL/SQLite, and applies/adopts baseline revision `0001_initial`. No automatic migration on PostgreSQL API/worker startup. Existing SQLite startup migration continues through the same entry point.
- `catalog_import.import_catalog(source_url: str = "https://os-appstore.vercel.app", *, apply: bool = False) -> dict` returns `applied`, `insertedApps`, `skippedApps`, `insertedCategories`, `skippedCategories`. Raise a safe actionable RuntimeError on conflicts/validation/network failure; module CLI exits nonzero and omits credentials/payloads.
- Import module entry point: `python -m app.catalog_import [--source-url URL] [--apply]` from `backend/`; also importable as `backend.app.catalog_import` from repo root. It never calls initialize/migrate. Schema/default settings must already exist.
- Runtime wrapper `node scripts/local.mjs <setup|db-up|db-down|dev|worker|migrate|import-catalog> [...args]`. It loads a single local file, validates destination, and supplies the same explicit local environment to children. Production/default commands retain their current behavior.
- npm commands: `local:setup`, `local:db:up`, `local:db:down`, `local:dev`, `local:jobs`, `local:db:migrate`, `local:catalog:import`. Preserve existing npm scripts. Import forwards flags to its module; migrate uses existing launcher.
- Python config in explicit `STORE_LOCAL=1` mode loads only the file named by absolute `STORE_ENV_FILE`, not root/backend fallback env files. Runtime wrapper overrides shell values with local-file values and forced local endpoints/mode; pins every absent application credential to an explicit empty string (GitHub OAuth/owner/auth secret/token, TypeSafe key, Discord webhook, proxy secret); pins API_HOST=127.0.0.1, API_PORT=8000, worktree-local PYTHON/SQLITE_PATH and BACKUP_DIR=.data/local-postgres/backups; and sets the default model explicitly. Node launchers skip root dotenv loading under STORE_LOCAL=1. Next may inspect fallback env files, but its application values are already present and cannot be replaced. Normal config/launchers retain current env loading.

## Task 1: Version and adopt the schema (session 1)

**Files:** migration ownership row above. **Consumes:** unchanged config and database contracts. **Produces:** `schema.upgrade_schema()` and unchanged `db.migrate()` entry point.

- [x] Read spec, plan, handoff, `db.py`, startup/CLI initialization callers, Dockerfile and all 17 tables/three indexes in `001_initial.sql`.
- [x] Pin compatible Alembic and SQLAlchemy dependencies after official documentation/version review; keep existing application adapters. Add config, env/template and immutable `0001_initial` revision resources. Docker must copy the new resources.
- [x] Build the migration engine from URLs safely (psycopg dialect, literal passwords including `%`, absolute SQLite path). Retain SQLite foreign-key and WAL configuration. Never log connection credentials.
- [x] Implement four schema states: empty -> upgrade; complete compatible unversioned -> verify then baseline-stamp; partial/incompatible -> reject with differences; known-versioned -> upgrade. Reflection verifies columns/types/nullability/defaults, PK/unique/FK/check constraints and required indexes semantically across both dialects; extra unknown app objects require review rather than destructive repair.
- [x] Serialize adoption/upgrades using one SQLAlchemy connection and PostgreSQL advisory lock `19962411`; pass that same connection through Alembic attributes. Do not hold a `db.transaction()` lock while opening another migration connection. Keep SQLite migration locking/error rollback coherent.
- [x] Delegate `db.migrate()` to the helper without changing ordinary PostgreSQL startup policy. Do not change runtime configuration, import CLI, schema shapes or production records. Baseline downgrade must refuse destructive table removal with an explicit recovery message; backups, not dropping populated tables, are the recovery path for adoption.
- [x] Run `python -m compileall -q backend/app backend/alembic`; safe-import modules with an empty temporary SQLite path and credentials blank without calling initialize/migrate. Review diff for data preservation and Docker resource paths.
- [x] Record checks/limits and proposed behavioral cases below in completion note; commit only owned files.

**Proposed behavioral validation (not authorized in this preparation):** disposable empty PostgreSQL and SQLite upgrades; exact legacy schema adoption with representative rows unchanged; partial schema/type/constraint mismatch refusal; repeat upgrade; unknown revision refusal; password containing `%`; concurrent migrators; interrupted migration rollback; downgrade refusal.

## Task 2: Import the published catalog safely (session 2)

**Files:** `backend/app/catalog_import.py`. **Consumes:** existing db/store/models/config, public endpoints. **Produces:** function and module CLI in frozen contracts.

- [x] Read spec/handoff and public `/api/catalog`, `/api/categories`, Metadata/publication validation and persistence contracts. Inspect local apps/candidates/slug_aliases collision semantics without connecting to production DB.
- [x] Implement destination guard before network access or any initialization/write: explicit local flag + development + literal-loopback PostgreSQL/55432/exact database; reject URL routing overrides. Require pre-migrated schema and existing local settings; default preview never seeds, audits or changes revisions.
- [x] Fetch only the two HTTPS public GET endpoints with timeout 10 seconds/request, no credentials/cookies, redirects disabled, maximum 5 MiB per response and at most 1,000 records per collection. Default source is the production frontend origin; validate custom source origin (HTTPS, no credentials/query/fragment/path).
- [x] Validate the entire snapshot: published boolean true, unique UUID app IDs/repo IDs/slugs, positive integer revisions, Metadata/publication rules and category graph with existing parents/no cycles. Reject inconsistent snapshots with retry guidance; sort categories parent-first.
- [x] Under one `db.transaction()`, recheck local collisions and compute insert-only changes. Matching app id/repo_id/slug triples skip even if metadata/publication changed locally; cross-identity or candidate/slug-alias conflicts abort. Matching category IDs with same name/parent skip; differing definitions abort. Do not bypass existing foreign-key/publication rules.
- [x] Preview returns predicted counts without writes. Apply inserts categories/apps, preserves source identity/revision, sets updated_at to local import time, omits clicks/private state, bumps local settings revision once and adds one local audit event only if something was inserted. Recheck under the transaction so concurrent edits/imports cannot silently overwrite.
- [x] Implement module CLI with `--source-url` and opt-in `--apply`; safe count/error output and nonzero failure exit. No replace/delete/reset modes, schema changes, private endpoints or new dependencies.
- [x] Run syntax and safe import checks without invoking CLI/import; review every write and error path. Record limits and proposed cases; commit owned module and completion note.

**Proposed behavioral validation (requires authorization):** preview leaves empty target unchanged; first/repeat apply; edited/unpublished local records preserved; all identity/category/candidate/alias conflicts; malformed/oversized/timeout/source-changing snapshots; mid-import failure rolls back; concurrent insertion; remote destination rejected before fetch/write; local click totals start at zero.

## Task 3: Wire the isolated local runtime (session 3)

**Files:** runtime ownership row above. **Consumes:** existing migration launcher and future importer CLI. **Produces:** wrapper/npm commands and dedicated DB Compose file.

- [x] Read spec/handoff and current Node/Python/Next environment loading. Preserve ordinary launcher/production Compose behavior; add a local-only wrapper and conditional Node/Python dotenv selection.
- [x] Add DB-only Compose project with image/endpoint/name from global constraints, persistent project-scoped volume, loopback-only port, pg_isready health check and no automatic volume deletion. Do not start services while implementing this lane.
- [x] `local:setup` creates `.env.development.local` with mode 0600 and a random URL-safe PostgreSQL password only if absent; never overwrite existing local/production env files. Track an example via an exact `.gitignore` exception. No real credentials in Git.
- [x] Validate the dedicated local URL before spawning children. Force local mode/endpoints and consistent backup paths; local credentials are only explicit local-file values. Check missing interpreter/Docker/env and occupied port errors; exit actionable and preserve existing services/data. Use current-directory worktree paths, not the root checkout's venv/data.
- [x] Wire database up/down, existing dev launcher, separate worker, migration launcher and importer module to local environment. Forward signals/exit codes; `dev` retains API/Next reload, worker changes require explicit restart. Fail clearly if migration/import lanes are not yet integrated. `db-down` must not pass `-v`.
- [x] Update README with setup/install/start order, environment precedence, explicit preview/apply import, repeat-import preservation policy, logs/stop/backup instructions, SQLite preservation, separate schema/data responsibilities and integration credential limits. Correct the current absolute claim that Next never calls GitHub: app README display fetches public GitHub content.
- [x] Run `node --check scripts/local.mjs`, Python config syntax/safe imports, JSON script parsing and `docker compose --env-file <temporary placeholders> -p os-appstore-local -f compose.local.yaml config --quiet` without starting containers or printing secrets. Review normal production env compatibility.
- [x] Commit only owned files/completion note. Shared lockfile edits are unnecessary because no Node dependencies are added.

**Proposed behavioral validation (requires authorization):** startup with hostile inherited Railway URLs/provider secrets; missing local env; occupied 55432; existing env preservation; API/worker same DB; signals/failed child cleanup; stop/start retains DB; homepage/detail renders all imported apps; local edit/download/job leaves source unchanged.

## Coordinator integration and handoff

Status: implementation, static integration gates and owner-authorized local activation complete. Checked lane tasks reflect committed implementations, lane completion reports and code review; they do not establish every separately listed behavioral case. See `docs/superpowers/completions/local-db-integration.md` and `docs/superpowers/completions/local-db-activation.md` for evidence and remaining verification limits. The integrated stack is on `develop`.

- [x] Review completion notes and verify exclusive file ownership. Create `local-db/integration` at the recorded planning baseline; merge migrations, catalog-import, then runtime (review at each step).
- [x] Resolve shared requests explicitly; install pinned requirements in an isolated integration venv. Run approved syntax/import/config checks, `npm run typecheck` and `npm run build`. Review root SQLite and production startup compatibility, URL/destination guards, locking, snapshot consistency and all import write paths.
- [x] Owner ran the three implementation sessions separately and reported all worktrees finished. This integration does not treat that report as permission to run application tests or live adoption/import.
- [x] Once implementation and the required behavioral validation are authorized, stop only root-local API/web/worker, back up existing local SQLite/config, create the dedicated local env, start PostgreSQL, migrate, preview/import public catalog with `--apply`, and start local dev+worker. Verify current public count (12 at planning time), both health paths, detail README and no unexpected production writes.
- [x] Land accepted integration on `develop`; never auto-merge to `main`, deploy production, delete new worktrees, or remove database volumes. Record final status and verification limits.

## Session launch prompt

Open the assigned worktree from the preparation report as a separate Codex project. Paste:

> Read `docs/superpowers/specs/2026-10-12-local-database-design.md`, `docs/superpowers/plans/2026-10-12-local-database-parallel.md` and `docs/superpowers/handoffs/local-db-<lane>.md`. Implement only that lane using superpowers:executing-plans. Preserve frozen contracts and exclusive ownership. Follow the no-application-tests policy; do not start services, touch production, share environments or implement another lane. Commit owned changes and your completion note; report shared blockers. Do not merge or deploy.

Replace `<lane>` with `migrations`, `catalog-import`, or `runtime`. Three sessions are sufficient; additional sessions would split coupled files and increase integration conflicts.
