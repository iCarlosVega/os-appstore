# Starting the weekly app-request sessions

Open four separate terminal tabs and run one command in each. `-C` pins Codex to an existing worktree; do not append `--worktree`. Each handoff contains the full context, ownership and tests. No env files or live services are required for development tests.

## Session 1 — Request persistence and submission API

```bash
codex -C "/Users/carlosvega/Documents/Projects/os-appstore/.worktrees/requests-data-api" "Read AGENTS.md and docs/superpowers/handoffs/requests-data-api.md. Implement your assigned task from the referenced plan, run the required safe tests, write the completion report, and commit only your owned files. Do not merge or deploy."
```

## Session 2 — GitHub repository search

```bash
codex -C "/Users/carlosvega/Documents/Projects/os-appstore/.worktrees/requests-github-search" "Read AGENTS.md and docs/superpowers/handoffs/requests-github-search.md. Implement your assigned task from the referenced plan, run the required safe tests, write the completion report, and commit only your owned files. Do not merge or deploy."
```

## Session 3 — Visitor request UI

```bash
codex -C "/Users/carlosvega/Documents/Projects/os-appstore/.worktrees/requests-ui" "Read AGENTS.md and docs/superpowers/handoffs/requests-ui.md. Implement your assigned task from the referenced plan, run the required safe tests, write the completion report, and commit only your owned files. Do not merge or deploy."
```

## Session 4 — Weekly selection and review job

```bash
codex -C "/Users/carlosvega/Documents/Projects/os-appstore/.worktrees/requests-weekly-review" "Read AGENTS.md and docs/superpowers/handoffs/requests-weekly-review.md. Implement your assigned task from the referenced plan, run the required safe tests, write the completion report, and commit only your owned files. Do not merge or deploy."
```

## Session 5 — integration, after all four finish

```bash
codex -C "/Users/carlosvega/Documents/Projects/os-appstore/.worktrees/requests-integration" "Read AGENTS.md and docs/superpowers/handoffs/requests-integration.md. The four development sessions are finished. Merge their branches in the specified order, complete Task 5 and its verification, write and commit the integration report. Stop before merging to develop or deploying."
```

Do not start Session 5's integration command until Sessions 1–4 have completed. All branches start from one common snapshot plus this plan. The original develop checkout and its uncommitted changes remain preserved.
