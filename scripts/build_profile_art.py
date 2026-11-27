#!/usr/bin/env python3
"""Profile art pipeline for github.com/Abdul-Manan-C.

Pulls live public profile data (GitHub REST + the public contributions
calendar), renders every visual in the profile README and refreshes the
auto-generated repository index:

    assets/hero.svg              animated console + radar
    assets/cards/tile-*.svg      three linked tiles (build / security / studio)
    assets/cards/repo-*.svg      one card per featured public repository
    assets/activity.svg          twelve-month contribution chart + streak stats
    data/profile.json            live snapshot

Standard library only. Safe to run offline: on a network failure the previous
snapshot is kept and the script exits cleanly.
"""

from __future__ import annotations

import base64
import html
import io
import json
import math
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER = "Abdul-Manan-C"
API = "https://api.github.com"
UA = "profile-art-builder/1.0 (+https://github.com/Abdul-Manan-C)"

FONT_DIR = ROOT / "scripts" / "fonts"
FONT_FILES = {
    "Inter": FONT_DIR / "inter.woff2",
    "JetBrains Mono": FONT_DIR / "jetbrains.woff2",
}
ICON_FILE = ROOT / "scripts" / "icons.json"

DISPLAY = "Inter, 'Segoe UI', system-ui, -apple-system, Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

# --------------------------------------------------------------------------- #
# design system - every visual in the profile is built from these values only
# --------------------------------------------------------------------------- #

# Type scale: Major Third 1.25 -> 12 14 16 18 20 24 30 36 48 60 72 96
T_XS, T_SM, T_MD, T_LG, T_XL = 12, 14, 16, 18, 20
T_2XL, T_3XL, T_4XL, T_5XL, T_6XL = 24, 30, 36, 48, 60
T_7XL = 72

# Weights: regular / semibold / bold. Nothing else.
W_REG, W_SEMI, W_BOLD = 400, 600, 700

# Colour: GitHub's own dark palette. Muted ink is #8b949e (6.15:1 on the
# panel), never #6e7681 (4.12:1 - below the WCAG AA floor for small text).
BG, SURFACE, BORDER, GRID = "#0d1117", "#161b22", "#30363d", "#21262d"
INK, INK_2, INK_3 = "#e6edf3", "#c9d1d9", "#8b949e"
GREEN, BLUE, AMBER, PINK = "#3fb949", "#58a6ff", "#d29922", "#f778ba"

# Radii: one card radius, one chip radius, one bar radius.
R_CARD, R_CHIP, R_BAR = 12, 6, 2

# Spacing: 8pt scale.
S_XS, S_S, S_M, S_L, S_XL, S_2XL = 8, 16, 24, 32, 48, 64

_FONT_CACHE: dict = {}

IDENTITY = [
    ("name", "Abdul Manan \u00b7 CH Manan"),
    ("role", "Founder & Principal Web Engineer @ CYNEX Studio"),
    ("study", "BSCS @ University of Azad Jammu & Kashmir"),
    ("base", "Muzaffarabad, Azad Kashmir"),
    ("builds", "Next.js \u00b7 React \u00b7 TypeScript \u00b7 Tailwind \u00b7 Three.js"),
    ("security", "AUTOCORE \u00b7 TryHackMe \u00b7 Kali \u00b7 Fedora"),
    ("live", "cynex.online"),
]

# The hero terminal has to fit two columns on some bands and one on others,
# so the values it prints are short enough for either. The full story is in
# the markdown under the hero and in the artwork's alt text.
IDENTITY_SHORT = [
    ("name", "Abdul Manan"),
    ("role", "CYNEX Studio"),
    ("study", "BSCS - UAJK"),
    ("base", "Muzaffarabad, AK"),
    ("builds", "Next.js - React - TS"),
    ("live", "cynex.online"),
]

TILES = [
    {
        "id": "build",
        "label": "BUILD",
        "metric": "platforms",
        "value": 6,
        "headline": "platforms in production",
        "sub": "Next.js \u00b7 TypeScript",
        "accent": BLUE,
        "url": "https://www.cynex.online/works",
    },
    {
        "id": "security",
        "label": "SECURITY",
        "metric": "streak",
        "value": 217,
        "headline": "day contribution streak",
        "sub": "AUTOCORE \u00b7 Kali",
        "accent": GREEN,
        "url": "https://tryhackme.com/p/mananhanif01",
    },
    {
        "id": "studio",
        "label": "STUDIO",
        "metric": "disciplines",
        "value": 10,
        "headline": "engineering disciplines",
        "sub": "3D \u00b7 AI \u00b7 SEO",
        "accent": AMBER,
        "url": "https://www.cynex.online",
    },
]

FEATURED = [
    ("autocore", "Automated pentest recon & enumeration orchestrator"),
    ("CYNEX-Portfolio", "Cyber-themed portfolio with a live system HUD"),
    ("nullshield", "Security services site: pentest, SOC monitoring, hardening"),
    ("ironcore", "IronCore Gym \u2014 dashboard, pricing, programmes, trainers"),
    ("Bus-Reservation-System", "C++ console app: buses, seat reservations, reports"),
    ("flamehouse", "Restaurant template with a one-file token theme system"),
]

REPO_META = {
    "autocore": (
        "Automated pentest recon & enumeration orchestrator \u2014 bash v3 and an AI-powered Python TUI v4 with auto OS detection.",
        "bash \u00b7 python \u00b7 textual \u00b7 llm",
    ),
    "CYNEX-Portfolio": (
        "Cyber-themed portfolio: terminal simulation, intrusion game and a live system HUD.",
        "react \u00b7 vite \u00b7 typescript \u00b7 tailwind",
    ),
    "movixstudio": (
        "Boutique video-editing agency site \u2014 hooks, stories and results.",
        "vite \u00b7 typescript",
    ),
    "movix": (
        "Movix Studio \u2014 premium video agency site, static build.",
        "html \u00b7 css \u00b7 js",
    ),
    "super-marketing": (
        "Super Marketing Pvt. Ltd \u2014 real-estate agency site with property listings, services and WhatsApp contact.",
        "html \u00b7 css \u00b7 js",
    ),
    "ironcore": (
        "IronCore Gym \u2014 fitness site with dashboard, pricing, programmes and trainers.",
        "html \u00b7 css \u00b7 js",
    ),
    "portfolio": (
        "Personal portfolio \u2014 3D layered multi-page build with timeline, skills and project lab.",
        "html \u00b7 css \u00b7 js",
    ),
    "flamehouse": (
        "Restaurant site template with a one-file token theme system (restaurant, gym, cafe).",
        "html \u00b7 css \u00b7 js",
    ),
    "nullshield": (
        "NullShield Security \u2014 pentest, SOC monitoring and defensive hardening services site.",
        "html \u00b7 css \u00b7 js",
    ),
    "novamind-ai": (
        "NovaMind AI \u2014 SaaS landing template (demo brand, front-end showcase).",
        "html \u00b7 css \u00b7 js",
    ),
    "mac-vision": (
        "Mac Vision \u2014 Apple & tech reseller store template (demo brand).",
        "html \u00b7 css \u00b7 js",
    ),
    "Bus-Reservation-System": (
        "Console app \u2014 add buses, reserve seats, print reports, file-based storage, no database.",
        "c++ \u00b7 file storage",
    ),
    "Abdul-Manan-C": (
        "This profile \u2014 README plus the generator that renders its own console art.",
        "markdown \u00b7 python",
    ),
    "MY_HTML-PRACTICE": (
        "ChatGPT-style blog UI \u2014 front-end practice build.",
        "html \u00b7 css \u00b7 js",
    ),
}

