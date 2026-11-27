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

TILES = [
    {
        "id": "build",
        "label": "BUILD",
        "metric": "platforms",
        "value": 6,
        "headline": "platforms in production",
        "sub": "Next.js \u00b7 TypeScript \u00b7 Tailwind",
        "accent": BLUE,
        "url": "https://www.cynex.online/works",
    },
    {
        "id": "security",
        "label": "SECURITY",
        "metric": "streak",
        "value": 217,
        "headline": "day contribution streak",
        "sub": "AUTOCORE \u00b7 TryHackMe \u00b7 Kali",
        "accent": GREEN,
        "url": "https://tryhackme.com/p/mananhanif01",
    },
    {
        "id": "studio",
        "label": "STUDIO",
        "metric": "disciplines",
        "value": 10,
        "headline": "engineering disciplines",
        "sub": "3D \u00b7 dashboards \u00b7 AI \u00b7 SEO",
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


def base_style() -> str:
    """Motion rules shared by every card.

    Persistent motion is opt-in through prefers-reduced-motion: no-preference,
    and the static state is always the default so nothing can be left hidden.
    Opacity entrances are SMIL (fail-safe: the base value stays visible even if
    the animation timeline never advances); CSS only ever moves things.
    """
    return (
        "<style>"
        ".cu-static{display:none}"
        ".spin,.print{transform-box:view-box;transform-origin:150px 148px}"
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
# hero
# --------------------------------------------------------------------------- #

W, H = 846, 320
CX, CY = 150, 148
RAD = 116


def radar() -> str:
    parts = [
        f'<circle cx="{CX}" cy="{CY}" r="{RAD}" fill="none" stroke="#21262d" stroke-width="1"/>',
        f'<circle cx="{CX}" cy="{CY}" r="84" fill="none" stroke="#1b2028" stroke-width="1"/>',
        f'<circle cx="{CX}" cy="{CY}" r="52" fill="none" stroke="#1b2028" stroke-width="1"/>',
        f'<line x1="{CX}" y1="{CY - RAD}" x2="{CX}" y2="{CY + RAD}" stroke="#1b2028" stroke-width="1" stroke-dasharray="3 7"/>',
        f'<line x1="{CX - RAD}" y1="{CY}" x2="{CX + RAD}" y2="{CY}" stroke="#1b2028" stroke-width="1" stroke-dasharray="3 7"/>',
    ]

    span = math.radians(54)
    ex = CX + RAD * math.sin(span)
    ey = CY - RAD * math.cos(span)
    parts.append(
        f'<g class="spin"><path d="M {CX} {CY} L {CX} {CY - RAD} A {RAD} {RAD} 0 0 1 {ex:.1f} {ey:.1f} Z" '
        f'fill="url(#sweep)" opacity="0.9"/></g>'
    )
    parts.append(
        f'<circle class="spin ring" cx="{CX}" cy="{CY}" r="36" fill="none" stroke="#30363d" stroke-width="1" '
        f'stroke-dasharray="2 6"/>'
    )

    blips = [(116, 108, "#3fb949"), (198, 96, "#d29922"), (188, 198, "#58a6ff"), (104, 182, "#3fb949")]
    for bx, by, colour in blips:
        parts.append(f'<circle class="pulse" cx="{bx}" cy="{by}" r="3.5" fill="{colour}"/>')
        parts.append(
            f'<circle class="ping" cx="{bx}" cy="{by}" r="3.5" fill="none" stroke="{colour}" stroke-width="1" opacity="0"/>'
        )

    hex_pts = []
    for i in range(6):
        angle = math.radians(90 + i * 60)
        hex_pts.append(f"{CX + 26 * math.cos(angle):.1f},{CY + 26 * math.sin(angle):.1f}")
    parts.append(f'<polygon points="{" ".join(hex_pts)}" fill="#0d1117" stroke="#58a6ff" stroke-width="1.5"/>')
    parts.append(
        f'<text x="{CX}" y="{CY + 8}" text-anchor="middle" font-family="{MONO}" font-size="20" '
        f'font-weight="700" fill="#58a6ff">C</text>'
    )
    parts.append(
        f'<text x="{CX}" y="292" text-anchor="middle" font-family="{MONO}" font-size="12" '
        f'letter-spacing="1.5" fill="#8b949e">CYNEX STUDIO</text>'
    )
    return "".join(parts)


def print_in(delay: float) -> str:
    """Opacity entrance that fails safe: the base value stays visible, the SMIL
    animation only overrides it once it starts (a CSS keyframe would leave the
    text hidden if the animation timeline never advances)."""
    return f'<animate attributeName="opacity" from="0" to="1" begin="{delay:.2f}s" dur="0.45s" fill="freeze"/>'


def console(snapshot: dict) -> str:
    parts = []
    parts.append(
        f'<text class="print" x="320" y="44" font-family="{MONO}" font-size="14" fill="#3fb949" '
        f'style="animation-delay:.10s">'
        f'<tspan fill="#3fb949">cynex@kali</tspan><tspan fill="#8b949e">:~$ </tspan>'
        f'<tspan fill="#c9d1d9">whoami</tspan>{print_in(0.10)}</text>'
    )
    for i, (label, value) in enumerate(IDENTITY):
        delay = 0.34 + i * 0.11
        parts.append(
            f'<text class="print" x="320" y="{84 + i * 30}" font-family="{MONO}" font-size="14" '
            f'style="animation-delay:{delay:.2f}s">'
            f'<tspan fill="#58a6ff">{html.escape(label.ljust(9))}</tspan>'
            f'<tspan fill="#c9d1d9">{html.escape(value)}</tspan>{print_in(delay)}</text>'
        )

    cursor_x = 320 + 9 * 9 + len("cynex.online") * 9 + 10
    parts.append(f'<rect class="cursor" x="{cursor_x}" y="248" width="8" height="16" fill="#3fb949"/>')

    stats = (
        f"{snapshot['contributions']} contributions \u00b7 {snapshot['public_repos']} repos \u00b7 "
        f"{snapshot['followers']} followers \u00b7 {snapshot['total_stars']} stars"
    )
    parts.append(f'<circle class="live" cx="326" cy="296" r="3.5" fill="#3fb949"/>')
    parts.append(
        f'<text class="print" x="340" y="300" font-family="{MONO}" font-size="12" fill="#8b949e" '
        f'style="animation-delay:1.25s">{html.escape(stats)}{print_in(1.25)}</text>'
    )
    parts.append(
        f'<text class="print" x="{W - 36}" y="44" text-anchor="end" font-family="{MONO}" font-size="12" '
        f'fill="{INK_3}" style="animation-delay:1.35s">refreshed daily{print_in(1.35)}</text>'
    )
    return "".join(parts)


def render_hero(snapshot: dict) -> str:
    defs = (
        "<defs>"
        '<radialGradient id="sweep" cx="0.5" cy="0.5" r="0.5">'
        '<stop offset="0%" stop-color="#58a6ff" stop-opacity="0.45"/>'
        '<stop offset="70%" stop-color="#58a6ff" stop-opacity="0.12"/>'
        '<stop offset="100%" stop-color="#58a6ff" stop-opacity="0"/>'
        "</radialGradient>"
        '<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">'
        '<rect width="4" height="1" fill="#ffffff" opacity="0.022"/>'
        "</pattern>"
        "</defs>"
    )
    style = (
        "<style>"
        ".spin,.print{transform-box:view-box;transform-origin:150px 148px}"
        ".ping{transform-box:fill-box;transform-origin:center}"
        "@media (prefers-reduced-motion: no-preference){"
        ".spin{animation:sweep 9s linear infinite}"
        ".spin.ring{animation-duration:26s}"
        ".ping{animation:ping 2.6s ease-out infinite}"
        ".pulse,.live{animation:pulse 2.6s ease-in-out infinite}"
        ".live{animation-duration:2s}"
        ".cursor{animation:blink 1.1s steps(1,end) infinite}"
        ".print{animation:rise .5s ease-out both}"
        "}"
        "@keyframes sweep{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}"
        "@keyframes ping{0%{transform:scale(1);opacity:.75}70%,100%{transform:scale(4.5);opacity:0}}"
        "@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}"
        "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}"
        "@keyframes rise{from{transform:translateY(6px)}to{transform:translateY(0)}}"
        "</style>"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="Abdul Manan — CYNEX Studio console profile">'
        f"{defs}{style}"
        f'<rect width="{W}" height="{H}" rx="12" fill="#0d1117"/>'
        f'<rect width="{W}" height="{H}" rx="12" fill="url(#scan)"/>'
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="none" stroke="#30363d"/>'
        f"{radar()}"
        f'<line x1="292" y1="34" x2="292" y2="286" stroke="#21262d" stroke-width="1"/>'
        f"{console(snapshot)}"
        f"</svg>\n"
    )
    return embed_fonts(svg)


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
        f'<text x="18" y="36" font-family="{MONO}" font-size="12" letter-spacing="1.5" fill="{accent}">'
        f'{tile["label"]}</text>'
        f'<circle cx="232" cy="30" r="5" fill="{accent}"/>'
        f'<circle class="ring-pulse" cx="232" cy="30" r="7" fill="none" stroke="{accent}" stroke-width="1.2" opacity="0"/>'
        f'{countup(tile["value"], 18, 100, T_4XL, INK, delay + 0.18)}'
        f'<text x="18" y="146" font-family="{DISPLAY}" font-size="{T_SM}" font-weight="{W_REG}" fill="{INK_2}">'
        f'{tile["headline"]}</text>'
        f'<text x="18" y="170" font-family="{MONO}" font-size="{T_XS}" fill="{INK_3}">{tile["sub"]}</text>'
        f"</g>"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{TW}" height="{TH}" viewBox="0 0 {TW} {TH}" '
        f'role="img" aria-label="{tile["label"]}: {tile["value"]} {tile["headline"]}">'
        f"{base_style()}{body}</svg>\n"
    )
    return embed_fonts(svg)


# --------------------------------------------------------------------------- #
# repo cards
# --------------------------------------------------------------------------- #

CW, CH = 396, 150


def render_repo_card(repo: dict, description: str, index: int) -> str:
    language = repo.get("language") or "—"
    colour = LANG_COLOURS.get(language, "#8b949e")
    delay = 0.05 + index * 0.12
    body = (
        f'<g class="enter" style="animation-delay:{delay:.2f}s">{fade_in(delay)}'
        f'{panel(CW, CH)}'
        f'<text x="18" y="36" font-family="{DISPLAY}" font-size="16" font-weight="600" fill="#e6edf3">'
        f'{html.escape(repo["name"])}</text>'
        f'<text x="18" y="60" font-family="{DISPLAY}" font-size="12" fill="#8b949e">'
        f'{html.escape(truncate(description, 58))}</text>'
        f'<circle cx="22" cy="122" r="4" fill="{colour}"/>'
        f'<text x="33" y="126" font-family="{MONO}" font-size="12" fill="#8b949e">{html.escape(language)}</text>'
        f'<text x="378" y="126" text-anchor="end" font-family="{MONO}" font-size="{T_XS}" fill="{INK_3}">'
        f'\u2605 {repo["stars"]} \u00b7 {relative_days(repo["pushed_at"])}</text>'
        f"</g>"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CW}" height="{CH}" viewBox="0 0 {CW} {CH}" '
        f'role="img" aria-label="{html.escape(repo["name"])} — {html.escape(description)}">'
        f"{base_style()}{body}</svg>\n"
    )
    return embed_fonts(svg)


# --------------------------------------------------------------------------- #
# activity chart
# --------------------------------------------------------------------------- #

AW, AH = 846, 210


def render_activity(snapshot: dict) -> str:
    """Twelve months of output.

    One job only: show the rhythm of the last year. The headline numbers that
    matter live in the stat tiles, so this chart carries the single total and
    the busiest month - not a second copy of the streak.
    """
    monthly = snapshot["monthly"]
    total = snapshot["contributions"]
    busiest = snapshot["busiest_month"]

    header = [
        f'<text x="36" y="36" font-family="{MONO}" font-size="{T_SM}" letter-spacing="1.5" fill="{BLUE}">12-MONTH ACTIVITY</text>',
        f'<text x="{AW - 36}" y="36" text-anchor="end" font-family="{DISPLAY}" font-size="{T_XL}" '
        f'font-weight="{W_BOLD}" fill="{INK}">{total}<tspan font-size="{T_MD}" font-weight="{W_REG}" '
        f'fill="{INK_3}"> contributions</tspan></text>',
        f'<text x="{AW - 36}" y="58" text-anchor="end" font-family="{MONO}" font-size="{T_XS}" fill="{INK_3}">'
        f'{snapshot["active_days"]} active days   ·   best month {html.escape(busiest["label"])}</text>',
    ]

    top = 88
    base = 166
    max_count = max([m["count"] for m in monthly] or [1])
    slot = 66
    bar_w = 46
    start_x = 36
    bars = []
    best = max(monthly, key=lambda m: m["count"])["key"] if monthly else None

    for i, month in enumerate(monthly):
        bx = start_x + i * slot
        height = 8 + int((month["count"] / max_count) * (base - top - 12)) if max_count else 8
        colour = GREEN if month["key"] == best else "#2ea043"
        delay = 0.15 + i * 0.06
        bars.append(
            f'<g class="grow" style="animation-delay:{delay:.2f}s">'
            f'<rect x="{bx}" y="{base - height}" width="{bar_w}" height="{height}" rx="{R_BAR}" fill="{colour}"/>'
            f"</g>"
        )
        bars.append(
            f'<text x="{bx + bar_w / 2}" y="188" text-anchor="middle" font-family="{MONO}" font-size="{T_XS}" '
            f'fill="{INK_3}">{month["label"]}</text>'
        )
        if month["key"] == best and month["count"]:
            bars.append(
                f'<text x="{bx + bar_w / 2}" y="{base - height - 8}" text-anchor="middle" '
                f'font-family="{DISPLAY}" font-size="{T_SM}" font-weight="{W_SEMI}" fill="{GREEN}">{month["count"]}</text>'
            )

    body = (
        f'<g class="enter">{fade_in(0.1)}'
        f'{panel(AW, AH)}{"".join(header)}'
        f'<line x1="36" y1="166" x2="{AW - 36}" y2="166" stroke="{GRID}" stroke-width="1"/>'
        f'{"".join(bars)}</g>'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{AW}" height="{AH}" viewBox="0 0 {AW} {AH}" '
        f'role="img" aria-label="Contribution activity: {total} contributions over the last 12 months, '
        f'{snapshot["active_days"]} active days">'
        f"{base_style()}{body}</svg>\n"
    )
    return embed_fonts(svg)


# --------------------------------------------------------------------------- #
# stack band
# --------------------------------------------------------------------------- #

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


def render_stack() -> str:
    """The toolbelt: official brand marks, grouped by what they are for.

    No word labels - the marks are the labels. Every icon keeps a <title> so
    the artwork still names itself for screen readers and for anyone who
    inspects the SVG.
    """
    icons = _icons()
    pad = 16
    gutter = 16
    col_w = (SW - pad * 2 - gutter * 3) / 4
    icon_size = 28
    icon_gap = 10

    parts = [f'<g class="enter">{fade_in(0.08)}{panel(SW, SH)}']

    for index, (label, accent, slugs) in enumerate(STACK):
        x = pad + index * (col_w + gutter)

        if index:
            parts.append(
                f'<line x1="{x - gutter / 2:.1f}" y1="30" x2="{x - gutter / 2:.1f}" y2="{SH - 30}" '
                f'stroke="#21262d" stroke-width="1"/>'
            )

        parts.append(
            f'<text x="{x:.1f}" y="40" font-family="{MONO}" font-size="12" letter-spacing="1.4" '
            f'fill="{accent}">{html.escape(label)}</text>'
        )
        parts.append(
            f'<rect x="{x:.1f}" y="50" width="30" height="2" rx="2" fill="{accent}" opacity="0.7"/>'
        )

        row = [icons.get(slug) for slug in slugs]
        row = [item for item in row if item]
        if not row:
            continue
        total = len(row) * icon_size + (len(row) - 1) * icon_gap
        start = x + (col_w - total) / 2
        top = 78
        for position, item in enumerate(row):
            slug = item["slug"]
            ix = start + position * (icon_size + icon_gap)
            scale = icon_size / 24
            dx, dy = ICON_OFFSETS.get(slug, (0.0, 0.0))
            parts.append(
                f'<g transform="translate({ix + dx:.2f},{top + dy:.2f}) scale({scale:.4f})" opacity="0.95">'
                f"<title>{html.escape(item['title'])}</title>"
                f'<path d="{item["path"]}" fill="{item["hex"]}"/></g>'
            )

    parts.append(
        f'<text x="{SW - pad}" y="40" text-anchor="end" font-family="{MONO}" font-size="12" '
        f'letter-spacing="1.0" fill="#8b949e">19 TOOLS</text>'
    )
    parts.append("</g>")

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SW}" height="{SH}" viewBox="0 0 {SW} {SH}" '
        f'role="img" aria-label="Technology stack: Next.js, React, TypeScript, Tailwind CSS, Vite, Three.js, '
        f'GSAP, Framer, WebGL, Node.js, Python, PostgreSQL, Prisma, Postman, Kali Linux, GNU Bash, '
        f'Burp Suite, Wireshark and Docker">'
        f"{base_style()}{''.join(parts)}</svg>\n"
    )
    return embed_fonts(svg)


