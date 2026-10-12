from uuid import uuid4
from . import db, store, github, discord
from .config import config
from .models import Metadata

def maintain(job, priority_only=False):
    completed = set(job.saved.get("completed", []))
    limit = store.get_settings().repositoryLimit
    apps = [a for a in store.list_apps(True) if (not priority_only or a["priority"]) and a["id"] not in completed]
    # list_apps orders by update time; rotate even unavailable sources fairly.
    apps.reverse()
    apps = apps[:max(0, limit - len(completed))]
    for app in apps:
        settings = store.get_settings()
        if settings.maintenancePaused or settings.budgetPaused:
            return False
        job.assert_lease()
        notice = None
        try:
            fresh = github.fetch_repository(app["repoUrl"])
            with db.transaction():
                job.assert_lease()
                settings = store.get_settings()
                if settings.maintenancePaused or settings.budgetPaused:
                    return False
                rows = db.query("SELECT data FROM apps WHERE id=$1", [app["id"]])
                if not rows:
                    continue
                original = Metadata.model_validate_json(rows[0]["data"])
                if (original.repoId, original.repoUrl) != (app["repoId"], app["repoUrl"]):
                    continue
                identity_changed = fresh.repoId != original.repoId
                # Adapter defaults carry no evidence of a cost/category change.
                proposed = Metadata.model_validate({**fresh.model_dump(), "costModel": original.costModel if fresh.costModel == "Needs review" else fresh.costModel, "categories": fresh.categories or original.categories})
                material_fields = ("repoId", "repoUrl", "license", "costModel")
                material = any(getattr(proposed, key) != getattr(original, key) for key in material_fields) or set(proposed.categories) != set(original.categories)
                proposals = db.query("SELECT data,status FROM proposals WHERE app_id=$1", [app["id"]])
                prior = Metadata.model_validate_json(proposals[0]["data"]) if proposals else None
                same = prior and all(getattr(prior, key) == getattr(proposed, key) for key in material_fields) and set(prior.categories) == set(proposed.categories)
                if material and not same:
                    db.query("INSERT INTO proposals(id,app_id,revision,data,status,updated_at) VALUES($1,$2,1,$3,'pending',$4) ON CONFLICT(app_id) DO UPDATE SET data=excluded.data,revision=proposals.revision+1,status='pending',updated_at=excluded.updated_at", [str(uuid4()), app["id"], store.encode(proposed), store.now()])
                    notice = discord.queue(f"Repository identity, URL, license, cost model, or category change needs review for {original.name}. Public source values are retained. {config.app_url}/admin?tab=changes")
                raw = original.model_dump()
                fields = ("lastChecked",) if identity_changed else ("version", "requirements", "stars", "archived", "lastActivity", "lastChecked", "condition")
                for field in fields:
                    if field not in original.overrides and (field not in ("version", "requirements") or getattr(fresh, field)):
                        raw[field] = getattr(fresh, field)
                data = Metadata.model_validate(raw)
                db.query("UPDATE apps SET data=$1,revision=revision+1,updated_at=$2 WHERE id=$3", [store.encode(data), store.now(), app["id"]])
                store.bump_revision()
                if not identity_changed:
                    db.query("INSERT INTO star_snapshots(repo_id,observed_at,stars) VALUES($1,$2,$3) ON CONFLICT(repo_id,observed_at) DO NOTHING", [fresh.repoId, fresh.lastChecked or store.now(), fresh.stars])
                completed.add(app["id"])
                job.checkpoint({"completed": sorted(completed)})
        except github.MissingRepository:
            with db.transaction():
                job.assert_lease()
                settings = store.get_settings()
                if settings.maintenancePaused or settings.budgetPaused:
                    return False
                rows = db.query("SELECT data FROM apps WHERE id=$1", [app["id"]])
                if not rows:
                    continue
                data = Metadata.model_validate_json(rows[0]["data"])
                if (data.repoId, data.repoUrl) != (app["repoId"], app["repoUrl"]):
                    continue
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
