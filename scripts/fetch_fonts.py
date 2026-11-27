#!/usr/bin/env python3
"""Download + subset the Google Fonts used by the profile art.

The README is a GitHub markdown file: no external stylesheet is allowed, and
an SVG loaded through <img> cannot fetch a remote font either. So the type is
embedded directly in each SVG as a base64 WOFF2 data URI.

Two families, one pairing:
  Inter           - display / headings / UI text
  JetBrains Mono  - labels, code, terminal copy

Both are served by Google Fonts as variable fonts, so one file per family
covers the whole weight axis. The files are subset to the characters the art
can use, which keeps them small, and the builder subsets them again per SVG
so each card only carries the glyphs it actually draws.

    python scripts/fetch_fonts.py
    -> scripts/fonts/inter.woff2, scripts/fonts/jetbrains-mono.woff2
"""

from __future__ import annotations

import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "scripts" / "fonts"
CACHE = Path("/tmp/opencode/font-cache")

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

# Characters used by every generated visual: ASCII, the typographic marks and
# the symbols the art draws directly.
UNICODES = ",".join(
    [
        "U+0020-007E",
        "U+00A0",
        "U+00B7",
        "U+00D7",
        "U+2013",
        "U+2014",
        "U+2018",
        "U+2019",
        "U+201C",
        "U+201D",
        "U+2022",
        "U+2026",
        "U+2192",
        "U+2197",
        "U+2605",
        "U+2713",
    ]
)

SOURCES = {
    "inter": "https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7.woff2",
    "jetbrains": "https://fonts.gstatic.com/s/jetbrainsmono/v24/tDbv2o-flEEny0FZhsfKu5WU4zr3E_BX0PnT8RD8yKwBNntkaToggR7BYRbKPxDcwg.woff2",
}


def download(url: str, target: Path) -> Path:
    if target.exists():
        return target
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        target.write_bytes(response.read())
    return target


def subset(source: Path, target: Path) -> Path:
    if target.exists():
        return target
    command = [
        sys.executable,
        "-m",
        "fontTools.subset",
        str(source),
        f"--output-file={target}",
        f"--unicodes={UNICODES}",
        "--flavor=woff2",
        "--layout-features=kern,liga,calt,ccmp,locl",
        "--no-hinting",
        "--desubroutinize",
        "--name-IDs=*",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"subset failed for {source.name}: {result.stderr[-600:]}")
    return target


def main() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        raw = download(url, CACHE / f"{name}-raw.woff2")
        small = subset(raw, CACHE / f"{name}-subset.woff2")
        target = OUT_DIR / f"{name}.woff2"
        target.write_bytes(small.read_bytes())
        print(
            f"{name:<10} raw={raw.stat().st_size / 1024:.1f} KB "
            f"subset={target.stat().st_size / 1024:.1f} KB -> {target.relative_to(ROOT)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
