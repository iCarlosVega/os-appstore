# AI integration: merge and review

Scope: owner-requested step 1 only — merge and review the four AI branches on an integration branch. Shared-code remediation, frontend build gates, deployment, and merging into `main` remain separate steps.

Branch: `ai/integration`.
Worktree: `/Users/carlosvega/.codex/worktrees/2fe3/os-appstore` (created through the native worktree tool).
Common baseline: `3da822989c36151d8d9d8d09db68d7c7a33b52be`.
Combined code revision reviewed: `6c16ba8f4cdd855825f17e2266ad980f4efb7fec`.

## Merge record

| Order | Source branch | Source tip | Merge commit |
| --- | --- | --- | --- |
| 1 | `ai/provider-budget` | `5abfd72` | `7804f80` |
| 2 | `ai/catalog-search` | `f475c25` | `b883afc` |
| 3 | `ai/discovery` | `50091f7` | `384bb46` |
| 4 | `ai/maintenance-jobs` | `ce8850f` | `6c16ba8` |

All four merges used `--no-ff` and completed without conflicts. Each branch changes only its owned production files and completion note. All twelve merged files match their source branch exactly; no merge resolution changed production code. Each source tip is an ancestor of the integration revision, and first-parent history confirms the requested order.

## Verification

- Compiled all eighteen `backend/app/*.py` modules in memory and safely imported them from the integration worktree with credentials disabled and an isolated unused SQLite path. No database initialization or application functions were invoked.
- Created an independent integration virtualenv and copied the installed dependency snapshot without changing or sharing another worktree's mutable environment. Confirmed all six direct dependency versions match `backend/requirements.txt`.
- Checked branch ancestry, exact merge order, per-lane file ownership, and byte equality of each merged file with its source branch: passed.
- Compared existing function/method arguments against the baseline across all eight changed production modules: all twenty-five existing signatures are unchanged.
- `git diff --check 3da8229..HEAD`: passed before the review report changes.
- An initial dependency metadata check used the extras-bearing name `psycopg[binary]`; corrected the verification script to inspect the distribution name `psycopg`, then the dependency and merge checks passed. This was a check-script issue, not an application failure.
- No application tests, database initialization/migrations, scheduled workers, paid calls, GitHub requests, Discord notifications, or frontend build ran in this step. The source plan explicitly permits syntax/import/code review only unless the owner requests application tests.

## Review and integration requests

Read-only combined review is complete. One independent reviewer inspected the merged production diff, the lane completion notes, the specification, and actual shared consumers. No further confirmed important introduced regression was found beyond the known unfinished integration contracts. The reviewer also identified the separately labeled baseline Settings issue below. All fixes remain outside this merge/review-only step.

Important findings to carry into step 2:

1. **P2, known integration contract — proposal review/application.** Admin review and approval must display and apply cost-model/category proposals, validate categories and publication eligibility, and preserve approved values/overrides. `backend/app/admin.py:180` currently applies source identity/attribution fields only; `src/app/admin/page.tsx:22` displays repository/license changes only. Approving such a proposal would mark it approved without applying those fields. Reachability qualification: today's GitHub adapter supplies unknown cost and empty categories, which maintenance preserves, so this is an unfinished expanded contract rather than a claim that ordinary current GitHub responses already generate these changes.
2. **P2, known pause contract — interrupted discovery can be marked complete.** Discovery pause/disabled early exits must return the exact value `False`. `backend/app/jobs.py:87` consumes that marker, but discovery currently exits with implicit `None` at lines 18, 47, 57, 68, 82, 106, and 115. A pause followed by unpause before finalization can mark partial discovery complete, preventing its checkpoint from resuming. Retain `None` for ordinary completion.
3. **P2, additional baseline finding — stale Settings can clear a newer budget stop.** `backend/app/admin.py:109–119` applies all submitted pause switches without comparing a rendered settings revision; `src/app/admin/page.tsx:25` submits no revision. A page opened before a budget stop can later save seeds/timezone with old unchecked controls, clearing the newer stop. A refused reservation, or an exact-limit reservation that later settles lower, leaves spending below target, so `budget.enforce()` does not restore that stop. Smallest fix: submit the settings revision and reject stale saves under the existing transaction before applying switches. This defect predates the lanes; the new exact-limit reservation pause adds another trigger.
4. **P2, known baseline metadata gap — unsupported software-type default.** New candidates need an unknown software-type representation or explicit type confirmation before publication. `backend/app/models.py:74` defaults to `Desktop app`, GitHub supplies no type evidence, and `src/components/metadata-editor.tsx:5` preselects it without explicit confirmation. Owner approval can publish that unsupported factual default. Keep Python/TypeScript contracts aligned when fixing this.

Discovery's cross-midnight quota request is resolved by the discovery branch: it calculates the current local insertion date inside the serialized persistence transaction (`backend/app/discovery.py:120`). Preserve the additional saved checkpoint mapping and fields on resume.

**P3, known configuration follow-up:** provider configuration/documentation should prefer the reviewed stable `jev-1.13.0` identifier over the current `jev-latest` default (`backend/app/config.py:26`, `.env.example:19`) and explain supported models, limits, and owner-configured prices. The current adapter accepts the alias; no present billing failure was established. A future alias change can invalidate the reviewed reservation bound.

## Confirmed combined contracts

- Search and discovery use question/answer shapes accepted by the merged Jev adapter. Non-strict search retains deterministic fallback; configured strict discovery failures reach durable failed-job/pause handling.
- Current budget callers and maintenance/job notification callers deliver after their outermost transaction commits. No introduced nested-transaction delivery defect was found.
- Discovery's additive saved checkpoint mapping survives persistence/resume through `JobContext`; its insertion-day quota is recalculated inside the locked write.
- GitHub/maintenance retain approved repository identity boundaries and routine owner overrides. No API routes, shared schema, dependencies, or frontend contracts changed in the four lane merges.

## Assessment and verification limits

Merge/review step complete; integration is **not ready for `main`** until the shared gaps are resolved. Frontend type checking/build and combined validation remain later plan gates.

The reviewer explicitly declined runtime certification of concurrency, PostgreSQL, crash recovery, DST, live GitHub/Jev schemas, actual billing, webhook delivery, prompt-injection resistance, OAuth, and browser behavior. The executor retains these as unverified requirements/limits rather than silently dropping them or treating structural checks as behavioral proof. No application tests were requested or run.

## Preserved state

`main` and the four implementation branches remain unchanged. The main checkout's existing local `next-env.d.ts` change was not copied into integration. No push, deployment, branch deletion, or worktree cleanup was performed.
