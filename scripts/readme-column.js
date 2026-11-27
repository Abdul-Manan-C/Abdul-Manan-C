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