# --------------------------------------------------------------------------- #
# mobile variants
#
# GitHub's README column is 846px on desktop but only ~418px on a phone. A
# desktop-width SVG scaled down to 418 turns 12px type into 6px - unreadable.
# Every visual therefore gets a second, purpose-built 400px composition and
# the README swaps them with <picture><source media="(max-width: 767px)">.
# --------------------------------------------------------------------------- #

MW = 400

MOBILE_IDENTITY = [
    ("name", "Abdul Manan"),
    ("role", "Founder, CYNEX Studio"),
    ("study", "BSCS - UAJK"),
    ("base", "Muzaffarabad, AK"),
    ("builds", "Next.js - React - TS"),
    ("live", "cynex.online"),
]


def render_hero_mobile(snapshot: dict) -> str:
    """A console card, not a squeezed console card."""
    h = 236
    parts = [
        f'<text class="print" x="18" y="32" font-family="{MONO}" font-size="{T_SM}" fill="{GREEN}" '
        f'style="animation-delay:.10s">'
        f'<tspan fill="{GREEN}">cynex@kali</tspan><tspan fill="{INK_3}">:~$ </tspan>'
        f'<tspan fill="{INK_2}">whoami</tspan>{print_in(0.10)}</text>'
    ]
    for i, (label, value) in enumerate(MOBILE_IDENTITY):
        delay = 0.30 + i * 0.10
        parts.append(
            f'<text class="print" x="18" y="{66 + i * 26}" font-family="{MONO}" font-size="{T_SM}" '
            f'style="animation-delay:{delay:.2f}s">'
            f'<tspan fill="{BLUE}">{html.escape(label.ljust(6))}</tspan>'
            f'<tspan fill="{INK_2}">{html.escape(value)}</tspan>{print_in(delay)}</text>'
        )

    stats = (
        f"{snapshot['contributions']} contributions - {snapshot['public_repos']} repos",
        f"{snapshot['followers']} followers - {snapshot['total_stars']} stars",
    )
    for i, line in enumerate(stats):
        delay = 1.05 + i * 0.10
        parts.append(
            f'<text class="print" x="18" y="{196 + i * 20}" font-family="{MONO}" font-size="{T_XS}" '
            f'fill="{INK_3}" style="animation-delay:{delay:.2f}s">{html.escape(line)}{print_in(delay)}</text>'
        )
    parts.append(f'<circle class="live" cx="22" cy="192" r="3.5" fill="{GREEN}"/>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{MW}" height="{h}" viewBox="0 0 {MW} {h}" '
        f'role="img" aria-label="Abdul Manan - CYNEX Studio console profile">'
        f'<style>'
        f'.print{{transform-box:view-box;transform-origin:0 0}}'
        f'@media (prefers-reduced-motion: no-preference){{'
        f'.print{{animation:rise .5s ease-out both}}'
        f'.live{{animation:pulse 2.6s ease-in-out infinite}}'
        f'}}'
        f'@keyframes rise{{from{{transform:translateY(6px)}}to{{transform:translateY(0)}}}}'
        f'@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}'
        f'</style>'
        f'<rect width="{MW}" height="{h}" rx="{R_CARD}" fill="{BG}"/>'
        f'<rect x="0.5" y="0.5" width="{MW - 1}" height="{h - 1}" rx="{R_CARD}" fill="none" stroke="{BORDER}"/>'
        f'{"".join(parts)}</svg>\n'
    )
    return embed_fonts(svg)


