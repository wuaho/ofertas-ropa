"""Tiendas que necesitan navegador (H&M, COS, Arket, Mango, Uniqlo, Zalando).

Abre cada listado con Chromium headless (Playwright), acepta cookies, hace scroll
o pasa de página, y aplica extract.js: un extractor genérico que encuentra los
productos con precio tachado/"precio normal" y saca nombre, precios, URL e imagen.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from . import config
from .common import Deal, classify, discount_pct

log = logging.getLogger(__name__)
EXTRACT_JS = (Path(__file__).parent / "extract.js").read_text()

COOKIE_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "button#didomi-notice-agree-button",
    "button[data-testid='uc-accept-all-button']",
]
COOKIE_TEXT = re.compile(r"^\s*(aceptar( todo| todas| cookies)?|acepto|accept( all)?|permitir todas?|de acuerdo|entendido)\s*$", re.I)
LOAD_MORE_TEXT = re.compile(r"(cargar|ver|mostrar)\s+(m[aá]s|siguiente)|load more", re.I)

STEALTH_JS = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"


class Browser:
    """Un único Chromium para todas las tiendas."""

    def __init__(self, debug_dir: Path | None = None):
        from playwright.sync_api import sync_playwright  # import tardío: solo si hace falta

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"]
        )
        self.debug_dir = debug_dir
        self.pages_loaded = 0

    def new_context(self):
        ctx = self._browser.new_context(
            locale="es-ES",
            timezone_id="Europe/Madrid",
            user_agent=config.HEADERS["User-Agent"],
            viewport={"width": 1366, "height": 900},
        )
        ctx.add_init_script(STEALTH_JS)
        return ctx

    def close(self):
        self._browser.close()
        self._pw.stop()

    # ------------------------------------------------------------------ helpers

    def _accept_cookies(self, page) -> None:
        for sel in COOKIE_SELECTORS:
            try:
                if page.locator(sel).first.is_visible(timeout=500):
                    page.locator(sel).first.click(timeout=2000)
                    return
            except Exception:
                pass
        try:
            btn = page.get_by_role("button", name=COOKIE_TEXT).first
            if btn.is_visible(timeout=1000):
                btn.click(timeout=2000)
        except Exception:
            pass

    def _scroll_all(self, page, max_rounds: int) -> None:
        """Scroll hasta el final (y pulsa 'cargar más') hasta que no crezca la página."""
        last_height, still = 0, 0
        for _ in range(max_rounds):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(700)
            try:
                more = page.get_by_role("button", name=LOAD_MORE_TEXT).first
                if more.is_visible(timeout=300):
                    more.click(timeout=2000)
                    page.wait_for_timeout(1200)
            except Exception:
                pass
            height = page.evaluate("document.body.scrollHeight")
            still = still + 1 if height == last_height else 0
            if still >= 3:
                break
            last_height = height

    def extract(self, ctx, url: str, scroll_rounds: int, store_id: str) -> list[dict] | None:
        """Devuelve los productos rebajados de una URL, o None si la página no carga."""
        page = ctx.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            self.pages_loaded += 1
            if resp is not None and resp.status >= 400:
                log.warning("[%s] %s -> HTTP %s", store_id, url, resp.status)
                return None
            page.wait_for_timeout(2500)
            self._accept_cookies(page)
            self._scroll_all(page, scroll_rounds)
            items = page.evaluate(EXTRACT_JS)
            if self.debug_dir:
                self.debug_dir.mkdir(parents=True, exist_ok=True)
                name = hashlib.md5(url.encode()).hexdigest()[:8]
                (self.debug_dir / f"{store_id}_{name}.html").write_text(page.content())
                page.screenshot(path=str(self.debug_dir / f"{store_id}_{name}.png"), full_page=False)
            log.info("[%s] %s -> %d rebajados", store_id, url, len(items))
            return items
        except Exception as e:
            log.warning("[%s] %s falló: %s", store_id, url, e)
            return None
        finally:
            page.close()

    def discover_links(self, ctx, start: str, pattern: str, limit: int) -> list[str]:
        page = ctx.new_page()
        try:
            page.goto(start, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(2500)
            self._accept_cookies(page)
            hrefs = page.eval_on_selector_all("a[href]", "els => els.map(a => a.href)")
        finally:
            page.close()
        rx = re.compile(pattern)
        seen: list[str] = []
        for h in hrefs:
            h = h.split("#")[0].split("?")[0]
            if rx.search(h) and h not in seen:
                seen.append(h)
        return seen[:limit]


# ---------------------------------------------------------------------- scan


def _urls_for(store: dict) -> list[list[list[str]]]:
    """Grupos en orden de preferencia; cada grupo es una lista de secuencias
    (las páginas 1..N de una misma URL). Se usa el primer grupo que dé ofertas."""
    groups = []
    for group in store.get("sources", []):
        seqs = []
        for tpl in group:
            tpl = tpl.replace("{brands}", ".".join(store.get("brands", [])))
            if "{page}" in tpl:
                seqs.append([tpl.replace("{page}", str(p)) for p in range(1, store.get("max_pages", 1) + 1)])
            else:
                seqs.append([tpl])
        groups.append(seqs)
    return groups


def scan(store: dict, browser: Browser, max_categories: int, full: bool = False) -> tuple[list[Deal], str]:
    ctx = browser.new_context()
    try:
        groups = _urls_for(store)
        if store.get("discover"):
            d = store["discover"]
            found = browser.discover_links(ctx, d["start"], d["pattern"], min(d.get("limit", 30), max_categories))
            log.info("[%s] %d categorías descubiertas", store["id"], len(found))
            groups.append([[u] for u in found])
        if full and len(groups) > 1:
            groups = groups[-1:]  # el último grupo es el recorrido amplio

        rounds = store.get("scroll_rounds", 15)
        any_loaded = False
        for i, seqs in enumerate(groups):
            raw: dict[str, dict] = {}
            for pages in seqs:
                for url in pages:
                    items = browser.extract(ctx, url, rounds, store["id"])
                    if items is None:
                        break  # página inexistente: fin de esta secuencia
                    any_loaded = True
                    new = [it for it in items if it["url"] not in raw]
                    for it in items:
                        raw.setdefault(it["url"], it)
                    if not new:
                        break  # la página no aporta nada nuevo: no seguimos paginando
            if raw:
                is_sale_group = i == 0 and len(groups) > 1 or store.get("sale_only")
                return _to_deals(store, raw.values()), "ofertas" if is_sale_group else "completo"
        if not any_loaded:
            raise RuntimeError("ninguna página cargó (¿bloqueo antibots o URLs cambiadas?)")
        return [], "ofertas"
    finally:
        ctx.close()


def _to_deals(store: dict, items) -> list[Deal]:
    min_pct = store.get("min_discount", config.MIN_DISCOUNT_PCT)
    out = []
    for it in items:
        price_c, old_c = round(it["price"] * 100), round(it["old_price"] * 100)
        if not it.get("name") or old_c <= price_c:
            continue
        pct = discount_pct(price_c, old_c)
        if pct < min_pct:
            continue
        name = re.sub(r"\s+", " ", it["name"]).strip()
        out.append(Deal(
            store=store["id"],
            store_name=store["name"],
            product_id=hashlib.md5(it["url"].encode()).hexdigest()[:12],
            name=name,
            price=price_c / 100,
            old_price=old_c / 100,
            discount=pct,
            url=it["url"],
            image=it.get("image"),
            category="",
            tipo=classify(name, []),
            sizes=None,
            colors=[],
        ))
    return out
