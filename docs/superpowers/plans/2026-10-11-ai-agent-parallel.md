# AI Agent Parallel Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for your assigned lane. The owner will open four separate Codex sessions. Do not start other sessions or implement another lane.

**Goal:** Complete the planned AI search, discovery, and maintenance behavior in four isolated Python worktrees without duplicating the backend migration.

**Architecture:** Retain the existing FastAPI service and durable worker. Jev makes bounded decisions over supplied evidence; Python owns retrieval, approval boundaries, scheduling, and spending. Four branches share a committed migration baseline and preserve existing interfaces.

**Tech stack:** Python, FastAPI, Pydantic, httpx, SQLite/PostgreSQL, TypeSafe Jev, GitHub REST, Discord; existing Next.js UI.

**Spec:** `docs/superpowers/specs/2026-10-11-app-store-design.md`.

**Precedence:** `2026-10-11-fastapi-migration.md` supersedes the original plan's TypeScript backend architecture. The original plan's Tasks 3–4 and spec define behavior. Existing checked boxes and compilation records are historical claims, not evidence that the new Python port satisfies them.

## Global constraints

- Implement the existing requirements; do not introduce a chatbot, generative descriptions, a new agent framework, external crawling, automatic installation, or automatic publication.
- Every new publication requires owner approval of the reviewed candidate revision.
- USD 20 monthly target. Missing cost configuration disables paid calls.
- Preserve schema, camelCase JSON, manual overrides, rejected repository IDs, revisions, uncertain reservations, and interrupted checkpoints.
- No public accounts, reviews, ratings, personalization, security scans, hosted downloads, or automated installation.
- No paid calls, live notifications, deployment, or production worker execution during development.
- Follow the source plans' verification policy: no application tests unless the owner requests them. Use syntax/import checks and code review; report behavioral verification limits. Proposed behavioral checks below are review cases, not authorization to add/run tests.
- Each worker changes only its assigned production files. Shared persistence, models, configuration, API routes, CLI, schema, dependency files, and deployment remain migration/integration ownership.

## Migration handoff gate

The migration plan already assigns all AI modules to the migration session. The Python files exist and are actively being written. Two sessions must not independently replace the same implementation.

1. Let the migration session finish its port and stop editing these modules, or explicitly hand off the AI modules with their supporting contracts finished.
2. The baseline must contain importable Python modules listed below and the migration's final interface decisions. Resolve any interface drift in this document before dispatch.
3. In a normal Terminal, run `bash scripts/prepare-ai-worktrees.sh --migration-ready`. In this checkout, Git initialization is blocked by sandbox permissions; no worktrees were created by the preparation session.
4. With no Git repository, the script initializes one and commits an explicit source/config/docs allowlist. With an existing repository, it requires a clean committed checkout. It never automatically commits an existing repository's pending work.
5. All four worktrees start at the same recorded commit. No worker rebases onto a moving migration branch during development.

You can read the handoffs while the migration proceeds. Implementation starts only after this gate. If immediate overlap is necessary, the migration session must explicitly relinquish the owned files first; isolation alone does not remove conflicting ownership.

## Sessions and ownership

| Session | Branch | Worktree | Exclusive production ownership | Handoff |
| --- | --- | --- | --- | --- |
| 1 | `ai/provider-budget` | `.worktrees/ai-provider-budget` | `backend/app/jev.py`, `backend/app/budget.py` | `docs/superpowers/handoffs/ai-provider-budget.md` |
| 2 | `ai/catalog-search` | `.worktrees/ai-catalog-search` | `backend/app/search.py` | `docs/superpowers/handoffs/ai-catalog-search.md` |
| 3 | `ai/discovery` | `.worktrees/ai-discovery` | `backend/app/github.py`, `backend/app/discovery.py` | `docs/superpowers/handoffs/ai-discovery.md` |
| 4 | `ai/maintenance-jobs` | `.worktrees/ai-maintenance-jobs` | `backend/app/maintenance.py`, `backend/app/jobs.py`, `backend/app/discord.py` | `docs/superpowers/handoffs/ai-maintenance-jobs.md` |

Four is the recommended number of implementation sessions. More would split files with coupled invariants. Fewer can combine lanes, but this preparation targets four as requested by the parallel workflow. The existing migration session is additional to these four.

## Shared interfaces

These names were observed in the Python port on October 11. Read the final baseline implementations before relying on return shapes or side effects; the migration is not yet finished. Preserve public signatures. Record needed shared changes in your completion note rather than modifying shared files.

