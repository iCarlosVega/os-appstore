import json
import re
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4
from . import db, store, budget, discord
from .models import InputError, Metadata, Settings, JOB_KINDS, repository_url, slugify

class Form:
    def __init__(self, fields):
        self.fields = fields
    def get(self, name):
        values = self.fields.get(name, [])
        return values[0].strip() if values else ""
    def all(self, name):
        return self.fields.get(name, [])
    def flag(self, name):
        return self.get(name) == "on"
    def revision(self):
        try:
            value = int(self.get("revision"))
            if value < 1:
                raise ValueError()
            return value
        except ValueError:
            raise InputError("Reload and review the latest revision.") from None

def dollars(value: str, nullable=False):
    if not value and nullable:
        return None
    try:
        amount = Decimal(value or "0")
        if not amount.is_finite() or not 0 <= amount <= 100000:
            raise ValueError()
        return int((amount * 1000000).to_integral_value())
    except (InvalidOperation, ValueError):
        raise InputError("Enter a valid nonnegative amount in USD.") from None

def edits(form: Form, original: Metadata) -> Metadata:
    if not form.flag("confirmedSafeContent"):
        raise InputError("Confirm the listing contains no NSFW content.")
    raw = original.model_dump()
    for key in ("name", "creator", "creatorUrl", "description", "license", "version", "requirements", "setup", "type", "costModel"):
        raw[key] = form.get(key)
    for key in ("categories", "platforms", "architectures"):
        raw[key] = form.all(key)
    for key in ("tags", "aliases", "alternatives"):
        raw[key] = [part.strip() for part in form.get(key).split(",") if part.strip()]
    raw["attributes"] = {key: True if form.get(key) == "yes" else False if form.get(key) == "no" else None for key in ("offline", "noAccount", "accessible", "lightweight")}
    raw["links"] = {key: form.get(f"link:{key}") for key in ("Website", "Documentation", "Support", "Donation", "Issues", "Additional source") if form.get(f"link:{key}")}
    raw.update(priority=form.flag("priority"), downloadsEnabled=form.flag("downloadsEnabled"), nsfw=False)
    data = Metadata.model_validate(raw)
    previous = original.model_dump()
    changed = [key for key, value in data.model_dump().items() if key not in ("overrides", "priority", "downloadsEnabled") and value != previous[key]]
    data.overrides = list(dict.fromkeys([*original.overrides, *changed]))
    if form.flag("releaseOverrides"):
        data.overrides = [key for key in data.overrides if key not in ("version", "requirements", "condition")]
    return data

def dashboard():
    return {
        "settings": store.get_settings().model_dump(), "apps": store.list_apps(True), "candidates": store.candidates(),
        "categories": store.categories(), "usage": budget.usage(),
        "proposals": db.query("SELECT * FROM proposals WHERE status='pending' ORDER BY updated_at DESC"),
        "requests": db.query("SELECT * FROM app_requests WHERE status='pending' ORDER BY created_at DESC"),
        "jobs": db.query("SELECT * FROM jobs ORDER BY started_at DESC LIMIT 50"),
        "notifications": db.query("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 30"),
        "costEntries": db.query("SELECT * FROM cost_entries ORDER BY created_at DESC LIMIT 50"),
    }

