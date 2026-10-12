# Maintenance/jobs execution record

Plan: `docs/superpowers/plans/2026-10-11-ai-agent-parallel.md`, Task 4.
Handoff: `docs/superpowers/handoffs/ai-maintenance-jobs.md`.
Branch: `ai/maintenance-jobs`. Starting commit: `3da8229`.

## Progress

- [x] Verify isolated worktree and read handoff, specification, shared plan, and final migration interfaces.
- [x] Trace worker/CLI, discovery checkpoint, GitHub metadata, admin resume/proposal/retry, budget, database transaction, and notification consumers.
- [x] Complete demonstrated maintenance, scheduling, lease, digest, and delivery gaps in the three owned modules.
- [x] Run syntax and safe import checks.
- [x] Finish the fresh-context read-only review and address material findings.
- [x] Commit scoped changes and report integration requests and verification limits.

## Pre-flight and rulings

- Session 3 consumes `JobContext` and supplies `Metadata`: preserve fields/signatures and the `completed`, `urls`, `index`, and `incomplete` checkpoint keys. Session 1 consumes Discord queue/delivery and owns budget pause state. Admin and CLI are read-only consumers for this lane.
- Ruling: follow the handoff's explicit no-application-test policy instead of the execution skill's default TDD workflow. Use syntax/import checks and static review, and do not claim behavioral verification. Cost: concurrency, restart, DST, and provider behavior lack executable regression coverage.
- Ruling: use this uniquely owned completion file as the execution ledger rather than adding shared plan/scratch files. Cost: progress and final report live together; no other lane is modified.
- Ruling: current GitHub metadata defaults `costModel` to `Needs review` and `categories` to an empty list, without upstream evidence. Treat those defaults as unknown rather than factual changes; retain approved values and queue only supplied non-default cost/category changes. Cost: detecting upstream loss of free-use/category evidence needs a richer adapter contract during integration.
- Ruling: a worker may return the exact value `False` to report stopping for a pause; ordinary `None` remains a compatible completion result. Maintenance supplies the signal and `execute` consumes it, including a forward-compatible signal from discovery. Cost: discovery must adopt the signal in its own lane to close its equivalent pause/unpause race; its code remains outside this lane.

## Evidence before editing

- Maintenance loops over the whole catalog despite `repositoryLimit`; it fetches newest-updated apps first, with no bounded oldest-first refresh.
- Maintenance checks pause controls before fetching but not when committing the returned metadata; it never records refresh star snapshots.
- Proposals compare identity/URL/license only. Admin's proposal approval also applies only identity/URL/license/attribution/source fields: extending cost/category proposals requires a shared admin integration change.
- `JobContext.checkpoint` validates the lease and writes in separate transactions when called outside an existing transaction. Heartbeats can extend expired leases. Stale queued-run skipping does not condition its write on the run still being queued.
- `execute` checks pause/failed controls only in its scheduler caller, does not clear a paused run's prior finish timestamp on claim, and parses checkpoints before its failure/pause handler.
- Digest omits uncertainty and recent runs; long candidate names can truncate its final admin link. Digest enqueue and job checkpoint are unrelated, allowing a restart to enqueue the same digest again.
- Notification delivery reads an unsent row without claiming it, allowing overlapping explicit retry requests to send twice.

## Verification

- Syntax compilation using the worktree-local Python 3.14.6: all three owned modules passed.
- `PYTHONPATH=backend backend/.venv/bin/python -B`: imported `app.maintenance`, `app.jobs`, and `app.discord`; confirmed configuration resolves to this worktree. No database initialization or external calls were performed.
- Confirmed all six direct dependencies match `backend/requirements.txt` exactly. A standalone worktree virtualenv contains a copy of the already-installed dependency snapshot; the main environment was not modified. The first uv attempt was blocked by its global cache permissions; using the worktree's `.data/uv-cache` allowed isolated virtualenv creation.
- AST compatibility check against `3da8229`: every existing top-level function and class method signature remains unchanged across the three owned modules (1 maintenance, 6 jobs, 3 Discord).
- `git diff --check`: passed after implementation.
- No application tests, live webhooks, GitHub/provider calls, database migration, or scheduled worker execution were run, following the handoff policy. Compilation/imports establish structural validity, not behavior.

## Implemented behavior

