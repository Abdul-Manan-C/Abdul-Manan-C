#!/usr/bin/env python3
"""GitHub's real stylesheet, fetched once and cached.

The preview harness used to hand-roll an approximation of GitHub's markdown
CSS. That was wrong in ways that mattered: the approximation removed link
underlines, which GitHub does render, and it guessed at heading sizes and
table borders. Any measurement taken against it was measuring a fiction.

This module downloads the stylesheets GitHub actually serves and caches them
on disk, so the preview is rendered with the same CSS the profile is.

    python scripts/github_css.py            # fetch / refresh the cache
"""

from __future__ import annotations

import pathlib
import re
import sys
import urllib.request

CACHE = pathlib.Path("/tmp/opencode/readme-shots/github-cache")
PROFILE = "https://github.com/Abdul-Manan-C"

UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}


def _get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def stylesheet_urls() -> list[str]:
    html = _get(PROFILE).decode("utf-8", "replace")
    found = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', html)
    # keep the order, drop duplicates
    return list(dict.fromkeys(found))


def fetch(force: bool = False) -> pathlib.Path:
    """Download GitHub's stylesheets into the cache and return the bundle."""
    CACHE.mkdir(parents=True, exist_ok=True)
    index = CACHE / "index.txt"
    bundle = CACHE / "github.css"

    if not force and index.exists() and bundle.exists():
        return bundle

    urls = stylesheet_urls()
    parts = []
    for url in urls:
        name = url.split("/")[-1].split("?")[0]
        path = CACHE / name
        if not path.exists() or force:
            try:
                path.write_bytes(_get(url))
            except Exception as exc:  # a single failed theme file is not fatal
                print(f"  skip {name}: {exc}", file=sys.stderr)
                continue
        parts.append(f"/* {name} */\n" + path.read_text(encoding="utf-8", errors="replace"))

    bundle.write_text("\n".join(parts), encoding="utf-8")
    index.write_text("\n".join(urls), encoding="utf-8")
    return bundle


def css() -> str:
    """The cached stylesheet, fetched on first use."""
    return fetch().read_text(encoding="utf-8", errors="replace")


# GitHub's README column is not a fixed width - it is a piecewise-linear
# function of the viewport, measured live by scripts/measure_column_curve.py:
#
#     viewport <  768   column = viewport - 82
#     768..1011         column = viewport - 370
#     1012..1279        column = viewport - 434
#     viewport >= 1280  column = 846
#
# The preview has to reproduce it, or every measurement is wrong by the
# difference - and the difference is exactly what decides whether artwork is
# squeezed or stretched.
PREVIEW_CSS = """
.preview-column { width: 100%; }
article.markdown-body.entry-content {
  box-sizing: border-box;
  padding-left: 0;
  padding-right: 0;
  width: calc(100vw - 82px);
  max-width: 846px;
  margin-left: auto;
  margin-right: auto;
}
@media (min-width: 768px) {
  article.markdown-body.entry-content { width: calc(100vw - 370px); }
}
@media (min-width: 1012px) {
  article.markdown-body.entry-content { width: calc(100vw - 434px); }
}
@media (min-width: 1280px) {
  article.markdown-body.entry-content { width: 846px; }
}
"""


def preview_html(markdown_html: str, theme: str = "dark") -> str:
    """Wrap rendered markdown in a page GitHub's own CSS can style.

    The structure and attributes are copied from a real profile page:

    * ``data-a11y-link-underlines="true"`` - GitHub underlines links, which
      the rulebooks require (colour alone is not enough).
    * ``data-color-mode`` - GitHub serves ``auto``, so the README is read on
      a light page as often as on a dark one. Both have to be checked.
    * the ``Box > Box-body > article.markdown-body`` nesting, which is what
      produces the real 846px column, the 24px body padding and the ``f5``
      14px body type.

    Getting these wrong means measuring a page GitHub never renders.
    """
    return (
        "<!DOCTYPE html>"
        '<html lang="en" data-color-mode="%s" data-light-theme="light" '
        'data-dark-theme="dark" data-a11y-link-underlines="true">'
        '<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<style>%s</style></head>"
        '<body class="logged-out env-production page-responsive page-profile" '
        'style="word-wrap: break-word; background-color: var(--bgColor-default);">'
        '<div class="preview-column">'
        '<div class="Box"><div class="Box-body tmp-p-4">'
        '<article class="markdown-body entry-content container-lg f5" itemprop="text">'
        "%s</article></div></div></div></body></html>"
    ) % (theme, css(), markdown_html)


if __name__ == "__main__":
    path = fetch(force="--force" in sys.argv)
    print(f"github css: {path} ({path.stat().st_size / 1024:.0f} KB)")
