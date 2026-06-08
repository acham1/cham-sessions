import json
import os
import urllib.request

API_BASE = "https://api.resend.com"
# Resend's edge blocks the default Python-urllib User-Agent (returns 403), so we
# set an explicit one on every request.
USER_AGENT = "cham-sessions/1.0"


def _get(path: str) -> dict:
    req = urllib.request.Request(
        API_BASE + path,
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_received_email(email_id: str) -> dict:
    """Full inbound email: text/html body, subject, from, attachments metadata."""
    return _get(f"/emails/receiving/{email_id}")


def get_attachment(email_id: str, attachment_id: str) -> dict:
    """Attachment metadata including a short-lived presigned `download_url`."""
    return _get(f"/emails/receiving/{email_id}/attachments/{attachment_id}")


def download(url: str) -> bytes:
    """Download from a presigned URL (no auth header needed)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()
