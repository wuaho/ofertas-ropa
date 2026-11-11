# ofertas-ropa: estado del proyecto y cómo continuar

Última actualización: 2026-11-10 (sesión inicial). Este archivo es el punto de partida para retomar el proyecto.

## Qué es

Scraper diario de **ofertas de moda de hombre** (más unisex y accesorios, bolsos incluidos) que junta en una sola página web las rebajas de varias tiendas, ordenadas por descuento.

- Repo: https://github.com/wuaho/ofertas-ropa (público)
- Página: https://wuaho.github.io/ofertas-ropa/ (GitHub Pages, carpeta `/docs`, rama `main`)
- Copia local del usuario: `~/Personal/ofertas-ropa` (Mac Apple Silicon, Python 3.9 del sistema)

## Arquitectura

```
ofertas/
  __main__.py   CLI: --only/--skip, --debug, --full, --compare, --no-notify
  config.py     TODO lo configurable: tiendas, URLs, marcas, descuento mínimo, canales de navegador
  common.py     Deal (modelo), clasificación por tipo de prenda, detección sección hombre
  http.py       Http (requests) + HybridHttp (requests → si 403/429/timeout, fetch() desde navegador)
  zara.py       API ?ajax=true de Zara (categoría "Special Prices")
  itx.py        API itxrest de Inditex: Pull&Bear, Bershka, Massimo Dutti
  shopify.py    /products.json: Nude Project (filtra tags man_product/woman_product)
  asos.py       API de búsqueda de ASOS (cid 8409 rebajas hombre), filtro por marcas
  browser.py    Playwright: Browser, BrowserHttp, scan genérico por URLs
  extract.js    Extractor genérico: busca precios tachados o "Precio normal"/"Último precio más bajo"
  build.py      deals.json + history.json (NUEVA, BAJA MÁS, datos "de ayer" si una tienda falla)
  notify.py     Resumen por Telegram (opcional, secrets TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)
docs/index.html Página estática con filtros (tienda, tipo, descuento, precio, tallas)
probar-local.sh Prueba completa en local: venv, deps, Chromium, ejecuta con --debug y abre localhost:8000
.github/workflows/ofertas.yml  Cron diario 06:23 UTC + ejecución manual
```

