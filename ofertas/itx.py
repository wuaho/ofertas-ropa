"""Pull&Bear, Bershka y Massimo Dutti: API itxrest de Inditex.

Flujo:
  1. /itxrest/2/catalog/store/{store}/{catalog}/category         -> árbol de categorías
  2. /itxrest/3/.../category/{id}/product?showProducts=false      -> productIds de cada categoría
  3. /itxrest/3/.../productsArray?productIds=a,b,c                -> detalle con price/oldPrice por talla
"""

from __future__ import annotations

import logging
from typing import Iterator

from . import config
from .common import (
    Deal,
    cents,
    classify,
    discount_pct,
    find_media_urls,
    men_leaf_categories,
    pick_categories,
    slugify,
)
from .http import Http

log = logging.getLogger(__name__)


def _api(store: dict, version: int) -> str:
    return f"{store['base']}/itxrest/{version}/catalog/store/{store['store_id']}/{store['catalog_id']}"


def _params(**extra) -> dict:
    return {"languageId": config.LANGUAGE_ID, "appId": 1, **extra}


def scan(store: dict, http: Http, max_categories: int, full: bool = False) -> tuple[list[Deal], str]:
    tree = http.get_json(f"{_api(store, 2)}/category", _params(typeCatalog=1))
    leaves = men_leaf_categories(tree, max_categories)
    if not leaves:
        raise RuntimeError("No encuentro la sección de hombre en el árbol de categorías")
    leaves, mode = pick_categories(leaves, full)
    log.info("[%s] modo %s: %d categorías", store["id"], mode, len(leaves))

    product_path: dict[str, list[str]] = {}
    for cid, path in leaves:
        try:
            data = http.get_json(f"{_api(store, 3)}/category/{cid}/product", _params(showProducts="false"))
        except RuntimeError as e:
            log.warning("[%s] categoría %s falló: %s", store["id"], cid, e)
            continue
        for pid in data.get("productIds") or []:
            product_path.setdefault(str(pid), path)
    log.info("[%s] %d productos únicos", store["id"], len(product_path))

    deals: dict[str, Deal] = {}
    ids = list(product_path)
    for i in range(0, len(ids), config.PRODUCTS_BATCH):
        batch = ids[i : i + config.PRODUCTS_BATCH]
        try:
            data = http.get_json(f"{_api(store, 3)}/productsArray", _params(productIds=",".join(batch)))
        except RuntimeError as e:
            log.warning("[%s] lote %d falló: %s", store["id"], i, e)
            continue
        for product in data.get("products") or []:
            path = product_path.get(str(product.get("id")), [])
            for deal in parse_product(product, store, path):
                prev = deals.get(deal.key)
                if not prev or deal.discount > prev.discount:
                    deals[deal.key] = deal
    return list(deals.values()), mode


def parse_product(product: dict, store: dict, path: list[str]) -> Iterator[Deal]:
    summaries = product.get("bundleProductSummaries") or [product]
    for summary in summaries:
        detail = summary.get("detail") or product.get("detail") or {}
        name = (summary.get("name") or product.get("name") or "").strip()
        pid = str(summary.get("id") or product.get("id"))
        best = None  # (price_c, old_c, color)
        discounted_colors: list[str] = []
        for color in detail.get("colors") or []:
            pairs = [
                (cents(s.get("price")), cents(s.get("oldPrice")))
                for s in color.get("sizes") or []
            ]
            pairs = [(p, o) for p, o in pairs if p and o and o > p]
            if not pairs:
                continue
            discounted_colors.append(str(color.get("name") or "").strip())
            p, o = min(pairs, key=lambda x: x[0] / x[1])
            if best is None or p / o < best[0] / best[1]:
                best = (p, o, color)
        if not best or not name:
            continue
        price_c, old_c, color = best
        pct = discount_pct(price_c, old_c)
        if pct < config.MIN_DISCOUNT_PCT:
            continue
        sizes = [
            str(s.get("name"))
            for s in color.get("sizes") or []
            if s.get("isBuyable") and str(s.get("visibilityValue", "SHOW")).upper() == "SHOW"
        ]
        yield Deal(
            store=store["id"],
            store_name=store["name"],
            product_id=pid,
            name=name.title() if name.isupper() else name,
            price=price_c / 100,
            old_price=old_c / 100,
            discount=pct,
            url=_product_url(summary, product, store, name, color),
            image=_image(detail, color),
            category=" > ".join(p for p in path[1:] if p) or (path[0] if path else ""),
            tipo=classify(name, path),
            sizes=sizes,
            colors=[c for c in discounted_colors if c],
        )


def _product_url(summary: dict, product: dict, store: dict, name: str, color: dict) -> str:
    color_id = color.get("id")
    raw = summary.get("productUrl") or product.get("productUrl")
    if raw and raw.startswith("http"):
        url = raw
    elif raw:
        url = f"{store['base']}/{config.COUNTRY}/{raw.lstrip('/')}"
        if store["url_suffix"] and not url.endswith(store["url_suffix"]):
            url += store["url_suffix"]
    else:
        # Patrón genérico de Inditex: /es/<slug>-c0p<id>.html
        pid = summary.get("id") or product.get("id")
        url = f"{store['base']}/{config.COUNTRY}/{slugify(name)}-c0p{pid}.html"
    if color_id:
        url += ("&" if "?" in url else "?") + f"colorId={color_id}"
    return url


def _image(detail: dict, color: dict) -> str | None:
    color_id = str(color.get("id") or "")
    xmedia = detail.get("xmedia") or []
    # Preferimos las fotos del color elegido
    for block in xmedia:
        if color_id and str(block.get("colorCode") or "") == color_id:
            for url in find_media_urls(block):
                return url
    for url in find_media_urls(xmedia):
        return url
    return None
