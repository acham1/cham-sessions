import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import functions_framework

_secrets_path = Path("/etc/secrets/.env")
if _secrets_path.exists():
    for line in _secrets_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from google.cloud import pubsub_v1, storage

import resend_api
from config import load_config
from email_sender import send_ack_email
from firestore_client import create_pending_episode

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

EMAIL_IN_ANGLE = re.compile(r"<([^>]+)>")


def _extract_email(raw_from: str) -> str:
    """Pull a bare address out of a 'Display Name <addr@host>' style header."""
    if not raw_from:
        return ""
    m = EMAIL_IN_ANGLE.search(raw_from)
    addr = m.group(1) if m else raw_from
    return addr.strip().lower()


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _recipients(data: dict) -> set:
    """All addresses the message was sent to (to + cc + bcc), normalized."""
    addrs = set()
    for field in ("to", "cc", "bcc"):
        for raw in data.get(field) or []:
            addr = _extract_email(raw)
            if addr:
                addrs.add(addr)
    return addrs


def _verify_signature(request) -> bool:
    """Verify the Resend (Svix-backed) webhook signature. Returns True if valid
    or if no secret is configured (with a warning)."""
    secret = os.environ.get("RESEND_WEBHOOK_SECRET")
    if not secret:
        logger.warning("RESEND_WEBHOOK_SECRET not set — skipping signature check")
        return True

    try:
        from svix.webhooks import Webhook, WebhookVerificationError
    except ImportError:
        logger.warning("svix not installed — skipping signature check")
        return True

    headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }
    try:
        Webhook(secret).verify(request.get_data(), headers)
        return True
    except WebhookVerificationError:
        logger.warning("Webhook signature verification failed")
        return False


def _episode_id(message_id: str) -> str:
    return hashlib.sha256(message_id.encode()).hexdigest()[:24]


def _stash_attachments(
    email_id: str, attachments_meta: list, episode_id: str, bucket_name: str
) -> list:
    """For each attachment, fetch its presigned download_url from the Resend API,
    download the bytes, and upload to GCS. Returns metadata records."""
    if not attachments_meta:
        return []

    bucket = storage.Client().bucket(bucket_name)
    records = []
    for att in attachments_meta:
        attachment_id = att.get("id")
        if not attachment_id:
            continue
        filename = att.get("filename") or f"attachment-{attachment_id}"
        content_type = att.get("content_type") or ""
        try:
            detail = resend_api.get_attachment(email_id, attachment_id)
            blob_bytes = resend_api.download(detail["download_url"])
        except Exception:
            logger.exception("Failed to fetch attachment %s", filename)
            continue

        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
        path = f"inbound/{episode_id}/{safe_name}"
        bucket.blob(path).upload_from_string(blob_bytes, content_type=content_type)
        records.append(
            {
                "filename": filename,
                "content_type": content_type,
                "gcs_uri": f"gs://{bucket_name}/{path}",
                "size_bytes": len(blob_bytes),
            }
        )
        logger.info("Stashed attachment %s (%d bytes)", path, len(blob_bytes))
    return records


@functions_framework.http
def inbound(request):
    if request.method != "POST":
        return ("method not allowed", 405)

    if not _verify_signature(request):
        return ("invalid signature", 401)

    payload = request.get_json(silent=True) or {}
    logger.info("Inbound event type: %s", payload.get("type"))
    data = payload.get("data") or payload

    config = load_config()

    sender = _extract_email(data.get("from", ""))
    # Allowlist lives in the ALLOWED_SENDERS secret (comma-separated) to keep
    # personal emails out of the public repo; fall back to config for local use.
    env_senders = os.environ.get("ALLOWED_SENDERS", "")
    allowed = {s.strip().lower() for s in env_senders.split(",") if s.strip()}
    if not allowed:
        allowed = {s.lower() for s in config.get("allowed_senders", [])}
    if allowed and sender not in allowed:
        # Accept (200) so Resend doesn't retry, but do nothing.
        logger.warning("Dropping email from non-allowlisted sender: %s", sender)
        return ("ignored", 200)

    inbound_address = config.get("inbound_address", "").strip().lower()
    if inbound_address and inbound_address not in _recipients(data):
        logger.warning(
            "Dropping email not addressed to %s (recipients: %s)",
            inbound_address,
            _recipients(data),
        )
        return ("ignored", 200)

    email_id = data.get("email_id")
    if not email_id:
        logger.error("No email_id in webhook payload")
        return ("bad request", 400)

    message_id = data.get("message_id") or email_id
    episode_id = _episode_id(message_id)

    # The webhook carries only metadata — fetch the full email for the body and
    # the authoritative attachment list.
    subject = (data.get("subject") or "").strip()
    body_text = ""
    attachments_meta = data.get("attachments") or []
    try:
        email = resend_api.get_received_email(email_id)
        subject = (email.get("subject") or subject).strip()
        body_text = (email.get("text") or "").strip()
        if not body_text and email.get("html"):
            body_text = _strip_html(email["html"])
        attachments_meta = email.get("attachments") or attachments_meta
    except Exception:
        logger.exception("Failed to fetch received email %s (using metadata)", email_id)

    attachments = _stash_attachments(
        email_id, attachments_meta, episode_id, config["podcast_bucket"]
    )

    request_record = {
        "sender": sender,
        "subject": subject,
        "body_text": body_text,
        "attachments": attachments,
        "email_id": email_id,
        "message_id": message_id,
        "received_at": datetime.now(timezone.utc),
    }

    created = create_pending_episode(episode_id, request_record)
    if not created:
        logger.info("Episode %s already exists, skipping (duplicate)", episode_id)
        return ("duplicate", 200)

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(config["gcp_project"], config["topic"])
    publisher.publish(
        topic_path, json.dumps({"episode_id": episode_id}).encode()
    ).result(timeout=30)
    logger.info("Published episode job %s", episode_id)

    source_hint = subject or (body_text[:120] + "…" if body_text else "your request")
    send_ack_email(sender, source_hint)

    return ("accepted", 202)