Tiendas configuradas (12): Zara, Pull&Bear, Bershka, Massimo Dutti, Nude Project, ASOS, H&M, Uniqlo, COS, Arket, Mango Man, Zalando.
- Zalando: 23 marcas (Selected Homme, Levi's, Scalpers, Tommy, CK, Lacoste, Les Deux, Carhartt WIP, New Balance, adidas Originals, Camper, Dr. Martens, Nike Sportswear/Performance, Under Armour, Puma, Salomon, The North Face, Armani Exchange, BOSS, Guess, HUGO, Timberland), desde -30 %.
- ASOS: las mismas marcas por nombre (más "Hugo Boss"), desde -30 %.
- Resto: desde -10 % (`MIN_DISCOUNT_PCT`).

## Decisiones tomadas

- Solo hombre/unisex + accesorios. Mujer no.
- Zara: leer solo la categoría de ofertas es suficiente (comprobado: las rebajas de categorías normales también están en Special Prices). Modo `auto` por defecto; `--compare` para verificarlo en otras tiendas.
- Plan de despliegue: **scraper en un ordenador de casa (cron + git push) y la página en GitHub Pages**. GitHub Actions sirve como respaldo pero sus IPs están muy bloqueadas.
- Un dominio propio no cambia nada para los bloqueos (solo importa desde dónde se hacen las peticiones). Se puede usar para la URL de la página si se quiere.

## Estado (10-nov-2026)

**Primera ejecución en GitHub Actions**: 94 ofertas, solo Zara (70) y Mango (24). El resto: 403 inmediatos (Inditex itxrest, H&M, COS, Arket, Uniqlo, Zalando), ASOS 400 (parámetros) y Nude Project 0 (no tenía rebajas).

**Primera ejecución en el Mac del usuario (commit bae7bad)**: el mismo resultado, Zara 71 y Mango 24. Diagnóstico con el navegador integrado de Claude desde la misma conexión:
- H&M carga perfectamente (210 productos rebajados) y la API itxrest de Pull&Bear responde 200 desde un navegador real.
- => **No es la IP, es la huella del cliente**: la librería `requests` (huella TLS) y el Chromium "headless shell" de Playwright.

**Arreglo subido (commit ea3238e), SIN PROBAR TODAVÍA contra las webs reales**:
- `HybridHttp`: APIs con requests; si 403/429/timeout → `BrowserHttp` (abre la portada de la tienda y hace fetch() desde la página).
- Navegador: Google Chrome (`channel="chrome"`) → Chromium completo → headless shell. User-Agent real sin "Headless". Página con 403 → espera 6 s y recarga una vez.
- H&M: nueva URL `/hombre/last-chance/ver-todo.html`.
- Tests: 12 en verde (`pytest`).

## Estado (11-nov-2026)

**Funciona en el Mac del usuario** (commit ea3238e): 2.571 ofertas. Zara 74, Pull&Bear 17, Bershka 23, Massimo Dutti 98, ASOS 1105, H&M 26, Uniqlo 118, Mango 85, Zalando 1025. COS 0 y Arket 0 (ahora mismo no tienen rebajas de hombre), Nude Project 0 (sin rebajas). El arreglo antibots (navegador real + fetch desde la página) funcionó.

Arreglado después, con los comentarios del usuario sobre la página (commit siguiente):
- "Ver más" salía con número negativo y no se ocultaba: `.more {display:block}` ganaba a `[hidden]`.
- Fotos borrosas en Bershka y Massimo Dutti: se cogía la foto `-r` (originalName "r…"), que es una miniatura de tela de 23x23 px. Ahora se descartan "r…" y clazz 5 (muestra de color), se prefiere clazz 1 y se pide `&w=600` (las originales son de 2000x3000).
- H&M/Zalando: el nombre a veces era el alt descriptivo de la foto. Ahora se prefiere el título de la ficha, y se buscan imágenes en data-src/srcset/<picture>.
- Burbujas de marca: campo `brand` en ASOS (normalizado a la marca configurada) y Zalando (detectada en el texto de la ficha con `brand_labels`). Aparecen al seleccionar esas tiendas.
- Nuevo `actualizar.sh`: ejecuta y publica (commit + push de docs/). Es lo que debe ir en el cron.

## Siguientes pasos (en orden)

0. Que el usuario haga `git pull && ./actualizar.sh` para publicar con los arreglos y revise fotos, nombres y marcas en la web.


1. **Ejecutar el arreglo en el Mac**: en `~/Personal/ofertas-ropa` → `git pull && ./probar-local.sh`. Después Claude lee `resultado.log` y `debug/` desde la carpeta conectada.
2. Corregir lo que siga fallando, tienda a tienda (`./probar-local.sh --only <tienda>`). Puntos a vigilar:
   - Zalando: `Page.goto` timeout de 45 s con la URL de 23 marcas. Probar con menos marcas o en varias URLs.
   - Mango: 24 ofertas = 8 en "bermudas", 8 en "lino" y 8 en "bañadores". Sospechoso: puede que sean los mismos 8 productos de un carrusel repetido en cada categoría. Revisar las capturas de `debug/browser/mango_*`.
   - Nude Project dio 429 con requests (el híbrido debería resolverlo).
   - ASOS: comprobar si el cambio a limit=72 basta o hace falta el navegador.
3. Cuando funcione en local: montar el **cron en el ordenador viejo de casa** (falta saber el sistema operativo) con `./actualizar.sh`, y **quitar el `schedule` del workflow** de GitHub Actions para que no se pisen (dejar `workflow_dispatch`).
4. Opcionales: aviso por Telegram (secrets), dominio propio para la página, añadir Lefties (Inditex, misma API itxrest: solo faltan sus IDs de tienda) u otras marcas Shopify (copiar el bloque de `SHOPIFY_STORES`).

## Notas para Claude (limitaciones del entorno)

- El contenedor cloud de Claude **no llega a las tiendas** (allowlist de red): no se puede ejecutar el scraper ahí. WebFetch sí lee algunas páginas, lo que sirve para investigar.
- El `device_bash` (VM Linux en el Mac) tampoco llega a las tiendas (allowlist), pero sí lee la carpeta conectada `~/Personal/ofertas-ropa`: útil para leer `resultado.log` y `debug/`. No hacer `git pull` ahí (deja ficheros .lock): que lo haga el usuario.
- Con el control del ordenador, la Terminal está en nivel "click" (no se puede escribir), así que los comandos los ejecuta el usuario.
- El navegador integrado de Claude (en el Mac del usuario) sirve para comprobar si una web carga desde su conexión y probar endpoints con `fetch()`.
- GitHub: push desde el contenedor vía `add_repo` (wuaho/ofertas-ropa, acceso push). Estado de los workflows y logs con la API pública sin autenticar: `api.github.com/repos/wuaho/ofertas-ropa/actions/runs`. `gh` no está autenticado.
- Commits con autor `wuaho <wuaho@users.noreply.github.com>`.
