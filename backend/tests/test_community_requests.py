"""Isolated SQLite/PostgreSQL community gate; synthetic secrets and no provider network."""
import importlib
import os
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from dataclasses import replace
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote
from uuid import uuid4

import httpx
import psycopg
from psycopg.conninfo import conninfo_to_dict
from fastapi import HTTPException, Request, Response
from fastapi.testclient import TestClient

with patch.dict(os.environ, {"APP_ENV": "development"}, clear=True), patch("dotenv.load_dotenv", return_value=False):
    from backend.app import admin, auth, db, github, main, schema, store
    from backend.app.models import InputError, Metadata
    config_module = importlib.import_module("backend.app.config")

BASE_CONFIG = config_module.config
RAW_PG = psycopg.connect
RAW_SQLITE = sqlite3.connect
RAW_HTTP_CLIENT = httpx.Client
TEMP = CONTAINER = PG_URL = PG_PORT = GUARDS = None
EARLY = "2026-10-05T00:00:00.000Z"
CUTOFF = "2026-10-12T00:00:00.000Z"


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.PIPE).strip()


def guarded_pg(conninfo="", **kwargs):
    values = conninfo_to_dict(conninfo, **{k: v for k, v in kwargs.items()
                                         if k not in ("autocommit", "row_factory", "context", "prepare_threshold")})
    if (values.get("host"), values.get("port"), values.get("dbname"), values.get("user")) != (
            "127.0.0.1", PG_PORT, "community_requests_verification", "verifier"):
        raise AssertionError("Only the community suite's disposable PostgreSQL is allowed")
    return RAW_PG(conninfo, **kwargs)


def guarded_sqlite(database, *args, **kwargs):
    if TEMP is None or not Path(database).resolve().is_relative_to(Path(TEMP.name).resolve()):
        raise AssertionError("Only the community suite's temporary SQLite is allowed")
    return RAW_SQLITE(database, *args, **kwargs)


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
    TEMP = tempfile.TemporaryDirectory(prefix="community-requests-verification-")
    try:
        password = uuid4().hex
        CONTAINER = docker("run", "--detach", "--rm", "--pull=never", "--name",
                           "community-requests-verify-" + uuid4().hex[:12],
                           "--tmpfs", "/var/lib/postgresql/data:rw", "-p", "127.0.0.1::5432",
                           "-e", "POSTGRES_USER=verifier", "-e", "POSTGRES_DB=community_requests_verification",
                           "-e", "POSTGRES_PASSWORD=" + password, "postgres:17")
        PG_PORT = docker("port", CONTAINER, "5432/tcp").rsplit(":", 1)[1]
        PG_URL = f"postgresql://verifier:{password}@127.0.0.1:{PG_PORT}/community_requests_verification"
        for _ in range(100):
            try:
                with RAW_PG(PG_URL, connect_timeout=1):
                    break
            except psycopg.OperationalError:
                time.sleep(.1)
        else:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        GUARDS = ExitStack()
        GUARDS.enter_context(patch.dict(os.environ, {"APP_ENV": "development"}, clear=True))
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


def metadata(repo_id="100", **changes):
    return Metadata(**(dict(repoId=repo_id, repoUrl=f"https://github.com/synthetic/repo-{repo_id}",
                            name="Server facts", creator="synthetic", creatorUrl="https://github.com/synthetic") | changes))


