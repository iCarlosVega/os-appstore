"""Weekly lane gate: disposable DBs, mocked GitHub and Session 1 persistence seam."""
import copy
import importlib
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
import unittest
from contextlib import ExitStack, closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
import psycopg
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
with patch('dotenv.load_dotenv', return_value=False):
    from backend.app import db, schema, store, jobs, github, budget, discord, telegram_review
    from backend.app.models import Metadata, Settings
    import backend.app as app_package
    config_module = importlib.import_module('backend.app.config')
try:
    weekly = importlib.import_module('backend.app.community_weekly')
except ModuleNotFoundError:
    weekly = None

BASE_CONFIG = config_module.config
TEMP = CONTAINER = GUARDS = None
PG_URL = PG_PORT = None
RAW_PG_CONNECT, RAW_SQLITE_CONNECT = psycopg.connect, sqlite3.connect
NOW = '2026-10-13T16:00:00.000Z'


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 13, 16, tzinfo=UTC).astimezone(tz or UTC)


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, stderr=subprocess.PIPE).strip()


def guarded_pg(conninfo='', **kwargs):
    values = conninfo_to_dict(conninfo, **{k: v for k, v in kwargs.items()
                                       if k not in ('autocommit', 'row_factory', 'context', 'prepare_threshold')})
    if (values.get('host'), values.get('port'), values.get('dbname'), values.get('user')) != (
            '127.0.0.1', PG_PORT, 'community_weekly_verification', 'verifier'):
        raise AssertionError('Only this suite disposable PostgreSQL destination is allowed')
    return RAW_PG_CONNECT(conninfo, **kwargs)


def guarded_sqlite(database, *args, **kwargs):
    value = os.fspath(database)
    path = Path(urlsplit(value).path if value.startswith('file:') else value).resolve()
    if TEMP is None or not path.is_relative_to(Path(TEMP.name).resolve()):
        raise AssertionError('Only this suite temporary SQLite files are allowed')
    return RAW_SQLITE_CONNECT(database, *args, **kwargs)


def cleanup():
    global TEMP, CONTAINER, GUARDS
    if GUARDS:
        GUARDS.close()
        GUARDS = None
    if CONTAINER:
        docker('rm', '-f', CONTAINER)
        CONTAINER = None
    if TEMP:
        TEMP.cleanup()
        TEMP = None


def setUpModule():
    global TEMP, CONTAINER, GUARDS, PG_URL, PG_PORT
    TEMP = tempfile.TemporaryDirectory(prefix='community-weekly-verify-')
    try:
        password = uuid4().hex
        CONTAINER = docker('run', '--detach', '--rm', '--pull=never', '--name',
                           'community-weekly-verify-' + uuid4().hex[:12], '--tmpfs',
                           '/var/lib/postgresql/data:rw', '-p', '127.0.0.1::5432',
                           '-e', 'POSTGRES_USER=verifier', '-e', 'POSTGRES_DB=community_weekly_verification',
                           '-e', 'POSTGRES_PASSWORD=' + password, 'postgres:17')
        PG_PORT = docker('port', CONTAINER, '5432/tcp').rsplit(':', 1)[1]
        PG_URL = f'postgresql://verifier:{password}@127.0.0.1:{PG_PORT}/community_weekly_verification'
        for _ in range(100):
            try:
                with RAW_PG_CONNECT(PG_URL, connect_timeout=1):
                    break
            except psycopg.OperationalError:
                time.sleep(.1)
        else:
            raise RuntimeError('Disposable database unavailable')
        GUARDS = ExitStack()
        GUARDS.enter_context(patch.object(psycopg, 'connect', guarded_pg))
        GUARDS.enter_context(patch.object(sqlite3, 'connect', guarded_sqlite))
        GUARDS.enter_context(patch.object(sqlite3.dbapi2, 'connect', guarded_sqlite))
        GUARDS.enter_context(patch.object(socket.socket, 'connect', side_effect=AssertionError('Live network forbidden')))
        GUARDS.enter_context(patch.object(socket, 'create_connection', side_effect=AssertionError('Live network forbidden')))
        GUARDS.enter_context(patch('dotenv.load_dotenv', return_value=False))
    except BaseException:
        cleanup()
        raise


