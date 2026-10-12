"""Deterministic weekly community selections; no I/O on import."""
import copy
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from . import db, github, store
from .config import config

if TYPE_CHECKING:
    from .jobs import JobContext


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def week_context(week_start: str, timezone: str) -> dict:
    start = date.fromisoformat(week_start)
    if start.weekday() != 0 or start.isoformat() != week_start:
        raise ValueError("Community week must start on a Monday.")
    cutoff = datetime.combine(start + timedelta(days=7), time(), ZoneInfo(timezone))
    return {"weekStart": week_start, "cutoff": _timestamp(cutoff),
            "dueAt": _timestamp(cutoff + timedelta(minutes=5))}


def closed_week(now: datetime, timezone: str) -> dict | None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Community scheduling requires a timezone-aware clock.")
    local = now.astimezone(ZoneInfo(timezone))
    monday = local.date() - timedelta(days=local.weekday())
    due = datetime.combine(monday, time(0, 5), local.tzinfo)
    if local < due:
        monday -= timedelta(days=7)
    return week_context((monday - timedelta(days=7)).isoformat(), timezone)


def _ready(job: "JobContext") -> bool:
    job.assert_lease()
    settings = store.get_settings()
    return bool(config.github_token and not settings.discoveryPaused and not settings.budgetPaused
                and not settings.publicationPaused and "community" not in settings.failedKinds)


def _known(repo_id: str) -> bool:
    return bool(db.query("SELECT repo_id FROM apps WHERE repo_id=$1", [repo_id])
                or db.query("SELECT repo_id FROM candidates WHERE repo_id=$1", [repo_id]))


def _progress(job: "JobContext", community_requests) -> dict | None:
    with db.transaction():
        if not _ready(job):
            return None
        match = re.fullmatch(r"community:(\d{4}-\d{2}-\d{2})", job.id)
        if not match:
            raise RuntimeError("Community jobs require a canonical weekly ID.")
        week = week_context(match[1], store.get_settings().timezone)
        if store.now() < week["dueAt"]:
            return None
        if not job.saved:
            ranked = community_requests.rank_pending(cutoff=week["cutoff"], limit=30)
            progress = {"version": 1, "weekStart": week["weekStart"], "cutoff": week["cutoff"],
                        "ranked": ranked[:30], "index": 0, "promotedRepoIds": [], "skipped": []}
        else:
            progress = copy.deepcopy(job.saved)
        ranked, promoted, index = progress.get("ranked"), progress.get("promotedRepoIds"), progress.get("index")
        valid = (progress.get("version") == 1 and progress.get("weekStart") == match[1]
                 and isinstance(ranked, list) and len(ranked) <= 30
                 and isinstance(promoted, list) and len(promoted) <= 10
                 and type(index) is int and 0 <= index <= len(ranked)
                 and isinstance(progress.get("skipped"), list))
        if not valid:
            raise RuntimeError("Community checkpoint is invalid. Review before resuming.")
        ids = []
        for row in ranked:
            if (not isinstance(row, dict) or not isinstance(row.get("repoId"), str)
                    or not re.fullmatch(r"[1-9][0-9]*", row["repoId"])
                    or type(row.get("suggestionCount")) is not int or row["suggestionCount"] < 1):
                raise RuntimeError("Community ranking is invalid. Review before resuming.")
            github.repository_url(row.get("repoUrl", ""))
            ids.append(row["repoId"])
        if len(set(ids)) != len(ids) or len(set(promoted)) != len(promoted) or any(p not in ids[:index] for p in promoted):
            raise RuntimeError("Community checkpoint identities are invalid. Review before resuming.")
        # The stored UTC cutoff survives a later settings-timezone change.
        cutoff = datetime.fromisoformat(progress.get("cutoff", "").replace("Z", "+00:00"))
        if cutoff.utcoffset() != timedelta(0):
            raise RuntimeError("Community cutoff must be UTC.")
        if not job.saved:
            job.checkpoint(progress)
        return progress


def promote_weekly(job: "JobContext") -> bool:
    if not _ready(job):
        return False
    # Session 1 owns this module; scheduler/calendar imports work before integration.
    from . import community_requests
    progress = _progress(job, community_requests)
    if progress is None:
        return False
    while progress["index"] < len(progress["ranked"]) and len(progress["promotedRepoIds"]) < 10:
        row = progress["ranked"][progress["index"]]
        data, reason = None, None
        with db.transaction():
            if not _ready(job):
                return False
            if _known(row["repoId"]):
                reason = "already_reviewed"
        if reason is None:
            try:
                data = github.fetch_repository(row["repoUrl"])
            except github.MissingRepository:
                reason = "unavailable"
            except github.GithubError:
                raise RuntimeError("Community GitHub lookup failed. Resume this batch after checking provider availability.") from None
            if data is not None:
                if data.repoId != row["repoId"]:
                    reason = "identity_changed"
                elif data.archived:
                    reason = "archived"
        with db.transaction():
            if not _ready(job):
                return False
            if _known(row["repoId"]):
                reason = "already_reviewed"
            next_progress = copy.deepcopy(progress)
            if reason is None:
                assessment = {"source": "community-weekly", "weekStart": progress["weekStart"],
                              "cutoff": progress["cutoff"], "suggestionCount": row["suggestionCount"],
                              "jobId": job.id, "inAppModelCalled": False,
                              "evidence": {"sources": data.sources, "license": data.license, "archived": data.archived},
                              "uncertain": ["free-use", "type", "platforms"]}
                if not store.save_candidate(data, assessment):
                    raise RuntimeError("Community candidate changed while holding the writer lease.")
                community_requests.mark_review_queued(row["repoId"], at=store.now())
                next_progress["promotedRepoIds"].append(row["repoId"])
                store.audit("community.promoted", {"repoId": row["repoId"], "jobId": job.id,
                                                   "suggestionCount": row["suggestionCount"]})
            else:
                next_progress["skipped"].append({"repoId": row["repoId"], "reason": reason})
                store.audit("community.skipped", {"repoId": row["repoId"], "jobId": job.id, "reason": reason})
            next_progress["index"] += 1
            job.checkpoint(next_progress)
        progress = next_progress
    return True
