"""Uso:
    python -m ofertas                                   # todas las tiendas, escribe docs/
    python -m ofertas --only zara --max-categories 5 --debug   # prueba rápida
    python -m ofertas --only hm --only cos --debug      # tiendas con navegador
    python -m ofertas --compare --only zara             # ¿se pierde algo leyendo solo ofertas?
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import asos, browser, config, itx, shopify, zara
from .build import build
from .http import Http
from .notify import telegram_summary

ALL_STORES = (
    [("zara", config.ZARA, zara.scan)]
    + [(s["id"], s, itx.scan) for s in config.ITX_STORES]
    + [(s["id"], s, shopify.scan) for s in config.SHOPIFY_STORES]
    + [("asos", config.ASOS, asos.scan)]
    + [(s["id"], s, browser.scan) for s in config.BROWSER_STORES]
)


class Clients:
    """Crea el cliente adecuado por tienda. El navegador se abre una sola vez y solo si hace falta."""

    def __init__(self, debug: bool):
        self.debug = debug
        self._browser: browser.Browser | None = None

    def get(self, store_id: str, cfg: dict, scan):
        if scan is browser.scan:
            if self._browser is None:
                self._browser = browser.Browser(Path("debug") / "browser" if self.debug else None)
            return self._browser
        return Http(cfg["base"], Path("debug") / store_id if self.debug else None)

    def close(self):
        if self._browser:
            self._browser.close()


def main(argv: list[str] | None = None) -> int:
    ids = ", ".join(s[0] for s in ALL_STORES)
    ap = argparse.ArgumentParser(description="Ofertas diarias de moda hombre")
    ap.add_argument("--out", default="docs", help="carpeta de salida (por defecto docs/)")
    ap.add_argument("--only", action="append", help=f"solo esta tienda ({ids})")
    ap.add_argument("--skip", action="append", help="saltar esta tienda")
    ap.add_argument("--max-categories", type=int, default=config.MAX_CATEGORIES_PER_STORE)
    ap.add_argument("--full", action="store_true", help="recorrer todo el catálogo, no solo ofertas")
    ap.add_argument("--compare", action="store_true", help="compara modo ofertas vs completo (no escribe nada)")
    ap.add_argument("--debug", action="store_true", help="guarda respuestas, HTML y capturas en debug/")
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("ofertas")

    stores = [s for s in ALL_STORES if (not args.only or s[0] in args.only) and s[0] not in (args.skip or [])]
    clients = Clients(args.debug)
    try:
        if args.compare:
            return compare(stores, clients, args)
        results = run(stores, clients, args, log)
    finally:
        clients.close()

    payload = build(results, Path(args.out))
    if not args.no_notify:
        telegram_summary(payload, os.getenv("PAGE_URL"))
    ok = sum(1 for r in results.values() if r["deals"] is not None)
    log.info("Hecho: %d/%d tiendas OK, %d ofertas en total", ok, len(results), payload["count"])
    return 0 if ok else 1


def run(stores, clients: Clients, args, log) -> dict[str, dict]:
    results: dict[str, dict] = {}
    full = args.full or config.SCAN_MODE == "full"
    for store_id, cfg, scan in stores:
        try:
            client = clients.get(store_id, cfg, scan)
            deals, mode = scan(cfg, client, args.max_categories, full)
            results[store_id] = {"name": cfg["name"], "deals": deals, "mode": mode}
            log.info("[%s] %d ofertas, modo %s", store_id, len(deals), mode)
        except Exception as e:  # una tienda caída no tumba a las demás
            log.error("[%s] FALLÓ: %s", store_id, e)
            results[store_id] = {"name": cfg["name"], "deals": None, "error": str(e)[:300]}
    return results


def compare(stores, clients: Clients, args) -> int:
    """Ejecuta modo ofertas y modo completo y muestra qué se perdería usando solo ofertas."""
    for store_id, cfg, scan in stores:
        try:
            sale, mode = scan(cfg, clients.get(store_id, cfg, scan), args.max_categories, False)
            if mode != "ofertas":
                print(f"\n== {cfg['name']}: no tiene sección de ofertas ahora mismo, siempre usa el modo completo")
                continue
            if scan is browser.scan and len(cfg.get("sources", [])) < 2 and not cfg.get("discover"):
                print(f"\n== {cfg['name']}: solo tiene sección de ofertas configurada, nada que comparar")
                continue
            full, _ = scan(cfg, clients.get(store_id, cfg, scan), args.max_categories, True)
        except Exception as e:
            print(f"\n== {cfg['name']}: FALLÓ ({e})")
            continue
        sale_keys, full_keys = {d.key for d in sale}, {d.key for d in full}
        missing = sorted((d for d in full if d.key not in sale_keys), key=lambda d: -d.discount)
        extra = [d for d in sale if d.key not in full_keys]
        print(f"\n== {cfg['name']}: ofertas={len(sale)} | completo={len(full)} | "
              f"solo en completo={len(missing)} | solo en ofertas={len(extra)}")
        for d in missing:
            print(f"  - {d.name} | {d.category} | {d.price:.2f} € (antes {d.old_price:.2f}) -{d.discount}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
