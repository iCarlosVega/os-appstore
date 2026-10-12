"""Opt-in Telegram poller. Importing this module never opens a DB or HTTP client."""
import argparse
import logging
import re
import signal
import sqlite3
import sys
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta
from uuid import uuid4


MAX_ID = (1 << 52) - 1
LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 20
DATABASE_TIMEOUT_MS = 10000


class WorkerError(RuntimeError):
    """Only fixed, credential-free operator messages may use this exception."""


class WorkerStopped(Exception):
    pass


def _timestamp(seconds=0):
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _configuration(config):
    if not config.telegram_enabled:
        raise WorkerError("Telegram is disabled. Set TELEGRAM_ENABLED=1 in the intended environment to enable this separate worker.")
    token = config.telegram_bot_token
    if (not re.fullmatch(r"[1-9][0-9]{0,15}:[A-Za-z0-9_-]{20,128}", token)
            or int(token.split(":", 1)[0]) > MAX_ID):
        raise WorkerError("Configure a valid TELEGRAM_BOT_TOKEN privately; use a separate bot for each database.")
    ids = []
    for value in (config.telegram_owner_user_id, config.telegram_chat_id):
        if not re.fullmatch(r"[1-9][0-9]{0,15}", value) or int(value) > MAX_ID:
            raise WorkerError("Set TELEGRAM_OWNER_USER_ID and TELEGRAM_CHAT_ID to canonical positive decimal private-chat IDs (at most 4503599627370495), never usernames or group IDs.")
        ids.append(int(value))
    return token, *ids


def _schema_ready(config, db):
    # db.connect() can create SQLite files; readiness must never do that.
    connection = None
    try:
        if config.database_url:
            connection = db.connect()
            connection.execute("BEGIN READ ONLY")
        else:
            connection = sqlite3.connect(config.sqlite_path.as_uri() + "?mode=ro", uri=True, timeout=10)
        versions = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        revisions = [row["version_num"] if config.database_url else row[0] for row in versions]
        if revisions != ["0002_telegram_reviews"]:
            raise ValueError("migration required")
        for statement in (
            "SELECT token,repo_id,candidate_revision,draft_version,owner_user_id,chat_id,status,snapshot,assessment,draft,options,confirmed,created_at,expires_at,message_id,app_slug FROM telegram_reviews WHERE 1=0",
            "SELECT id,data FROM telegram_state WHERE 1=0",
            "SELECT id,owner,expires_at FROM leases WHERE 1=0",
            "SELECT repo_id,revision,status,data,assessment,updated_at FROM candidates WHERE 1=0",
            "SELECT id,name,parent_id FROM categories WHERE 1=0",
            "SELECT id,repo_id,slug,published,revision,data,updated_at FROM apps WHERE 1=0",
            "SELECT id,action,data,created_at FROM audit WHERE 1=0",
        ):
            connection.execute(statement).fetchall()
        if not connection.execute("SELECT id FROM settings WHERE id=1").fetchall():
            raise ValueError("initialization required")
    except Exception:
        raise WorkerError("Telegram schema is not ready. Check the intended database and connectivity, integrate all Telegram lanes, back up the database, then explicitly run npm run local:db:migrate (local) or npm run db:migrate (ordinary environment). Worker startup never migrates.") from None
    finally:
        if connection is not None:
            connection.close()


class PollerLease:
    def __init__(self, db, bot_id, stopping):
        self.db = db
        self.lease_id = f"telegram:{bot_id}"
        self.owner = str(uuid4())
        self.stopping = stopping
        self.lost = threading.Event()
        self.heartbeat_stop = threading.Event()
        self.thread = None
        self.acquired = False

    def acquire(self):
        with self.db.transaction():
            rows = self.db.query("SELECT owner,expires_at FROM leases WHERE id=$1", [self.lease_id])
            if rows and rows[0]["expires_at"] > _timestamp():
                raise WorkerError("Another Telegram consumer holds this bot's lease. Stop it first, or wait for its 90-second lease to expire after a crash.")
            if self.stopping.is_set():
                raise WorkerStopped()
            self.db.query(
                "INSERT INTO leases(id,owner,expires_at) VALUES($1,$2,$3) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at",
                [self.lease_id, self.owner, _timestamp(LEASE_SECONDS)],
            )
        self.acquired = True
        self.thread = threading.Thread(target=self._heartbeat, name="telegram-lease", daemon=True)
        self.thread.start()

    def assert_active(self):
        if self.lost.is_set():
            raise WorkerError("Telegram lease was lost or could not be renewed. Worker stopped; check database health and other consumers before restarting.")
        if self.stopping.is_set():
            raise WorkerStopped()
        rows = self.db.query("SELECT owner,expires_at FROM leases WHERE id=$1", [self.lease_id])
        if not rows or rows[0]["owner"] != self.owner or rows[0]["expires_at"] <= _timestamp():
            self.lost.set()
            self.stopping.set()
            raise WorkerError("Telegram lease expired or changed owner. Worker stopped; review other consumers before restarting.")

    def _heartbeat(self):
        # ContextVars are thread-local; explicitly bound this thread's connections too.
        with self.db.operation_timeout(DATABASE_TIMEOUT_MS):
            self._renew_loop()

    def _renew_loop(self):
        while not self.heartbeat_stop.wait(HEARTBEAT_SECONDS):
            try:
                with self.db.transaction():
                    self.assert_active()
                    self.db.query(
                        "UPDATE leases SET expires_at=$1 WHERE id=$2 AND owner=$3 AND expires_at>$4",
                        [_timestamp(LEASE_SECONDS), self.lease_id, self.owner, _timestamp()],
                    )
                    self.assert_active()
            except WorkerStopped:
                return
            except Exception:
                self.lost.set()
                self.stopping.set()
                return

    def close(self):
        self.heartbeat_stop.set()
        if self.thread is not None:
            self.thread.join(timeout=11)
            if self.thread.is_alive():
                # A blocked database cannot safely coordinate cleanup; allow expiry.
                print("Telegram lease heartbeat is blocked. After this process exits, wait 90 seconds before restarting.", file=sys.stderr)
                return
        if self.acquired:
            try:
                # One conditional DELETE needs no global writer lock during shutdown.
                connection = (self.db.connect() if self.db.config.database_url else sqlite3.connect(
                    self.db.config.sqlite_path.as_uri() + "?mode=rw", uri=True, timeout=10, isolation_level=None,
                ))
                with closing(connection):
                    if self.db.config.database_url:
                        connection.execute("SET statement_timeout='5s'")
                        sql = "DELETE FROM leases WHERE id=%s AND owner=%s"
                    else:
                        sql = "DELETE FROM leases WHERE id=? AND owner=?"
                    connection.execute(sql, (self.lease_id, self.owner))
            except Exception:
                print("Telegram lease cleanup failed or timed out. Wait 90 seconds after process exit before restarting.", file=sys.stderr)


