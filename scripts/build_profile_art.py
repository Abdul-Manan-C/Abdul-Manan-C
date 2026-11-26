#!/usr/bin/env python3
"""Profile art pipeline for github.com/Abdul-Manan-C.

Pulls live public profile data (GitHub REST + the public contributions
calendar), renders assets/hero.svg (animated console + radar emblem) and
refreshes the auto-generated repository index inside README.md.

Standard library only. Safe to run offline: on a network failure the previous
snapshot is kept and the script exits cleanly.
"""

from __future__ import annotations

import html
import json
import os
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

IDENTITY = [
    ("name", "Abdul Manan \u00b7 CH Manan"),
    ("role", "Founder & Principal Web Engineer @ CYNEX Studio"),
    ("study", "BSCS @ University of Azad Jammu & Kashmir"),
    ("base", "Muzaffarabad, Azad Kashmir"),
    ("builds", "Next.js \u00b7 React \u00b7 TypeScript \u00b7 Tailwind \u00b7 Three.js"),
    ("security", "AUTOCORE \u00b7 TryHackMe \u00b7 Kali \u00b7 Fedora"),
    ("live", "cynex.online"),
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
    """Return (official_total, days) from the public contributions fragment."""
    raw = http_get(f"https://github.com/users/{USER}/contributions").decode("utf-8", "replace")
    total = None
    match = re.search(r"([\d,]+)\s+contributions\s+in the last year", raw)
    if match:
        total = int(match.group(1).replace(",", ""))
    days = []
    for day, level in re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d)"', raw):
        days.append((day, int(level)))
    if not days:
        raise RuntimeError("contributions calendar did not parse")
    return total, days


def streaks(days: list) -> tuple:
    levels = dict(days)
    today = date.today()
    current = 0
    cursor = today
    if levels.get(cursor.isoformat(), 0) == 0:
        cursor = today.fromordinal(today.toordinal() - 1)
    while levels.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor = date.fromordinal(cursor.toordinal() - 1)
    longest = 0
    run = 0
    for _, level in sorted(days):
        run = run + 1 if level > 0 else 0
        longest = max(longest, run)
    return current, longest


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

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "login": profile["login"],
        "name": profile.get("name") or USER,
        "followers": profile.get("followers", 0),
        "public_repos": len(public),
        "public_repos_total": profile.get("public_repos", len(public)),
        "contributions": total if total is not None else sum(1 for _, level in days if level > 0),
        "current_streak": current,
        "longest_streak": longest,
        "total_stars": sum(r["stars"] for r in public),
        "repos": public,
    }


# --------------------------------------------------------------------------- #
# hero.svg
# --------------------------------------------------------------------------- #

W, H = 900, 320
CX, CY = 150, 148
RAD = 116
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"


def radar() -> str:
    parts = [
        f'<circle cx="{CX}" cy="{CY}" r="{RAD}" fill="none" stroke="#21262d" stroke-width="1"/>',
        f'<circle cx="{CX}" cy="{CY}" r="84" fill="none" stroke="#1b2028" stroke-width="1"/>',
        f'<circle cx="{CX}" cy="{CY}" r="52" fill="none" stroke="#1b2028" stroke-width="1"/>',
        f'<line x1="{CX}" y1="{CY - RAD}" x2="{CX}" y2="{CY + RAD}" stroke="#1b2028" stroke-width="1" stroke-dasharray="3 7"/>',
        f'<line x1="{CX - RAD}" y1="{CY}" x2="{CX + RAD}" y2="{CY}" stroke="#1b2028" stroke-width="1" stroke-dasharray="3 7"/>',
    ]

    # rotating sweep wedge
    import math

    span = math.radians(54)
    ex = CX + RAD * math.sin(span)
    ey = CY - RAD * math.cos(span)
    parts.append(
        f'<g class="spin"><path d="M {CX} {CY} L {CX} {CY - RAD} A {RAD} {RAD} 0 0 1 {ex:.1f} {ey:.1f} Z" '
        f'fill="url(#sweep)" opacity="0.9"/></g>'
    )

    # dashed outer ring
    parts.append(
        f'<circle class="spin ring" cx="{CX}" cy="{CY}" r="36" fill="none" stroke="#30363d" stroke-width="1" '
        f'stroke-dasharray="2 6"/>'
    )

    # blips
    blips = [(116, 108, "#3fb949"), (198, 96, "#d29922"), (188, 198, "#58a6ff"), (104, 182, "#3fb949")]
    for bx, by, colour in blips:
        parts.append(
            f'<circle class="pulse" cx="{bx}" cy="{by}" r="3.5" fill="{colour}"/>'
        )
        parts.append(
            f'<circle class="ping" cx="{bx}" cy="{by}" r="3.5" fill="none" stroke="{colour}" stroke-width="1" opacity="0"/>'
        )

    # core hexagon
    hex_pts = []
    for i in range(6):
        angle = math.radians(90 + i * 60)
        hex_pts.append(f"{CX + 26 * math.cos(angle):.1f},{CY + 26 * math.sin(angle):.1f}")
    parts.append(
        f'<polygon points="{" ".join(hex_pts)}" fill="#0d1117" stroke="#58a6ff" stroke-width="1.5"/>'
    )
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
    parts.append(
        f'<rect class="cursor" x="{cursor_x}" y="248" width="8" height="16" fill="#3fb949"/>'
    )

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
            (repo.get("description") or "Public repository.", repo.get("language") or "—"),
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


def main() -> int:
    snapshot_path = ROOT / "data" / "profile.json"
    try:
        snapshot = build_snapshot()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, ValueError) as exc:
        print(f"warning: live fetch failed ({exc}); keeping previous snapshot", file=sys.stderr)
        return 0

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    hero_path = ROOT / "assets" / "hero.svg"
    hero_path.parent.mkdir(parents=True, exist_ok=True)
    hero_path.write_text(render_hero(snapshot), encoding="utf-8")

    readme_path = ROOT / "README.md"
    if readme_path.exists():
        current = readme_path.read_text(encoding="utf-8")
        updated = update_readme(current, render_repo_index(snapshot))
        if updated != current:
            readme_path.write_text(updated, encoding="utf-8")

    print(
        "profile art rebuilt: "
        f"{snapshot['contributions']} contributions, "
        f"{snapshot['public_repos']} public repos, "
        f"{snapshot['followers']} followers, "
        f"{snapshot['total_stars']} stars"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
