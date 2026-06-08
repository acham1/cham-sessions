from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring

from config import load_config


def _pub_date(value) -> str | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def build_rss_xml(episodes: list[dict]) -> str:
    config = load_config()
    site_url = config["site_url"]

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = config["name"]
    SubElement(channel, "link").text = site_url
    SubElement(channel, "description").text = config["description"]
    SubElement(channel, "language").text = "en-us"

    for ep in episodes:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = ep.get("title", "Untitled")

        link = f"{site_url}/episode.html?id={ep.get('id', '')}"
        SubElement(item, "link").text = link
        SubElement(item, "guid").text = link

        SubElement(item, "description").text = ep.get("description", "")

        pub = _pub_date(ep.get("published_at") or ep.get("created_at"))
        if pub:
            SubElement(item, "pubDate").text = pub

    xml_str = tostring(rss, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
