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
    def __init__(self, referer: str, debug_dir: Path | None = None):
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self.session.headers["Referer"] = referer + "/"
        self.debug_dir = debug_dir
        self._last = 0.0
        self.calls = 0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < config.REQUEST_DELAY_S:
            time.sleep(config.REQUEST_DELAY_S - elapsed)
        self._last = time.monotonic()

    def get_json(self, url: str, params: dict | None = None) -> dict:
        last_err: Exception | None = None
        for attempt in range(1, config.MAX_RETRIES + 1):
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
                wait = 2 ** attempt
                log.warning("Fallo %s (intento %d): %s. Reintento en %ds", url, attempt, e, wait)
                time.sleep(wait)
        raise RuntimeError(f"No se pudo obtener {url}: {last_err}")

    def _dump(self, url: str, params: dict | None, data: dict) -> None:
        if not self.debug_dir:
            return
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^a-zA-Z0-9]+", "_", url.split("//", 1)[-1])[-120:]
        if params:
            name += "_" + re.sub(r"[^a-zA-Z0-9]+", "_", json.dumps(params, sort_keys=True))[:60]
        (self.debug_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False)[:2_000_000])
