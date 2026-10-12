"""Bounded, fixed-origin Telegram transport. No requests on import/construction."""

import json
import logging
import re
from urllib.parse import urlsplit

import httpx

MAX_ID = (1 << 52) - 1
MAX_RESPONSE = 1024 * 1024
_TOKEN = re.compile(r"[1-9][0-9]{0,19}:[A-Za-z0-9_-]{20,128}", re.ASCII)
_METHODS = {
    "getMe", "getWebhookInfo", "getUpdates", "sendMessage",
    "editMessageText", "answerCallbackQuery",
}
_ERRORS = {
    "transient": "Telegram connection failed temporarily; retry shortly.",
    "rate_limited": "Telegram rate limit reached; wait before retrying.",
    "not_modified": "Telegram message already shows the current review.",
    "callback_expired": "Telegram callback acknowledgement has expired.",
    "message_unavailable": "Telegram review message can no longer be edited.",
    "permanent": "Telegram request failed; check bot credentials, chat access and configuration.",
}


class TelegramError(RuntimeError):
    def __init__(self, code: str, retry_after: int | None = None):
        self.code = code if code in _ERRORS else "permanent"
        self.retry_after = min(60, max(1, retry_after)) if type(retry_after) is int else None
        super().__init__(_ERRORS[self.code])


def _integer(value: object, minimum: int = 1, maximum: int = MAX_ID) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _string(value: object, limit: int, *, empty: bool = False) -> bool:
    if not isinstance(value, str) or (not value and not empty):
        return False
    try:
        return len(value.encode("utf-16-le")) // 2 <= limit
    except UnicodeError:
        return False


def _url(value: object) -> bool:
    if not _string(value, 2048) or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        return bool(parsed.scheme in ("https", "http") and parsed.hostname
                    and not parsed.username and not parsed.password and parsed.port != 0)
    except ValueError:
        return False


def _markup(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"inline_keyboard"}:
        return False
    rows = value["inline_keyboard"]
    if not isinstance(rows, list) or len(rows) > 100:
        return False
    count = 0
    for row in rows:
        if not isinstance(row, list) or not 1 <= len(row) <= 8:
            return False
        count += len(row)
        for button in row:
            if not isinstance(button, dict) or not _string(button.get("text"), 64):
                return False
            if set(button) == {"text", "callback_data"}:
                data = button["callback_data"]
                if not _string(data, 64) or not 1 <= len(data.encode("utf-8")) <= 64:
                    return False
            elif set(button) != {"text", "url"} or not _url(button["url"]):
                return False
    return count <= 100


def _payload(method: str, payload: dict) -> None:
    valid = False
    if method in ("getMe", "getWebhookInfo"):
        valid = not payload
    elif method == "getUpdates":
        valid = (set(payload) <= {"offset", "limit", "timeout", "allowed_updates"}
                 and _integer(payload.get("offset", 0), 0)
                 and _integer(payload.get("limit", 20), 1, 20)
                 and _integer(payload.get("timeout", 20), 0, 20)
                 and payload.get("allowed_updates", ["message", "callback_query"])
                 == ["message", "callback_query"])
    elif method in ("sendMessage", "editMessageText"):
        keys = {"chat_id", "text", "reply_markup", "link_preview_options", "protect_content"}
        if method == "editMessageText":
            keys = keys - {"protect_content"} | {"message_id"}
        valid = (set(payload) <= keys and _integer(payload.get("chat_id"))
                 and _string(payload.get("text"), 4096)
                 and ("reply_markup" not in payload or _markup(payload["reply_markup"]))
                 and ("link_preview_options" not in payload
                      or payload["link_preview_options"] == {"is_disabled": True})
                 and ("protect_content" not in payload or payload["protect_content"] is True)
                 and (method != "editMessageText" or _integer(payload.get("message_id"))))
    elif method == "answerCallbackQuery":
        valid = (set(payload) <= {"callback_query_id", "text", "show_alert"}
                 and _string(payload.get("callback_query_id"), 256)
                 and ("text" not in payload or _string(payload["text"], 200, empty=True))
                 and ("show_alert" not in payload or type(payload["show_alert"]) is bool))
    if not valid:
        raise TelegramError("permanent")


def _result(method: str, result: object, payload: dict) -> object:
    valid = False
    if method == "getMe":
        valid = (isinstance(result, dict) and _integer(result.get("id"))
                 and result.get("is_bot") is True and _string(result.get("first_name"), 256))
    elif method == "getWebhookInfo":
        valid = (isinstance(result, dict) and _string(result.get("url"), 2048, empty=True)
                 and type(result.get("has_custom_certificate")) is bool
                 and _integer(result.get("pending_update_count"), 0))
    elif method == "getUpdates":
        valid = isinstance(result, list) and len(result) <= payload.get("limit", 20)
        previous = -1
        if valid:
            for update in result:
                if (not isinstance(update, dict) or not _integer(update.get("update_id"), 0, MAX_ID - 1)
                        or update["update_id"] <= previous):
                    valid = False
                    break
                previous = update["update_id"]
    elif method in ("sendMessage", "editMessageText"):
        valid = (isinstance(result, dict) and _integer(result.get("message_id"))
                 and isinstance(result.get("chat"), dict)
                 and type(result["chat"].get("id")) is int
                 and result["chat"]["id"] == payload["chat_id"]
                 and result["chat"].get("type") == "private"
                 and (method != "editMessageText" or result["message_id"] == payload["message_id"]))
    elif method == "answerCallbackQuery":
        valid = result is True
    if not valid:
        raise TelegramError("permanent")
    return result


