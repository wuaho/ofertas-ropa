# Ofertas de moda (hombre)

Cada mañana, un script revisa las rebajas de hombre (accesorios incluidos) de **Zara, Pull&Bear, Bershka, Massimo Dutti, H&M, COS, Arket, Mango Man, Uniqlo, Nude Project, ASOS y Zalando**, y publica una página con todo junto, ordenado por descuento.

- `NUEVA`: es la primera vez que aparece rebajada.
- `BAJA MÁS`: ya estaba rebajada y hoy está más barata que nunca.
- `de ayer`: esa tienda falló hoy y se muestran sus datos de ayer.
- Filtros por tienda, tipo de prenda, descuento mínimo, precio máximo y tus tallas (se guardan en el navegador).

## Puesta en marcha (unos 5 minutos)

1. Crea un repo en GitHub y sube este proyecto.
   - **Público**: GitHub Pages es gratis.
   - **Privado**: Pages solo funciona con GitHub Pro. Si no lo tienes, ver "Sin Pages" abajo.
2. **Settings → Pages → Build and deployment**: *Deploy from a branch*, rama `main`, carpeta `/docs`.
3. **Settings → Actions → General → Workflow permissions**: *Read and write permissions*.
4. **Actions → Ofertas diarias → Run workflow**. La primera vez, prueba tienda a tienda con `--debug`:
   - `--only zara --debug`
   - `--only hm --only cos --debug`
5. Abre `https://<tu-usuario>.github.io/<repo>/` y guárdala en la pantalla de inicio del móvil.

Se ejecuta solo cada día a las 07:23 (hora de Madrid). Para cambiar la hora, edita el `cron` en `.github/workflows/ofertas.yml` (está en UTC).

### Aviso por Telegram (opcional)

1. Habla con [@BotFather](https://t.me/BotFather), crea un bot y copia el token.
2. Escríbele cualquier cosa a tu bot y abre `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver tu `chat.id`.
3. En el repo: **Settings → Secrets and variables → Actions**, crea `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.

Te llegará un mensaje con las 10 mejores ofertas nuevas del día (solo si hay alguna).

## En local

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m ofertas --only zara --debug        # una tienda
python -m ofertas --skip zalando             # todas menos una
python -m ofertas                            # todo
python -m ofertas --compare --only zara      # ¿se pierde algo leyendo solo la sección de ofertas?
cd docs && python -m http.server 8000        # abre http://localhost:8000
pytest                                       # tests
```

Con `--debug`, en `debug/` se guardan las respuestas de las APIs y, para las tiendas con navegador, el HTML y una captura de cada página. En Actions se descargan como artefacto `debug`.

## Cómo funciona

Hay cuatro tipos de tienda:

**Con API** (Inditex): Zara, Pull&Bear, Bershka y Massimo Dutti. Se leen sus APIs internas en JSON. Primero busca la categoría de ofertas de hombre (Special Prices, Promociones, Rebajas…) y solo lee esa. Si no la hay, recorre todas las categorías de hombre. Trae tallas (menos Zara).

**Shopify**: Nude Project. Se lee `/products.json`, que es público y trae el precio anterior (`compare_at_price`), las tallas disponibles y etiquetas de hombre o mujer. Para añadir otra marca que use Shopify basta con copiar el bloque de `SHOPIFY_STORES` en `config.py` (si `https://marca.com/products.json` devuelve JSON, es Shopify).

**ASOS**: su API de búsqueda (`/api/product/search/v2/categories/8409`, rebajas de hombre), 200 productos por petición. Son miles de artículos, así que se filtra por marca (`ASOS` → `brands` en `config.py`, nombres tal cual salen en ASOS) y desde -30 %. ASOS bloquea a menudo las IPs de servidores: si en Actions da 403, ejecútalo desde casa.

**Con navegador** (Playwright + Chromium): H&M, COS, Arket, Mango, Uniqlo y Zalando. Abre cada listado, acepta las cookies, hace scroll o pasa de página, y aplica `ofertas/extract.js`. Ese extractor es genérico: busca precios tachados o con etiqueta ("Precio normal", "Último precio más bajo"…), sube hasta la ficha del producto y saca nombre, precio, enlace y foto. No depende de clases CSS concretas, así que aguanta rediseños.

Cada tienda con navegador tiene en `config.py` una lista de `sources` en orden de preferencia. Se usa la primera que dé ofertas:

| Tienda | 1º intenta | Si no hay rebajas |
|---|---|---|
| H&M | `/hombre/rebajas/ver-todo` y `/hombre/last-chance` | (nada) |
| Uniqlo | `/feature/sale/men` | (nada) |
| COS | `/men/sale` | `/men/view-all` filtrando lo tachado |
| Arket | `/men/sale/` | `/men/clothing/` filtrando lo tachado |
| Mango | `/c/hombre/rebajas` | categorías enlazadas desde la portada de hombre |
| Zalando | `/hombre-rebajas/` (ropa, zapatos y complementos), solo marcas elegidas, desde -30 % | (nada) |

### Zalando: elegir marcas

En `config.py`, `BROWSER_STORES` → `zalando` → `brands`. Los nombres son los de la URL de Zalando: si la marca está en `zalando.es/selected-homme/`, el slug es `selected-homme`. `min_discount` controla el descuento mínimo. Nike está dividida en dos marcas en Zalando: `nike-sportswear` (calle) y `nike-performance` (deporte).

## Antibots

Casi todas estas webs usan antibots (Akamai y similares) que no miran tanto la IP como la *huella* del cliente:

- **APIs**: si `requests` recibe 403, 429 o se queda colgado, esa tienda pasa automáticamente a hacer las mismas peticiones con `fetch()` desde dentro de su propia web, abierta en un navegador real (con las cookies del antibot). Lo verás en el log como "paso a navegador".
- **Navegador**: se usa tu Google Chrome instalado (`BROWSER_CHANNELS` en `config.py`), con su User-Agent real. Si una página responde 403, se espera unos segundos y se recarga una vez (muchos antibots resuelven un reto JS y dejan pasar).
- `OFERTAS_HEADED=1 ./probar-local.sh` abre las ventanas visibles, por si quieres ver qué pasa.

## Problemas conocidos

- **Antibots**: Zara, Mango, Zalando y Uniqlo tienen protección. Si una tienda falla siempre en Actions (HTTP 403 o 0 productos, y la captura de `--debug` muestra un captcha), ejecútalo desde tu ordenador con `cron`/`launchd` y `git push`, o con un *self-hosted runner*. Desde una IP de casa casi nunca bloquean.
- **URLs que cambian**: las secciones de rebajas cambian de URL entre temporadas. Si una tienda devuelve 0, mira la captura de `--debug` y actualiza `sources` en `config.py`.
- **Tallas**: solo en Pull&Bear, Bershka, Massimo Dutti y Nude Project. En las demás el filtro de tallas no oculta nada.
- **Tipos de prenda**: en las tiendas con navegador se deducen del nombre, así que alguna puede caer en "Otros".
- Son APIs y webs no documentadas: pueden cambiar sin aviso. Úsalo con moderación y para uso personal.

## Sin Pages (repo privado)

Quita el paso de Pages y quédate con el resumen de Telegram (ya incluido), o sube `docs/` como artefacto. También puedes abrir la página en local.
