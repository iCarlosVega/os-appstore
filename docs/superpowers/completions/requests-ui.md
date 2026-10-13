# Requests UI — Task 3 completion

Branch: `requests/ui`

Worktree: `/Users/carlosvega/Documents/Projects/os-appstore/.worktrees/requests-ui`

Base: `c032bf4bf9884fbedca9812216f221a1911effcf`

Final commit: the commit containing this report, titled `feat(requests): add repository picker and weekly suggestion UI`. Resolve its SHA with `git log -1 --format=%H -- docs/superpowers/completions/requests-ui.md`; the session's final response also records the SHA.

## Delivered and owned files

- `src/components/repository-picker.tsx`: optional labeled GitHub search, three-character minimum, 400 ms debounce, cancellation and generation guard, exact URL lookup, ten results, ordinary keyboard-operable selection buttons and official links. Shows GitHub best matches, description, stars, license fallback, store status, archived flag, loading/empty/incomplete/throttled/unavailable states.
- `src/lib/community-types.ts`: frozen HTTP types, optional rollout response compatibility, pure search/request reducers, canonical selection and response messages. Numeric repository IDs remain strings.
- `src/components/request-form.tsx`: canonical selection fills editable fields, short names use owner/name, idea-only/manual URL/honeypot submission stays on the existing same-origin POST path. Errors preserve fields and allow retry. Success distinguishes recorded, duplicate, listed, awaiting review and already reviewed without promising publication.
- `src/app/request/page.tsx`, `src/app/request/request.css`: weekly consideration and carry-forward copy, scoped responsive picker/form styling imported from the request page.
- `src/lib/backend.ts`: only Dashboard's optional `communitySuggestions` field added.
- `src/app/admin/page.tsx`: owner-visible aggregate browser counts, pending/queued state and first-suggested date; absent field produces an empty community section. Existing manual request actions remain.
- `src/app/about/page.tsx`: weekly owner review and anonymous cookie/privacy explanation, including GitHub lookup, 180-day signed HttpOnly cookie, pseudonymous stored key and limits of browser counts.
- `scripts/verify-community-ui.mjs`: Node assertions using the installed TypeScript transpiler, complete synthetic repository fixtures, optional isolated mock/Next server and HTTP render smoke.
- `docs/superpowers/completions/requests-ui.md`: this report.

## Checks actually run

- Read the installed Next 16.3.7 route-handler, client-component, forms, data-fetching and CSS guidance before editing.
- `node scripts/verify-community-ui.mjs`: initial RED, exit 1 (`Community UI response/state helpers must exist`); after implementation, PASS, five behavior groups. Covers stale success/error/cleared-query generations, result cap, short queries, exact URL routing/host-path rejection, canonical short-name selection, response statuses/counts, legacy responses and retry/input retention.
- `npm run typecheck`: PASS, exit 0.
- `node scripts/verify-community-ui.mjs --serve-fixtures`: started Next on 127.0.0.1:3183 and the synthetic backend on 127.0.0.1:3184, with an explicit sanitized child environment. No env files, DB, GitHub, Telegram or AI providers used. Stopped before commit.
- `node scripts/verify-community-ui.mjs --http http://127.0.0.1:3183`: PASS, five helper groups plus rendered `/request?name=Offline%20editor`, `/admin?tab=requests`, `/about`, and the admin rollout with `communitySuggestions` absent. An earlier run could not connect after the prototype fixture session ended; another exposed React's HTML comment separators in a literal text assertion. The check now removes those separators before comparing rendered text; the application code was not changed for that assertion.
- `git diff --check`: PASS.
- Independent read-only review of the complete UI diff: no must-fix or should-fix findings; reviewer independently reran all five helper checks successfully.

Browser/manual check attempt: browser discovery returned no connected browser; in-app browser creation was unavailable; native Chrome access returned `Computer Use was not approved to use Google Chrome`. Consequently no actual Tab/Enter, screen-reader, screenshot or mobile viewport check is claimed. The rendered form contains labeled inputs, status regions and native buttons/links; actual keyboard/mobile verification remains below.

## Remaining integration requirements

- Merge the data/API and GitHub search lanes; register the search router in the integration lane. This branch consumes frozen responses and adds no production backend stubs or proxy changes.
- Verify actual search → selection → submission/duplicate → weekly candidate → owner Accept, signed cookie forwarding and fresh store-status enrichment after the other lanes land.
- Run the integration build/full backend gate and actual keyboard/desktop/mobile smoke against disposable data. Specifically Tab from search to Select/official link, Enter to select without submitting, edit fields, test 429/503 fallback and failed-POST retry, then submit an idea without a repository.
- No deployment, push, DB migration, candidate decision changes, Telegram behavior changes or automatic publication performed.

Integration choice is already specified by the handoff: preserve this branch/worktree and stop after commit for Session 5 to merge.
