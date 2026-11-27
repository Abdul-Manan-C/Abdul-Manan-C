#!/usr/bin/env python3
"""A/B the repository-index table against the squint test.

The full repo table was the heaviest block on the page - heavier than the
hero. This script renders candidate table treatments through the real GitHub
markdown pipeline and measures each one, so the choice is made on numbers
instead of opinion.

    python scripts/exp_repo_table.py
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = Path("/tmp/opencode/readme-shots/exp")
PORT = 8734
BG = (13, 17, 23)

GITHUB_CSS = (ROOT / "scripts" / "verify_readme.py").read_text(encoding="utf-8").split('GITHUB_CSS = """')[1].split('"""')[0]


def render_markdown(text: str) -> str:
    payload = json.dumps({"text": text, "mode": "gfm"}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/vnd.github+json",
               "User-Agent": "readme-exp"}
    token = os.environ.get("GITHUB_PAT")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request("https://api.github.com/markdown", data=payload, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def edge_rows(im: Image.Image) -> list[int]:
    gray = im.convert("L")
    w, h = gray.size
    px = gray.load()
    out = []
    for y in range(h):
        total = 0
        for x in range(w):
            right = px[x + 1, y] if x + 1 < w else px[x, y]
            down = px[x, y + 1] if y + 1 < h else px[x, y]
            total += abs(px[x, y] - right) + abs(px[x, y] - down)
        out.append(total)
    return out


def measure(name: str, markdown: str, server_dir: Path) -> dict:
    html = render_markdown(markdown)
    page = server_dir / "index.html"
    page.write_text(
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<style>{GITHUB_CSS}</style></head><body>"
        f"<div id='wrap' class='markdown-body'>{html}</div></body></html>",
        encoding="utf-8")

    env = dict(os.environ, CDP_WINDOW="900,7000")
    shot = OUT / f"{name}.png"
    subprocess.run(
        ["google-chrome", "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
         "--force-device-scale-factor=1", "--window-size=900,7000", f"--screenshot={shot}",
         "--virtual-time-budget=20000", f"http://127.0.0.1:{PORT}/index.html"],
        capture_output=True, text=True, timeout=180)

    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "cdp_eval.mjs"), f"http://127.0.0.1:{PORT}/index.html",
         str(ROOT / "scripts" / "readme-sections.js"), "10000"],
        capture_output=True, text=True, timeout=180, env=env)
    data = json.loads(result.stdout)
    blocks = data["blocks"]

    im = Image.open(shot).convert("RGB")
    rows = edge_rows(im)
    total = sum(rows) or 1

    tables = [b for b in blocks if "table" in b["tag"]]
    table = next((b for b in tables if b["text"].startswith("Repository")), None) or (tables[-1] if tables else None)
    hero = next((b for b in blocks if b["imgs"] and any("hero" in i["src"] for i in b["imgs"])), None)
    gallery = next((b for b in blocks if b["imgs"] and any("laxitech" in i["src"] for i in b["imgs"])), None)

    def energy(b):
        if not b:
            return 0.0, 0
        top, bot = max(0, b["top"]), min(len(rows), b["bottom"])
        return 100 * sum(rows[top:bot]) / total, bot - top

    table_pct, table_h = energy(table)
    hero_pct, _ = energy(hero)
    gallery_pct, _ = energy(gallery)
    return {
        "name": name,
        "page_height": max((b["bottom"] for b in blocks), default=0),
        "table_top": table["top"] if table else None,
        "table_height": table_h,
        "table_detail": table_pct,
        "hero_detail": hero_pct,
        "gallery_detail": gallery_pct,
        "ratio": (table_pct / hero_pct) if hero_pct else 0,
        "blocks": blocks,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"<!-- AUTO:REPOS:START -->.*?<!-- AUTO:REPOS:END -->", source, re.S)
    if not match:
        print("error: auto repo block not found", file=sys.stderr)
        return 1
    current = match.group(0)
    body = current.split("-->", 1)[1].rsplit("<!--", 1)[0].strip()

    def trim_description(text: str, limit: int = 58) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= limit:
            return text
        cut = text[:limit].rsplit(" ", 1)[0]
        return cut.rstrip(" ,;:-") + "…"

    def variant_compact() -> str:
        """Four columns, one-line descriptions."""
        lines = ["| Repository | What it is | ★ | Pushed |", "|---|---|---|---|"]
        for row in body.splitlines()[2:]:
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if len(cells) < 5:
                continue
            lines.append(f"| {cells[0]} | {trim_description(cells[1])} | {cells[3]} | {cells[4]} |")
        return "<!-- AUTO:REPOS:START -->\n" + "\n".join(lines) + "\n<!-- AUTO:REPOS:END -->"

    def variant_details() -> str:
        """The same table, folded behind a summary."""
        return (
            "<!-- AUTO:REPOS:START -->\n"
            "<details>\n<summary>All 14 public repositories</summary>\n\n"
            + body + "\n\n</details>\n"
            "<!-- AUTO:REPOS:END -->"
        )

    def variant_details_compact() -> str:
        return (
            "<!-- AUTO:REPOS:START -->\n"
            "<details>\n<summary>All 14 public repositories</summary>\n\n"
            + variant_compact().split("-->", 1)[1].rsplit("<!--", 1)[0].strip()
            + "\n\n</details>\n"
            "<!-- AUTO:REPOS:END -->"
        )

    variants = {
        "A-current": current,
        "B-compact": variant_compact(),
        "C-details": variant_details(),
        "D-details-compact": variant_details_compact(),
    }

    handler = functools.partial(QuietHandler, directory=str(OUT))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    # the README references ./assets/... - the preview must resolve them
    assets_link = OUT / "assets"
    if assets_link.is_symlink() or assets_link.exists():
        assets_link.unlink()
    assets_link.symlink_to(ROOT / "assets", target_is_directory=True)

    results = []
    try:
        for name, block in variants.items():
            markdown = source.replace(current, block)
            results.append(measure(name, markdown, OUT))
            print(f"  measured {name}")
    finally:
        httpd.shutdown()

    print()
    print("=== REPOSITORY-INDEX TABLE VARIANTS ===\n")
    print(f"  {'variant':<18} {'table h':>9} {'page h':>9} {'table':>8} {'hero':>8} "
          f"{'gallery':>8} {'table/hero':>11}")
    print("  " + "-" * 80)
    for r in results:
        print(f"  {r['name']:<18} {r['table_height']:>7}px {r['page_height']:>7}px "
              f"{r['table_detail']:>7.2f}% {r['hero_detail']:>7.2f}% "
              f"{r['gallery_detail']:>7.2f}% {r['ratio']:>10.2f}x")
    print()
    print("  lower table/hero ratio = the hero wins the squint test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
