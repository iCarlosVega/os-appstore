from uuid import uuid4
from urllib.parse import urlsplit
from datetime import UTC, datetime, timedelta
import httpx
from .config import config
from .db import query, transaction
from .store import now

def queue(message: str) -> str:
    notification_id = str(uuid4())
    query("INSERT INTO notifications(id,message,status,created_at) VALUES($1,$2,'pending',$3)", [notification_id, message[:1900], now()])
    return notification_id

def deliver(notification_id: str):
    if not config.discord_webhook:
        return
    lease_id, owner = f"notification:{notification_id}", str(uuid4())
    with transaction():
        rows = query("SELECT * FROM notifications WHERE id=$1 AND status!='sent'", [notification_id])
        leases = query("SELECT expires_at FROM leases WHERE id=$1", [lease_id])
        if not rows or (leases and leases[0]["expires_at"] > now()):
            return
        expires = (datetime.now(UTC) + timedelta(seconds=60)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        query("INSERT INTO leases(id,owner,expires_at) VALUES($1,$2,$3) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at", [lease_id, owner, expires])
    status, error = "failed", "Discord delivery interrupted. Review before retrying."
    try:
        url = urlsplit(config.discord_webhook)
        if url.scheme != "https" or url.hostname not in ("discord.com", "discordapp.com") or url.port not in (None, 443) or not url.path.startswith("/api/webhooks/") or url.username or url.password:
            raise ValueError("Invalid Discord webhook configuration.")
        response = httpx.post(config.discord_webhook, json={"content": rows[0]["message"], "allowed_mentions": {"parse": []}}, timeout=5, follow_redirects=False)
        if not response.is_success:
            raise ValueError(f"Discord returned HTTP {response.status_code}")
        status, error = "sent", None
    except (httpx.HTTPError, ValueError) as failure:
        error = str(failure) if isinstance(failure, ValueError) else "Discord connection failed."
    finally:
        with transaction():
            leases = query("SELECT owner FROM leases WHERE id=$1", [lease_id])
            if leases and leases[0]["owner"] == owner:
                query("UPDATE notifications SET status=$1,error=$2 WHERE id=$3", [status, error, notification_id])
                query("DELETE FROM leases WHERE id=$1 AND owner=$2", [lease_id, owner])

def notify(message: str):
    notification_id = queue(message)
    deliver(notification_id)
