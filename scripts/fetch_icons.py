#!/usr/bin/env python3
"""Vendor the brand marks used by the toolbelt and the connect row.

The icons are the official Simple Icons marks (CC0-1.0, simpleicons.org),
downloaded once and stored in scripts/icons.json so the daily build is
deterministic and works offline.

LinkedIn is the one exception: Simple Icons removed every LinkedIn mark for
trademark reasons, so its glyph is taken from Font Awesome Brands 6
(CC BY 4.0, https://fontawesome.com/license/free) and credited below.

    python scripts/fetch_icons.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scripts" / "icons.json"
ICON_DIR = ROOT / "assets" / "icons"
CACHE = Path("/tmp/opencode/icon-cache")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

SVG_URL = "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg"
DATA_URL = "https://cdn.jsdelivr.net/npm/simple-icons@latest/_data/simple-icons.json"

# Brand colour overrides: the official mark colour is unreadable on a dark
# panel for these, so the brand's own accent is used instead.
OVERRIDES = {
    "nextdotjs": "#ffffff",
    "threedotjs": "#ffffff",
    "prisma": "#5A67D8",
    "webgl": "#8AB4F8",
    "gsap": "#0AE448",
    "kalilinux": "#367BF0",
    "github": "#ffffff",
    "tryhackme": "#ffffff",
    "x": "#ffffff",
}

# LinkedIn glyph from Font Awesome Brands 6.0 (CC BY 4.0).
# Copyright Font Awesome Free 6.x by Fonticons, Inc - https://fontawesome.com
LINKEDIN_PATH = (
    "M100.28 448H7.4V148.9h92.88zM53.79 108.1C24.09 108.1 0 83.5 0 53.8a49.79 49.79 0 0 1 "
    "28.17-45.9C47.51 0 71.57 24.6 71.57 54.3c0 29.6-24.1 53.8-53.78 53.8zM447.9 448h-92.68V302.4"
    "c0-34.7-.7-79.2-48.29-79.2-48.29 0-55.69 37.7-55.69 76.7V448H108.9V148.9h88.92v40.8h1.3"
    "a97.6 97.6 0 0 1 87.68-47.28c93.83 0 111.1 61.9 111.1 142.3V448z"
)

# A plain envelope for email - there is no brand mark for a mailbox.
MAIL_PATH = (
    "M2 5.5A2.5 2.5 0 0 1 4.5 3h15A2.5 2.5 0 0 1 22 5.5v13a2.5 2.5 0 0 1-2.5 2.5h-15"
    "A2.5 2.5 0 0 1 2 18.5v-13Zm2.5-.5a.5.5 0 0 0-.5.5v.42l8 5.33 8-5.33v-.42a.5.5 0 0 0-.5-.5h-15Z"
)

# slug -> official Simple Icons title (the data file is keyed by title)
TITLES = {
    "nextdotjs": "Next.js",
    "react": "React",
    "typescript": "TypeScript",
    "tailwindcss": "Tailwind CSS",
    "vite": "Vite",
    "threedotjs": "Three.js",
    "gsap": "GSAP",
    "framer": "Framer",
    "webgl": "WebGL",
    "nodedotjs": "Node.js",
    "python": "Python",
    "postgresql": "PostgreSQL",
    "prisma": "Prisma",
    "postman": "Postman",
    "kalilinux": "Kali Linux",
    "gnubash": "GNU Bash",
    "burpsuite": "Burp Suite",
    "wireshark": "Wireshark",
    "docker": "Docker",
    "github": "GitHub",
    "linkedin": "LinkedIn",
    "instagram": "Instagram",
    "fiverr": "Fiverr",
    "tryhackme": "TryHackMe",
    "whatsapp": "WhatsApp",
    "mail": "Email",
}

SLUGS = list(TITLES)


def fetch(url: str, cache_name: str) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / cache_name
    if not target.exists():
        request = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=60) as response:
            target.write_bytes(response.read())
    return target.read_text(encoding="utf-8")


def main() -> int:
    data = json.loads(fetch(DATA_URL, "simple-icons.json"))
    by_title = {entry["title"]: entry for entry in data}

    icons = {}
    for slug in SLUGS:
        title_text = TITLES.get(slug, slug)
        if slug == "linkedin":
            svg = (
                '<svg role="img" viewBox="0 0 448 512" xmlns="http://www.w3.org/2000/svg">'
                f'<path d="{LINKEDIN_PATH}"/></svg>'
            )
            hex_colour = "#0A66C2"
        elif slug == "mail":
            svg = (
                '<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
                f'<path d="{MAIL_PATH}"/></svg>'
            )
            hex_colour = "#e6edf3"
        else:
            svg = fetch(SVG_URL.format(slug=slug), f"{slug}.svg")
            if not re.search(r'<path d="([^"]+)"', svg):
                print(f"  missing path for {slug}", file=sys.stderr)
                continue
            found = re.search(r"<title>([^<]+)</title>", svg)
            if found:
                title_text = found.group(1)
            hex_colour = OVERRIDES.get(slug)
            if not hex_colour:
                entry = by_title.get(TITLES.get(slug, ""))
                hex_colour = entry.get("hex") if entry else None

        path = re.search(r'<path d="([^"]+)"', svg)
        if not path:
            print(f"  missing path for {slug}", file=sys.stderr)
            continue
        icons[slug] = {
            "slug": slug,
            "title": title_text,
            "hex": hex_colour if hex_colour.startswith("#") else f"#{hex_colour}",
            "path": path.group(1),
        }
        print(f"  {slug:<16} {icons[slug]['title']:<16} {icons[slug]['hex']}")

    OUT.write_text(json.dumps(icons, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.1f} KB, {len(icons)} icons)")
    print("connect tiles are rendered by scripts/build_profile_art.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