LANG_COLOURS = {
    "Python": "#3572A5",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "C++": "#f34b7d",
    "C": "#555555",
    "Bash": "#89e051",
    "Shell": "#89e051",
    "Java": "#b07219",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "PHP": "#4F5D95",
    "Ruby": "#701516",
    "Dart": "#00B4AB",
    "Swift": "#F05138",
    "Kotlin": "#A97BFF",
    "Markdown": "#083fa1",
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def api(path: str) -> object:
    return json.loads(http_get(f"{API}{path}").decode("utf-8"))


def fetch_profile() -> dict:
    return api(f"/users/{USER}")


def fetch_repos() -> list:
    repos = api(f"/users/{USER}/repos?per_page=100&sort=pushed")
    return [r for r in repos if not r.get("fork")]


def fetch_contributions() -> tuple:
    """Return (official_total, days) where days is [(iso_date, level, count)].

    The calendar fragment ships an exact count in each day's tooltip, so the
    chart can show real contribution counts rather than a 0-4 heat level.
    """
    raw = http_get(f"https://github.com/users/{USER}/contributions").decode("utf-8", "replace")
    total = None
    match = re.search(r"([\d,]+)\s+contributions\s+in the last year", raw)
    if match:
        total = int(match.group(1).replace(",", ""))

    days = []
    pattern = (
        r'<td[^>]*data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d)"[^>]*>.*?</td>'
        r'\s*<tool-tip[^>]*>([^<]*)</tool-tip>'
    )
    for day, level, tip in re.findall(pattern, raw, re.S):
        count = 0
        counted = re.match(r"(\d+) contributions? on", tip)
        if counted:
            count = int(counted.group(1))
        days.append((day, int(level), count))
    if not days:
        raise RuntimeError("contributions calendar did not parse")
    return total, days


def streaks(days: list) -> tuple:
    levels = dict((d, l) for d, l, _ in days)
    today = date.today()
    current = 0
    cursor = today
    if levels.get(cursor.isoformat(), 0) == 0:
        cursor = date.fromordinal(cursor.toordinal() - 1)
    while levels.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor = date.fromordinal(cursor.toordinal() - 1)
    longest = 0
    run = 0
    for _, level, _ in sorted(days):
        run = run + 1 if level > 0 else 0
        longest = max(longest, run)
    return current, longest


def monthly_totals(days: list) -> list:
    buckets = {}
    for day, _, count in days:
        key = day[:7]
        buckets[key] = buckets.get(key, 0) + count
    ordered = sorted(buckets.items())
    return [{"key": key, "label": MONTHS[int(key[5:7]) - 1], "count": count} for key, count in ordered][-12:]


def relative_days(stamp: str) -> str:
    try:
        when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    days = (datetime.now(timezone.utc) - when).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def build_snapshot() -> dict:
    profile = fetch_profile()
    repos = fetch_repos()
    total, days = fetch_contributions()
    current, longest = streaks(days)

    public = []
    for repo in repos:
        public.append(
            {
                "name": repo["name"],
                "url": repo["html_url"],
                "language": repo.get("language"),
                "stars": repo.get("stargazers_count", 0),
                "pushed_at": repo.get("pushed_at", ""),
                "description": repo.get("description") or "",
            }
        )
    public.sort(key=lambda r: r["pushed_at"], reverse=True)

    active = [d for d in days if d[2] > 0]
    busiest = max(days, key=lambda d: d[2]) if days else ("", 0, 0)
    monthly = monthly_totals(days)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "login": profile["login"],
        "name": profile.get("name") or USER,
        "followers": profile.get("followers", 0),
        "public_repos": len(public),
        "public_repos_total": profile.get("public_repos", len(public)),
        "contributions": total if total is not None else sum(d[2] for d in days),
        "current_streak": current,
        "longest_streak": longest,
        "active_days": len(active),
        "total_stars": sum(r["stars"] for r in public),
        "busiest_day": {"date": busiest[0], "count": busiest[2]},
        "busiest_month": max(monthly, key=lambda m: m["count"]) if monthly else {"label": "-", "count": 0},
        "monthly": monthly,
        "repos": public,
    }


# --------------------------------------------------------------------------- #
# type: embedded Google Fonts
# --------------------------------------------------------------------------- #


def _subset_base64(font_path: Path, characters: set) -> str:
    """Base64 WOFF2 for this font, cut down to the glyphs actually drawn.

    GitHub serves README images through camo and an SVG loaded through <img>
    cannot fetch anything, so the only way to get real Inter / JetBrains Mono
    into the artwork is to carry the font inside the file. The build keeps the
    raw font on disk and embeds a per-card subset, which is roughly a tenth
    of the size of the full face.
    """
    key = (str(font_path), tuple(sorted(characters)))
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    raw = font_path.read_bytes()
    try:
        from fontTools.subset import Options, Subsetter
        from fontTools.ttLib import TTFont

        font = TTFont(io.BytesIO(raw))
        # Without this the head table's modified timestamp is stamped with the
        # current time, so every daily rebuild produces a byte-different (but
        # visually identical) font and the repository history fills up with
        # noise. The artwork must be reproducible.
        font.recalcTimestamp = False
        options = Options()
        options.flavor = "woff2"
        options.layout_features = ["kern", "liga", "calt", "ccmp", "locl"]
        options.hinting = False
        options.desubroutinize = True
        options.notdef_outline = True
        options.recalc_bounds = False
        options.name_IDs = ["*"]
        options.drop_tables = []
        options.recalc_timestamp = False
        subsetter = Subsetter(options=options)
        subsetter.populate(unicodes={ord(char) for char in characters if ord(char) > 31})
        subsetter.subset(font)
        buffer = io.BytesIO()
        font.flavor = "woff2"
        font.save(buffer)
        raw = buffer.getvalue()
    except Exception as exc:  # fontTools or brotli missing: ship the full face
        print(f"note: font subsetting unavailable ({exc}); embedding full face", file=sys.stderr)

    encoded = base64.b64encode(raw).decode("ascii")
    _FONT_CACHE[key] = encoded
    return encoded


def _drawn_characters(svg: str) -> set:
    """Every character that is painted in this SVG."""
    characters = set()
    for chunk in re.findall(r">([^<]*)<", svg):
        characters.update(html.unescape(chunk))
    return characters


def embed_fonts(svg: str) -> str:
    """Insert @font-face rules for the families this SVG actually uses."""
    families = []
    if "JetBrains Mono" in svg and FONT_FILES["JetBrains Mono"].exists():
        families.append("JetBrains Mono")
    if "Inter" in svg and FONT_FILES["Inter"].exists():
        families.append("Inter")
    if not families:
        return svg

    characters = _drawn_characters(svg)
    characters.update(" ·—→0123456789")

    faces = []
    for family in families:
        data = _subset_base64(FONT_FILES[family], characters)
        faces.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:100 900;"
            f"font-display:block;src:url(data:font/woff2;base64,{data}) format('woff2')}}"
        )

    style = "<style>" + "".join(faces) + "</style>"
    opening = re.search(r"<svg\b[^>]*>", svg)
    if not opening:
        return svg
    return svg[: opening.end()] + style + svg[opening.end() :]


# --------------------------------------------------------------------------- #
# shared svg helpers
# --------------------------------------------------------------------------- #


def panel(w: int, h: int, rx: int = R_CARD) -> str:
    """A card: flat fill + a single hairline. Depth comes from the fill, not
    from a stack of shadows - and the stroke uses the same radius as the fill
    so there is exactly one corner style in the whole system."""
    return (
        f'<rect width="{w}" height="{h}" rx="{rx}" fill="{BG}"/>'
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="none" stroke="{BORDER}"/>'
    )


def base_style(radar_origin: str = "150px 148px") -> str:
    """Motion rules shared by every card.

    Persistent motion is opt-in through prefers-reduced-motion: no-preference,
    and the static state is always the default so nothing can be left hidden.
    Opacity entrances are SMIL (fail-safe: the base value stays visible even if
    the animation timeline never advances); CSS only ever moves things.

    ``radar_origin`` is where the sweeping dial turns around. It is passed in
    because the dial moves with the band width.
    """
    return (
        "<style>"
        ".cu-static{display:none}"
        f".spin,.print{{transform-box:view-box;transform-origin:{radar_origin}}}"
        ".ping{transform-box:fill-box;transform-origin:center}"
        ".grow{transform-box:fill-box;transform-origin:bottom}"
        "@media (prefers-reduced-motion: reduce){"
        ".cu-motion{display:none}.cu-static{display:inline}"
        ".shine,.ring-pulse{display:none}"
        "}"
        "@media (prefers-reduced-motion: no-preference){"
        ".enter{animation:enter .6s cubic-bezier(.2,.7,.3,1) both}"
        ".grow{animation:grow .6s cubic-bezier(.2,.7,.3,1) both}"
        ".shine{animation:shine 7s ease-in-out infinite}"
        ".ring-pulse{animation:ringpulse 3.2s ease-out infinite}"
        "}"
        "@keyframes enter{from{transform:translateY(10px)}to{transform:none}}"
        "@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
        "@keyframes shine{0%,72%{transform:translateX(-120%)}100%{transform:translateX(420%)}}"
        "@keyframes ringpulse{0%{transform:scale(.5);opacity:.9}70%,100%{transform:scale(2.4);opacity:0}}"
        "</style>"
    )