def _suppress_http_logs():
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.CRITICAL + 1)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
    for name, logger in logging.Logger.manager.loggerDict.copy().items():
        if isinstance(logger, logging.Logger) and name.startswith(("httpx.", "httpcore.")):
            logger.disabled = True


def _retry(operation, error_type, stopping):
    delay = 1
    while not stopping.is_set():
        try:
            return operation()
        except error_type as error:
            if error.code not in ("transient", "rate_limited"):
                raise WorkerError("Telegram request cannot be retried safely. Check bot credentials, private chat access and integrated bot code before restarting.") from None
            requested = error.retry_after
            wait = min(60, max(1, requested)) if type(requested) is int else delay
            print("Telegram transport temporarily unavailable; retrying with the saved offset.", file=sys.stderr)
            if stopping.wait(wait):
                break
            delay = min(60, delay * 2)
    raise WorkerStopped()


def _run(config, token, owner_user_id, chat_id, once, stopping):
    try:
        from . import db
        from .telegram_api import TelegramClient, TelegramError
        from .telegram_bot import run_once
    except ImportError:
        raise WorkerError("Telegram integration modules or backend dependencies are missing. Integrate review-core, bot and runtime, and install backend/requirements.txt in this worktree before starting.") from None

    _schema_ready(config, db)
    if stopping.is_set():
        raise WorkerStopped()
    _suppress_http_logs()
    client = TelegramClient(token)
    lease = None
    try:
        identity = _retry(lambda: client.call("getMe"), TelegramError, stopping)
        if (not isinstance(identity, dict) or type(identity.get("id")) is not int
                or not 0 < identity["id"] <= MAX_ID or identity.get("is_bot") is not True
                or identity["id"] != int(token.split(":", 1)[0])):
            raise WorkerError("Telegram returned an invalid bot identity. Check the configured token before restarting.")
        bot_id = identity["id"]
        webhook = _retry(lambda: client.call("getWebhookInfo"), TelegramError, stopping)
        if not isinstance(webhook, dict) or not isinstance(webhook.get("url"), str):
            raise WorkerError("Telegram returned invalid webhook information. Review bot configuration before restarting.")
        if webhook["url"]:
            raise WorkerError("This bot has an active webhook. Stop its existing consumer and remove the webhook deliberately before polling; this worker never removes webhooks or drops updates.")
        lease = PollerLease(db, bot_id, stopping)
        lease.acquire()
        print("Telegram worker started for " + ("production" if config.production else "development") + ".")
        while not stopping.is_set():
            _retry(
                lambda: run_once(
                    client, owner_user_id=owner_user_id, chat_id=chat_id,
                    poller_key=f"telegram:{bot_id}:{owner_user_id}:{chat_id}",
                    app_url=config.app_url, environment="production" if config.production else "development",
                    stop_event=stopping, assert_active=lease.assert_active,
                    poll_timeout=0 if once else 20,
                ),
                TelegramError, stopping,
            )
            lease.assert_active()
            if once:
                break
            stopping.wait(1)
        if lease.lost.is_set():
            raise WorkerError("Telegram lease was lost or could not be renewed. Check database health and other consumers before restarting.")
    except WorkerStopped:
        if lease is not None and lease.lost.is_set():
            raise WorkerError("Telegram lease was lost or could not be renewed. Check database health and other consumers before restarting.") from None
        raise
    finally:
        stopping.set()
        try:
            if lease is not None:
                lease.close()
        finally:
            client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Separate opt-in Telegram approval worker")
    parser.add_argument("--once", action="store_true", help="one controller iteration with zero-second polling timeout")
    args = parser.parse_args()
    stopping = threading.Event()
    handlers = {}
    try:
        try:
            from .config import config
        except Exception:
            raise WorkerError("Telegram configuration could not be loaded. Check the intended environment; local mode requires the guarded absolute STORE_ENV_FILE and dedicated PostgreSQL configuration.") from None
        token, owner_user_id, chat_id = _configuration(config)
        from . import db
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.signal(sig, lambda *_: stopping.set())
        # Apply before readiness queries, lease acquisition and controller work.
        with db.operation_timeout(DATABASE_TIMEOUT_MS):
            _run(config, token, owner_user_id, chat_id, args.once, stopping)
    except WorkerStopped:
        pass
    except WorkerError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print("Telegram worker stopped safely. Check database connectivity, configuration and the integrated Telegram code before restarting; raw errors are suppressed to protect credentials.", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
