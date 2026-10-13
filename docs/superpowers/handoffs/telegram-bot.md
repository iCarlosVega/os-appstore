# Session 2 — Telegram API, cards and controller

Branch: `telegram/bot`. Work only in its worktree, located in `docs/superpowers/completions/telegram-approvals-preparation.md`.

Read the Telegram spec/parallel plan dated 2026-10-12 and execute Task 2 using superpowers:executing-plans. Consume the review service exactly as frozen, though session 1's files will not exist in your baseline.

## Exclusive ownership

- New `backend/app/telegram_api.py`.
- New `backend/app/telegram_bot.py`.
- `docs/superpowers/completions/telegram-bot.md`.

Do not create/modify review core, migrations, config, launchers, worker, store/admin/models, frontend or dependencies. Do not add shared import stubs. Report interface issues to the coordinator.

## Deliverable

Fixed-origin httpx client with safe logging/errors; bounded owner-only private cards and inline review flow; required metadata selections without GitHub OAuth/web admin; callback parsing and draft version handling; bounded backlog/commands; replay-safe offset progression and terminal status recovery. Use the plan's exact client, render_review and run_once interfaces. Runtime passes owner/chat/app URL/environment/lease assertions; controller does not read Config.

Use frozen token/decimal parsing, render the supplied assessment, and implement every TelegramError.code classification. Unchanged edits and expired acknowledgements must not trap replay. Unavailable open cards use guarded `reset_delivery` for a bounded resend; completed publication stays final and offsets can progress.

## Verification and finish

Use your own dependencies, without copying root env/DB/token or sharing environments. Compile both modules; safe imports only where dependency graph is present. Core import availability is checked at integration—do not add fake core code. Review untrusted text, private sender/chat binding, URL logs, callback/message bounds and network-outside-transaction rules.

No application tests, real network/API requests, services, live messages, schema operations or candidate mutation. Record actual checks, unresolved dependencies and proposed behavioral cases; commit only owned code/report. Do not merge or deploy.