def fade_in(delay: float, dur: float = 0.6) -> str:
    """SMIL opacity entrance: visible by default, faded in when it runs."""
    return f'<animate attributeName="opacity" from="0" to="1" begin="{delay:.2f}s" dur="{dur:.2f}s" fill="freeze"/>'


def countup(value: int, x: float, y: float, size: int, colour: str, delay: float = 0.0, duration: float = 1.1) -> str:
    """Animated number that ends on the real value and can never hide it.

    The moving group is hidden entirely for reduced-motion users and a static
    copy of the final value is shown instead, so the number is always legible.
    """
    steps = 10 if value > 40 else 6
    values = [round(value * i / steps) for i in range(steps + 1)]
    if values[-1] != value:
        values.append(value)
    step_dur = duration / max(1, len(values) - 1)

    parts = []
    for i, v in enumerate(values[:-1]):
        t = delay + i * step_dur
        parts.append(
            f'<text class="cu-step" x="{x}" y="{y}" font-family="{DISPLAY}" font-size="{size}" '
            f'font-weight="700" fill="{colour}" opacity="0">{v}'
            f'<set attributeName="opacity" to="1" begin="{t:.3f}s" dur="{step_dur:.3f}s" fill="remove"/>'
            f'<set attributeName="opacity" to="0" begin="{t + step_dur:.3f}s" fill="remove"/></text>'
        )
    t_end = delay + (len(values) - 1) * step_dur
    parts.append(
        f'<text class="cu-step" x="{x}" y="{y}" font-family="{DISPLAY}" font-size="{size}" '
        f'font-weight="700" fill="{colour}">{value}'
        f'<set attributeName="opacity" to="0" begin="{delay:.3f}s" fill="freeze"/>'
        f'<set attributeName="opacity" to="1" begin="{t_end:.3f}s" fill="freeze"/></text>'
    )
    static = (
        f'<text class="cu-static" x="{x}" y="{y}" font-family="{DISPLAY}" font-size="{size}" '
        f'font-weight="700" fill="{colour}">{value}</text>'
    )
    return f'<g class="cu-motion">{"".join(parts)}</g>{static}'


def truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "\u2026"


# --------------------------------------------------------------------------- #
# radar - the sweeping dial beside the terminal on wide bands
# --------------------------------------------------------------------------- #

RAD = 116


def radar(cx: float, cy: float, rad: float = RAD) -> str:
    """A radar sweep.

    The dial is drawn around whatever centre it is given, so the same drawing
    works in a wide hero and in a narrower one.
    """
    inner = rad * 0.72
    parts = [
        f'<circle cx="{cx}" cy="{cy}" r="{rad}" fill="none" stroke="#21262d" stroke-width="1"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{inner:.1f}" fill="none" stroke="#1b2028" stroke-width="1"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{rad * 0.45:.1f}" fill="none" stroke="#1b2028" stroke-width="1"/>',
        f'<line x1="{cx}" y1="{cy - rad}" x2="{cx}" y2="{cy + rad}" stroke="#1b2028" stroke-width="1" stroke-dasharray="3 7"/>',
        f'<line x1="{cx - rad}" y1="{cy}" x2="{cx + rad}" y2="{cy}" stroke="#1b2028" stroke-width="1" stroke-dasharray="3 7"/>',
    ]

    span = math.radians(54)
    ex = cx + rad * math.sin(span)
    ey = cy - rad * math.cos(span)
    parts.append(
        f'<g class="spin"><path d="M {cx} {cy} L {cx} {cy - rad} A {rad} {rad} 0 0 1 {ex:.1f} {ey:.1f} Z" '
        f'fill="url(#sweep)" opacity="0.9"/></g>'
    )
    parts.append(
        f'<circle class="spin ring" cx="{cx}" cy="{cy}" r="{rad * 0.31:.1f}" fill="none" '
        f'stroke="#30363d" stroke-width="1" stroke-dasharray="2 6"/>'
    )

    # Four returns on the dial, placed on the ring rather than at fixed
    # pixels so the layout follows the radius.
    for angle, radius, colour in (
        (-38, 0.92, "#3fb949"), (18, 0.80, "#d29922"),
        (142, 0.86, "#58a6ff"), (-104, 0.74, "#3fb949"),
    ):
        theta = math.radians(angle)
        bx = cx + rad * radius * math.sin(theta)
        by = cy - rad * radius * math.cos(theta)
        parts.append(f'<circle class="pulse" cx="{bx:.1f}" cy="{by:.1f}" r="3.5" fill="{colour}"/>')
        parts.append(
            f'<circle class="ping" cx="{bx:.1f}" cy="{by:.1f}" r="3.5" fill="none" stroke="{colour}" '
            f'stroke-width="1" opacity="0"/>'
        )

    hex_pts = []
    for i in range(6):
        angle = math.radians(90 + i * 60)
        hex_pts.append(f"{cx + rad * 0.22 * math.cos(angle):.1f},{cy + rad * 0.22 * math.sin(angle):.1f}")
    parts.append(
        f'<polygon points="{" ".join(hex_pts)}" fill="#0d1117" stroke="#58a6ff" stroke-width="1.5"/>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + 8}" text-anchor="middle" font-family="{MONO}" font-size="20" '
        f'font-weight="700" fill="#58a6ff">C</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + rad + 30}" text-anchor="middle" font-family="{MONO}" '
        f'font-size="{BAND_MIN_TYPE}" letter-spacing="1.0" fill="#8b949e">CYNEX STUDIO</text>'
    )
    return "".join(parts)


def print_in(delay: float) -> str:
    """Opacity entrance that fails safe: the base value stays visible, the SMIL
    animation only overrides it once it starts (a CSS keyframe would leave the
    text hidden if the animation timeline never advances)."""
    return f'<animate attributeName="opacity" from="0" to="1" begin="{delay:.2f}s" dur="0.45s" fill="freeze"/>'


# --------------------------------------------------------------------------- #
# call to action
# --------------------------------------------------------------------------- #

BTN_H = 52
BTN_R = R_CHIP


def render_button(label: str, width: int, primary: bool) -> str:
    """A real button.

    The README is markdown, so a link can never carry a filled-background
    treatment - this is the only way to give the page a primary action that
    actually looks like one. Primary is a solid brand fill; secondary is an
    outline. Exactly one primary exists on the page.
    """
    if primary:
        fill, stroke, ink = GREEN, GREEN, BG
    else:
        fill, stroke, ink = "none", BORDER, INK_2

    text_x = width / 2
    body = (
        f'<rect x="0.75" y="0.75" width="{width - 1.5}" height="{BTN_H - 1.5}" rx="{BTN_R}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        f'<text x="{text_x}" y="{BTN_H / 2 + 6}" text-anchor="middle" font-family="{DISPLAY}" '
        f'font-size="{T_MD}" font-weight="{W_SEMI}" fill="{ink}" letter-spacing="0">{html.escape(label)}</text>'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{BTN_H}" '
        f'viewBox="0 0 {width} {BTN_H}" role="img" aria-label="{html.escape(label)}">'
        f"{body}</svg>\n"
    )
    return embed_fonts(svg)


# --------------------------------------------------------------------------- #
# tiles
# --------------------------------------------------------------------------- #

TW, TH = 260, 200


