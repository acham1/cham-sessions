import os
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, register_namespace, tostring

from config import load_config

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
# Tell ElementTree to serialize this namespace with the `itunes:` prefix instead
# of an auto-generated `ns0:`. Without this, the `{uri}tag` elements below would
# render as ns0: and ElementTree would emit a second, redundant xmlns line.
register_namespace("itunes", ITUNES_NS)


def _pub_date(value):
    if not value:
        return None
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def build_podcast_rss_xml(episodes: list[dict]) -> str:
    config = load_config()
    site_url = config["site_url"]

    rss = Element("rss", version="2.0")

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = config["name"]
    SubElement(channel, "link").text = site_url
    SubElement(channel, "language").text = "en-us"
    SubElement(channel, "description").text = config["podcast_description"]

    SubElement(channel, f"{{{ITUNES_NS}}}author").text = config["name"]
    SubElement(channel, f"{{{ITUNES_NS}}}summary").text = config["podcast_description"]
    SubElement(channel, f"{{{ITUNES_NS}}}explicit").text = "no"

    image = SubElement(channel, f"{{{ITUNES_NS}}}image")
    image.set("href", config["podcast_cover_url"])

    owner = SubElement(channel, f"{{{ITUNES_NS}}}owner")
    SubElement(owner, f"{{{ITUNES_NS}}}name").text = config["name"]
    SubElement(owner, f"{{{ITUNES_NS}}}email").text = os.environ.get(
        "ADMIN_EMAIL", config["from_email"]
    )

    category = SubElement(channel, f"{{{ITUNES_NS}}}category")
    category.set("text", config["podcast_category"])

    for ep in episodes:
        audio_url = ep.get("audio_url")
        if not audio_url:
            continue

        item = SubElement(channel, "item")
        SubElement(item, "title").text = ep.get("title", "Untitled")
        SubElement(item, f"{{{ITUNES_NS}}}author").text = config["name"]
        SubElement(item, f"{{{ITUNES_NS}}}explicit").text = "no"

        source = ep.get("source") or {}
        source_url = source.get("url")
        source_title = source.get("title") or ""
        # Link to the original source if we have one, else the episode page.
        episode_page = f"{site_url}/episode.html?id={ep.get('id', '')}"
        SubElement(item, "link").text = source_url or episode_page
        SubElement(item, "guid").text = audio_url

        description = ep.get("description", "")
        if source_title:
            description = f"Discussing: {source_title}\n\n{description}"
        SubElement(item, "description").text = description

        enclosure = SubElement(item, "enclosure")
        enclosure.set("url", audio_url)
        enclosure.set("type", "audio/mpeg")
        enclosure.set("length", str(ep.get("audio_size_bytes", 0)))

        secs = ep.get("audio_duration_secs", 0)
        minutes, sec = divmod(secs, 60)
        hours, minutes = divmod(minutes, 60)
        dur = f"{hours}:{minutes:02d}:{sec:02d}" if hours else f"{minutes}:{sec:02d}"
        SubElement(item, f"{{{ITUNES_NS}}}duration").text = dur

        pub = _pub_date(ep.get("published_at") or ep.get("created_at"))
        if pub:
            SubElement(item, "pubDate").text = pub

    xml_str = tostring(rss, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
