import base64
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
import httpx
from pydantic import BaseModel, Field
from .config import config
from .models import Metadata, repository_url
from .store import now

class MissingRepository(RuntimeError):
    pass

class GithubError(RuntimeError):
    pass

class Owner(BaseModel):
    login: str
    html_url: str

class License(BaseModel):
    spdx_id: str | None

class Repository(BaseModel):
    id: int
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
    private: bool = False

def api(path: str, optional=False):
    if not config.github_token:
        raise GithubError("Configure GITHUB_TOKEN for repository discovery.")
    if not path.startswith("/") or path.startswith("//"):
        raise GithubError("Invalid GitHub API path.")
    headers = {"Authorization": f"Bearer {config.github_token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    # GitHub's own rename redirects stay on the fixed API host; never forward tokens to arbitrary hosts.
    url = f"https://api.github.com{path}"
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            for _ in range(4):
                with client.stream("GET", url, headers=headers) as response:
                    if response.status_code in (301, 302, 307, 308):
                        target = httpx.URL(response.headers.get("location", ""))
                        if target.scheme != "https" or target.host != "api.github.com" or target.port not in (None, 443) or target.userinfo:
                            raise GithubError("Unexpected GitHub API redirect.")
                        url = str(target)
                        continue
                    if response.status_code == 404:
                        if optional:
                            return None
                        raise MissingRepository("Repository is missing or inaccessible.")
                    if not response.is_success:
                        raise GithubError(f"GitHub HTTP {response.status_code}; remaining API allowance: {response.headers.get('x-ratelimit-remaining', 'unknown')}")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 2000000:
                            raise GithubError("GitHub response exceeded its limit.")
                    import json
                    return json.loads(data)
            raise GithubError("Too many GitHub API redirects.")
    except httpx.HTTPError:
        raise GithubError("GitHub connection failed.") from None

def search_repositories(search: str, limit=20):
    result = api("/search/repositories?" + urlencode({"q": search, "sort": "stars", "order": "desc", "per_page": min(limit, 30)}))
    if not isinstance(result, dict) or not isinstance(result.get("items"), list):
        raise GithubError("GitHub search returned invalid metadata.")
    return {"urls": [repository_url(item["html_url"]) for item in result["items"]], "incomplete": bool(result.get("incomplete_results"))}

def fetch_repository(url: str) -> Metadata:
    path = repository_url(url).removeprefix("https://github.com")
    repo = Repository.model_validate(api(f"/repos{path}"))
    if repo.private:
        raise GithubError("Only public repositories are eligible.")
    release = api(f"/repos{path}/releases/latest", optional=True)
    readme_raw = api(f"/repos{path}/readme", optional=True)
    version = release.get("tag_name", "") if release and not release.get("prerelease") and not release.get("draft") else ""
    release_date = release.get("published_at") or "" if release else ""
    readme = ""
    if readme_raw and readme_raw.get("encoding") == "base64":
        content = readme_raw.get("content", "")
        if len(content) > 1500000:
            raise GithubError("README exceeds its limit.")
        readme = base64.b64decode(content).decode("utf8", errors="replace")[:15000]
    match = re.search(r"^#{1,4}\s+(?:System\s+)?(?:Requirements|Prerequisites|Dependencies)\s*\r?\n([\s\S]*?)(?=^#{1,4}\s|\Z)", readme, re.I | re.M)
    requirements = match[1].strip()[:3000] if match else ""
    topics = [topic.lower() for topic in repo.topics]
    platforms = [name for topic, name in [("windows", "Windows"), ("macos", "macOS"), ("linux", "Linux"), ("android", "Android"), ("ios", "iOS")] if topic in topics]
    activity = max(repo.pushed_at or "", release_date)
    inactive = repo.archived or bool(activity and datetime.fromisoformat(activity.replace("Z", "+00:00")) < datetime.now(UTC) - timedelta(days=365))
    links = {"Issues": f"{repo.html_url}/issues"}
    if repo.homepage and repo.homepage.startswith("https://"):
        from .models import https_url
        try:
            links["Website"] = https_url(repo.homepage)
        except ValueError:
            pass
    license_id = repo.license.spdx_id if repo.license else ""
    return Metadata(repoId=str(repo.id), repoUrl=repo.html_url, name=repo.name, creator=repo.owner.login, creatorUrl=repo.owner.html_url, description=repo.description or "", license=license_id if license_id and license_id != "NOASSERTION" else "", version=version, platforms=platforms, tags=repo.topics[:30], requirements=requirements, links=links, sources=[repo.html_url, f"{repo.html_url}#readme"], stars=repo.stargazers_count, archived=repo.archived, lastActivity=activity, lastChecked=now(), condition="inactive" if inactive else "active")
