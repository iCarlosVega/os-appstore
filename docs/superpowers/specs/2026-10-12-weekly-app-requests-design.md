# GitHub app requests and weekly community selections

## Intent and scope

Visitors can recommend a public GitHub project, including their own, without an account. They can search GitHub or paste a repository URL. Suggestions accumulate in a backlog; once a week, up to ten become pending candidates in the existing owner/Telegram review flow. Only the owner's Accept action publishes an app.

The user approved repository search and asked for the ten most suggested apps at the end of each week, then explicitly requested a worktree implementation plan and session commands. This document records the decisions needed for those independent sessions. Defaults below are implementation decisions, not claims that the user specified an exact hour or identity mechanism.

## Visitor experience

- Keep `/request`, the idea/name field, optional repository URL, honeypot and no-login experience.
- Add a search field accepting project names, descriptions, `owner/repository`, or a public GitHub repository URL. Search GitHub's index; do not build a local GitHub mirror.
- Show at most ten results with name, owner, description, stars, license (or "Not provided"), official repository link and current store status. Default to GitHub best match, not descending total stars. No AI calls for search or counting.
- Select a result to fill the existing name and repository fields; use owner/name for a one-character repository name to satisfy the existing form constraint. Typed/pasted repository URLs remain supported. A visitor submitting their own project uses this same flow; no unverified ownership badge.
- Search after three characters and 400 ms without typing. Cancel obsolete requests and ignore late responses. Pasted URLs use exact lookup rather than text search.
- Show loading, empty, provider unavailable, throttled and submitted states. Repository pasting and idea-only requests remain usable when search is unavailable.
- Successful suggestions say they are being considered for the weekly top ten, not that they were added to the store. Published, pending-review and already-reviewed projects get appropriate distinct messages.

## Counting and ranking

- "Top" means the most distinct anonymous browser suggestions for the same canonical numeric GitHub repository ID. No public upvote leaderboard and no ranking by GitHub stars.
- Use a random 32-byte identifier in a signed, HttpOnly, SameSite=Lax, 180-day cookie; Secure for HTTPS. Store a domain-separated HMAC of the identifier, never the raw cookie or IP. Validate signature and expiry; use a stable AUTH_SECRET in production. Local secret fallback is acceptable only in development.
- One contribution per repository per browser identifier, enforced by a database uniqueness constraint, including concurrent submissions. This approximates distinct visitors; cookie deletion and multiple devices cannot establish unique human identity.
- Existing per-address submission limit remains five attempts per hour. Forwarded addresses are trusted only through the existing authenticated backend proxy. Invalid honeypot/origin submissions cannot contribute.
- Canonicalize and verify repository identity on the server using GitHub. Never trust a client-supplied name, license, numeric ID or count. Rename and case variants merge under numeric ID.
- Rank pending suggestions by cumulative distinct contributions received before the weekly cutoff; unselected suggestions and their contributions carry forward. Ties: earliest contribution ascending, then numeric repository ID ascending. No reset of the backlog every week.
- Already published, pending candidates and rejected candidates are excluded from selection and never overwritten or reopened by this feature. A later discovery match also excludes the suggestion. Return `already_reviewed` for a previously rejected candidate without exposing private assessment details.
- Idea-only requests stay in `app_requests` for manual review and do not enter repository ranking. Existing historical requests are retained; do not invent anonymous contributors or silently convert them into votes.

## Weekly selection and review

