"""Community backlog and distinct browser counts, serialized with store writers."""
import re
from datetime import UTC, datetime
from fastapi import HTTPException
from . import db, store
from .models import InputError, Metadata


def _ready():
    try:
        db.query("SELECT s.repo_id,c.visitor_key FROM community_suggestions s LEFT JOIN community_contributions c ON c.repo_id=s.repo_id WHERE 1=0")
    except Exception:
        raise HTTPException(503, "Community requests require database migration 0003_community_requests; run the explicit backend migration command.") from None


def _timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Community timestamps require a timezone.")
    return parsed.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def repository_status(repo_id: str) -> dict:
    _ready()
    row = db.query("""
        SELECT EXISTS(SELECT 1 FROM apps WHERE repo_id=$1) AS listed,
            (SELECT status FROM candidates WHERE repo_id=$1) AS candidate,
            (SELECT state FROM community_suggestions WHERE repo_id=$1) AS state,
            (SELECT COUNT(*) FROM community_contributions WHERE repo_id=$1) AS total
    """, [repo_id])[0]
    if row["listed"]:
        return {"status": "already_listed", "suggestionCount": None}
    if row["candidate"] is not None:
        return {"status": "awaiting_review" if row["candidate"] == "pending" else "already_reviewed", "suggestionCount": None}
    if row["state"] == "queued":
        return {"status": "awaiting_review", "suggestionCount": None}
    return {"status": "suggested" if row["state"] else "available", "suggestionCount": int(row["total"])}


def record_suggestion(data: Metadata, visitor_key: str, *, at: str | None = None) -> dict:
    data = Metadata.model_validate(data.model_dump())
    if not re.fullmatch(r"[1-9][0-9]*", data.repoId):
        raise InputError("Repository identity must be a canonical positive numeric ID.")
    if not isinstance(visitor_key, str) or not 1 <= len(visitor_key) <= 200:
        raise ValueError("A browser storage key is required.")
    timestamp = _timestamp(at if at is not None else store.now())
    _ready()
    with db.transaction():
        status = repository_status(data.repoId)
        if status["status"] not in ("available", "suggested"):
            return {"ok": True, **status}
        db.query("""
            INSERT INTO community_suggestions(repo_id,repo_url,name,state,created_at,updated_at)
            VALUES($1,$2,$3,'pending',$4,$4)
            ON CONFLICT(repo_id) DO UPDATE SET repo_url=excluded.repo_url,name=excluded.name,
                updated_at=CASE WHEN $5 THEN excluded.updated_at ELSE community_suggestions.updated_at END
        """, [data.repoId, data.repoUrl, data.name, timestamp, not data.archived])
        inserted = db.query("""
            INSERT INTO community_contributions(repo_id,visitor_key,created_at) VALUES($1,$2,$3)
            ON CONFLICT(repo_id,visitor_key) DO NOTHING RETURNING repo_id
        """, [data.repoId, visitor_key, timestamp])
        count = db.query("SELECT COUNT(*) AS total FROM community_contributions WHERE repo_id=$1", [data.repoId])[0]["total"]
        return {"ok": True, "status": "recorded" if inserted else "already_suggested", "suggestionCount": int(count)}


def rank_pending(*, cutoff: str, limit: int = 30) -> list[dict]:
    if type(limit) is not int or limit < 0:
        raise ValueError("Ranking limit must be a nonnegative integer.")
    _ready()
    # Failed eligibility checks remain deferred until a newer verified,
    # nonarchived submission. Retained audit evidence supplies durable state
    # without discarding contributions or presenting a nonexistent review.
    repo_field = "a.data::jsonb ->> 'repoId'" if db.config.database_url else "json_extract(a.data,'$.repoId')"
    reason_field = "a.data::jsonb ->> 'reason'" if db.config.database_url else "json_extract(a.data,'$.reason')"
    rows = db.query(f"""
        SELECT s.repo_id,s.repo_url,s.name,COUNT(*) AS total,MIN(c.created_at) AS first_at
        FROM community_suggestions s JOIN community_contributions c ON c.repo_id=s.repo_id
        WHERE s.state='pending' AND c.created_at < $1
            AND NOT EXISTS(SELECT 1 FROM apps a WHERE a.repo_id=s.repo_id)
            AND NOT EXISTS(SELECT 1 FROM candidates d WHERE d.repo_id=s.repo_id)
            AND NOT EXISTS(SELECT 1 FROM audit a WHERE a.action='community.skipped'
                AND a.created_at >= s.updated_at AND {repo_field}=s.repo_id
                AND {reason_field} IN ('unavailable','archived','identity_changed'))
        GROUP BY s.repo_id,s.repo_url,s.name
        ORDER BY COUNT(*) DESC,MIN(c.created_at) ASC,LENGTH(s.repo_id) ASC,s.repo_id ASC LIMIT $2
    """, [_timestamp(cutoff), limit])
    return [dict(repoId=r["repo_id"], repoUrl=r["repo_url"], name=r["name"], suggestionCount=int(r["total"]),
                 firstSuggestedAt=r["first_at"]) for r in rows]


def mark_review_queued(repo_id: str, *, at: str) -> None:
    if db._connection.get() is None:
        raise RuntimeError("Marking a suggestion queued requires the caller's writer transaction.")
    _ready()
    db.query("UPDATE community_suggestions SET state='queued',updated_at=$2 WHERE repo_id=$1 AND state='pending'",
             [repo_id, _timestamp(at)])


def admin_suggestions() -> list[dict]:
    _ready()
    rows = db.query("""
        SELECT s.repo_id,s.repo_url,s.name,s.state,s.created_at,COUNT(c.visitor_key) AS total
        FROM community_suggestions s LEFT JOIN community_contributions c ON c.repo_id=s.repo_id
        GROUP BY s.repo_id,s.repo_url,s.name,s.state,s.created_at
        ORDER BY s.created_at DESC,LENGTH(s.repo_id),s.repo_id
    """)
    return [dict(repoId=r["repo_id"], repoUrl=r["repo_url"], name=r["name"], suggestionCount=int(r["total"]),
                 state=r["state"], createdAt=r["created_at"]) for r in rows]
