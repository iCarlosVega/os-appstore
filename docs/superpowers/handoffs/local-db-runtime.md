# Session 3 — Isolated local runtime

Branch: `local-db/runtime`. Resolve your worktree and common baseline from the coordinator's preparation report; do not work in the root checkout.

Read the local-database spec and parallel plan dated 2026-10-12, then execute Task 3 with superpowers:executing-plans. The plan's global constraints, frozen interfaces and verification policy apply.

## Exclusive ownership

- New `compose.local.yaml`, `scripts/local.mjs`, `.env.development.example`
- `backend/app/config.py`, `scripts/dev.mjs`, `scripts/backend.mjs`
- `package.json`, `.gitignore`, `README.md`
- `docs/superpowers/completions/local-db-runtime.md`

Keep production Compose, Dockerfiles, schema/CLI/importer, dependencies/lockfile, worker and frontend unchanged. Report shared blockers to the coordinator.

## Deliverable

The seven `local:*` npm commands and wrapper subcommands named in the plan. Dedicated PostgreSQL 17, project `os-appstore-local`, host `127.0.0.1:55432`, database `os_appstore_development`, persistent separate volume. Single ignored `.env.development.local`; `local:setup` never overwrites it and generates a private random password if absent. Local API/web/worker use the same guarded database and forced local endpoints, with external integration credentials absent unless explicitly set locally. Node/Python skip fallback dotenv loading in explicit local mode. Explicitly empty absent application credentials before launching Next; merely deleting variables lets Next restore fallback values. Pin API ports/interpreter/paths as specified in the plan. Production environment behavior and SQLite data remain intact.

Do not add a second schema/import implementation: migration invokes the existing launcher; importer invokes the other lane's module. Before integration, missing modules/dependencies must produce actionable errors. Worker remains explicitly started and requires restart after its code changes.

## Start and finish

1. Verify your branch and clean baseline. Use worktree-local dependencies/virtualenvs if needed. Never share root `.env`/`.data` or start another listener on 3000/8000/55432 during implementation.
2. Trace Python dotenv, Node shell precedence, Next env-file loading, child process signals and existing launcher behavior. Preserve normal commands; isolate explicit local commands.
3. Implement Task 3 and run only syntax/config/safe-import/code-review gates. Compose config verification uses temporary placeholder values and `--quiet`; no containers, migrations, import, workers or application tests.
4. Document setup, preview/apply, preservation, migration recovery, volume retention and stopping/restarting services. Commit owned files and completion note; report limits/shared blockers. Do not merge, deploy or delete worktrees.
