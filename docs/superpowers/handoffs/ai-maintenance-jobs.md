# Session 4: Maintenance, durable jobs, and Discord

Read the parallel plan, original Task 4, and the spec's maintenance, schedules, administration/Discord, and budget sections. Complete real gaps in the existing port.

**Branch:** `ai/maintenance-jobs`.
**Own:** `backend/app/maintenance.py`, `backend/app/jobs.py`, `backend/app/discord.py`.
**Completion note:** `docs/superpowers/completions/ai-maintenance-jobs.md`.

Preserve `maintain(job, priority_only=False)`, `JobContext` fields and `assert_lease()`/`checkpoint(data)`, `run_due_jobs()`, `execute(job_id, kind, local_day)`, and Discord `queue`/`deliver`/`notify`. Preserve durable checkpoint keys. Session 3 develops discovery against that JobContext and owns the GitHub adapter; Session 1 owns budget behavior. CLI and admin consumers remain integrator ownership.

Review factual refreshes and explicit owner overrides. Transfers/renames with the same repository ID require review before changing the public canonical link; a distinct repository ID cannot supply routine public updates while identity review is pending. License/free-use/category changes stay proposals. Missing repositories retain approved data and need owner attention. Archived or 12-month-inactive projects are downranked, not silently removed.

Review defaults in America/New_York: discovery daily 02:00, maintenance Sunday 03:00, priority maintenance daily 03:00, digest Monday 09:00, and the existing backup integration daily 03:30. Preserve local schedule identities across restarts/DST, DB-backed exclusion and leases, and checkpoint recovery across midnight. Interrupted runs must not be discarded as never-started stale work. Recheck lease ownership before writes.

Failed runs pause only their affected type unless a global/budget pause applies. Pauses requiring owner response persist through rollover/restart. Retrying or resuming must be explicit. A failed Discord delivery stays durable and retryable without recursively queuing alerts; absent credentials leave notifications visible. Digests summarize pending/uncertain candidates, changes, requests, runs, and spending, with protected admin links.

Do not modify discovery/GitHub, provider/budget, database/models/store, CLI/admin, schema, backup code, dependencies, or deployment. Record shared integration requests, including admin retry/resume behavior, in your completion note. No webhook calls or real worker runs during validation.

Use syntax checks, safe imports, and code review. No application tests unless requested. Record changes, commands/results, reviewed cases, shared requests, and unverified concurrency/DST/provider behavior. Commit owned files and your unique completion note only. Do not invent changes if already complete.