def render_tile(tile: dict, index: int) -> str:
    accent = tile["accent"]
    delay = 0.05 + index * 0.16
    shine = (
        f'<g class="shine" opacity="0.5">'
        f'<rect x="-90" y="-40" width="60" height="280" fill="url(#shineGrad)" transform="skewX(-18)"/>'
        f"</g>"
    )
    body = (
        f'<g class="enter" style="animation-delay:{delay:.2f}s">{fade_in(delay)}'
        f'{panel(TW, TH)}'
        f'<defs><linearGradient id="shineGrad" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="#ffffff" stop-opacity="0"/>'
        f'<stop offset="50%" stop-color="#ffffff" stop-opacity="0.10"/>'
        f'<stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>'
        f"</linearGradient></defs>"
        f'{shine}'
        f'<text x="18" y="36" font-family="{MONO}" font-size="{BAND_MIN_TYPE}" letter-spacing="1.0" fill="{accent}">'
        f'{tile["label"]}</text>'
        f'<circle cx="232" cy="30" r="5" fill="{accent}"/>'
        f'<circle class="ring-pulse" cx="232" cy="30" r="7" fill="none" stroke="{accent}" stroke-width="1.2" opacity="0"/>'
        f'{countup(tile["value"], 18, 100, T_4XL, INK, delay + 0.18)}'
        f'<text x="18" y="146" font-family="{DISPLAY}" font-size="{BAND_MIN_TYPE}" font-weight="{W_REG}" fill="{INK_2}">'
        f'{html.escape(fit(tile["headline"], TW - 36, BAND_MIN_TYPE))}</text>'
        f'<text x="18" y="172" font-family="{MONO}" font-size="{BAND_MIN_TYPE}" fill="{INK_3}">'
        f'{html.escape(fit(tile["sub"], TW - 36, BAND_MIN_TYPE, mono=True))}</text>'
        f"</g>"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{TW}" height="{TH}" viewBox="0 0 {TW} {TH}" '
        f'role="img" aria-label="{tile["label"]}: {tile["value"]} {tile["headline"]}">'
        f"{base_style()}{body}</svg>\n"
    )
    return embed_fonts(svg)


SW, SH = 846, 206

STACK = [
    ("FRONTEND", "#58a6ff", ["nextdotjs", "react", "typescript", "tailwindcss", "vite"]),
    ("MOTION / 3D", "#d29922", ["threedotjs", "gsap", "framer", "webgl"]),
    ("BACKEND / DATA", "#3fb949", ["nodedotjs", "python", "postgresql", "prisma", "postman"]),
    ("SECURITY / OPS", "#f778ba", ["kalilinux", "gnubash", "burpsuite", "wireshark", "docker"]),
]

# Optical centring: a few marks are wide-and-flat (GSAP, Tailwind) or
# narrow (Framer), so they are nudged into the middle of their 28px cell
# instead of hanging from the top-left of it.
ICON_OFFSETS = {
    "react": (0.0, 1.5),
    "tailwindcss": (0.0, 5.6),
    "vite": (0.0, 0.7),
    "gsap": (0.0, 8.9),
    "framer": (4.7, 0.0),
    "webgl": (0.0, 8.2),
    "nodedotjs": (1.6, 0.0),
    "python": (0.2, 0.0),
    "postgresql": (0.5, 0.0),
    "prisma": (2.4, 0.0),
    "kalilinux": (0.0, 3.6),
    "gnubash": (1.8, 0.0),
    "docker": (0.0, 4.0),
}


def _icons() -> dict:
    if not ICON_FILE.exists():
        return {}
    return json.loads(ICON_FILE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# connect row - one 44x44 tile per channel
# --------------------------------------------------------------------------- #

CONNECT = [
    ("github", "GitHub"),
    ("linkedin", "LinkedIn"),
    ("instagram", "Instagram"),
    ("fiverr", "Fiverr"),
    ("tryhackme", "TryHackMe"),
    ("whatsapp", "WhatsApp"),
    ("mail", "Email"),
]

CONNECT_SIZE = 44
CONNECT_GLYPH = 24


def render_connect_icon(item: dict) -> str:
    """A 44x44 tile - the glyph is 24px, so the tap target clears 44px."""
    scale = CONNECT_GLYPH / (24 if item["slug"] != "linkedin" else 448)
    height = CONNECT_GLYPH if item["slug"] != "linkedin" else CONNECT_GLYPH * (512 / 448)
    pad = (CONNECT_SIZE - CONNECT_GLYPH) / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CONNECT_SIZE}" height="{CONNECT_SIZE}" '
        f'viewBox="0 0 {CONNECT_SIZE} {CONNECT_SIZE}" role="img" aria-label="{html.escape(item["title"])}">'
        f'<g transform="translate({pad:.1f},{(CONNECT_SIZE - height) / 2:.1f}) scale({scale:.4f})">'
        f"<title>{html.escape(item['title'])}</title>"
        f'<path d="{item["path"]}" fill="{item["hex"]}"/></g></svg>\n'
    )


# --------------------------------------------------------------------------- #
# viewport bands
#
# GitHub's README column is fluid, not fixed. Measured live:
#
#     viewport <  768   column = viewport - 82     (phone / tablet)
#     768..1011         column = viewport - 370    (the profile sidebar appears)
#     1012..1279        column = viewport - 434    (wider container)
#     viewport >= 1280  column = 846                (capped)
#
# Artwork drawn at one width is therefore squeezed on some devices and
# stretched on others, and the type inside it shrinks with it: the old
# 846px hero scaled into a 398px column rendered its 14px console lines at
# 6.6px, which is not type, it is texture.
#
# So every visual is drawn once per band, at that band's widest column, and
# the browser picks the copy with <picture><source media="(max-width: ...)">.
# The band table is computed from the measured curve by
# scripts/compute_bands.py and kept in data/bands.json, so the artwork
# follows the real layout instead of a guess.
#
# A band may shrink its artwork by at most 0.75x before it reaches a phone.
# The smallest type any band draws with is therefore 16px, which is still
# 12px on the narrowest screen in the band - the floor below which text
# stops being readable.
# --------------------------------------------------------------------------- #

BANDS_FILE = ROOT / "data" / "bands.json"

BAND_MIN_TYPE = 16
BAND_MIN_RENDERED = 12


def load_bands() -> list[dict]:
    if not BANDS_FILE.exists():
        return []
    return json.loads(BANDS_FILE.read_text(encoding="utf-8"))


def mono_width(text: str, size: int) -> float:
    """JetBrains Mono advances 0.6em for every glyph."""
    return len(text) * size * 0.6


def sans_width(text: str, size: int) -> float:
    """A close-enough Inter width estimate, used for line breaking."""
    narrow = set("iljtfrI.,;:'`|()[]{}!-")
    wide = set("mwMW@%")
    total = 0.0
    for char in text:
        if char in narrow:
            total += 0.30
        elif char in wide:
            total += 0.86
        elif char.isupper():
            total += 0.66
        elif char.isdigit():
            total += 0.57
        else:
            total += 0.53
    return total * size


def fit(text: str, limit: float, size: int, mono: bool = False) -> str:
    """Shorten text until it fits the space it has."""
    measure = mono_width if mono else sans_width
    if measure(text, size) <= limit:
        return text
    ellipsis = "\u2026"
    while text and measure(text + ellipsis, size) > limit:
        text = text[:-1]
    return text.rstrip() + ellipsis


def wrap(text: str, limit: float, size: int, mono: bool = False, lines: int = 2) -> list[str]:
    """Break text into at most `lines` lines that each fit `limit` pixels."""
    measure = mono_width if mono else sans_width
    out: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and measure(candidate, size) > limit:
            out.append(current)
            current = word
            if len(out) == lines:
                break
        else:
            current = candidate
    if current and len(out) < lines:
        out.append(current)
    if out:
        out[-1] = fit(out[-1], limit, size, mono)
    return out


def pack(items: list[str], limit: float, size: int, separator: str = " \u00b7 ") -> list[str]:
    """Lay a list of fragments out over as many lines as they need."""
    measure = mono_width
    lines: list[str] = []
    current = ""
    for item in items:
        candidate = f"{current}{separator}{item}" if current else item
        if current and measure(candidate, size) > limit:
            lines.append(current)
            current = item
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


# --------------------------------------------------------------------------- #
# hero - the terminal, and on wide bands a radar beside it
# --------------------------------------------------------------------------- #

HERO_RADAR_MIN = 520
HERO_CONSOLE_X = 280
HERO_HEIGHT = 320


def hero_prompt(x: int, y: int) -> str:
    return (
        f'<text class="print" x="{x}" y="{y}" font-family="{MONO}" font-size="{BAND_MIN_TYPE}" '
        f'fill="{GREEN}" style="animation-delay:.10s">'
        f'<tspan fill="{GREEN}">cynex@kali</tspan><tspan fill="{INK_3}">:~$ </tspan>'
        f'<tspan fill="{INK_2}">whoami</tspan>{print_in(0.10)}</text>'
    )


