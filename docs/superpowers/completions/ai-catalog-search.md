# Catalog search completion

Branch: `ai/catalog-search`. Baseline: `3da8229`.
Production ownership: `backend/app/search.py` only.

## Changes

- Retained published-only, in-memory catalog retrieval and the 100-result limit. Added an explicit publication check at the eligibility boundary. Descendant-category, manual platform/type, and confirmed-true attribute filters remain intact.
- Search now includes category display names, strips combining accents consistently, and matches tokens with bounded prefix/typo tolerance instead of arbitrary internal substrings. Short fuzzy queries and stop-word-only queries cannot fabricate name matches. Approved aliases and alternative-product terms remain searchable.
- Capped additive word scores below name relevance. Exact names/approved aliases take precedence before truncation, candidate selection, and after ranking. Popularity remains secondary, deterministic ties use listing ID, and inactive listings are downranked even among zero-score suggestions or Jev ties.
- Jev receives at most 20 current matching listings, with approved aliases, category names, platform/type/attribute facts, filters, and the existing bounded description. `jev.decide` remains the only provider/budget entry point; no second reservation layer was introduced.
- Canonicalized the four supported filter keys for cache reuse. Retained 24-hour expiry and query/filter/revision/model keys; added a ranking-version key to invalidate prior ranking behavior.
- Cached rankings must be complete, duplicate-free permutations of the current eligible published candidate IDs. Corrupt JSON, wrong shapes, missing/extra IDs, and changed candidate sets are cache misses.
- Require complete typed finite scores in `[0,1]` before applying or caching a new ranking. Partial/malformed responses, provider exceptions/timeouts, and cache read/write failures preserve deterministic results. Disabled AI, missing credentials/cost configuration, and AI/budget pauses skip ranking.

## Contracts and reviewed cases

Read the parallel plan, original Task 3, visitor/search/budget sections of the spec, migration verification policy, provider/config/models/store/database, `/api/search`, the TypeScript client, and catalog UI. The only production caller is `main.catalog_search`; the HTTP/client contracts need no changes.

Preserved `search_catalog(query="", filters=None, use_ai=True)` and result fields:

- `items`: at most 100 published listings satisfying manual filters; Jev only reorders the first 20 deterministic matches.
- `related`: true for a nonempty normalized query without deterministic matches; those items are suggestions, not matches. The existing UI already labels suggestions and offers the app-request link.
- `mode`: `catalog` for deterministic/fallback results, `Jev` only after a validated ranking is applied.
- `total`: all deterministic matches before truncation; zero for suggestions.

Code-review cases (not executed application tests): empty/whitespace/punctuation input, internal 200-character clamp and existing HTTP length rejection, exact/former names and accents, alternative-to product queries, category names with unrelated IDs, multiword typos, short/generic/unrelated queries, nested category filters, unsupported category/platform/type/attribute values, true/false/null attributes, inactive and high-star competitors, more than 100 matches, more than 20 candidates, empty catalogs, and distinct suggestion IDs.

Also reviewed disabled/missing/paused AI, missing cost configuration, `None`/partial/wrong-type/boolean/string/nonfinite/out-of-range scores, extra provider keys (unused), provider exceptions, corrupt/non-list/duplicate/private/stale cached IDs, changed query/filter/revision/model, expiry, and cache failures. No visitor path performs external repository search.

## Verification

- `/Users/carlosvega/Documents/Projects/os-appstore/backend/.venv/bin/python -m py_compile backend/app/search.py`: passed.
- `git diff --check`: passed.
- Safe import with `PYTHONPATH=backend`, `PYTHONDONTWRITEBYTECODE=1`, `APP_ENV=development`, empty `DATABASE_URL`/`TYPESAFE_API_KEY`/`GITHUB_TOKEN`/`DISCORD_WEBHOOK_URL`, and `SQLITE_PATH=/private/tmp/ai-catalog-search-import-only.sqlite`, using the existing main checkout's virtual-environment interpreter: passed. `from app import search` resolved to this worktree and `inspect.signature(search.search_catalog)` printed `(query='', filters=None, use_ai=True)`. No search, database initialization, worker, or provider call was executed.
- Initial dependency probe using system `python3` failed with `ModuleNotFoundError: httpx`; reused the existing virtual environment without installing or changing dependencies.
- Final self-review against the lane requirements and full owned diff: no outstanding blocking findings. No independent reviewer/session was started, following the parallel plan.

## Decisions, shared requests, and limits

- Followed the handoff/source plans' explicit no-application-tests policy over skill test gates. Search behavior, ranking quality, and failure paths are reviewed rather than runtime proven.
- Followed the parallel plan's prohibition on other sessions; review was performed by the author. No merge, push, deployment, live notifications, paid calls, or worktree cleanup is part of this lane.
- No required shared/API fixes identified. Provider/budget, persistence, schema, configuration, HTTP limits, frontend, and dependencies were not modified.
- Retained the approved initial in-memory retrieval approach. Catalog-scale performance and live SQLite/PostgreSQL, concurrent publication/cache invalidation, provider billing, and HTTP integration remain unverified. Large candidate evidence can exceed the provider's existing 60 KB request guard and fall back deterministically.
