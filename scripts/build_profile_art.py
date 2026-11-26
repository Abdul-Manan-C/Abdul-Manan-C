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

import html
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

DISPLAY = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

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
        "value": 6,
        "headline": "platforms in production",
        "sub": "Next.js \u00b7 TypeScript \u00b7 Tailwind",
        "accent": "#58a6ff",
        "url": "https://cynex.online/works",
    },
    {
        "id": "security",
        "label": "SECURITY",
        "value": 216,
        "headline": "day contribution streak",
        "sub": "AUTOCORE \u00b7 TryHackMe \u00b7 Kali",
        "accent": "#3fb949",
        "url": "https://github.com/Abdul-Manan-C/autocore",
    },
    {
        "id": "studio",
        "label": "STUDIO",
        "value": 10,
        "headline": "engineering disciplines",
        "sub": "3D \u00b7 dashboards \u00b7 AI \u00b7 SEO",
        "accent": "#d29922",
        "url": "https://cynex.online",
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
# shared svg helpers
# --------------------------------------------------------------------------- #


def panel(w: int, h: int, rx: int = 12) -> str:
    return (
        f'<rect width="{w}" height="{h}" rx="{rx}" fill="#0d1117"/>'
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx - 0.5}" fill="none" stroke="#30363d"/>'
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

W, H = 900, 320
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
        f'<text x="{CX}" y="{CY + 8}" text-anchor="middle" font-family="{MONO}" font-size="22" '
        f'font-weight="700" fill="#58a6ff">C</text>'
    )
    parts.append(
        f'<text x="{CX}" y="292" text-anchor="middle" font-family="{MONO}" font-size="10" '
        f'letter-spacing="2.5" fill="#6e7681">CYNEX STUDIO</text>'
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
        f'<text class="print" x="320" y="44" font-family="{MONO}" font-size="15" fill="#3fb949" '
        f'style="animation-delay:.10s">'
        f'<tspan fill="#3fb949">cynex@kali</tspan><tspan fill="#8b949e">:~$ </tspan>'
        f'<tspan fill="#c9d1d9">whoami</tspan>{print_in(0.10)}</text>'
    )
    for i, (label, value) in enumerate(IDENTITY):
        delay = 0.34 + i * 0.11
        parts.append(
            f'<text class="print" x="320" y="{84 + i * 30}" font-family="{MONO}" font-size="15" '
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
        f'<text class="print" x="340" y="300" font-family="{MONO}" font-size="12.5" fill="#8b949e" '
        f'style="animation-delay:1.25s">{html.escape(stats)}{print_in(1.25)}</text>'
    )
    parts.append(
        f'<text class="print" x="864" y="300" text-anchor="end" font-family="{MONO}" font-size="12" '
        f'fill="#6e7681" style="animation-delay:1.35s">refreshed daily{print_in(1.35)}</text>'
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
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="Abdul Manan — CYNEX Studio console profile">'
        f"{defs}{style}"
        f'<rect width="{W}" height="{H}" rx="14" fill="#0d1117"/>'
        f'<rect width="{W}" height="{H}" rx="14" fill="url(#scan)"/>'
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="13.5" fill="none" stroke="#30363d"/>'
        f"{radar()}"
        f'<line x1="292" y1="34" x2="292" y2="286" stroke="#21262d" stroke-width="1"/>'
        f"{console(snapshot)}"
        f"</svg>\n"
    )


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
        f'<text x="18" y="36" font-family="{MONO}" font-size="12" letter-spacing="2.4" fill="{accent}">'
        f'{tile["label"]}</text>'
        f'<circle cx="232" cy="30" r="5" fill="{accent}"/>'
        f'<circle class="ring-pulse" cx="232" cy="30" r="7" fill="none" stroke="{accent}" stroke-width="1.2" opacity="0"/>'
        f"{countup(tile['value'], 18, 100, 54, '#e6edf3', delay + 0.18)}"
        f'<text x="18" y="146" font-family="{DISPLAY}" font-size="13.5" font-weight="500" fill="#c9d1d9">'
        f'{tile["headline"]}</text>'
        f'<text x="18" y="170" font-family="{MONO}" font-size="11" fill="#6e7681">{tile["sub"]}</text>'
        f"</g>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{TW}" height="{TH}" viewBox="0 0 {TW} {TH}" '
        f'role="img" aria-label="{tile["label"]}: {tile["value"]} {tile["headline"]}">'
        f"{base_style()}{body}</svg>\n"
    )


# --------------------------------------------------------------------------- #
# repo cards
# --------------------------------------------------------------------------- #

CW, CH = 390, 150


