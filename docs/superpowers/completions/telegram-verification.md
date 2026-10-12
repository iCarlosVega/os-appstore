# Telegram behavioral verification

Owner authorization: the owner answered “yes” to disposable database tests with mocked Telegram responses, then requested continuation. Verification was performed in the `telegram/integration` worktree, starting from `ab72c3a`.

## Result

All **52 tests passed** in **8.218 seconds** on the final code. The suite exercises real SQLite and PostgreSQL migrations, store transactions, review/controller/worker behavior, and mocked Telegram transport. Independent read-only review found no blocking issue in the tests or migration correction.

Reproduce from the repository root with the existing backend virtualenv, Docker running and the `postgres:17` image available locally:

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -p test_telegram.py -v
```

No additional test dependency is required. Docker image pulling is disabled by the suite. Each run creates its own uniquely named PostgreSQL container, random loopback port and tmpfs data directory, plus temporary SQLite files; cleanup removes them. Existing local/production databases and real Telegram are not used. Tests disable dotenv loading, restrict database destinations and block ordinary socket connections. Telegram responses and faults are synthetic.

## Covered behavior

- Fresh schema, repeated migration, baseline upgrade with candidate/settings/category rows preserved, worker readiness and explicit schema-drift rejection.
- Owner/chat binding, private-chat enforcement, malformed callbacks, explicit required fields, NSFW/publication pause/category removal blocks, stale candidate/draft versions and expiry renewal.
- Optional metadata and manual overrides, reverted selections, rejection replay, monotonic offsets, concurrent review preparation and concurrent web/Telegram publication.
- Full publication/audit/review rollback after an injected audit failure; restart after publication before offset persistence; selection replay after transient edit failure; expired acknowledgements and unchanged edits.
- Unavailable-card resend, compare-and-clear delivery protection, crash after send before delivery persistence, five-card/twenty-update budgets, Unicode message and callback bounds.
- Disabled/malformed configuration makes no DB/HTTP connection, webhook refusal, once mode, competing pollers, lost lease, ownership-safe cleanup, SIGINT/SIGTERM cleanup and restored handlers.
- Real PostgreSQL writer-lock timeout, preserved configured schema and unchanged timeout defaults outside the Telegram scope.
- Safe error classes, rate-limit bounds, credential redaction, fixed API origin, redirects, oversized/compressed/malformed responses, nonmonotonic updates and interruptible retry waits.

## Failure found and corrected

Initial run: 48 of 51 checks passed. Two errors were a test-fixture keyword collision, corrected in the fixture. The third exposed an existing PostgreSQL migration guard bug: `_extra_objects` rejected every ordinary primary-key/unique/foreign-key constraint with `connoinherit=true`, preventing baseline upgrades. A focused repeat reproduced the PostgreSQL failure while SQLite passed.

The correction limits the `connoinherit` rejection to CHECK/NOT NULL constraints, retaining validation, deferrability, unsupported-type and other schema checks. Ordinary key/foreign-key constraints are non-inheritable without constituting schema drift. Reference: [PostgreSQL 17 constraint catalog](https://www.postgresql.org/docs/17/catalog-pg-constraint.html). Added repeat-migration coverage and an explicit `CHECK ... NO INHERIT` rejection regression. The final complete run passed all 52 checks.

Python compilation and Git whitespace checks also passed. Container inventory after the run contained no `os-appstore-telegram-verify-*` containers. The independent reviewer inspected the actual correction and isolation/cleanup paths without executing additional tests or accessing databases.

## Remaining operation

The verified integration was fast-forwarded into `develop` at `6af8402`, with identical tested code. Real bot creation/configuration, backing up and migrating the intended local database, and starting Telegram remain separate activation steps. This run sent no real Telegram messages and published only synthetic listings into disposable databases. No production deployment or remote push was performed. The HTTP timeout remains a per-operation inactivity limit, not an overall request deadline.
