import json
from datetime import date
from pathlib import Path

from ofertas import config, itx, zara
from ofertas.build import build
from ofertas.common import classify, is_men_root, men_leaf_categories, pick_categories

FIX = Path(__file__).parent / "fixtures"
load = lambda n: json.loads((FIX / f"{n}.json").read_text())
PULL = config.ITX_STORES[0]


class FakeHttp:
    """Devuelve fixtures según la URL pedida."""

    def __init__(self, routes):
        self.routes, self.calls = routes, 0

    def get_json(self, url, params=None):
        self.calls += 1
        for fragment, payload in self.routes.items():
            if fragment in url:
                return payload
        raise RuntimeError(f"sin ruta para {url}")


def test_men_root_detection():
    assert is_men_root({"name": "HOMBRE", "nameEn": "MAN"})
    assert is_men_root({"key": "BERSHKA_MAN"})
    assert not is_men_root({"name": "MUJER", "nameEn": "WOMAN"})
    assert not is_men_root({"name": "WOMAN", "key": "WOMEN."})
    assert not is_men_root({"name": "NEW IN"})


def test_men_leaves_skip_women_dividers_and_irrelevant():
    leaves = men_leaf_categories(load("itx_tree"), 100)
    assert [c for c, _ in leaves] == ["211", "212", "221"]
    zleaves = men_leaf_categories(load("zara_tree"), 100)
    assert [c for c, _ in zleaves] == ["201", "202"]


def test_pick_sale_categories():
    leaves = men_leaf_categories(load("zara_tree"), 100)
    picked, mode = pick_categories(leaves, full=False)
    assert mode == "ofertas" and [c for c, _ in picked] == ["201"]
    picked, mode = pick_categories(leaves, full=True)
    assert mode == "completo" and len(picked) == 2
    mixed = [("1", ["HOMBRE", "Promociones"]), ("2", ["HOMBRE", "Jerséis"])]
    assert pick_categories(mixed, False) == ([mixed[0]], "ofertas")


def test_classify():
    assert classify("Cazadora bomber efecto ante", []) == "Abrigos y chaquetas"
    assert classify("Camiseta básica", []) == "Camisetas y polos"
    assert classify("Camisa oxford", []) == "Camisas"
    assert classify("Jeans baggy", []) == "Pantalones y vaqueros"
    assert classify("Mochila básica", []) == "Bolsos y accesorios"
    assert classify("Mocasín piel", []) == "Calzado"


def test_itx_scan():
    http = FakeHttp({
        "/productsArray": load("itx_products"),
        "/product": load("itx_category"),
        "/category": load("itx_tree"),
    })
    found, mode = itx.scan(PULL, http, 100)
    assert mode == "completo"  # el fixture no tiene categoría de ofertas en hombre
    deals = {d.product_id: d for d in found}
    assert set(deals) == {"1001", "1003"}  # el jersey no está rebajado
    bomber = deals["1001"]
    assert (bomber.price, bomber.old_price, bomber.discount) == (25.99, 39.99, 35)
    assert bomber.sizes == ["S", "M"]  # L no se puede comprar
    assert bomber.colors == ["Chocolate"]
    assert bomber.url == "https://www.pullandbear.com/es/cazadora-bomber-efecto-ante-l03710514?colorId=717"
    assert bomber.image.startswith("https://static.pullandbear.net/assets/public/")
    assert bomber.tipo == "Abrigos y chaquetas"
    # 1003: 19.99 vs 22.99 = 13 %, pasa el mínimo del 10 %
    assert deals["1003"].discount == 13
    assert deals["1003"].url.endswith("mochila-basica-c0p1003.html?colorId=2")


def test_zara_parse():
    deals = list(zara.parse_products(load("zara_products"), config.ZARA, ["HOMBRE", "SPECIAL PRICES"]))
    by_id = {d.product_id: d for d in deals}
    assert set(by_id) == {"555", "557"}
    blazer = by_id["555"]
    assert blazer.discount == 56 and blazer.price == 39.99
    assert blazer.url == "https://www.zara.com/es/es/blazer-regular-fit-traje-con-lana-p0123456.html?v1=555"
    assert blazer.image == "https://static.zara.net/assets/public/x/y/z.jpg?ts=1&w=500"
    assert blazer.sizes is None
    assert by_id["557"].image.startswith("https://static.zara.net/photos//2026/")