def render_repo_card(repo: dict, description: str, index: int) -> str:
    language = repo.get("language") or "—"
    colour = LANG_COLOURS.get(language, "#8b949e")
    delay = 0.05 + index * 0.12
    body = (
        f'<g class="enter" style="animation-delay:{delay:.2f}s">{fade_in(delay)}'
        f'{panel(CW, CH)}'
        f'<text x="18" y="36" font-family="{DISPLAY}" font-size="16" font-weight="650" fill="#e6edf3">'
        f'{html.escape(repo["name"])}</text>'
        f'<text x="18" y="60" font-family="{DISPLAY}" font-size="12.5" fill="#8b949e">'
        f'{html.escape(truncate(description, 58))}</text>'
        f'<circle cx="22" cy="122" r="4" fill="{colour}"/>'
        f'<text x="33" y="126" font-family="{MONO}" font-size="11" fill="#8b949e">{html.escape(language)}</text>'
        f'<text x="372" y="126" text-anchor="end" font-family="{MONO}" font-size="11" fill="#6e7681">'
        f'\u2605 {repo["stars"]} \u00b7 {relative_days(repo["pushed_at"])}</text>'
        f"</g>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CW}" height="{CH}" viewBox="0 0 {CW} {CH}" '
        f'role="img" aria-label="{html.escape(repo["name"])} — {html.escape(description)}">'
        f"{base_style()}{body}</svg>\n"
    )


# --------------------------------------------------------------------------- #
# activity chart
# --------------------------------------------------------------------------- #

AW, AH = 880, 210


def render_activity(snapshot: dict) -> str:
    monthly = snapshot["monthly"]
    stats = [
        ("contributions", snapshot["contributions"]),
        ("active days", snapshot["active_days"]),
        ("streak", f"{snapshot['current_streak']}d"),
        ("best month", snapshot["busiest_month"]["label"]),
    ]

    header = [
        f'<text x="28" y="36" font-family="{MONO}" font-size="12" letter-spacing="2.4" fill="#58a6ff">ACTIVITY</text>'
    ]
    x = 852
    for label, value in reversed(stats):
        header.append(
            f'<text x="{x}" y="30" text-anchor="end" font-family="{DISPLAY}" font-size="17" font-weight="650" '
            f'fill="#e6edf3">{html.escape(str(value))}</text>'
        )
        header.append(
            f'<text x="{x}" y="46" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="#6e7681">'
            f'{html.escape(label)}</text>'
        )
        x -= 150

    top = 78
    base = 166
    max_count = max([m["count"] for m in monthly] or [1])
    slot = 68
    bar_w = 46
    start_x = 40
    bars = []
    best = max(monthly, key=lambda m: m["count"])["key"] if monthly else None

    for i, month in enumerate(monthly):
        bx = start_x + i * slot
        height = 8 + int((month["count"] / max_count) * (base - top - 12)) if max_count else 8
        colour = "#3fb949" if month["key"] == best else "#2ea043"
        delay = 0.15 + i * 0.06
        bars.append(
            f'<g class="grow" style="animation-delay:{delay:.2f}s">'
            f'<rect x="{bx}" y="{base - height}" width="{bar_w}" height="{height}" rx="4" fill="{colour}"/>'
            f"</g>"
        )
        bars.append(
            f'<text x="{bx + bar_w / 2}" y="188" text-anchor="middle" font-family="{MONO}" font-size="10.5" '
            f'fill="#6e7681">{month["label"]}</text>'
        )
        if month["key"] == best and month["count"]:
            bars.append(
                f'<text x="{bx + bar_w / 2}" y="{base - height - 8}" text-anchor="middle" '
                f'font-family="{DISPLAY}" font-size="12" font-weight="650" fill="#3fb949">{month["count"]}</text>'
            )

    body = (
        f'<g class="enter">{fade_in(0.1)}'
        f'{panel(AW, AH)}{"".join(header)}'
        f'<line x1="28" y1="166" x2="852" y2="166" stroke="#21262d" stroke-width="1"/>'
        f'{"".join(bars)}</g>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{AW}" height="{AH}" viewBox="0 0 {AW} {AH}" '
        f'role="img" aria-label="Contribution activity: {snapshot["contributions"]} contributions in the last year">'
        f"{base_style()}{body}</svg>\n"
    )


# --------------------------------------------------------------------------- #
# README repository index
# --------------------------------------------------------------------------- #

START = "<!-- AUTO:REPOS:START -->"
END = "<!-- AUTO:REPOS:END -->"


def render_repo_index(snapshot: dict) -> str:
    rows = []
    for repo in snapshot["repos"]:
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


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    snapshot_path = ROOT / "data" / "profile.json"
    try:
        snapshot = build_snapshot()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, ValueError) as exc:
        print(f"warning: live fetch failed ({exc}); keeping previous snapshot", file=sys.stderr)
        return 0

    write(snapshot_path, json.dumps(snapshot, indent=2) + "\n")

    write(ROOT / "assets" / "hero.svg", render_hero(snapshot))

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

    write(ROOT / "assets" / "activity.svg", render_activity(snapshot))

    readme_path = ROOT / "README.md"
    if readme_path.exists():
        current = readme_path.read_text(encoding="utf-8")
        updated = update_readme(current, render_repo_index(snapshot))
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
