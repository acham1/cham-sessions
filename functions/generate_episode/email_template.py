import html

from config import load_config


def _format_duration(secs: int) -> str:
    if not secs:
        return ""
    minutes, _ = divmod(secs, 60)
    return f"{minutes} min" if minutes else "<1 min"


def render_email(
    episode: dict, episode_id: str, unsub_token: str, site_url: str
) -> str:
    config = load_config()
    title = html.escape(episode.get("title", "New episode"))
    description = html.escape(episode.get("description", ""))

    source = episode.get("source") or {}
    source_title = html.escape(source.get("title") or "")
    source_url = source.get("url")
    source_line = ""
    if source_title:
        if source_url:
            source_line = (
                f'Discussing: <a href="{html.escape(source_url)}">{source_title}</a>'
            )
        else:
            source_line = f"Discussing: {source_title}"

    audio_url = episode.get("audio_url")
    duration = _format_duration(episode.get("audio_duration_secs", 0))
    fmt = html.escape((episode.get("format") or "").title())

    episode_url = f"{site_url}/episode.html?id={episode_id}"
    unsub_url = f"{site_url}/unsubscribe.html?token={unsub_token}"
    archive_url = f"{site_url}/archive.html"

    listen_btn = (
        f'<a href="{audio_url}" style="display:inline-block;background:#fff;'
        f"color:#1a1a2e;padding:12px 28px;text-decoration:none;border-radius:4px;"
        f'font-size:15px;border:1px solid #1a1a2e;">Listen now</a>'
        if audio_url
        else ""
    )

    meta_bits = " · ".join(b for b in [fmt, duration] if b)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;">
<tr><td align="center" style="padding:20px 10px;">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;">

<tr><td style="background:#1a1a2e;padding:24px 32px;">
<h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:600;">{config["name"]}</h1>
</td></tr>

<tr><td style="padding:32px 32px 8px;">
<h2 style="margin:0 0 8px;color:#1a1a2e;font-size:24px;">{title}</h2>
<p style="margin:0;color:#999;font-size:13px;text-transform:uppercase;letter-spacing:.04em;">{meta_bits}</p>
</td></tr>

<tr><td style="padding:8px 32px 0;">
<p style="margin:0;color:#333;font-size:16px;line-height:1.6;">{description}</p>
{f'<p style="margin:12px 0 0;color:#666;font-size:14px;">{source_line}</p>' if source_line else ''}
</td></tr>

<tr><td align="center" style="padding:28px 32px;">
<a href="{episode_url}" style="display:inline-block;background:#1a1a2e;color:#ffffff;padding:12px 28px;text-decoration:none;border-radius:4px;font-size:15px;">Open episode</a>
{f'&nbsp;&nbsp;{listen_btn}' if listen_btn else ''}
</td></tr>

<tr><td style="background:#f9f9f9;padding:20px 32px;border-top:1px solid #eee;">
<p style="margin:0;color:#999;font-size:13px;text-align:center;">
<a href="{archive_url}" style="color:#666;">Browse all episodes</a>
&nbsp;&middot;&nbsp;
<a href="{unsub_url}" style="color:#666;">Unsubscribe</a>
</p>
<p style="margin:8px 0 0;color:#bbb;font-size:12px;text-align:center;">
By {config["host_name"]} &middot;
<a href="{config["host_linkedin"]}" style="color:#999;">LinkedIn</a> &middot;
<a href="{config["host_github"]}" style="color:#999;">GitHub</a> &middot;
<a href="mailto:{config["host_email"]}" style="color:#999;">{config["host_email"]}</a>
</p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""
