# Weekly App Requests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let visitors find and suggest public GitHub projects, then send the ten most suggested eligible projects into owner review each week.

**Architecture:** Four isolated sessions implement request persistence/API, GitHub lookup, visitor UI and weekly processing against the contracts below. A fifth worktree integrates them in order and runs the complete verification gate. Reuse the Python backend, Alembic, Next API proxy, job leases/checkpoints and Telegram review pipeline.

**Tech Stack:** Python/FastAPI/Pydantic, PostgreSQL/SQLite, Alembic, Next.js 16.3.7, React 19, TypeScript, unittest and mocked HTTP transports. No new runtime dependencies expected.

**Spec:** `docs/superpowers/specs/2026-10-12-weekly-app-requests-design.md`

## Global Constraints

- No login, public GitHub projects only, no ownership badge or public leaderboard.
- One contribution per canonical numeric repository ID and signed anonymous browser identifier; five submission attempts/hour/address.
- Three search characters, 400 ms debounce, ten displayed results, five-minute provider cache, ten search requests/minute/address and ten uncached operations/minute globally.
- Monday 00:05 in settings.timezone, cutoff Monday 00:00; cumulative backlog, frozen ranking, maximum 30 evaluations and ten new candidates per closed week.
- Weekly cap is independent of discovery's daily quota; never auto-publish, reopen rejected candidates or revise an existing candidate.
- No AI calls, live Telegram calls, production writes, root credential copies, shared local DB migrations or shared service restarts in worker sessions.
- All workers read AGENTS.md and applicable skills. Frontend workers read installed Next documentation before editing; do not assume older Next APIs.
- Own files exclusively. Missing cross-lane modules are dependencies, not permission to create placeholder production modules or edit another lane.

## Review Focus

1. Concurrent tabs/requests and renamed repositories must count once; Task 1 pins these cases.
2. A selected result that becomes unavailable or whose metadata is forged by a client must not create an unverified contribution; Tasks 1/2 pin these cases.
3. Provider throttling, late autocomplete responses and cached stale store status must preserve a usable submission flow; Tasks 2/3 pin these cases.
4. DST, worker downtime, late submissions and a process dying between candidate creation/checkpoint must not duplicate or reorder a frozen batch; Task 4 pins these cases.
5. Existing rejected/pending candidates, paused publication and an additive migration must preserve review history and keep Telegram usable; Tasks 1/4/5 pin these cases.

## Shared baseline and worktree map

Baseline snapshot: `061206cb84a59399617bb4b785e7d468edf49229`, parent develop `c6985896426011e6a8534f8b439371e41e1a3c61`.
The snapshot contains current tracked edits plus the Telegram card completion report. It includes the four-button Telegram flow and existing page edits. The original develop checkout/index and its uncommitted work remain untouched. All five worktrees branch from a documentation commit on top of this snapshot.

| Session | Branch | Directory | Owns |
|---|---|---|---|
| 1 | requests/data-api | .worktrees/requests-data-api | Migration, counting, identity, submission API, admin data |
| 2 | requests/github-search | .worktrees/requests-github-search | GitHub lookup, search router, provider cache/rate control |
| 3 | requests/ui | .worktrees/requests-ui | Visitor form, search UI, request/admin/privacy presentation |
| 4 | requests/weekly-review | .worktrees/requests-weekly-review | Frozen weekly selection, jobs, Telegram schema compatibility |
| 5 | requests/integration | .worktrees/requests-integration | Router wiring, merged behavior, integration tests and runbook |

Sessions 1–4 can start together. Session 4's ranking/persistence integration checks need Session 1's finished commit; its pure calendar/scheduler tests can run first. Session 5 starts after Sessions 1–4 report completion. No worker merges another branch. The integrator merges 1 → 2 → 3 → 4 and resolves actual integration issues.

## Frozen contracts

Dates on HTTP/DB boundaries are UTC ISO strings with milliseconds and `Z`, using store.now conventions. Counts are nonnegative integers; repoId is a numeric string. Contracts live in this document; runtime schemas belong to the named owner, not a competing shared stub.

