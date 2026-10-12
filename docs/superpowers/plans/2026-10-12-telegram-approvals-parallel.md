# Telegram Approvals Parallel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans in your assigned session. Implement only your lane; do not spawn implementers for other lanes. Steps use checkbox syntax. The owner's no-application-tests policy overrides test-writing defaults until tests are explicitly requested.

**Goal:** Review and approve discovered candidates from a private, owner-only Telegram chat using the existing publication rules.

**Architecture:** Durable review drafts and polling offsets live in two additive Alembic tables. A transport/controller renders buttons and handles authenticated updates. A separate worker supplies configuration and a renewable poller lease; it does not run inside discovery/API.

**Tech Stack:** Python/FastAPI project, existing psycopg/sqlite adapters, Alembic, httpx, existing Node launchers. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-12-telegram-approvals-design.md`.

## Global constraints

- Local `develop` first. No production writes/deployments, actual bot creation/requests/messages, paid calls, publication, live schema changes or service starts during implementation sessions.
- Do not copy any ignored root env files, GitHub token, database or dependencies into worktrees. Existing root app/worker remain running and untouched.
- Preserve current approval validation, candidate revisions, manual metadata, SQLite/PostgreSQL compatibility, ordinary launchers, Discord and frontend behavior. No changes to discovery/search or automatic/bulk approval.
- Exact schema, configuration values, Telegram limits, callback format, seven-day review expiry and lease timing are in the spec and apply to every lane.
- No application tests unless requested. Syntax/import/configuration checks and code review are authorized; behavioral cases below are proposed, not permission to execute them.
- Own only the files below and your completion report. Report contract/shared-file issues to the coordinator; do not work around them by editing another lane or adding divergent stubs.

## Review focus

1. Unauthorized Telegram users/chats, malformed callbacks or repository text cannot cause candidate mutation or disclose private review data (bot + core).
2. Candidate refresh, draft edit, repeated click and concurrent web approval cannot publish stale information or publish twice (core).
3. Crashes between publication/offset persistence or message send/delivery persistence recover safely; card duplication must not duplicate publication (core + bot).
4. Inherited secrets, token-bearing HTTP logs, existing webhook and two pollers must fail safely without leaking credentials or silently consuming another bot's updates (bot + runtime).
5. Required-field selection works entirely in Telegram; unknown optional metadata stays intact, flagged NSFW remains blocked, and failure editing a success message never rolls back publication (core + bot).

## Worktree ownership and integration order

Resolve actual absolute paths and baseline SHA from `docs/superpowers/completions/telegram-approvals-preparation.md`, present in every worktree. Do not rebase onto moving `develop`.

| Session | Branch | Exclusive production files | Handoff |
| --- | --- | --- | --- |
| 1 | `telegram/review-core` | new `backend/app/telegram_review.py`; new `backend/alembic/versions/0002_telegram_reviews.py` | `docs/superpowers/handoffs/telegram-review-core.md` |
| 2 | `telegram/bot` | new `backend/app/telegram_api.py`; new `backend/app/telegram_bot.py` | `docs/superpowers/handoffs/telegram-bot.md` |
| 3 | `telegram/runtime` | new `backend/app/telegram_worker.py`; `backend/app/config.py`; `scripts/backend.mjs`; `scripts/local.mjs`; `package.json`; `.env.example`; `.env.development.example`; `README.md` | `docs/superpowers/handoffs/telegram-runtime.md` |

Each owns `docs/superpowers/completions/telegram-<lane>.md`, where lane is `review-core`, `bot` or `runtime`. Coordinator owns spec/plan/handoffs/preparation and later integration. Merge in table order onto a fresh `telegram/integration` branch from the frozen baseline.

Keep `store.py`, `admin.py`, `models.py`, `main.py`, `cli.py`, `jobs.py`, `discovery.py`, `discord.py`, migration helper/baseline, SQL, frontend and dependency/lockfiles unchanged. Report demonstrated shared blockers rather than changing these files.

## Frozen interfaces

Session 1 defines `ReviewView` as a TypedDict with exactly these keys:

```text
token: str; repo_id: str; candidate_revision: int; draft_version: int
status: str; expires_at: str; message_id: str | None; app_slug: str | None
data: dict  # current Metadata-shaped draft; preserves existing camelCase keys
options: dict  # categories: [{id: str, name: str}], types: [str], cost_models: [str]
confirmed: dict  # category, type, cost, safe: bool
```

Review service in `telegram_review.py`, no config/network dependency or import-time database work:

```python
prepare_reviews(*, owner_user_id: int, chat_id: int, limit: int = 5) -> list[ReviewView]
get_review(token: str, *, owner_user_id: int, chat_id: int) -> ReviewView
mark_delivered(token: str, message_id: int, *, owner_user_id: int, chat_id: int) -> None
apply_action(token: str, expected_version: int, action: str, value: str | None = None,
             *, owner_user_id: int, chat_id: int) -> dict
