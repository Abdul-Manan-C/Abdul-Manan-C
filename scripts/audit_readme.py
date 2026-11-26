#!/usr/bin/env python3
"""Render the published README the way GitHub renders it and audit the layout.

Uses the GitHub markdown API for byte-accurate GitHub-flavoured HTML, rewrites
relative asset paths to raw.githubusercontent.com, then loads the result in
headless Chrome at GitHub's README column width and checks:

  * every image actually loads (naturalWidth > 0)
  * no element overflows the README column
  * table rows stay inside the column
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = "https://raw.githubusercontent.com/Abdul-Manan-C/Abdul-Manan-C/main"
OUT = Path("/tmp/opencode/readme-render")

GITHUB_CSS = """
body { margin:0; background:#0d1117; color:#e6edf3;
  font:16px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Noto Sans,Helvetica,Arial,sans-serif; }
#wrap { width: 900px; margin: 0 auto; padding: 24px 16px 60px; box-sizing: border-box; }
.markdown-body { overflow-wrap: break-word; word-wrap: break-word; }
.markdown-body h1,.markdown-body h2 { border-bottom:1px solid #21262d; padding-bottom:.3em; margin-top:24px; }
.markdown-body h2 { font-size:1.5em; }
.markdown-body table { border-collapse:collapse; display:block; width:max-content; max-width:100%; overflow:auto; }
.markdown-body th,.markdown-body td { border:1px solid #30363d; padding:6px 13px; }
.markdown-body th { background:#161b22; }
.markdown-body tr:nth-child(2n) { background:#161b22; }
.markdown-body a { color:#58a6ff; text-decoration:none; }
.markdown-body img { max-width:100%; box-sizing:content-box; }
.markdown-body code { background:#161b22; padding:.2em .4em; border-radius:6px; font-size:85%; }
.markdown-body pre { background:#161b22; padding:16px; border-radius:6px; overflow:auto; }
.markdown-body pre code { background:none; padding:0; }
.markdown-body hr { height:.25em; background:#30363d; border:0; margin:24px 0; }
.markdown-body div[align=center] { text-align:center; }
"""

AUDIT_JS = r"""
(async () => {
  const wrap = document.getElementById('wrap');
  const out = [];

  await Promise.all([...document.images].map(img =>
    img.complete ? Promise.resolve() : new Promise(res => {
      img.addEventListener('load', res, { once: true });
      img.addEventListener('error', res, { once: true });
    })
  ));
  await new Promise(r => setTimeout(r, 800));

  const imgs = [...document.images];
  const broken = imgs.filter(i => !i.complete || i.naturalWidth === 0);
  out.push(`images=${imgs.length} broken=${broken.length}`);
  broken.forEach(i => out.push(`  BROKEN ${i.getAttribute('src')}`));

  const W = wrap.getBoundingClientRect().width;
  let overflow = 0;
  document.querySelectorAll('#wrap *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    if (r.right > W + 2) {
      overflow++;
      if (overflow <= 12) out.push(`  OVERFLOW <${el.tagName.toLowerCase()} class="${el.className}"> right=${r.right.toFixed(0)} > ${W} src="${el.getAttribute && el.getAttribute('src') || ''}"`);
    }
  });
  out.push(`horizontal overflow elements=${overflow}`);

  const doc = document.documentElement;
  out.push(`document scrollWidth=${doc.scrollWidth} clientWidth=${doc.clientWidth}`);

  const tables = [...document.querySelectorAll('table')];
  out.push(`tables=${tables.length}`);
  tables.forEach((t, i) => {
    const r = t.getBoundingClientRect();
    out.push(`  table${i} width=${r.width.toFixed(0)} rows=${t.rows.length} cells=${t.rows[0] ? t.rows[0].cells.length : 0}`);
  });

  const cards = [...document.querySelectorAll('#wrap img')].map(i => ({
    src: i.getAttribute('src').split('/').pop(),
    w: Math.round(i.getBoundingClientRect().width),
    h: Math.round(i.getBoundingClientRect().height),
    loaded: i.complete && i.naturalWidth > 0,
  }));
  cards.forEach(c => out.push(`  img ${c.src.padEnd(28)} ${String(c.w).padStart(4)}x${String(c.h).padStart(4)} loaded=${c.loaded}`));

  document.title = 'DONE';
  const pre = document.createElement('pre');
  pre.id = 'audit';
  pre.textContent = out.join('\n');
  document.body.appendChild(pre);
})();
"""


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


def main() -> int:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    html = render_markdown(readme)
    html = html.replace('src="./', f'src="{RAW}/').replace('href="./', f'href="{RAW}/')

    OUT.mkdir(parents=True, exist_ok=True)
    page = OUT / "index.html"
    page.write_text(
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{GITHUB_CSS}</style></head><body>"
        f"<div id='wrap' class='markdown-body'>{html}</div>"
        f"<script>{AUDIT_JS}</script></body></html>",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "google-chrome",
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--virtual-time-budget=25000",
            "--window-size=900,2400",
            "--dump-dom",
            page.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    match = re.search(r'<pre id="audit">(.*?)</pre>', result.stdout, re.S)
    print(match.group(1) if match else "AUDIT DID NOT RUN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