def tearDownModule():
    cleanup()


def metadata(repo_id, **changes):
    return Metadata(**(dict(repoId=str(repo_id), repoUrl=f'https://github.com/fixture/repo-{repo_id}',
                            name=f'Project {repo_id}', creator='fixture', creatorUrl='https://github.com/fixture',
                            license='MIT', description='A useful project.', sources=[f'https://github.com/fixture/repo-{repo_id}']) | changes))


class CalendarCases(unittest.TestCase):
    def test_latest_closed_week_and_dst(self):
        self.assertIsNotNone(weekly, 'Weekly service must implement calendar boundaries')
        fixtures = [
            ('2026-10-12T04:04:59+00:00', '2026-09-28', '2026-10-05T04:00:00.000Z', '2026-10-05T04:05:00.000Z'),
            ('2026-10-12T04:05:00+00:00', '2026-10-05', '2026-10-12T04:00:00.000Z', '2026-10-12T04:05:00.000Z'),
            ('2026-03-09T04:05:00+00:00', '2026-03-02', '2026-03-09T04:00:00.000Z', '2026-03-09T04:05:00.000Z'),
            ('2026-11-02T05:05:00+00:00', '2026-10-26', '2026-11-02T05:00:00.000Z', '2026-11-02T05:05:00.000Z'),
            ('2026-10-18T23:00:00+00:00', '2026-10-05', '2026-10-12T04:00:00.000Z', '2026-10-12T04:05:00.000Z'),
        ]
        for now, start, cutoff, due in fixtures:
            with self.subTest(now=now):
                self.assertEqual(weekly.closed_week(datetime.fromisoformat(now), 'America/New_York'),
                                 {'weekStart': start, 'cutoff': cutoff, 'dueAt': due})
        with self.assertRaises(ValueError):
            weekly.closed_week(datetime(2026, 10, 12), 'America/New_York')