**RepositorySummary JSON (Session 2):** `{repoId, repoUrl, name, owner, description, stars, license, archived}`. Canonical HTTPS GitHub root URL; archived is boolean. Missing description/license are empty strings. No private repository data.

**SearchResult JSON (Session 2):** `{items: RepositorySummaryWithStatus[], incomplete: boolean}`. Each item adds `status: available|suggested|already_listed|awaiting_review|already_reviewed` and `suggestionCount: number`. `GET /api/community/repositories?q=...` returns at most ten; `GET /api/community/repository?url=...` returns one `{item: ...}`. Exact missing repository is 404. Status enrichment uses Session 1's service; provider tests patch this seam until merged. Export `router` from `backend/app/community_github.py`; Session 5 alone registers this router in main.py.

**Submission API (Session 1):** existing `POST /api/requests`, same-origin, same body `{name:string, repoUrl:string, website:string}`. No repository: legacy app_requests plus `{ok:true,status:"recorded",suggestionCount:null}`. Verified public repository: `{ok:true,status:"recorded"|"already_suggested"|"already_listed"|"awaiting_review"|"already_reviewed",suggestionCount:number|null}`. Keep successful status 201 for compatibility. Other failures retain the existing `{error:string}` shape. Counts are null when not applicable. The backend fetches repository metadata itself through existing github.fetch_repository; frontend search results are not proof.

**Community persistence (Session 1), `backend/app/community_requests.py`:**

- `record_suggestion(data: Metadata, visitor_key: str, *, at: str | None = None) -> dict`: return the submission response above. Validate canonical data and transactionally deduplicate before inserting contribution; do not overwrite store candidates.
- `repository_status(repo_id: str) -> dict`: return `{status, suggestionCount}` with the search status vocabulary; apps/candidates take precedence over pending suggestions.
- `rank_pending(*, cutoff: str, limit: int = 30) -> list[dict]`: rows `{repoId, repoUrl, name, suggestionCount, firstSuggestedAt}`; pending only, contributions `< cutoff`, exclude any app/candidate, order count DESC / first contribution ASC / numeric ID ASC. Do not truncate numerically large GitHub IDs.
- `mark_review_queued(repo_id: str, *, at: str) -> None`: update a pending suggestion to queued; caller must hold the surrounding writer transaction. Does not create candidates or advance jobs itself.
- `admin_suggestions() -> list[dict]`: rows `{repoId, repoUrl, name, suggestionCount, state, createdAt}` for the admin dashboard's new `communitySuggestions` field. No visitor identity fields.

**Migration (Session 1):** `0003_community_requests`, down_revision `0002_telegram_reviews`. `community_suggestions`: repo_id TEXT PK, repo_url TEXT UNIQUE NOT NULL, name TEXT NOT NULL, state TEXT NOT NULL (pending/queued), created_at TEXT NOT NULL, updated_at TEXT NOT NULL. `community_contributions`: repo_id TEXT NOT NULL FK to suggestions, visitor_key TEXT NOT NULL, created_at TEXT NOT NULL; composite primary key (repo_id,visitor_key), index on created_at/repo_id. Application state controls add no destructive changes to legacy tables. Preserve the normalized metadata evidence in candidates at promotion rather than copying full README into the suggestion table.

**Anonymous identity (Session 1), `backend/app/request_identity.py`:** `visitor_identity(request: Request, response: Response) -> str`, validating or setting cookie `store_suggester`, returns HMAC storage key. Random identifier and signature are opaque to the UI. Use config.auth_secret (production requires at least 32 characters); local fallback shares the existing auth._local_secret. Signed payload has version, identifier and expiration; separate signing/storage domains.

**Weekly service (Session 4), `backend/app/community_weekly.py`:** `closed_week(now: datetime, timezone: str) -> dict | None` returns `{weekStart, cutoff, dueAt}` for the latest eligible closed week, with UTC timestamp strings for cutoff/dueAt and local date string for weekStart. At Monday 00:00–00:04 do not select the just-closed week yet; an older unfinished eligible job may still resume. `promote_weekly(job: JobContext) -> bool`: True when finished, False when paused. Lazy-import the Session 1 service inside the function so unrelated job imports and pure calendar tests work before that lane is merged.

