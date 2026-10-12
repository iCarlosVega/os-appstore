# Telegram runtime lane completion

Implemented Task 3 on `telegram/runtime` in `/Users/carlosvega/.codex/worktrees/4f19/os-appstore`, from frozen baseline `7f97d34e70b55d1248babcfb5628484b659c2d22` (`telegram-approvals-baseline-2026-10-12`). No merge, push, deployment or activation was performed.

## Owned changes

- `backend/app/config.py`: four Telegram attributes; only exactly `1` enables Telegram, IDs remain strings, token excluded from config repr. Explicit local mode pins all four values to local-file values or disabled/blank defaults.
- `scripts/local.mjs`: the same local-file Telegram isolation in Node; `telegram` subcommand accepts only optional `--once`. Existing command routes/flags remain available.
- `scripts/backend.mjs`, `package.json`: `telegram` routes directly to `app.telegram_worker`; four exact npm scripts: `telegram`, `telegram:once`, `local:telegram`, `local:telegram:once`.
- `.env.example`, `.env.development.example`: disabled/blank placeholders only.
- New `backend/app/telegram_worker.py`: safe import in both package namespaces; strict enable/token/positive decimal ID validation before integration imports or DB/network work; lazy integration imports with safe actionable errors; read-only schema/version/table/settings readiness; SQLite readiness uses URI `mode=ro`, so it cannot create a missing database. No initialize/migrate calls.
- Worker startup suppresses HTTP logs, validates `getMe` bot identity and refuses an existing webhook. Lease key is exactly `telegram:<bot_id>`; offset key is exactly `telegram:<bot_id>:<owner_user_id>:<chat_id>`. Lease uses random UUID ownership, 90-second expiry and 20-second heartbeat; acquisition/renewal use existing writer transactions and controller receives `assert_active` for external calls and guarded mutations.
- Runtime supports SIGINT/SIGTERM, interruptible bounded exponential/retry-after backoff for only `transient`/`rate_limited`, lost-lease failure, and one zero-timeout controller iteration for `--once`. Cleanup always attempts client closure. Lease release deletes only its UUID-owned row; PostgreSQL cleanup avoids the global advisory writer lock and has a 5-second statement timeout, SQLite cleanup uses an existing file and a 10-second busy timeout. Failed/blocked cleanup reports safe text and defers to lease expiry. No provider payloads, exception tracebacks, tokens or token URLs are emitted by worker error handling.
- `README.md`: setup through BotFather; private verified owner/chat IDs without first-user enrollment; local/ordinary migration/start order; four commands and direct module equivalents; no GitHub OAuth requirement for Telegram; backlog and required-field review flow; expiration/replay/card-duplication limits; stop/restart; separate bots per database; changing owner/chat cannot recover acknowledged updates; explicit later activation gate. Existing Compose definitions are documented as not starting Telegram.

## Checks actually run

All final checks below passed on 2026-10-12:

- `node --check scripts/backend.mjs` and `node --check scripts/local.mjs`.
- Parsed `package.json` and asserted each of the four npm scripts equals the exact frozen launcher command.
- `backend/.venv/bin/python -m compileall -q backend/app/config.py backend/app/telegram_worker.py`.
- Safe config/worker imports in both `backend.app.*` and `app.*` namespaces, with audit hooks rejecting DB connections, network activity, subprocess launches and private `.env` reads. Observed zero DB/network/subprocess attempts; integration modules were not imported. Did not call worker `main()` or startup helpers.
- Offline Python configuration inspection using temporary synthetic local env files: absent Telegram fields override inherited enabled/token/IDs with disabled/blank values; explicit local values win; only exactly `1` enables the Config attribute; IDs stay strings; token is absent from repr. No real env/credentials/data were copied or read.
- Offline Node inspection of the actual `localEnvironment` function with synthetic inputs confirmed all four local-file/default values override inherited Telegram fields. No launcher/main/child process was executed.
- `git diff --check` and static ownership/interface review. An independent read-only runtime review checked configuration isolation, schema reads, webhook refusal, lease/offset scope, retries and shutdown. It found one shutdown cleanup lock issue; the final implementation removes that writer-lock dependency and bounds the conditional delete. Compilation/safe imports/Node syntax/whitespace checks were rerun after the fix. Behavioral proof of the fix remains deferred under owner policy.

Created a worktree-local `backend/.venv` and installed only existing pinned `python-dotenv==1.2.2`, needed for safe config imports. The sandbox attempt failed registry DNS; the approved escalated registry-only retry succeeded. No dependency declarations/lockfiles were modified; other backend and Node dependencies were not installed or borrowed. No Next.js APIs/frontend code were changed.

## Rulings and limits

- The explicit no-application-tests/no-launch policy overrides skill TDD/test-suite/task-done defaults. Used the assigned checkbox Task 3 and a local execution ledger directly instead of sequential task-script parsing. Cost: runtime behavior remains unproven; the coordinator must authorize disposable behavioral checks before activation.
- Review ran against the final lane work product (including the new worker), rather than a merged feature. Bot/core behavior and transport details cannot be verified here. No deferred minor findings.
- No application tests, fake controller/transport behavioral tests, CLI/worker launches, live DB access, migrations, Telegram/GitHub requests/messages, service changes, candidate publication or production changes were performed. Only dependency installation accessed the package registry.
- Static/configuration checks do not prove unauthorized-update handling, publication rollback/idempotency, webhook/config failure paths, concurrent/lost leases, signal timing, transport logging safety, offset recovery or active API/jobs independence.

## Integration dependencies and coordinator follow-up

Expected absent resources in this lane at handoff: `backend/app/telegram_review.py`, `backend/app/telegram_api.py`, `backend/app/telegram_bot.py`, and `backend/alembic/versions/0002_telegram_reviews.py`. No stubs or cross-lane edits were added. Worker imports compile independently; enabled startup reports missing integration/dependencies safely. Full combined imports and schema/bot/worker availability must be checked after review-core → bot → runtime integration.

Existing `db.transaction()` acquires PostgreSQL's global advisory writer lock without a timeout before yielding. Cleanup is now bounded independently, but startup lease acquisition, heartbeat and controller domain transactions still inherit that shared behavior; a stalled external writer can delay their return despite a stop signal. Review bounded shared DB-operation handling during integrated concurrency/shutdown checks; this lane does not modify `db.py` or bot/core transactions.

Coordinator retains combined security review, explicitly authorized disposable behavioral checks, migration, private bot configuration and any activation/deployment. The root checkout, private env, running services/DB, discovery/jobs/API/CLI, review/bot modules, migrations, Discord, frontend and dependency/lockfiles were left unchanged.
