return (() => {
  const art = document.querySelector('article.markdown-body');
  if (!art) return { error: 'no article', url: location.href };
  const artR = art.getBoundingClientRect();
  const tables = [...art.querySelectorAll('table')].map((t, i) => {
    const r = t.getBoundingClientRect();
    const td = t.querySelector('td');
    const tdR = td ? td.getBoundingClientRect() : null;
    const tdCs = td ? getComputedStyle(td) : null;
    const imgs = [...t.querySelectorAll('img')].map((im) => {
      const ir = im.getBoundingClientRect();
      return { src: (im.currentSrc || im.src).split('/').pop(),
               w: Math.round(ir.width),
               scale: im.naturalWidth ? Math.round((ir.width / im.naturalWidth) * 1000) / 1000 : 0 };
    });
    return {
      i, tableW: Math.round(r.width), clientW: t.clientWidth, scrollW: t.scrollWidth,
      cellW: tdR ? Math.round(tdR.width) : null,
      cellPad: tdCs ? tdCs.padding : null,
      cellContentW: tdR && tdCs
        ? Math.round(tdR.width - parseFloat(tdCs.paddingLeft) - parseFloat(tdCs.paddingRight))
        : null,
      imgs: imgs.slice(0, 2),
    };
  });
  const p = art.querySelector('p');
  return {
    innerWidth: window.innerWidth,
    docScrollW: document.documentElement.scrollWidth,
    articleW: Math.round(artR.width),
    articleX: Math.round(artR.left),
    bodyPx: p ? getComputedStyle(p).fontSize : null,
    tables,
  };
})();
