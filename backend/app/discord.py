from uuid import uuid4
from urllib.parse import urlsplit
import httpx
from .config import config
from .db import query
from .store import now

def queue(message: str) -> str:
    notification_id = str(uuid4())
    query("INSERT INTO notifications(id,message,status,created_at) VALUES($1,$2,'pending',$3)", [notification_id, message[:1900], now()])
    return notification_id

def deliver(notification_id: str):
    rows = query("SELECT * FROM notifications WHERE id=$1 AND status!='sent'", [notification_id])
    if not rows or not config.discord_webhook:
        return
    try:
        url = urlsplit(config.discord_webhook)
        if url.scheme != "https" or url.hostname not in ("discord.com", "discordapp.com") or not url.path.startswith("/api/webhooks/") or url.username or url.password:
            raise ValueError("Invalid Discord webhook configuration.")
        response = httpx.post(config.discord_webhook, json={"content": rows[0]["message"], "allowed_mentions": {"parse": []}}, timeout=5, follow_redirects=False)
        if not response.is_success:
            raise ValueError(f"Discord returned HTTP {response.status_code}")
        query("UPDATE notifications SET status='sent',error=NULL WHERE id=$1", [notification_id])
    except (httpx.HTTPError, ValueError) as error:
        message = str(error) if isinstance(error, ValueError) else "Discord connection failed."
        query("UPDATE notifications SET status='failed',error=$1 WHERE id=$2", [message, notification_id])

def notify(message: str):
    notification_id = queue(message)
    deliver(notification_id)