def hero_rows(rows: list[tuple[str, str]], x: int, y: int, gap: int) -> list[str]:
    parts = []
    for i, (label, value) in enumerate(rows):
        delay = 0.30 + i * 0.08
        parts.append(
            f'<text class="print" x="{x}" y="{y + i * gap}" font-family="{MONO}" '
            f'font-size="{BAND_MIN_TYPE}" style="animation-delay:{delay:.2f}s">'
            f'<tspan fill="{BLUE}">{html.escape(label.ljust(6))}</tspan>'
            f'<tspan fill="{INK_2}">{html.escape(value)}</tspan>{print_in(delay)}</text>'
        )
    return parts


def hero_stats(snapshot: dict, x: int, y: int, limit: float) -> tuple[list[str], int]:
    """The live counters, wrapped into as many lines as the space needs."""
    items = [
        f"{snapshot['contributions']} contributions",
        f"{snapshot['current_streak']}d streak",
        f"{snapshot['followers']} followers",
        f"{snapshot['total_stars']} stars",
    ]
    lines = pack(items, limit, BAND_MIN_TYPE)
    parts = []
    for i, line in enumerate(lines):
        delay = 1.05 + i * 0.10
        parts.append(
            f'<text class="print" x="{x}" y="{y + i * 22}" font-family="{MONO}" '
            f'font-size="{BAND_MIN_TYPE}" fill="{INK_3}" style="animation-delay:{delay:.2f}s">'
            f"{html.escape(line)}{print_in(delay)}</text>"
        )
    return parts, len(lines)


def render_hero_band(snapshot: dict, width: int) -> tuple[str, int]:
    """The hero, drawn at the width of the band it belongs to.

    Two compositions. A wide band gets the radar and the terminal side by
    side; a narrow band gets the terminal alone, because a radar and a
    terminal that can still be read do not both fit in 400px.
    """
    if width >= HERO_RADAR_MIN:
        return _hero_radar(snapshot, width)
    return _hero_terminal(snapshot, width)


def _hero_radar(snapshot: dict, width: int) -> tuple[str, int]:
    console_x = HERO_CONSOLE_X
    console_w = width - console_x - 24
    parts = [radar(140, 160, 116)]
    parts.append(hero_prompt(console_x, 44))
    parts.extend(hero_rows(IDENTITY_SHORT, console_x, 84, 30))
    stats, _ = hero_stats(snapshot, console_x, 290, console_w)
    parts.extend(stats)
    parts.append(f'<circle class="live" cx="{console_x + 6}" cy="286" r="3.5" fill="{GREEN}"/>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{HERO_HEIGHT}" '
        f'viewBox="0 0 {width} {HERO_HEIGHT}" role="img" aria-label="Abdul Manan \u2014 founder of '
        f'CYNEX Studio, BScS at UAJK, building with Next.js, React and TypeScript">'
        f"{base_style('140px 160px')}{panel(width, HERO_HEIGHT)}{''.join(parts)}</svg>\n"
    )
    return embed_fonts(svg), HERO_HEIGHT


def _hero_terminal(snapshot: dict, width: int) -> tuple[str, int]:
    pad = 14
    content = width - pad * 2
    parts = [hero_prompt(pad, 32)]
    parts.extend(hero_rows(IDENTITY_SHORT, pad, 62, 28))

    stat_y = 232
    stats, lines = hero_stats(snapshot, pad, stat_y, content)
    parts.extend(stats)
    parts.append(f'<circle class="live" cx="{pad + 6}" cy="{stat_y - 4}" r="3.5" fill="{GREEN}"/>')

    height = stat_y + lines * 22 + 18
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Abdul Manan \u2014 founder of '
        f'CYNEX Studio, BScS at UAJK, building with Next.js, React and TypeScript">'
        f"<style>"
        f".print{{transform-box:view-box;transform-origin:0 0}}"
        f"@media (prefers-reduced-motion: no-preference){{"
        f".print{{animation:rise .5s ease-out both}}"
        f".live{{animation:pulse 2.6s ease-in-out infinite}}"
        f"}}"
        f"@keyframes rise{{from{{transform:translateY(6px)}}to{{transform:translateY(0)}}}}"
        f"@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}"
        f"</style>"
        f'<rect width="{width}" height="{height}" rx="{R_CARD}" fill="{BG}"/>'
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="{R_CARD}" '
        f'fill="none" stroke="{BORDER}"/>'
        f'{"".join(parts)}</svg>\n'
    )
    return embed_fonts(svg), height


# --------------------------------------------------------------------------- #
# toolbelt
# --------------------------------------------------------------------------- #

STACK_ICON_TOP = 32
STACK_ROW_H = 76


def render_stack_band(width: int) -> tuple[str, int]:
    """The toolbelt: official brand marks, grouped by what they are for.

    No word labels - the marks are the labels. Every icon keeps a <title> so
    the artwork still names itself for screen readers and for anyone who
    inspects the SVG. The grouping changes with the band: four across when
    there is room, two by two in the middle, one column on a phone.
    """
    icons = _icons()
    pad = 16
    gutter = 16

    if width >= 740:
        columns, icon_size, icon_gap = 4, 26, 8
    elif width >= 400:
        columns, icon_size, icon_gap = 2, 28, 10
    else:
        columns, icon_size, icon_gap = 1, 28, 10
    rows = math.ceil(len(STACK) / columns)
    cell_w = (width - pad * 2 - gutter * (columns - 1)) / columns

    height = 24 + rows * STACK_ROW_H + 16
    parts = [f'<g class="enter">{fade_in(0.08)}{panel(width, height)}']

    for index, (label, accent, slugs) in enumerate(STACK):
        column, row = divmod(index, columns)
        x = pad + column * (cell_w + gutter)
        top = 24 + row * STACK_ROW_H

        if column:
            parts.append(
                f'<line x1="{x - gutter / 2:.1f}" y1="30" x2="{x - gutter / 2:.1f}" y2="{height - 26}" '
                f'stroke="#21262d" stroke-width="1"/>'
            )

        parts.append(
            f'<text x="{x:.1f}" y="{top + 12}" font-family="{MONO}" font-size="{BAND_MIN_TYPE}" '
            f'letter-spacing="1.0" fill="{accent}">{html.escape(label)}</text>'
        )
        parts.append(
            f'<rect x="{x:.1f}" y="{top + 20}" width="30" height="2" rx="{R_BAR}" '
            f'fill="{accent}" opacity="0.7"/>'
        )

        row_icons = [icons.get(slug) for slug in slugs]
        row_icons = [item for item in row_icons if item]
        if not row_icons:
            continue
        total = len(row_icons) * icon_size + (len(row_icons) - 1) * icon_gap
        start = x + (cell_w - total) / 2
        for position, item in enumerate(row_icons):
            slug = item["slug"]
            ix = start + position * (icon_size + icon_gap)
            scale = icon_size / 24
            dx, dy = ICON_OFFSETS.get(slug, (0.0, 0.0))
            parts.append(
                f'<g transform="translate({ix + dx:.2f},{top + STACK_ICON_TOP + dy:.2f}) '
                f'scale({scale:.4f})" opacity="0.95">'
                f"<title>{html.escape(item['title'])}</title>"
                f'<path d="{item["path"]}" fill="{item["hex"]}"/></g>'
            )

    parts.append(
        f'<text x="{width - pad}" y="{height - 14}" text-anchor="end" font-family="{MONO}" '
        f'font-size="{BAND_MIN_TYPE}" fill="{INK_3}">19 TOOLS</text>'
    )
    parts.append("</g>")

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Technology stack: Next.js, React, '
        f'TypeScript, Tailwind CSS, Vite, Three.js, GSAP, Framer, WebGL, Node.js, Python, PostgreSQL, '
        f'Prisma, Postman, Kali Linux, GNU Bash, Burp Suite, Wireshark and Docker">'
        f"{base_style()}{''.join(parts)}</svg>\n"
    )
    return embed_fonts(svg), height


# --------------------------------------------------------------------------- #
# activity
# --------------------------------------------------------------------------- #

