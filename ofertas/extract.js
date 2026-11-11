// Extractor genérico de productos rebajados en una página de listado.
// Idea: todo producto rebajado muestra un precio "antiguo" (tachado o con una
// etiqueta tipo "Precio normal"). Desde ese precio subimos hasta la ficha del
// producto (el ancestro con enlace + imagen) y sacamos nombre, precio actual,
// URL e imagen. Devuelve una lista de objetos planos.
() => {
  const PRICE_RE = /(?:€\s*(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?))|(?:(\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:€|EUR))/;
  const OLD_LABEL_RE = /precio\s+(normal|original|anterior|inicial|mediano|recomendado)|[uú]ltimo\s+precio\s+m[aá]s\s+bajo|\bantes\b|\bpvpr?\b|originally|was\b/i;

  const toNumber = (txt) => {
    const m = (txt || "").replace(/ /g, " ").match(PRICE_RE);
    if (!m) return null;
    let s = (m[1] || m[2] || "").replace(/\s/g, "");
    if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
    else if (/\.\d{3}$/.test(s)) s = s.replace(/\./g, "");
    const n = parseFloat(s);
    return Number.isFinite(n) && n > 0 && n < 5000 ? n : null;
  };

  // Elementos "hoja" que contienen un precio (ningún hijo contiene otro precio).
  const priceEls = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  for (let el = walker.currentNode; el; el = walker.nextNode()) {
    if (!(el instanceof HTMLElement) || ["SCRIPT", "STYLE", "NOSCRIPT"].includes(el.tagName)) continue;
    const text = el.textContent || "";
    if (text.length > 80 || toNumber(text) === null) continue;
    const childHasPrice = [...el.children].some((c) => toNumber(c.textContent) !== null);
    if (!childHasPrice) priceEls.push(el);
  }

  const isStruck = (el) => {
    for (let n = el, i = 0; n && i < 3; n = n.parentElement, i++) {
      if (["S", "DEL", "STRIKE"].includes(n.tagName)) return true;
      const deco = getComputedStyle(n).textDecorationLine || getComputedStyle(n).textDecoration || "";
      if (deco.includes("line-through")) return true;
    }
    return false;
  };
  const labelText = (n) => ((n.getAttribute && n.getAttribute("aria-label")) || "") + " " + (n.textContent || "");
  const countPrices = (n) => priceEls.filter((p) => n.contains(p)).length;
  // Etiqueta "Precio normal", "Último precio más bajo"... en el propio elemento,
  // en un hermano anterior, o en un padre que solo contiene este precio.
  const hasOldLabel = (el) => {
    if (OLD_LABEL_RE.test(labelText(el))) return true;
    let sib = el.previousElementSibling;
    for (let i = 0; sib && i < 2; sib = sib.previousElementSibling, i++) {
      if (toNumber(sib.textContent) !== null) break;
      if (OLD_LABEL_RE.test(labelText(sib))) return true;
    }
    for (let n = el.parentElement, i = 0; n && i < 2; n = n.parentElement, i++) {
      if (countPrices(n) > 1) break;
      const t = labelText(n);
      if (t.length < 120 && OLD_LABEL_RE.test(t)) return true;
    }
    return false;
  };

  const findCard = (el) => {
    for (let n = el.parentElement, depth = 0; n && n !== document.body && depth < 12; n = n.parentElement, depth++) {
      const link = n.matches("a[href]") ? n : n.querySelector("a[href]");
      const img = n.querySelector("img");
      if (link && img) {
        // Si el ancestro abarca varios productos, nos hemos pasado.
        const hrefs = new Set([...n.querySelectorAll("a[href]")].map((a) => a.href.split("?")[0].split("#")[0]));
        if (hrefs.size > 4) return null;
        return n;
      }
    }
    return null;
  };

  const firstSrcset = (v) => (v || "").split(",").map((s) => s.trim().split(" ")[0]).filter(Boolean).pop();
  const usable = (s) => s && !s.startsWith("data:") && !/blank|placeholder|spacer|1x1/i.test(s);
  const imgSrc = (card) => {
    // Primero imágenes ya cargadas; luego atributos de carga diferida y <picture>.
    const cands = [];
    for (const img of card.querySelectorAll("img")) {
      if (img.naturalWidth > 40) cands.push(img.currentSrc || img.src);
      cands.push(img.getAttribute("data-src"), img.getAttribute("data-original"),
        firstSrcset(img.getAttribute("srcset")), firstSrcset(img.getAttribute("data-srcset")), img.src);
    }
    for (const src of card.querySelectorAll("picture source")) {
      cands.push(firstSrcset(src.getAttribute("srcset")), firstSrcset(src.getAttribute("data-srcset")));
    }
    const src = cands.find(usable);
    return src ? new URL(src, location.href).href : null;
  };

  // Texto alternativo que describe la foto ("Una zapatilla negra se muestra…"), no el producto.
  const DESCRIPTIVE_ALT = /\bse muestra\b|\bfotograf|\bimagen de\b|\bmodelo (lleva|viste)\b|\bsobre fondo\b|\bvista (frontal|lateral|trasera)\b/i;
  const cleanLines = (txt) => (txt || "").split("\n").map((s) => s.trim())
    .filter((s) => s.length >= 3 && s.length <= 120 && toNumber(s) === null && !/^-?\d+\s*%$/.test(s) && !OLD_LABEL_RE.test(s));

  const productName = (card, link, img) => {
    const cands = [];
    // 1) Título explícito de la ficha
    // (en este orden: querySelectorAll con comas devolvería orden de documento)
    for (const sel of ["h1,h2,h3,h4,h5", "[class*='title' i]", "[data-testid*='name' i]", "[class*='name' i]:not([class*='brand' i])"]) {
      for (const h of card.querySelectorAll(sel)) cands.push(...cleanLines(h.innerText || h.textContent));
    }
    // 2) Texto de los enlaces y atributos del enlace
    const linkTexts = [...card.querySelectorAll("a[href]")].flatMap((a) => cleanLines(a.innerText || a.textContent));
    cands.push(...linkTexts.sort((a, b) => b.length - a.length).slice(0, 1));
    cands.push(link.getAttribute("aria-label"), link.getAttribute("title"));
    // 3) Texto alternativo de la foto, si no es una descripción de la imagen
    const alt = img && img.alt;
    if (alt && !DESCRIPTIVE_ALT.test(alt)) cands.push(alt);
    // 4) La línea más larga de la ficha
    cands.push(...cleanLines(card.innerText).sort((a, b) => b.length - a.length).slice(0, 1));
    if (alt) cands.push(alt);
    return (cands.find((s) => s && s.trim().length >= 3 && !/^(nuevo|nueva|oferta|rebajas?|sale)$/i.test(s.trim())) || "").trim();
  };

  const out = new Map();
  for (const el of priceEls) {
    if (!isStruck(el) && !hasOldLabel(el)) continue;
    const old = toNumber(el.textContent);
    const card = findCard(el);
    if (!old || !card) continue;
    const others = priceEls.filter((p) => p !== el && card.contains(p) && !isStruck(p) && !hasOldLabel(p))
      .map((p) => toNumber(p.textContent)).filter((n) => n && n < old);
    if (!others.length) continue;
    const price = Math.min(...others);
    const link = card.matches("a[href]") ? card : card.querySelector("a[href]");
    const url = new URL(link.getAttribute("href"), location.href).href;
    const key = url.split("#")[0];
    const img = card.querySelector("img");
    const prev = out.get(key);
    if (prev && prev.price / prev.old_price <= price / old) continue;
    out.set(key, {
      url: key, name: productName(card, link, img), price, old_price: old, image: imgSrc(card),
      text: (card.innerText || "").slice(0, 300),  // para detectar la marca en multimarca
    });
  }
  return [...out.values()];
}