def render_stack_mobile() -> str:
    """The same four groups, stacked, with type that survives a phone."""
    h = 4 * 76 + 32
    parts = [f'<g class="enter">{fade_in(0.08)}{panel(MW, h)}']
    for index, (label, accent, slugs) in enumerate(STACK):
        y = 18 + index * 76
        parts.append(
            f'<text x="18" y="{y + 12}" font-family="{MONO}" font-size="{T_SM}" letter-spacing="1.4" '
            f'fill="{accent}">{html.escape(label)}</text>'
        )
        parts.append(
            f'<rect x="18" y="{y + 20}" width="28" height="2" rx="{R_BAR}" fill="{accent}" opacity="0.7"/>'
        )

        icons = _icons()
        row = [icons.get(slug) for slug in slugs]
        row = [item for item in row if item]
        if not row:
            continue
        size, gap = 24, 10
        for position, item in enumerate(row):
            ix = 18 + position * (size + gap)
            dx, dy = ICON_OFFSETS.get(item["slug"], (0.0, 0.0))
            scale = size / 24
            parts.append(
                f'<g transform="translate({ix + dx:.2f},{y + 32 + dy:.2f}) scale({scale:.4f})" opacity="0.95">'
                f"<title>{html.escape(item['title'])}</title>"
                f'<path d="{item["path"]}" fill="{item["hex"]}"/></g>'
            )
    parts.append("</g>")

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{MW}" height="{h}" viewBox="0 0 {MW} {h}" '
        f'role="img" aria-label="Technology stack: Next.js, React, TypeScript, Tailwind CSS, Vite, Three.js, '
        f'GSAP, Framer, WebGL, Node.js, Python, PostgreSQL, Prisma, Postman, Kali Linux, GNU Bash, '
        f'Burp Suite, Wireshark and Docker">'
        f"{base_style()}{''.join(parts)}</svg>\n"
    )
    return embed_fonts(svg)