get_offset(poller_key: str) -> int  # zero when absent; next Telegram update ID to request
advance_offset(poller_key: str, next_update_id: int) -> None  # monotonic, never regress
```

- `prepare_reviews` expires/stales obsolete open drafts, creates new snapshots for eligible pending revisions, and returns at most `limit` unsent open reviews in oldest-candidate order. It can renew expired unchanged revisions with a new token; do not resend marked deliveries every iteration.
- Options are snapshots taken when review is created. Sort category options by `(name.lower(), id)`; types use `models.TYPES`; cost models exactly `['Free', 'Free with optional paid features']`. Category/type/cost values are decimal zero-based indices. `safe` accepts only `yes`; `approve` and `reject` require no value. No other actions. All confirmations begin false; each change increments draft version. A select action confirms that field even if the value already matched.
- `apply_action` returns `{'review': ReviewView, 'outcome': str, 'message': str}`. Outcomes: `updated`, `approved`, `rejected`, `already_done`, `stale`, `expired`, `blocked`. Invalid syntax/action/option, unknown token or wrong identity raises existing `models.InputError` with safe text. Known stale/expired/terminal review returns its outcome without mutating candidates. Final `approved` supplies the link slug through `review['app_slug']`.
- Existing `db.transaction` is nestable. Controller may wrap a service mutation to assert lease under the same writer lock. Each service also protects its standalone mutations. No Telegram I/O while locked.

Session 2 defines API transport in `telegram_api.py`:

```python
class TelegramError(RuntimeError):
    retry_after: int | None  # bounded 1..60 if provider asks for retry, otherwise None
class TelegramClient:
    def __init__(self, token: str): ...  # no network in constructor
    def call(self, method: str, payload: dict | None = None) -> object: ...
    def close(self) -> None: ...
```

`call` accepts only six methods from the spec, POST JSON to the fixed Telegram origin, and returns the validated `result` of an `ok:true` envelope; safe TelegramError for failures. Validate each method's required result shape in transport/controller before use. No root logger configuration at import; never expose URLs/raw provider errors. Runtime suppresses httpx/httpcore logging before first call. Transport must remain safe for ordinary callers too (use a client-specific redacting request logging strategy or establish safe logger behavior before any token-bearing request).

Controller in `telegram_bot.py`:

```python
render_review(review: ReviewView, *, app_url: str, environment: str) -> dict
# returns send/edit payload fields {'text': str, 'reply_markup': dict}; no chat/message IDs
run_once(client: TelegramClient, *, owner_user_id: int, chat_id: int,
         poller_key: str, app_url: str, environment: str,
         stop_event: threading.Event, assert_active: Callable[[], None],
         poll_timeout: int = 20) -> dict