**Job checkpoint (Session 4):** `{version:1, weekStart, cutoff, ranked:[rank_pending rows], index:0, promotedRepoIds:[], skipped:[]}`. Save frozen ranking transactionally under lease before fetching metadata. On each successful item, candidate insertion, mark_review_queued, promoted list/index and job.checkpoint occur in one writer transaction. `skipped` entries contain only repoId/reason. Do not mark an unprocessed failure consumed.

**Assessment (Session 4):** source `community-weekly`, weekStart, cutoff, suggestionCount, jobId, inAppModelCalled false, fetched GitHub evidence and truthful uncertainty. Unknown free-use remains `Needs review`; existing Telegram suggestions provide category selection without publishing.

## Task 1: Persist and accept community suggestions — Session 1

**Files:** Create `backend/alembic/versions/0003_community_requests.py`, `backend/app/community_requests.py`, `backend/app/request_identity.py`, `backend/tests/test_community_requests.py`. Modify `backend/app/main.py` only for POST /api/requests, `backend/app/admin.py` only for dashboard `communitySuggestions`. Report `docs/superpowers/completions/requests-data-api.md`.

**Interfaces:** Produces submission, identity, schema and persistence contracts above. Consumes existing Metadata/github.fetch_repository/db.transaction/store/auth; no imports from another new lane.

- [ ] Write failing disposable SQLite/PostgreSQL tests: `test_same_browser_counts_once` (count 1 after two identical requests), `test_two_browsers_count_twice` (2), `test_concurrent_duplicate_counts_once` (1), `test_rename_uses_numeric_identity` (one suggestion), `test_cutoff_excludes_late_contribution` (late event not counted), `test_stable_numeric_ties` (2 before 10), `test_candidate_states_do_not_reopen` (candidate revision/data unchanged), `test_forged_metadata_is_not_accepted` (server facts prevail), `test_cookie_tamper_and_expiry` (fresh signed identity), `test_origin_honeypot_and_rate_limits` (no contribution on rejection).
- [ ] Add migration preservation tests: existing app_requests/apps/telegram_state rows survive upgrade; repeat upgrade is safe; tables/constraints work on both supported DBs; historical requests produce zero synthetic contributions. Reuse the safety patterns of test_telegram.py with a separately named disposable database and fully mocked network.
- [ ] Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_community_requests.py -v`; confirm a relevant failure, not a missing dependency.
- [ ] Implement exact schema and service signatures above. Modify existing app_request handler to validate/fetch a public repository outside the writer transaction, obtain signed visitor identity, and record a contribution. Keep idea-only legacy insertion and old response compatibility. Add owner-visible dashboard data; no public list of contributor identifiers.
- [ ] Run targeted tests to PASS and record PostgreSQL/SQLite coverage. Commit only owned files and report exact commit/checks/limits.

## Task 2: GitHub search and exact lookup — Session 2

**Files:** Create `backend/app/community_github.py`, `backend/tests/test_community_github.py`. Report `docs/superpowers/completions/requests-github-search.md`. Do not edit main.py, github.py, auth.py, config.py or package files.

**Interfaces:** Produces router and HTTP summary/result contracts. Consumes existing fixed-origin github.api, namespaced search_cache/rate_limits tables and Session 1 repository_status (lazy runtime import; injected/mocked for lane tests).

- [ ] Write failing tests: `test_best_match_public_results` (ten maximum, no sort=stars, no private data), `test_exact_lookup_canonicalizes_rename`, `test_host_and_path_validation`, `test_incomplete_results_disclosed`, `test_provider_cache_five_minutes`, `test_cached_facts_refresh_store_status`, `test_provider_limit_shared_between_clients` (eleventh uncached operation in a minute yields 429), `test_exact_and_search_share_provider_bucket`, `test_cache_hit_avoids_provider_bucket`, `test_timeout_and_rate_limit_are_sanitized` (503/429 and Retry-After; synthetic secret absent).
- [ ] Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_community_github.py -v`; verify relevant failures. Use a standalone FastAPI test app with only this router so no integration wiring is required.
- [ ] Implement router, summary validation, five-minute provider-facts caching and transactional global bucket. Apply per-address auth.rate_limit and refresh status after cache lookup. Use a single public-repository search operation per request and fixed-origin github.api for exact lookup; do not fetch each README/release for result cards. Treat input as bounded search text (max 200 characters), treat search input as ordinary words rather than accepting arbitrary GitHub query operators, enforce public scope server-side and use the exact URL parser for direct lookup.
- [ ] Run targeted tests to PASS, including concurrency against a disposable DB; ensure no live GitHub/Telegram requests.
- [ ] Commit owned files and completion report. Router registration is the integration session's responsibility.

