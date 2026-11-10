"""Zara: endpoints ?ajax=true de la propia web.

  1. /es/es/categories?ajax=true                    -> árbol de categorías (ids internos)
  2. /es/es/category/{id}/products?ajax=true        -> productos con price/oldPrice
"""

from __future__ import annotations

import logging
from typing import Iterator
from urllib.parse import quote

from . import config
from .common import Deal, cents, classify, discount_pct, men_leaf_categories, pick_categories
from .http import Http

log = logging.getLogger(__name__)
IMG_WIDTH = 500


def scan(cfg: dict, http: Http, max_categories: int, full: bool = False) -> tuple[list[Deal], str]:
    root = cfg["base"] + cfg["path"]
    tree = http.get_json(f"{root}/categories", {"ajax": "true"})
    leaves = men_leaf_categories(tree, max_categories)
    if not leaves:
        raise RuntimeError("No encuentro la sección de hombre en el árbol de Zara")
    leaves, mode = pick_categories(leaves, full)
    log.info("[zara] modo %s: %d categorías", mode, len(leaves))

    deals: dict[str, Deal] = {}
    for cid, path in leaves:
        try:
            data = http.get_json(f"{root}/category/{cid}/products", {"ajax": "true"})
        except RuntimeError as e:
            log.warning("[zara] categoría %s falló: %s", cid, e)
            continue
        for deal in parse_products(data, cfg, path):
            prev = deals.get(deal.key)
            if not prev or deal.discount > prev.discount:
                deals[deal.key] = deal
    return list(deals.values()), mode


def iter_components(data: dict) -> Iterator[dict]:
    for group in data.get("productGroups") or []:
        for element in group.get("elements") or []:
            for comp in element.get("commercialComponents") or []:
                if isinstance(comp, dict):
                    yield comp


def parse_products(data: dict, cfg: dict, path: list[str]) -> Iterator[Deal]:
    for comp in iter_components(data):
        deal = parse_component(comp, cfg, path)
        if deal:
            yield deal


def parse_component(comp: dict, cfg: dict, path: list[str]) -> Deal | None:
    name = (comp.get("name") or "").strip()
    if not name:
        return None
    colors = (comp.get("detail") or {}).get("colors") or []

    # El precio puede venir en el producto o en cada color.
    candidates = [(cents(comp.get("price")), cents(comp.get("oldPrice")), None)]
    for c in colors:
        candidates.append((cents(c.get("price")), cents(c.get("oldPrice")), c))
    candidates = [(p, o, c) for p, o, c in candidates if p and o and o > p]
    if not candidates:
        return None
    price_c, old_c, color = min(candidates, key=lambda x: x[0] / x[1])
    pct = discount_pct(price_c, old_c)
    if pct < config.MIN_DISCOUNT_PCT:
        return None

    discounted = [
        str(c.get("name") or "").strip()
        for c in colors
        if (cents(c.get("oldPrice")) or 0) > (cents(c.get("price")) or 0) > 0
    ]
    return Deal(
        store=cfg["id"],
        store_name=cfg["name"],
        product_id=str(comp.get("id")),
        name=name.capitalize() if name.isupper() else name,
        price=price_c / 100,
        old_price=old_c / 100,
        discount=pct,
        url=_url(comp, cfg),
        image=_image(comp, color or (colors[0] if colors else None)),
        category=" > ".join(p for p in path[1:] if p),
        tipo=classify(name, path),
        sizes=None,  # el listado de Zara no trae tallas
        colors=[c for c in discounted if c],
    )


def _url(comp: dict, cfg: dict) -> str:
    seo = comp.get("seo") or {}
    root = cfg["base"] + cfg["path"]
    keyword, seo_id = seo.get("keyword"), seo.get("seoProductId")
    if keyword and seo_id:
        url = f"{root}/{keyword}-p{seo_id}.html"
        if seo.get("discernProductId"):
            url += f"?v1={seo['discernProductId']}"
        return url
    return f"{root}/search?searchTerm={quote(comp.get('name', ''))}"


def _image(comp: dict, color: dict | None) -> str | None:
    sources = []
    if color:
        sources.append(color.get("xmedia") or [])
    sources.append(comp.get("xmedia") or [])
    for xmedia in sources:
        for m in xmedia:
            if not isinstance(m, dict):
                continue
            if m.get("url"):
                return m["url"].replace("{width}", str(IMG_WIDTH))
            if m.get("path") and m.get("name"):
                ts = f"?ts={m['timestamp']}" if m.get("timestamp") else ""
                return f"https://static.zara.net/photos//{m['path']}/w/{IMG_WIDTH}/{m['name']}.jpg{ts}"
    return None
