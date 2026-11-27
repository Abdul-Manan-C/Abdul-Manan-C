#!/usr/bin/env python3
"""Pixel-level visual audit of the rendered profile README.

Eyeballing a screenshot misses things; measuring it does not. This script
answers the questions the rulebooks care about, straight from the pixels:

  * where does the visual mass sit (the squint test, done numerically)
  * does the hierarchy survive desaturation (the grayscale test)
  * does every block share one left edge (the alignment grid)
  * is the vertical rhythm on the 8pt scale
  * which colours carry the eye, and do they have enough contrast

    python scripts/audit_visual.py [--shot /tmp/opencode/readme-shots/audit/900.png]
"""

from __future__ import annotations

import argparse
import colorsys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageFilter

BG = (13, 17, 23)
PANEL = (22, 27, 34)


def luminance(rgb: tuple[int, int, int]) -> float:
    def ch(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def content_mask(im: Image.Image) -> Image.Image:
    """White where the pixel is not the page background or a flat panel."""
    px = im.convert("RGB")
    out = Image.new("L", px.size, 0)
    src = px.load()
    dst = out.load()
    w, h = px.size
    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            d_bg = abs(r - BG[0]) + abs(g - BG[1]) + abs(b - BG[2])
            d_panel = abs(r - PANEL[0]) + abs(g - PANEL[1]) + abs(b - PANEL[2])
            dst[x, y] = 255 if min(d_bg, d_panel) > 24 else 0
    return out


def row_profile(mask: Image.Image) -> list[int]:
    """Ink per row."""
    data = mask.load()
    w, h = mask.size
    return [sum(1 for x in range(w) if data[x, y]) for y in range(h)]


def bands_from_rows(rows: list[int], min_gap: int = 18, min_ink: int = 3) -> list[tuple[int, int]]:
    """Contiguous vertical bands of content, separated by quiet gaps."""
    out: list[tuple[int, int]] = []
    start = None
    quiet = 0
    for y, ink in enumerate(rows):
        if ink > min_ink:
            if start is None:
                start = y
            quiet = 0
        else:
            if start is not None:
                quiet += 1
                if quiet >= min_gap:
                    out.append((start, y - quiet + 1))
                    start = None
                    quiet = 0
    if start is not None:
        out.append((start, len(rows)))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shot", default="/tmp/opencode/readme-shots/audit/900.png")
    args = parser.parse_args()

    im = Image.open(args.shot).convert("RGB")
    w, h = im.size
    print(f"=== {args.shot}  ({w}x{h}) ===\n")

    # ------------------------------------------------------------------ #
    # 1. squint test: blur hard, find where the visual mass concentrates
    # ------------------------------------------------------------------ #
    small = im.convert("L").resize((max(1, w // 12), max(1, h // 12)), Image.BOX)
    px = small.load()
    sw, sh = small.size
    mass_rows = [sum(px[x, y] for x in range(sw)) for y in range(sh)]
    total = sum(mass_rows) or 1
    chunks = 10
    size = sh // chunks
    print("--- SQUINT TEST: where the visual weight lands ---")
    for i in range(chunks):
        part = sum(mass_rows[i * size:(i + 1) * size])
        pct = 100 * part / total
        print(f"  band {i + 1:>2}  y {i * size * 12:>6}-{(i + 1) * size * 12:>6}  {pct:5.1f}%  {'#' * int(pct * 1.6)}")
    print()

    # ------------------------------------------------------------------ #
    # 2. alignment grid: where does content actually start?
    # ------------------------------------------------------------------ #
    mask = content_mask(im)
    mpx = mask.load()
    rows = row_profile(mask)
    bs = bands_from_rows(rows)
    col_hits = [0] * w
    for y in range(0, h, 2):
        for x in range(w):
            if mpx[x, y]:
                col_hits[x] += 1
    significant = [x for x, c in enumerate(col_hits) if c > 3]
    print("--- ALIGNMENT GRID ---")
    if significant:
        print(f"  leftmost content column : {min(significant)}")
        print(f"  rightmost content column: {max(significant)}")
        lefts = []
        for top, bot in bs:
            cols = [x for x in range(w) if any(mpx[x, y] for y in range(top, bot, 3))]
            if cols:
                lefts.append((top, min(cols)))
        if lefts:
            common = Counter(l for _, l in lefts).most_common(1)[0]
            print(f"  most common left edge   : {common[0]} (in {common[1]} of {len(lefts)} bands)")
            off = [(t, l) for t, l in lefts if abs(l - common[0]) > 2]
            print(f"  bands off that edge     : {len(off)}")
            for t, l in off[:12]:
                print(f"     y={t:<6} left={l}  (delta {l - common[0]:+d})")
    print()

    # ------------------------------------------------------------------ #
    # 3. vertical rhythm
    # ------------------------------------------------------------------ #
    print("--- VERTICAL RHYTHM ---")
    print(f"  content bands: {len(bs)}")
    gaps = [(bs[i][0] - bs[i - 1][1], bs[i - 1][1], bs[i][0]) for i in range(1, len(bs))]
    if gaps:
        vals = sorted(g[0] for g in gaps)
        print(f"  gap sizes: min {vals[0]}  median {vals[len(vals)//2]}  max {vals[-1]}")
        near8 = sum(1 for g in gaps if min(abs(g[0] - k * 8) for k in range(g[0] // 8 + 2)) <= 4)
        print(f"  gaps within 4px of a multiple of 8: {near8}/{len(gaps)}")
        print("  largest gaps:")
        for g in sorted(gaps, reverse=True)[:8]:
            print(f"     {g[0]:>4}px  (y {g[1]} -> {g[2]})")
    print()

    # ------------------------------------------------------------------ #
    # 4. colour: what does the eye catch?
    # ------------------------------------------------------------------ #
    print("--- COLOUR MASS (top 14 non-background colours) ---")
    quant = im.quantize(colors=24, method=Image.MEDIANCUT).convert("RGB")
    counts = Counter(quant.getdata())
    for colour, n in counts.most_common(14):
        pct = 100 * n / (w * h)
        r, g, b = colour
        hue = "  "
        if max(colour) - min(colour) > 24:
            hh, _, _ = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            names = {0.33: "green", 0.58: "blue", 0.08: "amber", 0.92: "pink"}
            hue = names.get(round(hh, 2), f"h{hh:.2f}")
        print(f"  #{r:02x}{g:02x}{b:02x} {hue:<6} {pct:6.3f}%  contrast vs bg {contrast(colour, BG):5.2f}:1")
    print()

    # ------------------------------------------------------------------ #
    # 5. grayscale test: does hierarchy survive without hue?
    # ------------------------------------------------------------------ #
    print("--- GRAYSCALE TEST ---")
    gray = im.convert("L")
    gpx = gray.load()
    band_lum = []
    for top, bot in bs:
        vals = [gpx[x, y] for y in range(top, min(bot, top + 400), 4) for x in range(0, w, 4)]
        band_lum.append((top, bot, max(vals) if vals else 0, sum(vals) / len(vals) if vals else 0))
    print("  brightest content bands (what survives a squint):")
    for top, bot, mx, avg in sorted(band_lum, key=lambda b: -b[2])[:6]:
        print(f"     y {top:>6}-{bot:<6} peak L {mx:>3}  mean L {avg:5.1f}")
    print()

    # ------------------------------------------------------------------ #
    # 6. text legibility
    # ------------------------------------------------------------------ #
    print("--- TEXT LEGIBILITY (vertical ink density) ---")
    g = gray.filter(ImageFilter.GaussianBlur(0.4))
    gpx2 = g.load()
    thin = []
    for y in range(h):
        row = [gpx2[x, y] for x in range(w)]
        edges = sum(1 for i in range(1, w) if abs(row[i] - row[i - 1]) > 28)
        if edges > 0:
            thin.append((y, edges))
    if thin:
        print(f"  rows containing text edges: {len(thin)}")
        print(f"  median edge count per text row: {sorted(e for _, e in thin)[len(thin)//2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
