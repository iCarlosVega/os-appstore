"""Public GitHub result cards; provider facts are cached separately from store status."""
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from . import auth, db, github
from .models import repository_url

router = APIRouter(prefix="/api/community")


class RepositoryCard(github.GithubModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    html_url: str = Field(max_length=2048)
    owner: github.Owner
    description: str | None = Field(max_length=4000)
    stargazers_count: int = Field(ge=0)
    license: github.License | None
    archived: bool
    private: bool


def repository_status(repo_id: str) -> dict:
    # Session 1 supplies this service; importing lazily keeps the router independent.
    from .community_requests import repository_status as status
    return status(repo_id)


def _stamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _throttled(retry: int):
    return HTTPException(429, "Please wait before searching GitHub again.", headers={"Retry-After": str(retry)})


def _address_limit(request: Request):
    if not auth.rate_limit(request, "community-github", 10):
        raise _throttled(60 - int(time.time()) % 60)


def _provider_limit():
    now = time.time()
    bucket = int(now // 60)
    # One durable conditional increment coordinates all clients and backend processes.
    with db.transaction():
        rows = db.query("""INSERT INTO rate_limits(id,total,expires_at) VALUES($1,1,$2)
            ON CONFLICT(id) DO UPDATE SET total=rate_limits.total+1
            WHERE rate_limits.total<10 RETURNING total""",
            [f"community:github:provider:{bucket}", _stamp((bucket + 1) * 60)])
    if not rows:
        raise _throttled(60 - int(now) % 60)


def _summary(raw: dict) -> dict:
    repo = RepositoryCard.model_validate(raw)
    canonical = repository_url(repo.html_url)
    if (repo.private or canonical != f"https://github.com/{repo.owner.login}/{repo.name}"
            or repo.owner.html_url != f"https://github.com/{repo.owner.login}"):
        raise ValueError("Invalid public repository metadata")
    license_id = repo.license.spdx_id if repo.license else ""
    if license_id and len(license_id) > 200:
        raise ValueError("Invalid license")
    return {
        "repoId": str(repo.id), "repoUrl": canonical, "name": repo.name, "owner": repo.owner.login,
        "description": repo.description or "", "stars": repo.stargazers_count,
        "license": license_id if license_id and license_id not in ("NOASSERTION", "NONE") else "",
        "archived": repo.archived,
    }


def _provider_error(error: github.GithubError):
    # github.api exposes only this bounded diagnostic format, never response bodies.
    diagnostic = re.fullmatch(
        r"GitHub HTTP (\d{3}); remaining API allowance: ([^;]*); reset: ([^;]*); retry after: (.*)", str(error))
    if diagnostic:
        status, remaining, reset, retry = diagnostic.groups()
        if status == "429" or (status == "403" and (remaining == "0" or retry.isascii() and retry.isdigit())):
            wait = 60
            if retry.isascii() and retry.isdigit() and len(retry) <= 10:
                wait = max(1, min(86400, int(retry)))
            elif reset.isascii() and reset.isdigit() and len(reset) <= 10:
                wait = max(1, min(86400, int(reset) - int(time.time())))
            return _throttled(wait)
    return HTTPException(503, "GitHub search is unavailable. Please try again later.")


def _facts(kind: str, value: str) -> dict:
    key = f"community:github:{kind}:v1:" + hashlib.sha256(value.encode()).hexdigest()
    cached = db.query("SELECT data FROM search_cache WHERE id=$1 AND expires_at>$2", [key, _stamp(time.time())])
    if cached:
        return json.loads(cached[0]["data"])
    _provider_limit()
    try:
        if kind == "search":
            raw = github.api("/search/repositories?" + urlencode({"q": value, "per_page": 10}))
            if (not isinstance(raw, dict) or not isinstance(raw.get("items"), list)
                    or type(raw.get("total_count")) is not int or raw["total_count"] < 0
                    or type(raw.get("incomplete_results")) is not bool or len(raw["items"]) > 10):
                raise ValueError("Invalid search response")
            facts = {"items": [_summary(item) for item in raw["items"]], "incomplete": raw["incomplete_results"]}
        else:
            raw = github.api("/repos" + value.removeprefix("https://github.com"))
            if isinstance(raw, dict) and raw.get("private") is True:
                raise HTTPException(404, "Public repository was not found.")
            facts = {"item": _summary(raw)}
    except github.MissingRepository:
        raise HTTPException(404, "Public repository was not found.") from None
    except github.GithubError as error:
        raise _provider_error(error) from None
    except (ValueError, TypeError):
        raise HTTPException(503, "GitHub returned invalid repository metadata. Please try again later.") from None
    db.query("""INSERT INTO search_cache(id,data,expires_at) VALUES($1,$2,$3)
        ON CONFLICT(id) DO UPDATE SET data=excluded.data,expires_at=excluded.expires_at""",
        [key, json.dumps(facts, separators=(",", ":")), _stamp(time.time() + 300)])
    return facts


def _with_status(item: dict) -> dict:
    status = repository_status(item["repoId"])
    return {**item, "status": status["status"], "suggestionCount": status["suggestionCount"]}


def _failure(error: HTTPException) -> JSONResponse:
    return JSONResponse({"error": error.detail}, status_code=error.status_code, headers=error.headers)


@router.get("/repositories")
def repositories(request: Request, q: str = Query(default="", max_length=200)):
    try:
        _address_limit(request)
        words = re.findall(r"\w+(?:[./-]\w+)*", q)
        if len(q.strip()) < 3 or not words:
            raise HTTPException(400, "Enter at least three characters to search GitHub.")
        # Quoted words cannot introduce qualifiers, negation or boolean query operators.
        query = " ".join(f'"{word}"' for word in words) + " is:public"
        facts = _facts("search", query)
        return {"items": [_with_status(item) for item in facts["items"]], "incomplete": facts["incomplete"]}
    except HTTPException as error:
        return _failure(error)


@router.get("/repository")
def repository(request: Request, url: str = Query(max_length=2048)):
    try:
        _address_limit(request)
        try:
            canonical = repository_url(url)
        except ValueError:
            raise HTTPException(400, "Use https://github.com/owner/repository without additional paths.") from None
        facts = _facts("exact", canonical.lower())
        return {"item": _with_status(facts["item"])}
    except HTTPException as error:
        return _failure(error)
