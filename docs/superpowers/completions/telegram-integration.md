# Telegram integration review

Completed static integration/review on 2026-10-12. Behavioral verification and activation remain pending owner authorization; Telegram has not been activated.

## Branch and commits

- Integration branch: `telegram/integration`.
- Worktree: `/Users/carlosvega/.codex/worktrees/f06b/os-appstore`.
- Frozen baseline: `7f97d34e70b55d1248babcfb5628484b659c2d22` (`telegram-approvals-baseline-2026-10-12`).
- Merged in order, without conflicts: review-core `d61bb1a` → bot `504e8be` → runtime `a958a8e`.
- Combined merge head: `617118486412342a8692d4dc356d02de6c6c4340`.
- Reviewed integration correction: `e83f2cdbde612a68b01c1f90eed97288bf92d6f1`.
- Root `develop` remains at the frozen baseline. No push, merge into develop/main, deployment or worktree cleanup performed.

All lane worktrees were clean before merging and complied with their exclusive file ownership. Their completion reports are preserved in this branch. The integration worktree has its own `backend/.venv`, installed from existing pinned `backend/requirements.txt`; no root env, credentials, dependencies or database was copied/shared.

## Combined review and corrections

An independent read-only review inspected the whole feature against the design/parallel plan and existing store/db/config/migration behavior. It found two concrete issues:

1. PostgreSQL advisory-lock and other query waits inherited unbounded SQL waits, preventing a stop signal from reaching cleanup. Added opt-in `db.operation_timeout(milliseconds)` using a ContextVar with default `None`. Telegram's main process and heartbeat thread explicitly use a 10-second scope. Newly opened PostgreSQL connections keep their original URL/service/environment settings, then set session statement/lock timeouts before transactions/domain queries. Failed timeout setup closes the new connection. Ordinary callers and SQLite behavior retain their existing defaults; cleanup keeps its narrower five-second statement timeout. This demonstrated shared blocker required a coordinator change to `db.py` beyond the original lane ownership.
2. README described HTTPX's 30-second timeout as an overall request-duration bound. Corrected it to a per-socket-operation inactivity timeout: a progressing response can take longer, and shutdown waits for the active request. No total HTTP deadline is claimed.

The reviewer caught and resolved an intermediate timeout approach that would have replaced PostgreSQL connection options such as `search_path`. The final version preserves original connection arguments and configures only the two session timeout settings. Final follow-up review confirmed both original findings addressed, with no remaining concrete findings from static inspection. This is not behavioral proof.

## Checks actually run

| Check | Result |
| --- | --- |
| Python compilation of config, db, review, transport, controller, worker and migration | Exit zero; repeated after final correction. |
| Combined safe imports of config, db and all four Telegram modules as both `app.*` and `backend.app.*` | Passed after final correction, with dotenv loading disabled and DB/network/subprocess/private-env access blocked. Zero attempted connections or private-env reads. No startup helpers or application actions called. |
| Node syntax for `scripts/backend.mjs` and `scripts/local.mjs` | Exit zero. |
| Four package JSON Telegram commands inspected against exact frozen commands | Passed. |
| Python configuration inspection with synthetic temporary local files | Absent fields disable/blank inherited Telegram values; explicit local values win; noncanonical enable remains disabled; IDs remain strings; token excluded from Config repr. No real env files used. |
| Node's actual `localEnvironment` inspected with synthetic filesystem/environment inputs | Absent and explicit local Telegram values override inherited values. No launcher/main/child process executed. |
| Offline migration metadata/DDL compilation for SQLite and PostgreSQL | Exact two additive tables, frozen column order, one ordinary lookup index and correct revision chain. No engine/connection or migration entry point executed. |
| Git whitespace, lane ownership, branch ancestry and clean working state | Passed. |

An initial DDL inspection script assumed inline Alembic operations; it was corrected to use the migration's pure metadata factory. The failed script did not invoke migration or access any database; the corrected offline inspection passed.

No application tests, disposable behavioral simulations, database connections, schema migrations, services, Telegram/GitHub API requests, messages, candidate publication, private env changes or production operations were performed. Only installing declared dependencies accessed the package registry. Existing root app/discovery processes and databases remain untouched.

## Remaining acceptance and activation

The owner policy and plan require explicit authorization before application tests. Proposed disposable checks must use synthetic records, temporary SQLite and isolated PostgreSQL, and mocked Telegram responses; never the current local or production database or a real bot. Cover:

- Fresh/upgrade schema and existing-row preservation.
- Owner/private-chat authorization, malformed callbacks and payload bounds.
- Explicit required selections, stale revisions/versions, expiry and NSFW blocks.
- Duplicate/concurrent decisions, publication/audit/review rollback and offset replay.
- Transient/permanent API outcomes, unavailable-card resend and crash recovery.
- Configuration isolation, webhook refusal, single poller, lease loss, bounded PostgreSQL waits, signals and restart.

After authorized behavioral verification and acceptance, merge to `develop`; separately back up/migrate the intended local database and configure a dedicated bot privately before real messaging or publication. Production remains a later, separately authorized deployment. Keep all implementation worktrees until accepted.
