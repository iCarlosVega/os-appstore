# Weekly app requests integration status

Branch: `requests/integration`  
Worktree: `.worktrees/requests-integration`  
Base: `c032bf4bf9884fbedca9812216f221a1911effcf`  
Integration implementation: `0c0f4ba`  
Final implementation/review-fix commit: `e592232`

All four lanes are merged and implementation plus automated verification passes. **The complete Task 5 acceptance gate remains open for browser keyboard/mobile verification.** No merge to develop/main, push, deployment, shared database migration or live bot/provider activation occurred. Preserve this branch/worktree for review.

## Branch integration

All worker branches were clean, committed and had completion reports before integration. Merged with `--no-ff` in the approved order, without conflicts:

| Lane | Worker head | Integration merge |
| --- | --- | --- |
| Data/API | `7a1fa74` | `45a41f0` |
| GitHub search | `eaabb4e` | `12d57e2` |
| UI | `09b4082` | `698755d` |
| Weekly review | `b8d1187` | `2ae0182` |

Registered `community_github.router` once in `backend/app/main.py`. Added real-service integration tests and a reproducible temporary API/proxy fixture in `backend/tests/test_community_integration.py`. README now documents suggestions, weekly scheduling, verification, backup/migration/worker rollout and history-preserving rollback.

The original root develop checkout was left untouched. Build-generated `next-env.d.ts` churn was restored in this worktree; typecheck passed again afterward.

## Independent review and corrected defect

A fresh read-only whole-branch reviewer inspected `c032bf4..0c0f4ba` against the spec, plan, connected code, reports and review focus. One Important finding, no Critical or Minor findings: the same 30 permanently unavailable leaders could occupy every weekly snapshot and starve the remaining backlog.

Fixed in `e592232`: ranking defers suggestions with a retained `community.skipped` audit for archived, missing or identity-changed metadata until a newer server-verified nonarchived submission refreshes eligibility. An archived resubmission cannot clear deferral. Existing contributions, pending state, counts, queue semantics and 30/10 caps remain intact. The existing one-year audit retention permits later periodic revalidation. No migration or fabricated pending candidate/review was introduced.

Two regressions failed on both engines before the fix, then all four cases passed: three successive weeks traverse 60 ineligible leaders and reach five valid projects; a fresh verified restored project becomes eligible without losing its contributions. The full suite was rerun after this single review-fix pass. No second review was substituted for those regressions.

## Commands and actual outcomes

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -p test_community_integration.py -v
backend/.venv/bin/python -m unittest discover -s backend/tests -p test_community_integration.py -k defer -v
backend/.venv/bin/python -m unittest discover -s backend/tests -v
node scripts/verify-community-ui.mjs
npm run typecheck
npm run build
backend/.venv/bin/python -m backend.tests.test_community_integration --serve-fixture
env -i PATH=/opt/homebrew/bin:/usr/bin:/bin NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 \
  BACKEND_URL=http://127.0.0.1:3184 BACKEND_PROXY_SECRET=synthetic-proxy \
  node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3183
backend/.venv/bin/python -m backend.tests.test_community_integration --verify-proxy
git diff --check
```

- Merged backend baseline: **175 tests passed**.
- Integration RED: search returned 404 on PostgreSQL/SQLite before router registration. The new fixture's readonly SQLite URI guard, poller key and raw HTTP stream were corrected to use the existing APIs; those were test-fixture errors, not production defects.
- Initial integration GREEN: **24 tests passed**, using actual suggestion/ranking/queue services. The final integration file has **28 cases**, included in full discovery after the review fix.
- Final full backend gate: **203 tests passed in 37.102 seconds**, no skips/failures/errors. Covers actual migrated PostgreSQL and SQLite, HTTP submission/deduplication, frozen ranking/counts, backfill/caps, rollback of candidate + queue + progress, concurrent workers, lease loss, publication pause during metadata I/O, rejected-candidate preservation, provider bucket concurrency, legacy requests and additive Telegram readiness. The existing calendar/DST/catch-up and migration-preservation suites pass in the same run.
- End-to-end: real search → signed submission/duplicate → weekly candidate → existing bot and Telegram transport with mocked HTTP → unauthorized-action rejection → owner Accept → published catalog. Search cache status refreshes through the actual persistence service; candidate creation does not publish, and reviewed apps get no new review.
- UI verifier: **five behavior groups passed**. TypeScript and the optimized Next 16.3.7 webpack production build passed. Diff whitespace checks passed.
- Real frontend proxy: the production Next server forwarded to the real isolated FastAPI fixture. Search, HttpOnly/SameSite/180-day Set-Cookie and subsequent Cookie roundtrip, duplicate count 1, refreshed status from cached provider facts and idea-only submission all passed.
- The installed Starlette/httpx TestClient emits its existing deprecation warning. No package/dependency changes were made.

Disposable PostgreSQL 17 containers, temporary SQLite, synthetic credentials, mocked GitHub/Telegram HTTP and restored connection/environment guards only. The API fixture explicitly rejects PostgreSQL and uses its own temporary SQLite file. Fixture servers on 3183/3184 were stopped and their temporary database removed. Dedicated test containers were removed. No root environment file or shared catalog was used.

## Outstanding manual acceptance

Native Chrome rendered the production-build `/request` page and synthetic search results with status/count copy and labeled editable fields. Shift+Tab focused the Select button. The Enter attempt reported a user change; subsequent state/screenshot calls returned only an empty window title. The user foregrounded the page on request, and the automation runtime was reset, but the window remained inaccessible. No connected browser or in-app browser was available.

Therefore **complete keyboard selection/submission, screen-reader behavior and mobile viewport checks are not claimed**. Finish the planned Tab/Enter selection, editable/manual fields, throttled/unavailable/retry states and desktop/mobile overflow smoke using the README's fresh isolated fixture. The missing browser gate is why Task 5 is not marked fully complete, despite green implementation/automated gates. Do not treat the user's foreground-ready reply as a manual test result.

## Rulings and remaining risks

1. Existing worker integration scenarios that passed immediately verify already implemented behavior; only missing wiring or concrete defects prompted new production changes. Cost if wrong: a scenario may lack regression sensitivity; assertions target real persisted state and publication boundaries.
2. Failed eligibility is deferred using durable audit evidence rather than deleting votes, introducing fake reviews or changing schema states. Cost: a restored project waits for a new verified submission, independent discovery or audit expiry instead of automatic weekly rechecking.
3. Concurrent cookie-less first requests may establish separate signed identifiers. This is the accepted per-identifier limit; the server does not group browsers by IP. Cost: simultaneous first requests can count separately. Existing-cookie concurrency deduplicates correctly; future origin-wide Web Lock synchronization is a separate mitigation.
4. Existing default software-type/Telegram inference remains shared behavior; community assessments record uncertainty. Cost: owner must inspect suggested metadata before acceptance.
5. Live provider capacity, credentials, scheduling and delivery remain separately authorized release checks. Cost: production-specific configuration/limits remain unproven by synthetic providers.
6. The browser gate remains explicitly open. Cost: accessibility/responsive defects may remain until the stated manual checks pass.

Deferred minor findings: none. Release steps, backup verification, migration targeting, stable secrets, single jobs/bot workers and rollback instructions are in README; none were executed against shared or production services here.