def test_build_history_and_stale(tmp_path):
    zdeals = list(zara.parse_products(load("zara_products"), config.ZARA, ["HOMBRE"]))
    day1 = build({"zara": {"name": "Zara", "deals": zdeals}}, tmp_path, date(2026, 11, 10))
    assert day1["count"] == 2 and all(d["new"] for d in day1["deals"])
    assert day1["deals"][0]["discount"] >= day1["deals"][1]["discount"]

    # Día 2: el blazer baja más; Bershka falla y no había datos previos
    zdeals[0].price = 29.99
    day2 = build({"zara": {"name": "Zara", "deals": zdeals},
                  "bershka": {"name": "Bershka", "deals": None, "error": "403"}}, tmp_path, date(2026, 11, 11))
    blazer = next(d for d in day2["deals"] if d["product_id"] == "555")
    assert not blazer["new"] and blazer["price_drop"]
    assert day2["stores"]["bershka"] == {"name": "Bershka", "ok": False, "count": 0, "error": "403"}

    # Día 3: Zara falla -> se conservan sus ofertas de ayer como "stale"
    day3 = build({"zara": {"name": "Zara", "deals": None, "error": "timeout"}}, tmp_path, date(2026, 11, 12))
    assert day3["count"] == 2 and all(d["stale"] for d in day3["deals"])


def test_browser_extractor_on_fixture():
    import pytest
    pytest.importorskip("playwright")
    from ofertas import browser

    b = browser.Browser()
    try:
        ctx = b.new_context()
        items = b.extract(ctx, (FIX / "listing.html").resolve().as_uri(), 1, "test")
        ctx.close()
    finally:
        b.close()
    by_name = {i["name"]: i for i in items}
    assert len(items) == 4, items
    hm = by_name["Americana Relaxed Fit"]
    assert (hm["price"], hm["old_price"]) == (71.99, 89.99)
    assert hm["url"].endswith("/es_es/productpage.111.html") and hm["image"] == "https://img.example/111.jpg"
    z = by_name["Levi's® 501 ORIGINAL - Vaqueros rectos"]
    assert (z["price"], z["old_price"]) == (59.95, 109.95)
    cos = next(i for i in items if "333" in i["url"])
    assert (cos["price"], cos["old_price"]) == (149, 250) and cos["name"] == "Abrigo de lana regular"
    assert cos["image"] == "https://img.example/333.jpg"
    leather = by_name["Chaqueta de piel"]
    assert (leather["price"], leather["old_price"]) == (899, 1299)

    deals = browser._to_deals({"id": "hm", "name": "H&M"}, items)
    assert {d.tipo for d in deals} >= {"Trajes y blazers", "Pantalones y vaqueros", "Abrigos y chaquetas"}


def test_browser_scan_fallback_and_pagination():
    import pytest
    pytest.importorskip("playwright")
    from ofertas import browser

    empty = (FIX / "empty.html").resolve().as_uri()
    listing = (FIX / "listing.html").resolve().as_uri()
    b = browser.Browser()
    try:
        # Rebajas vacías -> usa el catálogo y lo marca como "completo"
        store = {"id": "cos", "name": "COS", "sources": [[empty], [listing]], "scroll_rounds": 1}
        deals, mode = browser.scan(store, b, 10)
        assert mode == "completo" and len(deals) == 4
        # Paginado: la página 2 repite lo mismo -> para y no pide la 3
        store = {"id": "hm", "name": "H&M", "sources": [[listing + "?page={page}"]], "sale_only": True,
                 "max_pages": 5, "scroll_rounds": 1}
        before = b.pages_loaded
        deals, mode = browser.scan(store, b, 10)
        assert mode == "ofertas" and len(deals) == 4 and b.pages_loaded - before == 2
    finally:
        b.close()