def render_activity_mobile(snapshot: dict) -> str:
    """The same twelve months, sized so a 12px month label is still 12px."""
    h = 196
    monthly = snapshot["monthly"]
    total = snapshot["contributions"]
    busiest = snapshot["busiest_month"]

    header = [
        f'<text x="16" y="26" font-family="{MONO}" font-size="{T_XS}" letter-spacing="1.4" fill="{BLUE}">12-MONTH ACTIVITY</text>',
        f'<text x="{MW - 16}" y="26" text-anchor="end" font-family="{DISPLAY}" font-size="{T_XL}" '
        f'font-weight="{W_BOLD}" fill="{INK}">{total}<tspan font-size="{T_XS}" font-weight="{W_REG}" '
        f'fill="{INK_3}"> contributions</tspan></text>',
        f'<text x="{MW - 16}" y="46" text-anchor="end" font-family="{MONO}" font-size="{T_XS}" fill="{INK_3}">'
        f'{snapshot["active_days"]} active days - best {html.escape(busiest["label"])}</text>',
    ]

    top, base = 78, 148
    max_count = max([m["count"] for m in monthly] or [1])
    slot, bar_w, start_x = 30, 22, 16
    best = max(monthly, key=lambda m: m["count"])["key"] if monthly else None
    bars = []

    for i, month in enumerate(monthly):
        bx = start_x + i * slot
        height = 8 + int((month["count"] / max_count) * (base - top - 12)) if max_count else 8
        colour = GREEN if month["key"] == best else "#2ea043"
        delay = 0.15 + i * 0.05
        bars.append(
            f'<g class="grow" style="animation-delay:{delay:.2f}s">'
            f'<rect x="{bx}" y="{base - height}" width="{bar_w}" height="{height}" rx="{R_BAR}" fill="{colour}"/>'
            f"</g>"
        )
        if i % 2 == 0:
            bars.append(
                f'<text x="{bx + bar_w / 2}" y="168" text-anchor="middle" font-family="{MONO}" '
                f'font-size="{T_XS}" fill="{INK_3}">{month["label"]}</text>'
            )

    body = (
        f'<g class="enter">{fade_in(0.1)}'
        f'{panel(MW, h)}{"".join(header)}'
        f'<line x1="16" y1="148" x2="{MW - 16}" y2="148" stroke="{GRID}" stroke-width="1"/>'
        f'{"".join(bars)}</g>'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{MW}" height="{h}" viewBox="0 0 {MW} {h}" '
        f'role="img" aria-label="Contribution activity: {total} contributions over the last 12 months">'
        f"{base_style()}{body}</svg>\n"
    )
    return embed_fonts(svg)


