# Catalog import lane — 2026-10-12

Implemented Task 2 on `local-db/catalog-import`, starting from frozen baseline `5db288133b2005f78698ac9776fa8db824f0a0ac`. Only `backend/app/catalog_import.py` and this completion note belong to the lane. Migration/runtime integration, service startup and actual import remain separate work.

## Delivered contract

`import_catalog(source_url="https://os-appstore.vercel.app", *, apply=False)` returns exactly `applied`, `insertedApps`, `skippedApps`, `insertedCategories`, and `skippedCategories`. Preview counts describe the proposed inserts and skips; `applied` is false unless explicitly requested. Module entry points are `python -m app.catalog_import` from `backend/` and `python -m backend.app.catalog_import` from the repository root. Both accept `--source-url` and opt-in `--apply`.

- Before any connection or fetch, require `STORE_LOCAL=1`, explicit `APP_ENV=development`, nonproduction effective configuration, and `postgres://` or `postgresql://` targeting `127.0.0.1` or `[::1]`, port `55432`, database `os_appstore_development`. Reject all URL query options/fragments, nonliteral/multiple/socket hosts, and inherited libpq routing/service/options variables. The future runtime wrapper must supply this environment; the importer does not load another env file or initialize/migrate a database.
- Require existing local schema and valid settings before fetching, then recheck under the existing transaction/advisory lock. Read only public `/api/catalog` and `/api/categories` with HTTPX's 10-second timeout, redirects and environment proxies disabled, separate cookie-free clients, and no authorization. Require uncompressed responses; stream at most 5 MiB and accept at most 1,000 records per collection. Duplicate JSON keys are invalid. Custom sources must be HTTPS origins without credentials, path, query or fragment.
- Validate the complete snapshot before mutation: canonical UUIDs, numeric repository identities, slugs, positive integer source revisions, literal `published=true`, strict Metadata values, explicit publication fields, free-use/non-NSFW eligibility, unique identities, category references, existing parents and acyclic hierarchy. Sort category inserts parent-first. Inconsistent public reads fail with retry guidance.
- Compute all destination collisions under the common writer lock. Exact app `id`/`repo_id`/`slug` matches skip without changing metadata, revision, publication, counters or related state. Conflicting app identities, new-app candidate/redirect collisions, and differing category definitions abort. Local publication pause prevents new app imports.
- Apply inserts missing categories/apps in one transaction, preserves source identities/revisions/Metadata, sets local timestamps, and creates no click history or private source state. Reuse existing publication validation for inserted apps. Bump local settings revision once and add one count-only local audit event only when something was inserted. No update/replace/delete/reset modes exist. CLI failures are nonzero and omit source payloads, credentials and database exceptions.

## Verification

Created an independent ignored `backend/.venv` with Python 3.14.6 and installed the unchanged pinned `backend/requirements.txt`; no shared virtualenv or tracked dependency changes.

Authorized checks:

- `backend/.venv/bin/python -m compileall -q backend/app/catalog_import.py` — passed.
- `backend/.venv/bin/python -m pip check` — passed, no broken requirements.
- Safe module imports as both `backend.app.catalog_import` and `app.catalog_import` in isolated child environments — passed. Disabled dotenv loading, cleared database/provider/auth credentials, and supplied an unused temporary SQLite path without initializing, migrating or opening it. Did not invoke the importer or CLI.
- `git diff --check` — passed.
- Independent read-only review of destination guards, bounded HTTP parsing, snapshot validation, all SQL writes and transaction/rollback paths found two important input-validation gaps and one safe-error gap. Fixed PostgreSQL INTEGER revision bounds, raw repository identity validation before whitespace normalization, and HTTPX origin validation before any database access. Reviewed those corrections and repeated authorized syntax/import checks; no second reviewer was dispatched.

These checks establish syntax/import/dependency consistency; they do not establish database or HTTP behavior. No application tests were added/run. No services, containers, schema migrations, catalog previews/imports, production data access, notifications, paid calls, merges or deployments were performed.

Official references reviewed: [HTTPX streaming and timeouts](https://www.python-httpx.org/quickstart/), [HTTPX environment controls](https://www.python-httpx.org/environment_variables/), [PostgreSQL connection URI and libpq parameters](https://www.postgresql.org/docs/17/libpq-connect.html).

## Integration notes and pending validation

No shared blocker was identified. Migration lane must provide the initialized schema/settings; runtime lane must provide explicit local environment and command forwarding. Existing ordinary config continues loading its own dotenv files until runtime changes land; independent destination guards still reject nonlocal destinations, and verification explicitly disabled dotenv loading.

Decision: exact matching apps skip before candidate checks, because ordinary local approval leaves an `approved` candidate row. Candidate conflicts still abort new app insertion; preserved apps retain all local state. Cost if wrong: importing a matching identity does not re-review its retained candidate, but never updates or republishes it.

Review ruling: treated the reviewer's minor malformed-host finding as important because an unhandled traceback breaks the promised safe, actionable CLI error contract. Fixed it within origin validation. Cost if wrong: unusual hosts HTTPX cannot parse are rejected before any local connection.

Review boundaries: runtime and migration implementation belong to the other lanes; behavioral rollback/concurrency/HTTP checks remain prohibited; a globally atomic source snapshot cannot be proven without a shared token from the public API; deployment/combined-lane acceptance belongs to integration. These boundaries defer validation rather than imply it passed. Cost if wrong: runtime behavior and source consistency may still need integration fixes; production remains untouched.

Pending owner-authorized behavioral checks: empty-target preview leaves all rows/revisions unchanged; first/repeat apply; preservation of edited/unpublished matching apps and nonzero local clicks; cross-identity/category/candidate/alias conflicts; malformed, duplicate, oversized, compressed, timed-out and changing snapshots; remote/multihost/service/socket/hostaddr destinations rejected before connection/fetch; publication pause; mid-import rollback; concurrent insertion/import; zero clicks for newly imported apps. All should use disposable isolated local targets and no production writes.
