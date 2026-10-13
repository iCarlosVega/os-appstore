"""Real merged services on disposable databases; GitHub/Telegram HTTP mocked."""
import importlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from datetime import UTC, datetime
from dataclasses import replace
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
import psycopg
from psycopg.conninfo import conninfo_to_dict
from fastapi import HTTPException, Request, Response
from fastapi.testclient import TestClient

with patch.dict(os.environ, {"APP_ENV": "development"}, clear=True), patch("dotenv.load_dotenv", return_value=False):
    from backend.app import admin, auth, budget, db, discord, github, jobs, main, schema, store
    from backend.app import community_github, community_requests, community_weekly, request_identity
    from backend.app import telegram_api, telegram_bot, telegram_review, telegram_worker
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
            "127.0.0.1", PG_PORT, "community_integration_verification", "verifier"):
        raise AssertionError("Only the community suite's disposable PostgreSQL is allowed")
    return RAW_PG(conninfo, **kwargs)


def guarded_sqlite(database, *args, **kwargs):
    value = os.fspath(database)
    path = Path(urlsplit(value).path if value.startswith('file:') else value).resolve()
    if TEMP is None or not path.is_relative_to(Path(TEMP.name).resolve()):
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
    TEMP = tempfile.TemporaryDirectory(prefix="community-integration-verification-")
    try:
        password = uuid4().hex
        CONTAINER = docker("run", "--detach", "--rm", "--pull=never", "--name",
                           "community-integration-verify-" + uuid4().hex[:12],
                           "--tmpfs", "/var/lib/postgresql/data:rw", "-p", "127.0.0.1::5432",
                           "-e", "POSTGRES_USER=verifier", "-e", "POSTGRES_DB=community_integration_verification",
                           "-e", "POSTGRES_PASSWORD=" + password, "postgres:17")
        PG_PORT = docker("port", CONTAINER, "5432/tcp").rsplit(":", 1)[1]
        PG_URL = f"postgresql://verifier:{password}@127.0.0.1:{PG_PORT}/community_integration_verification"
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


NOW = '2026-10-13T16:00:00.000Z'
IDENTITY = dict(owner_user_id=111, chat_id=111)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 13, 16, tzinfo=UTC).astimezone(tz or UTC)


