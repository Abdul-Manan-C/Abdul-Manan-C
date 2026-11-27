#!/usr/bin/env python3
"""Weigh every README section against the pixels.

Combines the DOM geometry (where each block sits) with the rendered pixels
(how much ink and how much *detail* each block actually carries) to produce
a visual-weight table.

The squint test, done numerically: the block that owns the most detail
energy is the one the reader's eye lands on first, whether or not that was
the intention.

    python scripts/weigh_sections.py [--shot /tmp/opencode/readme-shots/audit/900.png]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BG = (13, 17, 23)


def ink_profile(im: Image.Image) -> list[int]:
    """Ink per row, measured as distance from the page background."""
    px = im.convert("RGB")
    w, h = px.size
    out = []
    for y in range(h):
        row = 0
        for x in range(w):
            r, g, b = px.getpixel((x, y))
            if abs(r - BG[0]) + abs(g - BG[1]) + abs(b - BG[2]) > 24:
                row += 1
        out.append(row)
    return out


def edge_profile(im: Image.Image) -> list[int]:
    """Detail energy per row.

    A flat filled panel is not attention-grabbing; texture is. Summing the
    local luminance gradient measures how much *detail* a row carries, which
    is what the eye actually lands on. This separates "the table has a
    background" from "the table has a lot to look at".
    """
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shot", default="/tmp/opencode/readme-shots/audit/900.png")
    parser.add_argument("--port", default="8733")
    args = parser.parse_args()

    preview = Path("/tmp/opencode/readme-shots/preview")
    if not (preview / "index.html").exists():
        print("error: run scripts/shoot_readme.py first", file=sys.stderr)
        return 1

    env = dict(os.environ, CDP_WINDOW="900,900")
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "cdp_eval.mjs"),
         f"http://127.0.0.1:{args.port}/index.html",
         str(ROOT / "scripts" / "readme-sections.js"), "10000"],
        capture_output=True, text=True, timeout=180, env=env)
    try:
        data = json.loads(result.stdout)
    except Exception:
        print(result.stdout[-1500:], result.stderr[-1500:])
        return 1
    if "error" in data:
        print(data)
        return 1

    im = Image.open(args.shot).convert("RGB")
    rows = ink_profile(im)
    edges = edge_profile(im)
    total = sum(rows) or 1
    etotal = sum(edges) or 1

    print(f"=== VISUAL WEIGHT PER BLOCK  ({args.shot}) ===\n")
    print(f"  {'#':>3}  {'tag':<10} {'top':>6} {'h':>6}  {'fill':>7} {'detail':>8}  content")
    print("  " + "-" * 96)
    ranked = []
    for b in data["blocks"]:
        top = max(0, b["top"])
        bot = min(len(rows), b["bottom"])
        ink = sum(rows[top:bot]) if bot > top else 0
        edge = sum(edges[top:bot]) if bot > top else 0
        ranked.append((edge, b, ink))
        label = b["text"] or (", ".join(i["src"] for i in b["imgs"]) or b["tag"])
        print(f"  {b['i']:>3}  {b['tag']:<10} {b['top']:>6} {b['h']:>6}  "
              f"{100*ink/total:6.2f}% {100*edge/etotal:7.2f}%  {label[:44]}")

    print("\n=== RANKED BY DETAIL ENERGY (the squint test, numerically) ===")
    print("   detail = local luminance gradient. It is what the eye lands on.\n")
    for rank, (edge, b, ink) in enumerate(sorted(ranked, key=lambda r: -r[0])[:10], 1):
        label = b["text"] or (", ".join(i["src"] for i in b["imgs"]) or b["tag"])
        bar = "█" * int(100 * edge / etotal * 1.8)
        print(f"  {rank:>2}. {100*edge/etotal:5.2f}%  {b['tag']:<10} y={b['top']:<6} {bar} {label[:40]}")

    print("\n=== GAPS BETWEEN BLOCKS ===")
    for g in sorted(data["gaps"], key=lambda x: -x["gap"])[:10]:
        if g["gap"] > 24:
            print(f"  {g['gap']:>4}px  after #{g['after']} ({g['from'][:30]!r}) -> #{g['before']} ({g['to'][:30]!r})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
