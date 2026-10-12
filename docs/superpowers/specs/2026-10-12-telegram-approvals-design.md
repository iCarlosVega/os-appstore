# Telegram candidate approvals

Status: implementation preparation requested by the owner; three independent Codex sessions will implement the feature. This preparation creates documentation and worktrees only.

## Outcome and scope

The owner reviews discovered candidates in a private Telegram chat, selects required listing facts, and explicitly approves or rejects each candidate. Approval publishes through the existing store transaction/validation logic. GitHub OAuth is not required for Telegram review. Existing web administration and Discord delivery keep working.

Start on local `develop`; production deployment and bot activation are later steps. Local and production must use separate bot tokens to avoid competing update consumers or approving into the wrong database. Every review card names its environment and links to its repository. No automatic approval, bulk approval, new discovery sources, AI enrichment, arbitrary chat commands, webhooks, frontend changes or Telegram Mini App are part of this version.

## User flow

1. An explicitly enabled, separate Telegram worker scans pending candidates, including the existing backlog. It sends at most five new cards per iteration to the configured private chat.
2. Each card shows name, description, repository, license, known platforms (or unknown), activity, selected category/type/free-use status, NSFW/uncertainty flags and environment. Repository content is displayed as untrusted text, never executed or interpreted as commands.
3. Inline buttons let the owner select one category, software type and cost model; confirm non-NSFW content; review the current summary; explicitly publish; or reject. Keep the flow entirely within Telegram for required fields. Unknown optional fields remain unknown, rather than being invented. Category, type and cost selections require explicit confirmation even when already suggested by discovery.
4. A final confirmation names the exact snapshot/choices to be published. It carries the current draft version, so editing a draft invalidates an older confirmation. Known NSFW candidates remain blocked in this version; the bot must not silently clear a flag.
5. Success updates the message with its final status and app link, removing action buttons. Already completed, changed, expired or otherwise unavailable reviews give a useful result without a second publication. Repeated callbacks are safe.
6. `/start`, `/help` and `/pending` are the only supported commands, only for the configured owner in the configured private chat. `/pending` requests bounded delivery of unsent/current reviews; it does not create duplicate active cards. No first-user enrollment or automatic trust of whoever sends `/start`.

## Authorization and consistency

- Require both exact numeric owner user ID and exact private chat ID on every command/callback. Use Telegram's `from.id`, `message.chat.id`, private chat type and authenticated Bot API updates; never trust usernames or callback-supplied identity. Ignore unauthorized updates without replying or changing candidates/reviews; advancing the poll offset is allowed.
- Review records bind an opaque random token to candidate repo ID/revision, owner/chat, immutable original metadata and assessment, draft, fixed option lists, explicit confirmations and expiry. Generate tokens with `secrets.token_urlsafe(16)`: exactly 22 ASCII characters matching `[A-Za-z0-9_-]{22}` (128 random bits). A token cannot substitute for owner authorization.
- Callback payloads stay within Telegram's 64-byte limit. Use `tg:<token>:<draft_version>:<action>[:<value>]`, where choices are short indices into stored options, never repository names/URLs/full category IDs. Version is canonical positive decimal, maximum 2147483647; option indices are canonical nonnegative decimal with the same maximum. Reject leading zeros except index `0`. Actions are exactly `category`, `type`, `cost`, `safe`, `approve`, `reject`; `safe` value is `yes`, final actions have no value. Validate the entire payload before mutation; refuse version overflow rather than wrapping.
- Every change rechecks candidate status and revision under `db.transaction()`. A refreshed/rejected/approved candidate invalidates the old review. Review expiry is seven days from creation. Terminal/expired reviews can be replaced by a fresh token for the same still-pending candidate.
- Final publish requires explicit category/type/cost/safe confirmations, a valid category, `Free` or `Free with optional paid features`, and non-NSFW metadata. Reuse `store.approve_candidate(repo_id, revision, Metadata)` and `store.reject_candidate(repo_id, revision)`; do not implement a second app-insertion path or weaken existing validation. Preserve untouched metadata and manual overrides; record owner-chosen changed fields as overrides.
- Store domain changes, terminal review state and a Telegram-specific audit entry in the same transaction as publication/rejection. Duplicate final callbacks return the existing outcome. No Telegram network requests inside database transactions.

## Persistence and migration

Add Alembic revision `0002_telegram_reviews`, down revision `0001_initial`. Never modify the immutable baseline, legacy SQL or migration helper.

- `telegram_reviews`: `token TEXT PRIMARY KEY NOT NULL`, `repo_id TEXT NOT NULL`, `candidate_revision INTEGER NOT NULL`, `draft_version INTEGER NOT NULL`, `owner_user_id TEXT NOT NULL`, `chat_id TEXT NOT NULL`, `status TEXT NOT NULL`, `snapshot TEXT NOT NULL`, `assessment TEXT NOT NULL`, `draft TEXT NOT NULL`, `options TEXT NOT NULL`, `confirmed TEXT NOT NULL`, `created_at TEXT NOT NULL`, `expires_at TEXT NOT NULL`, `message_id TEXT NULL`, `app_slug TEXT NULL`. JSON stays TEXT and timestamps use existing store UTC formatting. `assessment` snapshots the candidate's assessment object unchanged (empty object if absent); it supplies uncertainty/evidence flags without inventing facts or independent controller queries. ID strings avoid integer-width surprises across SQLite/PostgreSQL. Statuses: `open`, `approved`, `rejected`, `stale`, `expired`. Add ordinary index `telegram_reviews_lookup` on `(repo_id,candidate_revision,owner_user_id,chat_id,status)`.
- `telegram_state`: `id TEXT PRIMARY KEY NOT NULL`, `data TEXT NOT NULL`; holds polling offsets keyed by verified bot ID + owner + chat. Never persist the bot token. Use existing `leases` for poller ownership; no third table is needed.
- Under the existing global writer transaction lock, ensure at most one open review per candidate revision/owner/chat. Keep terminal records for audit; do not add a uniqueness rule that prevents renewing an expired unchanged candidate.
- Migration adds only these tables/index. Existing rows are preserved. Downgrade refuses destructive removal and explains disabling the feature and restoring a backup instead. New worker requires the explicit migration; it never calls initialize/migrate itself.

