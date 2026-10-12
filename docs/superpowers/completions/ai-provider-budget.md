# Provider and budget completion

Branch: `ai/provider-budget`. Baseline: `3da8229`. Scope: `backend/app/jev.py`, `backend/app/budget.py`, and this note. Public signatures and returned answer/usage shapes are preserved. No shared production files changed.

## Changes

- Validate state, 1–30 question identities, supported `noul`/`choice` types, instructions, and compatible criteria before reserving or calling TypeSafe. Choice criteria permit the documented maximum of 255 options. Reject non-JSON/non-finite request values and requests over 60,000 UTF-8 bytes. Send the serialized snapshot used for validation.
- Require exactly the requested response identities, matching answer types, declared choices, and finite probabilities/confidence in `[0,1]`. Validate supplied choice distributions against criteria, their total, and the selected maximum. Preserve the existing optional confidence/distribution compatibility; distributions are not added to returned answer dictionaries.
- Reject missing usage and usage beyond the 65,536-token reservation bound before settlement. All invalid, partial, timeout, HTTP-error, and unknown-usage paths retain the full reservation. Strict failures raise `ProviderError`; non-strict search falls back through `None`. Disabled/missing-configuration paths still return `None` without paid calls.
- Use integer ceiling arithmetic for both reservation and settlement. Read the configured rate and reserve under the same existing database lock, then retain that rate for settlement. The private `_reserve` helper performs ledger/state writes under its caller's transaction; the public `reserve(amount)` contract remains unchanged.
- Read usage consistently, use one timestamp/month for allowance checking and inserting a reservation, and atomically settle/enforce. Reaching the target exactly now persists the pause and queues its alert immediately. Delivery happens after these transactions commit. Invalid non-integer/bool/negative public amounts cannot enter the ledger.
- Preserve greater-of-hosting-allowance/current-month-actual accounting, all unresolved reservations, UTC month periods, and owner-required pause switches. Settlement and monthly rollover never clear pauses. Reuse SQLite `BEGIN IMMEDIATE` and PostgreSQL advisory locking rather than adding another locking mechanism.

## Provider contract and remaining billing uncertainty

Reviewed primary [model documentation](https://docs.typesafe.ai/models) and [API reference](https://docs.typesafe.ai/api) on 2026-10-11, without authenticated or paid requests. Jev 1.13 documents input-only billing, a combined 64k state/questions input limit, a separate 32k state-plus-longest-question limit, and request-level `usage.input_tokens`. The existing 65,536-token reservation covers the documented combined input limit; the byte limit is a payload bound, not an exact tokenizer count. The provider may reject inputs against its smaller per-question limit; such errors retain the reservation.

Only documented current model identifiers (`jev-1.13.0`, `jev-latest`, `jev-preview`) are enabled by this adapter. Other identifiers fail before spending until their bound is reviewed. Aliases can change remotely; the input limit, token accounting, and configured price are not a guaranteed billing contract for future alias targets or custom agreements. Over-bound reported usage is rejected and retained for owner reconciliation, rather than treated as a valid settlement. No live billing/tokenizer behavior was verified.

## Verification and review

- `backend/.venv/bin/python -m py_compile backend/app/jev.py backend/app/budget.py`: passed.
- `env PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 backend/.venv/bin/python -c 'import backend.app.jev, backend.app.budget; print("Safe imports passed")'`: passed, without database initialization or external calls.
- `env PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 backend/.venv/bin/python -c 'import backend.app.jev, backend.app.budget, backend.app.search, backend.app.discovery, backend.app.jobs, backend.app.admin; print("Safe provider, budget, and consumer imports passed")'`: passed.
- `git diff --check`: passed.
- Reviewed the complete diff and callers in search, discovery, jobs, and admin, plus shared settings/store/database/config/Discord/schema interfaces. Confirmed missing credentials, missing rate/hosting, paused states, invalid questions, missing/extra identities, wrong types/choices, non-finite values, malformed or missing usage, oversized input, exact/insufficient allowance, concurrent reservations/rate edits/settlements, month boundaries, and old-month reconciliation by code inspection only.
- Worktree-local Python environment created. Global Python initially lacked `httpx`; offline `uv pip install ... -r backend/requirements.txt` could not resolve uncached pinned FastAPI. Copied already installed distributions into the local environment without mutating the source environment; metadata confirms all six requirements match their pinned versions. No dependencies or requirement files changed.
- Per the source plans, no application tests, migrations, workers, live provider calls, Discord notifications, or deployment ran. Syntax/import checks and author review do not prove behavioral correctness, HTTP compatibility, PostgreSQL/SQLite concurrency, actual billing, notification delivery, or scheduler integration.

## Shared-file/integration requests

- Configuration/documentation owner: prefer `TYPESAFE_MODEL=jev-1.13.0` for a stable reviewed input bound. Document the supported identifiers, strict missing-usage behavior, and review both pricing and limits before moving a model alias/version. Configured prices still require an accurate owner-supplied contract rate.
- Session 4/integrator: retain `ProviderError` propagation into failed-job checkpoints/pauses, and public search fallback on `None`. Notifications must continue to persist with failed/missing webhook delivery and require explicit retry. No Discord/jobs API changes are required for this lane.
- Integrator: all new direct helper calls hold the database transaction. If future consumers wrap public budget functions in an outer transaction, the current shared database interface has no after-commit callbacks; defer notification delivery until the outer commit. Current reviewed callers do not wrap these public calls.
- Integrator: preserve explicit owner resume after a budget stop, including one caused by an exact-limit in-flight reservation that later settles lower. Verify rollover/concurrency/provider cases behaviorally when authorized, and reconcile retained unknown or over-bound charges against provider billing.

## Execution rulings

- Followed the source plans' explicit syntax/import/review-only policy instead of generic skill testing requirements. Cost: behavior remains unverified.
- Executed and reviewed inline, honoring the parallel plan's prohibition on starting other sessions. Cost: author review is weaker than an independent review.
- Kept the existing optional choice confidence and distribution compatibility, validating distributions when supplied; treated missing billing usage as failure. Cost: this is deliberately narrower than enforcing every field in the provider's current full response schema.

No merge, push, branch deletion, or deployment was performed.