- Use the store's configured timezone (currently America/New_York). Weeks are Monday 00:00 through the following Monday 00:00, calculated as local calendar dates and converted to UTC; do not assume 168 UTC hours across DST.
- Run at Monday 00:05 local time for the week that just closed. After downtime, select once for the most recently closed eligible week, even when restarted on another weekday. Do not replay every missed historical week.
- Stable job ID: `community:YYYY-MM-DD`, where the date is the closed week's local Monday. Add the `community` job kind to the existing durable job runner, failure/resume controls and lease system. Exempt this job from the existing stale daily-job skip behavior.
- Snapshot up to 30 eligible repositories with their counts/order at cutoff into the job checkpoint. Derive the initial cutoff from the stable job ID and freeze before any provider I/O; retrying in a later week cannot move the cutoff. Contributions after cutoff do not change this snapshot; they remain available for a later week if the project is still pending.
- Promote at most ten new candidates; if fewer are eligible, send fewer. Check at most the 30 frozen repositories, backfilling past missing/archived or concurrently already-reviewed entries. A later week handles the rest of the backlog.
- Metadata fetch uses the existing bounded GitHub client. Missing or archived repositories are audited and skipped in this batch. Transient provider failures stop resumably without advancing the failed item. Fetch outside transactions.
- Under the existing writer transaction, assert lease, recheck pause/eligibility, create a candidate through `store.save_candidate`, mark its suggestion queued, and advance the checkpoint atomically. A crash or retry cannot create a second candidate or an eleventh promotion. Do not update an existing candidate's revision or assessment.
- Weekly community selection has its own ten-candidate cap and does not consume or increase the automated discovery daily quota. Daily discovery stays unchanged.
- Honor discoveryPaused, budgetPaused, publicationPaused, missing GitHub configuration and failedKinds; preserve/resume the frozen batch. aiPaused alone does not block this deterministic, unpaid workflow. No paid AI calls.
- Candidate assessment records source `community-weekly`, closed week, cutoff, frozen suggestion count and job ID. Use existing metadata and category suggestion rules; unknown type, platform, free-use and license remain unknown. Do not invent eligibility just to make Accept succeed.
- The existing Telegram worker sends the candidates with Open repo / Accept / Reject / More. Preserve owner/chat/revision/pause/NSFW checks. Candidate creation never sends directly or publishes. Telegram being offline must not lose the batch.

## Search service and safety

- New backend router under `/api/community`: `GET /repositories?q=...` and `GET /repository?url=...`. The Next catch-all proxy already supports GET, cookies, Set-Cookie and Retry-After; keep that behavior.
- Search only public repositories, with fixed-host GitHub requests and a server-only token. Treat names/README/metadata as data, never instructions or HTML to execute.
- Cache provider facts for five minutes using namespaced `search_cache` entries. Enrich store/suggestion status after retrieving cached facts so published/pending status is fresh. Cache only successes; disclose incomplete provider results.
- Per address: ten requests/minute for these endpoints. Across all visitors and backend processes: ten uncached provider operations/minute using a durable database bucket. Cache hits do not consume the provider bucket; exact lookup and text search share it. This ceiling reduces contention with discovery but is not a promise that GitHub never throttles shared credentials.
- Return 429 with Retry-After when locally/provider throttled, and a sanitized 503 when unavailable. No raw token-bearing provider error output.

## Persistence and compatibility

- Add migration `0003_community_requests` after `0002_telegram_reviews`, creating `community_suggestions` and `community_contributions`. Existing tables, requests, catalog, reviews and polling offsets survive unchanged.
- Support PostgreSQL and temporary SQLite. Normal startup never silently migrates PostgreSQL. Do not downgrade by deleting suggestion/review history; disable feature and restore a verified backup into a separate database if rollback is needed.
- The Telegram readiness check currently requires exactly revision 0002. Update it to accept 0002 and 0003 while still checking its required tables; an additive migration must not disable the existing bot. Request routes require the new tables and fail clearly if migration is missing.
- Keep existing `POST /api/requests` body `{name, repoUrl, website}` and preserve `{ok:true}` in successful responses. Add status/count fields without breaking the legacy form or proxy.
- Suggestions, pseudonymous contribution records and counts are owner-visible in admin requests; do not expose visitor keys or raw cookie IDs. Add a concise privacy explanation of the anonymous browser identifier and stored suggestions.

## Verification and release boundary

Tests use synthetic GitHub/Telegram transports and disposable PostgreSQL/SQLite, never the current local catalog or a live bot. Verify concurrent deduplication, rename identity, stable ranking, cutoff/DST, missed-run recovery, retry/lease/pause behavior, ten-cap, unchanged daily quota, stale search responses, proxy cookie forwarding and the complete submit-to-review-to-owner-accept path.

This task prepares isolated branches and instructions only. Worker sessions implement and commit their owned files. Integration happens after those branches finish. No deployment, shared local database migration or live bot test is authorized by the planning task.
