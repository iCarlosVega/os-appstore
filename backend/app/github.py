import base64
import binascii
import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .config import config
from .models import Metadata, https_url, repository_url
from .store import now

class MissingRepository(RuntimeError):
    pass

class GithubError(RuntimeError):
    pass

class GithubModel(BaseModel):
    model_config = ConfigDict(strict=True)

class Owner(GithubModel):
    login: str
    html_url: str

class License(GithubModel):
    spdx_id: str | None

class Repository(GithubModel):
    id: int = Field(gt=0)
    name: str
    html_url: str
    description: str | None
    owner: Owner
    license: License | None
    stargazers_count: int = Field(ge=0)
    archived: bool
    pushed_at: str | None
    topics: list[str] = Field(default_factory=list)
    homepage: str | None = None
    private: bool

class Release(GithubModel):
    tag_name: str = Field(min_length=1, max_length=200)
    published_at: str | None
    prerelease: bool
    draft: bool

class Readme(GithubModel):
    encoding: str
    content: str = Field(max_length=1500000)

def timestamp(value: str | None):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("GitHub timestamp has no timezone.")
    return parsed.astimezone(UTC)

def api(path: str, optional=False):
    if not config.github_token:
        raise GithubError("Configure GITHUB_TOKEN for repository discovery.")
    if not path.startswith("/") or path.startswith("//"):
        raise GithubError("Invalid GitHub API path.")
    headers = {"Authorization": f"Bearer {config.github_token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    # GitHub's own rename redirects stay on the fixed API host; never forward tokens to arbitrary hosts.
    try:
        url = httpx.URL(f"https://api.github.com{path}")
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            for _ in range(4):
                if url.scheme != "https" or url.host != "api.github.com" or url.port not in (None, 443) or url.userinfo or url.fragment:
                    raise GithubError("Unexpected GitHub API destination.")
                with client.stream("GET", url, headers=headers) as response:
                    if response.status_code in (301, 302, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise GithubError("GitHub API redirect has no destination.")
                        url = url.join(location)
                        continue
                    if response.status_code == 404:
                        if optional:
                            return None
                        raise MissingRepository("Repository is missing or inaccessible.")
                    if not response.is_success:
                        raise GithubError(f"GitHub HTTP {response.status_code}; remaining API allowance: {response.headers.get('x-ratelimit-remaining', 'unknown')[:40]}; reset: {response.headers.get('x-ratelimit-reset', 'unknown')[:40]}; retry after: {response.headers.get('retry-after', 'unknown')[:40]}")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        if len(data) + len(chunk) > 2000000:
                            raise GithubError("GitHub response exceeded its limit.")
                        data.extend(chunk)
                    return json.loads(data)
            raise GithubError("Too many GitHub API redirects.")
    except httpx.HTTPError:
        raise GithubError("GitHub connection failed.") from None
    except (ValueError, httpx.InvalidURL):
        raise GithubError("GitHub returned invalid JSON or an invalid API URL.") from None

def search_repositories(search: str, limit=20):
    limit = max(0, min(limit, 100))
    if not limit:
        return {"urls": [], "incomplete": False}
    urls, incomplete = [], False
    per_page = min(limit, 30)
    try:
        for page in range(1, 5):
            result = api("/search/repositories?" + urlencode({"q": search, "sort": "stars", "order": "desc", "per_page": per_page, "page": page}))
            if not isinstance(result, dict) or not isinstance(result.get("items"), list) or type(result.get("total_count")) is not int or result["total_count"] < 0 or type(result.get("incomplete_results")) is not bool:
                raise GithubError("GitHub search returned invalid metadata.")
            items = result["items"]
            if len(items) > per_page:
                raise GithubError("GitHub search exceeded its page limit.")
            for item in items:
                if not isinstance(item, dict) or item.get("private") is not False or not isinstance(item.get("html_url"), str):
                    raise GithubError("GitHub search returned non-public or invalid metadata.")
                url = repository_url(item["html_url"])
                if url not in urls:
                    urls.append(url)
            incomplete |= result["incomplete_results"]
            if len(urls) >= limit or len(items) < per_page:
                incomplete |= result["total_count"] > min(len(urls), limit)
                break
        else:
            incomplete |= result["total_count"] > len(urls)
        return {"urls": urls[:limit], "incomplete": incomplete}
    except (KeyError, TypeError, ValueError):
        raise GithubError("GitHub search returned invalid metadata.") from None

def fetch_repository(url: str) -> Metadata:
    path = repository_url(url).removeprefix("https://github.com")
    try:
        repo = Repository.model_validate(api(f"/repos{path}"))
        if repo.private:
            raise GithubError("Only public repositories are eligible.")
        canonical = repository_url(repo.html_url)
        if repo.owner.html_url != f"https://github.com/{repo.owner.login}":
            raise GithubError("GitHub returned an invalid owner URL.")
        path = canonical.removeprefix("https://github.com")
        sources = [canonical]
        release_raw = api(f"/repos{path}/releases/latest", optional=True)
        release = Release.model_validate(release_raw) if release_raw is not None else None
        stable = release is not None and not release.prerelease and not release.draft
        version = release.tag_name if stable else ""
        dates = [date for date in (timestamp(repo.pushed_at), timestamp(release.published_at) if stable else None) if date]
        activity = max(dates).isoformat().replace("+00:00", "Z") if dates else ""
        if stable:
            sources.append(f"{canonical}/releases/tag/{quote(version, safe='')}")
        readme_raw = api(f"/repos{path}/readme", optional=True)
        readme = ""
        if readme_raw is not None:
            document = Readme.model_validate(readme_raw)
            if document.encoding == "base64":
                content = re.sub(r"\s", "", document.content)
                readme = base64.b64decode(content, validate=True).decode("utf8", errors="replace")[:15000]
                sources.append(f"{canonical}#readme")
    except (ValidationError, ValueError, binascii.Error):
        raise GithubError("GitHub returned invalid repository, release, or README metadata.") from None
    match = re.search(r"^#{1,6}[ \t]+(?:System[ \t]+)?(?:Requirements|Prerequisites|Dependencies)[ \t]*\r?\n([\s\S]*?)(?=^#{1,6}[ \t]|\Z)", readme, re.I | re.M)
    requirements = match[1].strip()[:3000] if match else ""
    inactive = repo.archived or bool(dates and max(dates) < datetime.now(UTC) - timedelta(days=365))
    links = {"Issues": f"{canonical}/issues"}
    if stable:
        links["Releases"] = f"{canonical}/releases"
    if repo.homepage and len(repo.homepage) <= 2048:
        try:
            links["Website"] = https_url(repo.homepage)
        except ValueError:
            pass
    license_id = repo.license.spdx_id if repo.license else ""
    # Topics are useful tags, but do not prove compatibility or free-use eligibility.
    try:
        return Metadata(repoId=str(repo.id), repoUrl=canonical, name=repo.name, creator=repo.owner.login, creatorUrl=repo.owner.html_url, description=repo.description or "", license=license_id if license_id and license_id not in ("NOASSERTION", "NONE") else "", version=version, tags=repo.topics[:30], requirements=requirements, links=links, sources=sources, stars=repo.stargazers_count, archived=repo.archived, lastActivity=activity, lastChecked=now(), condition="inactive" if inactive else "active")
    except ValidationError:
        raise GithubError("GitHub metadata exceeded catalog field limits.") from None
