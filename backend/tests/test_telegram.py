"""Authorized disposable integration gate: unittest, Docker postgres:17, no live bot.

Run from the repository root:
backend/.venv/bin/python -m unittest discover -s backend/tests -p test_telegram.py -v
"""
import copy
import importlib
import io
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
import psycopg
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
for key in tuple(os.environ):
    if key.startswith(("STORE_", "TELEGRAM_", "PG")) or key in ("DATABASE_URL", "SQLITE_PATH", "APP_ENV"):
        os.environ.pop(key, None)
os.environ["APP_ENV"] = "development"
with patch("dotenv.load_dotenv", return_value=False):
    from backend.app import db, schema, store, telegram_api as api, telegram_bot as bot
    from backend.app import telegram_review as reviews, telegram_worker as worker
    from backend.app.models import InputError, Metadata, Settings
    config_module = importlib.import_module("backend.app.config")

BASE_CONFIG = config_module.config
OWNER = 111
IDENTITY = {"owner_user_id": OWNER, "chat_id": OWNER}
POLLER = "telegram:900:111:111"
TOKEN = "900:" + "x" * 32  # Synthetic; HTTP is always mocked.
TEMP = None
CONTAINER = None
PG_URL = None
PG_PORT = None
GUARDS = None
RAW_PG_CONNECT = psycopg.connect
RAW_SQLITE_CONNECT = sqlite3.connect


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.PIPE).strip()


def guarded_pg(conninfo="", **kwargs):
    values = conninfo_to_dict(conninfo, **{k: v for k, v in kwargs.items()
                                       if k not in ("autocommit", "row_factory", "context", "prepare_threshold")})
    if (values.get("host") != "127.0.0.1" or values.get("port") != PG_PORT
            or values.get("dbname") != "telegram_verification" or values.get("user") != "verifier"):
        raise AssertionError("Only this suite's disposable PostgreSQL destination is allowed")
    return RAW_PG_CONNECT(conninfo, **kwargs)


def guarded_sqlite(database, *args, **kwargs):
    value = os.fspath(database)
    path = Path(urlsplit(value).path if value.startswith("file:") else value).resolve()
    if TEMP is None or not path.is_relative_to(Path(TEMP.name).resolve()):
        raise AssertionError("Only this suite's temporary SQLite files are allowed")
    return RAW_SQLITE_CONNECT(database, *args, **kwargs)


def cleanup():
    global GUARDS, CONTAINER, TEMP
    if GUARDS:
        GUARDS.close()
        GUARDS = None
    if CONTAINER:
        docker("rm", "-f", CONTAINER)
        CONTAINER = None
    if TEMP:
        TEMP.cleanup()
        TEMP = None


def setUpModule():
    global TEMP, CONTAINER, PG_URL, PG_PORT, GUARDS
    TEMP = tempfile.TemporaryDirectory(prefix="os-appstore-telegram-verification-")
    try:
        password = uuid4().hex
        CONTAINER = docker("run", "--detach", "--rm", "--pull=never",
                           "--name", "os-appstore-telegram-verify-" + uuid4().hex[:12],
                           "--tmpfs", "/var/lib/postgresql/data:rw", "-p", "127.0.0.1::5432",
                           "-e", "POSTGRES_USER=verifier", "-e", "POSTGRES_DB=telegram_verification",
                           "-e", "POSTGRES_PASSWORD=" + password, "postgres:17")
        PG_PORT = docker("port", CONTAINER, "5432/tcp").rsplit(":", 1)[1]
        PG_URL = f"postgresql://verifier:{password}@127.0.0.1:{PG_PORT}/telegram_verification"
        for _ in range(100):
            try:
                with RAW_PG_CONNECT(PG_URL, connect_timeout=1):
                    break
            except psycopg.OperationalError:
                time.sleep(.1)
        else:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        GUARDS = ExitStack()
        GUARDS.enter_context(patch.object(psycopg, "connect", guarded_pg))
        GUARDS.enter_context(patch.object(sqlite3, "connect", guarded_sqlite))
        GUARDS.enter_context(patch.object(sqlite3.dbapi2, "connect", guarded_sqlite))
        GUARDS.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("Live network forbidden")))
        GUARDS.enter_context(patch.object(socket, "create_connection", side_effect=AssertionError("Live network forbidden")))
        GUARDS.enter_context(patch("dotenv.load_dotenv", return_value=False))
    except BaseException:
        cleanup()
        raise


