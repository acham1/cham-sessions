import hashlib
import hmac
import os
from datetime import datetime, timezone

from google.cloud import firestore


def _db():
    return firestore.Client(project=os.environ.get("GCP_PROJECT"))


def add_subscriber(email: str) -> str:
    db = _db()
    existing = list(
        db.collection("subscribers").where("email", "==", email).limit(1).stream()
    )
    if existing:
        doc = existing[0]
        if not doc.to_dict().get("active", True):
            doc.reference.update({"active": True})
            return "resubscribed"
        return "already_subscribed"

    secret = os.environ["UNSUBSCRIBE_SECRET"]
    token = hmac.new(secret.encode(), email.encode(), hashlib.sha256).hexdigest()
    db.collection("subscribers").add(
        {
            "email": email,
            "subscribed_at": datetime.now(timezone.utc),
            "unsubscribe_token": token,
            "active": True,
        }
    )
    return "subscribed"


def remove_subscriber(token: str) -> bool:
    db = _db()
    docs = list(
        db.collection("subscribers")
        .where("unsubscribe_token", "==", token)
        .limit(1)
        .stream()
    )
    if not docs:
        return False
    docs[0].reference.update({"active": False})
    return True


def _clean_list_item(d: dict) -> dict:
    """Trim a full episode doc down to what list/card views need."""
    for key in ("turns", "request", "error"):
        d.pop(key, None)
    for key in ("created_at", "published_at"):
        if key in d and hasattr(d[key], "isoformat"):
            d[key] = d[key].isoformat()
    return d


def list_episodes(limit: int = 20, start_after: str | None = None) -> list[dict]:
    db = _db()
    # Over-fetch slightly so filtering out unpublished docs still fills a page.
    q = (
        db.collection("episodes")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit * 2)
    )
    if start_after:
        doc = db.collection("episodes").document(start_after).get()
        if doc.exists:
            q = q.start_after(doc)

    results = []
    for doc in q.stream():
        d = doc.to_dict()
        if d.get("status") != "published":
            continue
        d["id"] = doc.id
        results.append(_clean_list_item(d))
        if len(results) >= limit:
            break
    return results


def get_latest_episode() -> dict | None:
    episodes = list_episodes(limit=1)
    return episodes[0] if episodes else None


def get_episode(episode_id: str) -> dict | None:
    doc = _db().collection("episodes").document(episode_id).get()
    if not doc.exists:
        return None
    d = doc.to_dict()
    if d.get("status") != "published":
        return None
    d["id"] = doc.id
    d.pop("request", None)
    for key in ("created_at", "published_at"):
        if key in d and hasattr(d[key], "isoformat"):
            d[key] = d[key].isoformat()
    return d


def episodes_for_feed(limit: int = 50) -> list[dict]:
    """Published episodes that have audio, newest first, full docs."""
    db = _db()
    q = (
        db.collection("episodes")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit * 2)
    )
    results = []
    for doc in q.stream():
        d = doc.to_dict()
        if d.get("status") != "published" or not d.get("audio_url"):
            continue
        d["id"] = doc.id
        results.append(d)
        if len(results) >= limit:
            break
    return results
