#!/usr/bin/env python3
"""A/B two treatments of the README and measure the difference.

Renders each variant through the real GitHub markdown pipeline, with
GitHub's real stylesheet, then reports what changed: page height, the
detail energy of each block, and where the eye lands.

    python scripts/exp_variants.py
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = Path("/tmp/opencode/readme-shots/exp2")
PORT = 8735

sys.path.insert(0, str(ROOT / "scripts"))
import github_css  # noqa: E402

COLUMN_CSS = "#readme { width: 100%; max-width: 846px; margin: 0 auto; padding: 24px 0 60px; }"


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


def measure(name: str, markdown: str, server_dir: Path, theme: str) -> dict:
    html = render_markdown(markdown)
    page = server_dir / "index.html"
    page.write_text(
        github_css.preview_html(html, theme).replace("</style>", COLUMN_CSS + "</style>"),
        encoding="utf-8")

    env = dict(os.environ, CDP_WINDOW="900,7000")
    shot = OUT / f"{name}-{theme}.png"
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

    def energy(b):
        if not b:
            return 0.0, 0
        top, bot = max(0, b["top"]), min(len(rows), b["bottom"])
        return 100 * sum(rows[top:bot]) / total, bot - top

    per = []
    for b in blocks:
        pct, _ = energy(b)
        per.append((b["tag"], b["text"] or ", ".join(i["src"] for i in b["imgs"]) or b["tag"], pct, b["h"]))

    headings = [x for x in per if x[0] in ("h2", "h3", "h4")]

    # The rulebook rule is per-section, not per-page: "the content in the
    # section should dominate, not the title." Pair each title with the
    # content that follows it, up to the next title.
    sections = []
    for idx, (tag, text, pct, h) in enumerate(per):
        if tag not in ("h2", "h3", "h4"):
            continue
        content = 0.0
        content_h = 0
        for nxt in per[idx + 1:]:
            if nxt[0] in ("h2", "h3", "h4"):
                break
            content += nxt[2]
            content_h += nxt[3]
        sections.append({
            "tag": tag,
            "text": text,
            "title": pct,
            "content": content,
            "ratio": (pct / content) if content else float("inf"),
        })

    return {
        "name": name,
        "theme": theme,
        "page_height": max((b["bottom"] for b in blocks), default=0),
        "heading_detail": sum(x[2] for x in headings),
        "heading_height": sum(x[3] for x in headings),
        "headings": headings,
        "sections": sections,
        "worst_ratio": max((s["ratio"] for s in sections), default=0),
        "per": per,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source = (ROOT / "README.md").read_text(encoding="utf-8")

    # the variants under test: how loud should a section title be?
    h3 = source.replace("\n### ", "\n#### ")
    h2 = source.replace("\n### ", "\n## ")
    variants = {
        "h2-21px": h2,
        "h3-17px": source,
        "h4-14px": h3,
    }

    handler = functools.partial(QuietHandler, directory=str(OUT))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    assets_link = OUT / "assets"
    if assets_link.is_symlink() or assets_link.exists():
        assets_link.unlink()
    assets_link.symlink_to(ROOT / "assets", target_is_directory=True)

    results = []
    try:
        for name, markdown in variants.items():
            results.append(measure(name, markdown, OUT, "dark"))
            print(f"  measured {name}")
    finally:
        httpd.shutdown()

    print()
    print("=== SECTION-TITLE TREATMENT (dark theme, GitHub's real CSS) ===\n")
    print(f"  {'variant':<12} {'page height':>12} {'title detail':>13} {'worst title/content':>21}")
    print("  " + "-" * 64)
    for r in results:
        print(f"  {r['name']:<12} {r['page_height']:>10}px {r['heading_detail']:>12.2f}% "
              f"{r['worst_ratio']:>19.2f}x")

    print("\n=== TITLE vs ITS OWN SECTION CONTENT ===")
    print("   rule: content must dominate its title, so the ratio must stay below 1.00x\n")
    for r in results:
        print(f"  {r['name']}:")
        for s in r["sections"]:
            flag = "  <-- title out-shouts" if s["ratio"] >= 1 else ""
            print(f"      {s['tag']:<3} title {s['title']:5.2f}%  content {s['content']:6.2f}%  "
                  f"{s['ratio']:5.2f}x  {s['text'][:36]}{flag}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
