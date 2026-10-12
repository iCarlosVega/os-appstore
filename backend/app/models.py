import re
import unicodedata
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, AfterValidator, field_validator

CATEGORY_NAMES = ["Productivity", "Development", "Creative Tools", "Privacy", "Utilities", "Communication", "Education", "AI", "Gaming"]
PLATFORMS = ("Windows", "macOS", "Linux", "Android", "iOS", "Browser")
TYPES = ("Desktop app", "Mobile app", "Game", "Command-line tool", "Browser extension", "Plugin", "Library", "Self-hosted service", "Web app")
JOB_KINDS = ("discovery", "maintenance", "priority", "digest", "backup")

class InputError(ValueError):
    pass

def https_url(value: str) -> str:
    try:
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("Use an HTTPS URL without credentials.")
        _ = url.port
    except ValueError:
        raise ValueError("Use an HTTPS URL without credentials.") from None
    return value

HttpsUrl = Annotated[str, Field(max_length=2048), AfterValidator(https_url)]
Short = Annotated[str, Field(max_length=200)]
Platform = Literal["Windows", "macOS", "Linux", "Android", "iOS", "Browser"]
SoftwareType = Literal["Desktop app", "Mobile app", "Game", "Command-line tool", "Browser extension", "Plugin", "Library", "Self-hosted service", "Web app"]

def repository_url(value: str) -> str:
    try:
        url = urlsplit(https_url(value))
        parts = url.path.rstrip("/").split("/")[1:]
        if url.hostname != "github.com" or url.port or url.query or url.fragment or len(parts) != 2 or any(not re.fullmatch(r"[\w.-]+", p, re.ASCII) for p in parts):
            raise ValueError()
        owner, repo = parts
        repo = re.sub(r"\.git$", "", repo)
        if owner in (".", "..") or repo in ("", ".", ".."):
            raise ValueError()
        return f"https://github.com/{owner}/{repo}"
    except ValueError:
        raise InputError("Use https://github.com/owner/repository without additional paths.") from None

def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")[:80]

class Model(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, validate_default=True)

class Attributes(Model):
    offline: bool | None = None
    noAccount: bool | None = None
    accessible: bool | None = None
    lightweight: bool | None = None

class Metadata(Model):
    repoId: Annotated[str, Field(pattern=r"^\d+$")]
    repoUrl: HttpsUrl
    name: Annotated[Short, Field(min_length=1)]
    creator: Annotated[Short, Field(min_length=1)]
    creatorUrl: HttpsUrl
    description: str = Field(default="", max_length=4000)
    license: Short = ""
    version: Short = ""
    platforms: list[Platform] = Field(default_factory=list, max_length=6)
    architectures: list[Literal["x86-64", "ARM64"]] = Field(default_factory=list, max_length=2)
    categories: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=20)
    tags: list[Short] = Field(default_factory=list, max_length=30)
    aliases: list[Short] = Field(default_factory=list, max_length=30)
    alternatives: list[Short] = Field(default_factory=list, max_length=30)
    requirements: str = Field(default="", max_length=4000)
    type: SoftwareType = "Desktop app"
    setup: Short = "See project instructions"
    costModel: Literal["Free", "Free with optional paid features", "Needs review"] = "Needs review"
    attributes: Attributes = Field(default_factory=Attributes)
    links: dict[Annotated[str, Field(max_length=40)], HttpsUrl] = Field(default_factory=dict, max_length=20)
    sources: list[HttpsUrl] = Field(default_factory=list, max_length=20)
    stars: int = Field(default=0, ge=0)
    archived: bool = False
    lastActivity: Short = ""
    lastChecked: Short = ""
    condition: Literal["active", "inactive", "availability-needs-review"] = "active"
    priority: bool = False
    downloadsEnabled: bool = True
    nsfw: bool = False
    overrides: list[Annotated[str, Field(max_length=40)]] = Field(default_factory=list, max_length=50)

    @field_validator("repoUrl")
    @classmethod
    def official_repository(cls, value: str) -> str:
        return repository_url(value)

Clock = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Nonnegative = Annotated[int, Field(ge=0)]
class Settings(Model):
    revision: int = Field(default=1, ge=1)
    budgetMicros: int = Field(default=20000000, ge=1, le=20000000)
    hostingMicros: Nonnegative | None = None
    hostingActualMicros: Nonnegative = 0
    hostingActualPeriod: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}$")
    jevMicrosPerMillion: Annotated[int, Field(gt=0)] | None = None
    discoveryPaused: bool = False
    maintenancePaused: bool = False
    publicationPaused: bool = False
    downloadsPaused: bool = False
    aiPaused: bool = True
    budgetPaused: bool = False
    failedKinds: list[str] = Field(default_factory=list, max_length=5)
    timezone: str = "America/New_York"
    discoveryTime: Clock = "02:00"
    maintenanceTime: Clock = "03:00"
    priorityTime: Clock = "03:00"
    digestTime: Clock = "09:00"
    backupTime: Clock = "03:30"
    dailyCandidates: int = Field(default=10, ge=1, le=100)
    repositoryLimit: int = Field(default=100, ge=1, le=100)
    seeds: list[str] = Field(default_factory=list, max_length=100)
    donationUrl: str = ""

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, KeyError):
            raise ValueError("Choose a valid IANA timezone.") from None
        return value

    @field_validator("donationUrl")
    @classmethod
    def optional_url(cls, value: str) -> str:
        return https_url(value) if value else ""

    @field_validator("seeds")
    @classmethod
    def valid_seeds(cls, values: list[str]) -> list[str]:
        return [repository_url(v) for v in values]

class AppRequest(Model):
    name: str = Field(min_length=2, max_length=200)
    repoUrl: str = Field(default="", max_length=300)
    website: str = Field(default="", max_length=0)

class DownloadRequest(Model):
    id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")

class AdminAction(Model):
    operation: str = Field(max_length=40)
    fields: dict[str, list[str]] = Field(max_length=100)

    @field_validator("fields")
    @classmethod
    def bounded_fields(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if any(len(k) > 80 or len(vs) > 100 or any(len(v) > 20000 for v in vs) for k, vs in value.items()):
            raise ValueError("Form input is too large.")
        return value
