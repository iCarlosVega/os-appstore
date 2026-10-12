# Local database migrations — 2026-10-12

Implemented Task 1 on `local-db/migrations`, starting at frozen baseline `5db288133b2005f78698ac9776fa8db824f0a0ac`. Only migration-lane files and this completion note changed. No shared blockers; importer/runtime integration remains the coordinator's work.

## Delivered

- `db.migrate()` delegates lazily to `schema.upgrade_schema()`. Existing query/transaction adapters and `store.initialize(migration=False)` are unchanged. PostgreSQL API/worker startup still does not run schema migrations; SQLite startup retains automatic migration, foreign keys, busy timeout and WAL.
- Alembic `0001_initial` freezes all 17 existing tables and three indexes. SQLAlchemy is used only for migration connections, schema definitions and inspection, without ORM models. SQLite's legacy nullable TEXT primary keys and PostgreSQL's implicit NOT NULL primary keys remain distinct; the integer settings key does not acquire a SERIAL sequence/default.
- Empty schemas upgrade; complete compatible unversioned schemas are verified before baseline stamping; partial/incompatible schemas and unknown/multiple revisions fail before schema mutation. Versioned baseline schemas are also checked before upgrade. There is no destructive repair or application-row rewriting.
- Inspection checks column names/types/nullability/defaults/generated values, PK/unique/FK/check constraints, indexes, version-table shape and unexpected tables/views/sequences/triggers. Supplemental PostgreSQL catalog checks reject deferrable/unvalidated constraints, alternate collations, table rules and row-security/inheritance policies. SQLite stored-DDL/index inventory rejects options omitted by reflection, including replacement conflict policies and expression indexes.
- Adoption and upgrade share one SQLAlchemy connection and transaction. PostgreSQL takes advisory lock `19962411`; SQLite begins an explicit `BEGIN IMMEDIATE` for transactional DDL. Migrations refuse entry from an existing application transaction rather than opening a second competing lock connection.
- PostgreSQL uses the existing psycopg connection string directly through an engine creator. Credentials never enter Alembic ConfigParser or the engine URL, preserving encoded/literal percent handling without interpolation. SQLite paths are resolved absolutely. Driver exception details are suppressed in migration errors.
- Direct/offline Alembic execution without the supplied connection is disabled. Baseline downgrade refuses table removal and points to recovery from a verified backup in a separate database.
- Pinned `alembic==1.20.0`, `SQLAlchemy==2.1.4`; installed requirements in this worktree's `backend/.venv`. Docker copies Alembic configuration and revision resources; existing production Compose/root SQL remain unchanged.

## Verification performed

- `backend/.venv/bin/python -m compileall -q backend/app backend/alembic` — passed.
- `backend/.venv/bin/python -m pip check` — no broken requirements.
- Safe import checks from both repository root (`backend.app`) and backend working directory (`app`) with an isolated environment, blank credentials and unused temporary SQLite path. Database connection functions were blocked. Confirmed migration dependencies remain lazy, revision head resolves to `0001_initial`, and no database file is created. No initialize/migrate calls were made.
- Compiled baseline DDL for PostgreSQL and SQLite without an engine/connection: 17 tables and three indexes in each dialect. Reviewed generated definitions against `migrations/001_initial.sql`, especially PK nullability, integer defaults, foreign keys and checks. This is configuration inspection, not behavioral proof.
- Independent read-only reviewer checked the migration lane and installed dialect source. Four important findings were addressed: PostgreSQL PK deferrability, PostgreSQL unvalidated constraints, SQLite unreflected expression indexes and SQLite constraint conflict policies. Fixes received static author review and repeated syntax/import checks; no behavioral tests were run.
- `git diff --check` and exclusive-file-ownership review — passed.

## Decisions and limits

Followed the plan/handoff's explicit owner policy of no application tests instead of the executing-plans skill's usual TDD gate. Migration execution, adoption, concurrency and rollback remain unproven; syntax/import/DDL checks are not behavioral verification. No database was connected to, created, adopted, stamped or migrated. No services, workers, imports, paid calls, production actions, merge or deployment were performed. The branch/worktree are retained for coordinator integration.

Compatibility verification is intentionally conservative: custom/extra schema objects or non-baseline options require manual review, even when they might be harmless. Baseline revision resources must remain immutable; future schema changes need new revisions and matching verification rules.

Proposed authorized follow-up: disposable PostgreSQL 17/SQLite empty upgrade; exact legacy adoption preserving representative rows; repeated upgrade; partial/type/default/nullability/PK/unique/FK/check/index mismatch refusal; unknown revision refusal; encoded/literal percent passwords; concurrent migrators; interruption/rollback and downgrade refusal. Include the review cases (deferrable/unvalidated constraints, expression indexes, replacement policies/collations), production startup compatibility and SQLite startup repeatability. None of these behavioral cases ran in this lane.

References reviewed: [Alembic shared migration connections](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands), [SQLAlchemy SQLite transaction control](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#enabling-non-legacy-sqlite-transactional-modes-with-the-sqlite3-or-aiosqlite-driver), [Alembic release](https://pypi.org/project/alembic/1.20.0/), [SQLAlchemy release](https://pypi.org/project/SQLAlchemy/2.1.4/).
