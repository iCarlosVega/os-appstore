"""Owner-bound review drafts; all domain writes use the store's global writer lock."""
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import TypedDict

from pydantic import ValidationError

from . import db, store
from .models import InputError, Metadata, TYPES

MAX_VERSION = 2147483647
MAX_TELEGRAM_ID = (1 << 52) - 1
COST_MODELS = ["Free", "Free with optional paid features"]
FIELDS = {"category": ("categories", "categories"), "type": ("type", "types"),
          "cost": ("costModel", "cost_models")}


class ReviewView(TypedDict):
    token: str
    repo_id: str
    candidate_revision: int
    draft_version: int
    status: str
    expires_at: str
    message_id: str | None
    app_slug: str | None
    data: dict
    assessment: dict
    options: dict
    confirmed: dict


def _integer(value, minimum, maximum, message):
    if type(value) is not int or not minimum <= value <= maximum:
        raise InputError(message)
    return value


def _identity(owner_user_id, chat_id):
    return tuple(str(_integer(value, 1, MAX_TELEGRAM_ID, "Use valid private owner and chat IDs."))
                 for value in (owner_user_id, chat_id))


def _token(token):
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{22}", token, re.ASCII):
        raise InputError("Review unavailable.")


def _bound_review(token, owner, chat):
    rows = db.query(
        "SELECT * FROM telegram_reviews WHERE token=$1 AND owner_user_id=$2 AND chat_id=$3",
        [token, owner, chat],
    )
    if not rows:
        raise InputError("Review unavailable.")
    return rows[0]


def _suggest_metadata(draft, options):
    """Use discovery's category when present; deterministic fallback needs no API call."""
    draft = dict(draft)
    if not draft.get("categories"):
        text = " ".join([draft.get("name", ""), draft.get("description", ""), *draft.get("tags", [])]).lower()
        terms = {
            "creative-tools": r"photoshop|image editor|photo|video|design|drawing|audio",
            "ai": r"\bai\b|agent|inference|pytorch|language model|decision engine",
            "gaming": r"\bgame\b|gaming",
            "privacy": r"privacy|encrypt|password|vpn",
            "communication": r"chat|messag|email|video call",
            "education": r"learn|education|math|guide|指南|阅读",
            "development": r"develop|plugin|framework|library|programming|\bapi\b",
            "productivity": r"notes|calendar|task|productivity",
        }
        allowed = {c["id"] for c in options["categories"]}
        category = next((key for key, pattern in terms.items() if key in allowed and re.search(pattern, text)), None)
        if category is None and "utilities" in allowed:
            category = "utilities"
        if category:
            draft["categories"] = [category]
    if draft.get("costModel") == "Needs review" and draft.get("license") in {
        "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0",
        "GPL-2.0", "GPL-3.0", "GPL-2.0-only", "GPL-3.0-only",
        "GPL-2.0-or-later", "GPL-3.0-or-later", "AGPL-3.0", "AGPL-3.0-only",
        "AGPL-3.0-or-later", "Unlicense", "CC0-1.0", "CC-BY-4.0",
    }:
        draft["costModel"] = "Free"
    return draft


def _view(row) -> ReviewView:
    return {
        "token": row["token"], "repo_id": row["repo_id"],
        "candidate_revision": row["candidate_revision"], "draft_version": row["draft_version"],
        "status": row["status"], "expires_at": row["expires_at"],
        "message_id": row["message_id"], "app_slug": row["app_slug"],
        "data": _suggest_metadata(json.loads(row["draft"]), json.loads(row["options"])), "assessment": json.loads(row["assessment"]),
        "options": json.loads(row["options"]), "confirmed": json.loads(row["confirmed"]),
    }


def _result(row, outcome, message):
    return {"review": _view(row), "outcome": outcome, "message": message}


