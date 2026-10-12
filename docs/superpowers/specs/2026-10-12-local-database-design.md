# Local PostgreSQL development and catalog snapshot

Status: all three implementation lanes are complete and integrated on `local-db/integration`. Static checks, build/typecheck and independent code review passed. Local activation, database behavioral validation and landing on `develop` remain pending; see `docs/superpowers/completions/local-db-integration.md`.

## Outcome

`http://localhost:3000` uses local FastAPI and a dedicated local PostgreSQL 17 database containing copies of the currently published apps and their categories. Edits and worker activity remain local. Railway remains the production source and is never a development write target.

## Design

- Add a database-only `compose.local.yaml`, separate from production `compose.yaml`, using `postgres:17-bookworm`, Compose project `os-appstore-local`, its own persistent volume, and host binding `127.0.0.1:55432`. Ports 5432 and 5433 are already occupied on this computer. Database name: `os_appstore_development`.
- Run Next.js and Uvicorn on the host with their existing reload behavior. Start the worker explicitly, separately. Local commands use a dedicated git-ignored `.env.development.local`; never copy production secrets or silently inherit remote database/backend URLs. Existing ordinary development/production commands retain their behavior. Node/Python skip fallback dotenv loading in explicit local mode; Next may still inspect its standard env files, so every application setting/credential is explicitly pinned to a local value or empty string.
- Explicit local commands force `STORE_LOCAL=1`, `APP_ENV=development`, `APP_URL=http://localhost:3000`, `BACKEND_URL=http://127.0.0.1:8000`, and a validated loopback PostgreSQL destination on port 55432/database `os_appstore_development`. Local GitHub/AI/Discord credentials default blank. Preserve the existing SQLite file without moving or deleting it.
- Alembic manages schema versions; SQLAlchemy is used for migration connections/reflection only. Keep existing psycopg/sqlite query and transaction code, Pydantic models, JSON fields, and public APIs. Do not rewrite the app as an ORM.
- `db.migrate()` remains the migration entry point. An empty database receives the baseline; a complete, semantically verified legacy schema is adopted without modifying its rows; partial/incompatible schemas are rejected before mutation. Unknown/newer Alembic revisions fail clearly. Preserve SQLite migration compatibility and explicit PostgreSQL pre-deploy migration.
- Import only public `GET /api/catalog` and `GET /api/categories` from `https://os-appstore.vercel.app`. No Railway credentials, database tunnel, private export, paid calls, or production writes are needed.
- Import is explicit and insert-only. Default invocation is a read-only preview; `--apply` commits. Existing local apps/categories and their edits remain untouched. Identity/category conflicts abort the whole import with a useful summary. Repeating the import skips existing matching identities; it does not synchronize overwrites or deletions.
- Preserve imported app IDs, repo IDs, slugs and source revisions; use local import timestamps and start local click counts at zero. Do not copy private candidates, proposals, settings, users/sessions, jobs, leases, requests, costs, notifications, click history, audit, caches, or rate limits. Local settings revision changes only when local catalog content is inserted.
- Validate the entire fetched snapshot before writes, including published status, Metadata/publication eligibility, uniqueness, category references/hierarchy, and collisions with local candidates and slug aliases. Two public GETs are not a transactional snapshot: reject inconsistency and allow a later explicit retry.

## Delivery and limits

Three separate sessions own migrations, runtime, and importer. They start from one committed `develop` baseline and must not edit another lane's files. Merge/review migrations, importer, then runtime into an integration branch based on that baseline. Only after integration should the root development services switch from SQLite to local PostgreSQL.

The existing owner verification policy remains: no application tests unless requested. Plan syntax/import/configuration/code-review gates; list disposable database behavioral checks separately as requiring authorization. No implementation, schema adoption, import, runtime switch, production deployment, or worktree dependency setup is authorized by this preparation alone. The requested worktree cleanup and creation are authorized now.

## Acceptance

- All three local services share the isolated PostgreSQL destination; homepage and app detail pages show the published snapshot (currently 12 ArtCraft apps).
- Local edits, downloads, and jobs leave production unchanged. Dry runs/rejected imports do not initialize or write any database.
- Fresh and existing compatible databases can reach Alembic head without data loss; incompatible schemas cannot be blindly stamped.
- Restarting the stack preserves local data; ordinary stop does not delete volumes. Environment examples and documentation cover startup, refresh, backups, worker limitations and migration recovery.

References: [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html), [shared migration connections](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands), [Docker Compose service configuration](https://docs.docker.com/reference/compose-file/services/).
