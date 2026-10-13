# Telegram review core completion

Completed 2026-10-12 in `/Users/carlosvega/.codex/worktrees/a049/os-appstore`, branch `telegram/review-core`.

Implementation commit: `2758045` (`feat: add durable Telegram review core`). This report is committed separately after that implementation. Frozen baseline: `7f97d34e70b55d1248babcfb5628484b659c2d22` (`telegram-approvals-baseline-2026-10-12`). No merge, push or deployment performed; worktree retained for integration.

## Owned files

- `backend/app/telegram_review.py`: frozen `ReviewView` and seven service functions, without network calls, direct configuration access or import-time database work.
- `backend/alembic/versions/0002_telegram_reviews.py`: additive revision after `0001_initial`, defining exactly `telegram_reviews`, `telegram_state` and the ordinary `telegram_reviews_lookup` index. Destructive downgrade refuses with disabling/backup recovery guidance.
- `docs/superpowers/completions/telegram-review-core.md`: this report.

No store/admin/models, baseline/helper migrations, configuration, bot/runtime, frontend, dependencies or other lane reports changed.

## Implemented behavior

- Owner/private-chat ID binding, exact 22-character random tokens, strict integer/action/value validation, canonical decimal option indices and bounded draft versions.
- Immutable original metadata and assessment snapshots; fixed, sorted category options, `models.TYPES` and the two allowed cost models. All four required confirmations begin false, even when discovery suggests values.
- At most five unsent open reviews per preparation call, ordered by candidate update time then repository ID. Global writer locking serializes open-review creation. Stale candidates and seven-day expiry invalidate old open records; still-pending candidates can receive fresh tokens after expiry.
- Every field action rechecks candidate status/revision and increments draft version. A button version mismatch returns `stale` with the current review while leaving a current open draft intact. Terminal review replay precedes version checks.
- Untouched optional metadata and existing overrides survive. Newly added overrides reflect final selected values that differ from the immutable original, matching web administration. Known NSFW content cannot be cleared or approved through Telegram.
- Publication requires explicit category/type/cost/safe confirmation and the existing store publication/category validation. Publication pause remains authoritative. Approval/rejection call only existing store functions; domain changes, terminal review state and Telegram owner/repository/token/outcome audit share one transaction. Store/audit failures propagate for rollback.
- Delivery recording and `reset_delivery` compare-and-clear under the writer lock. Terminal reviews and mismatched/newer message IDs are not cleared. A missing owner-bound reset target is a safe no-op; malformed inputs fail before access.
- Polling state accepts only canonical `telegram:<bot_id>:<owner_user_id>:<chat_id>` scopes and advances monotonically under the same writer lock. Bot credentials are never persisted.

## Checks actually run

Created this worktree's own ignored `backend/.venv` with Python 3.14.6 and installed only existing `backend/requirements.txt` dependencies. No root environment, database, credentials or dependency environment copied or shared.

| Check | Result |
| --- | --- |
| `backend/.venv/bin/python -m compileall -q backend/app/telegram_review.py backend/alembic/versions/0002_telegram_reviews.py` | Exit 0, including after the review correction. |
| Safe imports of `app.telegram_review` and `backend.app.telegram_review` | Passed with SQLite, psycopg, SQLAlchemy engine connections and socket connections blocked; dotenv file loading disabled. Zero attempted connections. |
| Offline SQLAlchemy `CreateTable` / `CreateIndex` compilation of the migration's definitions for SQLite and PostgreSQL | Passed: two tables and one ordinary index for each dialect. Generated DDL visually checked against the frozen columns, nullability, primary keys and index order. No migration entry point invoked. |
| Independent read-only review of the complete core lane against spec, frozen interfaces and existing store/db/admin/model behavior | No Critical/Important findings. One override provenance mismatch identified and corrected as described below; author inspected the correction and repeated static gates. |
| `git diff --cached --check` and staged ownership/diff inspection before implementation commit | Passed; only the two assigned production additions staged. Report whitespace/ownership checked separately before its commit. |

Static inspection artifacts and execution ledger were kept in this worktree's ignored `.superpowers/sdd/2026-10-12-telegram-approvals-parallel/` during implementation; they are not production files or application tests.

## Decisions and review limits

The execution skill normally defers Minor findings. The explicit handoff requirement to preserve existing override semantics takes precedence: selecting A → B → A must not introduce an override absent from the original metadata. The final implementation derives new overrides from final differences against the snapshot and retains all original overrides. If that interpretation were wrong, a reverted selection would no longer pin that field; this deliberately matches `admin.edits`.

Raw Telegram sender/private-chat authorization and callback version parsing, card escaping/limits/message recovery, credentials/logging/webhook safety and poller lease lifecycle remain the frozen bot/runtime responsibilities. Arbitrary JSON properties outside `Metadata` retain the existing model/store `extra="ignore"` behavior; this lane preserves every defined optional metadata field. These integration assumptions require the planned combined review before activation.

No application tests were written or run. No database connection, schema migration, service start, Telegram/GitHub API call, message, candidate publication or production operation performed. Compilation/import/DDL checks do not prove concurrency, replay, rollback, crash recovery or upgraded-database behavior. Disposable behavioral checks listed in Task 1 remain subject to explicit owner authorization before activation; this includes wrong identity/token, required flags, stale candidate/draft, category changes, expiry renewal, duplicate/concurrent approvals, transaction rollback, rejection replay, offset regression and concurrent preparation.

## Shared blockers and integration

No shared-file blocker found. Existing store validation, publication/rejection and nestable transaction contracts were sufficient. Bot/runtime modules are intentionally absent from this lane, and no cross-lane substitute was created. Merge review-core → bot → runtime only on the coordinator's separate integration branch from the frozen baseline, review the combined feature, and obtain the required behavioral-check authorization before migration or activation.
