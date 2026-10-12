# Free Software Store

An anonymous software directory with owner-approved GitHub discovery. **FastAPI + Uvicorn + Pydantic** run the backend; **Next.js + TypeScript** run the frontend. The UI follows the compact directory layout of [shadcndirectory.com](https://www.shadcndirectory.com/).

## Project structure

```text
backend/
  app/main.py          FastAPI routes, startup, request limits, error responses
  app/models.py        Pydantic validation and persisted metadata/settings
  app/db.py            SQLite/PostgreSQL connections and transactions
  app/store.py         Catalog persistence, revisions, publication rules
  app/auth.py          GitHub owner sessions, origin guards, request limits
  app/admin.py         Owner approvals, edits, requests, controls, and costs
  app/search.py        Catalog matching, alternatives, Jev ranking/cache
  app/github.py        GitHub metadata/release/README adapter
  app/jev.py           Validated TypeSafe decisions
  app/budget.py        Atomic spending reservations and pause controls
  app/jobs.py          Durable worker scheduling, leases, and checkpoints
  app/discovery.py     Private app proposals
  app/maintenance.py   Metadata refresh and source-change proposals
  app/discord.py       Owner notifications
  app/backup.py        Database snapshots and retention
  app/cli.py           Migrate, worker, and backup commands
  app/telegram_worker.py  Separate opt-in Telegram poller and bot-scoped lease
  app/telegram_bot.py     Owner-only review cards and update controller
  app/telegram_api.py     Bounded Telegram Bot API transport
  app/telegram_review.py  Durable review drafts, actions and polling offsets
  requirements.txt
  Dockerfile
src/app/               Next.js pages and administration UI
src/app/api/[...path]/  Same-origin HTTP proxy to FastAPI
src/components/        Directory, listing forms, download options
src/lib/backend.ts     Server-side HTTP client; no database/provider logic
migrations/            Shared database schema
```

Next.js does not read the database, execute jobs, or call Jev. It fetches public GitHub READMEs for listing display; FastAPI handles repository discovery/metadata, validates incoming data with Pydantic, and owns all writes and authorization. The proxy preserves `/api/*` URLs and owner cookies on the frontend origin, so public accounts and cross-origin browser calls are unnecessary.

## Run locally

Prerequisites: **Python 3.12+** (3.14 recommended), **Node 24 LTS**, and npm.

```sh
npm ci
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
cp .env.example .env
npm run db:migrate
npm run dev
```

If `.env` already exists, keep it and add the new `BACKEND_URL`/optional proxy setting rather than overwriting credentials. On Windows, the virtual environment interpreter is `backend/.venv/Scripts/python.exe`.

`npm run dev` starts **both** Uvicorn (port 8000) and Next.js (port 3000), with reload enabled. Ctrl+C stops both. The backend uses `.data/store.sqlite` by default; the existing database is preserved. There is no Node SQLite dependency or experimental Node SQLite warning.

- Store: **http://localhost:3000**
- FastAPI Swagger documentation: **http://localhost:8000/docs**
- Backend health: **http://localhost:8000/api/health**

Run individual services if preferred:

```sh
npm run dev:api
npm run dev:web
```

Equivalent Uvicorn command from the repository root:

```sh
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

Use `PYTHON` to select a different interpreter, and `API_PORT`/`API_HOST` to change the development API listener. If changing ports, update `BACKEND_URL`; update `APP_URL` and OAuth callback when changing the browser origin. Production web and API are started separately.

The launchers load the root `.env` and preserve explicit shell overrides. Relative `SQLITE_PATH` and `BACKUP_DIR` values resolve against the repository root for both the API and worker.

### Isolated local PostgreSQL and catalog snapshot

Use the dedicated `local:*` commands to develop against PostgreSQL without changing the existing SQLite file or targeting Railway. This workflow requires the migration, catalog-import and runtime lanes to be integrated first. Commands report missing migration/import resources rather than substituting another implementation.

Install dependencies **in this worktree**, then create the local configuration:

```sh
npm ci
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
npm run local:setup
```

The isolated local launcher requires a POSIX host such as macOS or Linux; it refuses Windows because the existing launchers cannot reliably stop descendant processes there. The original non-local workflow remains available on Windows. Setup creates a git-ignored `.env.development.local` with a random URL-safe password and owner-only permissions. It never overwrites an existing file. Keep that file with the persistent database: changing its password does not change a password already stored in a PostgreSQL volume. `.env.development.example` documents the settings; do not copy production credentials into it or the local file.

Start a local Docker engine with Compose v2 or later, and stop any API/frontend already occupying ports 8000/3000 explicitly before switching. The wrapper does not stop existing services. Then:

```sh
npm run local:db:up
npm run local:db:migrate
npm run local:catalog:import
# Review the preview counts, then explicitly insert the snapshot:
npm run local:catalog:import -- --apply
npm run local:dev
```

In another terminal in the same worktree:

```sh
npm run local:jobs
# Or process due work once:
npm run local:jobs -- --once
```

`local:dev` runs Next.js and Uvicorn with reload at `http://localhost:3000` and `http://127.0.0.1:8000`; both listeners bind to loopback. The worker is separate and requires an explicit restart after code/config changes. API startup does not migrate PostgreSQL: run `local:db:migrate` before starting services and again after integrating schema changes. Schema migration and catalog import are separate operations; the importer never initializes the database.

`compose.local.yaml` contains only PostgreSQL 17 (`postgres:17-bookworm`). It uses project `os-appstore-local`, persistent volume `os-appstore-local_database`, database `os_appstore_development`, and host port **127.0.0.1:55432**. Production `compose.yaml` is separate. The wrapper requires a local Unix Docker socket, waits for database health on startup, and refuses occupied ports. Concurrent worktrees share these fixed local ports/project, so run only one integrated local stack at a time.

All local commands except setup read only `.env.development.local`. Its values take precedence over inherited shell application settings. The wrapper forces development mode, the endpoints above, worktree-local Python/SQLite paths and `.data/local-postgres/backups`. `DATABASE_URL` must be exactly `postgresql://store:PASSWORD@127.0.0.1:55432/os_appstore_development`, with a matching URL-safe `POSTGRES_PASSWORD`; alternate hosts, ports, databases, socket/service/multihost URLs and query overrides are rejected before launching anything. Inherited `PG*` connection overrides are removed. No URL or password is printed in wrapper errors.

Node launchers skip `.env` in local mode. Python requires an absolute `STORE_ENV_FILE`, loads only that file without interpolation, validates the dedicated destination, and pins application settings. GitHub OAuth/owner/auth/token, TypeSafe, Discord and proxy credentials default to explicit empty strings unless set in the local file. Telegram defaults to `TELEGRAM_ENABLED=0` and blank token/owner/chat, even if shell or fallback env files contain Telegram credentials. The default model is explicitly `jev-1.13.0`. Next.js may inspect its usual fallback env files, but these application values already exist in its process environment and cannot be replaced. Ordinary non-local commands retain their previous loading behavior; use `local:*` consistently for this stack.

Local owner administration requires a separate GitHub OAuth app with callback `http://localhost:3000/api/auth/callback`, plus explicitly configured local owner ID/auth secret. Discovery needs a local GitHub token. Paid AI starts disabled in database settings; a key alone does not enable it. Notifications need an explicitly configured webhook. Enabling these integrations can make external calls; blank defaults keep them unconfigured.

The catalog importer defaults to a preview using only public `GET /api/catalog` and `/api/categories` from `https://os-appstore.vercel.app`. `--apply` inserts missing apps/categories in one transaction. Repeated imports skip matching app identities even after local edits/unpublication, preserve existing category definitions and local counters, and reject conflicting identities/categories rather than overwrite them. Imported click counts start at zero; private production records/settings are not copied. If the two public responses are inconsistent, retry the preview later. An alternative HTTPS origin can be supplied with `-- --source-url https://example.com`; the importer validates it. This is a snapshot, not ongoing synchronization, and does not write to production.

Ctrl+C stops the foreground dev process or worker; stop both separately before shutting down the database. Database logs and shutdown:

```sh
docker compose --env-file .env.development.local -p os-appstore-local -f compose.local.yaml logs -f db
npm run local:db:down
```

`local:db:down` keeps the database volume; the next `local:db:up` reuses it. Do not add `-v` or remove volumes if you need the records. With the integrated backend and PostgreSQL 17 client tools (`pg_dump`/`pg_restore`) installed locally, create a backup using the same guarded Python configuration:

```sh
STORE_LOCAL=1 STORE_ENV_FILE="$PWD/.env.development.local" backend/.venv/bin/python -m backend.app.cli backup
```

The worker also schedules backups under `.data/local-postgres/backups`. Stop API/worker before recovery, preserve the volume and local env, and follow the backup/restore instructions below. Review migration failures before retrying: never blindly stamp an incompatible schema or drop populated tables to make migration succeed. Restore into a separate empty recovery database and review it before switching; ordinary local commands deliberately reject other destinations. The previous `.data/store.sqlite` and root `.env` remain available for the original non-local workflow.

### Background worker

In another terminal:

```sh
npm run jobs
```

The worker checks due/queued jobs every 30 seconds. `npm run jobs:once` processes currently due work and exits. `npm run backup` creates a database snapshot. These commands launch Python; Uvicorn serves HTTP only and does not run the scheduler in an API process.

Direct CLI from `backend/`: `.venv/bin/python -m app.cli migrate`, `worker`, `worker --once`, or `backup`.

## Features

- Category trees and platform/type/feature filters; local matching, typo tolerance, aliases, alternatives, related suggestions, and optional bounded Jev ranking.
- Listings credit creators and show requirements, latest known stable version, platforms, x86-64/ARM64, setup, license, official links, sources, and download-button clicks. Unknown facts remain unknown.
- Downloads open the approved GitHub repository. A dropdown copies an installation prompt. No files are hosted or installed, and no security scanning or certification is claimed. Download at your own risk.
- Anonymous app requests, single-owner GitHub OAuth, private discovery proposals, revision-aware publication, edits, manual overrides, unpublishing, category/seed management, and emergency controls.
- Nightly discovery, star history/growth signals, weekly refresh, daily priority refresh, material-source-change approval, Discord reporting, and explicit failed-job resumption.
- $20 monthly operating target, atomic Jev reservations, conservative timeout/malformed-response accounting, and daily backups retaining seven snapshots.

The catalog starts empty. All new additions require owner approval; no fake listings or click counts are supplied. NSFW listings cannot be published. For rewritten/decompiled games, the owner must document required original assets and setup rather than assuming the repository is a standalone playable game.

## Owner and integrations

Configure these **on FastAPI and the worker**, never with a `NEXT_PUBLIC_` prefix:

1. Register a [GitHub OAuth application](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app) with callback **`APP_URL/api/auth/callback`**. Keep this callback on the frontend/proxy origin. Set `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, your numeric `OWNER_GITHUB_ID`, and a random `AUTH_SECRET` of at least 32 characters. Generate secrets with `openssl rand -hex 32`. Only that GitHub account can administer the store; no development bypass is provided.
2. Set `GITHUB_TOKEN` with least-privilege access to public repository search, READMEs, releases, and metadata. No write permission is needed; private repositories are excluded.
3. Set `TYPESAFE_API_KEY` for [TypeSafe Jev](https://docs.typesafe.ai/api). Jev evaluates catalog facts; GitHub discovers repositories. Visitor search does not crawl the web. Configure its current input price and a hosting allowance in Administration → Costs, then explicitly enable AI in Settings. It starts disabled.
4. Set a private `DISCORD_WEBHOOK_URL`. Digests, failures, and budget alerts disable mentions. Missing configuration queues notifications; failed deliveries can be retried in Operations. Respond by reviewing/resuming in the dashboard; there is no Discord conversational bot.
5. Set the Buy Me a Coffee URL in Settings. The public About page describes operating costs and Wikimedia Foundation support. The app does not transfer or split donations automatically.

Next.js needs only **`BACKEND_URL`** and, in production, the shared **`BACKEND_PROXY_SECRET`**. Generate a separate proxy secret of at least 32 characters and configure it on both services to authenticate forwarded client-IP headers. It does not grant owner access. The backend ignores forwarded IPs without this secret. Your trusted frontend ingress must replace client-supplied forwarded-IP headers. Put public services behind HTTPS.

### First collection

Sign in at `/admin`, add official GitHub repository URLs under Settings → Seeds, run the worker, and queue Discovery in Operations. Review Candidates, verify free-use eligibility and licensing, select categories/platforms, record setup/requirements, explicitly confirm the selected software type and non-NSFW content, and approve the reviewed revision. The type confirmation is required on listing edits too; a discovered candidate's initial type is not verified evidence.

Owner corrections made during initial approval or later editing are preserved as manual overrides. Repository identity, URL, license, and supplied cost/category changes become private proposals. Review shows current and proposed eligibility/categories, and approval requires both the proposal and listing revisions to match. Missing cost/category evidence in legacy proposals keeps approved values. The current GitHub adapter does not supply cost/category change evidence; its unknown defaults cannot erase approved values. Replacement repositories cannot supply new public metadata before identity approval. Rejected repository IDs remain suppressed until explicitly reopened. Missing repositories keep the approved destination with an availability warning; inactive projects are downranked. Descriptions remain upstream or owner-authored.

### Telegram candidate approvals

Telegram review runs in its own process, independently of the API and discovery/jobs worker. GitHub OAuth is not required for Telegram review; web administration still uses GitHub OAuth. Discovery still needs its existing configuration. Telegram never automatically approves candidates.

Integrate the review-core, bot and runtime lanes before starting. Activation requires the owner's separate authorization for disposable behavioral checks of authorization, stale/duplicate callbacks, transaction rollback and restart recovery. Syntax/import checks alone do not establish that approval is safe. These instructions describe later operation; implementation does not create a bot, contact Telegram, migrate a database or publish candidates.

Create a dedicated local bot through the official [BotFather](https://core.telegram.org/bots/features#botfather) `/newbot` flow and store its token privately. Use a different bot/token for each database, including local and production. Never commit tokens, use a `NEXT_PUBLIC_` setting, or put token-bearing request URLs in logs, shell history or screenshots. Configure these four values in `.env.development.local` for `local:*`, or in the ordinary backend environment for non-local operation:

```dotenv
TELEGRAM_ENABLED=0
TELEGRAM_BOT_TOKEN=
TELEGRAM_OWNER_USER_ID=
TELEGRAM_CHAT_ID=
```

Keep the worker stopped while identifying the owner/chat. In Telegram, open a **private** conversation with your own bot and send `/start`. Inspect the authenticated Bot API `getUpdates` result using a trusted local client that keeps the token and full response private. Take the owner's numeric `message.from.id` and `message.chat.id`, verify `message.chat.type` is `private`, and verify that update came from your own account. Do not run a second update consumer while the worker is active. Usernames, group/channel IDs and whoever happens to send the first `/start` never establish trust. Both configured IDs must be canonical positive decimals (no whitespace, signs or leading zeros), at most `4503599627370495`; the worker requires both exact IDs on incoming commands/callbacks.

Back up the intended database, then explicitly migrate it with the integrated release **before** enabling Telegram. For the isolated local workflow, after installing this worktree's dependencies and running `local:setup`:

```sh
npm run local:db:up
npm run local:db:migrate
# Privately fill the local bot token and owner/chat IDs, then set TELEGRAM_ENABLED=1.
npm run local:telegram
```

For the ordinary environment, use `npm run db:migrate`, configure the intended database and frontend `APP_URL`, set the four Telegram values with `TELEGRAM_ENABLED=1`, then run `npm run telegram`. Only exactly `1` enables the worker. An absent/disabled flag or missing/malformed credentials exits before DB/network access. Local Node and Python loaders pin all four Telegram values to the local file or disabled/blank defaults; inherited shell credentials and Next.js fallback env files cannot enable local Telegram. Existing local env files are not overwritten by `local:setup`; add the four values privately if your file predates them.

| Command | Behavior |
| --- | --- |
| `npm run telegram` | Ordinary environment, continuous polling |
| `npm run telegram:once` | Ordinary environment, one iteration with zero-second poll timeout |
| `npm run local:telegram` | Guarded local environment, continuous polling |
| `npm run local:telegram:once` | Guarded local environment, one iteration with zero-second poll timeout |

Direct equivalents are `python -m app.telegram_worker [--once]` from `backend/` using its venv, or `backend/.venv/bin/python -m backend.app.telegram_worker [--once]` from the repository root. Direct local invocation also requires `STORE_LOCAL=1` and an absolute `STORE_ENV_FILE` pointing at this worktree's local file. `--once` may send real cards and process real approvals; it is not a dry run. API and discovery startup never starts Telegram. The existing Docker Compose definitions do not start this additional process; a future production deployment must explicitly provision a separate Telegram worker with its own production bot, database and `APP_URL`.

Startup checks schema revision `0002_telegram_reviews`, required tables and initialized settings with read-only queries; it never initializes/migrates schema, and SQLite readiness cannot create a missing file. It verifies the bot with `getMe`, checks `getWebhookInfo`, and refuses a configured webhook with instructions to review/remove it deliberately. The worker never deletes webhooks or drops pending updates automatically. Missing lane modules/dependencies fail with an integration message.

Pending candidates, including the backlog, are delivered at most five new cards per iteration. Only the configured private owner/chat can use `/start`, `/help` and `/pending`; `/pending` uses the same bounded delivery budget. Each card names its environment and repository and shows listing facts, activity, unknown fields and assessment flags. Explicitly select a category, software type and free-use cost model, confirm non-NSFW content, review the current summary, then publish that exact draft or reject it. Suggestions require confirmation too. Only `Free` and `Free with optional paid features` qualify; known NSFW candidates remain blocked. Unknown optional facts are preserved. Reviews expire after seven days; refreshed candidates, edited drafts and stale confirmation buttons cannot publish an earlier snapshot. Approval uses the existing store validation/transaction and preserves manual overrides.

One renewable database lease, **`telegram:<bot_id>`**, covers every owner/chat configuration for that bot. It expires after 90 seconds and renews every 20 seconds; a second poller fails clearly and lease loss stops processing. Polling uses at most 20 updates, a 20-second poll timeout and a 30-second HTTP timeout. Only transient transport and rate-limit failures retry, using interruptible backoff capped at 60 seconds. Other permanent failures stop safely without raw provider errors or token URLs.

Offsets are durable, monotonic and scoped to **`telegram:<bot_id>:<owner_user_id>:<chat_id>`**. Restart resumes the saved offset after completed/ignored updates. Replayed final actions cannot publish twice. Delivery is at least once: a crash after sending but before storing the message ID can duplicate a card, but both cards use the same review token and publication remains idempotent. An unchanged edit or expired callback acknowledgement is nonfatal. An unavailable open card becomes eligible for bounded resend; terminal publication stands even when its success-message edit fails.

Stop with Ctrl+C or SIGTERM. Backoff stops immediately. PostgreSQL statements and lock waits in this worker, including its heartbeat, have a 10-second timeout; other workers retain their defaults. Database connections and SQLite busy waits also have 10-second timeouts. HTTP uses a 30-second inactivity timeout for each socket operation, rather than an overall request deadline: a response that keeps making progress can take longer, and shutdown waits for the active request to return. Normal shutdown closes the client and releases only this process's lease. After a crash or failed database cleanup, allow the 90-second lease to expire before retrying. Restart explicitly after code/config changes. To disable, stop the process and set `TELEGRAM_ENABLED=0`; stored reviews/audit/offsets stay available. Stop Telegram along with API/jobs before database recovery.

Database leases cannot coordinate **different databases**: separate databases must use separate bots even if each has only one worker. Before changing owner/chat, stop the previous consumer and verify the new identity privately. Telegram may already have acknowledged earlier updates, so changing owner/chat or offset keys cannot recover an old per-user inbox. No automatic enrollment, bulk approval or production activation is provided.

### Default schedules

Timezone: **America/New_York**, editable in Settings.

| Work | Schedule |
| --- | --- |
| Discovery | Daily, 02:00 |
| Priority refresh | Daily, 03:00 |
| Full metadata refresh | Sunday, 03:00 |
| Backup | Daily, 03:30 |
| Discord digest | Monday, 09:00 |

Discovery considers at most 100 repository URLs/run and adds at most 10 new candidates/day by default. Growth is unknown until a later star observation. Jobs use durable IDs, leases, and checkpoints; interrupted/paused runs survive midnight. Failed job kinds wait for owner resumption in Operations. Run only the Python worker after switching from the original TypeScript backend.

## Spending controls

The monthly target defaults to **$20** and cannot be raised above it in this version. In Costs, configure a hosting allowance covering Vercel, Railway, database, storage, and other operating/agent charges; enter the current Jev input price per million tokens from your contract or [official pricing](https://docs.typesafe.ai/models). Update reported hosting cost/projection during the month. The ledger uses the greater of your allowance and current-month hosting report, plus AI usage and reservations.

Before each paid call, the backend atomically reserves the configured cost of the model's full 65,536-token input window, then settles to valid returned input usage after validating all required decisions. Timed-out or malformed responses retain their reservation until reconciled against provider billing. TypeSafe currently bills input tokens; verify pricing/model assumptions before enabling AI. No separate paid agent provider is included.

The default and `.env.example` pin `TYPESAFE_MODEL=jev-1.13.0`, the model reviewed for this input bound. The adapter also accepts `jev-latest` and `jev-preview`; these aliases can change remotely. Other model identifiers are disabled until their limits are reviewed. Review input limits and your contract's input price before changing versions or using an alias, and keep the configured rate current. Existing `.env` values are preserved, so update an old alias explicitly if you want the pin. Missing usage, malformed decisions, and reported usage beyond the reserved bound retain the full reservation for owner reconciliation rather than being treated as settled billing.

If the target is reached or the next reservation cannot fit, discovery, metadata checks, and paid AI pause and a notification is queued. Browsing, deterministic search, and repository links continue. UTC calendar months define cost periods; a new month does not automatically clear a prior stop. Review costs, clear the budget stop/relevant pause switches, and resume failed jobs explicitly.

Settings saves require the revision shown when the page was opened. If a budget stop or another update occurs meanwhile, reload and review the latest controls before saving; an older form cannot clear that newer stop.

This guard cannot cap hosting invoices, egress, unreported costs, or incorrect provider pricing. Set provider billing limits/alerts separately. Backups and notifications continue as operational work while discovery is paused.

## Vercel + Railway deployment

### Railway: FastAPI, worker, PostgreSQL

1. Provision PostgreSQL and build the **repository root** with Dockerfile **`backend/Dockerfile`** for the API service. Its default command runs Uvicorn on Railway's `PORT`.
2. Configure `DATABASE_URL`, `APP_ENV=production`, the frontend `APP_URL`, owner/provider secrets, and `BACKEND_PROXY_SECRET`. Use TLS for the public API/database endpoint where applicable. Backend-only secrets stay off Vercel.
3. Pre-deploy migration command: **`python -m backend.app.cli migrate`**. Migrate before making the API/frontend available. Health path: **`/api/health`**.
4. Create a worker from the same backend Dockerfile with start command **`python -m backend.app.cli worker`**. Use the same database and app/provider configuration. Start one worker initially.
5. Mount a persistent backup volume at `/app/.data/backups`. Set build argument `POSTGRES_MAJOR` to your database server major (default 17) so `pg_dump` matches. The worker needs no public port.
6. Enable a Railway HTTPS domain for FastAPI; use that URL as Vercel's `BACKEND_URL`. Confirm API + worker + database operating costs fit your allowance before enabling discovery.

### Vercel: Next.js only

Framework Next.js, Node 24, install **`npm ci`**, build **`npm run build`**. Set server-side `BACKEND_URL` to the Railway HTTPS API origin and the shared `BACKEND_PROXY_SECRET`. No PostgreSQL driver, database URL, GitHub secret, Jev key, or scheduler is needed on Vercel. Browser requests remain on `/api/*`; the Next.js proxy forwards them to FastAPI and preserves OAuth cookies/redirects. Set GitHub's callback to the Vercel/custom frontend origin.

Deploy and migrate the backend before the frontend. No external services are provisioned automatically. Live OAuth, providers, PostgreSQL, containers, browser behavior, and deployment networking still require validation with your configured accounts.

## Self-hosting

Copy `.env.example` to `.env` if needed, set a unique long **URL-safe** `POSTGRES_PASSWORD`, configure secrets, and set `APP_URL` to your public HTTPS frontend origin.

```sh
docker compose up --build -d
```

Compose starts PostgreSQL 17, migrates, then starts FastAPI, the worker, and Next.js. Web/API bind only to host loopback at 3000/8000; use a trusted TLS reverse proxy for public frontend access. The database has no host port. Named `database` and `backups` volumes persist data. Do not run `docker compose down -v` if you need the records.

A single-host production backend can use SQLite with an explicit persistent `SQLITE_PATH`; multi-machine or serverless deployments need shared PostgreSQL. The schema is compatible with the prior implementation; there is no data reset or format rewrite.

## Backup, restore, rollback

`npm run backup` creates a consistent SQLite backup or PostgreSQL custom-format dump. Partial files are never counted as valid snapshots. The worker retains seven completed snapshots with restricted file permissions. Protect them and copy them to independent storage; automated offsite transfer is not implemented.

Stop API and worker before recovery. Restore PostgreSQL into a **new empty database** using a matching client:

```sh
pg_restore --no-owner --no-privileges --dbname="$RESTORE_DATABASE_URL" /path/to/store-backup.dump
```

Point the backend at the restored database only after reviewing it. Keep the prior database until recovery is confirmed. For SQLite, preserve the existing database/WAL files, copy the selected snapshot to a **new path**, update `SQLITE_PATH`, migrate, and restart.

The original TypeScript backend/configuration was preserved locally in `.data/migration-backups/typescript-backend-before-fastapi.zip` before replacement. To roll back, stop Python API/worker, restore that archive to a separate checkout, and run the previous services against the unchanged schema. Do not run old/new writers together. The archive and local data are git-ignored; keep your own backup.

## Validation and known limits

```sh
backend/.venv/bin/python -m compileall -q backend/app
npm run typecheck
npm run build
```

No application tests were added/run under the current session instruction. Compilation/import checks do not prove endpoint or live integration correctness. The development environment blocks network listeners, browser access, Docker, and registry DNS; dependencies were provisioned from available local distributions.

Search initially matches the published catalog in memory, returns up to 100 results, and ranks at most 20 candidates with Jev. Add indexed database retrieval and pagination when the collection grows. Download clicks count button activations, not completed installations or unique users. Metadata extraction is conservative and needs owner review. No public accounts, reviews, ratings, binary mirroring, installation, or malware scanning are included.

[FastAPI migration record](docs/superpowers/plans/2026-10-11-fastapi-migration.md) · [Product design](docs/superpowers/specs/2026-10-11-app-store-design.md)