## Task 3: Visitor search and request presentation — Session 3

**Files:** Modify `src/components/request-form.tsx`, `src/app/request/page.tsx`, `src/app/admin/page.tsx`, `src/app/about/page.tsx`, `src/lib/backend.ts` only for its Dashboard definition's optional communitySuggestions field. Create `src/components/repository-picker.tsx`, `src/lib/community-types.ts`, `src/app/request/request.css`, `scripts/verify-community-ui.mjs`. Report `docs/superpowers/completions/requests-ui.md`. Do not edit globals.css, API proxy, backend, package.json/lockfiles or unrelated app pages.

**Interfaces:** Consumes only frozen HTTP contracts, using typed fixtures while backend lanes finish. The admin field must be optional during rollout; display an empty section if absent. Import request.css from request page; keep styles scoped to request UI.

- [ ] Read installed Next docs for route handlers, forms and client data fetching. Add focused failing checks in the zero-dependency Node verification script for the extracted pure response/state helpers: a late search A cannot replace newer B, selecting a result fills canonical URL/name, duplicate/listed/pending messages map correctly, and errors keep manual input. Use node:assert and the installed TypeScript transpiler for TS helper tests; avoid a new test framework.
- [ ] Run `node scripts/verify-community-ui.mjs` and observe a relevant failure.
- [ ] Implement accessible repository picker with label, keyboard-selectable result buttons/links, status announcements, three-character minimum, 400 ms debounce, AbortController plus request-generation guard, ten results, exact lookup for valid GitHub URLs. React escapes repository text. Keep existing idea-only and URL form submission/honeypot/origin behavior.
- [ ] Implement weekly-consideration success copy, count/status messages and graceful cache/provider/rate errors. Add admin aggregate suggestion rows and anonymous-cookie privacy copy. Do not claim browser counts prove unique humans, ownership, suitability or publication.
- [ ] Run `node scripts/verify-community-ui.mjs` and `npm run typecheck` to PASS. Record keyboard/manual checks against fixtures or an isolated mocked server. Commit owned files and report; live integrated smoke belongs to Session 5.

## Task 4: Weekly selection and scheduler — Session 4

**Files:** Create `backend/app/community_weekly.py`, `backend/tests/test_community_weekly.py`. Modify `backend/app/jobs.py`, `backend/app/models.py` only JOB_KINDS and failedKinds max_length 6, `backend/app/telegram_worker.py` only additive schema readiness, `backend/tests/test_telegram.py` only readiness regression cases, `src/lib/model.ts` only the frontend JOB_KINDS mirror. Report `docs/superpowers/completions/requests-weekly-review.md`. Do not edit migrations, request routes, persistence, bot rendering or Telegram review actions.

**Interfaces:** Consumes Session 1 rank_pending/mark_review_queued, existing store.save_candidate and JobContext. Produces community job/checkpoint/service contract; safe lazy import permits independent scheduler/calendar work before merge. Keep the frontend JOB_KINDS mirror aligned so admin Operations exposes the new job.