def render_activity_band(snapshot: dict, width: int) -> tuple[str, int]:
    """Twelve months of output.

    One job only: show the rhythm of the last year. The headline numbers that
    matter live in the stat tiles, so this chart carries the single total and
    the busiest month - not a second copy of the streak.
    """
    monthly = snapshot["monthly"]
    total = snapshot["contributions"]
    busiest = snapshot["busiest_month"]
    pad = 16
    content = width - pad * 2
    wide = width >= 430

    header = [
        f'<text x="{pad}" y="{30 if wide else 26}" font-family="{MONO}" '
        f'font-size="{BAND_MIN_TYPE}" letter-spacing="1.0" fill="{BLUE}">12-MONTH ACTIVITY</text>',
    ]
    if wide:
        header.append(
            f'<text x="{width - pad}" y="30" text-anchor="end" font-family="{DISPLAY}" '
            f'font-size="24" font-weight="{W_BOLD}" fill="{INK}">{total}'
            f'<tspan font-size="{BAND_MIN_TYPE}" font-weight="{W_REG}" fill="{INK_3}"> contributions</tspan></text>'
        )
        header.append(
            f'<text x="{width - pad}" y="52" text-anchor="end" font-family="{MONO}" '
            f'font-size="{BAND_MIN_TYPE}" fill="{INK_3}">'
            f'{snapshot["active_days"]} active days - best {html.escape(busiest["label"])}</text>'
        )
        top, base = 78, 154
    else:
        header.append(
            f'<text x="{pad}" y="52" font-family="{DISPLAY}" font-size="24" '
            f'font-weight="{W_BOLD}" fill="{INK}">{total}'
            f'<tspan font-size="{BAND_MIN_TYPE}" font-weight="{W_REG}" fill="{INK_3}"> contributions</tspan></text>'
        )
        header.append(
            f'<text x="{pad}" y="74" font-family="{MONO}" font-size="{BAND_MIN_TYPE}" fill="{INK_3}">'
            f'best {html.escape(busiest["label"])}</text>'
        )
        top, base = 96, 164

    max_count = max([m["count"] for m in monthly] or [1])
    slot = content / len(monthly) if monthly else content
    bar_w = max(6, slot - 6)
    best = max(monthly, key=lambda m: m["count"])["key"] if monthly else None
    bars = []

    for i, month in enumerate(monthly):
        bx = pad + i * slot
        height = 8 + int((month["count"] / max_count) * (base - top - 12)) if max_count else 8
        colour = GREEN if month["key"] == best else "#2ea043"
        delay = 0.15 + i * 0.05
        bars.append(
            f'<g class="grow" style="animation-delay:{delay:.2f}s">'
            f'<rect x="{bx:.1f}" y="{base - height}" width="{bar_w:.1f}" height="{height}" '
            f'rx="{R_BAR}" fill="{colour}"/></g>'
        )
        # A month label only appears when it has room. On a phone every other
        # month is named; the other six bars are still there.
        if slot >= 40 or i % 2 == 0:
            bars.append(
                f'<text x="{bx + bar_w / 2:.1f}" y="{base + 22}" text-anchor="middle" '
                f'font-family="{MONO}" font-size="{BAND_MIN_TYPE}" fill="{INK_3}">'
                f'{month["label"]}</text>'
            )

    height = base + 42
    body = (
        f'<g class="enter">{fade_in(0.1)}'
        f'{panel(width, height)}{"".join(header)}'
        f'<line x1="{pad}" y1="{base}" x2="{width - pad}" y2="{base}" stroke="{GRID}" stroke-width="1"/>'
        f'{"".join(bars)}</g>'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Contribution activity: '
        f'{total} contributions over the last 12 months">'
        f"{base_style()}{body}</svg>\n"
    )
    return embed_fonts(svg), height


# --------------------------------------------------------------------------- #
# selected work - one grid, drawn to fit the band
# --------------------------------------------------------------------------- #

# A phone has room for one line of description, a desktop has room for two.
# The full wording lives in the repository index further down the page.
FEATURED_SHORT = {
    "autocore": "Pentest recon orchestrator",
    "CYNEX-Portfolio": "Cyber portfolio with a live HUD",
    "nullshield": "Pentest, SOC monitoring and hardening",
    "ironcore": "Gym: dashboard, pricing and programmes",
    "Bus-Reservation-System": "C++ console for buses and seats",
    "flamehouse": "Restaurant template with token themes",
}

WORK_GAP = 12
WORK_CARD_H = 120
WORK_CARD_H_NARROW = 98


def render_work_grid(snapshot: dict, width: int) -> tuple[str, int]:
    """The six featured repositories as one card grid.

    One artwork, not a table of six: a table cannot reflow, so on a phone it
    would squeeze each card into a 92px column. The grid is drawn to the
    band's width instead - two columns where there is room, one where there
    is not - so every card is read at its own size.
    """
    by_name = {r["name"]: r for r in snapshot["repos"]}
    items = []
    for name, description in FEATURED:
        repo = by_name.get(name)
        if repo:
            items.append((repo, description))

    columns = 2 if width >= 620 else 1
    card_w = (width - WORK_GAP * (columns - 1)) / columns
    pad = 16
    inner = card_w - pad * 2
    narrow = columns == 1
    card_h = WORK_CARD_H_NARROW if narrow else WORK_CARD_H
    rows = math.ceil(len(items) / columns)
    height = rows * card_h + (rows - 1) * WORK_GAP

    parts = []
    for index, (repo, description) in enumerate(items):
        column, row = divmod(index, columns)
        x = column * (card_w + WORK_GAP)
        y = row * (card_h + WORK_GAP)
        language = repo.get("language") or "-"
        colour = LANG_COLOURS.get(language, INK_3)
        delay = 0.05 + index * 0.08

        body = [f'<g class="enter" style="animation-delay:{delay:.2f}s">{fade_in(delay)}']
        body.append(f'<g transform="translate({x:.1f},{y:.1f})">')
        body.append(panel(card_w, card_h))
        body.append(
            f'<text x="{pad}" y="30" font-family="{DISPLAY}" font-size="{BAND_MIN_TYPE}" '
            f'font-weight="{W_SEMI}" fill="{INK}">{html.escape(fit(repo["name"], inner, BAND_MIN_TYPE))}</text>'
        )

        if narrow:
            text = FEATURED_SHORT.get(repo["name"], description)
            body.append(
                f'<text x="{pad}" y="54" font-family="{DISPLAY}" font-size="{BAND_MIN_TYPE}" '
                f'fill="{INK_2}">{html.escape(fit(text, inner, BAND_MIN_TYPE))}</text>'
            )
            meta_y = 82
        else:
            for i, line in enumerate(wrap(description, inner, BAND_MIN_TYPE, lines=2)):
                body.append(
                    f'<text x="{pad}" y="{54 + i * 22}" font-family="{DISPLAY}" '
                    f'font-size="{BAND_MIN_TYPE}" fill="{INK_2}">{html.escape(line)}</text>'
                )
            meta_y = 104

        body.append(f'<circle cx="{pad + 6}" cy="{meta_y - 5}" r="4" fill="{colour}"/>')
        body.append(
            f'<text x="{pad + 18}" y="{meta_y}" font-family="{MONO}" font-size="{BAND_MIN_TYPE}" '
            f'fill="{INK_3}">{html.escape(language)}</text>'
        )
        body.append(
            f'<text x="{card_w - pad}" y="{meta_y}" text-anchor="end" font-family="{MONO}" '
            f'font-size="{BAND_MIN_TYPE}" fill="{INK_3}">'
            f'\u2605 {repo["stars"]} \u00b7 {relative_days(repo["pushed_at"])}</text>'
        )
        body.append("</g></g>")
        parts.append("".join(body))

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Selected work: '
        f'autocore, CYNEX Portfolio, nullshield, ironcore, Bus Reservation System and flamehouse">'
        f"{base_style()}{''.join(parts)}</svg>\n"
    )
    return embed_fonts(svg), height


