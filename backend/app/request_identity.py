"""Signed browser identity; only a separately keyed digest reaches persistence."""
import base64
import hmac
import json
import re
import secrets
import time

from fastapi import HTTPException, Request, Response
from . import auth
from .config import config

LIFETIME = 180 * 24 * 60 * 60


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def visitor_identity(request: Request, response: Response) -> str:
    if config.production and len(config.auth_secret) < 32:
        raise HTTPException(503, "Configure a stable AUTH_SECRET of at least 32 characters for community requests.")
    secret = (config.auth_secret or auth._local_secret).encode()
    now = int(time.time())

    def signature(payload):
        return _b64(hmac.digest(secret, b"community-cookie:v1:" + payload.encode(), "sha256"))

    identifier = None
    cookie = request.cookies.get("store_suggester", "")
    try:
        if not cookie or len(cookie) > 1024:
            raise ValueError()
        payload, signed = cookie.split(".")
        if not hmac.compare_digest(signed, signature(payload)):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if (not isinstance(data, dict) or type(data.get("v")) is not int or data["v"] != 1
                or type(data.get("exp")) is not int or not now < data["exp"] <= now + LIFETIME
                or not isinstance(data.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", data["id"])):
            raise ValueError()
        raw = base64.urlsafe_b64decode(data["id"] + "=")
        if len(raw) != 32 or _b64(raw) != data["id"]:
            raise ValueError()
        identifier = raw
    except (ValueError, TypeError, UnicodeError):
        pass
    if identifier is None:
        identifier = secrets.token_bytes(32)
        payload = _b64(json.dumps({"v": 1, "id": _b64(identifier), "exp": now + LIFETIME}, separators=(",", ":")).encode())
        response.set_cookie("store_suggester", f"{payload}.{signature(payload)}", max_age=LIFETIME,
                            httponly=True, secure=config.app_url.startswith("https://"), samesite="lax", path="/")
    return hmac.digest(secret, b"community-visitor:v1:" + identifier, "sha256").hex()
