import os
import re
from dataclasses import dataclass
from pathlib import Path
from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if os.getenv("STORE_LOCAL") == "1":
    env_file = Path(os.getenv("STORE_ENV_FILE", ""))
    if not env_file.is_absolute() or not env_file.is_file():
        raise RuntimeError("Local mode requires an absolute STORE_ENV_FILE; use npm run local:setup and local:* commands.")
    local = dotenv_values(env_file, interpolate=False)
    database = local.get("DATABASE_URL", "") or ""
    password = local.get("POSTGRES_PASSWORD", "") or ""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", password) or database != f"postgresql://store:{password}@127.0.0.1:55432/os_appstore_development":
        raise RuntimeError("Local DATABASE_URL must match POSTGRES_PASSWORD and the dedicated loopback PostgreSQL destination; see .env.development.example.")
    # libpq can use PGHOSTADDR instead of the hostname in DATABASE_URL.
    for key in list(os.environ):
        if key.startswith("PG"):
            del os.environ[key]
    os.environ.update({key: local.get(key) or "" for key in (
        "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "OWNER_GITHUB_ID", "AUTH_SECRET",
        "GITHUB_TOKEN", "TYPESAFE_API_KEY", "DISCORD_WEBHOOK_URL", "BACKEND_PROXY_SECRET",
    )})
    os.environ.update(
        DATABASE_URL=database, APP_ENV="development", APP_URL="http://localhost:3000",
        TYPESAFE_MODEL=local.get("TYPESAFE_MODEL") or "jev-1.13.0",
        SQLITE_PATH=str(ROOT / ".data/local-postgres/unused.sqlite"),
        BACKUP_DIR=str(ROOT / ".data/local-postgres/backups"),
    )
else:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "backend" / ".env")

def project_path(value: str | None, default: str) -> Path:
    path = Path(value or default)
    return (path if path.is_absolute() else ROOT / path).resolve()

@dataclass(frozen=True)
class Config:
    app_url: str = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
    database_url: str = os.getenv("DATABASE_URL", "")
    sqlite_path: Path = project_path(os.getenv("SQLITE_PATH"), ".data/store.sqlite")
    backup_dir: Path = project_path(os.getenv("BACKUP_DIR"), ".data/backups")
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_client_id: str = os.getenv("GITHUB_CLIENT_ID", "")
    github_client_secret: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    owner_id: str = os.getenv("OWNER_GITHUB_ID", "")
    auth_secret: str = os.getenv("AUTH_SECRET", "")
    typesafe_key: str = os.getenv("TYPESAFE_API_KEY", "")
    typesafe_model: str = os.getenv("TYPESAFE_MODEL", "jev-1.13.0")
    discord_webhook: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    production: bool = os.getenv("APP_ENV", "development") == "production"
    proxy_secret: str = os.getenv("BACKEND_PROXY_SECRET", "")

config = Config()
