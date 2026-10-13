# Request persistence and submission API completion

Branch: `requests/data-api`.
Base: `c032bf4bf9884fbedca9812216f221a1911effcf`.
Final commit: the commit containing this report, on `requests/data-api`; resolve its full SHA with `git log -1 --format=%H -- docs/superpowers/completions/requests-data-api.md`. The session's final response supplies the resulting SHA. This avoids embedding a self-referential commit hash.

Task 1 implementation is complete and its required gate passes. The combined backend gate requires the other assigned lanes before it can pass.

## Owned files

- `backend/alembic/versions/0003_community_requests.py`
- `backend/app/community_requests.py`
- `backend/app/request_identity.py`
- `backend/app/main.py` — submission handler and its required Response import only.
- `backend/app/admin.py` — dashboard aggregate only.
- `backend/tests/test_community_requests.py`
- `docs/superpowers/completions/requests-data-api.md`

## Implemented behavior

Migration 0003 adds the suggestion backlog and contributions, composite contribution primary key, foreign key, cutoff index and pending/queued state constraint. It preserves historical requests, apps and Telegram offsets, creates no synthetic votes, and refuses destructive downgrade.

The signed `store_suggester` cookie uses a random 32-byte identifier, a versioned expiring payload, 180-day lifetime, HttpOnly, SameSite=Lax and Secure on HTTPS. Cookie signing and stored visitor HMAC use separate domains. Production requires an AUTH_SECRET of at least 32 characters; development shares auth._local_secret when no secret is configured. Raw identifiers and addresses are not persisted in contributions or exposed in the dashboard.

Repository submission fetches public GitHub facts through existing github.fetch_repository outside the writer transaction. Client IDs, names, licenses and counts cannot supply repository facts. Missing repositories return a sanitized 404, provider/private-repository failures a sanitized 503. Successful responses retain HTTP 201 and ok:true with the frozen status/count fields. Idea-only requests remain manual app_requests. Existing origin, honeypot, five-attempt hourly limit and authenticated-proxy address rules remain intact.

Service exports match the frozen record_suggestion, repository_status, rank_pending, mark_review_queued and admin_suggestions contracts. Counts deduplicate atomically under the existing writer lock and composite key. Rename metadata merges under numeric repository identity. Ranking uses cumulative contributions strictly before cutoff, then count descending, earliest contribution ascending and numeric ID ascending without integer truncation. Apps, existing candidates and queued suggestions cannot be selected or reopened. Queue marking requires the caller's transaction. Dashboard communitySuggestions exposes only aggregate suggestion fields.

## Commands actually run and outcomes

- `graft ask "Implement assigned task from docs/superpowers/handoffs/requests-data-api.md" --source` — repository context retrieved; reported approximately 13,056 tokens saved.
- `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_community_requests.py -v` — initial Docker sandbox restriction required escalation. Authorized RED run: 40 expected failures on missing migration/identity. First implementation run: 36/40 passed; four failures traced to the HTTP test client omitting correctly Secure HTTPS cookies. Corrected the fixture to use the configured HTTPS base URL.
- The same targeted command, through executing-plans `scripts/task-done docs/superpowers/plans/2026-10-12-weekly-app-requests.md 1 c032bf4bf9884fbedca9812216f221a1911effcf -- backend/.venv/bin/python -m unittest discover -s backend/tests -p test_community_requests.py -v` — final **40/40 PASS**, 20 PostgreSQL and 20 SQLite, no skips. Docker temporarily became unavailable between runs; the user restored it before this final gate. Fresh disposable PostgreSQL database/schema and temporary SQLite files only; synthetic credentials and mocked HTTP; guards restored and containers removed.
- `backend/.venv/bin/python /private/tmp/requests-data-api-sqlite.py` — interim SQLite-only wrapper during Docker outage: **20/20 PASS**. Wrapper substitutes only test module setup, forbids PostgreSQL/live network and uses temporary SQLite; not a production stub.
- `backend/.venv/bin/python /private/tmp/requests-data-api-sqlite-regression.py` — interim combined SQLite/Telegram transport wrapper: **48/52 PASS**, four expected cross-lane failures listed below.
- `backend/.venv/bin/python -m unittest discover -s backend/tests -v` — outage run stopped at two Docker module-setup errors, zero tests. Final run after Docker recovery: **94/102 PASS**, two failures and six errors. All 40 new community cases passed in the combined run too.
- `git diff --check` — PASS.
- Fresh read-only review by `/root/final_review` — zero Critical, Important or Minor findings; approved for the assigned commit. Reviewer inspected the actual code and connected code, and ran no tests. Final dual-engine and combined-suite runs were performed by the implementer afterward.

The installed Starlette/httpx integration emits its existing TestClient deprecation warning; no runtime dependency changes were made.

## Remaining integration requirements and exact failing checks

The final full-suite failures occur for **both test_telegram.PostgreSQLCases and test_telegram.SQLiteCases**:

- `test_fresh_schema_and_worker_readiness` — worker readiness requires exactly revision 0002 and rejects additive revision 0003.
- `test_signals_stop_worker_and_restore_handlers` — the same readiness rejection prevents worker startup.
- `test_webhook_refusal_and_once_mode` — the same rejection occurs before client lifecycle assertions.
- `test_upgrade_preserves_baseline_rows` — fixture drops Telegram tables and rewinds the revision to 0001 while leaving new community tables; the conservative migration validator correctly rejects unexpected tables.

Task 4 owns Telegram revision compatibility; Task 5 owns combined fixture updates and the integrated gate. Those files were deliberately not edited here. There is no missing incoming dependency for Task 1. Integration must merge this lane before the search, UI and weekly consumers, register the community router, supply request/admin/privacy presentation, verify proxy cookie roundtrip and the complete submission/review/owner-accept path, and run the combined tests again. Normal PostgreSQL startup still never migrates; release needs the explicit migration step and stable production AUTH_SECRET.

No shared local/production database was accessed or migrated. No root environment files were loaded/copied, shared launchers or pollers run, recommendations sent, AI called, app published, deployment performed, merge made or branch pushed. Keep this branch and worktree for the integration session.

## Review rulings and costs if wrong

1. Simultaneous first requests without a cookie may establish different identifiers. The frozen guarantee is per signed identifier; changing it requires first-use browser synchronization.
2. Cookie deletion, multiple devices and copied cookies remain accepted anonymous identity limits. Counts approximate browsers rather than unique people.
3. Archived repositories can enter the backlog; Task 4 filters at promotion. An ineligible repository may remain in backlog until that filtering runs.
4. Search throttling, cache freshness and stale autocomplete handling remain Tasks 2/3. Search recovery must be verified during integration.
5. Calendar/DST, downtime, frozen checkpoints, pause/crash recovery and promotion caps remain Task 4. Weekly promotion requires those checks before release.
6. Telegram readiness for 0003 remains Task 4. Standalone worker startup fails until that lane is integrated.
7. Proxy cookies, presentation/privacy and the complete submit-to-publication path remain Tasks 3/5. Integrated behavior still needs its gate.
8. No live/load/provider checks were authorized. Production-specific capacity and provider behavior remain unmeasured.
9. Pre-existing Telegram test import-time environment mutation was not changed in a nonowned file. New guards restore independently; broader test isolation remains an integration concern.

Deferred minor findings: none.
