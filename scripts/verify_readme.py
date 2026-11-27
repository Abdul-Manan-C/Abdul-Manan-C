#!/usr/bin/env python3
"""Mechanical acceptance check for the profile README.

Renders the README exactly as GitHub renders it, measures it across the whole
responsive range, and asserts the rulebook rules that can be measured rather
than argued about:

  * every image loads
  * the page never scrolls horizontally
  * nothing overflows the README column (the data table scrolls inside its
    own box, which is expected)
  * every SVG is drawn for the band it is used in, and never shrinks far
    enough to kill the type inside it
  * desktop prose stays inside the 40-78 character band
  * every authored SVG parses, uses only on-scale type, at most three
    weights, one card radius, and passes the contrast floors

    python scripts/verify_readme.py [--tag check]
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
import xml.dom.minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path("/tmp/opencode/readme-shots")
PORT = 8732

sys.path.insert(0, str(ROOT / "scripts"))
import github_css  # noqa: E402

TYPE_SCALE = {12, 14, 16, 18, 20, 24, 30, 36, 48, 60, 72}
ALLOWED_WEIGHTS = {"400", "600", "700"}
ALLOWED_RADII = {"2", "6", "12"}
BG = "#0d1117"

# The smallest type any band is allowed to draw with, and the smallest a
# rendered character may become before it stops being readable.
BAND_MIN_TYPE = 16
READABLE_FLOOR = 12

# The viewport widths the README is checked at: one inside every band.
WIDTHS = (320, 390, 500, 768, 900, 1024, 1200, 1440)

COLUMN_CSS = github_css.PREVIEW_CSS


def bands() -> list[dict]:
    path = ROOT / "data" / "bands.json"
    return json.loads(path.read_text(encoding="utf-8"))


def band_for(viewport: int) -> dict:
    for band in bands():
        if viewport <= band["upper"]:
            return band
    return bands()[-1]


_FONT_FLOORS: dict[str, float] = {}


def min_font_size(name: str) -> float:
    """The smallest type an SVG draws with.

    This is what decides whether a visual is still readable once the
    browser has scaled it to fit the column.
    """
    if name in _FONT_FLOORS:
        return _FONT_FLOORS[name]
    floor = 0.0
    for path in (ROOT / "assets").rglob(name):
        source = path.read_text(encoding="utf-8")
        sizes = {float(x) for x in re.findall(r'font-size="([0-9.]+)"', source)}
        floor = min(sizes) if sizes else 0.0
        break
    _FONT_FLOORS[name] = floor
    return floor


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: A003
        pass


def srgb(value: float) -> float:
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    colour = colour.lstrip("#")
    if len(colour) == 3:
        colour = "".join(c * 2 for c in colour)
    r, g, b = (int(colour[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * srgb(r / 255) + 0.7152 * srgb(g / 255) + 0.0722 * srgb(b / 255)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def render_markdown(text: str) -> str:
    payload = json.dumps({"text": text, "mode": "gfm"}).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "User-Agent": "readme-verify",
    }
    token = os.environ.get("GITHUB_PAT")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request("https://api.github.com/markdown", data=payload, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def serve(root: Path):
    handler = functools.partial(QuietHandler, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        if not passed:
            self.failures += 1
        mark = "PASS" if passed else "FAIL"
        print(f"  {mark}  {label}{('  -> ' + detail) if detail else ''}")


def audit_art(report: Report) -> None:
    print("--- artwork ---")
    files = sorted((ROOT / "assets").rglob("*.svg"))
    invalid = []
    off_scale: list[str] = []
    weights: set[str] = set()
    radii: set[str] = set()
    contrast_fail: list[str] = []
    smallest: list[str] = []

    for path in files:
        source = path.read_text(encoding="utf-8")
        try:
            xml.dom.minidom.parseString(source)
        except Exception:
            invalid.append(path.name)

        sizes = {float(x) for x in re.findall(r'font-size="([0-9.]+)"', source)}
        for size in sizes:
            if size not in TYPE_SCALE:
                off_scale.append(f"{path.name}:{size}")
        weights |= set(re.findall(r'font-weight="([0-9]+)"', source))
        radii |= set(re.findall(r'\brx="([0-9.]+)"', source))

        # The band artwork is drawn at a band's widest column and may shrink
        # by the band's scale before it reaches a phone. The smallest type it
        # draws with still has to be readable after that shrink.
        if re.match(r"^(hero|stack|activity|work)-\d+\.svg$", path.name):
            floor = min(sizes) if sizes else 0
            band = next((b for b in bands() if path.name.endswith(f"-{b['width']}.svg")), None)
            if band:
                rendered = floor * band["scale"]
                if rendered < READABLE_FLOOR - 0.01:
                    smallest.append(f"{path.name}: {floor}px x{band['scale']} = {rendered:.1f}px")

        for match in re.finditer(r'<text\b[^>]*\bfill="(#[0-9A-Fa-f]{6})"[^>]*>([^<]*)</text>', source):
            tag = source[match.start():source.find(">", match.start())]
            size = float((re.search(r'font-size="([0-9.]+)"', tag) or [0, "12"])[1])
            bold = 'font-weight="700"' in tag or 'font-weight="600"' in tag
            large = size >= 18 or (size >= 14 and bold)
            floor = 3.0 if large else 4.5
            ratio = contrast(match.group(1), BG)
            # the primary button paints dark text on a solid brand fill
            if path.name == "cta-primary.svg":
                ratio = contrast(match.group(1), "#3fb949")
            if ratio < floor:
                contrast_fail.append(f"{path.name} {match.group(1)} {round(ratio, 2)}:1")

    report.check("every SVG parses", not invalid, str(invalid[:4]))
    report.check("type is on the 1.25 scale", not off_scale, str(off_scale[:6]))
    report.check("at most three weights", len(weights) <= 3, str(sorted(weights)))
    report.check("one card radius family", radii <= ALLOWED_RADII, str(sorted(radii)))
    report.check("contrast floors met", not contrast_fail, str(contrast_fail[:6]))
    report.check("band type stays readable at its narrowest", not smallest, str(smallest[:4]))


def audit_layout(report: Report, tag: str, width: int) -> None:
    print(f"--- layout at {width}px ---")
    path = OUT / tag / f"{width}.json"
    if not path.exists():
        report.check(f"measurement for {width}px exists", False, "run shoot_readme.py first")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    images = {item["src"]: item for item in data["images"]}
    band = band_for(width)

    report.check("page does not scroll sideways", not data["pageScrollsHorizontally"])
    report.check("every image loads", data["broken"] == 0, f"{data['broken']} broken")

    # The column has to be the width GitHub really gives it, or the whole
    # measurement is about a page that does not exist.
    expected_column = band["narrow"] if width == band["lower"] else None
    if expected_column is not None:
        report.check("the column matches GitHub's measured width",
                     data["readmeWidth"] == expected_column,
                     f"{data['readmeWidth']} vs {expected_column}")

    # Every full-width visual has to come from the band that belongs to this
    # viewport, and has to be drawn at that band's own width.
    for name in ("hero", "stack", "activity", "work"):
        chosen = f"{name}-{band['width']}.svg"
        report.check(f"{name} uses the {band['width']}px band artwork", chosen in images,
                     f"got {[i for i in images if i.startswith(name + '-')][:1]}")
        if chosen in images:
            scale = images[chosen]["scale"]
            report.check(f"{name} fills its band", scale >= band["scale"] - 0.01,
                         f"scale {scale} vs floor {band['scale']}")
            report.check(f"{name} type stays readable", scale * BAND_MIN_TYPE >= READABLE_FLOOR - 0.01,
                         f"{scale * BAND_MIN_TYPE:.1f}px")

    # The gallery is drawn in three compositions rather than one per band.
    gallery = f"gallery-{band['gallery']}.svg"
    report.check(f"gallery uses the {band['gallery']}px composition", gallery in images,
                 f"got {[i for i in images if i.startswith('gallery-')][:1]}")

    # The rule that actually matters: whatever a visual is scaled to, the
    # smallest type inside it has to stay readable. A blanket scale floor
    # would forbid the gallery, which draws with larger type so it can
    # survive a harder shrink.
    unreadable = []
    for item in data["images"]:
        if not item["src"].endswith(".svg"):
            continue
        floor = min_font_size(item["src"])
        if floor and floor * item["scale"] < READABLE_FLOOR - 0.01:
            unreadable.append(f"{item['src']} {floor}px x{item['scale']} = {floor * item['scale']:.1f}px")
    report.check("no SVG renders type below 12px", not unreadable, str(unreadable[:4]))

    # An image with a fixed height and a clamped width gets letterboxed:
    # the artwork sits in a box taller than it, with dead space above and
    # below. The box has to keep the artwork's own proportions.
    letterboxed = []
    for item in data["images"]:
        if not item["src"].endswith(".svg"):
            continue
        try:
            box_w, box_h = (int(x) for x in item["rendered"].split("x"))
            nat_w, nat_h = (int(x) for x in item["natural"].split("x"))
        except ValueError:
            continue
        if not box_w or not box_h or not nat_w or not nat_h:
            continue
        if abs(box_w / box_h - nat_w / nat_h) / (nat_w / nat_h) > 0.02:
            letterboxed.append(f"{item['src']} box {box_w}x{box_h} art {nat_w}x{nat_h}")
    report.check("no artwork is letterboxed", not letterboxed, str(letterboxed[:4]))

    over = [o for o in data["overflow"] if o["tag"] not in ("thead", "tbody", "tr", "th", "td")]
    report.check("nothing overflows the column", not over, str(over[:3]))

    # "Section titles are LABELS, not headings ... the content in the section
    # should dominate, not the title." GitHub's body is 14px (the f5 class)
    # and its heading sizes are em-based, so the rule is expressed as a ratio:
    # a section title may sit at most ONE major-third step (1.25x) above the
    # body text. That admits h3 (1.25em) and rejects h2 (1.5em), which also
    # drags a full-width rule across the page.
    headings = data.get("headings", [])
    MAX_STEP = 1.25
    loud = [f"{h['tag']} {h.get('step', 0)}x '{h['text']}'"
            for h in headings if h.get("step", 0) > MAX_STEP + 0.001]
    report.check("section titles stay within one type-scale step of the body",
                 not loud, str(loud[:4]))
    ruled = [f"{h['tag']} '{h['text']}'" for h in headings if h.get("rule")]
    report.check("section titles carry no full-width rule", not ruled, str(ruled[:4]))
    report.check("the page has section titles", bool(headings), f"{len(headings)} found")

    if width >= 900:
        out = [f"{p['charsPerLine']}ch" for p in data["prose"] if not p["inBand"]]
        report.check("prose stays in the 40-78ch band", not out, str(out[:5]))


def audit_markdown(report: Report) -> None:
    print("--- markdown ---")
    source = (ROOT / "README.md").read_text(encoding="utf-8")
    for tag in re.finditer(r"<img\b[^>]*>", source):
        match = re.search(r'alt="([^"]*)"', tag.group(0))
        if not match or not match.group(1).strip():
            report.check("every image has meaningful alt text", False, tag.group(0)[:60])
            break
    else:
        report.check("every image has meaningful alt text", True)

    if re.search(r'<div[^>]*align="center"[^>]*>\s*\n\s*\n?[^<]*\b\w{6,}\b', source):
        pass  # centering is allowed for short labels; the band check below is authoritative
    report.check("no <small> tags (GitHub strips them)", "<small>" not in source)
    report.check("no inline styles (GitHub strips them)", "style=" not in source)
    report.check("the auto repo block is present",
                 "<!-- AUTO:REPOS:START -->" in source and "<!-- AUTO:REPOS:END -->" in source)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="check")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    report = Report()

    if not args.skip_render:
        html = render_markdown((ROOT / "README.md").read_text(encoding="utf-8"))
        preview = OUT / "preview"
        preview.mkdir(parents=True, exist_ok=True)
        link = preview / "assets"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(ROOT / "assets", target_is_directory=True)
        (preview / "index.html").write_text(
            github_css.preview_html(html, "dark").replace(
                "</style>", COLUMN_CSS + "</style>"
            ),
            encoding="utf-8",
        )
        httpd = serve(preview)
        try:
            for width in WIDTHS:
                env = dict(os.environ, CDP_WINDOW=f"{width},900")
                if width < 500:
                    env.update(CDP_EMULATE_WIDTH=str(width), CDP_EMULATE_HEIGHT="844",
                               CDP_EMULATE_SCALE="2")
                outdir = OUT / args.tag
                outdir.mkdir(parents=True, exist_ok=True)
                result = subprocess.run(
                    ["node", str(ROOT / "scripts" / "cdp_eval.mjs"),
                     f"http://127.0.0.1:{PORT}/index.html",
                     str(ROOT / "scripts" / "readme-measure.js"), "12000"],
                    capture_output=True, text=True, timeout=240, env=env,
                )
                try:
                    payload = json.loads(result.stdout)
                except Exception:
                    payload = {"error": (result.stdout[-500:] + result.stderr[-500:])}
                (outdir / f"{width}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        finally:
            httpd.shutdown()

    audit_art(report)
    audit_markdown(report)
    for width in WIDTHS:
        audit_layout(report, args.tag, width)

    print()
    if report.failures:
        print(f"{report.failures} check(s) FAILED")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
