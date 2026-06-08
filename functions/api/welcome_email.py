import logging
import os

import resend

from config import load_config
from firestore_client import get_latest_episode

logger = logging.getLogger(__name__)


def send_welcome_email(email: str):
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        logger.warning("RESEND_API_KEY not set, skipping welcome email")
        return

    config = load_config()
    resend.api_key = api_key
    from_email = config["from_email"]
    site_url = config["site_url"]
    name = config["name"]

    episode = get_latest_episode()

    body = f"""<h2>Welcome to {name}!</h2>
<p>{config['description']}</p>"""

    if episode:
        episode_url = f"{site_url}/episode.html?id={episode['id']}"
        body += f"""<hr>
<p>Here's the latest episode to get you started:</p>
<h3>{episode.get('title', 'Untitled')}</h3>
<p><em>{episode.get('description', '')}</em></p>
<p><a href="{episode_url}">Open the episode</a></p>"""

    try:
        resend.Emails.send(
            {
                "from": from_email,
                "to": email,
                "subject": f"Welcome to {name}!",
                "html": body,
            }
        )
    except Exception:
        logger.exception("Failed to send welcome email to %s", email)
