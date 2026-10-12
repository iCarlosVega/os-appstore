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
        self.assert_lease()
        db.query("UPDATE jobs SET checkpoint=$1 WHERE id=$2", [store.encode(data), self.id])
        self.saved = data

def digest():
    pending = [c for c in store.candidates() if c["status"] == "pending"]
    costs = budget.usage()
    requests = db.query("SELECT COUNT(*) AS total FROM app_requests WHERE status='pending'")[0]["total"]
    changes = db.query("SELECT COUNT(*) AS total FROM proposals WHERE status='pending'")[0]["total"]
    names = "\n".join(f"• {c['data']['name']}" + (" (NSFW — excluded from publication)" if c["data"]["nsfw"] else "") for c in pending[:15])
    discord.notify(f"Weekly software store digest\n{len(pending)} candidates · {requests} app requests · {changes} changes to review\n{names}\nCosts ({costs['period']}): Jev {budget.money(costs['ai'])}, hosting allowance/usage {budget.money(costs['hosting'])}, total {budget.money(costs['total'])} / {budget.money(costs['budget'])}\nOther agent providers: not configured.\nReview: {config.app_url}/admin")

def execute(job_id, kind, local_day):
    owner = str(uuid4())
    lease_id = "maintenance" if kind == "priority" else kind
    with db.transaction():
        leases = db.query("SELECT * FROM leases WHERE id=$1", [lease_id])
        if leases and leases[0]["expires_at"] > store.now():
            return
        rows = db.query("SELECT status FROM jobs WHERE id=$1", [job_id])
        if rows and rows[0]["status"] in ("complete", "failed", "resumed", "skipped"):
            return
        db.query("INSERT INTO leases(id,owner,expires_at) VALUES($1,$2,$3) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at", [lease_id, owner, future(120)])
        db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,$2,'running','{}',$3) ON CONFLICT(id) DO UPDATE SET status='running',error=NULL", [job_id, kind, store.now()])
    row = db.query("SELECT checkpoint FROM jobs WHERE id=$1", [job_id])[0]
    job = JobContext(job_id, lease_id, owner, local_day, json.loads(row["checkpoint"]))
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(20):
            try:
                db.query("UPDATE leases SET expires_at=$1 WHERE id=$2 AND owner=$3", [future(120), lease_id, owner])
            except Exception:
                logger.warning("Job lease heartbeat failed.")
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        if kind == "discovery":
            discover(job)
        elif kind == "digest":
            digest()
        elif kind == "backup":
            backup_database()
        else:
            maintain(job, kind == "priority")
        with db.transaction():
            job.assert_lease()
            settings = store.get_settings()
            external = kind in ("discovery", "maintenance", "priority")
            paused = external and (settings.budgetPaused or (settings.discoveryPaused if kind == "discovery" else settings.maintenancePaused))
            db.query("UPDATE jobs SET status=$1,finished_at=$2 WHERE id=$3", ["paused" if paused else "complete", store.now(), job_id])
    except Exception as error:
        logger.exception("%s job failed", kind)
        message = str(error)[:500] if isinstance(error, RuntimeError) else f"{type(error).__name__}: backend job failed. Review server logs."
        still_owner = False
        with db.transaction():
            leases = db.query("SELECT owner FROM leases WHERE id=$1", [lease_id])
            if leases and leases[0]["owner"] == owner:
                still_owner = True
                db.query("UPDATE jobs SET status='failed',error=$1,finished_at=$2 WHERE id=$3", [message, store.now(), job_id])
                settings = store.get_settings()
                if kind not in settings.failedKinds:
                    settings.failedKinds.append(kind)
                store.write_settings(settings)
        if still_owner:
            discord.notify(f"{kind} job failed and is waiting for owner response. {message}\nReview and resume: {config.app_url}/admin?tab=operations")
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
    queued = db.query("SELECT * FROM jobs WHERE status IN ('queued','running','paused') ORDER BY started_at")
    for row in queued:
        kind = row["kind"]
        current = store.get_settings()
        external = kind in ("discovery", "maintenance", "priority")
        if kind not in JOB_KINDS or kind in current.failedKinds or (external and (current.budgetPaused or not config.github_token)) or (kind == "discovery" and current.discoveryPaused) or (kind in ("maintenance", "priority") and current.maintenancePaused):
            continue
        if row["status"] == "queued" and re.fullmatch(r"[a-z]+:\d{4}-\d{2}-\d{2}", row["id"]) and not row["id"].endswith(day):
            db.query("UPDATE jobs SET status='skipped',finished_at=$2 WHERE id=$1", [row["id"], store.now()])
            continue
        execute(row["id"], kind, day)
    db.query("DELETE FROM rate_limits WHERE expires_at<$1", [store.now()])
    db.query("DELETE FROM search_cache WHERE expires_at<$1", [store.now()])
    db.query("DELETE FROM jobs WHERE finished_at<$1 AND status IN ('complete','skipped')", [future(-30 * 86400)])
    db.query("DELETE FROM audit WHERE created_at<$1", [future(-365 * 86400)])
    db.query("DELETE FROM cost_entries WHERE created_at<$1 AND settled=1", [future(-365 * 86400)])
