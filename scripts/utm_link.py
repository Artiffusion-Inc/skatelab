#!/usr/bin/env python3
"""Generate UTM-tagged URLs for social media links.

Usage:
    python scripts/utm_link.py --source tiktok --campaign build_in_public --content v_2026_05_24
    python scripts/utm_link.py --source telegram --campaign channel --content post_2026_05_24
"""

import argparse
from urllib.parse import urlencode

BASE_URL = "https://skatelab.ru"


def build_utm_url(
    source: str, campaign: str, content: str | None = None, medium: str = "organic"
) -> str:
    params = {
        "utm_source": source,
        "utm_medium": medium,
        "utm_campaign": campaign,
    }
    if content:
        params["utm_content"] = content
    return f"{BASE_URL}?{urlencode(params)}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate UTM-tagged URLs")
    parser.add_argument(
        "--source", required=True, help="Traffic source (tiktok, telegram, whatsapp)"
    )
    parser.add_argument("--campaign", required=True, help="Campaign name")
    parser.add_argument("--content", default=None, help="Content identifier (video id, post id)")
    parser.add_argument("--medium", default="organic", help="Medium (default: organic)")
    parser.add_argument("--path", default="/", help="URL path (default: /)")
    args = parser.parse_args()

    url = build_utm_url(args.source, args.campaign, args.content, args.medium)
    if args.path != "/":
        url = url.replace(f"{BASE_URL}?", f"{BASE_URL}{args.path}?")
    print(url)  # noqa: T201


if __name__ == "__main__":
    main()
