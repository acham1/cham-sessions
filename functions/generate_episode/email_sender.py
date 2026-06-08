import logging
import os

import resend

from config import load_config
from email_template import render_email

logger = logging.getLogger(__name__)


def send_episode_email(subscribers: list[dict], episode: dict, episode_id: str):
    config = load_config()
    resend.api_key = os.environ["RESEND_API_KEY"]
    from_email = config["from_email"]
    site_url = config["site_url"]

    subject = f"{config['name']}: {episode.get('title', 'New episode')}"

    for sub in subscribers:
        html = render_email(episode, episode_id, sub["unsubscribe_token"], site_url)
        try:
            resend.Emails.send(
                {
                    "from": from_email,
                    "to": sub["email"],
                    "subject": subject,
                    "html": html,
                }
            )
        except Exception:
            logger.exception("Failed to send email to %s", sub["email"])
