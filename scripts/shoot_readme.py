#!/usr/bin/env python3
"""Render the README the way GitHub renders it, screenshot it, and measure it.

  python scripts/shoot_readme.py [--widths 1440,900,390] [--tag before]

The README's own markdown is converted to GitHub-flavoured HTML through the
GitHub markdown API (so the sanitizer's behaviour is exact), then served from
a local HTTP server rooted at the repo so that relative asset paths resolve
to the working tree - not to whatever is currently published.

Produces, under /tmp/opencode/readme-shots/<tag>/:
  <width>.png   screenshot of the rendered README
  <width>.json  measured layout facts (overflow, tables, images, text widths)
"""

from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parent.parent
OUT = Path("/tmp/opencode/readme-shots")
PORT = 8731

sys.path.insert(0, str(ROOT / "scripts"))
import github_css  # noqa: E402

# The README column is 846px on a desktop profile page. GitHub centres it.
COLUMN = 846
COLUMN_CSS = github_css.PREVIEW_CSS


def render_markdown(text: str) -> str:
    payload = json.dumps({"text": text, "mode": "gfm"}).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "User-Agent": "readme-audit",
    }
    token = os.environ.get("GITHUB_PAT")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request("https://api.github.com/markdown", data=payload, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: A003 - silence the access log
        pass


def serve(root: Path):
    handler = functools.partial(QuietHandler, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--widths", default="1440,900,390")
    parser.add_argument("--tag", default="before")
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--theme", default="dark", choices=("dark", "light"))
    args = parser.parse_args()

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    html = render_markdown(readme)

    outdir = OUT / args.tag
    outdir.mkdir(parents=True, exist_ok=True)

    # The rendered page must sit next to the real assets so that the README's
    # relative "./assets/..." paths resolve to the working tree.
    preview = OUT / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    assets_link = preview / "assets"
    if assets_link.is_symlink() or assets_link.exists():
        assets_link.unlink()
    assets_link.symlink_to(ROOT / "assets", target_is_directory=True)
    page = preview / "index.html"
    page.write_text(
        github_css.preview_html(html, args.theme).replace(
            "</style>", COLUMN_CSS + "</style>"
        ),
        encoding="utf-8",
    )

    httpd = serve(preview)
    try:
        for width in [int(w) for w in args.widths.split(",")]:
            shot = outdir / f"{width}.png"
            env = dict(os.environ, CDP_WINDOW=f"{width},{args.height}")

            if width < 500:
                # Chrome cannot open a window this narrow, so emulate a phone.
                env.update(
                    CDP_EMULATE_WIDTH=str(width),
                    CDP_EMULATE_HEIGHT="844",
                    CDP_EMULATE_SCALE="2",
                    CDP_SCREENSHOT=str(shot),
                )
            else:
                height = 7000 if width <= 900 else 5200
                subprocess.run(
                    ["google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
                     "--hide-scrollbars", "--force-device-scale-factor=1",
                     f"--window-size={width},{height}",
                     "--screenshot=" + str(shot),
                     "--virtual-time-budget=25000",
                     "http://127.0.0.1:8731/index.html"],
                    capture_output=True, text=True, timeout=240,
                )

            measured = subprocess.run(
                ["node", str(ROOT / "scripts" / "cdp_eval.mjs"),
                 "http://127.0.0.1:8731/index.html",
                 str(ROOT / "scripts" / "readme-measure.js"), "12000"],
                capture_output=True, text=True, timeout=240, env=env,
            )
            try:
                data = json.loads(measured.stdout)
            except Exception:
                data = {"error": (measured.stdout[-800:] + measured.stderr[-800:])}
            (outdir / f"{width}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
            print(f"--- width {width} ---")
            print(json.dumps(data, indent=1)[:2500])
    finally:
        httpd.shutdown()

    print(f"\nscreenshots -> {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
