# AI integration: merge and review

Scope: initially merge and review the four AI branches on an integration branch. The owner subsequently authorized the confirmed shared-code fixes; those fixes and structural/frontend validation are now complete. Deployment and merging into `main` remain separate actions.

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

Read-only combined review is complete. One independent reviewer inspected the merged production diff, the lane completion notes, the specification, and actual shared consumers. No further confirmed important introduced regression was found beyond the known unfinished integration contracts. The reviewer also identified the separately labeled baseline Settings issue below. The following findings describe the merged revision before remediation; their resolutions are recorded below.

Important findings carried into remediation:

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

At the initial merge/review stage, integration was not ready for `main` until the shared gaps were resolved. Remediation and frontend gates are now complete as recorded below; owner acceptance remains pending.

The reviewer explicitly declined runtime certification of concurrency, PostgreSQL, crash recovery, DST, live GitHub/Jev schemas, actual billing, webhook delivery, prompt-injection resistance, OAuth, and browser behavior. The executor retains these as unverified requirements/limits rather than silently dropping them or treating structural checks as behavioral proof. No application tests were requested or run.

## Remediation

Authorized follow-up: fix the four confirmed issues and the model configuration recommendation on `ai/integration`, starting from `69cd4b4`.

- Discovery's seven pause/disabled exits now return exact `False`; normal completion still returns `None`. The runner's existing observed-pause marker preserves the interrupted checkpoint after an owner unpauses.
- Settings submits its rendered revision. The backend compares that revision under the existing transaction lock before applying any fields or pause flags, rejecting stale forms with a reload/review message.
- Proposal review shows current/proposed free-use eligibility and category names. Approval validates both the proposal revision and the listing revision rendered on the form. It applies cost/categories with source changes through `store.edit_app`, retaining its existing category/publication validation and all unrelated approved fields/overrides. Legacy unknown cost/empty categories retain current values; the UI explicitly describes this behavior.
- Candidate approval and listing edits require an initially unchecked software-type confirmation, enforced in the browser and backend. This is explicit owner confirmation rather than a new metadata default or persisted schema field; existing Python/TypeScript metadata contracts and stored records remain compatible. Existing listings are not retrospectively certified. Confirmation is required on edits as well as initial approval, following the existing content-confirmation form pattern.
- Default/example configuration now pins `jev-1.13.0`. README documents supported identifiers, mutable aliases, model-limit/rate review, retained uncertain charges, and the fact that existing explicit environment values are preserved. No credentials or existing `.env` files were changed.

### Follow-up verification and review

- Syntax compilation and safe imports of all eighteen backend modules: passed after the fixes. Confirmed that configuration resolves to this integration worktree and the absent-environment model default is `jev-1.13.0`. Credentials were disabled and the unused SQLite path was isolated; no application functions or database initialization ran.
- `npm ci --ignore-scripts --no-audit --no-fund`: installed the locked frontend dependencies locally without changing dependency manifests or lockfiles.
- `NEXT_TELEMETRY_DISABLED=1 BACKEND_URL=http://127.0.0.1:9 GITHUB_TOKEN='' TYPESAFE_API_KEY='' DISCORD_WEBHOOK_URL='' npm run build`: passed, including production compilation, built-in TypeScript validation, static generation, and build traces. Backend-dependent routes remain dynamic; no API server or worker was started.
- `npm run typecheck`: passed after the build generated the local Next.js types.
- `git diff --check`: passed after source edits.
- One follow-up read-only review by the integration reviewer verified all five resolutions and their shared consumers. No confirmed introduced regression or incomplete requested fix was found. No further review or application tests were run.

The explicit source-plan no-application-tests policy continues to govern verification. Syntax/import/build checks and code review do not establish runtime concurrency, billing, crash recovery, live OAuth/provider/webhook behavior, or browser form operation. The current GitHub adapter still does not infer cost/category evidence; no new evidence-extraction feature was added.

Remediation and the permitted structural/frontend gates are complete. The integration branch is preserved for owner acceptance; no merge into `main`, push, deployment, or worktree removal was performed.

## Remaining-step closeout

On the owner's request to continue the remaining steps, reconciled the plan with the already completed implementation rather than repeating changes or inventing new scope. Steps 2–4 (shared fixes, provider configuration/documentation, and combined structural/frontend validation) were completed in `7ed321b`. Step 5's verification-limit record is complete above; final landing/acceptance remains an owner decision.

Fresh closeout inspection confirmed all four recorded lane tips are ancestors of integration, all completion notes are present, and production/config/frontend/dependency files still match reviewed and validated `7ed321b` exactly. No new application code or checks requiring application execution were introduced. Updated all twenty-one lane checklist entries from their committed reports and checked the worktree-preservation item; the implementation and integration checklist now reflects the completed work.

No remaining code blocker was identified by the completed follow-up review. The unresolved items are runtime/live-service validation listed above and the owner's choice of local merge, pull request, or keeping the branch. None is silently treated as executed, verified, or accepted. The no-application-tests policy remains in effect.

## Preserved state

`main` and the four implementation branches remain unchanged. The main checkout's existing local `next-env.d.ts` change was not copied into integration. No push, deployment, branch deletion, or worktree cleanup was performed.
