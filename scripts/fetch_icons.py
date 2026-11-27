#!/usr/bin/env python3
"""Vendor the brand marks used by the toolbelt.

The icons are the official Simple Icons marks (CC0-1.0, simpleicons.org),
downloaded once and stored in scripts/icons.json so the daily build is
deterministic and works offline.

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
}

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
        svg = fetch(SVG_URL.format(slug=slug), f"{slug}.svg")
        path = re.search(r'<path d="([^"]+)"', svg)
        if not path:
            print(f"  missing path for {slug}", file=sys.stderr)
            continue
        title = re.search(r"<title>([^<]+)</title>", svg)
        hex_colour = OVERRIDES.get(slug)
        if not hex_colour:
            entry = by_title.get(TITLES.get(slug, ""))
            hex_colour = entry.get("hex") if entry else None
        icons[slug] = {
            "slug": slug,
            "title": title.group(1) if title else TITLES.get(slug, slug),
            "hex": hex_colour if hex_colour.startswith("#") else f"#{hex_colour}",
            "path": path.group(1),
        }
        print(f"  {slug:<16} {icons[slug]['title']:<16} {icons[slug]['hex']}")

    OUT.write_text(json.dumps(icons, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.1f} KB, {len(icons)} icons)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
