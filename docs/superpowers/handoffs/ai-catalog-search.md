# Session 2: Catalog search and Jev ranking

Read the parallel plan, original Task 3, and the spec's visitor/search sections. Complete actual gaps in the Python search port.

**Branch:** `ai/catalog-search`.
**Own:** `backend/app/search.py`.
**Completion note:** `docs/superpowers/completions/ai-catalog-search.md`.

Preserve `search_catalog(query="", filters=None, use_ai=True)` and public `items`, `related`, `mode`, `total` semantics. Read the final baseline's API/client consumers to confirm exact result values; do not change them. Session 1 owns provider and budget. Consume `jev.decide` without changing its contract or adding a second reservation layer.

Review published-only retrieval, names/approved aliases/alternative-product terms, basic typo tolerance, descendant categories, manual platform/type filters, and confirmed-true attributes. Unknown attributes must not match. Relevance dominates popularity, exact names stay preferred, and inactive listings are downranked. Review empty, long, and no-match queries and distinct labeled suggestions.

Keep at most 20 Jev candidates per request and a 24-hour cache keyed by normalized query, filters, catalog revision, and model configuration. Validate cached/ranked IDs against the eligible published set. Disabled AI, unavailable credentials, budget pauses, timeouts, malformed/partial decisions, and provider errors must leave deterministic search usable. Preserve existing result limits unless the spec requires a demonstrated correction.

Do not add external repository search to visitor queries. Do not modify provider/budget, persistence, HTTP rate limits, frontend, schema, or dependencies. Report any required shared/API fixes for integration; the integrator owns those files.

Use syntax checks, safe imports, and code review. No application tests unless requested, following the source plans. Record actual changes, commands/results, reviewed cases, shared requests, and verification limits in the completion note. Commit only owned changes and the unique note. A documented no-op is valid if behavior already satisfies the plan.
