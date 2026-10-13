# Local database runtime lane — 2026-10-12

Task 3 implemented on `local-db/runtime` in the prepared isolated worktree, based on `5db2881`. This lane is ready for coordinator integration; the local stack has not been started or behaviorally validated.

## Changes

- Added the seven planned `local:*` npm commands through `scripts/local.mjs`. Setup exclusively creates a private `.env.development.local` with a random password, preserving existing files. The tracked example has an exact ignore exception.
- Added DB-only `compose.local.yaml`: PostgreSQL 17 Bookworm, project `os-appstore-local`, persistent project volume, database `os_appstore_development`, loopback port 55432, and readiness health check. Shutdown never passes `-v`.
- Local commands require the canonical loopback database URL and matching URL-safe password before launching children. Query/service/socket/multihost routing overrides cannot pass. Inherited `PG*` settings are removed; Docker commands check the effective context/host for a local socket before contacting the engine.
- The wrapper reads only the dedicated env file, overrides inherited application settings, pins development endpoints, worktree Python/data/backup paths and model default, and blanks every absent application credential. Python local config independently validates and pins its settings without loading fallback files or interpolating env values. Ordinary Node/Python dotenv behavior remains unchanged outside local mode.
- Database startup waits for health; missing Docker/interpreter/dependencies/integration modules and occupied ports have actionable failures. Child signals/exit codes propagate. Local dev pins API/Next to loopback and ports 8000/3000, retaining reload and existing failure cleanup. Worker startup is separate.
- Documented dependency/setup/start order, migration versus import, preview/apply and repeat-import preservation, local credentials, logging, shutdown, backup/recovery and volume/password retention. Corrected the previous claim about Next.js: listing READMEs are fetched publicly from GitHub.

## Verification performed

- `node --check scripts/local.mjs`, `scripts/dev.mjs` and `scripts/backend.mjs` passed.
- `python3 -m py_compile backend/app/config.py` passed.
- Parsed `package.json` and confirmed the seven expected local scripts.
- `docker compose --env-file <temporary placeholder file> -p os-appstore-local -f compose.local.yaml config --quiet` passed without contacting the engine or starting containers.
- Safe-imported `backend.app.config` in normal development mode with a temporary unused SQLite path and blank credentials, and in local mode with an absolute temporary placeholder env file. Neither check called initialization/migration or opened a database connection.
- Reviewed Next 16.3.7's installed environment guide in the root checkout read-only; `process.env` precedes fallback files. No root dependency/environment/database was modified or shared for execution.
- Created an ignored worktree-local `backend/.venv` and installed only the existing pinned `python-dotenv==1.2.2` dependency for safe imports. Sandbox package-index DNS failed; installation succeeded with command escalation. Full integrated requirements and Node dependencies still need installation in the integration worktree.
- Git whitespace and ignore-rule checks passed: the actual local env is ignored and the example is eligible for tracking.

Syntax, configuration and import checks do not prove runtime isolation or end-to-end behavior. No application tests, local setup command, containers/listeners, worker, database migration/adoption, catalog fetch/import, paid calls, notifications, production writes or deployment were run.

## Integration requirements and decisions

- Integrate migrations and catalog-import before runtime, as planned. Runtime deliberately requires the migration lane's `backend/app/schema.py` and dependencies; import additionally requires `backend/app/catalog_import.py`. No replacement schema/import code or shared-file requests were necessary.
- Destination validation deliberately accepts only the generated canonical `postgresql://store:PASSWORD@127.0.0.1:55432/os_appstore_development` form. Other loopback aliases/protocol spellings must be normalized in the local file. The PostgreSQL password must match the Compose password; generated passwords satisfy both parsers without interpolation.
- Docker database commands require a local Unix socket. A remote context is refused even when an inherited local `DOCKER_HOST` would otherwise obscure it. TCP Docker endpoints must be switched to a local socket/context.
- A fresh read-only reviewer found one Important issue: the existing Windows Node launchers can orphan Python when a child fails. Restricted the new local wrapper to POSIX hosts (macOS/Linux), with an actionable refusal before file access or child startup, and documented the limit. Existing non-local commands remain unchanged. Supporting native Windows later requires process-tree cleanup; it is not part of this lane.
- Honored the explicit plan/handoff policy against application tests; behavioral validation is deferred to authorized coordinator integration. Keep this branch/worktree for that integration; do not merge, deploy or delete it automatically.

## Behavioral validation still required

In a disposable integrated environment, authorize and check hostile inherited URLs/credentials and fallback env files; first/repeated setup and private file permissions; missing env/dependencies/modules; occupied 55432/8000/3000 and failed-child cleanup; local Docker selection; API/worker sharing one destination; signals/reload and worker restarts; migration then preview/apply import; preserved volume and password on stop/start; local backups; homepage/detail/README display; and local edits/downloads/jobs leaving production unchanged. Importer and migration behavioral cases remain with their respective lanes/coordinator.

The reviewer otherwise found no Critical or Minor issues in the inspected POSIX path. Live lifecycle/port/volume behavior and other lanes were not judged, per ownership and verification policy. The reviewer checked application env coverage but did not independently inspect installed Next implementation or rerun the supplied configuration checks. The coordinator must review those integration boundaries and run authorized behavioral validation before switching the stack.