# --------------------------------------------------------------------------- #
# platform gallery
#
# The gallery used to be an HTML table. A table cannot reflow, so on a
# 320px phone GitHub squeezed each of the six screenshots into a 93px
# column and cut the right-hand side off - the table scrolled sideways
# inside its own box and the second platform was simply gone.
#
# So the gallery is artwork now, drawn in three compositions - one column,
# two narrow columns, two wide columns - and the browser picks one by
# viewport, the same way it picks the rest of the profile's art. Each
# screenshot is embedded in the SVG as a data URI, because an SVG loaded
# through <img> may not fetch anything from the network.
# --------------------------------------------------------------------------- #

PLATFORMS = [
    {
        "name": "Laxitech",
        "domain": "laxitech.com",
        "url": "https://laxitech.com/",
        "photo": "assets/screens/m/laxitech.jpg",
        "description": "3D MacBook stage with WebGL aurora lighting.",
    },
    {
        "name": "Vixion Studio",
        "domain": "vixion.studio",
        "url": "https://www.vixion.studio/",
        "photo": "assets/screens/m/vixion.jpg",
        "description": "Dark-to-light scroll; AI concierge to WhatsApp.",
    },
    {
        "name": "Movix Studio",
        "domain": "movixstudio.com",
        "url": "https://www.movixstudio.com/",
        "photo": "assets/screens/m/movix.jpg",
        "description": "Instant HD showreel; indexed on Google in 20 min.",
    },
    {
        "name": "Commerce Lions",
        "domain": "commercelions.com",
        "url": "https://www.commercelions.com/",
        "photo": "assets/screens/m/commerce-lions.jpg",
        "description": "Education portal with protected member accounts.",
    },
    {
        "name": "Super Luxuries",
        "domain": "superluxuries.store",
        "url": "https://www.superluxuries.store/",
        "photo": "assets/screens/m/super-luxuries.jpg",
        "description": "Dubai + London boutique; WhatsApp checkout.",
    },
    {
        "name": "Mac Vision",
        "domain": "macvision.store",
        "url": "https://www.macvision.store/",
        "photo": "assets/screens/m/mac-vision.jpg",
        "description": "Apple reseller; founder-locked owner dashboard.",
    },
]

# The compositions the gallery is drawn in. Which one serves a viewport is
# decided by scripts/compute_bands.py and recorded in data/bands.json.
GALLERY_COMPOSITIONS = {424: 1, 566: 2, 846: 2}

# Every screenshot is 400x250 - 1.6:1 - so the photo slot keeps that ratio
# and the image is never letterboxed or cropped.
PHOTO_RATIO = 1.6


def _photo_data(path: Path) -> str:
    """A screenshot as a data URI, for embedding inside the SVG."""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def render_gallery(width: int, columns: int) -> tuple[str, int]:
    """The six client platforms, as artwork.

    One column on a phone, two where there is room. Each card carries the
    screenshot, the brand and the domain, so the picture is worth something
    even before the list underneath it is read.
    """
    pad = 12
    gap = 12
    card_w = (width - gap * (columns - 1)) / columns
    photo_w = card_w - pad * 2
    photo_h = photo_w / PHOTO_RATIO

    # The type has to survive the scale the band puts on it, so the narrow
    # composition - the one that shrinks hardest - carries larger type.
    name_size = 24
    domain_size = 24 if columns == 1 else 20
    name_y = pad + photo_h + 28
    domain_y = name_y + 30
    card_h = domain_y + 12

    rows = math.ceil(len(PLATFORMS) / columns)
    height = rows * card_h + (rows - 1) * gap

    parts = []
    for index, platform in enumerate(PLATFORMS):
        column, row = divmod(index, columns)
        x = column * (card_w + gap)
        y = row * (card_h + gap)
        delay = 0.04 + index * 0.07

        photo = ROOT / platform["photo"]
        if not photo.exists():
            continue

        body = [f'<g class="enter" style="animation-delay:{delay:.2f}s">{fade_in(delay)}']
        body.append(f'<g transform="translate({x:.1f},{y:.1f})">')
        body.append(panel(card_w, card_h))
        body.append(
            f'<defs><clipPath id="g{index}"><rect x="{pad}" y="{pad}" width="{photo_w:.1f}" '
            f'height="{photo_h:.1f}" rx="{R_CHIP}"/></clipPath></defs>'
        )
        body.append(
            f'<image x="{pad}" y="{pad}" width="{photo_w:.1f}" height="{photo_h:.1f}" '
            f'preserveAspectRatio="xMidYMid slice" clip-path="url(#g{index})" '
            f'href="data:image/jpeg;base64,{_photo_data(photo)}"/>'
        )
        body.append(
            f'<text x="{pad}" y="{name_y:.1f}" font-family="{DISPLAY}" font-size="{name_size}" '
            f'font-weight="{W_SEMI}" fill="{INK}">{html.escape(platform["name"])}</text>'
        )
        body.append(
            f'<text x="{pad}" y="{domain_y:.1f}" font-family="{MONO}" font-size="{domain_size}" '
            f'fill="{INK_3}">{html.escape(platform["domain"])}</text>'
        )
        body.append("</g></g>")
        parts.append("".join(body))

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height:.0f}" '
        f'viewBox="0 0 {width} {height:.0f}" role="img" aria-label="Six client platforms in '
        f'production: Laxitech, Vixion Studio, Movix Studio, Commerce Lions, Super Luxuries '
        f'and Mac Vision">'
        f"{base_style()}{''.join(parts)}</svg>\n"
    )
    return embed_fonts(svg), round(height)


