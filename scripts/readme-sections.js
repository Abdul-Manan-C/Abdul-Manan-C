return (() => {
  const readme = document.querySelector('#readme') || document.querySelector('#wrap') || document.querySelector('.markdown-body');
  if (!readme) return { error: 'no readme element' };

  // A block's real extent is the union of its visible children - a
  // <picture> wrapper is an inline span, so its own box is meaningless.
  const union = (el) => {
    let top = Infinity, bottom = -Infinity, left = Infinity, right = -Infinity;
    const consider = (r) => {
      if (r.width < 1 || r.height < 1) return;
      top = Math.min(top, r.top); bottom = Math.max(bottom, r.bottom);
      left = Math.min(left, r.left); right = Math.max(right, r.right);
    };
    consider(el.getBoundingClientRect());
    for (const img of el.querySelectorAll('img')) consider(img.getBoundingClientRect());
    return { top, bottom, left, right };
  };

  const out = [];
  let n = 0;
  for (const el of readme.children) {
    const u = union(el);
    if (!isFinite(u.top)) continue;
    const text = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 52);
    const imgs = [...el.querySelectorAll('img')].map((i) => {
      const ir = i.getBoundingClientRect();
      const src = (i.currentSrc || i.src || '').split('/').pop();
      // GitHub proxies external images through camo, whose URL ends in a hex
      // blob - show the real filename instead.
      const pretty = /^[0-9a-f]{40,}$/.test(src) ? '(external image)' : src.split('?')[0];
      return { src: pretty, w: Math.round(ir.width), h: Math.round(ir.height),
               top: Math.round(ir.top + scrollY) };
    });
    out.push({
      i: ++n,
      tag: el.tagName.toLowerCase(),
      top: Math.round(u.top + scrollY),
      bottom: Math.round(u.bottom + scrollY),
      h: Math.round(u.bottom - u.top),
      w: Math.round(u.right - u.left),
      text,
      imgs,
    });
  }

  const gaps = [];
  for (let i = 1; i < out.length; i++) {
    gaps.push({ after: out[i - 1].i, before: out[i].i,
                gap: out[i].top - out[i - 1].bottom,
                from: out[i - 1].text || out[i - 1].tag,
                to: out[i].text || out[i].tag });
  }

  return { blocks: out, gaps };
})();
