#!/usr/bin/env bash
# Prueba completa en tu ordenador (macOS o Linux):
#   1. crea un entorno virtual e instala dependencias + Chromium
#   2. ejecuta el scraper con --debug (sin Telegram)
#   3. abre la página en http://localhost:8000
# Uso:  ./probar-local.sh            (todas las tiendas)
#       ./probar-local.sh --only asos --only hm   (solo algunas)
set -euo pipefail
cd "$(dirname "$0")"

# Busca el Python más nuevo disponible (Homebrew, pyenv, sistema...). 3.9 vale,
# pero con 3.10+ se instala un Playwright más reciente.
PY=""
for v in 3.13 3.12 3.11 3.10; do
  for dir in "" /opt/homebrew/bin/ /usr/local/bin/ "$HOME/.homebrew/bin/" "$HOME/.pyenv/shims/"; do
    if command -v "${dir}python$v" >/dev/null 2>&1; then PY="$(command -v "${dir}python$v")"; break 2; fi
  done
done
if [ -z "$PY" ] && command -v uv >/dev/null 2>&1; then
  echo "==> No hay Python 3.10+; uv descargará uno"
  uv python install 3.12 >/dev/null && PY="$(uv python find 3.12)"
fi
if [ -z "$PY" ]; then
  PY="$(command -v python3 || command -v python)"
  echo "==> Usando $("$PY" --version) (funciona, pero si puedes: brew install python@3.12)"
fi
"$PY" -c 'import sys; assert sys.version_info >= (3, 9), "Hace falta Python 3.9 o superior"'
echo "==> Python: $PY ($("$PY" --version))"

if [ -d .venv ] && ! .venv/bin/python -c 'import sys' >/dev/null 2>&1; then rm -rf .venv; fi
if [ ! -d .venv ]; then
  echo "==> Creando entorno virtual"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "==> Instalando dependencias"
pip install -q --upgrade pip
pip install -q -r requirements.txt
python -m playwright install chromium

echo "==> Sacando ofertas (tarda unos minutos)"
python -m ofertas --no-notify --debug "$@" 2>&1 | tee resultado.log

echo
echo "==> Resumen por tienda"
python - <<'EOF'
import json
d = json.load(open("docs/deals.json"))
for s in d["stores"].values():
    estado = "OK " if s["ok"] else "MAL"
    print(f"  {estado} {s['name']:15} {s['count']:5} ofertas  {(s.get('error') or '')[:90]}")
print(f"  Total: {d['count']}")
EOF

echo
echo "==> Abriendo http://localhost:8000  (Ctrl+C para parar)"
( sleep 1; (command -v open >/dev/null && open http://localhost:8000) || (command -v xdg-open >/dev/null && xdg-open http://localhost:8000) || true ) &
cd docs && python -m http.server 8000
