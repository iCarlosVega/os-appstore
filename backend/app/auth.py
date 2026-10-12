import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlsplit
from fastapi import HTTPException, Request
from .config import config


def configured() -> bool:
    return bool(config.github_client_id and config.github_client_secret and config.owner_id.isdigit() and len(config.auth_secret) >= 32)

def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")

def sign(value: dict) -> str:
    if len(config.auth_secret) < 32:
        raise HTTPException(503, "Owner authentication is not configured.")
    payload = _b64(json.dumps(value, separators=(",", ":")).encode())
    signature = _b64(hmac.digest(config.auth_secret.encode(), payload.encode(), "sha256"))
    return f"{payload}.{signature}"

def verify(value: str | None):
    try:
        if not value or len(value) > 3000 or len(config.auth_secret) < 32:
            return None
        payload, signature = value.split(".")
        expected = _b64(hmac.digest(config.auth_secret.encode(), payload.encode(), "sha256"))
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if not isinstance(data, dict) or not isinstance(data.get("exp"), (int, float)) or data["exp"] < time.time() * 1000:
            return None
        return data
    except (ValueError, TypeError):
        return None

def current_owner(request: Request) -> bool:
    session = verify(request.cookies.get("store_session")) if configured() else None
    return bool(session and session.get("owner") == config.owner_id)

def require_owner(request: Request):
    if not current_owner(request):
        raise HTTPException(401, "Administrator sign-in required.")

def require_origin(request: Request):
    parsed = urlsplit(config.app_url)
    if request.headers.get("origin") != f"{parsed.scheme}://{parsed.netloc}":
        raise HTTPException(403, "Request origin was not accepted.")

def require_mutation(request: Request):
    require_owner(request)
    require_origin(request)

def state():
    value = secrets.token_urlsafe(32)
    return value, sign({"state": value, "exp": int(time.time() * 1000) + 600000})

def cookie_options():
    return {"httponly": True, "secure": config.app_url.startswith("https://"), "samesite": "lax", "path": "/"}

_local_secret = secrets.token_hex(32)
def rate_limit(request: Request, action: str, limit: int, seconds=60) -> bool:
    from .db import query
    from datetime import UTC, datetime
    bucket = int(time.time() // seconds)
    trusted = len(config.proxy_secret) >= 32 and secrets.compare_digest(request.headers.get("x-store-proxy", ""), config.proxy_secret)
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip() if trusted else ""
    address = forwarded or (request.client.host if request.client else "local")
    key = hmac.new((config.auth_secret or _local_secret).encode(), f"{action}:{bucket}:{address}".encode(), hashlib.sha256).hexdigest()
    expires = datetime.fromtimestamp((bucket + 1) * seconds, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    row = query("INSERT INTO rate_limits(id,total,expires_at) VALUES($1,1,$2) ON CONFLICT(id) DO UPDATE SET total=rate_limits.total+1 RETURNING total", [key, expires])[0]
    return row["total"] <= limit
