"""Junta las ofertas de todas las tiendas, actualiza el historial y escribe docs/*.json."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config
from .common import Deal

log = logging.getLogger(__name__)


def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return default


def build(results: dict[str, dict], out_dir: Path, today: date | None = None) -> dict:
    """results: {store_id: {"name": str, "deals": [Deal] | None, "error": str | None}}"""
    today = today or date.today()
    today_s = today.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    deals_path, history_path = out_dir / "deals.json", out_dir / "history.json"

    previous = _load(deals_path, {"deals": []})
    history: dict = _load(history_path, {})

    deals: list[dict] = []
    stores_status = {}
    for store_id, res in results.items():
        if res.get("deals") is None:
            # La tienda ha fallado hoy: mantenemos sus ofertas de ayer marcadas como antiguas.
            stale = [dict(d, stale=True) for d in previous.get("deals", []) if d.get("store") == store_id]
            deals.extend(stale)
            stores_status[store_id] = {"name": res["name"], "ok": False, "count": len(stale), "error": res.get("error")}
            continue
        for deal in res["deals"]:
            d = deal.to_dict() if isinstance(deal, Deal) else dict(deal)
            h = history.get(d["key"])
            if h is None:
                h = history[d["key"]] = {"first_seen": today_s, "min_price": d["price"]}
            # "Nuevo" = es la primera vez que lo vemos rebajado (o vuelve tras desaparecer)
            if h.get("last_seen") and h["last_seen"] < (today - timedelta(days=1)).isoformat():
                h["first_seen"] = today_s
            d["new"] = h["first_seen"] == today_s
            prev_min = h.get("min_price", d["price"])
            # "Ha bajado más": ya estaba rebajado y hoy está más barato que nunca.
            d["price_drop"] = (not d["new"]) and d["price"] < prev_min
            h["min_price"] = min(prev_min, d["price"])
            h["last_seen"] = today_s
            h["name"] = d["name"]
            d["first_seen"] = h["first_seen"]
            deals.append(d)
        stores_status[store_id] = {"name": res["name"], "ok": True, "count": len(res["deals"]), "error": None, "mode": res.get("mode")}

    cutoff = (today - timedelta(days=config.HISTORY_KEEP_DAYS)).isoformat()
    history = {k: v for k, v in history.items() if v.get("last_seen", today_s) >= cutoff}

    deals.sort(key=lambda d: (-d["discount"], d["price"]))
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stores": stores_status,
        "count": len(deals),
        "deals": deals,
    }
    deals_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    history_path.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    log.info("Escritas %d ofertas en %s", len(deals), deals_path)
    return payload
