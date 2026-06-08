import hashlib
import hmac
import os
from datetime import datetime, timezone

from google.cloud import firestore


def _db():
    return firestore.Client(project=os.environ.get("GCP_PROJECT"))


def add_subscriber(email: str) -> tuple[str, str]:
    """Add (or re-activate) a subscriber as UNCONFIRMED. Returns
    (status, confirmation_token). Double opt-in: the subscriber must click the
    confirmation link before they're emailed episodes."""
    db = _db()
    existing = list(
        db.collection("subscribers").where("email", "==", email).limit(1).stream()
    )
    secret = os.environ["UNSUBSCRIBE_SECRET"]

    if existing:
        doc = existing[0]
        data = doc.to_dict()
        if data.get("confirmed") and data.get("active"):
            return "already_subscribed", ""
        if not data.get("active"):
            confirm_token = hmac.new(
                secret.encode(), f"confirm:{email}".encode(), hashlib.sha256
            ).hexdigest()
            doc.reference.update(
                {
                    "active": True,
                    "confirmed": False,
                    "confirmation_token": confirm_token,
                }
            )
            return "pending_confirmation", confirm_token
        return "pending_confirmation", data.get("confirmation_token", "")

    unsub_token = hmac.new(secret.encode(), email.encode(), hashlib.sha256).hexdigest()
    confirm_token = hmac.new(
        secret.encode(), f"confirm:{email}".encode(), hashlib.sha256
    ).hexdigest()
    db.collection("subscribers").add(
        {
            "email": email,
            "subscribed_at": datetime.now(timezone.utc),
            "unsubscribe_token": unsub_token,
            "confirmation_token": confirm_token,
            "confirmed": False,
            "active": True,
        }
    )
    return "pending_confirmation", confirm_token


def confirm_subscriber(token: str) -> bool:
    db = _db()
    docs = list(
        db.collection("subscribers")
        .where("confirmation_token", "==", token)
        .limit(1)
        .stream()
    )
    if not docs:
        return False
    docs[0].reference.update({"confirmed": True})
    return True


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
