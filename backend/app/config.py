import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
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
    typesafe_model: str = os.getenv("TYPESAFE_MODEL", "jev-latest")
    discord_webhook: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    production: bool = os.getenv("APP_ENV", "development") == "production"
    proxy_secret: str = os.getenv("BACKEND_PROXY_SECRET", "")

config = Config()
