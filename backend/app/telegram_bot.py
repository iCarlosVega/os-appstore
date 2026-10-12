"""Owner-bound Telegram review UI; runtime supplies configuration and lease checks."""

import json
import re
import threading
import unicodedata
from collections.abc import Callable
from urllib.parse import urlsplit

from . import db, telegram_review as reviews
from .models import InputError, repository_url
from .telegram_api import MAX_ID, TelegramClient, TelegramError
from .telegram_review import ReviewView

_TOKEN = re.compile(r"[A-Za-z0-9_-]{22}", re.ASCII)
_POSITIVE = re.compile(r"[1-9][0-9]{0,9}", re.ASCII)
_INDEX = re.compile(r"0|[1-9][0-9]{0,9}", re.ASCII)
_MAX_VERSION = 2147483647
_HELP = (
    "Accept publishes an app using its suggested category and metadata. Reject dismisses it. "
    "More shows the full details. Open repo opens GitHub. "
    "/pending delivers unsent reviews; /help shows these instructions."
)


def _int(value: object, minimum: int = 1, maximum: int = MAX_ID) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _text(value: object, limit: int) -> str:
    text = str(value) if value is not None else "unknown"
    # Strip controls, bidi overrides and invalid surrogates from untrusted display text.
    text = " ".join("".join(c for c in text if unicodedata.category(c)[0] != "C").split())
    encoded = text.encode("utf-16-le")
    if len(encoded) <= limit * 2:
        return text
    return encoded[:max(0, limit - 1) * 2].decode("utf-16-le", errors="ignore") + "…"


def _parse_callback(data: object) -> tuple[str, int, str, str | None]:
    if not isinstance(data, str) or not data.isascii() or not 1 <= len(data) <= 64:
        raise InputError("Invalid review button. Use the current card.")
    parts = data.split(":")
    if len(parts) not in (4, 5) or parts[0] != "tg" or not _TOKEN.fullmatch(parts[1]):
        raise InputError("Invalid review button. Use the current card.")
    if not _POSITIVE.fullmatch(parts[2]) or int(parts[2]) > _MAX_VERSION:
        raise InputError("Invalid review version. Use the current card.")
    action = parts[3]
    value = parts[4] if len(parts) == 5 else None
    if action in ("category", "type", "cost"):
        valid = value is not None and _INDEX.fullmatch(value) and int(value) <= _MAX_VERSION
    elif action == "safe":
        valid = value == "yes"
    else:
        valid = action in ("approve", "accept", "reject", "more") and value is None
    if not valid:
        raise InputError("Invalid review choice. Use the current card.")
    return parts[1], int(parts[2]), action, value


def _button(review: ReviewView, label: str, action: str, value: str | None = None) -> dict:
    data = f"tg:{review['token']}:{review['draft_version']}:{action}"
    if value is not None:
        data += f":{value}"
    _parse_callback(data)
    return {"text": _text(label, 64), "callback_data": data}