# returns non-secret counts {'updates': int, 'sent': int}
```

`run_once` sends at most five unsent cards, polls at most 20 updates using saved next-ID offset, validates sender/chat/private context, processes supported commands/callbacks, answers callbacks promptly and edits the message with the returned current review. Stop early on stop/lease loss. Call `assert_active` before external calls and inside DB transactions before mutations/offset writes. Advance offsets only after completed/ignored updates. Malformed authorized input gets safe feedback and no candidate mutation. Failed delivery/API calls raise safe TelegramError; do not advance past an unprocessed update. `/pending` uses the same per-iteration send budget, not an additional unbounded batch. Use text with no parse mode (or correctly escape every untrusted field), plain HTTPS repository URL buttons and bounded/truncated message text within 4096 characters. Link terminal approvals to the configured environment's app URL.

Session 3 adds exact Config attributes from the spec and `telegram_worker.main() -> None`, with module `__main__` guard. Startup order: validate explicit enable/token/IDs; verify required schema using read-only queries (safe actionable migration error); create client; `getMe` to verify numeric bot ID; `getWebhookInfo` and refuse nonempty webhook URL; acquire lease; process loop. No bot requests on safe module import. No schema initialization or destructive webhook calls.

## Task 1 — Review core and additive persistence

**Consumes:** existing Metadata/store/db contracts. **Produces:** service/ReviewView and migration above. **Files:** session 1 ownership row.

- [ ] Read spec/plan/handoff, existing publication/rejection and web confirmation code, JSON encoding, nested transaction lock and Alembic helper.
- [ ] Add revision `0002_telegram_reviews` with exactly the two tables/index and refusal downgrade from the spec. Compile migration definitions for both dialects without connecting; preserve baseline and existing rows.
- [ ] Implement review creation, binding, snapshots/options, expiry/renewal and delivery recording. Serialize open-draft creation through existing writer lock. Generate callback-safe random tokens; validate positive IDs, limits and message IDs.
- [ ] Implement typed field actions and explicit confirmations. Version increments and candidate checks must protect each mutation, not only final approve. Preserve unedited metadata/unknown fields and add changed owner selections to overrides.
- [ ] Implement final approval/rejection and terminal/stale/blocked outcomes. Call existing store functions inside the shared transaction; include Telegram audit identity, repo/revision/token and outcome without credentials/payload dumps. A stale draft version cannot reuse earlier final confirmation.
- [ ] Implement scoped monotonic polling offset storage without token persistence. Inspect transaction boundaries and all replay paths.
- [ ] Run `backend/.venv/bin/python -m compileall -q backend/app/telegram_review.py backend/alembic/versions/0002_telegram_reviews.py`; safe-import with DB connection calls blocked. Expected: exit zero/no connections. No migrations/tests.
- [ ] Write completion report with exact owned changes/checks/limits/shared blockers; commit only owned files.

**Behavioral cases requiring authorization:** fresh/upgraded SQLite/PostgreSQL schema with rows unchanged; required flags; wrong actor/chat/token; stale candidate/draft; changed/deleted category; expired renewal; duplicate/concurrent web+Telegram approval; rollback of publication/audit/review; rejection replay; offset regression; two concurrent review preparers.

## Task 2 — Telegram transport, cards and controller

**Consumes:** frozen review-service signatures, config passed as arguments. **Produces:** transport/controller contracts above. **Files:** session 2 ownership row.

- [ ] Read spec/plan/handoff and current candidate/store data. Implement against frozen interfaces; do not create the missing core module or edit runtime/config.
- [ ] Build fixed-origin bounded httpx transport, envelope/result validation, retry-after handling, safe token/redacted logging and close behavior. Validate token before building its URL. Never print HTTP exceptions or raw responses. No network on imports/construction.
- [ ] Implement bounded card rendering, environment label, repository link, required-field selection buttons, explicit final summary/confirmation, reject and terminal states. Keep every callback UTF-8 payload <=64 bytes, regardless of source text/long category IDs; use snapshot indices.
- [ ] Implement owner+private-chat verification before review access or callbacks. Unknown/unauthorized input cannot enroll users or send them candidate details. Parse every update defensively; callback messages can be inaccessible or missing.
- [ ] Implement bounded backlog delivery, the three commands, callbacks, delivery recording and saved offsets. Assert lease before requests and under DB lock before service mutations. Preserve replay safety and terminal-message recovery on edit failures; never hold a transaction across API I/O.
- [ ] Run Python compile check; safe-import transport/controller once core is available only during integration. In the lane, controller's unresolved core import is an expected dependency, not permission to add a substitute. Review API bodies/payload limits and use offline parsing/configuration inspection only; no fake behavioral tests or real Telegram calls.
- [ ] Write completion report/checks/limits/shared blockers; commit only owned files.

**Behavioral cases requiring authorization:** unauthorized user/chat/group, spoofed callback identity, oversized/invalid updates, 64-byte payload and 4096-character card bounds, changed/expired draft, repeated update, transient send/edit/ack failure, crash after publish/before offset or send/before delivery record, API429/retry-after and missing/inaccessible message.

## Task 3 — Opt-in worker, isolation and operating instructions

**Consumes:** bot/client contracts. **Produces:** Config values, separate worker and four npm commands. **Files:** session 3 ownership row.

- [ ] Read spec/plan/handoff, local dotenv precedence, existing launchers and schema/startup policy. Do not modify root private env or start services.
- [ ] Add the four opt-in/blank Telegram variables and Config attributes. In Node/Python explicit local mode, pin all to local-file values or disabled/blank so shell/Next fallbacks cannot activate the bot or import a production token. Add placeholders to tracked examples; never a real token/ID.
- [ ] Implement argument parsing/strict configuration validation before DB/network work. Check migration state without initialize/migrate. Suppress token-bearing HTTP logging before client use, handle errors without secret traceback output, verify bot identity/webhook and derive poller key.
- [ ] Add guarded 90-second lease acquisition, 20-second heartbeat, owner assertion, lost-lease shutdown, interruptible API backoff and signal cleanup. `--once` runs one controller iteration with `poll_timeout=0`; a normal loop calls `run_once` until stopped. Release only your lease; close client in finally. Other discovery/API workers remain independent.
- [ ] Route `scripts/backend.mjs telegram [--once]` to `app.telegram_worker`, add local wrapper subcommand and four npm scripts exactly as specified. Preserve all existing commands/flags; missing integrated bot/core resources must fail clearly.
- [ ] Document BotFather setup, private owner/chat ID configuration without first-user trust, local/production separate bots, migration/start order, backlog, required-field flow, replay/delivery limits, stop/restart and no GitHub OAuth requirement. No bot setup through real API or deployment.
- [ ] Run Node syntax, package JSON script checks, Python compilation and safe config imports with DB/network blocked. Runtime module can compile before other lanes exist; unresolved bot imports at lane completion are reported and resolved by integration. No CLI launches/worker/services/tests.
- [ ] Write completion report/checks/limits/shared blockers; commit only owned files.

**Behavioral cases requiring authorization:** disabled/missing/malformed config makes zero DB/network calls; hostile inherited Telegram variables; missing migration; existing webhook refusal; double poller; lost lease/signal/network-backoff shutdown; restart resumes offset; normal API/jobs unaffected; local and production cannot accidentally share a consumer.

## Coordinator integration and activation

- [ ] Review lane reports and ownership, merge review-core → bot → runtime on isolated `telegram/integration` from recorded baseline, then perform a fresh whole-branch security/code review.
- [ ] Install only existing pinned dependencies in integration's own environments. Compile/safe-import combined modules with network/DB blocked, check configuration isolation/commands and migration DDL; typecheck/build only if connected changes justify it. Record missing behavioral evidence explicitly.
- [ ] Obtain explicit authorization for the proposed disposable behavioral checks before activation; no live candidate publication or Telegram messaging is implied by plan preparation or static checks.
- [ ] After acceptance, land on `develop`, back up local database, migrate, configure a separate local bot privately, start the separate Telegram worker and review its first real card with the owner. Production setup/deployment stays separately authorized. Keep implementation worktrees until integration is accepted.

## Session launch

Open the assigned worktree and paste:

> Read `docs/superpowers/specs/2026-10-12-telegram-approvals-design.md`, `docs/superpowers/plans/2026-10-12-telegram-approvals-parallel.md`, `docs/superpowers/completions/telegram-approvals-preparation.md`, and `docs/superpowers/handoffs/telegram-<lane>.md`. Implement only your lane using superpowers:executing-plans. Preserve exclusive ownership and frozen interfaces. Follow the no-application-tests policy; no service starts, network requests, migrations, credentials, production changes, messages or publication. Commit owned files and your completion report. Report shared blockers; do not merge or deploy.

Replace `<lane>` with `review-core`, `bot` or `runtime`.