def tearDownModule():
    cleanup()


class FakeTelegram:
    def __init__(self, updates=(), failures=None, webhook="", on_poll=None):
        self.updates = list(updates)
        self.failures = failures or {}
        self.webhook, self.on_poll = webhook, on_poll
        self.calls, self.closed = [], False
        self.next_message = 1000

    def call(self, method, payload=None):
        if db._connection.get() is not None:
            raise AssertionError("Telegram I/O attempted inside a database transaction")
        payload = payload or {}
        self.calls.append((method, copy.deepcopy(payload)))
        failures = self.failures.get(method, [])
        if failures:
            raise api.TelegramError(failures.pop(0))
        if method == "getMe":
            return {"id": 900, "is_bot": True, "first_name": "Synthetic"}
        if method == "getWebhookInfo":
            return {"url": self.webhook, "has_custom_certificate": False, "pending_update_count": 0}
        if method == "getUpdates":
            if self.on_poll:
                self.on_poll()
            return [u for u in self.updates if u["update_id"] >= payload["offset"]][:payload["limit"]]
        if method == "sendMessage":
            self.next_message += 1
            return {"message_id": self.next_message, "chat": {"id": OWNER, "type": "private"}}
        if method == "editMessageText":
            return {"message_id": payload["message_id"], "chat": {"id": OWNER, "type": "private"}}
        if method == "answerCallbackQuery":
            return True
        raise AssertionError("Unexpected Telegram method")

    def close(self):
        self.closed = True


def callback(review, action="approve", value=None, update_id=1):
    data = f"tg:{review['token']}:{review['draft_version']}:{action}"
    if value is not None:
        data += ":" + value
    return {"update_id": update_id, "callback_query": {
        "id": "query" + str(update_id), "from": {"id": OWNER}, "data": data,
        "message": {"message_id": 701, "date": 1700000000,
                    "chat": {"id": OWNER, "type": "private"}},
    }}


