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
  requirements.txt
  Dockerfile
src/app/               Next.js pages and administration UI
src/app/api/[...path]/  Same-origin HTTP proxy to FastAPI
src/components/        Directory, listing forms, download options
src/lib/backend.ts     Server-side HTTP client; no database/provider logic
migrations/            Shared database schema
```

Next.js does not read the database, execute jobs, or call GitHub/Jev directly. FastAPI validates incoming data with Pydantic and owns all writes and authorization. The proxy preserves `/api/*` URLs and owner cookies on the frontend origin, so public accounts and cross-origin browser calls are unnecessary.

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
