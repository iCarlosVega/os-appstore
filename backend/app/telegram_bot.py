"""Owner-bound Telegram review UI; runtime supplies configuration and lease checks."""

import json
import re
import threading
import unicodedata
from collections.abc import Callable
from urllib.parse import quote, urlsplit

from . import db, telegram_review as reviews
from .models import InputError, repository_url
from .telegram_api import MAX_ID, TelegramClient, TelegramError
from .telegram_review import ReviewView

_TOKEN = re.compile(r"[A-Za-z0-9_-]{22}", re.ASCII)
_POSITIVE = re.compile(r"[1-9][0-9]{0,9}", re.ASCII)
_INDEX = re.compile(r"0|[1-9][0-9]{0,9}", re.ASCII)
_MAX_VERSION = 2147483647
_HELP = (
    "Select a category, software type and free-use status on each review card; "
    "confirm non-NSFW content, review the versioned summary, then explicitly publish or reject. "
    "Suggestions need your confirmation. /pending delivers up to five unsent reviews per iteration. "
    "/start and /help show these instructions. GitHub sign-in is not required."
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
        valid = action in ("approve", "reject") and value is None
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


def render_review(review: ReviewView, *, app_url: str, environment: str) -> dict:
    app_url = _app_base(app_url)
    data, confirmed, options = review["data"], review["confirmed"], review["options"]
    if not _TOKEN.fullmatch(review["token"]) or not _int(review["draft_version"], 1, _MAX_VERSION):
        raise ValueError("Invalid stored Telegram review identity.")
    names = {option["id"]: option["name"] for option in options["categories"]}
    categories = ", ".join(str(names.get(value, value)) for value in data.get("categories", [])) or "unselected"
    platforms = ", ".join(data.get("platforms", [])) or "unknown"
    assessment = json.dumps(review["assessment"], ensure_ascii=False, separators=(",", ":"))
    status = review["status"]
    lines = [
        f"[{_text(environment, 48)}] Candidate review — {_text(status, 20)}",
        f"Name: {_text(data.get('name'), 160)}",
        f"Repository ID: {_text(review['repo_id'], 32)} · revision {review['candidate_revision']} · draft {review['draft_version']}",
        f"Description (repository text): {_text(data.get('description'), 650) or 'unknown'}",
        f"Repository: {_text(data.get('repoUrl'), 300)}",
        f"License: {_text(data.get('license'), 140) or 'unknown'}",
        f"Platforms: {_text(platforms, 100)}",
        f"Activity: {_text(data.get('lastActivity'), 100) or 'unknown'} · {_text(data.get('condition'), 40)}",
        f"Archived: {'yes' if data.get('archived') else 'no'} · stars: {_text(data.get('stars'), 24)}",
        f"NSFW flag: {'YES — publication blocked' if data.get('nsfw') else 'no'}",
        f"Assessment / uncertainty (snapshot): {_text(assessment, 600)}",
        "Current publication summary:",
        f"Category: {_text(categories, 160)} · {'confirmed' if confirmed.get('category') else 'select to confirm'}",
        f"Type: {_text(data.get('type'), 80)} · {'confirmed' if confirmed.get('type') else 'select to confirm'}",
        f"Free use: {_text(data.get('costModel'), 80)} · {'confirmed' if confirmed.get('cost') else 'select to confirm'}",
        f"Non-NSFW: {'confirmed' if confirmed.get('safe') else 'owner confirmation required'}",
        f"Expires: {_text(review['expires_at'], 40)}",
        "Repository text and assessment are untrusted; buttons below control this review.",
    ]
    keyboard = []
    try:
        repo_url = repository_url(data.get("repoUrl", ""))
    except (InputError, ValueError, TypeError):
        repo_url = None
    if repo_url:
        keyboard.append([{"text": "Open repository", "url": repo_url}])
    if status == "open":
        # shortcut: show at most 60 categories; add versioned pagination if the catalog outgrows this.
        for action, key, prefix in (("category", "categories", "Category"), ("type", "types", "Type"), ("cost", "cost_models", "Cost")):
            limit = 60 if action == "category" else 12
            for index, option in enumerate(options[key][:limit]):
                label = option["name"] if action == "category" else option
                keyboard.append([_button(review, f"{prefix}: {label}", action, str(index))])
            if len(options[key]) > limit:
                lines.append(f"{prefix} choices limited to the first {limit} snapshot options.")
        if not data.get("nsfw"):
            keyboard.append([_button(review, "Confirm non-NSFW content", "safe", "yes")])
        if all(confirmed.get(field) is True for field in ("category", "type", "cost", "safe")) and not data.get("nsfw"):
            lines.append(f"Confirm publication of the summary above for draft {review['draft_version']}. Editing a choice invalidates this confirmation.")
            keyboard.append([_button(review, f"Confirm & publish draft {review['draft_version']}", "approve")])
        else:
            lines.append("Select and confirm every required field to reveal the final publish button.")
        keyboard.append([_button(review, "Reject candidate", "reject")])
    elif status == "approved":
        lines.append("Published. This review is final.")
        slug = review.get("app_slug")
        if isinstance(slug, str) and 1 <= len(slug) <= 200:
            link = f"{app_url}/apps/{quote(slug, safe='')}"
            lines.append(f"App: {_text(link, 300)} (full link below)")
            keyboard.append([{"text": "View published app", "url": link}])
    elif status == "rejected":
        lines.append("Rejected. This review is final.")
    else:
        lines.append("This review is unavailable. /pending requests current unsent reviews.")
    # Reserve room for callback outcome feedback, including astral characters.
    text = "\n".join(lines)
    encoded = text.encode("utf-16-le")
    if len(encoded) > 3800 * 2:
        text = encoded[:3799 * 2].decode("utf-16-le", errors="ignore") + "…"
    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


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
        payload = render_review(current, app_url=app_url, environment=environment)
        feedback = {
            "updated": "Choice confirmed. Review the current summary.",
            "approved": "Published. This review is final.",
            "rejected": "Rejected. This review is final.",
            "already_done": "This review already has its final outcome.",
            "stale": "Review changed. Check the current summary before choosing again.",
            "expired": "Review expired. Use /pending for current reviews.",
            "blocked": "Publication blocked. Check required confirmations, NSFW flag and publication settings.",
        }.get(result["outcome"], "Use the current review card.")
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
