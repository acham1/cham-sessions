import os
from datetime import datetime, timezone

from google.cloud import firestore


def _db():
    return firestore.Client(project=os.environ.get("GCP_PROJECT"))


def create_pending_episode(episode_id: str, request: dict) -> bool:
    """Create a pending episode keyed by a stable id derived from the inbound
    message. Returns True if newly created, False if it already exists (a
    duplicate webhook delivery), so the caller can skip re-processing.
    """
    doc_ref = _db().collection("episodes").document(episode_id)

    @firestore.transactional
    def _txn(txn):
        snapshot = doc_ref.get(transaction=txn)
        if snapshot.exists:
            return False
        txn.set(
            doc_ref,
            {
                "status": "pending",
                "request": request,
                "created_at": datetime.now(timezone.utc),
                "email_sent": False,
                "email_sent_at": None,
            },
        )
        return True

    return _txn(_db().transaction())
