const readme = document.querySelector("#readme") || document.querySelector(".markdown-body");
const out = { url: location.href, viewport: window.innerWidth, found: Boolean(readme) };
if (readme) {
  const r = readme.getBoundingClientRect();
  out.readme = {
    width: Math.round(r.width),
    left: Math.round(r.left),
    right: Math.round(r.right),
  };
  out.images = [...readme.querySelectorAll("img")].slice(0, 30).map((i) => {
    const b = i.getBoundingClientRect();
    return {
      src: (i.getAttribute("src") || "").split("/").pop().slice(0, 44),
      rendered: `${Math.round(b.width)}x${Math.round(b.height)}`,
      natural: `${i.naturalWidth}x${i.naturalHeight}`,
    };
  });
  out.tables = [...readme.querySelectorAll("table")].map((t) => {
    const b = t.getBoundingClientRect();
    return { width: Math.round(b.width), rows: t.rows.length, cells: t.rows[0]?.cells.length || 0 };
  });
}
return out;
