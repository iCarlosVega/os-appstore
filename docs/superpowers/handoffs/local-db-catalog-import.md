# Session 2 — Public catalog import

Branch: `local-db/catalog-import`. Resolve your worktree and common baseline from the coordinator's preparation report; do not work in the root checkout.

Read the local-database spec and parallel plan dated 2026-10-12, then execute Task 2 with superpowers:executing-plans. The plan's global constraints, frozen interfaces and verification policy apply.

## Exclusive ownership

- New `backend/app/catalog_import.py`
- `docs/superpowers/completions/local-db-catalog-import.md`

Keep database/schema/config/models/store/CLI/runtime/README/dependencies unchanged. Importer owns its module CLI, so no shared CLI edit is needed. Report shared blockers to the coordinator.

## Deliverable

`import_catalog(source_url="https://os-appstore.vercel.app", *, apply=False) -> dict`, with the exact summary fields in the plan. CLI: `python -m app.catalog_import [--source-url URL] [--apply]` from `backend/`.

Guard the explicitly local PostgreSQL destination before any fetch/initialization/write. Read public catalog/categories only; validate a bounded complete snapshot before insert-only changes. Default preview never initializes/migrates/writes. Existing local metadata, unpublished apps, settings and counts remain untouched; identity/category/candidate/slug-alias collisions abort. Apply uses one existing transaction, imported stable identities/source revisions, local timestamps, zero imported click history, and one local revision bump/audit only if inserts occurred.

## Start and finish

1. Verify your branch and clean baseline. Create your own `backend/.venv` with current requirements; no shared venv, root `.env` or database.
2. Read the public endpoints and storage/publication contracts. Your module can compile/import before the other two lanes land; actual application requires migrated local PostgreSQL and the runtime wrapper.
3. Implement Task 2 and run only authorized syntax/safe-import/code-review gates. Do not run the importer, initialize databases, start services, add/run application tests, or access private production data.
4. Commit the module and completion note with exact checks, limits and shared blockers. Do not merge, deploy or delete worktrees.