## Telegram API and delivery

Use installed httpx and the official HTTPS Bot API, no new dependencies. Fixed origin `https://api.telegram.org`, validated token path, allowlisted methods, redirects disabled, proxies from inherited environment disabled, bounded responses (1 MiB), bounded inputs and safe errors. Never log the token-bearing URL, headers, raw exceptions or complete update payloads. Telegram worker suppresses httpx/httpcore request logging.

Use `getMe`, `getWebhookInfo`, `getUpdates`, `sendMessage`, `editMessageText`, and `answerCallbackQuery`. Refuse an existing webhook with an actionable message; do not remove it or drop updates automatically. Poll batches of at most 20 updates with timeout 20 seconds (zero for `--once`); HTTP timeout 30 seconds. Handle HTTP/API errors and retry-after safely with bounded, interruptible backoff.

Persist offset monotonically only after the update has been processed or deliberately ignored. Publication cannot be repeated if a crash happens before offset acknowledgement. A single renewable database lease prevents competing consumers; check lease ownership before external work and within mutation transactions. On lost lease, stop processing. Runtime owns lease lifecycle; controller consumes an assertion callback.

Notification delivery is at least once: a crash after send succeeds but before message ID is persisted can duplicate a card. Both cards refer to the same review token/version; approval remains idempotent. Document this limit. A failed message edit after publication never undoes publication; replay can render the terminal result again.

Transport classifies safe errors as `transient`, `rate_limited`, `not_modified`, `callback_expired`, `message_unavailable`, or `permanent`. An unchanged edit counts as synchronized. Expired/invalid callback acknowledgements are nonfatal. For an unavailable/uneditable message after a durable action, advance the offset; for an open review, atomically clear its matching delivery ID so bounded backlog delivery can resend the current card. Terminal reviews need no resend. Network/429/5xx failures remain retryable and cannot skip an unprocessed domain action. Other permanent failures (including invalid bot credentials) exit safely with actionable text rather than retry forever. Never expose raw provider descriptions.

## Runtime and configuration

Separate process: `python -m app.telegram_worker [--once]` from backend, also importable/run as `backend.app.telegram_worker` from repo root. It must not block discovery, API or the existing jobs loop. Disabled/missing config exits with actionable text before network/database work.

Variables: `TELEGRAM_ENABLED=0`, `TELEGRAM_BOT_TOKEN=`, `TELEGRAM_OWNER_USER_ID=`, `TELEGRAM_CHAT_ID=`. Explicit enable requires exactly `1`, a bot token, and positive decimal IDs within Telegram's documented safe integer range. Private chat only. Normal config adds `telegram_enabled`, `telegram_bot_token`, `telegram_owner_user_id`, `telegram_chat_id`; IDs stay strings until validated by the worker. Explicit local mode pins all four to local-file values or disabled/blank, overriding shell/Next fallback configuration. Update examples, not real env files.

Commands: `npm run telegram`, `npm run telegram:once`, `npm run local:telegram`, `npm run local:telegram:once`. Use existing launchers; `scripts/backend.mjs telegram` selects module `app.telegram_worker`, all other commands retain current behavior. `scripts/local.mjs telegram [--once]` uses the same guarded local environment as other local commands.

Lease ID `telegram:<bot_id>`, owner random UUID; 90-second expiry, heartbeat every 20 seconds. Telegram has one update stream per bot, so the lease must cover all owner/chat configurations for that bot. Offset state remains scoped to bot + owner + chat. Graceful SIGINT/SIGTERM stops polling and releases only its own lease. Duplicate poller fails clearly. Separate bots for local/production are still required: a local database lease cannot coordinate two different databases. Changing the configured owner/chat requires stopping the previous consumer; Telegram may already have acknowledged older updates, so offset state is not a recoverable per-user inbox.

## Delivery and verification boundaries

Three lanes own review persistence/domain, Telegram API/controller, and configuration/runtime/docs. The parallel plan freezes signatures and exclusive files. All start from one recorded planning baseline and install dependencies only in their own worktree if needed. No env/credentials/database copies, symlinked dependencies, production changes, bot creation, messages, live migrations or running services during lane implementation.

Existing owner policy remains: no application tests unless requested. Lane gates are syntax, safe import/configuration checks and code review, with behavioral cases listed separately. Approval is security-sensitive; activation must wait for explicit authorization of disposable behavioral checks covering owner authorization, stale/duplicate callbacks, transaction rollback and restart recovery. Successful compilation is not behavioral proof. Creating this plan/worktrees does not authorize publishing candidates or sending Telegram messages.

References: [Telegram inline keyboards](https://core.telegram.org/bots/api#inlinekeyboardmarkup), [callback queries](https://core.telegram.org/bots/api#callbackquery), [polling](https://core.telegram.org/bots/api#getupdates), [BotFather](https://core.telegram.org/bots/features#botfather).
