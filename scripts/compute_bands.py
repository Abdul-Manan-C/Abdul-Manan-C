#!/usr/bin/env python3
"""Turn the measured column curve into artwork bands.

GitHub's README column is not a single width - it is a piecewise-linear
function of the viewport:

    viewport <  768   column = viewport - 82     (phone / tablet)
    768..1011         column = viewport - 370    (profile sidebar appears)
    1012..1279        column = viewport - 434    (wider container)
    viewport >= 1280  column = 846                (capped)

Artwork drawn at one fixed width therefore gets squeezed on some devices and
stretched on others, and the type inside it shrinks with it. The fix is to
draw one copy of each visual per band, sized to that band's widest column,
and let the browser pick the copy with ``<picture><source media=...>``.

This script computes the bands from the measured curve and writes them to
``data/bands.json``. ``build_profile_art.py`` reads that file.

    python scripts/compute_bands.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CURVE = ROOT / "data" / "column_curve.json"
OUT = ROOT / "data" / "bands.json"

# The smallest type the artwork is allowed to use, in CSS pixels.
MIN_TYPE = 16
# The smallest a rendered character may become before it stops being readable.
FLOOR_TYPE = 12
# The scale floor a band has to keep.
SCALE_FLOOR = FLOOR_TYPE / MIN_TYPE

BREAKPOINTS = (768, 1012, 1280)

# The platform gallery is drawn in three compositions: one column for the
# narrow bands, two narrow columns in the middle, two wide columns on a
# desktop. A composition is only allowed to serve a band when the art stays
# within these bounds - too small and the type dies, too large and the
# screenshots are upscaled into mush.
GALLERY_VARIANTS = (424, 566, 846)
GALLERY_MIN_SCALE = 0.55
GALLERY_MAX_SCALE = 1.07


def gallery_for(band: dict) -> int:
    """The gallery composition that serves a band."""
    for width in GALLERY_VARIANTS:
        if (band["narrow"] / width >= GALLERY_MIN_SCALE
                and band["width"] / width <= GALLERY_MAX_SCALE):
            return width
    return GALLERY_VARIANTS[-1]


def column(viewport: int) -> int:
    """The README column width at a viewport, from the measured curve."""
    if viewport >= BREAKPOINTS[2]:
        return 846
    if viewport >= BREAKPOINTS[1]:
        return viewport - 434
    if viewport >= BREAKPOINTS[0]:
        return viewport - 370
    return viewport - 82


def verify_curve() -> int:
    """Check the formula against every live measurement."""
    if not CURVE.exists():
        print("no curve file; run measure_column_curve.py first")
        return 0
    rows = json.loads(CURVE.read_text(encoding="utf-8"))
    bad = []
    for row in rows:
        v = int(row["requested"])
        expected = column(v)
        if abs(expected - int(row["article"])) > 1:
            bad.append(f"v={v}: measured {row['article']} formula {expected}")
    if bad:
        print("curve mismatch:")
        for line in bad:
            print("   ", line)
        return len(bad)
    print(f"curve verified: formula matches all {len(rows)} live measurements")
    return 0


def compute(min_viewport: int = 320, max_viewport: int = 1920) -> list[dict]:
    """Greedily split the viewport range into bands that hold the scale floor."""
    bands: list[dict] = []
    lower = min_viewport
    while lower <= max_viewport:
        # A band may not cross one of GitHub's own breakpoints: the column
        # drops there, so the artwork would be scaled one way on each side.
        ceiling = max_viewport
        for bp in BREAKPOINTS:
            if lower < bp <= max_viewport:
                ceiling = bp - 1
                break

        # Widen the band while the narrow end still renders at SCALE_FLOOR.
        best = lower
        for candidate in range(lower, ceiling + 1):
            if column(lower) / column(candidate) < SCALE_FLOOR:
                break
            best = candidate
        if best < lower:
            best = lower

        bands.append({
            "lower": lower,
            "upper": best,
            "width": column(best),
            "narrow": column(lower),
            "scale": round(column(lower) / column(best), 4),
        })
        lower = best + 1

    # The last band is the capped one: the column stops growing, so the
    # artwork can be the full 846px with nothing scaled.
    if bands and bands[-1]["upper"] >= BREAKPOINTS[2]:
        bands[-1]["width"] = 846
        bands[-1]["narrow"] = 846
        bands[-1]["scale"] = 1.0

    return bands


def main() -> int:
    problems = verify_curve()
    if problems:
        return 1

    bands = compute()
    for band in bands:
        band["gallery"] = gallery_for(band)

    print(f"\nscale floor {SCALE_FLOOR:.2f} (min type {MIN_TYPE}px, floor {FLOOR_TYPE}px)")
    print(f"{'band':>4} {'viewport range':>16} {'column':>12} {'art':>6} {'scale':>7} {'gallery':>8}")
    print("  " + "-" * 60)
    for index, band in enumerate(bands):
        print(f"  {index:>2} {band['lower']:>5}..{band['upper']:<9} "
              f"{band['narrow']:>5}..{band['width']:<5} {band['width']:>6} {band['scale']:>6.3f}x "
              f"{band['gallery']:>6}px")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bands, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT} ({len(bands)} bands)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
