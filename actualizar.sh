#!/usr/bin/env bash
# Saca las ofertas y las PUBLICA en GitHub Pages (commit + push de docs/).
# Es lo que ejecuta el cron diario. Requiere haber pasado antes ./probar-local.sh
# (crea el entorno .venv con las dependencias).
#   ./actualizar.sh                  todas las tiendas
#   ./actualizar.sh --only zara      solo algunas (el resto conserva lo de la última vez)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "Falta el entorno: ejecuta primero ./probar-local.sh" >&2
  exit 1
fi

git pull --rebase --autostash -q origin main
.venv/bin/python -m ofertas "$@" 2>&1 | tee actualizar.log

git add docs/deals.json docs/history.json
if git diff --cached --quiet; then
  echo "==> Sin cambios en las ofertas"
else
  git commit -q -m "Ofertas $(date +%F)"
  git push -q origin main
  echo "==> Publicado: https://wuaho.github.io/ofertas-ropa/ (tarda ~1 min en refrescarse)"
fi