def _suppress_request_logs() -> None:
    # These libraries include token-bearing URLs/exceptions in request/debug logs.
    names = {"httpx", "httpcore", "httpcore.connection", "httpcore.http11",
             "httpcore.http2", "httpcore.proxy", "httpcore.socks"}
    names.update(name for name in list(logging.Logger.manager.loggerDict)
                 if name.startswith(("httpx.", "httpcore.")))
    for name in names:
        logging.getLogger(name).disabled = True


def _failure(method: str, status: int, body: dict, retry_header: str | None) -> TelegramError:
    error = body.get("error_code")
    statuses = {status, error} if type(error) is int else {status}
    parameters = body.get("parameters")
    retry = parameters.get("retry_after") if isinstance(parameters, dict) else None
    if type(retry) is not int and isinstance(retry_header, str) and re.fullmatch(r"[0-9]{1,9}", retry_header):
        retry = int(retry_header)
    if 429 in statuses:
        return TelegramError("rate_limited", retry)
    if any(500 <= code <= 599 for code in statuses):
        return TelegramError("transient")
    description = body.get("description", "")
    description = description.lower() if isinstance(description, str) else ""
    if method == "editMessageText":
        if "message is not modified" in description:
            return TelegramError("not_modified")
        if any(text in description for text in (
            "message to edit not found", "message can't be edited", "message can not be edited",
            "message_id_invalid", "message identifier is not specified",
        )):
            return TelegramError("message_unavailable")
    if method == "answerCallbackQuery" and any(text in description for text in (
        "query is too old", "query id is invalid", "query_id_invalid", "query has expired",
        "response timeout expired",
    )):
        return TelegramError("callback_expired")
    return TelegramError("permanent")


class TelegramClient:
    def __init__(self, token: str):
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise TelegramError("permanent")
        self._token = token
        self._client = httpx.Client(timeout=30, follow_redirects=False, trust_env=False,
                                    headers={"Accept-Encoding": "identity"})

    def call(self, method: str, payload: dict | None = None) -> object:
        if not isinstance(method, str) or method not in _METHODS:
            raise TelegramError("permanent")
        payload = {} if payload is None else payload
        if not isinstance(payload, dict):
            raise TelegramError("permanent")
        _payload(method, payload)
        try:
            encoded = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode("ascii")
        except (ValueError, TypeError, RecursionError):
            raise TelegramError("permanent") from None
        if len(encoded) > 64 * 1024:
            raise TelegramError("permanent")
        _suppress_request_logs()
        try:
            with self._client.stream(
                "POST", f"https://api.telegram.org/bot{self._token}/{method}",
                content=encoded, headers={"Content-Type": "application/json"},
            ) as response:
                if 300 <= response.status_code < 400:
                    raise TelegramError("permanent")
                retryable = response.status_code == 429 or 500 <= response.status_code <= 599
                raw = bytearray()
                for chunk in response.iter_raw(chunk_size=16384):
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE:
                        if retryable:
                            raise _failure(method, response.status_code, {}, response.headers.get("Retry-After"))
                        raise TelegramError("permanent")
                # Reject compressed responses rather than decompress unbounded provider input.
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    if retryable:
                        raise _failure(method, response.status_code, {}, response.headers.get("Retry-After"))
                    raise TelegramError("permanent")
                try:
                    body = json.loads(raw)
                except (ValueError, UnicodeError, RecursionError):
                    if retryable:
                        raise _failure(method, response.status_code, {}, response.headers.get("Retry-After")) from None
                    raise TelegramError("permanent") from None
                if retryable:
                    raise _failure(method, response.status_code, body if isinstance(body, dict) else {},
                                   response.headers.get("Retry-After"))
                if not isinstance(body, dict) or type(body.get("ok")) is not bool:
                    raise TelegramError("permanent")
                if not response.is_success or not body["ok"]:
                    raise _failure(method, response.status_code, body, response.headers.get("Retry-After"))
                return _result(method, body.get("result"), payload)
        except (httpx.HTTPError, OSError):
            raise TelegramError("transient") from None
        except TelegramError:
            raise
        except RuntimeError:
            # A closed client is a configuration/lifecycle error, not an endless retry.
            raise TelegramError("permanent") from None

    def close(self) -> None:
        _suppress_request_logs()
        try:
            self._client.close()
        except (httpx.HTTPError, OSError, RuntimeError):
            raise TelegramError("permanent") from None
