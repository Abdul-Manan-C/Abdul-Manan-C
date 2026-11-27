#!/usr/bin/env python3
"""Measure the README column width GitHub really renders, at every breakpoint.

The profile README lives in a fluid column. On a phone it is about
``viewport - 82``; when the profile sidebar appears at 768px it collapses to
roughly 400px; on a wide desktop it stops at 846px. Any artwork sized for one
of those widths is squeezed at the others, and the type inside it shrinks with
it.

This script measures the curve on the live profile - the only ground truth -
and writes it to ``data/column_curve.json``. ``build_profile_art.py`` reads
that file to decide where the artwork bands go, so the bands follow the real
layout instead of a guess.

    python scripts/measure_column_curve.py
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "column_curve.json"
PROFILE = "https://github.com/Abdul-Manan-C"

PROBE = """
return (() => {
  const art = document.querySelector('article.markdown-body');
  if (!art) return { error: 'no article' };
  const r = art.getBoundingClientRect();
  const t = art.querySelector('table');
  const td = t ? t.querySelector('td') : null;
  const tdCs = td ? getComputedStyle(td) : null;
  const tdR = td ? td.getBoundingClientRect() : null;
  return {
    vw: window.innerWidth,
    article: Math.round(r.width),
    cellContent: tdR && tdCs
      ? Math.round(tdR.width - parseFloat(tdCs.paddingLeft) - parseFloat(tdCs.paddingRight))
      : null,
  };
})();
"""

WIDTHS = [
    320, 344, 368, 392, 416, 440, 464, 488, 512, 536, 560, 584,
    608, 632, 656, 680, 704, 728, 752, 767,
    768, 800, 832, 864, 896, 928, 960, 992, 1024, 1056, 1088, 1120,
    1152, 1184, 1216, 1248, 1280, 1320, 1360, 1400, 1440, 1600, 1920,
]


def probe(width: int, attempt: int = 0) -> dict | None:
    probe_file = pathlib.Path("/tmp/opencode/readme-shots/curve-probe.js")
    probe_file.parent.mkdir(parents=True, exist_ok=True)
    probe_file.write_text(PROBE, encoding="utf-8")

    env = dict(
        os.environ,
        CDP_EMULATE_WIDTH=str(width),
        CDP_EMULATE_HEIGHT="900",
        CDP_EMULATE_SCALE="1",
        CDP_WINDOW="1440,900",
    )
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "cdp_eval.mjs"), PROFILE, str(probe_file), "11000"],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or "error" in data:
        return None
    data["requested"] = width
    return data


def measure(width: int) -> dict | None:
    """Probe one width, retrying a couple of times before giving up."""
    for attempt in range(3):
        data = probe(width, attempt)
        if data and data.get("article"):
            return data
    return None


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--widths":
        widths = [int(x) for x in sys.argv[2].split(",")]
    else:
        widths = WIDTHS

    results: dict[int, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(measure, w): w for w in widths}
        for future in concurrent.futures.as_completed(futures):
            width = futures[future]
            data = future.result()
            if data:
                results[width] = data
                print(f"  viewport {width:>5}  column {data['article']:>4}px  "
                      f"2-up cell {data.get('cellContent')}px")
            else:
                print(f"  viewport {width:>5}  FAILED")

    ordered = [results[w] for w in sorted(results)]

    # Merge with anything already on disk so a partial run can be topped up.
    previous: dict[int, dict] = {}
    if OUT.exists():
        try:
            for row in json.loads(OUT.read_text(encoding="utf-8")):
                previous[int(row["requested"])] = row
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError):
            previous = {}
    previous.update(results)
    ordered = [previous[w] for w in sorted(previous)]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT} ({len(ordered)}/{len(widths)} widths)")
    return 0 if ordered else 1


if __name__ == "__main__":
    sys.exit(main())
