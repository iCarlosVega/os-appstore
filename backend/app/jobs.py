import json
import logging
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from . import db, store, budget, discord
from .backup import backup_database
from .config import config
from .discovery import discover
from .maintenance import maintain
from .models import JOB_KINDS
from .community_weekly import closed_week, promote_weekly, week_context

logger = logging.getLogger(__name__)

def future(seconds):
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")

@dataclass
class JobContext:
    id: str
    lease_id: str
    owner: str
    local_day: str
    saved: dict

    def assert_lease(self):
        rows = db.query("SELECT owner,expires_at FROM leases WHERE id=$1", [self.lease_id])
        if not rows or rows[0]["owner"] != self.owner or rows[0]["expires_at"] <= store.now():
            raise RuntimeError("Job lease expired. Resume after review.")

    def checkpoint(self, data):
        with db.transaction():
            self.assert_lease()
            db.query("UPDATE jobs SET checkpoint=$1 WHERE id=$2", [store.encode(data), self.id])
        self.saved = data

def digest():
    pending = [c for c in store.candidates() if c["status"] == "pending"]
    costs = budget.usage()
    requests = db.query("SELECT COUNT(*) AS total FROM app_requests WHERE status='pending'")[0]["total"]
    changes = db.query("SELECT COUNT(*) AS total FROM proposals WHERE status='pending'")[0]["total"]
    uncertain = sum(c["data"]["costModel"] == "Needs review" or not c["assessment"].get("decisions") or c["assessment"]["decisions"].get("suitable", {}).get("noul", 0) < .5 for c in pending)
    runs = db.query("SELECT kind,status,started_at FROM jobs ORDER BY started_at DESC LIMIT 5")
    recent = "\n".join(f"• {run['kind']}: {run['status']} ({run['started_at'][:10]})" for run in runs)
    names = "\n".join(f"• {c['data']['name'][:80]}" + (" (NSFW — excluded from publication)" if c["data"]["nsfw"] else "") for c in pending[:8])
    return discord.queue(f"Weekly software store digest\nReview: {config.app_url}/admin\n{len(pending)} candidates · {uncertain} uncertain · {requests} app requests · {changes} changes to review\nCosts ({costs['period']}): Jev {budget.money(costs['ai'])}, hosting allowance/usage {budget.money(costs['hosting'])}, total {budget.money(costs['total'])} / {budget.money(costs['budget'])}\nOther agent providers: not configured.\nRecent runs (up to 5):\n{recent}\nCandidates (up to 8):\n{names}")

def _blocked(kind, settings):
    external = kind in ("discovery", "maintenance", "priority", "community")
    return kind not in JOB_KINDS or kind in settings.failedKinds or (external and (settings.budgetPaused or not config.github_token)) or (kind in ("discovery", "community") and settings.discoveryPaused) or (kind == "community" and settings.publicationPaused) or (kind in ("maintenance", "priority") and settings.maintenancePaused)

def _community_alias(job_id):
    """Normalize admin's manual/retry jobs to one dated, capped batch."""
    if not re.fullmatch(r"community:manual:[0-9a-f-]{36}", job_id):
        return job_id
    rows = db.query("SELECT checkpoint FROM jobs WHERE id=$1 AND kind='community'", [job_id])
    if not rows:
        raise RuntimeError("Community retry job is unavailable.")
    saved = json.loads(rows[0]["checkpoint"])
    week = week_context(saved["weekStart"], store.get_settings().timezone) if saved else closed_week(datetime.now(UTC), store.get_settings().timezone)
    canonical = f"community:{week['weekStart']}"
    existing = db.query("SELECT status FROM jobs WHERE id=$1", [canonical])
    if not existing:
        db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,'community','queued',$2,$3)", [canonical, store.encode(saved), store.now()])
    elif existing[0]["status"] in ("failed", "resumed"):
        # The canonical row is authoritative; never reset its frozen checkpoint.
        db.query("UPDATE jobs SET status='queued',error=NULL,finished_at=NULL WHERE id=$1", [canonical])
    db.query("UPDATE jobs SET status='resumed',finished_at=$2 WHERE id=$1", [job_id, store.now()])
    return canonical