class IntegrationCases:
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.schema_name = 'case_' + uuid4().hex
        url = ''
        if self.engine == 'postgres':
            with closing(psycopg.connect(PG_URL, autocommit=True)) as connection:
                connection.execute('CREATE SCHEMA "' + self.schema_name + '"')
            self.addCleanup(self.drop_schema)
            url = PG_URL + '?options=' + quote('-csearch_path=' + self.schema_name)
        self.config = replace(BASE_CONFIG, database_url=url, sqlite_path=Path(TEMP.name)/(uuid4().hex+'.sqlite'),
                              production=False, app_url='https://store.example', auth_secret='synthetic-'+'x'*32,
                              proxy_secret='synthetic-proxy', github_token='synthetic-github',
                              typesafe_key='', discord_webhook='', telegram_enabled=False)
        for module in (config_module, admin, auth, budget, db, discord, github, jobs, main, schema, store,
                       community_weekly, request_identity):
            self.stack.enter_context(patch.object(module, 'config', self.config, create=True))
        self.stack.enter_context(patch.object(store, 'now', return_value=NOW))
        self.stack.enter_context(patch.object(jobs, 'datetime', Clock))
        schema.upgrade_schema()
        store.initialize()
        self.fail_repo, self.archived, self.provider_requests = None, set(), []
        self.updates, self.cards = [], []
        self.stack.enter_context(patch.object(httpx, 'Client', side_effect=lambda **kw:
            RAW_HTTP_CLIENT(**(kw | {'transport': httpx.MockTransport(self.provider)}))))

    def drop_schema(self):
        with closing(psycopg.connect(PG_URL, autocommit=True)) as connection:
            connection.execute('DROP SCHEMA "' + self.schema_name + '" CASCADE')

    def provider(self, request):
        self.assertIsNone(db._connection.get(), 'Provider HTTP must stay outside transactions')
        if request.url.host == 'api.telegram.org':
            method = request.url.path.rsplit('/', 1)[-1]
            payload = json.loads(request.content)
            if method == 'getUpdates':
                result = [u for u in self.updates if u['update_id'] >= payload['offset']]
            elif method == 'sendMessage':
                self.cards.append(payload)
                result = {'message_id': 701 + len(self.cards), 'chat': {'id': 111, 'type': 'private'}}
            elif method == 'editMessageText':
                result = {'message_id': payload['message_id'], 'chat': {'id': 111, 'type': 'private'}}
            elif method == 'answerCallbackQuery':
                result = True
            else:
                raise AssertionError('Unexpected synthetic Telegram operation')
            return httpx.Response(200, stream=httpx.ByteStream(json.dumps({'ok': True, 'result': result}).encode()))
        self.assertEqual(request.url.host, 'api.github.com')
        path = request.url.path
        self.provider_requests.append(path)
        if path == '/search/repositories':
            raw = self.repository('100')
            return httpx.Response(200, json={'total_count': 1, 'incomplete_results': False, 'items': [raw]})
        if path.endswith(('/readme', '/releases/latest')):
            return httpx.Response(404, json={'message': 'Not Found'})
        repo_id = path.rsplit('-', 1)[-1]
        if repo_id == self.fail_repo:
            return httpx.Response(503, json={'message': 'Synthetic failure'})
        return httpx.Response(200, json=self.repository(repo_id))

    def repository(self, repo_id):
        return dict(id=int(repo_id), name='repo-'+repo_id, html_url=f'https://github.com/synthetic/repo-{repo_id}',
                    owner={'login': 'synthetic', 'html_url': 'https://github.com/synthetic'},
                    description='An offline image editor. Supports layers and masks.', license={'spdx_id': 'MIT'},
                    stargazers_count=10, archived=repo_id in self.archived, private=False,
                    pushed_at='2026-10-01T00:00:00Z', topics=['editor'], homepage=None)

    def client(self):
        return TestClient(main.app, base_url=self.config.app_url)

    def submit(self, client, repo_id='100'):
        return client.post('/api/requests', headers={'Origin': self.config.app_url}, json={
            'name': 'Client supplied name', 'repoUrl': f'https://github.com/synthetic/repo-{repo_id}', 'website': ''})

    def seed(self, count=12):
        for i in range(1, count+1):
            community_requests.record_suggestion(metadata(str(i), license='MIT'), 'browser-a', at='2026-10-10T12:00:00.000Z')

    def bot(self):
        client = telegram_api.TelegramClient('900:'+'A'*35)
        self.addCleanup(client.close)
        telegram_bot.run_once(client, **IDENTITY, poller_key='telegram:900:111:111', app_url=self.config.app_url,
                              environment='verification', stop_event=threading.Event(),
                              assert_active=lambda: None, poll_timeout=0)

    def test_http_search_submit_duplicate_weekly_review_accept_and_fresh_status(self):
        with self.client() as client:
            search = client.get('/api/community/repositories?q=image+editor')
            self.assertEqual(search.status_code, 200)
            self.assertEqual(search.json()['items'][0]['status'], 'available')
            with patch.object(store, 'now', return_value='2026-10-10T12:00:00.000Z'):
                first = self.submit(client)
                duplicate = self.submit(client)
            self.assertEqual(first.status_code, 201)
            self.assertIn('store_suggester=', first.headers['set-cookie'])
            self.assertEqual(first.json(), {'ok': True, 'status': 'recorded', 'suggestionCount': 1})
            self.assertEqual(duplicate.json()['status'], 'already_suggested')
            self.assertEqual(duplicate.json()['suggestionCount'], 1)
            self.assertEqual(client.get('/api/community/repositories?q=image+editor').json()['items'][0]['status'], 'suggested')
            jobs.execute('community:2026-10-05', 'community', '2026-10-13')
            self.assertEqual(store.list_apps(), [])
            candidate = store.candidates()[0]
            self.assertEqual(candidate['data']['name'], 'repo-100')
            self.assertEqual(candidate['assessment']['suggestionCount'], 1)
            self.assertEqual(db.query("SELECT state FROM community_suggestions WHERE repo_id='100'")[0]['state'], 'queued')
            self.assertEqual(self.submit(client).json()['status'], 'awaiting_review')
            self.bot()
            review = db.query('SELECT token,draft_version,message_id FROM telegram_reviews')[0]
            buttons = [button for row in self.cards[0]['reply_markup']['inline_keyboard'] for button in row]
            self.assertEqual([b['text'] for b in buttons], ['Open repo', 'Accept', 'Reject', 'More'])
            # An unauthorized callback cannot publish, nor can an unauthorized domain action.
            with self.assertRaises(InputError):
                telegram_review.apply_action(review['token'], review['draft_version'], 'accept', owner_user_id=222, chat_id=111)
            self.assertEqual(store.list_apps(), [])
            self.updates = [{'update_id': 1, 'callback_query': {
                'id': 'synthetic-query', 'from': {'id': 111}, 'data': buttons[1]['callback_data'],
                'message': {'message_id': int(review['message_id']), 'date': 1700000000,
                            'chat': {'id': 111, 'type': 'private'}}}}]
            self.bot()
            self.assertEqual(len(store.list_apps()), 1)
            self.assertEqual(self.submit(client).json()['status'], 'already_listed')
            cached = client.get('/api/community/repositories?q=image+editor')
            self.assertEqual(cached.json()['items'][0]['status'], 'already_listed')
            self.assertEqual(self.provider_requests.count('/search/repositories'), 1)
            self.assertEqual(telegram_review.prepare_reviews(**IDENTITY), [])
            self.assertEqual(db.query("SELECT COUNT(*) AS n FROM community_contributions")[0]['n'], 1)

    def test_real_ranking_freezes_counts_and_resumes_without_an_eleventh_candidate(self):
        self.seed()
        self.fail_repo = '2'
        with patch.object(jobs.logger, 'exception'):
            jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        saved = json.loads(db.query("SELECT checkpoint FROM jobs WHERE id='community:2026-10-05'")[0]['checkpoint'])
        self.assertEqual(saved['index'], 1)
        self.assertEqual([r['repoId'] for r in saved['ranked']], [str(i) for i in range(1, 13)])
        for i in range(20):
            community_requests.record_suggestion(metadata('12'), 'late-browser-'+str(i), at=NOW)
        # Resume the real canonical job with the admin's retry shape.
        manual = 'community:manual:'+str(uuid4())
        db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,'community','queued',$2,$3)", [manual, store.encode(saved), NOW])
        db.query("UPDATE jobs SET status='resumed' WHERE id='community:2026-10-05'")
        settings = store.get_settings(); settings.failedKinds = []; store.write_settings(settings)
        self.fail_repo = None
        jobs.execute(manual, 'community', '2026-10-13')
        self.assertEqual({c['repoId'] for c in store.candidates()}, {str(i) for i in range(1, 11)})
        self.assertTrue(all(c['revision'] == 1 and c['assessment']['suggestionCount'] == 1 for c in store.candidates()))
        self.assertEqual([r['repoId'] for r in community_requests.rank_pending(cutoff='2026-10-19T04:00:00.000Z')], ['12', '11'])
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM community_suggestions WHERE state='queued'")[0]['n'], 10)

    def test_atomic_failure_rolls_back_candidate_queue_marker_and_progress(self):
        self.seed(1)
        original = community_requests.mark_review_queued
        def fail_after_queue(repo_id, *, at):
            original(repo_id, at=at)
            raise RuntimeError('Crash before checkpoint commit')
        with patch.object(community_requests, 'mark_review_queued', side_effect=fail_after_queue), patch.object(jobs.logger, 'exception'):
            jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        self.assertEqual(store.candidates(), [])
        self.assertEqual(db.query('SELECT state FROM community_suggestions')[0]['state'], 'pending')
        saved = json.loads(db.query('SELECT checkpoint FROM jobs')[0]['checkpoint'])
        self.assertEqual(saved['index'], 0)
        self.assertEqual(saved['promotedRepoIds'], [])

    def test_archived_backfill_and_daily_quota(self):
        self.seed()
        self.archived = {'1', '2'}
        db.query("INSERT INTO daily_additions(day,total) VALUES('2026-10-13',10)")
        jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        self.assertEqual({c['repoId'] for c in store.candidates()}, {str(i) for i in range(3, 13)})
        self.assertEqual(db.query('SELECT total FROM daily_additions')[0]['total'], 10)
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM community_suggestions WHERE state='queued'")[0]['n'], 10)

    def test_real_ranking_limits_unavailable_evaluation_to_thirty(self):
        self.seed(35)
        self.archived = {str(i) for i in range(1, 36)}
        jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        saved = json.loads(db.query('SELECT checkpoint FROM jobs')[0]['checkpoint'])
        self.assertEqual(len(saved['ranked']), 30)
        self.assertEqual(saved['index'], 30)
        self.assertEqual(len(saved['skipped']), 30)
        self.assertEqual(store.candidates(), [])
        self.assertEqual(len([p for p in self.provider_requests if not p.endswith(('/readme', '/releases/latest'))]), 30)
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM community_suggestions WHERE state='pending'")[0]['n'], 35)

    def test_search_provider_limit_is_durable_under_concurrent_clients(self):
        def search(index):
            with self.client() as client:
                response = client.get('/api/community/repositories', params={'q': 'unique query '+str(index)},
                                      headers={'X-Store-Proxy': self.config.proxy_secret,
                                               'X-Forwarded-For': f'192.0.2.{index+1}'})
                if response.status_code == 429:
                    self.assertTrue(response.headers['retry-after'].isdigit())
                return response.status_code
        with patch.object(community_github.time, 'time', return_value=1791907200), ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(search, range(20)))
        self.assertEqual(statuses.count(200), 10)
        self.assertEqual(statuses.count(429), 10)
        self.assertEqual(self.provider_requests.count('/search/repositories'), 10)

    def test_concurrent_workers_share_one_batch_and_ten_queue_markers(self):
        self.seed()
        fetching, release = threading.Event(), threading.Event()
        original = github.fetch_repository
        def blocked_fetch(url):
            if url.endswith('repo-1'):
                fetching.set()
                if not release.wait(5):
                    raise AssertionError('Second worker did not complete while lease was active')
            return original(url)
        with patch.object(github, 'fetch_repository', side_effect=blocked_fetch), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(jobs.execute, 'community:2026-10-05', 'community', '2026-10-13')
            try:
                self.assertTrue(fetching.wait(5))
                pool.submit(jobs.execute, 'community:2026-10-05', 'community', '2026-10-13').result(timeout=5)
            finally:
                release.set()
            first.result(timeout=10)
        self.assertEqual(len(store.candidates()), 10)
        self.assertTrue(all(c['revision'] == 1 for c in store.candidates()))
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM community_suggestions WHERE state='queued'")[0]['n'], 10)
        self.assertEqual(db.query("SELECT status FROM jobs WHERE kind='community'")[0]['status'], 'complete')

    def test_pause_during_fetch_keeps_real_queue_and_frozen_progress(self):
        self.seed(1)
        original = github.fetch_repository
        def pause_after_fetch(url):
            data = original(url)
            settings = store.get_settings(); settings.publicationPaused = True; store.write_settings(settings)
            return data
        with patch.object(github, 'fetch_repository', side_effect=pause_after_fetch):
            jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        self.assertEqual(store.candidates(), [])
        self.assertEqual(db.query('SELECT state FROM community_suggestions')[0]['state'], 'pending')
        row = db.query('SELECT status,checkpoint FROM jobs')[0]
        self.assertEqual(row['status'], 'paused')
        self.assertEqual(json.loads(row['checkpoint'])['index'], 0)

    def test_lease_lost_during_fetch_cannot_commit_real_queue_marker(self):
        self.seed(1)
        original = github.fetch_repository
        def lose_after_fetch(url):
            data = original(url)
            db.query("UPDATE leases SET owner='replacement-worker' WHERE id='community'")
            return data
        with patch.object(github, 'fetch_repository', side_effect=lose_after_fetch), patch.object(jobs.logger, 'exception'):
            jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        self.assertEqual(store.candidates(), [])
        self.assertEqual(db.query('SELECT state FROM community_suggestions')[0]['state'], 'pending')
        self.assertEqual(json.loads(db.query('SELECT checkpoint FROM jobs')[0]['checkpoint'])['index'], 0)

    def test_rejected_candidate_stays_excluded_from_backlog_and_review(self):
        self.seed(2)
        store.save_candidate(metadata('1', license='MIT'), {'source': 'earlier-review'})
        store.reject_candidate('1', 1)
        before = db.query("SELECT * FROM candidates WHERE repo_id='1'")
        jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        self.assertEqual(db.query("SELECT * FROM candidates WHERE repo_id='1'"), before)
        self.assertEqual([r['repo_id'] for r in telegram_review.prepare_reviews(**IDENTITY)], ['2'])
        self.assertEqual(community_requests.repository_status('1')['status'], 'already_reviewed')

    def test_paused_publication_keeps_suggestions_pending(self):
        self.seed(1)
        settings = store.get_settings(); settings.publicationPaused = True; store.write_settings(settings)
        jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        self.assertEqual(store.candidates(), [])
        self.assertEqual(db.query('SELECT state FROM community_suggestions')[0]['state'], 'pending')
        settings.publicationPaused = False; store.write_settings(settings)
        jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        self.assertEqual(len(store.candidates()), 1)

    def test_migrated_schema_readiness_and_legacy_idea_requests(self):
        with self.client() as client:
            response = client.post('/api/requests', headers={'Origin': self.config.app_url},
                                   json={'name': 'Offline calendar', 'repoUrl': '', 'website': ''})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {'ok': True, 'status': 'recorded', 'suggestionCount': None})
        before = db.query('SELECT * FROM app_requests')
        schema.upgrade_schema()
        telegram_worker._schema_ready(self.config, db)
        self.assertEqual(db.query('SELECT * FROM app_requests'), before)
        self.assertEqual(db.query('SELECT version_num FROM alembic_version')[0]['version_num'], '0003_community_requests')
        self.assertEqual(community_requests.admin_suggestions(), [])