def _refresh(row, timestamp):
    # Terminal results survive candidate changes and expiry for callback replay.
    if row["status"] != "open":
        return
    candidates = db.query("SELECT revision,status FROM candidates WHERE repo_id=$1", [row["repo_id"]])
    if (not candidates or candidates[0]["status"] != "pending"
            or candidates[0]["revision"] != row["candidate_revision"]):
        status = "stale"
    elif row["expires_at"] <= timestamp:
        status = "expired"
    else:
        return
    db.query("UPDATE telegram_reviews SET status=$1 WHERE token=$2", [status, row["token"]])
    row["status"] = status


def _unavailable(row):
    status = row["status"]
    if status in ("approved", "rejected"):
        return _result(row, "already_done", f"Review already {status}.")
    if status == "stale":
        return _result(row, "stale", "Candidate changed. Review its latest card.")
    if status == "expired":
        return _result(row, "expired", "Review expired. Request a fresh card with /pending.")
    return None


def prepare_reviews(*, owner_user_id: int, chat_id: int, limit: int = 5) -> list[ReviewView]:
    owner, chat = _identity(owner_user_id, chat_id)
    _integer(limit, 1, 5, "Choose a review limit from 1 to 5.")
    with db.transaction():
        timestamp = store.now()
        db.query("""
            UPDATE telegram_reviews SET status='stale'
            WHERE owner_user_id=$1 AND chat_id=$2 AND status='open'
              AND NOT EXISTS (SELECT 1 FROM candidates c WHERE c.repo_id=telegram_reviews.repo_id
                  AND c.revision=telegram_reviews.candidate_revision AND c.status='pending')
        """, [owner, chat])
        db.query("""
            UPDATE telegram_reviews SET status='expired'
            WHERE owner_user_id=$1 AND chat_id=$2 AND status='open' AND expires_at<=$3
        """, [owner, chat, timestamp])
        candidates = db.query("""
            SELECT c.*, r.token AS review_token FROM candidates c
            LEFT JOIN telegram_reviews r ON r.repo_id=c.repo_id AND r.candidate_revision=c.revision
                AND r.owner_user_id=$1 AND r.chat_id=$2 AND r.status='open'
            WHERE c.status='pending' AND (r.token IS NULL OR r.message_id IS NULL)
            ORDER BY c.updated_at ASC, c.repo_id ASC LIMIT $3
        """, [owner, chat, limit])
        reviews = []
        for candidate in candidates:
            token = candidate["review_token"]
            if token is None:
                token = secrets.token_urlsafe(16)
                options = {
                    "categories": [{"id": c["id"], "name": c["name"]} for c in sorted(
                        store.categories(), key=lambda c: (c["name"].lower(), c["id"]))],
                    "types": list(TYPES), "cost_models": COST_MODELS,
                }
                confirmed = {key: False for key in ("category", "type", "cost", "safe")}
                assessment = json.loads(candidate.get("assessment") or "{}")
                if assessment is None:
                    assessment = {}
                expires = (datetime.fromisoformat(timestamp) + timedelta(days=7)).isoformat(
                    timespec="milliseconds").replace("+00:00", "Z")
                db.query("""
                    INSERT INTO telegram_reviews(token,repo_id,candidate_revision,draft_version,
                        owner_user_id,chat_id,status,snapshot,assessment,draft,options,confirmed,
                        created_at,expires_at,message_id,app_slug)
                    VALUES($1,$2,$3,1,$4,$5,'open',$6,$7,$6,$8,$9,$10,$11,NULL,NULL)
                """, [token, candidate["repo_id"], candidate["revision"], owner, chat, candidate["data"],
                      store.encode(assessment), store.encode(options), store.encode(confirmed), timestamp, expires])
            reviews.append(_view(_bound_review(token, owner, chat)))
        return reviews


def get_review(token: str, *, owner_user_id: int, chat_id: int) -> ReviewView:
    _token(token)
    owner, chat = _identity(owner_user_id, chat_id)
    with db.transaction():
        row = _bound_review(token, owner, chat)
        _refresh(row, store.now())
        return _view(row)