- `db.query(sql: str, values=()) -> list[dict]`; `db.transaction()` is the transaction context manager. Do not invent a second connection/locking abstraction.
- `store.get_settings() -> Settings`, `write_settings(settings)`, `categories()`, `list_apps(include_private=False)`, `find_app(app_id: str)`, `save_candidate(data: Metadata, assessment: dict) -> bool`, `now() -> str`, `encode(value) -> str`, `bump_revision()`, `audit(action: str, data)`.
- `Metadata` and `Settings` remain in `backend/app/models.py`; camelCase record fields are shared contracts.
- `jev.decide(state, questions: dict, strict=False)` returns validated typed answer dictionaries or `None` for unavailable/disabled/non-strict failure. `ProviderError` is the strict failure boundary. Callers must use existing typed-question/answer shapes.
- `budget.usage()`, `enforce()`, `reserve(amount: int)`, `settle(reservation: str, amount: int)`, `money(micros)`; currency uses integer microdollars. Preserve actual baseline result shapes.
- `search.search_catalog(query="", filters=None, use_ai=True)` returns `items`, `related`, `mode`, and `total`; preserve existing frontend values and semantics.
- `github.fetch_repository(url: str) -> Metadata`, `search_repositories(search: str, limit=20)`, `MissingRepository`, `GithubError`.
- `discovery.discover(job)` and `maintenance.maintain(job, priority_only=False)` consume the existing `JobContext`: preserve its fields, `assert_lease()`, and `checkpoint(data)`. Do not rename checkpoint keys used by interrupted runs.
- `jobs.run_due_jobs()`, `execute(job_id, kind, local_day)` and CLI invocation remain compatible.
- `discord.queue(message: str) -> str`, `deliver(notification_id: str)`, `notify(message: str)` preserve durable delivery semantics.

The graph traces discovery and maintenance through `jobs.execute` → `run_due_jobs` → `cli.main`. Integration must inspect those callers even though the CLI is outside worker ownership. Search and admin also consume provider/budget APIs. No worker may change those public interfaces unilaterally.

## Review focus

1. Missing/malformed/partial Jev responses and timeouts retain uncertain costs and cannot expose a paid-call path without reservation. Owner: Session 1.
2. Unpublished records, unknown attributes, unrelated queries, and cache revisions cannot produce misleading public matches. Owner: Session 2.
3. Repository instructions, missing facts, rejected IDs, first star observations, and daily limits remain safe proposals under restart. Owner: Session 3.
4. Repository transfers, overrides, DST, lease loss, and interrupted checkpoints cannot mutate approved identity or duplicate work. Owner: Session 4.
5. Budget stops and failed Discord delivery remain durable and require explicit owner action where specified. Owners: Session 1 (budget state) and Session 4 (delivery/run state).

## Task 1: Provider decisions and spending

**Files / interfaces:** Session 1 row and shared interfaces above. Original Task 3; spec: Catalog search and Jev / Budget controls.

- [x] Read the lane handoff and final baseline; identify concrete gaps before editing.
- [x] Review response schema, key/type/criteria validation, bounded requests, strict/non-strict errors, and reservation/settlement ordering.
- [x] Complete only demonstrated gaps in owned files. Preserve fallback and durable pause behavior.
- [x] Review concurrent reservations, timeout/unknown usage, rollover, missing configuration, and overspending paths.
- [x] Run owned-file syntax checks and environment-appropriate safe import checks; record exactly what was checked.
- [x] Commit owned changes and `docs/superpowers/completions/ai-provider-budget.md`; report no-op if the baseline already satisfies the lane.

## Task 2: Published-catalog search

**Files / interfaces:** Session 2 row and shared interfaces above. Original Task 3; spec: Catalog search and Jev / Visitor experience.

- [x] Read the lane handoff and baseline; trace public search callers without changing their contracts.
- [x] Review published-only retrieval, aliases, typo tolerance, descendant categories, attribute filtering, exact-name precedence, relevance, and inactive penalties.
- [x] Complete only demonstrated gaps in owned files; keep the 20-candidate Jev bound and 24-hour revision/model/filter cache.
- [x] Review malformed provider decisions, empty queries, unsupported filters, no-match suggestions, and deterministic fallback.
- [x] Run syntax/import checks and commit owned changes plus `docs/superpowers/completions/ai-catalog-search.md`.

## Task 3: GitHub evidence and private discovery

**Files / interfaces:** Session 3 row and shared interfaces above. Original Task 4; spec: Scheduled discovery / Listings and attribution.

