"""ASOS: API de búsqueda que usa su propia web.

GET /api/product/search/v2/categories/{cid}?offset=&limit=200&store=ES...
Cada producto trae name, brandName, price.current / price.previous / price.rrp,
url (relativa) e imageUrl (sin esquema). Las rebajas de hombre son miles de
artículos, así que se filtra por marca y descuento mínimo.
"""

from __future__ import annotations

import logging

from . import config
from .common import Deal, classify, discount_pct
from .http import Http

log = logging.getLogger(__name__)
PAGE_SIZE = 200


def scan(store: dict, http: Http, max_categories: int, full: bool = False) -> tuple[list[Deal], str]:
    url = f"{store['base']}/api/product/search/v2/categories/{store['category_id']}"
    params = {
        "limit": PAGE_SIZE, "store": "ES", "lang": "es-ES", "currency": "EUR",
        "country": "ES", "sizeSchema": "EU", "channel": "desktop-web", "rowlength": 4,
    }
    deals: list[Deal] = []
    offset, total = 0, None
    while offset < store.get("max_items", 12_000):
        data = http.get_json(url, {**params, "offset": offset})
        products = data.get("products") or []
        total = data.get("itemCount", total)
        if not products:
            break
        for p in products:
            deal = parse_product(p, store)
            if deal:
                deals.append(deal)
        offset += len(products)
        if total is not None and offset >= total:
            break
    log.info("[asos] %d productos revisados de %s, %d pasan el filtro", offset, total, len(deals))
    return deals, "ofertas"


def _brand_ok(brand: str, store: dict) -> bool:
    wanted = [b.lower() for b in store.get("brands", [])]
    if not wanted:
        return True  # lista vacía = todas las marcas
    b = (brand or "").lower()
    return any(w == b or b.startswith(w + " ") or w in b for w in wanted)


def _value(price: dict, key: str) -> float | None:
    v = (price.get(key) or {}).get("value")
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_product(p: dict, store: dict) -> Deal | None:
    brand = p.get("brandName") or ""
    if not _brand_ok(brand, store):
        return None
    price = p.get("price") or {}
    current = _value(price, "current")
    old = _value(price, "previous") or _value(price, "rrp")
    if not current or not old or old <= current:
        return None
    price_c, old_c = round(current * 100), round(old * 100)
    pct = discount_pct(price_c, old_c)
    if pct < store.get("min_discount", config.MIN_DISCOUNT_PCT):
        return None
    name = (p.get("name") or "").strip()
    rel = (p.get("url") or "").lstrip("/")
    image = p.get("imageUrl")
    if image and image.startswith("//"):
        image = "https:" + image
    elif image and not image.startswith("http"):
        image = "https://" + image
    return Deal(
        store=store["id"],
        store_name=store["name"],
        product_id=str(p.get("id")),
        name=name,
        price=price_c / 100,
        old_price=old_c / 100,
        discount=pct,
        url=f"{store['base']}/es/{rel}" if rel and not rel.startswith("http") else rel,
        image=image,
        category=brand,
        tipo=classify(name, []),
        sizes=None,
        colors=[p["colour"]] if p.get("colour") else [],
    )
