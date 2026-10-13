# Telegram approval worktree preparation

Prepared 2026-10-12 on `develop`. Feature implementation is assigned to three independent Codex sessions; no Telegram feature code, bot setup, messages or candidate publication was performed during preparation.

## Frozen starting point

All three branches start at the commit identified by local tag `telegram-approvals-baseline-2026-10-12`. Resolve its SHA with `git rev-parse telegram-approvals-baseline-2026-10-12`. Do not rebase onto moving `develop` during implementation. The baseline includes the previously pending app-detail centering change, committed as `8f41500`.

| Session | Branch | Absolute worktree path | Read this handoff |
| --- | --- | --- | --- |
| 1 | `telegram/review-core` | `/Users/carlosvega/.codex/worktrees/a049/os-appstore` | `docs/superpowers/handoffs/telegram-review-core.md` |
| 2 | `telegram/bot` | `/Users/carlosvega/.codex/worktrees/a16d/os-appstore` | `docs/superpowers/handoffs/telegram-bot.md` |
| 3 | `telegram/runtime` | `/Users/carlosvega/.codex/worktrees/4f19/os-appstore` | `docs/superpowers/handoffs/telegram-runtime.md` |

These are native Codex-managed worktrees under `~/.codex/worktrees`, each on its named Git branch. Existing worktrees were retained; none were deleted or repurposed. The root checkout stays on `develop` with its services untouched.

## Launch one terminal per session

Session 1:

```sh
cd /Users/carlosvega/.codex/worktrees/a049/os-appstore
codex
```

Paste:

> Read `docs/superpowers/handoffs/telegram-review-core.md` and every spec/plan/preparation document it references. Implement Task 1 only using superpowers:executing-plans. Follow frozen contracts, exclusive ownership and the no-application-tests policy. No root env/DB access, running services, live APIs, migrations, messages, publication or production changes. Commit owned files and `docs/superpowers/completions/telegram-review-core.md`; report shared blockers. Do not merge or deploy.

Session 2:

```sh
cd /Users/carlosvega/.codex/worktrees/a16d/os-appstore
codex
```

Paste:

> Read `docs/superpowers/handoffs/telegram-bot.md` and every spec/plan/preparation document it references. Implement Task 2 only using superpowers:executing-plans. Follow frozen contracts, exclusive ownership and the no-application-tests policy. No root env/DB access, running services, live APIs, migrations, messages, publication or production changes. Commit owned files and `docs/superpowers/completions/telegram-bot.md`; report shared blockers. Do not merge or deploy.

Session 3:

```sh
cd /Users/carlosvega/.codex/worktrees/4f19/os-appstore
codex
```

Paste:

> Read `docs/superpowers/handoffs/telegram-runtime.md` and every spec/plan/preparation document it references. Implement Task 3 only using superpowers:executing-plans. Follow frozen contracts, exclusive ownership and the no-application-tests policy. No root env/DB access, running services, live APIs, migrations, messages, publication or production changes. Commit owned files and `docs/superpowers/completions/telegram-runtime.md`; report shared blockers. Do not merge or deploy.

## Instructions and dependency boundaries

- Design: `docs/superpowers/specs/2026-10-12-telegram-approvals-design.md`.
- Tasks, contracts and later merge order: `docs/superpowers/plans/2026-10-12-telegram-approvals-parallel.md`.
- Each lane owns distinct files and its completion report. Core, bot and runtime may be implemented concurrently; missing modules from other lanes are expected until integration. Do not create cross-lane stubs or alter shared contracts independently.
- Install only existing declared dependencies in each worktree's own environment if needed. No ignored env, tokens, local database, `.data`, root `.venv` or `node_modules` was copied or symlinked. Tracked example env files are present with placeholders.
- Compile/safe-import/configuration inspection is authorized. Application tests remain unrequested. Do not launch workers, connect to live databases or call Telegram/GitHub. Dependency installation alone may access the package registry.
- Future integration order: review-core → bot → runtime on a separate `telegram/integration` branch from the frozen baseline. Then review combined behavior and request authorization for disposable behavioral checks before activation. No automatic production deployment.

## Preparation evidence

The plan received an independent read-only review. Four gaps were fixed before freezing: exact token/decimal representation; immutable assessment data for uncertainty flags; safe transport errors and nonblocking replay recovery; bot-scoped polling lease. The reviewer found no remaining material contract gap in the revisions.

Preparation verification checks Git whitespace, branch/path mapping, a common baseline, clean worktree state, instruction files in each checkout and absence of copied private env/data/dependencies. No application tests, live schema changes, service restarts or Telegram API calls were executed.
