"""Tiendas Shopify (p. ej. Nude Project): /products.json es público.

Cada producto trae variantes con price y compare_at_price (precio anterior),
disponibilidad por talla y tags. Sirve para cualquier marca en Shopify.
"""

from __future__ import annotations

import logging

from . import config
from .common import Deal, cents, classify, discount_pct
from .http import Http

log = logging.getLogger(__name__)
MAX_PAGES = 40  # 250 productos por página


def scan(store: dict, http: Http, max_categories: int, full: bool = False) -> tuple[list[Deal], str]:
    deals: list[Deal] = []
    seen = 0
    for page in range(1, MAX_PAGES + 1):
        data = http.get_json(f"{store['base']}/products.json", {"limit": 250, "page": page})
        products = data.get("products") or []
        if not products:
            break
        seen += len(products)
        for p in products:
            deal = parse_product(p, store)
            if deal:
                deals.append(deal)
    log.info("[%s] %d productos revisados", store["id"], seen)
    return deals, "completo"


def _wanted(product: dict, store: dict) -> bool:
    tags = {t.lower() for t in (product.get("tags") or [])} if isinstance(product.get("tags"), list) \
        else {t.strip().lower() for t in str(product.get("tags") or "").split(",")}
    exclude = {t.lower() for t in store.get("exclude_tags", [])}
    include = {t.lower() for t in store.get("include_tags", [])}
    if tags & exclude and not tags & include:
        return False  # p. ej. solo-mujer
    return True


def parse_product(p: dict, store: dict) -> Deal | None:
    if not _wanted(p, store):
        return None
    variants = p.get("variants") or []
    pairs = []
    for v in variants:
        price, old = cents(_eur_to_cents(v.get("price"))), cents(_eur_to_cents(v.get("compare_at_price")))
        if price and old and old > price:
            pairs.append((price, old))
    if not pairs:
        return None
    price_c, old_c = min(pairs, key=lambda x: x[0] / x[1])
    pct = discount_pct(price_c, old_c)
    if pct < store.get("min_discount", config.MIN_DISCOUNT_PCT):
        return None
    sizes = []
    for v in variants:
        if v.get("available", True):
            label = v.get("option1") or v.get("title")
            if label and label not in sizes and label.lower() != "default title":
                sizes.append(str(label))
    images = p.get("images") or []
    name = (p.get("title") or "").strip()
    return Deal(
        store=store["id"],
        store_name=store["name"],
        product_id=str(p.get("id")),
        name=name,
        price=price_c / 100,
        old_price=old_c / 100,
        discount=pct,
        url=f"{store['base']}/products/{p.get('handle')}",
        image=images[0].get("src") if images else None,
        category=str(p.get("product_type") or ""),
        tipo=classify(name, [str(p.get("product_type") or "")]),
        sizes=sizes,
        colors=[],
    )


def _eur_to_cents(value):
    """Shopify da los precios como "59.00" (euros)."""
    if value in (None, ""):
        return None
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None
