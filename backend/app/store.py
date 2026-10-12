import json
from datetime import UTC, datetime
from uuid import uuid4
from . import db
from .config import config
from .models import CATEGORY_NAMES, InputError, Metadata, Settings, slugify

def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def encode(value) -> str:
    return json.dumps(value.model_dump() if hasattr(value, "model_dump") else value, separators=(",", ":"), ensure_ascii=False)

def initialize(migration=False):
    if migration or not config.database_url:
        db.migrate()
    with db.transaction():
        db.query("INSERT INTO settings(id,data) VALUES(1,$1) ON CONFLICT(id) DO NOTHING", [encode(Settings())])
        for name in CATEGORY_NAMES:
            db.query("INSERT INTO categories(id,name,parent_id) VALUES($1,$2,NULL) ON CONFLICT(id) DO NOTHING", [slugify(name), name])

def get_settings() -> Settings:
    rows = db.query("SELECT data FROM settings WHERE id=1")
    if not rows:
        raise RuntimeError("Initialize the backend database before serving requests.")
    return Settings.model_validate_json(rows[0]["data"])

def write_settings(settings: Settings):
    value = Settings.model_validate(settings.model_dump())
    db.query("UPDATE settings SET data=$1 WHERE id=1", [encode(value)])

def bump_revision():
    settings = get_settings()
    settings.revision += 1
    write_settings(settings)

def audit(action: str, data):
    db.query("INSERT INTO audit(id,action,data,created_at) VALUES($1,$2,$3,$4)", [str(uuid4()), action, encode(data), now()])

def categories():
    return db.query("SELECT * FROM categories ORDER BY name")

def validate_categories(ids: list[str]):
    allowed = {c["id"] for c in categories()}
    if any(value not in allowed for value in ids):
        raise InputError("Choose an existing category.")

def to_app(row: dict):
    return {**Metadata.model_validate_json(row["data"]).model_dump(), "id": row["id"], "slug": row["slug"], "revision": row["revision"], "published": row["published"] == 1, "clicks": int(row.get("clicks") or 0)}

def list_apps(include_private=False):
    private = "" if include_private else "WHERE a.published=1"
    rows = db.query(f"SELECT a.*, COALESCE((SELECT SUM(total) FROM clicks WHERE app_id=a.id),0) AS clicks FROM apps a {private} ORDER BY a.updated_at DESC")
    return [to_app(row) for row in rows]

def find_app(app_id: str):
    rows = db.query("SELECT a.*, COALESCE((SELECT SUM(total) FROM clicks WHERE app_id=a.id),0) AS clicks FROM apps a WHERE id=$1", [app_id])
    return to_app(rows[0]) if rows else None

def get_app(slug: str):
    rows = db.query("SELECT a.*, COALESCE((SELECT SUM(total) FROM clicks WHERE app_id=a.id),0) AS clicks FROM apps a WHERE slug=$1 AND published=1", [slug])
    if rows:
        return to_app(rows[0])
    alias = db.query("SELECT a.slug FROM slug_aliases s JOIN apps a ON a.id=s.app_id WHERE s.slug=$1 AND a.published=1", [slug])
    return {"redirect": alias[0]["slug"]} if alias else None

def candidates():
    return [{"repoId": r["repo_id"], "revision": r["revision"], "status": r["status"], "data": Metadata.model_validate_json(r["data"]).model_dump(), "assessment": json.loads(r["assessment"]), "updatedAt": r["updated_at"]} for r in db.query("SELECT * FROM candidates ORDER BY updated_at DESC")]

def save_candidate(data: Metadata, assessment: dict) -> bool:
    data = Metadata.model_validate(data.model_dump())
    with db.transaction():
        if db.query("SELECT id FROM apps WHERE repo_id=$1", [data.repoId]):
            return False
        existing = db.query("SELECT status FROM candidates WHERE repo_id=$1", [data.repoId])
        status = existing[0]["status"] if existing else "pending"
        db.query("INSERT INTO candidates(repo_id,revision,status,data,assessment,updated_at) VALUES($1,1,$2,$3,$4,$5) ON CONFLICT(repo_id) DO UPDATE SET revision=candidates.revision+1,data=excluded.data,assessment=excluded.assessment,updated_at=excluded.updated_at", [data.repoId, status, encode(data), encode(assessment), now()])
        return not existing

def validate_publication(data: Metadata):
    if data.nsfw or data.costModel == "Needs review" or not data.categories:
        raise InputError("Confirm free-use eligibility, a category, and non-NSFW content before publishing.")
    validate_categories(data.categories)

def approve_candidate(repo_id: str, revision: int, data: Metadata):
    with db.transaction():
        if get_settings().publicationPaused:
            raise InputError("Publication is paused.")
        rows = db.query("SELECT * FROM candidates WHERE repo_id=$1", [repo_id])
        if not rows or rows[0]["status"] != "pending" or rows[0]["revision"] != revision:
            raise InputError("Candidate changed. Reload and review its latest revision.")
        if data.repoId != repo_id:
            raise InputError("Candidate repository identity changed.")
        validate_publication(data)
        app_id = str(uuid4())
        slug = f"{slugify(data.name) or 'app'}-{repo_id}"
        db.query("INSERT INTO apps(id,repo_id,slug,published,revision,data,updated_at) VALUES($1,$2,$3,1,1,$4,$5)", [app_id, repo_id, slug, encode(data), now()])
        db.query("UPDATE candidates SET status='approved',revision=revision+1 WHERE repo_id=$1", [repo_id])
        bump_revision()
        audit("candidate.approved", {"repoId": repo_id, "revision": revision, "id": app_id})
        return slug

def reject_candidate(repo_id: str, revision: int, reopen=False):
    with db.transaction():
        rows = db.query("UPDATE candidates SET status=$1,revision=revision+1 WHERE repo_id=$2 AND revision=$3 AND status IN ('pending','rejected') RETURNING repo_id", ["pending" if reopen else "rejected", repo_id, revision])
        if not rows:
            raise InputError("Candidate changed. Reload before deciding.")
        audit("candidate.reopened" if reopen else "candidate.rejected", {"repoId": repo_id, "revision": revision})

def edit_app(app_id: str, revision: int, data: Metadata, published: bool | None = None):
    with db.transaction():
        original = find_app(app_id)
        if not original or original["revision"] != revision:
            raise InputError("Listing changed. Reload before saving.")
        public = original["published"] if published is None else published
        if get_settings().publicationPaused and public and not original["published"]:
            raise InputError("Publication is paused.")
        if public:
            validate_publication(data)
        else:
            validate_categories(data.categories)
        db.query("UPDATE apps SET data=$1,published=$2,revision=revision+1,updated_at=$3,repo_id=$5 WHERE id=$4", [encode(data), int(public), now(), app_id, data.repoId])
        bump_revision()
        audit("app.updated", {"id": app_id, "revision": revision})
