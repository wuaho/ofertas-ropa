"""Cliente HTTP con ritmo pausado, reintentos y volcado opcional para depurar."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import requests

from . import config

log = logging.getLogger(__name__)


class Http:
    def __init__(self, referer: str, debug_dir: Path | None = None, retries: int | None = None):
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self.session.headers["Referer"] = referer + "/"
        self.debug_dir = debug_dir
        self.retries = retries or config.MAX_RETRIES
        self._last = 0.0
        self.calls = 0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < config.REQUEST_DELAY_S:
            time.sleep(config.REQUEST_DELAY_S - elapsed)
        self._last = time.monotonic()

    def get_json(self, url: str, params: dict | None = None) -> dict:
        last_err: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._wait()
            self.calls += 1
            try:
                r = self.session.get(url, params=params, timeout=config.TIMEOUT_S)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
                r.raise_for_status()
                data = r.json()
                self._dump(url, params, data)
                return data
            except (requests.RequestException, ValueError) as e:
                last_err = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in (401, 403, 404):
                    break  # reintentar no va a arreglarlo
                if attempt == self.retries:
                    break
                wait = 2 ** attempt
                log.warning("Fallo %s (intento %d): %s. Reintento en %ds", url, attempt, e, wait)
                time.sleep(wait)
        raise RuntimeError(f"No se pudo obtener {url}: {last_err}")

    def _dump(self, url: str, params: dict | None, data: dict) -> None:
        _dump_json(self.debug_dir, url, params, data)


BLOCK_HINTS = ("403", "429", "timed out", "Timeout", "Connection", "Max retries")


class HybridHttp:
    """Prueba con requests (rápido). Si el antibot lo bloquea (403/429/cuelgue),
    pasa a hacer las mismas peticiones desde un navegador real para esa tienda."""

    def __init__(self, base: str, store_id: str, debug_dir: Path | None, browser_factory):
        self.base, self.store_id, self.debug_dir = base, store_id, debug_dir
        self.http = Http(base, debug_dir, retries=1)
        self._browser_factory = browser_factory
        self.browser_http = None

    @property
    def calls(self) -> int:
        return self.http.calls + (self.browser_http.calls if self.browser_http else 0)

    def get_json(self, url: str, params: dict | None = None) -> dict:
        if self.browser_http is None:
            try:
                return self.http.get_json(url, params)
            except RuntimeError as e:
                if not any(h in str(e) for h in BLOCK_HINTS):
                    raise
                log.warning("[%s] bloqueado con requests (%s); paso a navegador", self.store_id, str(e)[-60:])
                from .browser import BrowserHttp

                self.browser_http = BrowserHttp(self._browser_factory(), self.base, self.store_id)
        data = self.browser_http.get_json(url, params)
        _dump_json(self.debug_dir, url, params, data)
        return data

    def close(self):
        if self.browser_http:
            self.browser_http.close()


def _dump_json(debug_dir: Path | None, url: str, params: dict | None, data: dict) -> None:
    """Con --debug, guarda cada respuesta JSON en debug/<tienda>/."""
    if not debug_dir:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^a-zA-Z0-9]+", "_", url.split("//", 1)[-1])[-120:]
    if params:
        name += "_" + re.sub(r"[^a-zA-Z0-9]+", "_", json.dumps(params, sort_keys=True))[:60]
    (debug_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False)[:2_000_000])