def _app_base(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 1400 or any(
        c.isspace() or unicodedata.category(c)[0] == "C" for c in value
    ):
        raise ValueError("Configure a valid APP_URL for Telegram review links.")
    try:
        url = urlsplit(value)
        if (not url.hostname or url.username or url.password or url.query or url.fragment
                or url.port == 0 or not (url.scheme == "https" or (
                    url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")))):
            raise ValueError()
    except ValueError:
        raise ValueError("Configure an HTTPS APP_URL (HTTP is allowed for loopback development).") from None
    return value.rstrip("/")


def render_review(review: ReviewView, *, app_url: str, environment: str, expanded: bool = False) -> dict:
    app_url = _app_base(app_url)
    if not _TOKEN.fullmatch(review["token"]) or not _int(review["draft_version"], 1, _MAX_VERSION):
        raise ValueError("Invalid stored Telegram review identity.")
    data = review["data"]
    description = _text(data.get("description") or "No description available.", 4000)
    sentences = re.split(r"(?<=[.!?])\s+|(?<=[。！？])\s*", description)
    summary = " ".join(sentence for sentence in sentences[:3] if sentence)
    lines = [_text(data.get("name"), 160), "", _text(summary, 600)]
    names = {c["id"]: c["name"] for c in review["options"]["categories"]}
    categories = ", ".join(names[c] for c in data.get("categories", []) if c in names)
    metadata = []
    if categories:
        metadata.append(f"Category: {_text(categories, 160)}")
    # GitHub collection defaults to Desktop app without verifying software type.
    software_type = data.get("type")
    if software_type and (software_type != "Desktop app" or review["confirmed"].get("type")
                          or "type" in data.get("overrides", [])):
        metadata.append(f"Type: {_text(software_type, 80)}")
    if data.get("platforms"):
        metadata.append(f"Platforms: {_text(', '.join(data['platforms']), 100)}")
    if data.get("costModel") in ("Free", "Free with optional paid features"):
        metadata.append(f"Cost: {_text(data['costModel'], 80)}")
    if data.get("license") and data["license"].lower() not in ("unknown", "none", "noassertion"):
        metadata.append(f"License: {_text(data['license'], 140)}")
    if metadata:
        lines.extend(["", *metadata])
    if expanded:
        names = {c["id"]: c["name"] for c in review["options"]["categories"]}
        categories = ", ".join(names.get(c, c) for c in data.get("categories", [])) or "Unassigned"
        lines = [lines[0], "", _text(description, 1200), "",
                 f"Category: {_text(categories, 160)}",
                 f"Type: {_text(data.get('type'), 80)}",
                 f"Free use: {_text(data.get('costModel'), 80)}",
                 f"License: {_text(data.get('license') or 'Unknown', 140)}",
                 f"Platforms: {_text(', '.join(data.get('platforms', [])) or 'Unknown', 100)}",
                 f"NSFW: {'yes — publication blocked' if data.get('nsfw') else 'no'}",
                 f"Assessment: {_text(json.dumps(review['assessment'], ensure_ascii=False), 600)}",
                 f"Store: {_text(environment, 48)}"]
    keyboard = []
    try:
        repo_url = repository_url(data.get("repoUrl", ""))
    except (InputError, ValueError, TypeError):
        repo_url = None
    if repo_url:
        keyboard.append([{"text": "Open repo", "url": repo_url}])
    if review["status"] == "open":
        keyboard.append([_button(review, "Accept", "accept"), _button(review, "Reject", "reject")])
        keyboard.append([_button(review, "More", "more")])
    else:
        lines.append({"approved": "Accepted and published.", "rejected": "Rejected."}.get(
            review["status"], "Review unavailable. Use /pending for current reviews."))
    return {"text": "\n".join(lines), "reply_markup": {"inline_keyboard": keyboard}}


def _authorized(sender: object, message: object, owner_user_id: int, chat_id: int) -> bool:
    if not isinstance(sender, dict) or not isinstance(message, dict):
        return False
    chat = message.get("chat")
    return (type(sender.get("id")) is int and sender["id"] == owner_user_id
            and isinstance(chat, dict) and type(chat.get("id")) is int
            and chat["id"] == chat_id and chat.get("type") == "private")


class _Stopped(Exception):
    pass


def run_once(client: TelegramClient, *, owner_user_id: int, chat_id: int,
             poller_key: str, app_url: str, environment: str,
             stop_event: threading.Event, assert_active: Callable[[], None],
             poll_timeout: int = 20) -> dict:
    if not _int(owner_user_id) or not _int(chat_id) or not _int(poll_timeout, 0, 20):
        raise ValueError("Telegram requires valid owner/private chat IDs and poll timeout.")
    if not isinstance(poller_key, str) or not re.fullmatch(
        rf"telegram:[1-9][0-9]{{0,15}}:{owner_user_id}:{chat_id}", poller_key, re.ASCII
    ):
        raise ValueError("Telegram polling state must bind the bot, owner and chat IDs.")
    app_url = _app_base(app_url)
    if not isinstance(environment, str) or not environment.strip() or len(environment) > 48:
        raise ValueError("Telegram review requires a bounded environment label.")
    counts = {"updates": 0, "sent": 0}

    def active() -> None:
        if stop_event.is_set():
            raise _Stopped()
        assert_active()

    def mutate(operation: Callable, *args, **kwargs):
        with db.transaction():
            active()
            return operation(*args, **kwargs)

    def call(method: str, payload: dict):
        active()
        return client.call(method, payload)

    identity = {"owner_user_id": owner_user_id, "chat_id": chat_id}

    def send(text: str) -> None:
        call("sendMessage", {"chat_id": chat_id, "text": text,
                             "protect_content": True, "link_preview_options": {"is_disabled": True}})

    def deliver() -> None:
        remaining = 5 - counts["sent"]
        if remaining <= 0:
            return
        pending = mutate(reviews.prepare_reviews, **identity, limit=remaining)
        for review in pending[:remaining]:
            active()
            # A concurrent web decision may invalidate a prepared card before send.
            current = mutate(reviews.get_review, review["token"], **identity)
            if current["status"] != "open" or current["message_id"] is not None:
                continue
            payload = render_review(current, app_url=app_url, environment=environment)
            result = call("sendMessage", {**payload, "chat_id": chat_id,
                                         "protect_content": True, "link_preview_options": {"is_disabled": True}})
            counts["sent"] += 1
            mutate(reviews.mark_delivered, current["token"], result["message_id"], **identity)

    def answer(query_id: str, text: str) -> None:
        try:
            call("answerCallbackQuery", {"callback_query_id": query_id, "text": _text(text, 200)})
        except TelegramError as error:
            if error.code != "callback_expired":
                raise

    def callback(query: dict) -> None:
        message = query.get("message")
        if not _authorized(query.get("from"), message, owner_user_id, chat_id):
            return
        query_id = query.get("id")
        if not isinstance(query_id, str) or not query_id.isascii() or not 1 <= len(query_id) <= 256:
            return
        try:
            token, version, action, value = _parse_callback(query.get("data"))
        except InputError as error:
            answer(query_id, str(error))
            return
        if not _int(message.get("message_id")) or message.get("date") == 0:
            answer(query_id, "This message is unavailable. Use /pending for current reviews.")
            if _int(message.get("message_id")):
                try:
                    mutate(reviews.reset_delivery, token, message["message_id"], **identity)
                except InputError:
                    pass
            return
        # Release Telegram's progress indicator before DB work; expired acknowledgements are harmless.
        answer(query_id, "Reviewing your choice…")
        try:
            result = mutate(reviews.apply_action, token, version, action, value, **identity)
        except InputError:
            send("Review choice unavailable or invalid. Use the current card or /pending.")
            return
        current = result["review"]
        payload = render_review(current, app_url=app_url, environment=environment, expanded=action == "more")
        feedback = {
            "updated": "Choice confirmed. Review the current summary.",
            "approved": "Published. This review is final.",
            "rejected": "Rejected. This review is final.",
            "already_done": "This review already has its final outcome.",
            "stale": "Review changed. Check the current summary before choosing again.",
            "expired": "Review expired. Use /pending for current reviews.",
            "blocked": result["message"],
            "details": "",
        }.get(result["outcome"], "Use the current review card.")
        if feedback:
            payload["text"] += f"\n{feedback}"
        try:
            call("editMessageText", {**payload, "chat_id": chat_id, "message_id": message["message_id"],
                                     "link_preview_options": {"is_disabled": True}})
        except TelegramError as error:
            if error.code == "not_modified":
                return
            if error.code != "message_unavailable":
                raise
            mutate(reviews.reset_delivery, token, message["message_id"], **identity)

    try:
        active()
        deliver()
        active()
        offset = reviews.get_offset(poller_key)
        if not _int(offset, 0):
            raise ValueError("Invalid Telegram polling offset; inspect persisted state.")
        updates = call("getUpdates", {"offset": offset, "limit": 20, "timeout": poll_timeout,
                                      "allowed_updates": ["message", "callback_query"]})
        for update in updates:
            active()
            update_id = update["update_id"]
            if update_id < offset:
                continue
            query = update.get("callback_query")
            message = update.get("message")
            if isinstance(query, dict):
                callback(query)
            elif isinstance(message, dict) and _authorized(message.get("from"), message, owner_user_id, chat_id):
                text = message.get("text")
                if text in ("/start", "/help"):
                    send(f"[{_text(environment, 48)}] {_HELP}")
                elif text == "/pending":
                    deliver()
                    send(f"[{_text(environment, 48)}] Delivered {counts['sent']} review card(s) this iteration (maximum five). Existing cards stay active.")
                else:
                    send("Use /start, /help or /pending, or choose a button on a current review card.")
            mutate(reviews.advance_offset, poller_key, update_id + 1)
            offset = update_id + 1
            counts["updates"] += 1
    except _Stopped:
        pass
    return counts
