return (() => {
  const rect = (el) => { const r = el.getBoundingClientRect();
    return { x:+r.left.toFixed(1), y:+(r.top+scrollY).toFixed(1),
             w:+r.width.toFixed(1), h:+r.height.toFixed(1) }; };
  const imgs = [...document.images];
  const by = (name) => imgs.find((i) => (i.currentSrc || i.src).split('/').pop() === name);

  const pick = (sel, limit) => [...document.querySelectorAll(sel)].slice(0, limit || 99).map((el) => {
    const cs = getComputedStyle(el);
    return { text: el.textContent.trim().replace(/\s+/g, ' ').slice(0, 44),
             tag: el.tagName.toLowerCase(),
             size: cs.fontSize, weight: cs.fontWeight, family: cs.fontFamily.split(',')[0].replace(/"/g, ''),
             color: cs.color, decoration: cs.textDecorationLine,
             border: cs.borderBottomWidth + ' ' + cs.borderBottomColor,
             padding: cs.padding, margin: cs.margin,
             ...rect(el) };
  });

  return {
    headings: pick('h1, h2, h3, h4, h5, h6'),
    links: pick('.markdown-body a, #readme a', 14),
    body: pick('.markdown-body p, #readme p', 4),
    lists: pick('.markdown-body li, #readme li', 4),
    icons: ['github.svg','linkedin.svg','instagram.svg','fiverr.svg','tryhackme.svg','whatsapp.svg','mail.svg']
      .map((n) => by(n) ? { name: n, ...rect(by(n)) } : null).filter(Boolean),
    ctas: ['cta-primary.svg','cta-secondary.svg'].map((n) => by(n) ? { name: n, ...rect(by(n)) } : null).filter(Boolean),
    tiles: ['tile-build.svg','tile-security.svg','tile-studio.svg'].map((n) => by(n) ? { name: n, ...rect(by(n)) } : null).filter(Boolean),
    code: pick('pre, code', 4),
  };
})();