- [x] Read the lane handoff and baseline; trace worker, storage, and maintenance consumers.
- [x] Review fixed-host GitHub access, redirects/rate limits, bounded pages/excerpts, stable IDs, releases, provenance, and documented facts.
- [x] Complete demonstrated gaps in seed/topic/recent/active collection, deduplication, rejection suppression, checkpoints, and bounded private proposals.
- [x] Review default limits of 100 evaluated repositories and 10 additions per day, cross-run/restart enforcement, first observations, uncertain eligibility, and untrusted repository text.
- [x] Run syntax/import checks and commit owned changes plus `docs/superpowers/completions/ai-discovery.md`.

## Task 4: Maintenance, durable jobs, and notifications

**Files / interfaces:** Session 4 row and shared interfaces above. Original Task 4; spec: Approval and maintenance / Administration and Discord / Scheduled discovery.

- [x] Read the lane handoff and baseline; preserve invocation and checkpoint contracts consumed by discovery and the CLI.
- [x] Review routine factual refreshes, owner overrides, identity/license/free-use/category proposals, unavailable sources, and inactivity.
- [x] Complete demonstrated gaps in leases, local schedule identities, resumable checkpoints, per-job failure pauses, weekly digest, and durable notifications.
- [x] Review DST/restarts, lease loss, cross-midnight recovery, explicit resume after budget/failure, and notification failure without recursive alerts.
- [x] Run syntax/import checks and commit owned changes plus `docs/superpowers/completions/ai-maintenance-jobs.md`.

## Integration after the four sessions

Reuse the migration/orchestration session for integration; a fifth implementation session is unnecessary.

- [x] Inspect each completion note and branch diff. Check file ownership and avoid merging speculative refactors or duplicate porting.
- [x] Merge `ai/provider-budget`, `ai/catalog-search`, `ai/discovery`, then `ai/maintenance-jobs` into an integration branch based on the recorded common baseline. This order validates dependencies; workers can develop concurrently against unchanged interfaces.
- [x] Resolve shared-file requests together. The integrator owns any needed `store.py`, `db.py`, `models.py`, `config.py`, API/CLI, schema, dependency, or deployment edits.
- [x] Verify provider consumers, discovery's JobContext, maintenance's GitHub calls, durable state, admin pause/resume, and unchanged frontend search JSON against the merged code. Verification is code review, not application execution.
- [x] Run Python syntax/import checks and the migration's TypeScript/build gates. Follow `backend/requirements.txt` in a worktree-local virtualenv; do not share mutable environments between sessions. Do not migrate or run workers against the main checkout's database.
- [x] Record limits honestly: without requested behavioral tests and live integration access, compilation and review do not prove concurrency, billing, DST, PostgreSQL, OAuth, or provider behavior.
- [x] Keep worktrees until the owner accepts integration; do not deploy or delete branches automatically. All worktrees and branches remain intact; no deployment or cleanup occurred.

Completion status: all four lane implementations and the integration checklist are complete under the stated syntax/import/build/code-review verification policy. The lane checkboxes were reconciled with their committed completion reports and integrated branch tips; they do not claim executable behavioral verification. The owner selected local landing, and `main` fast-forwarded to `c899fd2` without conflicts.

Merge/review, remediation, and local-landing record: `docs/superpowers/completions/ai-integration.md`. The four conflict-free merges and shared fixes are now on local `main`. Post-merge Python syntax/imports and frontend type checking/build passed. All branches/worktrees and the main checkout's existing local `next-env.d.ts` change remain intact; no push or deployment occurred. Behavioral and live-service validation remain unverified under the plan's no-application-tests policy.

## Launch prompt

Open each worktree as its own Codex project/session. Paste:

> Read `docs/superpowers/plans/2026-10-11-ai-agent-parallel.md` and my lane handoff at `docs/superpowers/handoffs/<lane>.md`. Implement only this lane using superpowers:executing-plans. Preserve the shared Python interfaces and file ownership. Start by reviewing the existing port for gaps; avoid rebuilding completed behavior. Follow the verification policy and write the specified completion note. Commit your scoped changes and report blockers. Do not merge, deploy, or start other sessions.

Replace `<lane>` with `ai-provider-budget`, `ai-catalog-search`, `ai-discovery`, or `ai-maintenance-jobs`.

## Preparation verification

- `bash -n scripts/prepare-ai-worktrees.sh`: passed.
- Disposable-repository smoke check: passed usage gate, baseline commit, four linked worktrees at the same commit, handoff availability, secret/data/cache exclusions, idempotent rerun, and refusal of a dirty checkout. Fixture removed after verification.
- Project worktree creation: blocked. `git init -b main` returned `.git: Operation not permitted`; native Codex worktree creation returned `fatal: not a git repository`. No project Git repository or AI worktrees were created.
- No application code was changed or application tests run. The preparation covers planning and setup only; the migration and four lane implementations remain separate work.