class SQLiteCases(IntegrationCases, unittest.TestCase):
    engine = 'sqlite'


class PostgreSQLCases(IntegrationCases, unittest.TestCase):
    engine = 'postgres'


def serve_fixture():
    """Optional loopback UI fixture, with the real API and a temporary SQLite DB."""
    global TEMP
    import uvicorn
    TEMP = tempfile.TemporaryDirectory(prefix='community-integration-ui-')
    case = SQLiteCases('test_migrated_schema_readiness_and_legacy_idea_requests')
    try:
        with ExitStack() as guards:
            guards.enter_context(patch.dict(os.environ, {'APP_ENV': 'development'}, clear=True))
            guards.enter_context(patch('dotenv.load_dotenv', return_value=False))
            guards.enter_context(patch.object(sqlite3, 'connect', guarded_sqlite))
            guards.enter_context(patch.object(sqlite3.dbapi2, 'connect', guarded_sqlite))
            guards.enter_context(patch.object(psycopg, 'connect', side_effect=AssertionError('UI fixture forbids PostgreSQL')))
            case.setUp()
            fixture_config = replace(case.config, app_url='http://127.0.0.1:3183')
            for module in (config_module, admin, auth, budget, db, discord, github, jobs, main, schema, store,
                           community_weekly, request_identity):
                guards.enter_context(patch.object(module, 'config', fixture_config, create=True))
            print('Isolated real API fixture: http://127.0.0.1:3184; synthetic providers only.', flush=True)
            uvicorn.run(main.app, host='127.0.0.1', port=3184, log_level='warning', access_log=False)
    finally:
        case.doCleanups()
        TEMP.cleanup()
        TEMP = None


