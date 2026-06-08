import logging
import os

from config import load_config

logger = logging.getLogger(__name__)


def send_ack_email(to_email: str, source_hint: str):
    """Reply to the sender confirming we received the request and are working
    on the episode. Best-effort — failures are logged, not raised."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        logger.warning("RESEND_API_KEY not set, skipping ack email")
        return

    import resend

    resend.api_key = api_key
    config = load_config()

    body = f"""<p>Got it — I'm putting together a Cham Sessions episode on:</p>
<blockquote>{source_hint}</blockquote>
<p>It'll show up in your feed shortly. If something goes wrong, you'll get a
heads-up.</p>
<p style="color:#999;font-size:13px;">— {config['name']}</p>"""

    try:
        resend.Emails.send(
            {
                "from": config["from_email"],
                "to": to_email,
                "subject": f"{config['name']}: working on your episode",
                "html": body,
            }
        )
    except Exception:
        logger.exception("Failed to send ack email to %s", to_email)
