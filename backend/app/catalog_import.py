"""Explicit, insert-only public catalog snapshots for the isolated local database."""

import argparse
import json
import os
import re
import sys
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from . import db, store
from .config import config
from .models import Metadata

DEFAULT_SOURCE = "https://os-appstore.vercel.app"
MAX_BYTES = 5 * 1024 * 1024
MAX_RECORDS = 1000


def _guard_destination() -> None:
    message = (
        "Catalog import requires STORE_LOCAL=1, APP_ENV=development and a PostgreSQL "
        "URL with literal loopback host (127.0.0.1 or ::1), port 55432 and database "
        "os_appstore_development, without query options or libpq routing overrides. "
        "Use the dedicated local runtime environment."
    )
    try:
        url = urlsplit(config.database_url)
        valid = (
            os.getenv("STORE_LOCAL") == "1"
            and os.getenv("APP_ENV") == "development"
            and not config.production
            and url.scheme in ("postgres", "postgresql")
            and url.hostname in ("127.0.0.1", "::1")
            and url.port == 55432
            and url.path == "/os_appstore_development"
            and "?" not in config.database_url
            and "#" not in config.database_url
            and not any(c.isspace() or ord(c) < 32 for c in config.database_url)
            and not any(os.getenv(key) for key in (
                "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGSERVICE",
                "PGSERVICEFILE", "PGSYSCONFDIR", "PGOPTIONS",
                "PGLOADBALANCEHOSTS", "PGTARGETSESSIONATTRS",
            ))
        )
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError(message)


def _source_origin(value: str) -> str:
    try:
        url = urlsplit(value)
        if (
            url.scheme != "https" or not url.hostname
            or url.username is not None or url.password is not None
            or url.path not in ("", "/") or "?" in value or "#" in value
            or "\\" in value or any(c.isspace() or ord(c) < 32 for c in value)
        ):
            raise ValueError()
        _ = url.port
        # Validate with the HTTP adapter too, before even checking the local schema.
        httpx.URL(value)
    except (ValueError, TypeError, httpx.InvalidURL):
        raise RuntimeError("Source must be an HTTPS origin without credentials, path, query or fragment.") from None
    return value.rstrip("/")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _fetch(origin: str, path: str) -> list:
    try:
        # Separate clients prevent source cookies carrying across the two public GETs.
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", origin + path, headers={
                "Accept": "application/json", "Accept-Encoding": "identity",
            }) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"Public {path} returned HTTP {response.status_code}; retry when the source is available.")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise RuntimeError(f"Public {path} must return an uncompressed snapshot; retry with a compatible source.")
                content = bytearray()
                for chunk in response.iter_raw(chunk_size=65536):
                    if len(content) + len(chunk) > MAX_BYTES:
                        raise RuntimeError(f"Public {path} exceeds the 5 MiB snapshot limit.")
                    content.extend(chunk)
        records = json.loads(content, object_pairs_hook=_unique_object)
    except httpx.HTTPError:
        raise RuntimeError(f"Could not read public {path}; check the HTTPS source and retry.") from None
    except (ValueError, RecursionError):
        raise RuntimeError(f"Public {path} contains invalid JSON; retry the snapshot later.") from None
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise RuntimeError(f"Public {path} must be an array of at most 1,000 records.")
    return records


class _Category(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=80)
    parent_id: str | None = Field(max_length=80)


def _snapshot(apps: list, categories: list) -> tuple[list[dict], list[dict]]:
    try:
        category_map = {}
        for raw in categories:
            category = _Category.model_validate(raw).model_dump()
            if category["id"] in category_map or category["name"] != category["name"].strip():
                raise ValueError()
            category_map[category["id"]] = category
        if any(c["parent_id"] is not None and c["parent_id"] not in category_map for c in category_map.values()):
            raise ValueError()
        ordered, pending, visited = [], dict(category_map), set()
        while pending:
            ready = [c for c in pending.values() if c["parent_id"] is None or c["parent_id"] in visited]
            if not ready:
                raise ValueError()
            for category in ready:
                ordered.append(category)
                visited.add(category["id"])
                del pending[category["id"]]
        ids, repositories, slugs = set(), set(), set()
        listings = []
        for raw in apps:
            if not isinstance(raw, dict) or raw.get("published") is not True:
                raise ValueError()
            app_id, repo_id, slug, revision = raw["id"], raw["repoId"], raw["slug"], raw["revision"]
            if (
                not isinstance(app_id, str) or str(UUID(app_id)) != app_id
                or not isinstance(repo_id, str) or not re.fullmatch(r"[1-9][0-9]*", repo_id)
                or not isinstance(slug, str) or len(slug) > 200
                or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)
                or type(revision) is not int or not 1 <= revision <= 2147483647
            ):
                raise ValueError()
            data = Metadata.model_validate(raw, strict=True)
            if (
                data.repoId != repo_id
                or data.repoUrl != raw["repoUrl"]
                or any(key not in raw for key in ("type", "nsfw", "costModel", "categories"))
                or data.nsfw or data.costModel == "Needs review" or not data.categories
                or any(c not in category_map for c in data.categories)
                or app_id in ids or data.repoId in repositories or slug in slugs
            ):
                raise ValueError()
            ids.add(app_id)
            repositories.add(data.repoId)
            slugs.add(slug)
            listings.append({"id": app_id, "slug": slug, "revision": revision, "data": data})
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RuntimeError(
            "Public snapshot is invalid or inconsistent: check listing identities, publication "
            "eligibility and category hierarchy. The source may have changed between reads; retry later."
        ) from None
    return listings, ordered


