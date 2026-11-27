#!/usr/bin/env python3
"""Find out what makes the gallery table wider than the README column.

The gallery is a two-column table. A table cannot reflow, so its cells have
to fit the narrowest column or the right-hand column gets cut off. This
measures the min-content width of each caption variant in the real browser.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path("/tmp/opencode/readme-shots")
PORT = 8739

PHOTO = "./assets/screens/m/laxitech.jpg"

VARIANTS = {
    "code": "<b><a href='https://laxitech.com/'>Laxitech</a></b> <code>laxitech.com</code><br />3D MacBook stage with WebGL aurora lighting.",
    "plain": "<b><a href='https://laxitech.com/'>Laxitech</a></b> laxitech.com<br />3D MacBook stage with WebGL aurora lighting.",
    "name": "<b><a href='https://laxitech.com/'>Laxitech</a></b><br />3D MacBook stage with WebGL aurora lighting.",
    "name+code": "<b><a href='https://laxitech.com/'>Laxitech</a></b><br /><code>laxitech.com</code><br />3D MacBook stage with WebGL aurora lighting.",
}

PROBE = """
return (() => {
  const art = document.querySelector('#col');
  if (!art) return { error: 'no column' };
  const t = art.querySelector('table');
  const r = t.getBoundingClientRect();
  const td = t.querySelector('td');
  const tdR = td.getBoundingClientRect();
  const cs = getComputedStyle(td);
  return {
    vw: innerWidth,
    article: Math.round(art.getBoundingClientRect().width),
    tableW: Math.round(r.width),
    clientW: t.clientWidth,
    scrollW: t.scrollWidth,
    cellW: Math.round(tdR.width),
    cellContent: Math.round(tdR.width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)),
  };
})();
"""

PAGE = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ margin:0; font-family: system-ui, sans-serif; font-size:14px; }}
#col {{ width: {col}px; }}
table {{ border-collapse: collapse; width: max-content; max-width: 100%; display:block; overflow:auto; }}
td {{ padding: 6px 13px; vertical-align: top; }}
img {{ max-width:100%; width:396px; }}
</style></head><body><div id="col"><table><tr>
<td>{cell}</td><td>{cell}</td>
</tr></table></div></body></html>"""


def main() -> int:
    probe = OUT / "gallery-probe.js"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(PROBE, encoding="utf-8")

    # the narrowest column GitHub ever gives the README: 238px at 320px wide
    for col in (238, 278, 308):
        print(f"\n=== column {col}px ===")
        for name, cell in VARIANTS.items():
            page = OUT / "gallery-probe.html"
            page.write_text(PAGE.format(col=col, cell=cell), encoding="utf-8")
            env = dict(os.environ, CDP_EMULATE_WIDTH="320", CDP_EMULATE_HEIGHT="844",
                       CDP_EMULATE_SCALE="1", CDP_WINDOW="1440,900")
            result = subprocess.run(
                ["node", str(ROOT / "scripts" / "cdp_eval.mjs"),
                 f"http://127.0.0.1:{PORT}/gallery-probe.html", str(probe), "3000"],
                capture_output=True, text=True, env=env, timeout=120,
            )
            try:
                data = json.loads(result.stdout)
            except Exception:
                print(f"  {name:<10} no data")
                continue
            overflow = data["scrollW"] - data["clientW"]
            print(f"  {name:<10} table {data['tableW']}px  scroll {data['scrollW']}  "
                  f"cell {data['cellW']} content {data['cellContent']}  "
                  f"overflow {overflow}px {'OK' if overflow <= 0 else 'CUT OFF'}")
    return 0


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: A003
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT),
                                   functools.partial(QuietHandler, directory=str(OUT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        sys.exit(main())
    finally:
        httpd.shutdown()
