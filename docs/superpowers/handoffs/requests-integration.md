# Session 5: Integration and verification

Branch: `requests/integration`. Worktree: `.worktrees/requests-integration`.

Read `AGENTS.md`, `docs/superpowers/specs/2026-10-12-weekly-app-requests-design.md`, `docs/superpowers/plans/2026-10-12-weekly-app-requests.md`, and the four lane reports in `docs/superpowers/completions/requests-*.md` after merging their branches. Execute **Task 5** using superpowers:executing-plans.

Start only after all four development sessions finish and commit. Confirm their branches are clean/finished; do not interrupt them, merge incomplete work or manufacture their reports. Merge in this order:

```bash
git merge --no-ff requests/data-api
git merge --no-ff requests/github-search
git merge --no-ff requests/ui
git merge --no-ff requests/weekly-review
```

Register `community_github.router` exactly once in main.py. Resolve actual contract/merge problems after all workers have stopped; document them. Run real migrated disposable-DB integration tests rather than accepting four independently mocked seams as complete evidence.

You own integration tests, README runbook sections and `docs/superpowers/completions/requests-integration.md`. Run the full backend suite, UI verifier, typecheck and build. Verify anonymous-cookie roundtrip through Next's proxy, top-ten cutoff/DST/catch-up, crash/concurrent-worker safety, legacy requests, unchanged daily quota, preserved Telegram schema/review behavior and owner-only publication.

The root develop checkout was intentionally left dirty. Its current edits were snapshotted in baseline 061206cb84a59399617bb4b785e7d468edf49229, then planning documents committed on this branch. Review later root edits before any future merge; do not reset/stash/commit the root's work on the user's behalf.

No root credential copies, shared local services/migrations, real suggestions, live bot messages, deployment, push or merge to develop/main. Finish with a committed report identifying readiness and remaining release steps.
