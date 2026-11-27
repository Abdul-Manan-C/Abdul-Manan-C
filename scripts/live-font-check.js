return (async () => {
  const imgs = [...document.querySelectorAll("#readme img, .markdown-body img")];
  const svg = imgs.filter((i) => i.src.includes("stack.svg") || i.src.includes("hero.svg"));
  const out = [];
  for (const i of svg) {
    const res = await fetch(i.src);
    const text = await res.text();
    out.push({
      visible: i.getAttribute("src").slice(0, 80),
      camo: i.src.includes("camo.githubusercontent.com"),
      status: res.status,
      bytes: text.length,
      fontFaces: (text.match(/@font-face/g) || []).length,
      embeddedWoff2: text.includes("data:font/woff2;base64,"),
      interFace: text.includes("font-family:'Inter'"),
      monoFace: text.includes("font-family:'JetBrains Mono'"),
    });
  }
  return out;
})()
