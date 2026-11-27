return (() => {
  const readme = document.querySelector('#readme') || document.querySelector('#wrap') || document.querySelector('.markdown-body');
  if (!readme) return { error: 'no readme element' };
  const R = readme.getBoundingClientRect();
  const doc = document.documentElement;

  const out = {
    viewport: innerWidth,
    readmeWidth: Math.round(R.width),
    docScrollWidth: doc.scrollWidth,
    docClientWidth: doc.clientWidth,
    pageScrollsHorizontally: doc.scrollWidth > doc.clientWidth + 1,
  };

  out.tables = [...readme.querySelectorAll('table')].map((t) => {
    const r = t.getBoundingClientRect();
    const cells = [...t.querySelectorAll('td')].map((td) => Math.round(td.getBoundingClientRect().width));
    return { width: Math.round(r.width), rows: t.rows.length, cols: t.rows[0] ? t.rows[0].cells.length : 0,
             clientW: t.clientWidth, scrollW: t.scrollWidth, cellWidths: cells.slice(0, 4) };
  });

  out.images = [...readme.querySelectorAll('img')].map((i) => {
    const r = i.getBoundingClientRect();
    const used = i.currentSrc || i.src || '';
    const scale = i.naturalWidth ? Math.round((r.width / i.naturalWidth) * 100) / 100 : 0;
    return { src: used.split('/').pop().split('?')[0],
             rendered: Math.round(r.width) + 'x' + Math.round(r.height),
             natural: i.naturalWidth + 'x' + i.naturalHeight,
             scale,
             ok: i.complete && i.naturalWidth > 0 };
  });
  out.broken = out.images.filter((i) => !i.ok).length;

  const over = [];
  readme.querySelectorAll('*').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    if (r.right > R.right + 2) {
      over.push({ tag: el.tagName.toLowerCase(), right: Math.round(r.right), limit: Math.round(R.right),
                  src: (el.getAttribute && el.getAttribute('src')) || el.textContent.trim().slice(0, 36) });
    }
  });
  out.overflowCount = over.length;
  out.overflow = over.slice(0, 10);

  // paragraph line length estimate - the 45-75ch rulebook band.
  // Uses Range rects so it measures the REAL rendered line boxes, not the
  // container width.
  out.prose = [...readme.querySelectorAll('p')].map((p) => {
    const cs = getComputedStyle(p);
    const px = parseFloat(cs.fontSize);
    const text = p.textContent.trim();

    // walk the text node by text node and collect distinct line-box tops
    const tops = new Set();
    const walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const rect of range.getClientRects()) {
        if (rect.width > 0.5 && rect.height > 0.5) tops.add(Math.round(rect.top));
      }
    }
    const lines = tops.size || 1;
    const perLine = Math.round(text.length / lines);
    return { chars: text.length, lines, charsPerLine: perLine,
             inBand: perLine >= 40 && perLine <= 78,
             px: Math.round(px), width: Math.round(p.getBoundingClientRect().width),
             centered: cs.textAlign === 'center',
             text: text.slice(0, 44) };
  }).filter((p) => p.chars > 30);

  return out;
})();
