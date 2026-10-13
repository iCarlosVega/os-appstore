# Task 4 completion: weekly selection and review scheduling

Branch: `requests/weekly-review`  
Worktree: `.worktrees/requests-weekly-review`  
Base: `c032bf4bf9884fbedca9812216f221a1911effcf`  
Implementation: `98a25e9` (`feat: schedule resumable weekly community app reviews`)  
Final implementation commit: `a984308` (`fix: preserve weekly review recovery boundaries`)

Task 4 is complete within its isolated lane. Preserve this branch/worktree for Session 5; nothing was merged, pushed or deployed.

## Behavior

- Schedules `community:YYYY-MM-DD` for the latest eligible closed week at Monday 00:05 in the store timezone, with a Monday 00:00 cutoff. Local calendar arithmetic covers both DST transitions. Restarting later catches up the latest week.
- Freezes at most 30 ranked suggestions before GitHub metadata calls and promotes at most ten new candidates per week. Unavailable, archived, identity-changed or concurrently known repositories are audited and skipped, allowing backfill within the evaluation cap.
- Candidate insertion, suggestion queue marker, audit and checkpoint advance share one writer transaction. GitHub calls happen outside it. Lease ownership and eligibility are checked again before commit. Existing candidates/apps are preserved, including rejected decisions.
- Retries retain frozen order, counts and progress. A transient provider failure does not consume its item. Weekly additions do not change the daily discovery quota.
- Honors discovery, budget and publication pauses, missing GitHub configuration and community failure blocks. No AI calls; AI pause alone does not block this deterministic job. Assessments retain GitHub evidence and uncertainty; candidates await existing owner review and never auto-publish.
- Adds `community` to backend/frontend job kinds and supports all six failed job kinds. Existing Telegram preparation remains usable without live delivery. Readiness accepts the additive `0003_community_requests` revision while still checking required Telegram tables; it does not run migrations.

## Review corrections and checkpoint detail

The independent whole-branch review found two important recovery gaps. Both were reproduced with failing regressions and fixed in `a984308`:

1. Claiming an empty canonical community job now saves `{weekStart, cutoff}` before ranking. This pre-ranking identity marker is **not** a frozen batch. It preserves the original week and UTC cutoff if ranking fails and admin retries in a later week, even after a timezone setting change. The first successful ranking replaces it with the plan's complete version-1 snapshot.
2. Superseded unfrozen jobs are skipped across queued, running and paused statuses. This decision rechecks current checkpoint/status and the live community lease under the writer transaction. Old frozen batches remain resumable; active workers are preserved.

Admin's `community:manual:UUID` aliases resolve to the canonical dated job. Its checkpoint and ten-candidate cap remain authoritative; manually starting an already completed week cannot reset them.

## Owned files

- `backend/app/community_weekly.py`
- `backend/app/jobs.py`
- `backend/app/models.py` — job kinds and failure capacity only
- `backend/app/telegram_worker.py` — schema readiness only
- `backend/tests/test_community_weekly.py`
- `backend/tests/test_telegram.py` — readiness regressions and disposable migration reconstruction fixture
- `src/lib/model.ts` — job-kind mirror only
- This completion report

## Verification

Commands actually run from this worktree:

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -p test_community_weekly.py -q
backend/.venv/bin/python -m unittest discover -s backend/tests -p test_telegram.py -q
backend/.venv/bin/python -m unittest discover -s backend/tests -p test_community_weekly.py -k failure_before_snapshot -q
backend/.venv/bin/python -m unittest discover -s backend/tests -p test_community_weekly.py -k superseded -q
backend/.venv/bin/python -m unittest discover -s backend/tests -q
npm run typecheck
git diff --check
```

Initial weekly/readiness tests failed before implementation. The original standalone weekly suite passed 43 tests; Telegram passed 68. The review's retry regression failed then passed on both engines (2 cases); rollover/lease/frozen-batch checks had four failures before the fix, then all six cases passed. Final full discovery passed **119 tests in 25.686 seconds**: 51 weekly and 68 Telegram. TypeScript and diff whitespace checks passed. The reviewer independently ran the original 43 weekly tests.

Database verification used temporary SQLite and uniquely named disposable PostgreSQL 17 instances with guarded destinations, synthetic credentials, mocked provider HTTP and restored guards. No shared local or production database, root environment file, live Telegram bot or shared service was used. The weekly verification containers were removed.

## Required integration gates

- Session 1's `community_requests` implementation/migration is intentionally absent from this branch. Weekly tests inject only the frozen `rank_pending(cutoff, limit)` / `mark_review_queued(repo_id, at)` seam; production candidate, job, lease and audit writes use real disposable databases.
- Session 5 must merge lanes in the approved order and verify actual contribution ranking/counts/cutoff SQL, queue-state persistence and rollback, schema migration preservation, and the complete submission → frozen batch → candidate → mocked Telegram Accept → publication flow.
- Run merged backend/UI/build checks and the disposable UI/proxy smoke required by Task 5. Production configuration, migration, scheduling and Telegram delivery remain later rollout steps.