def test_shopify_nude_project():
    from ofertas import shopify

    def prod(pid, title, tags, price, old, sizes=("S", "M")):
        return {"id": pid, "title": title, "handle": f"h{pid}", "product_type": "Hoodies", "tags": tags,
                "images": [{"src": f"https://cdn.shopify.com/{pid}.jpg"}],
                "variants": [{"price": price, "compare_at_price": old, "option1": s, "available": s != "M"} for s in sizes]}

    page1 = {"products": [
        prod(1, "Skyline Hoodie", ["man_product", "M_HOODIES"], "69.00", "119.00"),
        prod(2, "Gotham Polo", ["woman_product"], "29.00", "59.00"),
        prod(3, "Unisex Cap", [], "25.00", "35.00", sizes=("Default Title",)),
        prod(4, "Tribeca Pants", ["man_product"], "109.00", None),
        prod(5, "Mixed Knit", ["man_product", "woman_product"], "60.00", "120.00"),
    ]}

    class PagedHttp:
        def __init__(self): self.pages = []
        def get_json(self, url, params=None):
            self.pages.append(params["page"])
            return page1 if params["page"] == 1 else {"products": []}

    http = PagedHttp()
    store = config.SHOPIFY_STORES[0]
    deals, mode = shopify.scan(store, http, 10)
    by_id = {d.product_id: d for d in deals}
    assert http.pages == [1, 2]
    assert set(by_id) == {"1", "3", "5"}  # sin el de solo-mujer ni el no rebajado
    hoodie = by_id["1"]
    assert (hoodie.price, hoodie.old_price, hoodie.discount) == (69.0, 119.0, 42)
    assert hoodie.url == "https://nude-project.com/products/h1" and hoodie.sizes == ["S"]
    assert hoodie.tipo == "Jerséis y sudaderas"
    assert by_id["3"].sizes == []


def test_asos_parse_and_paging():
    from ofertas import asos

    def prod(pid, name, brand, cur, prev, rrp=None):
        return {"id": pid, "name": name, "brandName": brand, "colour": "NEGRO",
                "price": {"current": {"value": cur}, "previous": {"value": prev}, "rrp": {"value": rrp}},
                "url": f"nike/zapatillas/prd/{pid}", "imageUrl": f"images.asos-media.com/products/x/{pid}-1-black"}

    pages = {
        0: {"itemCount": 5, "products": [
            prod(1, "Zapatillas Air Max de Nike", "Nike Running", 89.99, 149.99),
            prod(2, "Camiseta básica de ASOS DESIGN", "ASOS DESIGN", 5.0, 12.0),     # marca no elegida
            prod(3, "Sudadera de HUGO", "HUGO", 99.0, None, 120.0),                  # -18 % < 30 %
        ]},
        3: {"itemCount": 5, "products": [
            prod(4, "Chaqueta de Carhartt WIP", "Carhartt WIP", 80.0, None, 160.0),  # rrp como precio anterior
            prod(5, "Pantalón de Levi's", "Levi's", 60.0, 60.0),                     # sin rebaja
        ]},
    }

    class Fake:
        def __init__(self): self.offsets = []
        def get_json(self, url, params=None):
            self.offsets.append(params["offset"])
            assert url.endswith("/categories/8409") and params["store"] == "ES"
            return pages[params["offset"]]

    http = Fake()
    deals, mode = asos.scan(config.ASOS, http, 10)
    by_id = {d.product_id: d for d in deals}
    assert http.offsets == [0, 0, 3]  # sonda + páginas; para al llegar a itemCount
    assert set(by_id) == {"1", "4"}
    nike = by_id["1"]
    assert (nike.price, nike.old_price, nike.discount) == (89.99, 149.99, 40)
    assert nike.url == "https://www.asos.com/es/nike/zapatillas/prd/1"
    assert nike.image == "https://images.asos-media.com/products/x/1-1-black"
    assert nike.tipo == "Calzado" and by_id["4"].discount == 50


def test_hybrid_http_falls_back_to_browser():
    import functools, http.server, threading
    import pytest
    pytest.importorskip("playwright")
    from ofertas import browser
    from ofertas.http import HybridHttp

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIX))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    b = browser.Browser()
    try:
        client = HybridHttp(base, "test", None, lambda: b)

        def blocked(url, params=None):
            raise RuntimeError(f"No se pudo obtener {url}: 403 Client Error: Forbidden")
        client.http.get_json = blocked

        data = client.get_json(base + "/itx_category.json", {"x": 1})
        assert data == {"productIds": [1001, 1002, 1003]}
        assert client.browser_http is not None  # pasó a navegador
        assert client.get_json(base + "/itx_tree.json")["categories"][1]["name"] == "HOMBRE"

        # Un error que no es de bloqueo (p. ej. 404 por URL mal) no cambia de modo
        client2 = HybridHttp(base, "t2", None, lambda: b)
        def notfound(url, params=None):
            raise RuntimeError(f"No se pudo obtener {url}: 404 Client Error")
        client2.http.get_json = notfound
        with pytest.raises(RuntimeError):
            client2.get_json(base + "/nada.json")
        assert client2.browser_http is None
        client.close()
    finally:
        b.close()
        srv.shutdown()