def mark_delivered(token: str, message_id: int, *, owner_user_id: int, chat_id: int) -> None:
    _token(token)
    owner, chat = _identity(owner_user_id, chat_id)
    _integer(message_id, 1, MAX_TELEGRAM_ID, "Use a valid message ID.")
    with db.transaction():
        row = _bound_review(token, owner, chat)
        _refresh(row, store.now())
        if row["status"] == "open":
            db.query("UPDATE telegram_reviews SET message_id=$1 WHERE token=$2", [str(message_id), token])


def reset_delivery(token: str, expected_message_id: int, *, owner_user_id: int, chat_id: int) -> None:
    _token(token)
    owner, chat = _identity(owner_user_id, chat_id)
    _integer(expected_message_id, 1, MAX_TELEGRAM_ID, "Use a valid message ID.")
    with db.transaction():
        rows = db.query(
            "SELECT * FROM telegram_reviews WHERE token=$1 AND owner_user_id=$2 AND chat_id=$3",
            [token, owner, chat],
        )
        if not rows:
            return
        row = rows[0]
        if row["status"] != "open" or row["message_id"] != str(expected_message_id):
            return
        _refresh(row, store.now())
        if row["status"] == "open":
            db.query("""UPDATE telegram_reviews SET message_id=NULL
                        WHERE token=$1 AND status='open' AND message_id=$2""", [token, str(expected_message_id)])


def _action(expected_version, action, value):
    _integer(expected_version, 1, MAX_VERSION, "Use a valid review version.")
    if not isinstance(action, str) or action not in (*FIELDS, "safe", "approve", "accept", "more", "reject"):
        raise InputError("Unknown review action.")
    if action in FIELDS:
        if (not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,9}", value, re.ASCII)
                or int(value) > MAX_VERSION):
            raise InputError("Choose a valid review option.")
        return int(value)
    if (action == "safe" and value != "yes") or (action in ("approve", "accept", "more", "reject") and value is not None):
        raise InputError("Invalid review action value.")
    return None


def _select(row, action, index):
    if row["draft_version"] == MAX_VERSION:
        return _result(row, "blocked", "Review version limit reached. Request a fresh card after expiry.")
    draft = json.loads(row["draft"])
    if action == "safe":
        if draft.get("nsfw") or json.loads(row["snapshot"]).get("nsfw"):
            return _result(row, "blocked", "Known NSFW candidates cannot be approved through Telegram.")
    else:
        field, option_key = FIELDS[action]
        choice = json.loads(row["options"])[option_key][index]
        choice = [choice["id"]] if action == "category" else choice
        draft[field] = choice
        snapshot = json.loads(row["snapshot"])
        changed = [key for key, _ in FIELDS.values() if draft.get(key) != snapshot.get(key)]
        draft["overrides"] = list(dict.fromkeys([*snapshot.get("overrides", []), *changed]))
    confirmed = json.loads(row["confirmed"])
    confirmed[action] = True
    row.update(draft=store.encode(draft), confirmed=store.encode(confirmed),
               draft_version=row["draft_version"] + 1)
    db.query("UPDATE telegram_reviews SET draft=$1,confirmed=$2,draft_version=$3 WHERE token=$4",
             [row["draft"], row["confirmed"], row["draft_version"], row["token"]])
    return _result(row, "updated", "Selection confirmed. Review the current choices before publishing.")