def render_repo_card_mobile(repo: dict, description: str, index: int) -> str:
    """A card built for a 200px column: bigger type, fewer words."""
    w, h = 200, 112
    language = repo.get("language") or "-"
    colour = LANG_COLOURS.get(language, INK_3)
    delay = 0.05 + index * 0.12

    words = description.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > 28:
            lines.append(current)
            current = word
            if len(lines) == 2:
                break
        else:
            current = candidate
    if current and len(lines) < 2:
        lines.append(current)

    body = [f'<g class="enter" style="animation-delay:{delay:.2f}s">{fade_in(delay)}{panel(w, h)}']
    body.append(
        f'<text x="14" y="28" font-family="{DISPLAY}" font-size="{T_MD}" font-weight="{W_SEMI}" '
        f'fill="{INK}">{html.escape(truncate(repo["name"], 20))}</text>'
    )
    for i, line in enumerate(lines[:2]):
        body.append(
            f'<text x="14" y="{50 + i * 17}" font-family="{DISPLAY}" font-size="{T_XS}" fill="{INK_2}">'
            f"{html.escape(line)}</text>"
        )
    body.append(f'<circle cx="18" cy="92" r="4" fill="{colour}"/>')
    body.append(
        f'<text x="29" y="96" font-family="{MONO}" font-size="{T_XS}" fill="{INK_3}">{html.escape(language)}</text>'
    )
    body.append(
        f'<text x="186" y="96" text-anchor="end" font-family="{MONO}" font-size="{T_XS}" fill="{INK_3}">'
        f'★ {repo["stars"]} · {relative_days(repo["pushed_at"])}</text>'
    )
    body.append("</g>")

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{html.escape(repo["name"])} — {html.escape(description)}">'
        f"{base_style()}{''.join(body)}</svg>\n"
    )
    return embed_fonts(svg)