def render_platform_list() -> str:
    """The six platforms as links, one sentence each.

    The artwork cannot be a link - an SVG loaded through <img> carries no
    anchors - so the writing and the links live here, under the pictures.
    """
    lines = [
        f"**[{platform['name']}]({platform['url']})** \u2014 {platform['description']}"
        for platform in PLATFORMS
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# README repository index
# --------------------------------------------------------------------------- #

START = "<!-- AUTO:REPOS:START -->"
END = "<!-- AUTO:REPOS:END -->"


def render_repo_index(snapshot: dict) -> str:
    """The complete public index, folded behind a disclosure.

    Sorted by stars, not by date: a visitor scans and satisfices - they take
    the first reasonable option - so the best work has to come first.

    It sits inside a <details> on purpose. Measured against the rendered
    page, an always-open fourteen-row table carried 30% of the page's
    detail energy - four times the hero - so the squint test landed on a
    reference table instead of on the person. GitHub keeps <details>, so
    the full index stays one click away without out-shouting the work.
    """
    rows = []
    ordered = sorted(snapshot["repos"], key=lambda r: (-r["stars"], r["pushed_at"]), reverse=False)
    for repo in ordered:
        name = repo["name"]
        description, stack = REPO_META.get(
            name,
            (repo.get("description") or "Public repository.", repo.get("language") or "\u2014"),
        )
        lang = repo.get("language")
        stack_cell = f"`{lang}`" if lang and lang in stack else stack
        rows.append(
            f"| **[{name}]({repo['url']})** | {description} | {stack_cell} | "
            f"{repo['stars']} | {relative_days(repo['pushed_at'])} |"
        )
    body = "\n".join(rows)
    count = len(rows)
    return (
        f"{START}\n"
        f"<details>\n"
        f"<summary><b>All {count} public repositories</b> &mdash; what it is, the stack, "
        f"stars and last push</summary>\n\n"
        "| Repository | What it is | Stack | \u2605 | Last push |\n"
        "|---|---|---|---|---|\n"
        f"{body}\n\n"
        "</details>\n"
        f"{END}"
    )


def update_readme(text: str, block: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        print("warning: auto block markers not found in README.md", file=sys.stderr)
        return text
    return pattern.sub(lambda _: block, text)


# --------------------------------------------------------------------------- #
# README blocks - the artwork the generator owns
# --------------------------------------------------------------------------- #

BLOCKS = {
    "HERO": ("<!-- AUTO:HERO:START -->", "<!-- AUTO:HERO:END -->"),
    "STACK": ("<!-- AUTO:STACK:START -->", "<!-- AUTO:STACK:END -->"),
    "WORK": ("<!-- AUTO:WORK:START -->", "<!-- AUTO:WORK:END -->"),
    "ACTIVITY": ("<!-- AUTO:ACTIVITY:START -->", "<!-- AUTO:ACTIVITY:END -->"),
    "GALLERY": ("<!-- AUTO:GALLERY:START -->", "<!-- AUTO:GALLERY:END -->"),
}


def replace_block(text: str, name: str, body: str) -> str:
    """Swap the contents of a marked block in the README."""
    start, end = BLOCKS[name.upper()]
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        print(f"warning: {name} block markers not found in README.md", file=sys.stderr)
        return text
    return pattern.sub(lambda _: f"{start}\n{body}\n{end}", text)


def picture(sources: list[tuple[int, str, int, int]], fallback: tuple[str, int, int], alt: str) -> str:
    """A <picture> with one <source> per band, narrowest band first.

    The ``width`` on each source is what makes the browser size the image to
    the band instead of scaling it down to fit: GitHub keeps the attribute,
    and Chrome lays the <img> box out from the selected source's width.

    The ``height`` is deliberately left off. GitHub's stylesheet clamps an
    image with ``max-width: 100%``, and a clamped width does not drag a
    fixed height along with it - the artwork is then letterboxed inside a
    box that is far taller than it, with dead space above and below. With
    no height the browser keeps the artwork's own proportions.
    """
    lines = ["<picture>"]
    for upper, src, width, height in sources:
        lines.append(
            f'  <source media="(max-width: {upper}px)" srcset="{src}" width="{width}">'
        )
    lines.append(
        f'  <img src="{fallback[0]}" alt="{alt}" width="{fallback[1]}" />'
    )
    lines.append("</picture>")
    return "\n".join(lines)


def build_bands(snapshot: dict) -> dict:
    """Draw every visual once per band and return the README blocks.

    Returns a mapping of block name to (markdown, written files).
    """
    bands = load_bands()
    if not bands:
        raise RuntimeError("data/bands.json is missing - run scripts/compute_bands.py")

    artwork: dict[str, dict[str, tuple[str, int]]] = {"hero": {}, "stack": {}, "activity": {}, "work": {}}

    for band in bands:
        width = band["width"]
        tag = f"-{width}"
        svg, height = render_hero_band(snapshot, width)
        artwork["hero"][tag] = (svg, height)
        svg, height = render_stack_band(width)
        artwork["stack"][tag] = (svg, height)
        svg, height = render_activity_band(snapshot, width)
        artwork["activity"][tag] = (svg, height)
        svg, height = render_work_grid(snapshot, width)
        artwork["work"][tag] = (svg, height)

    alts = {
        "hero": "Abdul Manan \u2014 founder of CYNEX Studio, BScS at UAJK, building with Next.js, React and TypeScript",
        "stack": (
            "Technology stack \u2014 Next.js, React, TypeScript, Tailwind CSS, Vite, Three.js, "
            "GSAP, Framer, WebGL, Node.js, Python, PostgreSQL, Prisma, Postman, Kali Linux, "
            "GNU Bash, Burp Suite, Wireshark and Docker"
        ),
        "activity": (
            f"Contribution activity \u2014 {snapshot['contributions']} contributions over the last 12 months"
        ),
        "work": (
            "Selected work \u2014 autocore, CYNEX Portfolio, nullshield, ironcore, "
            "Bus Reservation System and flamehouse"
        ),
    }

    blocks: dict[str, str] = {}
    for name, files in artwork.items():
        sources = []
        for band in bands[:-1]:
            tag = f"-{band['width']}"
            svg, height = files[tag]
            write(ROOT / "assets" / f"{name}{tag}.svg", svg)
            sources.append((band["upper"], f"./assets/{name}{tag}.svg", band["width"], height))

        last = bands[-1]
        tag = f"-{last['width']}"
        svg, height = files[tag]
        write(ROOT / "assets" / f"{name}{tag}.svg", svg)
        blocks[name] = picture(sources, (f"./assets/{name}{tag}.svg", last["width"], height), alts[name])

    blocks["gallery"] = build_gallery(bands)

    return blocks


def build_gallery(bands: list[dict]) -> str:
    """Draw the platform gallery in its compositions and wire up the <picture>.

    The gallery is not drawn per band: three compositions cover every band,
    and data/bands.json says which composition serves which viewport.
    """
    drawn: dict[int, tuple[str, int]] = {}
    for width, columns in GALLERY_COMPOSITIONS.items():
        drawn[width] = render_gallery(width, columns)

    sources = []
    for band in bands[:-1]:
        width = band["gallery"]
        svg, height = drawn[width]
        write(ROOT / "assets" / f"gallery-{width}.svg", svg)
        src = f"./assets/gallery-{width}.svg"
        if sources and sources[-1][1] == src:
            # the same composition serves this band too - one source is enough
            sources[-1] = (band["upper"], src, width, height)
            continue
        sources.append((band["upper"], src, width, height))

    last = bands[-1]
    width = last["gallery"]
    svg, height = drawn[width]
    write(ROOT / "assets" / f"gallery-{width}.svg", svg)

    return picture(
        sources,
        (f"./assets/gallery-{width}.svg", width, height),
        "Six client platforms in production \u2014 Laxitech, Vixion Studio, Movix Studio, "
        "Commerce Lions, Super Luxuries and Mac Vision",
    ) + "\n\n" + render_platform_list()


def update_readme_alts(text: str, snapshot: dict) -> str:
    """Keep the alt text in step with the numbers in the artwork.

    The figures that move every day - the contribution streak and the yearly
    total - live in the alt text too, so a screen reader is told the same
    story the picture shows.
    """
    text = re.sub(
        r"a \d+-day contribution streak",
        f"a {snapshot['current_streak']}-day contribution streak",
        text,
    )
    text = re.sub(
        r"Contribution activity — \d+ contributions over the last 12 months",
        f"Contribution activity — {snapshot['contributions']} contributions over the last 12 months",
        text,
    )
    return text


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_snapshot(path: Path, snapshot: dict) -> None:
    """Write the live snapshot, but only move its clock when the data moved.

    ``generated_at`` records when this snapshot was taken. If nothing about the
    profile actually changed, the previous snapshot is still an accurate
    description of the account, so its timestamp is kept. That keeps the
    nightly rebuild byte-stable and stops the workflow from committing a
    one-line timestamp diff every morning.
    """
    payload = json.dumps(snapshot, indent=2) + "\n"
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = None
        if isinstance(previous, dict):
            old = {k: v for k, v in previous.items() if k != "generated_at"}
            new = {k: v for k, v in snapshot.items() if k != "generated_at"}
            if old == new and previous.get("generated_at"):
                snapshot = dict(snapshot, generated_at=previous["generated_at"])
                payload = json.dumps(snapshot, indent=2) + "\n"
    write(path, payload)


def main() -> int:
    snapshot_path = ROOT / "data" / "profile.json"
    try:
        snapshot = build_snapshot()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, ValueError) as exc:
        print(f"warning: live fetch failed ({exc}); keeping previous snapshot", file=sys.stderr)
        return 0

    write_snapshot(snapshot_path, snapshot)

    write(ROOT / "assets" / "cta-primary.svg", render_button("Work with me", 168, True))
    write(ROOT / "assets" / "cta-secondary.svg", render_button("Browse all repos", 192, False))

    cards = ROOT / "assets" / "cards"
    for index, tile in enumerate(TILES):
        tile = dict(tile)
        if tile["id"] == "security":
            tile["value"] = snapshot["current_streak"]
        write(cards / f"tile-{tile['id']}.svg", render_tile(tile, index))

    # One copy of every full-width visual per viewport band.
    blocks = build_bands(snapshot)

    icon_dir = ROOT / "assets" / "icons"
    icons = _icons()
    for slug, _label in CONNECT:
        item = icons.get(slug)
        if item:
            write(icon_dir / f"{slug}.svg", render_connect_icon(item))

    readme_path = ROOT / "README.md"
    if readme_path.exists():
        current = readme_path.read_text(encoding="utf-8")
        updated = update_readme(current, render_repo_index(snapshot))
        for name, body in blocks.items():
            updated = replace_block(updated, name, body)
        updated = update_readme_alts(updated, snapshot)
        if updated != current:
            write(readme_path, updated)

    print(
        "profile art rebuilt: "
        f"{snapshot['contributions']} contributions, "
        f"{snapshot['active_days']} active days, "
        f"{snapshot['current_streak']}d streak, "
        f"{snapshot['public_repos']} public repos, "
        f"{snapshot['followers']} followers, "
        f"{snapshot['total_stars']} stars"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