def apply_action(token: str, expected_version: int, action: str, value: str | None = None,
                 *, owner_user_id: int, chat_id: int) -> dict:
    _token(token)
    owner, chat = _identity(owner_user_id, chat_id)
    index = _action(expected_version, action, value)
    with db.transaction():
        row = _bound_review(token, owner, chat)
        if action in FIELDS and index >= len(json.loads(row["options"])[FIELDS[action][1]]):
            raise InputError("Choose a valid review option.")
        _refresh(row, store.now())
        unavailable = _unavailable(row)
        if unavailable is not None:
            return unavailable
        if expected_version != row["draft_version"]:
            return _result(row, "stale", "This button is outdated. Review the current choices.")
        if action in (*FIELDS, "safe"):
            return _select(row, action, index)
        if action == "more":
            return _result(row, "details", "")
        if action in ("approve", "accept"):
            confirmed = json.loads(row["confirmed"])
            if action == "approve" and not all(confirmed.get(key) is True for key in ("category", "type", "cost", "safe")):
                return _result(row, "blocked", "Explicitly confirm category, software type, cost and safe content first.")
            if json.loads(row["snapshot"]).get("nsfw"):
                return _result(row, "blocked", "Known NSFW candidates cannot be approved through Telegram.")
            try:
                draft = (_suggest_metadata(json.loads(row["draft"]), json.loads(row["options"]))
                         if action == "accept" else json.loads(row["draft"]))
                data = Metadata.model_validate(draft)
            except ValidationError:
                return _result(row, "blocked", "Listing metadata is invalid. Review the candidate in web administration.")
            if data.repoId != row["repo_id"]:
                return _result(row, "blocked", "Candidate repository identity changed.")
            try:
                store.validate_publication(data)
            except InputError as error:
                return _result(row, "blocked", str(error))
            if store.get_settings().publicationPaused:
                return _result(row, "blocked", "Publication is paused.")
            # Do not catch store/audit failures here: the outer transaction must roll back.
            if action == "accept":
                row["draft"] = store.encode(data)
                db.query("UPDATE telegram_reviews SET draft=$1 WHERE token=$2", [row["draft"], token])
            row["app_slug"] = store.approve_candidate(row["repo_id"], row["candidate_revision"], data)
            status, message = "approved", "App approved and published."
        else:
            store.reject_candidate(row["repo_id"], row["candidate_revision"])
            status, message = "rejected", "Candidate rejected."
        row["status"] = status
        db.query("UPDATE telegram_reviews SET status=$1,app_slug=$2 WHERE token=$3",
                 [status, row["app_slug"], token])
        store.audit(f"telegram.review.{status}", {
            "ownerUserId": owner, "chatId": chat, "repoId": row["repo_id"],
            "candidateRevision": row["candidate_revision"], "draftVersion": row["draft_version"],
            "token": token, "outcome": status,
        })
        return _result(row, status, message)


def _poller_key(poller_key):
    if not isinstance(poller_key, str) or not re.fullmatch(
            r"telegram:[1-9][0-9]{0,15}:[1-9][0-9]{0,15}:[1-9][0-9]{0,15}", poller_key, re.ASCII):
        raise InputError("Use a valid bot, owner and chat polling scope.")
    if any(int(part) > MAX_TELEGRAM_ID for part in poller_key.split(":")[1:]):
        raise InputError("Use a valid bot, owner and chat polling scope.")


def _offset(poller_key):
    rows = db.query("SELECT data FROM telegram_state WHERE id=$1", [poller_key])
    if not rows:
        return 0
    try:
        offset = json.loads(rows[0]["data"])["offset"]
        return _integer(offset, 0, MAX_TELEGRAM_ID, "Polling state is invalid.")
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("Telegram polling state is invalid. Review it before restarting the worker.") from None


def get_offset(poller_key: str) -> int:
    _poller_key(poller_key)
    return _offset(poller_key)


def advance_offset(poller_key: str, next_update_id: int) -> None:
    _poller_key(poller_key)
    _integer(next_update_id, 0, MAX_TELEGRAM_ID, "Use a valid next update ID.")
    with db.transaction():
        if next_update_id > _offset(poller_key):
            db.query("""INSERT INTO telegram_state(id,data) VALUES($1,$2)
                        ON CONFLICT(id) DO UPDATE SET data=excluded.data""",
                     [poller_key, store.encode({"offset": next_update_id})])