# --------------------------------------------------------------------------- #
# README repository index
# --------------------------------------------------------------------------- #

START = "<!-- AUTO:REPOS:START -->"
END = "<!-- AUTO:REPOS:END -->"


def render_repo_index(snapshot: dict) -> str:
    """The complete public index.

    Sorted by stars, not by date: a visitor scans and satisfices - they take
    the first reasonable option - so the best work has to come first.
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
    return (
        f"{START}\n"
        "| Repository | What it is | Stack | \u2605 | Last push |\n"
        "|---|---|---|---|---|\n"
        f"{body}\n"
        f"{END}"
    )


def update_readme(text: str, block: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        print("warning: auto block markers not found in README.md", file=sys.stderr)
        return text
    return pattern.sub(lambda _: block, text)


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

    write(ROOT / "assets" / "hero.svg", render_hero(snapshot))
    write(ROOT / "assets" / "hero.mobile.svg", render_hero_mobile(snapshot))

    write(ROOT / "assets" / "cta-primary.svg", render_button("Work with me", 168, True))
    write(ROOT / "assets" / "cta-secondary.svg", render_button("Browse all repos", 192, False))

    cards = ROOT / "assets" / "cards"
    for index, tile in enumerate(TILES):
        tile = dict(tile)
        if tile["id"] == "security":
            tile["value"] = snapshot["current_streak"]
        write(cards / f"tile-{tile['id']}.svg", render_tile(tile, index))

    by_name = {r["name"]: r for r in snapshot["repos"]}
    for index, (name, description) in enumerate(FEATURED):
        repo = by_name.get(name)
        if not repo:
            continue
        write(cards / f"repo-{name.lower()}.svg", render_repo_card(repo, description, index))
        write(
            cards / f"repo-{name.lower()}.mobile.svg",
            render_repo_card_mobile(repo, description, index),
        )

    write(ROOT / "assets" / "activity.svg", render_activity(snapshot))
    write(ROOT / "assets" / "activity.mobile.svg", render_activity_mobile(snapshot))
    write(ROOT / "assets" / "stack.svg", render_stack())
    write(ROOT / "assets" / "stack.mobile.svg", render_stack_mobile())

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