def _ready():
    try:
        settings = store.get_settings()
        for statement in (
            "SELECT id,name,parent_id FROM categories LIMIT 0",
            "SELECT id,repo_id,slug,published,revision,data,updated_at FROM apps LIMIT 0",
            "SELECT repo_id FROM candidates LIMIT 0",
            "SELECT slug,app_id FROM slug_aliases LIMIT 0",
            "SELECT app_id,day,total FROM clicks LIMIT 0",
            "SELECT id,action,data,created_at FROM audit LIMIT 0",
        ):
            db.query(statement)
        return settings
    except Exception:
        raise RuntimeError(
            "Local database is unavailable or not initialized. Start the dedicated local PostgreSQL "
            "and run local:db:migrate before import; this command never initializes a database."
        ) from None


def _changes(apps: list[dict], categories: list[dict]) -> tuple[list[dict], list[dict]]:
    new_categories = []
    for category in categories:
        rows = db.query("SELECT id,name,parent_id FROM categories WHERE id=$1", [category["id"]])
        if rows and rows[0] != category:
            raise RuntimeError("A local category definition conflicts with the source. Review local categories before retrying.")
        if not rows:
            new_categories.append(category)
    new_apps = []
    for app in apps:
        identity = {"id": app["id"], "repo_id": app["data"].repoId, "slug": app["slug"]}
        rows = db.query("SELECT id,repo_id,slug FROM apps WHERE id=$1 OR repo_id=$2 OR slug=$3", list(identity.values()))
        if rows:
            if len(rows) != 1 or rows[0] != identity:
                raise RuntimeError("A local app identity conflicts with the source. Review local IDs, repositories and slugs before retrying.")
            # Locally approved apps can retain candidates; matching apps are always preserved.
            continue
        if db.query("SELECT repo_id FROM candidates WHERE repo_id=$1", [identity["repo_id"]]):
            raise RuntimeError("A source repository already has a local candidate. Review it locally before retrying.")
        if db.query("SELECT slug FROM slug_aliases WHERE slug=$1", [identity["slug"]]):
            raise RuntimeError("A source slug conflicts with a local redirect. Review local slug aliases before retrying.")
        new_apps.append(app)
    return new_apps, new_categories


def import_catalog(source_url: str = DEFAULT_SOURCE, *, apply: bool = False) -> dict:
    """Preview, or explicitly insert, a validated public snapshot into local PostgreSQL."""
    _guard_destination()
    if type(apply) is not bool:
        raise RuntimeError("Apply must be an explicit boolean; omit it to preview.")
    origin = _source_origin(source_url)
    _ready()
    apps, categories = _snapshot(_fetch(origin, "/api/catalog"), _fetch(origin, "/api/categories"))
    try:
        with db.transaction():
            # Recheck after network access under the application's common writer lock.
            settings = _ready()
            new_apps, new_categories = _changes(apps, categories)
            summary = {
                "applied": apply,
                "insertedApps": len(new_apps), "skippedApps": len(apps) - len(new_apps),
                "insertedCategories": len(new_categories), "skippedCategories": len(categories) - len(new_categories),
            }
            if new_apps and settings.publicationPaused:
                raise RuntimeError("Local publication is paused. Review the local publication control before importing new apps.")
            if apply and (new_apps or new_categories):
                for category in new_categories:
                    db.query("INSERT INTO categories(id,name,parent_id) VALUES($1,$2,$3)", [category["id"], category["name"], category["parent_id"]])
                timestamp = store.now()
                for app in new_apps:
                    data = app["data"]
                    store.validate_publication(data)
                    db.query(
                        "INSERT INTO apps(id,repo_id,slug,published,revision,data,updated_at) VALUES($1,$2,$3,1,$4,$5,$6)",
                        [app["id"], data.repoId, app["slug"], app["revision"], store.encode(data), timestamp],
                    )
                store.bump_revision()
                store.audit("catalog.imported", summary)
        return summary
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError(
            "Local catalog transaction failed and was rolled back. Check local schema, connectivity "
            "and concurrent identity changes, then preview again. No existing records are replaced."
        ) from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE, help="Public HTTPS store origin")
    parser.add_argument("--apply", action="store_true", help="Insert missing records (default: preview only)")
    args = parser.parse_args()
    try:
        print(json.dumps(import_catalog(args.source_url, apply=args.apply), sort_keys=True))
    except RuntimeError as error:
        print(f"Catalog import failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