class DatabaseCases:
    engine = None

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        path = Path(TEMP.name) / (uuid4().hex + ".sqlite")
        self.schema_name = "case_" + uuid4().hex
        url = ""
        if self.engine == "postgres":
            with closing(psycopg.connect(PG_URL, autocommit=True)) as connection:
                connection.execute('CREATE SCHEMA "' + self.schema_name + '"')
            url = PG_URL + "?options=" + quote("-csearch_path=" + self.schema_name)
        self.config = replace(BASE_CONFIG, database_url=url, sqlite_path=path, production=False,
                              app_url="http://localhost:3000", telegram_enabled=True,
                              telegram_bot_token=TOKEN, telegram_owner_user_id=str(OWNER),
                              telegram_chat_id=str(OWNER))
        for module in (config_module, db, schema, store):
            self.stack.enter_context(patch.object(module, "config", self.config))
        schema.upgrade_schema()
        store.initialize()
        self.addCleanup(self.drop_schema)

    def drop_schema(self):
        if self.engine == "postgres":
            with closing(psycopg.connect(PG_URL, autocommit=True)) as connection:
                connection.execute('DROP SCHEMA "' + self.schema_name + '" CASCADE')

    def candidate(self, repo_id="100", **changes):
        fields = dict(repoId=repo_id, repoUrl=f"https://github.com/synthetic/repo-{repo_id}",
                      name="Synthetic app", creator="Fixture", creatorUrl="https://github.com/synthetic",
                      license="MIT", description="Synthetic description")
        data = Metadata(**(fields | changes))
        store.save_candidate(data, {"uncertain": ["cost"], "source": "fixture"})
        return data

    def review(self, **changes):
        self.candidate(**changes)
        result = reviews.prepare_reviews(**IDENTITY)[0]
        reviews.mark_delivered(result["token"], 701, **IDENTITY)
        return result

    def select(self, review, action, value=None):
        return reviews.apply_action(review["token"], review["draft_version"], action, value, **IDENTITY)

    def ready(self, **changes):
        result = self.review(**changes)
        for action, value in (("category", "0"), ("type", "0"), ("cost", "0"), ("safe", "yes")):
            result = self.select(result, action, value)["review"]
        return result

    def run_bot(self, client, assert_active=lambda: None):
        return bot.run_once(client, **IDENTITY, poller_key=POLLER, app_url=self.config.app_url,
                            environment="verification", stop_event=threading.Event(),
                            assert_active=assert_active, poll_timeout=0)

    def test_fresh_schema_and_worker_readiness(self):
        schema.upgrade_schema()  # A repeat migration must accept its own ordinary constraints.
        worker._schema_ready(self.config, db)
        self.assertIn(db.query("SELECT version_num FROM alembic_version")[0]["version_num"],
                      ("0002_telegram_reviews", "0003_community_requests"))
        self.assertEqual(len(store.categories()), 9)

    def test_additive_community_revision_preserves_telegram_readiness(self):
        self.review()
        before = db.query("SELECT * FROM telegram_reviews")
        # Session 1 owns the additive migration. Readiness only needs its revision
        # and the existing Telegram tables; no fake migration is installed here.
        db.query("UPDATE alembic_version SET version_num='0003_community_requests'")
        worker._schema_ready(self.config, db)
        self.assertEqual(db.query("SELECT * FROM telegram_reviews"), before)

    def test_additive_revision_does_not_hide_missing_telegram_tables(self):
        db.query("UPDATE alembic_version SET version_num='0003_community_requests'")
        db.query("DROP TABLE telegram_state")
        with self.assertRaises(worker.WorkerError):
            worker._schema_ready(self.config, db)

    def test_unknown_revision_is_not_silently_accepted(self):
        db.query("UPDATE alembic_version SET version_num='0099_unknown'")
        with self.assertRaises(worker.WorkerError):
            worker._schema_ready(self.config, db)

    def test_upgrade_preserves_baseline_rows(self):
        self.candidate()
        before = {table: db.query("SELECT * FROM " + table) for table in ("candidates", "settings", "categories")}
        # Reconstruct an actual 0001 database even after Session 1's migration
        # is integrated; otherwise its 0003 tables survive the test rewind.
        db.query("DROP TABLE IF EXISTS community_contributions")
        db.query("DROP TABLE IF EXISTS community_suggestions")
        db.query("DROP TABLE telegram_reviews")
        db.query("DROP TABLE telegram_state")
        db.query("UPDATE alembic_version SET version_num='0001_initial'")
        with self.assertRaises(worker.WorkerError):
            worker._schema_ready(self.config, db)
        schema.upgrade_schema()
        for table, rows in before.items():
            self.assertEqual(db.query("SELECT * FROM " + table), rows)
        worker._schema_ready(self.config, db)

    def test_simple_card_accept_and_more(self):
        review = self.review(description="An image editor for photos. Extra details for advanced users.")
        payload = bot.render_review(review, app_url=self.config.app_url, environment="verification")
        buttons = [b for row in payload["reply_markup"]["inline_keyboard"] for b in row]
        self.assertEqual([b["text"] for b in buttons], ["Open repo", "Accept", "Reject", "More"])
        self.assertIn("An image editor for photos. Extra details for advanced users.", payload["text"])
        client = FakeTelegram([callback(review, "more")])
        self.run_bot(client)
        expanded = [p for m, p in client.calls if m == "editMessageText"][0]
        self.assertIn("Creative Tools", expanded["text"])
        self.assertEqual(store.list_apps(), [])
        client = FakeTelegram([callback(review, "accept", update_id=2)])
        self.run_bot(client)
        apps = store.list_apps()
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["categories"], ["creative-tools"])
        self.assertEqual(apps[0]["costModel"], "Free")
        self.assertEqual(self.select(review, "accept")["outcome"], "already_done")

    def test_card_keeps_three_sentences_and_known_metadata(self):
        review = self.review(
            description="An editor for photos. It supports layers and masks. Built for designers. More technical details follow.",
            platforms=["macOS"], type="Desktop app", overrides=["type"],
        )
        payload = bot.render_review(review, app_url=self.config.app_url, environment="verification")
        self.assertIn("An editor for photos. It supports layers and masks. Built for designers.", payload["text"])
        self.assertNotIn("More technical details follow.", payload["text"])
        for line in ("Category: Creative Tools", "Type: Desktop app", "Platforms: macOS", "Cost: Free", "License: MIT"):
            self.assertIn(line, payload["text"])
        expanded = bot.render_review(review, app_url=self.config.app_url, environment="verification", expanded=True)
        self.assertIn("More technical details follow.", expanded["text"])

    def test_card_omits_unknown_metadata_and_unverified_default_type(self):
        review = self.review(license="", description="A useful tool.")
        payload = bot.render_review(review, app_url=self.config.app_url, environment="verification")
        for label in ("Type:", "Platforms:", "Cost:", "License:", "Needs review", "Unknown"):
            self.assertNotIn(label, payload["text"])

    def test_accept_keeps_publication_guards(self):
        review = self.review(nsfw=True)
        self.assertEqual(self.select(review, "accept")["outcome"], "blocked")
        self.assertEqual(store.list_apps(), [])

    def test_accept_does_not_guess_unknown_free_use(self):
        review = self.review(license="")
        self.assertEqual(self.select(review, "accept")["outcome"], "blocked")
        self.assertEqual(store.list_apps(), [])

    def test_identity_and_required_confirmation(self):
        review = self.review()
        for identity in ({"owner_user_id": 222, "chat_id": OWNER}, {"owner_user_id": OWNER, "chat_id": 222}):
            with self.assertRaises(InputError):
                reviews.apply_action(review["token"], 1, "reject", **identity)
        self.assertEqual(self.select(review, "approve")["outcome"], "blocked")
        self.assertEqual(store.list_apps(), [])

    def test_publication_preserves_optional_metadata_and_replay(self):
        review = self.ready(attributes={"offline": None, "noAccount": True}, overrides=["description"])
        result = self.select(review, "approve")
        self.assertEqual(result["outcome"], "approved")
        app = store.get_app(result["review"]["app_slug"])
        self.assertIsNone(app["attributes"]["offline"])
        self.assertTrue(app["attributes"]["noAccount"])
        self.assertIn("description", app["overrides"])
        self.assertEqual(self.select(review, "approve")["outcome"], "already_done")
        self.assertEqual(len(store.list_apps()), 1)
        self.assertEqual(len(db.query("SELECT * FROM audit WHERE action='telegram.review.approved'")), 1)

    def test_reverted_selection_does_not_pin_override(self):
        review = self.review(type="Desktop app", costModel="Free", categories=["ai"])
        changed = self.select(review, "type", "1")["review"]
        restored = self.select(changed, "type", "0")["review"]
        self.assertNotIn("type", restored["data"]["overrides"])
        self.assertTrue(restored["confirmed"]["type"])

    def test_old_button_and_refreshed_candidate_cannot_publish(self):
        review = self.ready()
        edited = self.select(review, "cost", "1")["review"]
        stale = self.select(review, "accept")
        self.assertEqual(stale["outcome"], "stale")
        self.assertEqual(stale["review"]["status"], "open")
        self.candidate()
        self.assertEqual(self.select(edited, "accept")["review"]["status"], "stale")
        self.assertEqual(store.list_apps(), [])

    def test_expiry_renews_without_reviving_old_token(self):
        review = self.ready()
        db.query("UPDATE telegram_reviews SET expires_at='2000-01-01T00:00:00.000Z' WHERE token=$1", [review["token"]])
        self.assertEqual(self.select(review, "accept")["outcome"], "expired")
        fresh = reviews.prepare_reviews(**IDENTITY)[0]
        self.assertNotEqual(fresh["token"], review["token"])
        self.assertFalse(any(fresh["confirmed"].values()))

    def test_nsfw_paused_publication_and_removed_category_are_blocked(self):
        review = self.ready(nsfw=True)
        self.assertEqual(self.select(review, "accept")["outcome"], "blocked")
        db.query("DELETE FROM telegram_reviews")
        db.query("DELETE FROM candidates")
        review = self.ready()
        settings = store.get_settings()
        settings.publicationPaused = True
        store.write_settings(settings)
        self.assertEqual(self.select(review, "accept")["outcome"], "blocked")
        settings.publicationPaused = False
        store.write_settings(settings)
        db.query("DELETE FROM categories WHERE id=$1", [review["data"]["categories"][0]])
        self.assertEqual(self.select(review, "accept")["outcome"], "blocked")
        self.assertEqual(store.list_apps(), [])

    def test_failure_after_publication_rolls_back_everything(self):
        review = self.ready()
        revision = store.get_settings().revision
        real_audit = store.audit
        def failing_audit(action, data):
            if action == "telegram.review.approved":
                raise RuntimeError("Synthetic audit failure")
            real_audit(action, data)
        with patch.object(store, "audit", side_effect=failing_audit), self.assertRaises(RuntimeError):
            self.select(review, "accept")
        self.assertEqual(store.list_apps(), [])
        self.assertEqual(store.candidates()[0]["status"], "pending")
        self.assertEqual(store.get_settings().revision, revision)
        self.assertEqual(db.query("SELECT * FROM audit"), [])
        self.assertEqual(reviews.get_review(review["token"], **IDENTITY)["status"], "open")

    def test_concurrent_web_and_telegram_decisions_publish_once(self):
        review = self.ready()
        barrier = threading.Barrier(2)
        def decide(telegram):
            barrier.wait(timeout=5)
            try:
                if telegram:
                    return self.select(review, "accept")["outcome"]
                return store.approve_candidate("100", 1, Metadata.model_validate(review["data"]))
            except InputError:
                return "stale"
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(decide, value) for value in (True, False)]
            [future.result(timeout=15) for future in futures]
        self.assertEqual(len(store.list_apps()), 1)
        self.assertEqual(len(db.query("SELECT * FROM audit WHERE action='candidate.approved'")), 1)

    def test_concurrent_preparers_share_one_review(self):
        self.candidate()
        barrier = threading.Barrier(2)
        def prepare():
            barrier.wait(timeout=5)
            return reviews.prepare_reviews(**IDENTITY)[0]["token"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(prepare) for _ in range(2)]
            tokens = [future.result(timeout=15) for future in futures]
        self.assertEqual(tokens[0], tokens[1])
        self.assertEqual(len(db.query("SELECT * FROM telegram_reviews")), 1)

    def test_reject_replay_and_monotonic_offset(self):
        review = self.review()
        self.assertEqual(self.select(review, "reject")["outcome"], "rejected")
        self.assertEqual(self.select(review, "reject")["outcome"], "already_done")
        reviews.advance_offset(POLLER, 20)
        reviews.advance_offset(POLLER, 3)
        self.assertEqual(reviews.get_offset(POLLER), 20)

    def test_unauthorized_and_malformed_updates_do_not_mutate(self):
        review = self.ready()
        updates = []
        for index, variant in enumerate(("owner", "chat", "group", "missing", "malformed"), 1):
            update = callback(review, update_id=index)
            query = update["callback_query"]
            if variant == "owner": query["from"]["id"] = 222
            if variant == "chat": query["message"]["chat"]["id"] = 222
            if variant == "group": query["message"]["chat"]["type"] = "group"
            if variant == "missing": query.pop("message")
            if variant == "malformed": query["data"] = "tg:invalid:01:approve"
            updates.append(update)
        client = FakeTelegram(updates)
        self.run_bot(client)
        self.assertEqual(store.list_apps(), [])
        self.assertEqual(reviews.get_offset(POLLER), 6)
        self.assertEqual([method for method, _ in client.calls].count("answerCallbackQuery"), 1)

    def test_restart_after_publish_before_offset_is_idempotent(self):
        review = self.ready()
        update = callback(review)
        with patch.object(reviews, "advance_offset", side_effect=RuntimeError("Synthetic crash")), self.assertRaises(RuntimeError):
            self.run_bot(FakeTelegram([update]))
        self.assertEqual(len(store.list_apps()), 1)
        self.assertEqual(reviews.get_offset(POLLER), 0)
        self.run_bot(FakeTelegram([update], {"answerCallbackQuery": ["callback_expired"], "editMessageText": ["not_modified"]}))
        self.assertEqual(len(store.list_apps()), 1)
        self.assertEqual(reviews.get_offset(POLLER), 2)

    def test_transient_edit_replays_without_reapplying_selection(self):
        review = self.review()
        update = callback(review, "type", "1")
        client = FakeTelegram([update], {"editMessageText": ["transient"]})
        with self.assertRaises(api.TelegramError): self.run_bot(client)
        self.assertEqual(reviews.get_offset(POLLER), 0)
        self.run_bot(client)
        current = reviews.get_review(review["token"], **IDENTITY)
        self.assertEqual(current["draft_version"], 2)
        self.assertEqual(reviews.get_offset(POLLER), 2)

    def test_unavailable_edit_resends_open_card_and_completes_terminal(self):
        review = self.review()
        self.run_bot(FakeTelegram([callback(review, "type", "1")], {"editMessageText": ["message_unavailable"]}))
        self.assertIsNone(reviews.get_review(review["token"], **IDENTITY)["message_id"])
        self.assertEqual(self.run_bot(FakeTelegram())["sent"], 1)
        current = reviews.get_review(review["token"], **IDENTITY)
        reviews.reset_delivery(review["token"], 701, **IDENTITY)
        self.assertEqual(reviews.get_review(review["token"], **IDENTITY)["message_id"], current["message_id"])
        self.run_bot(FakeTelegram([callback(current, "reject", update_id=3)], {"editMessageText": ["message_unavailable"]}))
        self.assertEqual(reviews.get_offset(POLLER), 4)
        self.assertEqual(self.run_bot(FakeTelegram())["sent"], 0)

    def test_crash_after_send_duplicates_card_but_not_review(self):
        self.candidate()
        client = FakeTelegram()
        with patch.object(reviews, "mark_delivered", side_effect=RuntimeError("Synthetic crash")), self.assertRaises(RuntimeError):
            self.run_bot(client)
        self.run_bot(client)
        sends = [payload for method, payload in client.calls if method == "sendMessage"]
        self.assertEqual(len(sends), 2)
        self.assertEqual(sends[0]["reply_markup"], sends[1]["reply_markup"])
        self.assertEqual(len(db.query("SELECT * FROM telegram_reviews")), 1)

    def test_delivery_and_update_budgets_are_bounded(self):
        for repo in range(100, 112): self.candidate(str(repo))
        updates = [{"update_id": i, "message": {"from": {"id": OWNER}, "chat": {"id": OWNER, "type": "private"}, "text": "/pending"}} for i in range(1, 26)]
        result = self.run_bot(FakeTelegram(updates))
        self.assertEqual(result, {"updates": 20, "sent": 5})
        self.assertEqual(len(db.query("SELECT * FROM telegram_reviews WHERE message_id IS NOT NULL")), 5)

    def test_card_and_callback_bounds(self):
        review = self.ready(description="🧪" * 4000)
        payload = bot.render_review(review, app_url=self.config.app_url, environment="verification")
        self.assertLessEqual(len(payload["text"].encode("utf-16-le")) // 2, 4096)
        self.assertNotIn("uncertain", payload["text"])
        for row in payload["reply_markup"]["inline_keyboard"]:
            for button in row:
                if "callback_data" in button:
                    self.assertLessEqual(len(button["callback_data"].encode()), 64)
        for value in ("01", "-1", "2147483648", "１", "0:extra"):
            with self.assertRaises(InputError):
                bot._parse_callback(f"tg:{review['token']}:1:type:{value}")

    def test_single_poller_lost_lease_and_cleanup(self):
        lease = worker.PollerLease(db, 900, threading.Event())
        other = worker.PollerLease(db, 900, threading.Event())
        try:
            lease.acquire()
            with self.assertRaises(worker.WorkerError): other.acquire()
            db.query("UPDATE leases SET owner='replacement' WHERE id='telegram:900'")
            with self.assertRaises(worker.WorkerError): lease.assert_active()
        finally:
            lease.close()
            other.close()
        self.assertEqual(db.query("SELECT owner FROM leases")[0]["owner"], "replacement")

    def test_disabled_or_invalid_config_never_connects(self):
        for changes in ({"telegram_enabled": False}, {"telegram_bot_token": "bad"}, {"telegram_chat_id": "-1"}):
            with patch.object(config_module, "config", replace(self.config, **changes)), patch.object(db, "connect", side_effect=AssertionError("Unexpected DB")), patch.object(api, "TelegramClient", side_effect=AssertionError("Unexpected HTTP")), patch.object(sys, "argv", ["telegram-worker"]), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as failure: worker.main()
                self.assertEqual(failure.exception.code, 1)

    def test_webhook_refusal_and_once_mode(self):
        client = FakeTelegram(webhook="https://example.invalid/webhook")
        with patch.object(api, "TelegramClient", return_value=client), self.assertRaises(worker.WorkerError):
            worker._run(self.config, TOKEN, OWNER, OWNER, True, threading.Event())
        self.assertTrue(client.closed)
        self.assertEqual(db.query("SELECT * FROM leases"), [])
        self.candidate()
        client = FakeTelegram()
        with patch.object(api, "TelegramClient", return_value=client), patch.object(sys, "argv", ["telegram-worker", "--once"]), redirect_stdout(io.StringIO()):
            worker.main()
        self.assertTrue(client.closed)
        self.assertEqual([payload["timeout"] for method, payload in client.calls if method == "getUpdates"], [0])
        self.assertEqual(db.query("SELECT * FROM leases"), [])

    def test_signals_stop_worker_and_restore_handlers(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            original = signal.getsignal(sig)
            client = FakeTelegram(on_poll=lambda: signal.raise_signal(sig))
            with patch.object(api, "TelegramClient", return_value=client), patch.object(sys, "argv", ["telegram-worker"]), redirect_stdout(io.StringIO()):
                worker.main()
            self.assertTrue(client.closed)
            self.assertEqual(db.query("SELECT * FROM leases"), [])
            self.assertEqual(signal.getsignal(sig), original)


class SQLiteCases(DatabaseCases, unittest.TestCase):
    engine = "sqlite"


class PostgreSQLCases(DatabaseCases, unittest.TestCase):
    engine = "postgres"

    def test_noninheritable_check_still_requires_manual_review(self):
        db.query("ALTER TABLE settings ADD CONSTRAINT explicit_noinherit CHECK (id=1) NO INHERIT")
        with self.assertRaisesRegex(RuntimeError, "non-baseline constraint settings.explicit_noinherit"):
            schema.upgrade_schema()

    def test_timeout_preserves_schema_and_bounds_writer_wait(self):
        with db.operation_timeout(150):
            with closing(db.connect()) as connection:
                self.assertEqual(connection.execute("SELECT current_schema() AS name").fetchone()["name"], self.schema_name)
                self.assertEqual(connection.execute("SHOW statement_timeout").fetchone()["statement_timeout"], "150ms")
            with closing(psycopg.connect(self.config.database_url, autocommit=True)) as blocker:
                blocker.execute("BEGIN")
                blocker.execute("SELECT pg_advisory_xact_lock(19962411)")
                started = time.monotonic()
                try:
                    with self.assertRaises((psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable)):
                        with db.transaction(): pass
                    self.assertLess(time.monotonic() - started, 2)
                finally:
                    blocker.execute("ROLLBACK")
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SHOW statement_timeout").fetchone()["statement_timeout"], "0")


class TransportCases(unittest.TestCase):
    def client(self, handler):
        client = api.TelegramClient(TOKEN)
        client._client.close()
        client._client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
        self.addCleanup(client.close)
        return client

    def response(self, status, body, **headers):
        content = body if isinstance(body, bytes) else json.dumps(body).encode()
        return httpx.Response(status, stream=httpx.ByteStream(content), headers=headers)

    def test_error_classification_and_secret_redaction(self):
        cases = [
            ("getMe", {}, 429, "Too Many Requests", "rate_limited"),
            ("getMe", {}, 503, "upstream failure", "transient"),
            ("getMe", {}, 401, "Unauthorized " + TOKEN, "permanent"),
            ("editMessageText", {"chat_id": OWNER, "message_id": 701, "text": "x"}, 400, "message is not modified", "not_modified"),
            ("editMessageText", {"chat_id": OWNER, "message_id": 701, "text": "x"}, 400, "message to edit not found", "message_unavailable"),
            ("answerCallbackQuery", {"callback_query_id": "query"}, 400, "query is too old and response timeout expired", "callback_expired"),
        ]
        for method, payload, status, description, expected in cases:
            with self.subTest(expected=expected):
                client = self.client(lambda request: self.response(status, {"ok": False, "error_code": status, "description": description, "parameters": {"retry_after": 999}}))
                with self.assertRaises(api.TelegramError) as error: client.call(method, payload)
                self.assertEqual(error.exception.code, expected)
                self.assertNotIn(TOKEN, str(error.exception))
                if expected == "rate_limited": self.assertEqual(error.exception.retry_after, 60)

    def test_redirect_oversized_compressed_and_malformed_responses(self):
        factories = [
            lambda: self.response(307, b"", location="https://example.invalid/"),
            lambda: self.response(200, b"x" * (api.MAX_RESPONSE + 1)),
            lambda: self.response(200, b"not gzip", **{"content-encoding": "gzip"}),
            lambda: self.response(200, {"ok": True, "result": {"id": True, "is_bot": True}}),
        ]
        for factory in factories:
            client = self.client(lambda request: factory())
            with self.assertRaises(api.TelegramError) as error: client.call("getMe")
            self.assertEqual(error.exception.code, "permanent")

    def test_fixed_origin_success_and_nonmonotonic_updates(self):
        requests = []
        def handler(request):
            requests.append(request)
            return self.response(200, {"ok": True, "result": {"id": 900, "is_bot": True, "first_name": "Synthetic"}})
        self.assertEqual(self.client(handler).call("getMe")["id"], 900)
        self.assertEqual(str(requests[0].url), "https://api.telegram.org/bot" + TOKEN + "/getMe")
        self.assertEqual(requests[0].headers["content-type"], "application/json")
        client = self.client(lambda request: self.response(200, {"ok": True, "result": [{"update_id": 2}, {"update_id": 1}]}))
        with self.assertRaises(api.TelegramError): client.call("getUpdates", {"offset": 0})

    def test_network_errors_are_safe_and_retry_wait_is_interruptible(self):
        def failure(request):
            raise httpx.ConnectError("Synthetic failure at " + str(request.url), request=request)
        with self.assertRaises(api.TelegramError) as error: self.client(failure).call("getMe")
        self.assertEqual(error.exception.code, "transient")
        self.assertNotIn(TOKEN, str(error.exception))
        stopping = threading.Event()
        timer = threading.Timer(.05, stopping.set)
        timer.start()
        started = time.monotonic()
        try:
            with redirect_stderr(io.StringIO()), self.assertRaises(worker.WorkerStopped):
                worker._retry(lambda: (_ for _ in ()).throw(api.TelegramError("rate_limited", 60)), api.TelegramError, stopping)
            self.assertLess(time.monotonic() - started, 1)
        finally:
            timer.join()


if __name__ == "__main__":
    unittest.main(verbosity=2)
