return (() => {
  const art = document.querySelector('article.markdown-body') || document.querySelector('.markdown-body');
  if (!art) return { error: 'no article' };
  const R = art.getBoundingClientRect();
  const imgs = [...art.querySelectorAll('img')].map((i) => {
    const r = i.getBoundingClientRect();
    const raw = (i.getAttribute('src') || '').split('/').pop().split('?')[0];
    const cur = (i.currentSrc || i.src || '').split('/').pop();
    return {
      src: raw || cur,
      cur,
      w: Math.round(r.width),
      nat: i.naturalWidth,
      scale: i.naturalWidth ? Math.round((r.width / i.naturalWidth) * 1000) / 1000 : 0,
      svg: /\.svg$/i.test(raw) || /\.svg$/i.test(cur),
    };
  });
  const bad = imgs.filter((i) => i.svg && i.scale < 0.92);
  return {
    vw: innerWidth,
    articleW: Math.round(R.width),
    total: imgs.length,
    bad,
    all: imgs.map((i) => `${i.svg ? 'svg ' : 'img '} ${i.src.padEnd(38)} ${String(i.w).padStart(4)}/${String(i.nat).padEnd(4)} x${i.scale}`),
  };
})();
