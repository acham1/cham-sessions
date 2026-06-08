import os
from datetime import datetime, timezone

from google.cloud import firestore


def _db():
    return firestore.Client(project=os.environ.get("GCP_PROJECT"))


def get_episode(episode_id: str) -> dict | None:
    doc = _db().collection("episodes").document(episode_id).get()
    if not doc.exists:
        return None
    d = doc.to_dict()
    d["id"] = doc.id
    return d


def update_episode(episode_id: str, data: dict):
    _db().collection("episodes").document(episode_id).update(data)


def set_status(episode_id: str, status: str, error: str | None = None):
    update = {"status": status}
    if error is not None:
        update["error"] = error
    if status == "published":
        update["published_at"] = datetime.now(timezone.utc)
    _db().collection("episodes").document(episode_id).update(update)


def get_subscribers() -> list[dict]:
    docs = _db().collection("subscribers").where("active", "==", True).stream()
    return [doc.to_dict() for doc in docs]


def mark_email_sent(episode_id: str):
    _db().collection("episodes").document(episode_id).update(
        {
            "email_sent": True,
            "email_sent_at": datetime.now(timezone.utc),
        }
    )