- Maintenance selects oldest-updated eligible listings first and caps the run by `repositoryLimit`, counting its existing `completed` checkpoint entries. Missing repositories rotate by their check attempt's database update time without fabricating a successful source timestamp.
- Recheck pause controls and current approved repository identity inside the write transaction after both successful and missing-repository fetches. Stale fetches cannot overwrite an owner's intervening repository edit.
- Preserve approved facts and overrides; retain known requirements when the adapter has no replacement evidence. Record actual upstream star observations only for the approved repository ID.
- Explicit upstream cost/category changes join identity/URL/license proposals; defaults without evidence do not erase approved values. Unchanged proposals, including rejected ones, do not repeatedly reopen.
- Checkpoint validation/write and heartbeat renewal use the existing serialized database transaction. Expired leases cannot be renewed; stale queued-run skipping is conditional on the row still being queued.
- Recheck failure and pause controls inside run acquisition, clear old finish timestamps, and route malformed persisted checkpoints through durable failure/pause handling. Failure notifications are enqueued atomically with failed status/settings before delivery.
- Preserve an observed maintenance pause even if the owner unpauses before final status is recorded, preventing a partially processed checkpoint from being marked complete.
- Digest includes uncertainty, up to five recent runs, bounded candidate names, provider cost totals, and an admin link before optional detail. A digest's durable `notificationId` checkpoint reuses its existing notification after interruption.
- Notification retry claims a per-notification lease before HTTP delivery and settles/releases it only while still its owner. Missing configuration retains the queue; delivery errors remain visible without recursive alerts. Exactly-once delivery is not claimed: a crash after Discord accepts a request, or an expired in-flight delivery, may still cause duplication on a later explicit retry.

## Reviewed baseline behavior retained

- America/New_York defaults and local-date run identities remain unchanged; repeated local clock times reuse the same ID, and skipped spring-forward times are picked up by the existing `clock >= scheduled` comparison.
- Interrupted `running`/`paused` runs retain their checkpoint across midnight; only still-queued daily runs can be skipped as stale.
- Failed job kinds stay gated by `failedKinds` until explicit admin resume; budget/manual pause controls remain authoritative. Maintenance and priority keep their shared lease without introducing a global pause for unrelated failures.
- Same-ID canonical URL/license changes retain approved source fields; a different repository ID still cannot supply public version/requirements/stars/activity updates. Missing repositories retain approved data and queue one availability transition alert.
- Archived/12-month inactivity remains the GitHub adapter's factual condition, respects condition overrides on routine refresh, and does not delete or unpublish apps.

## Integration requests

- Extend revision-aware admin proposal review/approval to handle `costModel` and `categories`, validating categories and preserving other approved/overridden fields. This lane cannot modify `backend/app/admin.py` or review UI files.
- Review discovery's per-day additions at midnight: the worker preserves the existing `JobContext.local_day` invocation contract; a long-running discovery invocation must not assume its date remains current for every persistence step.
- Discovery's pause exits must return `False` so `execute` preserves interrupted work even if pause controls are cleared before finalization. Its current implicit `None` exits retain the baseline pause/unpause race until its lane adopts this optional result signal. Normal completion continues to return `None`.

## Final review

One fresh-context, read-only reviewer inspected the three owned modules and their shared consumers. No confirmed introduced regression was found. The reviewer identified one retained in-scope Important issue: a transient pause followed by unpause could mark unfinished maintenance complete. Fixed in one pass with the optional `False` worker result above. The reviewer confirmed the admin proposal and discovery midnight/pause integration gates; they remain outside this lane's ownership. No second review or application tests were run.

The reviewer declined runtime certification of concurrency, DST, provider behavior, and crash recovery. These remain explicitly unverified under the handoff's compilation/import/code-review policy rather than being treated as passing.

## Limits

The final code review and compilation checks do not prove live delivery, concurrent PostgreSQL behavior, DST execution, or crash recovery. The admin and discovery integration requests above remain required before end-to-end completion can be claimed.

## Delivery

Implementation commit: `0b73cfd` (`fix: harden maintenance jobs and notification delivery`). Only the three owned production modules changed in that commit. After the final pause fix, syntax compilation, worktree-local safe imports, existing argument-signature compatibility, branch/file ownership checks, and `git diff --check` all passed again.

The `ai/maintenance-jobs` branch and its worktree are preserved for integration. No merge, push, deployment, or worktree removal was performed.
