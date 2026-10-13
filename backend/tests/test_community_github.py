"""Isolated search gate: temporary SQLite, synthetic credentials, mocked HTTP."""
import copy
import importlib
import os
import socket
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
with patch.dict(os.environ, {"APP_ENV": "development"}, clear=True), patch("dotenv.load_dotenv", return_value=False):
    from backend.app import auth, db, github
    config_module = importlib.import_module("backend.app.config")

RAW_CLIENT = httpx.Client
RAW_SQLITE_CONNECT = sqlite3.connect
SECRET = "synthetic-github-secret-never-return"
START = 1_800_000_010


def repository(number=1, **changes):
    value = {
        "id": number, "name": f"app-{number}", "html_url": f"https://github.com/example/app-{number}",
        "owner": {"login": "example", "html_url": "https://github.com/example"},
        "description": "Useful software", "stargazers_count": number, "license": {"spdx_id": "MIT"},
        "archived": False, "private": False, "pushed_at": None,
    }
    value.update(changes)
    return value


class CommunityGithubTests(unittest.TestCase):
    def setUp(self):
        try:
            self.service = importlib.import_module("backend.app.community_github")
        except ModuleNotFoundError as error:
            self.fail(f"Task 2 router is not implemented: {error}")
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="community-github-test-"))
        self.config = replace(config_module.config, database_url="", sqlite_path=Path(self.temp) / "test.sqlite",
                              github_token=SECRET, auth_secret="a" * 32, proxy_secret="p" * 32,
                              production=False, telegram_enabled=False, telegram_bot_token="", typesafe_key="")
        for module in (config_module, db, auth, github):
            self.enterContext(patch.object(module, "config", self.config))
        connection_token = db._connection.set(None)
        self.addCleanup(db._connection.reset, connection_token)
        self.enterContext(patch("dotenv.load_dotenv", return_value=False))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Live network forbidden")))
        self.enterContext(patch.object(socket, "create_connection", side_effect=AssertionError("Live network forbidden")))
        self.enterContext(patch("psycopg.connect", side_effect=AssertionError("Only temporary SQLite is allowed")))
        self.enterContext(patch.object(sqlite3, "connect", side_effect=self.sqlite_connect))
        self.clock = self.enterContext(patch("time.time", return_value=START))
        db.query("CREATE TABLE search_cache (id TEXT PRIMARY KEY, data TEXT NOT NULL, expires_at TEXT NOT NULL)")
        db.query("CREATE TABLE rate_limits (id TEXT PRIMARY KEY, total INTEGER NOT NULL, expires_at TEXT NOT NULL)")
        self.status = self.enterContext(patch.object(self.service, "repository_status", return_value={
            "status": "available", "suggestionCount": 0,
        }))
        self.requests = []
        self.body = {"items": [repository()], "total_count": 1, "incomplete_results": False}
        self.http_status, self.headers, self.failure = 200, {}, None
        self.enterContext(patch.object(github.httpx, "Client", side_effect=lambda **kwargs: RAW_CLIENT(
            transport=httpx.MockTransport(self.provider), **kwargs)))
        self.app = FastAPI()
        self.app.include_router(self.service.router)
        self.client = self.enterContext(TestClient(self.app))

    def sqlite_connect(self, database, *args, **kwargs):
        if not Path(database).resolve().is_relative_to(Path(self.temp).resolve()):
            raise AssertionError("Only this test's temporary SQLite file is allowed")
        return RAW_SQLITE_CONNECT(database, *args, **kwargs)

    def provider(self, request):
        self.assertEqual(request.url.host, "api.github.com")
        self.assertEqual(request.headers["authorization"], f"Bearer {SECRET}")
        self.assertIsNone(db._connection.get(), "Provider I/O must be outside writer transactions")
        self.requests.append(request)
        if self.failure:
            raise self.failure
        return httpx.Response(self.http_status, json=copy.deepcopy(self.body), headers=self.headers)

    def search(self, query="useful app", address="visitor"):
        return self.client.get("/api/community/repositories", params={"q": query}, headers={
            "x-store-proxy": self.config.proxy_secret, "x-forwarded-for": address,
        })

    def exact(self, url="https://github.com/example/app-1", address="visitor"):
        return self.client.get("/api/community/repository", params={"url": url}, headers={
            "x-store-proxy": self.config.proxy_secret, "x-forwarded-for": address,
        })

    def provider_total(self):
        return sum(row["total"] for row in db.query(
            "SELECT total FROM rate_limits WHERE id LIKE 'community:github:provider:%'"))

    def test_best_match_public_results(self):
        self.body = {"items": [repository(n) for n in range(1, 11)], "total_count": 200, "incomplete_results": False}
        response = self.search()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 10)
        self.assertEqual([item["repoId"] for item in response.json()["items"]], [str(n) for n in range(1, 11)])
        self.assertEqual(response.json()["items"][0], {
            "repoId": "1", "repoUrl": "https://github.com/example/app-1", "name": "app-1", "owner": "example",
            "description": "Useful software", "stars": 1, "license": "MIT", "archived": False,
            "status": "available", "suggestionCount": 0,
        })
        self.assertEqual(len(self.requests), 1)
        params = self.requests[0].url.params
        self.assertNotIn("sort", params)
        self.assertNotIn("order", params)
        self.assertEqual(params["per_page"], "10")
        self.assertIn("is:public", params["q"])
        self.body["items"][0]["private"] = True
        denied = self.search("different search")
        self.assertEqual(denied.status_code, 503)
        self.assertNotIn("Useful software", denied.text)

    def test_exact_lookup_canonicalizes_rename(self):
        self.body = repository(9007199254740993, name="x", html_url="https://github.com/new-owner/x",
                               owner={"login": "new-owner", "html_url": "https://github.com/new-owner"},
                               description=None, license=None, archived=True)
        response = self.exact("https://github.com/old-owner/old-name.git/")
        self.assertEqual(response.status_code, 200)
        item = response.json()["item"]
        self.assertEqual(item["repoId"], "9007199254740993")
        self.assertEqual(item["repoUrl"], "https://github.com/new-owner/x")
        self.assertEqual((item["name"], item["description"], item["license"], item["archived"]), ("x", "", "", True))
        self.assertEqual(self.requests[0].url.path, "/repos/old-owner/old-name")
        self.assertEqual(len(self.requests), 1)
        self.status.assert_called_once_with("9007199254740993")

    def test_host_and_path_validation(self):
        for url in ("http://github.com/a/b", "https://evil.test/a/b", "https://github.com.evil.test/a/b",
                    "https://user:pass@github.com/a/b", "https://github.com:443/a/b", "https://github.com/a/b/issues",
                    "https://github.com/a/b?x=y", "https://github.com/a/b#readme", "https://github.com/a/%2e%2e",
                    "https://github.com/../b", "//github.com/a/b", "https://github.com/a/b\\c"):
            with self.subTest(url=url):
                response = self.exact(url, address=url)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.requests), 0)

    def test_search_words_cannot_override_public_scope(self):
        response = self.search('editor repo:secret/private OR is:private -is:public fork:true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.requests[0].url.params["q"],
                         '"editor" "repo" "secret/private" "OR" "is" "private" "is" "public" "fork" "true" is:public')
        for query in ("ab", "  ", "!!!", "x" * 201):
            response = self.search(query)
            self.assertIn(response.status_code, (400, 422))
        self.assertEqual(len(self.requests), 1)

    def test_incomplete_results_disclosed(self):
        self.body["incomplete_results"] = True
        response = self.search()
        self.assertTrue(response.json()["incomplete"])

    def test_provider_cache_five_minutes(self):
        self.assertEqual(self.search().status_code, 200)
        self.clock.return_value = START + 299
        self.assertEqual(self.search().status_code, 200)
        self.assertEqual(len(self.requests), 1)
        self.clock.return_value = START + 300
        self.body["items"][0]["stargazers_count"] = 55
        response = self.search()
        self.assertEqual(response.json()["items"][0]["stars"], 55)
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(all(row["id"].startswith("community:github:") for row in db.query("SELECT id FROM search_cache")))
        self.body = repository()
        self.assertEqual(self.exact().status_code, 200)
        self.clock.return_value = START + 599
        self.assertEqual(self.exact().status_code, 200)
        self.assertEqual(len(self.requests), 3)
        self.clock.return_value = START + 600
        self.assertEqual(self.exact().status_code, 200)
        self.assertEqual(len(self.requests), 4)

    def test_cached_facts_refresh_store_status(self):
        self.assertEqual(self.search().json()["items"][0]["status"], "available")
        for status in ("suggested", "already_listed", "awaiting_review", "already_reviewed"):
            self.status.return_value = {"status": status, "suggestionCount": 7}
            item = self.search().json()["items"][0]
            self.assertEqual((item["status"], item["suggestionCount"]), (status, 7))
        self.assertEqual(len(self.requests), 1)
        self.assertNotIn("suggestionCount", db.query("SELECT data FROM search_cache")[0]["data"])

    def test_provider_limit_shared_between_clients(self):
        for number in range(10):
            self.assertEqual(self.search(f"app {number}", f"visitor-{number}").status_code, 200)
        response = self.search("eleventh uncached", "another-visitor")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(int(response.headers["retry-after"]), 50)
        self.assertEqual(len(self.requests), 10)
        self.assertEqual(self.provider_total(), 10)
        self.clock.return_value = START + 50
        self.assertEqual(self.search("next minute", "another-visitor").status_code, 200)

    def test_exact_and_search_share_provider_bucket(self):
        for number in range(9):
            self.assertEqual(self.search(f"app {number}", str(number)).status_code, 200)
        self.body = repository()
        self.assertEqual(self.exact(address="exact-visitor").status_code, 200)
        self.assertEqual(self.search("eleventh uncached", "last-visitor").status_code, 429)
        self.assertEqual(self.provider_total(), 10)

    def test_cache_hit_avoids_provider_bucket(self):
        self.assertEqual(self.search("cached result", "first").status_code, 200)
        for number in range(9):
            self.assertEqual(self.search(f"other {number}", str(number)).status_code, 200)
        self.assertEqual(self.search("cached result", "cache-visitor").status_code, 200)
        self.assertEqual(self.provider_total(), 10)
        self.assertEqual(len(self.requests), 10)

    def test_per_address_limit_includes_cached_and_exact_requests(self):
        self.search()
        for _ in range(9):
            self.assertEqual(self.search().status_code, 200)
        self.assertEqual(self.exact().status_code, 429)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.search(address="second-visitor").status_code, 200)

    def test_untrusted_forwarded_addresses_do_not_bypass_limit(self):
        for number in range(11):
            response = self.client.get("/api/community/repositories", params={"q": "useful app"},
                                       headers={"x-forwarded-for": f"forged-{number}"})
            self.assertEqual(response.status_code, 200 if number < 10 else 429)

    def test_concurrent_clients_cannot_overspend_provider_bucket(self):
        def request(number):
            with TestClient(self.app) as client:
                return client.get("/api/community/repositories", params={"q": f"app {number}"}, headers={
                    "x-store-proxy": self.config.proxy_secret, "x-forwarded-for": str(number),
                }).status_code
        with ThreadPoolExecutor(max_workers=12) as pool:
            codes = list(pool.map(request, range(20)))
        self.assertEqual(codes.count(200), 10)
        self.assertEqual(codes.count(429), 10)
        self.assertEqual(self.provider_total(), 10)
        self.assertEqual(len(self.requests), 10)

    def test_timeout_and_rate_limit_are_sanitized(self):
        cases = [(429, {"retry-after": "27"}, 429, 27),
                 (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(START + 90)}, 429, 90),
                 (403, {"retry-after": "12"}, 429, 12),
                 (403, {}, 503, None), (500, {"retry-after": SECRET}, 503, None)]
        for number, (status, headers, expected, retry) in enumerate(cases):
            self.http_status, self.headers, self.body = status, headers, {"message": SECRET}
            response = self.search(f"failure {number}")
            self.assertEqual(response.status_code, expected)
            self.assertNotIn(SECRET, response.text)
            if retry:
                self.assertEqual(int(response.headers["retry-after"]), retry)
        self.failure = httpx.ReadTimeout(SECRET)
        response = self.search("timeout search")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(SECRET, response.text)
        self.assertEqual(db.query("SELECT id FROM search_cache"), [])
        self.failure, self.http_status, self.headers = None, 200, {}
        self.body = {"items": [repository()], "total_count": 1, "incomplete_results": False}
        self.assertEqual(self.search("timeout search").status_code, 200)

    def test_exact_missing_or_private_repository(self):
        self.http_status, self.body = 404, {"message": SECRET}
        response = self.exact()
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(SECRET, response.text)
        self.http_status, self.body = 200, repository(private=True)
        self.assertEqual(self.exact().status_code, 404)
        self.assertEqual(db.query("SELECT id FROM search_cache"), [])

    def test_invalid_provider_summaries_are_not_cached(self):
        invalid = [repository(id=True), repository(stargazers_count=-1), repository(archived="false"),
                   repository(html_url="https://evil.test/example/app-1"), repository(name="mismatch"),
                   repository(description={"html": SECRET}), repository(private=None)]
        for number, item in enumerate(invalid):
            self.body = {"items": [item], "total_count": 1, "incomplete_results": False}
            response = self.search(f"invalid {number}")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(SECRET, response.text)
        self.assertEqual(db.query("SELECT id FROM search_cache"), [])


if __name__ == "__main__":
    unittest.main()