- [ ] Write failing tests: `test_latest_closed_week_and_dst` (local Monday boundaries across spring/fall), `test_missed_monday_runs_once_later`, `test_snapshot_excludes_late_votes`, `test_ranked_backfill_and_ten_cap` (30 evaluations maximum, ten candidates maximum), `test_resume_after_atomic_promotion` (crash/retry preserves one candidate/revision), `test_two_workers_and_lost_lease`, `test_all_pause_controls`, `test_existing_candidate_unchanged`, `test_transient_failure_does_not_advance`, `test_404_archived_are_skipped`, `test_daily_quota_unchanged`, `test_telegram_offline_does_not_lose_candidates`. Mock persistence at the declared seam until Session 1 is merged; mark integration-dependent cases explicitly rather than inventing its implementation.
- [ ] Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_community_weekly.py -v`; verify relevant failures.
- [ ] Implement closed_week and promote_weekly; use local calendar arithmetic, frozen checkpoints, provider fetches outside transactions, atomic candidate/state/checkpoint writes under lease and strict caps. Recheck all pause controls inside the commit transaction.
- [ ] Add community to backend and frontend JOB_KINDS and job dispatch/block/resume/finish paths, support six failed job kinds, schedule latest due week daily/catch-up without stale daily skipping. Existing discovery, maintenance, priority, digest and backup behavior must stay intact. Update readiness for additive 0003 without automatically migrating.
- [ ] Verify standalone tests plus `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_telegram.py -q`; commit owned files and report missing cross-lane gates for integration.

## Task 5: Integrate and verify — Session 5, after Sessions 1–4 finish

**Files:** Session 5 owns integration-only registration in `backend/app/main.py`, `backend/tests/test_community_integration.py`, `README.md` feature/runbook sections, `docs/superpowers/completions/requests-integration.md`. It may resolve genuine merge/contract defects in other files after all workers stop; document those edits.

**Interfaces:** Consumes four branch commits. Produces one verified integration branch for user review; no merge to develop/main or deployment in this task.

- [ ] Confirm all four reports/commits exist and workers are finished. Merge requests/data-api → requests/github-search → requests/ui → requests/weekly-review using `git merge --no-ff`; do not cherry-pick another worker's incomplete state. Register community_github.router once.
- [ ] Add failing integration tests for the actual migrated PostgreSQL/SQLite schema and HTTP submit → duplicate → frozen batch → candidate → mocked Telegram card → owner Accept → published listing. Assert no publication before Accept and no new review for an already reviewed app.
- [ ] Add migration/readiness and real service contract tests, cookie Set-Cookie roundtrip through the Next proxy, all weekly failure/race cases and legacy idea-only requests. Resolve only concrete integration defects; no feature expansion.
- [ ] Run full backend unittest discovery, UI verification script, npm typecheck and npm build. Inspect build/runtime errors rather than inventing success. Perform request-page keyboard/mobile/desktop smoke against a disposable environment with synthetic provider data.
- [ ] Write rollout/rollback runbook: verified DB backup, explicitly migrate intended target, ensure stable AUTH_SECRET/GITHUB_TOKEN and proxy secret configured privately, start one jobs worker and one bot poller per bot/database, verify next due date and review delivery. Separate local acceptance from a later production release. Commit report with evidence/remaining limits, then stop for user review.

## Session setup and boundaries

Each worktree has its own installed node_modules and backend/.venv. No env files or credentials are copied. Do not run local:setup/local:db:up/local:dev/local:jobs/local:telegram in parallel lanes: the supplied local launcher pins shared ports and DB 55432. Unit tests must create their own temporary SQLite and disposable PostgreSQL destinations, guard all database connections, and mock provider networking.

Do not copy test_telegram's global socket/DB guards into a shared module without checking unittest discovery order. New suites must restore guards and never depend on another module's setUpModule; full-suite discovery is an integration requirement.

Use the handoff files for exact lane boundaries and start commands in `docs/superpowers/handoffs/requests-sessions.md`. Run Codex with `-C` pointing to the existing directory; do not add `--worktree`, which would create another workspace. Do not merge, deploy, migrate a shared DB or start the weekly job against real suggestions during implementation.
