import logging
import os

import resend

from config import load_config

logger = logging.getLogger(__name__)


def send_confirmation_email(email: str, confirm_token: str):
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        logger.warning("RESEND_API_KEY not set, skipping confirmation email")
        return

    config = load_config()
    resend.api_key = api_key
    from_email = config["from_email"]
    site_url = config["site_url"]
    name = config["name"]

    confirm_url = f"{site_url}/confirm.html?token={confirm_token}"

    body = f"""<h2>Confirm your subscription to {name}</h2>
<p>Click the button below to confirm your email address and start receiving
new {name} episodes as they're published.</p>
<p style="text-align:center;margin:24px 0;">
<a href="{confirm_url}"
   style="display:inline-block;background:#1a1a2e;color:#ffffff;
          padding:12px 28px;text-decoration:none;border-radius:4px;
          font-size:15px;">Confirm subscription</a>
</p>
<p style="color:#999;font-size:13px;">If you didn't sign up, you can safely
ignore this email.</p>"""

    try:
        resend.Emails.send(
            {
                "from": from_email,
                "to": email,
                "subject": f"Confirm your subscription to {name}",
                "html": body,
            }
        )
    except Exception:
        logger.exception("Failed to send confirmation email to %s", email)
