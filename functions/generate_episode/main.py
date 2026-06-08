import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import functions_framework
from cloudevents.http import CloudEvent

_secrets_path = Path("/etc/secrets/.env")
if _secrets_path.exists():
    for line in _secrets_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from config import load_config
from email_sender import send_episode_email
from firestore_client import (
    get_episode,
    get_subscribers,
    mark_email_sent,
    set_status,
    update_episode,
)
from ingest import prepare_request
from podcast_generator import generate_episode_audio
from script_writer import write_script

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)


def _send_error_alert(episode_id: str, error: Exception, sender: str | None):
    resend_key = os.environ.get("RESEND_API_KEY")
    if not resend_key:
        return
    import resend

    resend.api_key = resend_key
    config = load_config()
    recipients = [r for r in {os.environ.get("ADMIN_EMAIL"), sender} if r]
    if not recipients:
        return
    try:
        resend.Emails.send(
            {
                "from": config["from_email"],
                "to": recipients,
                "subject": f"{config['name']}: episode generation failed",
                "html": (
                    f"<p>Episode <code>{episode_id}</code> failed to generate.</p>"
                    f"<pre>{error.__class__.__name__}: {error}</pre>"
                ),
            }
        )
    except Exception:
        logger.exception("Failed to send error alert")


@functions_framework.cloud_event
def generate_episode(cloud_event: CloudEvent) -> None:
    raw = cloud_event.data["message"].get("data")
    payload = json.loads(base64.b64decode(raw).decode()) if raw else {}
    episode_id = payload.get("episode_id")
    if not episode_id:
        logger.error("No episode_id in message, ignoring")
        return

    episode_doc = get_episode(episode_id)
    sender = (episode_doc or {}).get("request", {}).get("sender")
    try:
        _generate(episode_id, episode_doc)
    except Exception as e:
        logger.exception("Episode generation failed")
        set_status(episode_id, "failed", error=str(e))
        _send_error_alert(episode_id, e, sender)
        raise


def _generate(episode_id: str, episode_doc: dict | None):
    if not episode_doc:
        logger.error("Episode %s not found", episode_id)
        return
    if episode_doc.get("status") not in ("pending", "failed"):
        logger.info(
            "Episode %s already in status %s, skipping",
            episode_id,
            episode_doc.get("status"),
        )
        return

    set_status(episode_id, "generating")
    request = episode_doc.get("request", {})

    prepared = prepare_request(request)
    logger.info(
        "Prepared request: subject=%r, %d file(s)",
        prepared.get("subject"),
        len(prepared.get("files", [])),
    )

    episode = write_script(prepared)
    logger.info(
        "Wrote %s episode '%s' with %d turns",
        episode.get("format"),
        episode.get("title"),
        len(episode.get("turns", [])),
    )

    update_episode(
        episode_id,
        {
            "title": episode.get("title"),
            "description": episode.get("description", ""),
            "format": episode.get("format"),
            "source": episode.get("source", {}),
            "speakers": episode.get("speakers", []),
            "turns": episode.get("turns", []),
            "script_generated_at": datetime.now(timezone.utc),
        },
    )

    audio = generate_episode_audio(episode, episode_id)
    update_episode(
        episode_id,
        {
            "audio_url": audio["audio_url"],
            "audio_duration_secs": audio["duration_secs"],
            "audio_size_bytes": audio["size_bytes"],
            "audio_model": audio["model"],
            "audio_generated_at": datetime.now(timezone.utc),
        },
    )
    episode["audio_url"] = audio["audio_url"]
    episode["audio_duration_secs"] = audio["duration_secs"]
    logger.info("Generated audio: %s", audio["audio_url"])

    set_status(episode_id, "published")

    subscribers = get_subscribers()
    if subscribers:
        send_episode_email(subscribers, episode, episode_id)
        mark_email_sent(episode_id)
        logger.info("Emailed %d subscribers", len(subscribers))
    else:
        logger.info("No subscribers, skipping email")
