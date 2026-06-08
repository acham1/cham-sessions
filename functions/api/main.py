import os
import re
import time
from collections import defaultdict
from pathlib import Path

import functions_framework
from flask import Response, jsonify

_secrets_path = Path("/etc/secrets/.env")
if _secrets_path.exists():
    for line in _secrets_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from config import load_config
from firestore_client import (
    add_subscriber,
    episodes_for_feed,
    get_episode,
    list_episodes,
    remove_subscriber,
)
from welcome_email import send_welcome_email

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# --- Rate limiting on subscribe (per-instance, in-memory) ---
_subscribe_attempts = defaultdict(list)
_RATE_LIMIT = 3
_RATE_WINDOW = 3600


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    _subscribe_attempts[ip] = [
        t for t in _subscribe_attempts[ip] if now - t < _RATE_WINDOW
    ]
    if len(_subscribe_attempts[ip]) >= _RATE_LIMIT:
        return True
    _subscribe_attempts[ip].append(now)
    return False


# --- Feed response cache (per-instance, TTL-based) — shields Firestore from
# scrapers/refresh storms; new episodes appear within _CACHE_TTL seconds. ---
_cache = {}
_CACHE_TTL = 300


def _cached(key: str, builder):
    now = time.time()
    if key in _cache and now - _cache[key][1] < _CACHE_TTL:
        return _cache[key][0]
    result = builder()
    _cache[key] = (result, now)
    return result


def _cors_headers():
    config = load_config()
    return {
        "Access-Control-Allow-Origin": config["site_url"],
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _respond(data, status=200):
    return (jsonify(data), status, _cors_headers())


@functions_framework.http
def api(request):
    if request.method == "OPTIONS":
        return ("", 204, _cors_headers())

    path = request.path.rstrip("/")
    method = request.method

    if path == "/subscribe" and method == "POST":
        return _handle_subscribe(request)
    elif path == "/unsubscribe" and method == "GET":
        return _handle_unsubscribe(request)
    elif path == "/feed.xml" and method == "GET":
        return _handle_feed()
    elif path == "/podcast.xml" and method == "GET":
        return _handle_podcast_feed()
    elif path == "/episodes" and method == "GET":
        return _handle_list_episodes(request)
    elif path.startswith("/episodes/") and method == "GET":
        episode_id = path.split("/episodes/", 1)[1]
        return _handle_get_episode(episode_id)
    else:
        return _respond({"error": "not found"}, 404)


def _handle_subscribe(request):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or ""
    ip = ip.split(",")[0].strip()
    if _is_rate_limited(ip):
        return _respond({"error": "too many requests, try again later"}, 429)

    data = request.get_json(silent=True)
    if not data or "email" not in data:
        return _respond({"error": "email required"}, 400)

    email = data["email"].strip().lower()
    if not EMAIL_RE.match(email):
        return _respond({"error": "invalid email"}, 400)

    status = add_subscriber(email)
    if status == "subscribed":
        send_welcome_email(email)
    return _respond({"status": status})


def _handle_unsubscribe(request):
    token = request.args.get("token", "")
    if not token:
        return _respond({"error": "token required"}, 400)

    if remove_subscriber(token):
        return _respond({"status": "unsubscribed"})
    return _respond({"error": "not found"}, 404)


def _handle_list_episodes(request):
    limit = min(int(request.args.get("limit", "20")), 50)
    start_after = request.args.get("start_after")
    episodes = list_episodes(limit=limit, start_after=start_after)
    return _respond({"episodes": episodes})


def _handle_get_episode(episode_id):
    episode = get_episode(episode_id)
    if not episode:
        return _respond({"error": "not found"}, 404)
    return _respond(episode)


def _handle_feed():
    from feed import build_rss_xml

    def _build():
        return build_rss_xml(episodes_for_feed(limit=50))

    xml = _cached("feed", _build)
    return Response(
        xml, content_type="application/rss+xml; charset=utf-8", headers=_cors_headers()
    )


def _handle_podcast_feed():
    from podcast_feed import build_podcast_rss_xml

    def _build():
        return build_podcast_rss_xml(episodes_for_feed(limit=50))

    xml = _cached("podcast_feed", _build)
    return Response(
        xml, content_type="application/rss+xml; charset=utf-8", headers=_cors_headers()
    )