def verify_proxy():
    """Exercise the real Next catch-all proxy against serve_fixture, never production."""
    base = 'http://127.0.0.1:3183'
    with RAW_HTTP_CLIENT(base_url=base, timeout=30, headers={
            'Origin': base, 'X-Forwarded-For': '192.0.2.201'}) as client:
        result = client.get('/api/community/repositories', params={'q': 'image editor'})
        assert result.status_code == 200, result.status_code
        data = {'name': 'Proxy test', 'repoUrl': 'https://github.com/synthetic/repo-100', 'website': ''}
        first = client.post('/api/requests', json=data)
        assert first.status_code == 201, first.status_code
        cookie = first.headers['set-cookie']
        assert 'store_suggester=' in cookie and 'HttpOnly' in cookie and 'SameSite=lax' in cookie
        assert 'Max-Age=15552000' in cookie
        assert first.json()['status'] == 'recorded', first.json()
        duplicate = client.post('/api/requests', json=data)
        assert duplicate.json() == {'ok': True, 'status': 'already_suggested', 'suggestionCount': 1}, duplicate.json()
        cached = client.get('/api/community/repositories', params={'q': 'image editor'})
        assert cached.json()['items'][0]['status'] == 'suggested', cached.json()
        idea = client.post('/api/requests', json={'name': 'Offline calendar', 'repoUrl': '', 'website': ''})
        assert idea.status_code == 201 and idea.json()['suggestionCount'] is None
        print('PASS real Next proxy: search, signed Set-Cookie/cookie roundtrip, duplicate count, fresh cached status and legacy idea.')


if __name__ == '__main__':
    if sys.argv[1:] == ['--serve-fixture']:
        serve_fixture()
    elif sys.argv[1:] == ['--verify-proxy']:
        verify_proxy()
    else:
        unittest.main()