def action(operation: str, fields: dict):
    form = Form(fields)
    message = "Saved."
    if operation == "approve":
        with db.transaction():
            rows = db.query("SELECT data FROM candidates WHERE repo_id=$1", [form.get("repoId")])
            if not rows:
                raise InputError("Candidate unavailable.")
            data = edits(form, Metadata.model_validate_json(rows[0]["data"]))
            store.approve_candidate(form.get("repoId"), form.revision(), data)
        message = "App approved and published."
    elif operation in ("reject", "reopen"):
        store.reject_candidate(form.get("repoId"), form.revision(), operation == "reopen")
        message = "Candidate rejected." if operation == "reject" else "Candidate reopened."
    elif operation == "edit":
        with db.transaction():
            app = store.find_app(form.get("id"))
            if not app:
                raise InputError("Listing unavailable.")
            store.edit_app(app["id"], form.revision(), edits(form, Metadata.model_validate(app)), form.flag("published"))
    elif operation == "category":
        name = form.get("name")
        category_id = form.get("id") or slugify(name)
        if not 2 <= len(name) <= 80 or not re.fullmatch("[a-z0-9-]+", category_id):
            raise InputError("Choose a category name containing letters or numbers.")
        parent = form.get("parent") or None
        with db.transaction():
            cats = {c["id"]: c for c in store.categories()}
            if parent and parent not in cats:
                raise InputError("Parent category unavailable.")
            ancestor, visited = parent, set()
            while ancestor:
                if ancestor == category_id or ancestor in visited:
                    raise InputError("A category cannot contain itself.")
                visited.add(ancestor)
                ancestor = cats[ancestor]["parent_id"]
            db.query("INSERT INTO categories(id,name,parent_id) VALUES($1,$2,$3) ON CONFLICT(id) DO UPDATE SET name=excluded.name,parent_id=excluded.parent_id", [category_id, name, parent])
            store.bump_revision()
            store.audit("category.saved", {"id": category_id, "name": name, "parent": parent})
    elif operation == "settings":
        with db.transaction():
            raw = store.get_settings().model_dump()
            for key in ("timezone", "discoveryTime", "maintenanceTime", "priorityTime", "digestTime", "backupTime", "donationUrl"):
                raw[key] = form.get(key)
            for key in ("discoveryPaused", "maintenancePaused", "publicationPaused", "downloadsPaused", "aiPaused", "budgetPaused"):
                raw[key] = form.flag(key)
            raw.update(dailyCandidates=form.get("dailyCandidates"), repositoryLimit=form.get("repositoryLimit"), seeds=[repository_url(line.strip()) for line in form.get("seeds").splitlines() if line.strip()], revision=raw["revision"] + 1)
            store.write_settings(Settings.model_validate(raw))
            store.audit("settings.updated", {})
        budget.enforce()
    elif operation == "costs":
        with db.transaction():
            raw = store.get_settings().model_dump()
            raw.update(budgetMicros=dollars(form.get("budget")), hostingMicros=dollars(form.get("hosting"), True), hostingActualMicros=dollars(form.get("hostingActual")), hostingActualPeriod=budget.period_now(), jevMicrosPerMillion=dollars(form.get("jevRate"), True), revision=raw["revision"] + 1)
            store.write_settings(Settings.model_validate(raw))
            store.audit("costs.configured", {})
        budget.enforce()
    elif operation == "reconcile":
        cost_id = str(UUID(form.get("id")))
        if not db.query("SELECT id FROM cost_entries WHERE id=$1", [cost_id]):
            raise InputError("Cost entry unavailable.")
        budget.settle(cost_id, dollars(form.get("actual")))
        store.audit("costs.reconciled", {"id": cost_id})
    elif operation == "request":
        with db.transaction():
            rows = db.query("SELECT * FROM app_requests WHERE id=$1 AND status='pending'", [form.get("id")])
            if not rows:
                raise InputError("Request already resolved.")
            row = rows[0]
            if form.get("decision") == "seed":
                if not row["repo_url"]:
                    raise InputError("Request has no repository URL.")
                settings = store.get_settings()
                settings.seeds = list(dict.fromkeys([*settings.seeds, repository_url(row["repo_url"])]))
                store.write_settings(settings)
            db.query("UPDATE app_requests SET status='resolved' WHERE id=$1", [row["id"]])
            store.audit("request.resolved", {"id": row["id"]})
    elif operation == "notification":
        discord.deliver(str(UUID(form.get("id"))))
    elif operation == "job":
        kind = form.get("kind")
        if kind not in JOB_KINDS:
            raise InputError("Unknown job type.")
        with db.transaction():
            settings = store.get_settings()
            settings.failedKinds = [k for k in settings.failedKinds if k != kind]
            store.write_settings(settings)
            previous_id = form.get("id")
            rows = db.query("SELECT checkpoint,kind FROM jobs WHERE id=$1 AND status='failed'", [previous_id]) if previous_id else []
            if previous_id and (not rows or rows[0]["kind"] != kind):
                raise InputError("Failed run is no longer available.")
            db.query("INSERT INTO jobs(id,kind,status,checkpoint,started_at) VALUES($1,$2,'queued',$3,$4)", [f"{kind}:manual:{uuid4()}", kind, rows[0]["checkpoint"] if rows else "{}", store.now()])
            if previous_id:
                db.query("UPDATE jobs SET status='resumed' WHERE id=$1", [previous_id])
            store.audit("job.queued", {"kind": kind, "previousId": previous_id})
        message = "Job queued. The worker will run it when its pause controls allow."
    elif operation == "proposal":
        decision = form.get("decision")
        if decision not in ("approve", "reject"):
            raise InputError("Choose approve or keep current source.")
        with db.transaction():
            rows = db.query("SELECT * FROM proposals WHERE id=$1 AND status='pending'", [form.get("id")])
            if not rows or rows[0]["revision"] != form.revision():
                raise InputError("Change proposal updated. Reload before deciding.")
            proposal = rows[0]
            if decision == "approve":
                app = store.find_app(proposal["app_id"])
                if not app:
                    raise InputError("App unavailable.")
                fresh = Metadata.model_validate_json(proposal["data"]).model_dump()
                raw = {**app, **{key: fresh[key] for key in ("repoId", "repoUrl", "license", "creator", "creatorUrl", "sources")}}
                store.edit_app(app["id"], app["revision"], Metadata.model_validate(raw))
            db.query("UPDATE proposals SET status=$1 WHERE id=$2", ["approved" if decision == "approve" else "rejected", proposal["id"]])
            store.audit("proposal.decided", {"id": proposal["id"], "decision": decision})
    else:
        raise InputError("Unknown action.")
    return {"message": message}
