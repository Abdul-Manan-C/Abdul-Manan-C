#!/usr/bin/env python3
"""Render the repository social preview (1280x640 PNG) from the same design
system as the README art.

GitHub has no public API for the social preview image, so the file is written
here and uploaded once by hand:
    repo -> Settings -> General -> Social preview -> upload assets/social-preview.png
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_profile_art import DISPLAY, MONO, radar  # noqa: E402

W, H = 1280, 640
OUT_SVG = ROOT / "assets" / "social-preview.svg"
OUT_PNG = ROOT / "assets" / "social-preview.png"
SNAPSHOT = ROOT / "data" / "profile.json"

CHROME_CANDIDATES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]


def find_chrome() -> str:
    for name in CHROME_CANDIDATES:
        try:
            result = subprocess.run(["which", name], capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
    return ""


def build_svg() -> str:
    style = (
        "<style>"
        ".spin{transform-box:view-box;transform-origin:150px 148px}"
        ".ping{transform-box:fill-box;transform-origin:center}"
        "@media (prefers-reduced-motion: no-preference){"
        ".spin{animation:sweep 9s linear infinite}"
        ".spin.ring{animation-duration:26s}"
        ".ping{animation:ping 2.6s ease-out infinite}"
        "}"
        "@keyframes sweep{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}"
        "@keyframes ping{0%{transform:scale(1);opacity:.75}70%,100%{transform:scale(4.5);opacity:0}}"
        "</style>"
    )
    defs = (
        "<defs>"
        '<radialGradient id="sweep" cx="0.5" cy="0.5" r="0.5">'
        '<stop offset="0%" stop-color="#58a6ff" stop-opacity="0.45"/>'
        '<stop offset="70%" stop-color="#58a6ff" stop-opacity="0.12"/>'
        '<stop offset="100%" stop-color="#58a6ff" stop-opacity="0"/>'
        "</radialGradient>"
        '<radialGradient id="glow" cx="0.78" cy="0.5" r="0.5">'
        '<stop offset="0%" stop-color="#1f6feb" stop-opacity="0.28"/>'
        '<stop offset="100%" stop-color="#1f6feb" stop-opacity="0"/>'
        "</radialGradient>"
        '<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">'
        '<rect width="4" height="1" fill="#ffffff" opacity="0.02"/>'
        "</pattern>"
        "</defs>"
    )
    stats = ""
    if SNAPSHOT.exists():
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        stats = (
            f"{snapshot.get('public_repos', 0)} public repos   \u00b7   "
            f"{snapshot.get('contributions', 0)} contributions   \u00b7   "
            f"{snapshot.get('followers', 0)} followers   \u00b7   "
            f"{snapshot.get('total_stars', 0)} stars"
        )
    if not stats:
        stats = "CYNEX Studio   \u00b7   github.com/Abdul-Manan-C"
    body = (
        f'<rect width="{W}" height="{H}" fill="#0d1117"/>'
        f'<rect width="{W}" height="{H}" fill="url(#glow)"/>'
        f'<rect width="{W}" height="{H}" fill="url(#scan)"/>'
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" fill="none" stroke="#21262d"/>'
        f'<g transform="translate(700,60) scale(1.9)">{radar()}</g>'
        f'<text x="88" y="196" font-family="{MONO}" font-size="17" letter-spacing="4" fill="#58a6ff">'
        f"ABDUL MANAN</text>"
        f'<text x="88" y="286" font-family="{DISPLAY}" font-size="66" font-weight="700" fill="#e6edf3">'
        f"Founder, CYNEX Studio</text>"
        f'<text x="88" y="346" font-family="{DISPLAY}" font-size="30" fill="#8b949e">'
        f"Web engineering \u00b7 3D product stages \u00b7 AI automation</text>"
        f'<text x="88" y="392" font-family="{DISPLAY}" font-size="30" fill="#8b949e">'
        f"Offensive tooling \u00b7 Linux \u00b7 Cybersecurity</text>"
        f'<rect x="88" y="432" width="86" height="4" rx="2" fill="#3fb949"/>'
        f'<text x="88" y="492" font-family="{MONO}" font-size="19" fill="#c9d1d9">{stats}</text>'
        f'<text x="88" y="536" font-family="{MONO}" font-size="19" fill="#58a6ff">cynex.online</text>'
        f'<text x="{W - 88}" y="536" text-anchor="end" font-family="{MONO}" font-size="19" fill="#6e7681">'
        f"github.com/Abdul-Manan-C</text>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="Abdul Manan — Founder, CYNEX Studio">{defs}{style}{body}</svg>\n'
    )


def to_png(chrome: str) -> bool:
    tmp = OUT_PNG.with_suffix(".tmp.png")
    command = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--virtual-time-budget=8000",
        f"--window-size={W},{H}",
        f"--screenshot={tmp}",
        OUT_SVG.as_uri(),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        tmp.unlink(missing_ok=True)
        return False
    if result.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(OUT_PNG)
    return True


def main() -> int:
    OUT_SVG.parent.mkdir(parents=True, exist_ok=True)
    OUT_SVG.write_text(build_svg(), encoding="utf-8")
    chrome = find_chrome()
    if not chrome:
        print("no chrome binary found; wrote the svg only", file=sys.stderr)
        return 0
    if to_png(chrome):
        print(f"social preview: {OUT_PNG.name} ({OUT_PNG.stat().st_size // 1024} KB)")
    else:
        print("social preview: png render failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
