# Session 3: Visitor request UI

Branch: `requests/ui`. Worktree: `.worktrees/requests-ui`.

## Required context

Read `AGENTS.md`, `docs/superpowers/specs/2026-10-12-weekly-app-requests-design.md`, then `docs/superpowers/plans/2026-10-12-weekly-app-requests.md`. The user chose separate Codex sessions in these existing worktrees. Implement only your assigned task using superpowers:executing-plans; the approved feature is GitHub suggestions with a weekly top-ten review batch. Do not restart brainstorming or implement the other lanes.

## Shared rules

- Work only on your named branch in your named worktree. Do not create another worktree.
- All sessions share one machine. Never copy root env files/tokens or connect to its current local/production DB. Never run the shared local launchers, migrate DB 55432, start a live Telegram poller or send recommendations.
- Your worktree has its own backend/.venv and node_modules. Tests use temporary SQLite/disposable PostgreSQL, synthetic secrets and mocked provider HTTP. Tests restore environment/connection/socket guards.
- Use the frozen interfaces. Missing cross-lane files are declared dependencies, not permission to invent production stubs or rename contracts. Report a shared blocker in your completion file.
- Preserve all existing candidate decisions and four-button Telegram behavior. No automatic publication, AI calls, deployment or push.
- Commit only owned files. Do not merge another branch or modify another lane's report.

## Your task

Execute **Task 3** of the plan.

Accessible debounced repository selection, exact URL lookup, manual/idea fallback, weekly submission messages, owner-visible counts and privacy explanation.

## Exclusive ownership

- `src/components/request-form.tsx`
- `src/components/repository-picker.tsx`
- `src/lib/community-types.ts`
- `src/lib/backend.ts (Dashboard field only)`
- `src/app/request/page.tsx`
- `src/app/request/request.css`
- `src/app/admin/page.tsx`
- `src/app/about/page.tsx`
- `scripts/verify-community-ui.mjs`
- `docs/superpowers/completions/requests-ui.md`

## Dependencies

Use frozen HTTP fixtures while other lanes finish. Do not edit global CSS, backend, API proxy or package files. Read installed Next docs before editing.

## Finish

Follow the task's fail → implement → pass checks and commit. Write your completion report with branch, final commit, owned files, commands actually run, actual outcomes and remaining integration requirements. Stop after the commit; the integration session merges all lanes after they finish.
