from uuid import uuid4
from . import db, store, github, discord
from .config import config
from .models import Metadata

def maintain(job, priority_only=False):
    apps = [a for a in store.list_apps(True) if not priority_only or a["priority"]]
    completed = set(job.saved.get("completed", []))
    for app in apps:
        if app["id"] in completed:
            continue
        settings = store.get_settings()
        if settings.maintenancePaused or settings.budgetPaused:
            return
        job.assert_lease()
        notice = None
        try:
            fresh = github.fetch_repository(app["repoUrl"])
            with db.transaction():
                job.assert_lease()
                rows = db.query("SELECT data FROM apps WHERE id=$1", [app["id"]])
                if not rows:
                    continue
                original = Metadata.model_validate_json(rows[0]["data"])
                identity_changed = fresh.repoId != original.repoId
                material = identity_changed or fresh.repoUrl != original.repoUrl or fresh.license != original.license
                proposals = db.query("SELECT data,status FROM proposals WHERE app_id=$1", [app["id"]])
                prior = Metadata.model_validate_json(proposals[0]["data"]) if proposals else None
                same = prior and all(getattr(prior, key) == getattr(fresh, key) for key in ("repoId", "repoUrl", "license"))
                if material and not same:
                    db.query("INSERT INTO proposals(id,app_id,revision,data,status,updated_at) VALUES($1,$2,1,$3,'pending',$4) ON CONFLICT(app_id) DO UPDATE SET data=excluded.data,revision=proposals.revision+1,status='pending',updated_at=excluded.updated_at", [str(uuid4()), app["id"], store.encode(fresh), store.now()])
                    notice = discord.queue(f"Repository identity, URL, or license change needs review for {app['name']}. Public source values are retained. {config.app_url}/admin?tab=changes")
                raw = original.model_dump()
                fields = ("lastChecked",) if identity_changed else ("version", "requirements", "stars", "archived", "lastActivity", "lastChecked", "condition")
                for field in fields:
                    if field not in original.overrides and (field != "version" or fresh.version):
                        raw[field] = getattr(fresh, field)
                data = Metadata.model_validate(raw)
                db.query("UPDATE apps SET data=$1,revision=revision+1,updated_at=$2 WHERE id=$3", [store.encode(data), store.now(), app["id"]])
                store.bump_revision()
                completed.add(app["id"])
                job.checkpoint({"completed": sorted(completed)})
        except github.MissingRepository:
            with db.transaction():
                job.assert_lease()
                rows = db.query("SELECT data FROM apps WHERE id=$1", [app["id"]])
                if not rows:
                    continue
                data = Metadata.model_validate_json(rows[0]["data"])
                first = data.condition != "availability-needs-review"
                data.condition = "availability-needs-review"
                db.query("UPDATE apps SET data=$1,revision=revision+1,updated_at=$2 WHERE id=$3", [store.encode(data), store.now(), app["id"]])
                store.bump_revision()
                if first:
                    notice = discord.queue(f"Repository unavailable: {app['name']}. Review its last approved link in the admin dashboard.")
                completed.add(app["id"])
                job.checkpoint({"completed": sorted(completed)})
        if notice:
            discord.deliver(notice)