def execute(job_id, kind, local_day):
    owner = str(uuid4())
    lease_id = "maintenance" if kind == "priority" else kind
    with db.transaction():
        if _blocked(kind, store.get_settings()):
            return
        leases = db.query("SELECT * FROM leases WHERE id=$1", [lease_id])
        if leases and leases[0]["expires_at"] > store.now():
            return
        if kind == "community":
            job_id = _community_alias(job_id)
        rows = db.query("SELECT status,checkpoint FROM jobs WHERE id=$1", [job_id])
        if rows and rows[0]["status"] in ("complete", "failed", "resumed", "skipped"):
            return
        db.query("INSERT INTO leases(id,owner,expires_at) VALUES($1,$2,$3) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at", [lease_id, owner, future(120)])
        saved = rows[0]["checkpoint"] if rows else "{}"
        if kind == "community" and saved == "{}" and re.fullmatch(r"community:\d{4}-\d{2}-\d{2}", job_id):
            week = week_context(job_id.removeprefix("community:"), store.get_settings().timezone)
            # Keep retry identity/cutoff even if ranking fails before its snapshot.
            saved = store.encode({key: week[key] for key in ("weekStart", "cutoff")})
        db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,$2,'running',$3,$4) ON CONFLICT(id) DO UPDATE SET status='running',checkpoint=excluded.checkpoint,error=NULL,finished_at=NULL", [job_id, kind, saved, store.now()])
    job = JobContext(job_id, lease_id, owner, local_day, {})
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(20):
            try:
                with db.transaction():
                    db.query("UPDATE leases SET expires_at=$1 WHERE id=$2 AND owner=$3 AND expires_at>$4", [future(120), lease_id, owner, store.now()])
            except Exception:
                logger.warning("Job lease heartbeat failed.")
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        job.saved = json.loads(saved)
        if not isinstance(job.saved, dict):
            raise RuntimeError("Job checkpoint is invalid. Review before resuming.")
        stopped_for_pause = False
        if kind == "discovery":
            stopped_for_pause = discover(job) is False
        elif kind == "community":
            stopped_for_pause = promote_weekly(job) is False
        elif kind == "digest":
            with db.transaction():
                job.assert_lease()
                notification_id = job.saved.get("notificationId")
                if not notification_id:
                    notification_id = digest()
                    job.checkpoint({**job.saved, "notificationId": notification_id})
            discord.deliver(notification_id)
        elif kind == "backup":
            backup_database()
        else:
            stopped_for_pause = maintain(job, kind == "priority") is False
        with db.transaction():
            job.assert_lease()
            settings = store.get_settings()
            external = kind in ("discovery", "maintenance", "priority", "community")
            paused = external and (stopped_for_pause or _blocked(kind, settings))
            db.query("UPDATE jobs SET status=$1,finished_at=$2 WHERE id=$3", ["paused" if paused else "complete", store.now(), job_id])
    except Exception as error:
        logger.exception("%s job failed", kind)
        message = str(error)[:500] if isinstance(error, RuntimeError) else f"{type(error).__name__}: backend job failed. Review server logs."
        notice = None
        with db.transaction():
            leases = db.query("SELECT owner FROM leases WHERE id=$1", [lease_id])
            if leases and leases[0]["owner"] == owner:
                db.query("UPDATE jobs SET status='failed',error=$1,finished_at=$2 WHERE id=$3", [message, store.now(), job_id])
                settings = store.get_settings()
                if kind not in settings.failedKinds:
                    settings.failedKinds.append(kind)
                store.write_settings(settings)
                notice = discord.queue(f"{kind} job failed and is waiting for owner response. {message}\nReview and resume: {config.app_url}/admin?tab=operations")
        if notice:
            discord.deliver(notice)
    finally:
        stop.set()
        thread.join(timeout=11)
        db.query("DELETE FROM leases WHERE id=$1 AND owner=$2", [lease_id, owner])

def run_due_jobs():
    budget.enforce()
    settings = store.get_settings()
    local = datetime.now(ZoneInfo(settings.timezone))
    day, clock = local.date().isoformat(), local.strftime("%H:%M")
    schedule = [("discovery", settings.discoveryTime, True), ("maintenance", settings.maintenanceTime, local.weekday() == 6), ("priority", settings.priorityTime, True), ("digest", settings.digestTime, local.weekday() == 0), ("backup", settings.backupTime, True)]
    for kind, scheduled, day_matches in schedule:
        if day_matches and clock >= scheduled and (kind in ("digest", "backup") or config.github_token):
            db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,$2,'queued','{}',$3) ON CONFLICT(id) DO NOTHING", [f"{kind}:{day}", kind, store.now()])
    community_week = closed_week(local, settings.timezone)
    community_id = f"community:{community_week['weekStart']}"
    if config.github_token:
        db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,'community','queued','{}',$2) ON CONFLICT(id) DO NOTHING", [community_id, store.now()])
    queued = db.query("SELECT * FROM jobs WHERE status IN ('queued','running','paused') ORDER BY started_at")
    for row in queued:
        kind = row["kind"]
        current = store.get_settings()
        if _blocked(kind, current):
            continue
        obsolete_community = (kind == "community" and row["id"] < community_id
                              and re.fullmatch(r"community:\d{4}-\d{2}-\d{2}", row["id"]))
        if obsolete_community:
            with db.transaction():
                # Recheck under the writer lock: another worker may have frozen
                # the batch or claimed its lease since the queue was read.
                leases = db.query("SELECT expires_at FROM leases WHERE id='community'")
                if leases and leases[0]["expires_at"] > store.now():
                    continue
                latest = db.query("SELECT status,checkpoint FROM jobs WHERE id=$1", [row["id"]])
                if not latest or latest[0]["status"] not in ("queued", "running", "paused"):
                    continue
                try:
                    checkpoint = json.loads(latest[0]["checkpoint"])
                except (ValueError, TypeError):
                    checkpoint = None
                unfrozen = checkpoint == {} or (isinstance(checkpoint, dict) and set(checkpoint) == {"weekStart", "cutoff"})
                if unfrozen:
                    db.query("UPDATE jobs SET status='skipped',finished_at=$2 WHERE id=$1", [row["id"], store.now()])
                    continue
        stale_daily = kind != "community" and re.fullmatch(r"[a-z]+:\d{4}-\d{2}-\d{2}", row["id"]) and not row["id"].endswith(day)
        if row["status"] == "queued" and stale_daily:
            db.query("UPDATE jobs SET status='skipped',finished_at=$2 WHERE id=$1 AND status='queued'", [row["id"], store.now()])
            continue
        execute(row["id"], kind, day)
    db.query("DELETE FROM rate_limits WHERE expires_at<$1", [store.now()])
    db.query("DELETE FROM search_cache WHERE expires_at<$1", [store.now()])
    db.query("DELETE FROM jobs WHERE finished_at<$1 AND status IN ('complete','skipped')", [future(-30 * 86400)])
    db.query("DELETE FROM audit WHERE created_at<$1", [future(-365 * 86400)])
    db.query("DELETE FROM cost_entries WHERE created_at<$1 AND settled=1", [future(-365 * 86400)])
