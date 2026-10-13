# Session 3 — Telegram configuration and separate worker

Branch: `telegram/runtime`. Work only in its worktree, located in `docs/superpowers/completions/telegram-approvals-preparation.md`.

Read the Telegram spec/parallel plan dated 2026-10-12 and execute Task 3 using superpowers:executing-plans. Implement the exact worker/config/npm contracts while bot/core implementations remain in their own branches.

## Exclusive ownership

- New `backend/app/telegram_worker.py`.
- `backend/app/config.py`, `scripts/backend.mjs`, `scripts/local.mjs`, `package.json`.
- `.env.example`, `.env.development.example`, `README.md`.
- `docs/superpowers/completions/telegram-runtime.md`.

Keep private env, credentials, root services/DB, discovery/jobs/API, CLI, review/bot modules, migrations, Discord, frontend and dependency/lockfiles unchanged. No shared stubs or automatic integration edits.

## Deliverable

Explicit enable plus blank-default owner/chat/token config; local-file isolation in both Node and Python; independent Telegram worker with read-only schema readiness checks, bot/webhook verification, renewable single-consumer lease, interruptible backoff/signals, and `--once`; four exact npm commands and complete startup/operating docs. Missing integration modules should fail clearly, without mutating schema or silently falling back. Disabled/unconfigured imports/startup must not connect.

Lease exactly `telegram:<bot_id>` across all owner/chat settings for that bot; offset key exactly `telegram:<bot_id>:<owner_user_id>:<chat_id>`. Retry only transient/rate_limited transport errors. Document that separate databases need separate bots and changing owner/chat cannot recover already acknowledged Telegram updates.

## Verification and finish

Install dependencies only in your own worktree if needed. Node syntax, JSON scripts, Python compilation and safe config imports with DB/network blocked are authorized. Bot/core availability is checked after integration; report it rather than editing those files. No application tests, CLI/worker launches, network calls, migration, secrets, messages, production changes or deployments.

Commit only owned files and completion report with checks actually run, limits and blockers. Stop at committed handoff; the coordinator performs later merge/review/activation.