class DatabaseCases:
    engine = None

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.schema_name = 'case_' + uuid4().hex
        url = ''
        if self.engine == 'postgres':
            with closing(psycopg.connect(PG_URL, autocommit=True)) as connection:
                connection.execute('CREATE SCHEMA "' + self.schema_name + '"')
            url = PG_URL + '?options=' + quote('-csearch_path=' + self.schema_name)
            self.addCleanup(self.drop_schema)
        self.config = replace(BASE_CONFIG, database_url=url, sqlite_path=Path(TEMP.name)/(uuid4().hex+'.sqlite'),
                              production=False, github_token='synthetic-token', typesafe_key='', discord_webhook='',
                              telegram_enabled=False)
        for module in (config_module, db, schema, store, jobs, github, budget, discord):
            self.stack.enter_context(patch.object(module, 'config', self.config))
        if weekly:
            self.stack.enter_context(patch.object(weekly, 'config', self.config))
        self.stack.enter_context(patch.object(store, 'now', return_value=NOW))
        self.stack.enter_context(patch.object(jobs, 'datetime', Clock))
        schema.upgrade_schema()
        store.initialize()
        self.ranked = [dict(repoId=str(i), repoUrl=f'https://github.com/fixture/repo-{i}', name=f'Project {i}',
                            suggestionCount=40-i, firstSuggestedAt='2026-10-01T12:00:00.000Z') for i in range(1, 31)]
        self.rank_cutoffs, self.fetches = [], []
        seam = types.ModuleType('backend.app.community_requests')
        def rank_pending(*, cutoff, limit=30):
            self.rank_cutoffs.append(cutoff)
            return copy.deepcopy(self.ranked[:limit])
        def mark_review_queued(repo_id, *, at):
            if db._connection.get() is None:
                raise AssertionError('Queue marker must share candidate/checkpoint transaction')
            store.audit('fixture.queued', {'repoId': repo_id, 'at': at})
        seam.rank_pending, seam.mark_review_queued = rank_pending, mark_review_queued
        self.seam = seam
        self.stack.enter_context(patch.dict(sys.modules, {'backend.app.community_requests': seam}))
        self.stack.enter_context(patch.object(app_package, 'community_requests', seam, create=True))
        def fetch(url):
            if db._connection.get() is not None:
                raise AssertionError('Provider I/O inside transaction')
            self.fetches.append(url)
            return metadata(url.rsplit('-', 1)[1])
        self.fetch = fetch
        self.stack.enter_context(patch.object(github, 'fetch_repository', side_effect=fetch))

    def drop_schema(self):
        with closing(psycopg.connect(PG_URL, autocommit=True)) as connection:
            connection.execute('DROP SCHEMA "' + self.schema_name + '" CASCADE')

    def job(self, job_id='community:2026-10-05', owner='fixture-owner'):
        db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,'community','running','{}',$2) ON CONFLICT(id) DO NOTHING", [job_id, NOW])
        db.query("INSERT INTO leases(id,owner,expires_at) VALUES('community',$1,'2099-01-01T00:00:00.000Z') ON CONFLICT(id) DO UPDATE SET owner=$1", [owner])
        saved = json.loads(db.query('SELECT checkpoint FROM jobs WHERE id=$1', [job_id])[0]['checkpoint'])
        return jobs.JobContext(job_id, 'community', owner, '2026-10-13', saved)

    def promote(self, job=None):
        self.assertIsNotNone(weekly, 'Weekly service must persist frozen top-ten batches')
        return weekly.promote_weekly(job or self.job())

    def pause(self, **fields):
        store.write_settings(Settings.model_validate(store.get_settings().model_dump() | fields))

    def test_ranked_backfill_and_ten_cap(self):
        def fetch(url):
            data = self.fetch(url)
            if int(data.repoId) < 4:
                raise github.MissingRepository('Unavailable')
            return data
        with patch.object(github, 'fetch_repository', side_effect=fetch):
            self.assertTrue(self.promote())
        self.assertEqual([c['repoId'] for c in sorted(store.candidates(), key=lambda c: int(c['repoId']))], [str(i) for i in range(4, 14)])
        self.assertEqual(len(self.fetches), 13)
        self.assertEqual(db.query('SELECT COUNT(*) AS n FROM apps')[0]['n'], 0)

    def test_evaluation_cap(self):
        self.ranked += [dict(self.ranked[0], repoId='99', repoUrl='https://github.com/fixture/repo-99')]
        def missing(url):
            self.fetch(url)
            raise github.MissingRepository('Unavailable')
        with patch.object(github, 'fetch_repository', side_effect=missing):
            self.assertTrue(self.promote())
        self.assertEqual(len(self.fetches), 30)
        self.assertEqual(len(store.candidates()), 0)

    def test_snapshot_excludes_late_votes(self):
        job = self.job()
        def unavailable(url):
            raise github.GithubError('Transient')
        with patch.object(github, 'fetch_repository', side_effect=unavailable):
            with self.assertRaises(RuntimeError): self.promote(job)
        self.ranked.reverse()  # Late popularity changes must not change the saved order.
        self.assertTrue(self.promote(self.job()))
        self.assertEqual(self.rank_cutoffs, ['2026-10-12T04:00:00.000Z'])
        self.assertEqual({c['repoId'] for c in store.candidates()}, {str(i) for i in range(1, 11)})

    def test_resume_after_atomic_promotion(self):
        job = self.job()
        real = job.checkpoint
        def crash(progress):
            real(progress)
            if progress['index'] == 1:
                raise RuntimeError('Injected crash before commit')
        with patch.object(job, 'checkpoint', side_effect=crash):
            with self.assertRaises(RuntimeError): self.promote(job)
        self.assertEqual(store.candidates(), [])
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM audit WHERE action='fixture.queued'")[0]['n'], 0)
        self.assertTrue(self.promote(self.job()))
        self.assertEqual(len(store.candidates()), 10)
        self.assertTrue(all(c['revision'] == 1 for c in store.candidates()))

    def test_two_workers_and_lost_lease(self):
        old = self.job()
        db.query("UPDATE leases SET owner='other' WHERE id='community'")
        with self.assertRaises(RuntimeError): self.promote(old)
        self.assertEqual(store.candidates(), [])
        self.assertTrue(self.promote(self.job(owner='other')))
        self.assertEqual(len(store.candidates()), 10)

    def test_lease_lost_during_fetch(self):
        def fetch(url):
            data = self.fetch(url)
            db.query("UPDATE leases SET owner='replacement' WHERE id='community'")
            return data
        with patch.object(github, 'fetch_repository', side_effect=fetch):
            with self.assertRaises(RuntimeError): self.promote()
        self.assertEqual(store.candidates(), [])

    def test_all_pause_controls(self):
        for field in ('discoveryPaused', 'budgetPaused', 'publicationPaused'):
            with self.subTest(field=field):
                self.pause(**{field: True})
                self.assertFalse(self.promote())
                self.assertEqual(store.candidates(), [])
                self.pause(**{field: False})
        self.pause(failedKinds=['community'])
        self.assertFalse(self.promote())
        self.pause(failedKinds=[])
        if weekly:
            with patch.object(weekly, 'config', replace(self.config, github_token='')):
                self.assertFalse(self.promote())
        self.pause(aiPaused=True)
        self.assertTrue(self.promote())

    def test_pause_during_fetch_preserves_item(self):
        def fetch(url):
            data = self.fetch(url)
            self.pause(publicationPaused=True)
            return data
        with patch.object(github, 'fetch_repository', side_effect=fetch):
            self.assertFalse(self.promote())
        self.assertEqual(store.candidates(), [])
        self.assertEqual(self.job().saved['index'], 0)

    def test_existing_candidate_unchanged(self):
        for i, state in ((1, 'pending'), (2, 'rejected')):
            store.save_candidate(metadata(i), {'source': 'original'})
            if state == 'rejected': store.reject_candidate(str(i), 1)
        before = {c['repoId']: c for c in store.candidates()}
        self.assertTrue(self.promote())
        after = {c['repoId']: c for c in store.candidates()}
        self.assertEqual([after['1'], after['2']], [before['1'], before['2']])
        self.assertEqual(len(after), 12)

    def test_candidate_appearing_during_fetch_is_not_overwritten(self):
        def fetch(url):
            data = self.fetch(url)
            if data.repoId == '1': store.save_candidate(data, {'source': 'concurrent-discovery'})
            return data
        with patch.object(github, 'fetch_repository', side_effect=fetch):
            self.assertTrue(self.promote())
        first = next(c for c in store.candidates() if c['repoId'] == '1')
        self.assertEqual(first['assessment'], {'source': 'concurrent-discovery'})
        self.assertEqual(first['revision'], 1)

    def test_transient_failure_does_not_advance(self):
        def fetch(url):
            data = self.fetch(url)
            if data.repoId == '2': raise github.GithubError('synthetic-sensitive-provider-detail')
            return data
        with patch.object(github, 'fetch_repository', side_effect=fetch):
            with self.assertRaises(RuntimeError) as failure: self.promote()
        self.assertNotIn('synthetic-sensitive', str(failure.exception))
        saved = self.job().saved
        self.assertEqual(saved['index'], 1)
        self.assertEqual(saved['promotedRepoIds'], ['1'])
        self.assertTrue(self.promote(self.job()))
        self.assertEqual(len(store.candidates()), 10)

    def test_404_archived_are_skipped(self):
        def fetch(url):
            data = self.fetch(url)
            if data.repoId == '1': raise github.MissingRepository('Unavailable')
            return data.model_copy(update={'archived': data.repoId == '2'})
        with patch.object(github, 'fetch_repository', side_effect=fetch): self.assertTrue(self.promote())
        self.assertNotIn('1', {c['repoId'] for c in store.candidates()})
        self.assertNotIn('2', {c['repoId'] for c in store.candidates()})

    def test_reused_repository_path_cannot_change_identity(self):
        with patch.object(github, 'fetch_repository', return_value=metadata('999')):
            self.assertTrue(self.promote())
        self.assertEqual(store.candidates(), [])

    def test_daily_quota_unchanged(self):
        db.query("INSERT INTO daily_additions(day,total) VALUES('2026-10-13',10)")
        self.assertTrue(self.promote())
        self.assertEqual(db.query('SELECT total FROM daily_additions')[0]['total'], 10)
        self.assertEqual(store.get_settings().dailyCandidates, 10)

    def test_telegram_offline_does_not_lose_candidates(self):
        self.assertTrue(self.promote())
        self.assertEqual(len(store.candidates()), 10)
        views = telegram_review.prepare_reviews(owner_user_id=111, chat_id=111, limit=5)
        self.assertEqual(len(views), 5)
        first = store.candidates()[0]
        self.assertEqual(first['assessment']['source'], 'community-weekly')
        self.assertEqual(first['assessment']['cutoff'], '2026-10-12T04:00:00.000Z')
        self.assertEqual(first['data']['costModel'], 'Needs review')
        self.assertEqual(first['data']['platforms'], [])
        self.assertEqual(db.query('SELECT COUNT(*) AS n FROM apps')[0]['n'], 0)

    def test_missed_monday_runs_once_later(self):
        # Tuesday restart must enqueue the closed week, not stale-skip it.
        with patch.object(jobs, 'execute') as execute, patch.object(budget, 'enforce'):
            jobs.run_due_jobs()
            jobs.run_due_jobs()
        rows = db.query("SELECT id,status FROM jobs WHERE kind='community'")
        self.assertEqual(rows, [{'id': 'community:2026-10-05', 'status': 'queued'}])
        self.assertTrue(any(call.args[0] == 'community:2026-10-05' for call in execute.call_args_list))

    def test_community_dispatch_and_complete_is_idempotent(self):
        self.assertIsNotNone(weekly, 'Community must be a runnable scheduled job')
        jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        self.assertEqual(db.query("SELECT status FROM jobs WHERE id='community:2026-10-05'")[0]['status'], 'complete')
        self.assertEqual(len(store.candidates()), 10)

    def test_superseded_unfrozen_jobs_skip_all_recoverable_statuses(self):
        old = [('community:2026-09-07', 'queued', '{}'),
               ('community:2026-09-14', 'running', '{}'),
               ('community:2026-09-21', 'paused', '{}'),
               ('community:2026-09-28', 'paused', store.encode({
                   'weekStart': '2026-09-28', 'cutoff': '2026-10-05T04:00:00.000Z'}))]
        for job_id, status, checkpoint in old:
            db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,'community',$2,$3,$4)", [job_id, status, checkpoint, '2026-10-01T12:00:00.000Z'])
        db.query("INSERT INTO leases(id,owner,expires_at) VALUES('community','crashed-worker','2026-10-01T12:00:00.000Z')")
        with patch.object(jobs, 'execute') as execute, patch.object(budget, 'enforce'):
            jobs.run_due_jobs()
        for job_id, _, _ in old:
            self.assertEqual(db.query('SELECT status FROM jobs WHERE id=$1', [job_id])[0]['status'], 'skipped')
        community_calls = [call.args[0] for call in execute.call_args_list if call.args[1] == 'community']
        self.assertEqual(community_calls, ['community:2026-10-05'])

    def test_superseded_unfrozen_job_with_live_lease_is_preserved(self):
        old = self.job('community:2026-09-28', owner='live-worker')
        with patch.object(jobs, 'execute') as execute, patch.object(budget, 'enforce'):
            jobs.run_due_jobs()
        self.assertEqual(db.query('SELECT status,checkpoint FROM jobs WHERE id=$1', [old.id])[0],
                         {'status': 'running', 'checkpoint': '{}'})
        self.assertFalse(any(call.args[0] == old.id for call in execute.call_args_list))
        self.assertEqual(db.query("SELECT owner FROM leases WHERE id='community'")[0]['owner'], 'live-worker')

    def test_superseded_frozen_paused_batch_is_preserved(self):
        old = self.job('community:2026-09-28')
        with patch.object(github, 'fetch_repository', side_effect=github.GithubError('Transient')):
            with self.assertRaises(RuntimeError): self.promote(old)
        checkpoint = db.query('SELECT checkpoint FROM jobs WHERE id=$1', [old.id])[0]['checkpoint']
        db.query("UPDATE jobs SET status='paused' WHERE id=$1", [old.id])
        db.query("DELETE FROM leases WHERE id='community'")
        with patch.object(jobs, 'execute') as execute, patch.object(budget, 'enforce'):
            jobs.run_due_jobs()
        self.assertEqual(db.query('SELECT status,checkpoint FROM jobs WHERE id=$1', [old.id])[0],
                         {'status': 'paused', 'checkpoint': checkpoint})
        self.assertTrue(any(call.args[0] == old.id for call in execute.call_args_list))

    def test_second_worker_does_not_take_live_lease(self):
        self.job(owner='running-worker')
        jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        self.assertEqual(store.candidates(), [])
        self.assertEqual(db.query("SELECT owner FROM leases WHERE id='community'")[0]['owner'], 'running-worker')

    def test_manual_empty_job_reuses_frozen_batch(self):
        jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        self.ranked.reverse()
        manual = 'community:manual:' + str(uuid4())
        db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,'community','queued','{}',$2)", [manual, NOW])
        jobs.execute(manual, 'community', '2026-10-13')
        self.assertEqual(len(store.candidates()), 10)
        self.assertEqual(self.rank_cutoffs, ['2026-10-12T04:00:00.000Z'])

    def test_manual_resume_uses_same_week_and_cap(self):
        def fetch(url):
            data = self.fetch(url)
            if data.repoId == '3': raise github.GithubError('Transient')
            return data
        with patch.object(github, 'fetch_repository', side_effect=fetch), patch.object(jobs.logger, 'exception'):
            jobs.execute('community:2026-10-05', 'community', '2026-10-13')
        row = db.query("SELECT * FROM jobs WHERE id='community:2026-10-05'")[0]
        self.assertEqual(row['status'], 'failed')
        manual = 'community:manual:' + str(uuid4())
        db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,'community','queued',$2,$3)", [manual, row['checkpoint'], NOW])
        db.query("UPDATE jobs SET status='resumed' WHERE id='community:2026-10-05'")
        self.pause(failedKinds=[])
        jobs.execute(manual, 'community', '2026-10-20')
        self.assertEqual(len(store.candidates()), 10)
        self.assertEqual(self.rank_cutoffs, ['2026-10-12T04:00:00.000Z'])

    def test_failure_before_snapshot_retries_original_cutoff_next_week(self):
        original = 'community:2026-10-05'
        with patch.object(self.seam, 'rank_pending', side_effect=RuntimeError('Ranking unavailable')), patch.object(jobs.logger, 'exception'):
            jobs.execute(original, 'community', '2026-10-13')
        row = db.query('SELECT status,checkpoint FROM jobs WHERE id=$1', [original])[0]
        self.assertEqual(row['status'], 'failed')
        # Reproduce admin's retry: copy the failed checkpoint into a manual alias.
        manual = 'community:manual:' + str(uuid4())
        db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,'community','queued',$2,$3)", [manual, row['checkpoint'], NOW])
        db.query("UPDATE jobs SET status='resumed' WHERE id=$1", [original])
        self.pause(failedKinds=[], timezone='UTC')
        later = datetime(2026, 10, 20, 16, tzinfo=UTC)
        with patch.object(jobs, 'datetime') as clock, patch.object(store, 'now', return_value='2026-10-20T16:00:00.000Z'):
            clock.now.side_effect = lambda tz=None: later.astimezone(tz or UTC)
            jobs.execute(manual, 'community', '2026-10-20')
        self.assertEqual(self.rank_cutoffs, ['2026-10-12T04:00:00.000Z'])
        self.assertEqual(db.query('SELECT status FROM jobs WHERE id=$1', [original])[0]['status'], 'complete')
        self.assertEqual(len(store.candidates()), 10)

    def test_six_failed_kinds_are_supported(self):
        self.pause(failedKinds=['discovery', 'maintenance', 'priority', 'digest', 'backup', 'community'])
        self.assertEqual(len(store.get_settings().failedKinds), 6)


class SQLiteCases(DatabaseCases, unittest.TestCase):
    engine = 'sqlite'


class PostgreSQLCases(DatabaseCases, unittest.TestCase):
    engine = 'postgres'
