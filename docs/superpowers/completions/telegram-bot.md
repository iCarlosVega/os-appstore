# Telegram bot lane completion

Branch: `telegram/bot`; worktree: `/Users/carlosvega/.codex/worktrees/a16d/os-appstore`.
Frozen baseline: `7f97d34e70b55d1248babcfb5628484b659c2d22` (`telegram-approvals-baseline-2026-10-12`). Task 2 only.

## Owned implementation

- `backend/app/telegram_api.py`: synchronous httpx transport with six allowlisted methods, validated token paths, fixed HTTPS origin, no redirects/environment proxies, 30-second timeout, 64 KiB request and 1 MiB raw response bounds. Requests advertise identity encoding and reject compressed responses. Input/envelope/result validation rejects malformed provider results. All six frozen safe error codes and bounded retry-after handling are implemented without exposing provider descriptions, URLs, HTTP exceptions or update payloads. Calls/close suppress the httpx/httpcore request loggers before I/O; importing the module does not configure logging. Construction performs no requests.
- `backend/app/telegram_bot.py`: frozen `render_review` and `run_once` interfaces, immutable supplied assessment display, plain bounded text, environment/repository/revision/version summary, snapshot-index choices and explicit required confirmations. The final publish button names the current draft version and appears only after all required confirmations; flagged NSFW remains blocked. Terminal cards contain no action callbacks and published cards link to the configured app URL. Owner ID, private chat ID and chat type are verified before review access. Canonical callback token/version/index grammar is enforced before actions. Missing private context is ignored; authenticated inaccessible cards cannot apply domain actions and can reset only their matching delivery ID.
- Iterations deliver at most five unsent cards and poll at most twenty updates. `/start`, `/help`, `/pending` are the only commands. `/pending` shares the iteration delivery budget. Every external call checks stop/lease state; every service mutation and offset write checks it under the existing nested writer transaction. No transaction spans Telegram I/O. Offsets advance after completed/ignored updates only. Expired callback acknowledgements and unchanged edits are nonfatal; unavailable edit targets reset matching open deliveries under the guard, while terminal publication stays final. Transient/rate-limit failures propagate with the saved offset for runtime retry; other permanent failures stop safely.

No review-core, migration, runtime/config, launcher, store/admin/model, frontend or dependency files were changed. No shared stubs were added.

## Verification evidence

- Assigned branch/path, clean starting state and common baseline SHA verified with Git.
- Created this worktree's own ignored `backend/.venv`; installed declared `httpx==0.28.1` and its dependencies there. No root environments, private configuration, tokens, databases or dependencies were copied or symlinked.
- `backend/.venv/bin/python -m compileall -q backend/app/telegram_api.py backend/app/telegram_bot.py`: exit zero.
- Safe import of `backend.app.telegram_api` with socket connection entry points and `sqlite3.connect` blocked: passed; installed httpx version is 0.28.1. No client requests/construction or application behavior was exercised.
- Both files parsed with Python AST; frozen public interfaces inspected against the plan. Transport/library logging sites inspected against the installed httpx/httpcore source.
- `git diff --check`: exit zero (repeated after staging for new files).
- Read-only independent whole-lane review of `7f97d34..246efa2`: no actionable correctness, security or frozen-contract findings. The reviewer checked owner/private binding, canonical parsing, card/payload bounds, safe transport/logging, all six error classifications, guarded reset, transaction/lease boundaries, offsets and the shared delivery budget. Verdict: Task 2 ready for integration review, with activation still dependent on integrated review and authorized behavioral checks.

Application tests, worker/services, live Telegram/GitHub requests, messages, schema operations and candidate mutations were not run, per the handoff. Compilation and safe import are not behavioral proof.

## Limits and integration dependencies

- `telegram_review.py` and its `ReviewView` are intentionally absent from this lane's baseline. Controller safe import and combined service/runtime behavior are deferred to integration. The coordinator must integrate review-core → bot → runtime and check the frozen contracts together. No demonstrated shared interface change is required.
- Notification delivery is at least once: a crash after a successful send and before `mark_delivered` can duplicate a card. Both copies share the same token/version; the review core must keep publication idempotent. A lease lost during a network call cannot retract the already-issued request.
- Cards show up to 60 category options and 12 type/cost options per snapshot to keep keyboards bounded (existing catalog/type lists fit). Additional options are explicitly labelled as omitted; versioned pagination would require a coordinated contract extension if the catalog grows beyond that bound. Long repository text and assessment are truncated for display; stored facts are preserved unchanged. HTTP APP_URL links are allowed only for loopback development; other app URLs require HTTPS.
- Request log suppression intentionally affects httpx/httpcore diagnostics in the calling process. Root logging and other logger namespaces are untouched.
- Independent review deferred judgments about absent core guarantees (concurrency/idempotency, rollback/audit atomicity, metadata preservation, expiry/reset), runtime guarantees (configuration/webhook/lease/retry/shutdown) and real Telegram/database operation. These are accepted integration dependencies rather than evidence of verified behavior in this lane; the coordinator must check them before activation.

## Proposed checks requiring authorization

Owner/user/chat/group and spoofed callback rejection; missing/inaccessible messages; malformed, Unicode, leading-zero, overflow and oversized callback/update input; maximum card/keyboard/callback bounds; required selections including unchanged suggested choices and flagged NSFW; stale/expired drafts and renewal; duplicate/terminal callbacks; transaction rollback and concurrent web decisions; transient send/edit/ack failures; all error classifications and 429 retry-after bounds; stop/lease loss; restart after publish before offset and send before delivery recording; unavailable-card guarded reset and bounded resend; unchanged edits and expired acknowledgements allowing offsets to progress.

## Execution rulings

- The explicit no-application-tests policy replaces TDD and full-suite gates with syntax, safe-import and static review checks. Behavioral verification remains outstanding for authorized integration.
- Only Task 2 was executed; other tasks remain with their assigned independent sessions. The branch/worktree stays in place for integration; no merge, push, deployment or activation was performed.
- The executing-plans task-done helper exits on silent successful compile output. Syntax success was recorded directly in the local ledger instead; this does not change the verification boundary or imply passing application tests.
- Review judgments about missing core/runtime and prohibited behavioral checks remain explicitly deferred to integration; incorrect assumptions there could invalidate replay/authorization guarantees. No shared interface defect was demonstrated by this lane's source review.