class DatabaseCases:
    engine = None

    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.schema_name = "case_" + uuid4().hex
        url = ""
        if self.engine == "postgres":
            with closing(psycopg.connect(PG_URL, autocommit=True)) as connection:
                connection.execute('CREATE SCHEMA "' + self.schema_name + '"')
            self.addCleanup(self.drop_schema)
            url = PG_URL + "?options=" + quote("-csearch_path=" + self.schema_name)
        self.config = replace(BASE_CONFIG, database_url=url, sqlite_path=Path(TEMP.name) / (uuid4().hex + ".sqlite"),
                              production=False, app_url="https://store.example", auth_secret="synthetic-" + "x" * 32,
                              proxy_secret="proxy-" + "y" * 32, github_token="synthetic-github-token")
        for module in (config_module, admin, auth, db, github, main, schema, store):
            stack.enter_context(patch.object(module, "config", self.config, create=True))
        schema.upgrade_schema()
        store.initialize()
        self.stack = stack

    def drop_schema(self):
        with closing(psycopg.connect(PG_URL, autocommit=True)) as connection:
            connection.execute('DROP SCHEMA "' + self.schema_name + '" CASCADE')

    def service(self):
        self.assertEqual(db.query("SELECT version_num FROM alembic_version")[0]["version_num"],
                         "0003_community_requests", "Community migration has not been implemented")
        return importlib.import_module("backend.app.community_requests")

    def identity(self):
        self.assertIsNotNone(importlib.util.find_spec("backend.app.request_identity"), "Signed visitor identity is missing")
        module = importlib.import_module("backend.app.request_identity")
        self.stack.enter_context(patch.object(module, "config", self.config))
        return module

    def submit(self, client, **changes):
        return client.post("/api/requests", headers={"origin": self.config.app_url},
                           json=dict(name="Visitor idea", repoUrl="https://github.com/old/project", website="") | changes)

    def provider(self, request):
        self.assertIsNone(db._connection.get(), "GitHub I/O must stay outside writer transactions")
        self.assertEqual(request.url.host, "api.github.com")
        if request.url.path.endswith(("/releases/latest", "/readme")):
            return httpx.Response(404)
        return httpx.Response(200, json=dict(id=100, name="Server facts", html_url="https://github.com/synthetic/repo-100",
                                            description="Provider metadata", owner=dict(login="synthetic", html_url="https://github.com/synthetic"),
                                            license=None, stargazers_count=9, archived=False, pushed_at=None, private=False))

    def mock_provider(self, handler=None):
        self.stack.enter_context(patch.object(github.httpx, "Client", side_effect=lambda **kw:
                                 RAW_HTTP_CLIENT(transport=httpx.MockTransport(handler or self.provider), **kw)))

    def test_same_browser_counts_once(self):
        self.service()
        with TestClient(main.app, base_url=self.config.app_url) as client:
            self.mock_provider()
            self.assertEqual(self.submit(client).json(), {"ok": True, "status": "recorded", "suggestionCount": 1})
            response = self.submit(client)
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json(), {"ok": True, "status": "already_suggested", "suggestionCount": 1})
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM community_contributions")[0]["n"], 1)

    def test_two_browsers_count_twice(self):
        self.service()
        with TestClient(main.app, base_url=self.config.app_url) as client:
            self.mock_provider()
            self.submit(client)
            client.cookies.clear()
            self.assertEqual(self.submit(client).json()["suggestionCount"], 2)

    def test_concurrent_duplicate_counts_once(self):
        service = self.service()
        barrier = threading.Barrier(8)
        def record(_):
            barrier.wait(timeout=10)
            return service.record_suggestion(metadata(), "a" * 64, at=EARLY)
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(record, range(8)))
        self.assertEqual(sum(row["status"] == "recorded" for row in responses), 1)
        self.assertEqual(service.repository_status("100"), {"status": "suggested", "suggestionCount": 1})

    def test_rename_uses_numeric_identity(self):
        service = self.service()
        service.record_suggestion(metadata(), "a" * 64, at=EARLY)
        result = service.record_suggestion(metadata(repoUrl="https://github.com/new/renamed", name="Renamed"), "a" * 64)
        self.assertEqual(result["status"], "already_suggested")
        rows = service.admin_suggestions()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["repoUrl"], rows[0]["name"], rows[0]["suggestionCount"]),
                         ("https://github.com/new/renamed", "Renamed", 1))

    def test_cutoff_excludes_late_contribution(self):
        service = self.service()
        service.record_suggestion(metadata(), "a" * 64, at=EARLY)
        service.record_suggestion(metadata(), "b" * 64, at=CUTOFF)
        service.record_suggestion(metadata("200"), "c" * 64, at=CUTOFF)
        self.assertEqual(service.rank_pending(cutoff=CUTOFF), [dict(repoId="100", repoUrl=metadata().repoUrl,
                         name="Server facts", suggestionCount=1, firstSuggestedAt=EARLY)])
        self.assertEqual(service.repository_status("100")["suggestionCount"], 2)

    def test_stable_numeric_ties(self):
        service = self.service()
        for repo_id in ("10", "9999999999999999999999999999999999999999", "2", "100"):
            service.record_suggestion(metadata(repo_id), "a" * 64, at=EARLY)
        service.record_suggestion(metadata("100"), "b" * 64, at=EARLY)
        self.assertEqual([r["repoId"] for r in service.rank_pending(cutoff=CUTOFF)],
                         ["100", "2", "10", "9999999999999999999999999999999999999999"])
        self.assertEqual(len(service.rank_pending(cutoff=CUTOFF, limit=2)), 2)
        self.assertEqual(service.rank_pending(cutoff=CUTOFF, limit=0), [])

    def test_first_contribution_breaks_tie(self):
        service = self.service()
        service.record_suggestion(metadata("2"), "a" * 64, at="2026-10-06T00:00:00.000Z")
        service.record_suggestion(metadata("10"), "a" * 64, at=EARLY)
        self.assertEqual([r["repoId"] for r in service.rank_pending(cutoff=CUTOFF)], ["10", "2"])

    def test_candidate_states_do_not_reopen(self):
        service = self.service()
        for repo_id, state, expected in (("100", "pending", "awaiting_review"), ("200", "rejected", "already_reviewed")):
            data = metadata(repo_id)
            service.record_suggestion(data, "a" * 64, at=EARLY)
            store.save_candidate(data, {"private": "assessment"})
            db.query("UPDATE candidates SET status=$1 WHERE repo_id=$2", [state, repo_id])
            before = db.query("SELECT * FROM candidates WHERE repo_id=$1", [repo_id])
            self.assertEqual(service.record_suggestion(data, "b" * 64)["status"], expected)
            self.assertEqual(service.repository_status(repo_id), {"status": expected, "suggestionCount": None})
            self.assertEqual(db.query("SELECT * FROM candidates WHERE repo_id=$1", [repo_id]), before)
        self.assertEqual(service.rank_pending(cutoff=CUTOFF), [])
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM community_contributions")[0]["n"], 2)

    def test_existing_apps_and_queued_suggestions_are_excluded(self):
        service = self.service()
        for repo_id in ("100", "200"):
            service.record_suggestion(metadata(repo_id), "a" * 64, at=EARLY)
        db.query("INSERT INTO apps(id,repo_id,slug,published,data,updated_at) VALUES('app','100','app',0,$1,$2)",
                 [store.encode(metadata()), EARLY])
        self.assertEqual(service.record_suggestion(metadata(), "b" * 64),
                         {"ok": True, "status": "already_listed", "suggestionCount": None})
        with db.transaction():
            service.mark_review_queued("200", at=CUTOFF)
        self.assertEqual(service.rank_pending(cutoff=CUTOFF), [])
        self.assertEqual(service.repository_status("200")["status"], "awaiting_review")
        self.assertEqual(service.admin_suggestions()[1]["state"], "queued")
        with self.assertRaises(RuntimeError):
            service.mark_review_queued("100", at=CUTOFF)

    def test_forged_metadata_is_not_accepted(self):
        service = self.service()
        with TestClient(main.app, base_url=self.config.app_url) as client:
            self.mock_provider()
            response = self.submit(client, name="Forged name", repoId="666", license="Forged", suggestionCount=999)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(service.admin_suggestions(), [dict(repoId="100", repoUrl="https://github.com/synthetic/repo-100",
                         name="Server facts", suggestionCount=1, state="pending", createdAt=service.admin_suggestions()[0]["createdAt"])])
        self.assertEqual(db.query("SELECT * FROM app_requests"), [])

    def test_unavailable_or_private_repository_does_not_count(self):
        self.service()
        with TestClient(main.app, base_url=self.config.app_url) as client:
            self.mock_provider(lambda request: httpx.Response(404))
            response = self.submit(client)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(set(response.json()), {"error"})
        self.assertEqual(db.query("SELECT * FROM community_contributions"), [])
        with TestClient(main.app, base_url=self.config.app_url) as client:
            def private(request):
                result = self.provider(request)
                return httpx.Response(200, json=result.json() | {"private": True})
            self.mock_provider(private)
            self.assertEqual(self.submit(client).status_code, 503)
        self.assertEqual(db.query("SELECT * FROM community_contributions"), [])

    def test_idea_only_remains_manual(self):
        self.service()
        with TestClient(main.app, base_url=self.config.app_url) as client:
            response = self.submit(client, repoUrl="")
        self.assertEqual(response.json(), {"ok": True, "status": "recorded", "suggestionCount": None})
        self.assertEqual(db.query("SELECT name,repo_url,status FROM app_requests"),
                         [dict(name="Visitor idea", repo_url="", status="pending")])
        self.assertEqual(db.query("SELECT * FROM community_contributions"), [])

    def test_origin_honeypot_and_rate_limits(self):
        self.service()
        with TestClient(main.app, base_url=self.config.app_url) as client:
            self.mock_provider()
            self.assertEqual(client.post("/api/requests", json={"name": "Bad origin"}).status_code, 403)
            self.assertEqual(self.submit(client, website="spam").status_code, 422)
            for _ in range(5):
                self.assertEqual(self.submit(client).status_code, 201)
            client.cookies.clear()
            response = self.submit(client)
            self.assertEqual(response.status_code, 429)
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM community_contributions")[0]["n"], 1)

    def test_forwarded_address_requires_authenticated_proxy(self):
        self.service()
        with TestClient(main.app, base_url=self.config.app_url) as client:
            for i in range(6):
                response = client.post("/api/requests", headers={"origin": self.config.app_url, "x-forwarded-for": f"192.0.2.{i}"},
                                       json={"name": "Idea"})
                self.assertEqual(response.status_code, 201 if i < 5 else 429)
            self.assertEqual(client.post("/api/requests", headers={"origin": self.config.app_url,
                             "x-forwarded-for": "192.0.2.99", "x-store-proxy": self.config.proxy_secret},
                             json={"name": "Idea"}).status_code, 201)

    def test_cookie_tamper_and_expiry(self):
        identity = self.identity()
        def get(cookie=""):
            request = Request({"type": "http", "headers": [(b"cookie", ("store_suggester=" + cookie).encode())]})
            response = Response()
            key = identity.visitor_identity(request, response)
            cookies = SimpleCookie(response.headers.get("set-cookie", ""))
            return key, cookies["store_suggester"].value if cookies else cookie, response
        with patch.object(identity.time, "time", return_value=1800000000):
            key, cookie, response = get()
            self.assertEqual(get(cookie)[0], key)
            self.assertNotEqual(get(cookie + "x")[0], key)
            self.assertNotIn(key, cookie)
            self.assertEqual(len(key), 64)
            for flag in ("HttpOnly", "Secure", "SameSite=lax", "Max-Age=15552000"):
                self.assertIn(flag, response.headers["set-cookie"])
            self.assertIsNone(auth.verify(cookie), "Suggester cookies cannot authenticate owners")
        with patch.object(identity.time, "time", return_value=1815552001):
            self.assertNotEqual(get(cookie)[0], key)

    def test_identity_secret_requirements_and_local_fallback(self):
        identity = self.identity()
        request = Request({"type": "http", "headers": []})
        for secret in ("", "short"):
            with patch.object(identity, "config", replace(self.config, production=True, auth_secret=secret)):
                with self.assertRaises(HTTPException) as error:
                    identity.visitor_identity(request, Response())
                self.assertEqual(error.exception.status_code, 503)
        with patch.object(identity, "config", replace(self.config, auth_secret="", app_url="http://localhost:3000")):
            response = Response()
            self.assertEqual(len(identity.visitor_identity(request, response)), 64)
            self.assertNotIn("Secure", response.headers["set-cookie"])

    def test_dashboard_hides_identity_and_requires_owner(self):
        service = self.service()
        service.record_suggestion(metadata(), "private-key" * 6, at=EARLY)
        value = admin.dashboard()["communitySuggestions"]
        self.assertEqual(set(value[0]), {"repoId", "repoUrl", "name", "suggestionCount", "state", "createdAt"})
        self.assertNotIn("private-key", str(value))
        with TestClient(main.app, base_url=self.config.app_url) as client:
            self.assertEqual(client.get("/api/admin/dashboard").status_code, 401)

    def test_migration_preserves_history_and_is_repeatable(self):
        self.service()
        db.query("DROP TABLE community_contributions")
        db.query("DROP TABLE community_suggestions")
        db.query("UPDATE alembic_version SET version_num='0002_telegram_reviews'")
        db.query("INSERT INTO app_requests(id,name,repo_url,created_at) VALUES('legacy','Legacy','https://github.com/old/repo',$1)", [EARLY])
        db.query("INSERT INTO apps(id,repo_id,slug,data,updated_at) VALUES('legacy-app','100','legacy',$1,$2)", [store.encode(metadata()), EARLY])
        db.query("INSERT INTO telegram_state(id,data) VALUES('poller','{\"offset\":42}')")
        before = {table: db.query("SELECT * FROM " + table) for table in ("app_requests", "apps", "telegram_state")}
        schema.upgrade_schema()
        schema.upgrade_schema()
        self.assertEqual({table: db.query("SELECT * FROM " + table) for table in before}, before)
        self.assertEqual(db.query("SELECT * FROM community_contributions"), [])
        self.assertEqual(db.query("SELECT * FROM community_suggestions"), [])

    def test_schema_constraints_and_atomic_rollback(self):
        service = self.service()
        service.record_suggestion(metadata(), "a" * 64, at=EARLY)
        for sql, values in (("INSERT INTO community_contributions VALUES($1,$2,$3)", ["100", "a" * 64, EARLY]),
                            ("INSERT INTO community_contributions VALUES($1,$2,$3)", ["999", "b" * 64, EARLY]),
                            ("UPDATE community_suggestions SET state='bad'", [])):
            with self.assertRaises((sqlite3.IntegrityError, psycopg.IntegrityError)):
                with db.transaction():
                    db.query(sql, values)
        with self.assertRaises(RuntimeError):
            with db.transaction():
                service.record_suggestion(metadata("200"), "b" * 64, at=EARLY)
                raise RuntimeError("rollback")
        self.assertEqual(service.repository_status("200"), {"status": "available", "suggestionCount": 0})

    def test_missing_migration_returns_clear_error_without_counting(self):
        self.service()
        db.query("DROP TABLE community_contributions")
        db.query("DROP TABLE community_suggestions")
        with TestClient(main.app, base_url=self.config.app_url, raise_server_exceptions=False) as client:
            self.mock_provider()
            response = self.submit(client)
        self.assertEqual(response.status_code, 503)
        self.assertIn("migration", response.json()["error"].lower())
        self.assertEqual(db.query("SELECT * FROM app_requests"), [])


class SQLiteCases(DatabaseCases, unittest.TestCase):
    engine = "sqlite"


class PostgreSQLCases(DatabaseCases, unittest.TestCase):
    engine = "postgres"
