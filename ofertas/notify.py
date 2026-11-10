"""Resumen diario por Telegram (opcional). Se activa si existen las variables
TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID."""

from __future__ import annotations

import html
import logging
import os

import requests

log = logging.getLogger(__name__)


def telegram_summary(payload: dict, page_url: str | None, top: int = 10) -> None:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    new = [d for d in payload["deals"] if d.get("new") and not d.get("stale")]
    if not new:
        log.info("Telegram: no hay ofertas nuevas hoy, no envío nada")
        return
    lines = [f"🛍 <b>{len(new)} ofertas nuevas hoy</b>"]
    for d in new[:top]:
        lines.append(
            f'• <a href="{html.escape(d["url"])}">{html.escape(d["name"])}</a> '
            f'({d["store_name"]}) <b>{d["price"]:.2f} €</b> <s>{d["old_price"]:.2f}</s> -{d["discount"]}%'
        )
    if page_url:
        lines.append(f'\n<a href="{html.escape(page_url)}">Ver todas</a>')
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": "\n".join(lines), "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=20,
    )
    if not r.ok:
        log.warning("Telegram respondió %s: %s", r.status_code, r.text[:200])
