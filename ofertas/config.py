"""Configuración del scraper. Todo lo que quieras tocar está aquí."""

COUNTRY = "es"
LANG = "es"
LANGUAGE_ID = -5  # español en las APIs itxrest de Inditex

# Educación con los servidores: 1 petición por segundo y por tienda.
REQUEST_DELAY_S = 1.0
TIMEOUT_S = 25
MAX_RETRIES = 3

# "auto": solo la categoría de ofertas de hombre si existe; si no, todas.
# "full": siempre todas las categorías (más lento, pilla rebajas sueltas fuera de ofertas).
SCAN_MODE = "auto"

# Límite de seguridad de categorías a recorrer por tienda.
MAX_CATEGORIES_PER_STORE = 250
# Tamaño de lote al pedir el detalle de productos (itxrest).
PRODUCTS_BATCH = 40

# Solo se guardan prendas con al menos este % de descuento.
MIN_DISCOUNT_PCT = 10

# Días que se conserva en el historial un producto que ya no está rebajado.
HISTORY_KEEP_DAYS = 90

# Tiendas que usan la API itxrest. Los IDs son los de la tienda de España.
ITX_STORES = [
    {
        "id": "pullandbear",
        "name": "Pull&Bear",
        "base": "https://www.pullandbear.com",
        "store_id": 24009400,
        "catalog_id": 20309411,
        "url_suffix": "",
    },
    {
        "id": "bershka",
        "name": "Bershka",
        "base": "https://www.bershka.com",
        "store_id": 44009500,
        "catalog_id": 40259530,
        "url_suffix": ".html",
    },
    {
        "id": "massimodutti",
        "name": "Massimo Dutti",
        "base": "https://www.massimodutti.com",
        "store_id": 34009456,
        "catalog_id": 30359503,
        "url_suffix": "",
    },
]

ZARA = {
    "id": "zara",
    "name": "Zara",
    "base": "https://www.zara.com",
    "path": f"/{COUNTRY}/{LANG}",
}

# Navegador para Playwright, en orden de preferencia. "chrome" = tu Google Chrome
# instalado (lo más parecido a un visitante normal); "chromium" = Chromium completo
# en modo headless nuevo; None = el "headless shell" por defecto (lo que más
# detectan los antibots, solo como último recurso).
BROWSER_CHANNELS = ["chrome", "chromium", None]

# Tiendas que se leen con navegador (Playwright). Cada tienda tiene "sources":
# grupos de URLs en orden de preferencia. Se usa el PRIMER grupo que devuelva
# ofertas: primero la sección de rebajas y, si no existe o está vacía, el catálogo.
# {page} se sustituye por 1..max_pages (para cuando nada nuevo aparece).
BROWSER_STORES = [
    {
        "id": "hm",
        "name": "H&M",
        "sources": [
            ["https://www2.hm.com/es_es/hombre/rebajas/ver-todo.html?page={page}",
             "https://www2.hm.com/es_es/hombre/last-chance/ver-todo.html?page={page}"],
        ],
        "sale_only": True,
        "max_pages": 10,
        "scroll_rounds": 6,
    },
    {
        "id": "uniqlo",
        "name": "Uniqlo",
        "sources": [["https://www.uniqlo.com/es/es/feature/sale/men"]],
        "sale_only": True,
        "scroll_rounds": 25,
    },
    {
        "id": "cos",
        "name": "COS",
        "sources": [
            ["https://www.cos.com/es-es/men/sale"],
            ["https://www.cos.com/es-es/men/view-all"],
        ],
        "scroll_rounds": 30,
    },
    {
        "id": "arket",
        "name": "Arket",
        "sources": [
            ["https://www.arket.com/es-es/men/sale/"],
            ["https://www.arket.com/es-es/men/clothing/"],
        ],
        "scroll_rounds": 30,
    },
    {
        "id": "mango",
        "name": "Mango Man",
        "sources": [["https://shop.mango.com/es/es/c/hombre/rebajas"]],
        # Si no hay rebajas, recorre las categorías enlazadas desde la portada de hombre.
        "discover": {
            "start": "https://shop.mango.com/es/es/h/hombre",
            "pattern": r"/es/es/c/hombre/[a-z0-9-]+/[0-9a-f]{8}$",
            "limit": 25,
        },
        "scroll_rounds": 20,
    },
    {
        "id": "zalando",
        "name": "Zalando",
        # Zalando es enorme: solo estas marcas y desde -30 %. Los slugs son los de
        # la URL de Zalando (p. ej. zalando.es/levi-s/). Cambia la lista a tu gusto.
        "brands": [
            "selected-homme", "levi-s", "scalpers", "tommy-hilfiger", "calvin-klein", "lacoste",
            "les-deux", "carhartt-wip", "new-balance", "adidas-originals", "camper", "dr-martens",
            "nike-sportswear", "nike-performance", "under-armour", "puma", "salomon", "the-north-face",
            "armani-exchange", "boss", "guess", "hugo", "timberland",
        ],
        "min_discount": 30,
        # hombre-rebajas = ropa + zapatos + complementos de hombre en rebajas
        "sources": [["https://www.zalando.es/hombre-rebajas/{brands}/?p={page}"]],
        "sale_only": True,
        "max_pages": 25,  # con Nike/adidas/Puma hay muchas páginas; para cuando no aparece nada nuevo
        "scroll_rounds": 6,
    },
]

# Tiendas Shopify: se lee /products.json (público). Para añadir otra marca en
# Shopify basta con copiar el bloque y cambiar id, name y base.
SHOPIFY_STORES = [
    {
        "id": "nudeproject",
        "name": "Nude Project",
        "base": "https://nude-project.com",
        # Nude Project marca sus productos con man_product / woman_product.
        # Se descarta lo que solo es de mujer; lo que no lleva etiqueta se queda.
        "exclude_tags": ["woman_product"],
        "include_tags": ["man_product"],
    },
]

# ASOS: rebajas de hombre (cid 8409), filtradas por marca (nombre tal cual sale en
# ASOS, sin distinguir mayúsculas; "Nike" incluye "Nike Running", etc.).
# Lista vacía = todas las marcas (son miles de artículos). Añade "ASOS DESIGN"
# si quieres también su marca propia.
ASOS = {
    "id": "asos",
    "name": "ASOS",
    "base": "https://www.asos.com",
    "category_id": 8409,
    "min_discount": 30,
    "brands": [
        "Selected Homme", "Levi's", "Tommy Hilfiger", "Calvin Klein", "Lacoste", "Les Deux",
        "Carhartt WIP", "New Balance", "adidas Originals", "Camper", "Dr Martens", "Nike",
        "Under Armour", "Puma", "Salomon", "The North Face", "Armani Exchange", "BOSS",
        "Guess", "HUGO", "Hugo Boss", "Timberland",
    ],
}

# Cabeceras de navegador normal. Sin ellas, algunas webs devuelven 403.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}
