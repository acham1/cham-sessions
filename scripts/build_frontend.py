#!/usr/bin/env python3
"""Build frontend HTML from config.yaml, replacing {{PLACEHOLDER}} tokens."""

import re
import shutil
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"
FRONTEND_DIR = REPO_ROOT / "frontend"
OUTPUT_DIR = REPO_ROOT / "_site"


def main():
    config = yaml.safe_load(CONFIG_PATH.read_text())

    api_url = (
        f"https://{config['gcp_region']}-{config['gcp_project']}"
        f".cloudfunctions.net/api"
    )

    replacements = {
        "NAME": config["name"],
        "TAGLINE": config["tagline"],
        "DESCRIPTION": config["description"],
        "SITE_URL": config["site_url"],
        "API_URL": api_url,
        "PODCAST_URL": config["podcast_url"],
    }

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()

    token_re = re.compile(r"\{\{(\w+)\}\}")

    for src in FRONTEND_DIR.iterdir():
        dest = OUTPUT_DIR / src.name
        if src.suffix in (".html", ".js"):
            text = src.read_text()
            unreplaced = set()

            def replace(m):
                key = m.group(1)
                if key in replacements:
                    return replacements[key]
                unreplaced.add(key)
                return m.group(0)

            text = token_re.sub(replace, text)
            if unreplaced:
                print(f"ERROR: unreplaced tokens in {src.name}: {unreplaced}")
                sys.exit(1)
            dest.write_text(text)
        else:
            shutil.copy2(src, dest)

    print(f"Built {OUTPUT_DIR} from {FRONTEND_DIR}")


if __name__ == "__main__":
    main()
