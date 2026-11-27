#!/usr/bin/env python3
"""Downscale the platform screenshots for phone-sized screens.

The desktop captures are 1440x900 JPEGs. GitHub's README column is ~418px on
a phone, so each cell renders the image at about 182px - a 1440px file is
~8x more pixels than the screen can show, and six of them is ~600 KB of
mobile bandwidth. The mobile variants are 400px wide, which is still crisp at
2x on a phone and roughly a quarter of the bytes.

    python scripts/shrink_screens.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    print("note: Pillow not installed; mobile screenshots skipped", file=sys.stderr)
    raise SystemExit(0)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "screens"
DST = SRC / "m"
TARGET_WIDTH = 400
QUALITY = 82


def main() -> int:
    if not SRC.exists():
        print(f"no screenshots at {SRC}", file=sys.stderr)
        return 0
    DST.mkdir(parents=True, exist_ok=True)
    total_before = total_after = 0
    for source in sorted(SRC.glob("*.jpg")):
        with Image.open(source) as image:
            image = image.convert("RGB")
            if image.width > TARGET_WIDTH:
                height = round(image.height * TARGET_WIDTH / image.width)
                image = image.resize((TARGET_WIDTH, height), Image.LANCZOS)
            target = DST / source.name
            image.save(target, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        before = source.stat().st_size
        after = target.stat().st_size
        total_before += before
        total_after += after
        print(f"  {source.name:<24} {before / 1024:>6.1f} KB -> {after / 1024:>5.1f} KB  "
              f"({image.width}x{image.height})")
    if total_before:
        print(f"  total {total_before / 1024:.0f} KB -> {total_after / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
