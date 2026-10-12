# Session 1: Jev provider and budget

Read the parallel plan, original Task 3, and the spec's Jev and budget sections. The migration has already ported these modules; assess and complete real gaps.

**Branch:** `ai/provider-budget`.
**Own:** `backend/app/jev.py`, `backend/app/budget.py`.
**Completion note:** `docs/superpowers/completions/ai-provider-budget.md`.

Preserve `decide(state, questions: dict, strict=False)`, `ProviderError`, typed response models, and existing budget function signatures. Search and discovery develop concurrently against these contracts. The existing adapter uses typed `noul` and `choice` decisions; do not substitute free-form generation.

Review required answer identities, finite valid scores, declared type/choice compatibility, question/request size limits, conservative upper-bound reservations, and complete validation before settlement. No missing credentials/rates or paused-state path may call the provider. Strict failures must propagate appropriately to jobs; public search retains fallback.

Review atomic allowance checks under concurrency, configured hosting allowance/actuals, integer microdollars, monthly periods, and uncertain charges. Timeouts, HTTP errors, invalid/partial responses, or absent usage must retain conservative reservations. Rollover must not silently clear an owner-response-required pause. Confirm whether the configured reservation bound actually bounds the billed request; record any unresolved billing-contract uncertainty.

Read shared store/db/models/config/Discord interfaces without modifying them. Session 4 owns notification delivery and jobs; record shared-state changes needed for integration. Do not add dependencies or a new framework. Consult primary provider documentation if implementation requires verifying an uncertain external contract; do not make paid calls.

Use syntax checks on owned files, safe imports if dependencies/config allow, and targeted code review. No application tests unless requested, following the source plans. In the completion note list actual changes, commands/results, reviewed failure cases, shared-file requests, and unverified behavior. Commit owned files and this unique completion note only. If already complete, document the assessment without manufactured changes.
