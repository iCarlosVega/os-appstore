import os
import re
import sqlite3
import subprocess
from .config import config
from .store import now

def backup_database():
    directory = config.backup_dir
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = now().replace(":", "-").replace(".", "-")
    path = directory / f"store-{stamp}.{'dump' if config.database_url else 'sqlite'}"
    temporary = path.with_name(path.name + ".partial")
    try:
        if config.database_url:
            env = {**os.environ, "PGCONNECT_TIMEOUT": "10"}
            try:
                subprocess.run(["pg_dump", "--dbname", config.database_url, "--format=custom", "--file", str(temporary)], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=True)
            except (OSError, subprocess.SubprocessError):
                raise RuntimeError("Database backup failed. Install pg_dump matching the server and check connectivity.") from None
        else:
            with sqlite3.connect(config.sqlite_path) as source, sqlite3.connect(temporary) as destination:
                source.backup(destination)
        temporary.chmod(0o600)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    backups = sorted((p for p in directory.iterdir() if re.fullmatch(r"store-\d{4}-\d{2}-\d{2}T[\d-]+Z\.(dump|sqlite)", p.name)), reverse=True)
    for old in backups[7:]:
        old.unlink()
    return str(path)
