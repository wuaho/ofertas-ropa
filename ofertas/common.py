"""Modelo de oferta y utilidades compartidas entre tiendas."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Iterable, Iterator

MEN_TOKENS = {"HOMBRE", "MAN", "MEN", "HOMME"}
WOMEN_MARKERS = ("WOM", "MUJER", "FEMME", "GIRL")


@dataclass
class Deal:
    store: str
    store_name: str
    product_id: str
    name: str
    price: float
    old_price: float
    discount: int
    url: str
    image: str | None = None
    category: str = ""
    tipo: str = "Otros"
    sizes: list[str] | None = None  # None = la tienda no da tallas en el listado
    colors: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.store}:{self.product_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["key"] = self.key
        return d


def cents(value) -> int | None:
    """Precios de Inditex: enteros o strings en céntimos ("2599")."""
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def discount_pct(price_c: int, old_c: int) -> int:
    return round((1 - price_c / old_c) * 100)


def is_men_root(cat: dict) -> bool:
    fields = [cat.get(k) for k in ("name", "nameEn", "key", "sectionName")]
    texts = [str(f).upper() for f in fields if f]
    if any(m in t for t in texts for m in WOMEN_MARKERS):
        return False
    return any(set(re.split(r"[^A-Z]+", t)) & MEN_TOKENS for t in texts)


def iter_leaves(cat: dict, path: list[str] | None = None) -> Iterator[tuple[dict, list[str]]]:
    path = (path or []) + [str(cat.get("name") or "").strip()]
    subs = [s for s in (cat.get("subcategories") or []) if isinstance(s, dict)]
    if not subs:
        yield cat, path
        return
    for s in subs:
        yield from iter_leaves(s, path)


def men_leaf_categories(tree: dict, limit: int) -> list[tuple[str, list[str]]]:
    """Devuelve (id, ruta) de todas las categorías hoja bajo las secciones de hombre."""
    out: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for root in tree.get("categories") or []:
        if not is_men_root(root):
            continue
        for leaf, path in iter_leaves(root):
            if leaf.get("irrelevant"):
                continue
            name = str(leaf.get("name") or "").strip()
            if not name or set(name) <= {"-", " ", "_"}:
                continue  # separadores de menú
            cid = str(leaf.get("redirectCategoryId") or leaf.get("id") or "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            out.append((cid, path))
    return out[:limit]


SALE_PATTERN = re.compile(
    r"ofertas|special\s*prices|precios\s*especiales|promoci|rebajas|\bsale\b|outlet|hasta\s*-?\d+\s*%|-\d+\s*%",
    re.IGNORECASE,
)


def is_sale_path(path: Iterable[str]) -> bool:
    return any(SALE_PATTERN.search(p or "") for p in path)


def pick_categories(leaves: list[tuple[str, list[str]]], full: bool) -> tuple[list[tuple[str, list[str]]], str]:
    """Si hay categorías de ofertas en hombre, solo esas. Si no (o con full=True), todas."""
    if not full:
        sale = [leaf for leaf in leaves if is_sale_path(leaf[1])]
        if sale:
            return sale, "ofertas"
    return leaves, "completo"


TIPOS = [
    ("Calzado", r"zapat|\bbota|sneaker|mocas|sandalia|nautic|calzado|shoe"),
    ("Bolsos y accesorios", r"bols|mochila|cartera|cinturon|gorr|sombrer|gafas|bufanda|guante|calcet|joy|collar|pulsera|anillo|accesor|perfum|fragan|neceser|tirante|corbata|belt"),
    ("Trajes y blazers", r"traje|blazer|americana|chaleco|suit"),
    ("Abrigos y chaquetas", r"abrigo|chaqueta|cazadora|parka|plumi|gabardina|bomber|sobrecamisa|cortavient|jacket|coat|overshirt"),
    ("Jerséis y sudaderas", r"jersey|jers|punto|cardigan|sudadera|hoodie|knit|sweat"),
    ("Camisetas y polos", r"camiseta|\bpolo|t-shirt|\btee\b"),
    ("Camisas", r"camisa|shirt"),
    ("Pantalones y vaqueros", r"pantal|jean|vaquer|chino|jogger|cargo|bermuda|short|trouser"),
]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def classify(name: str, path: Iterable[str]) -> str:
    # Primero el nombre de la prenda (más fiable), luego la categoría.
    for text in (_norm(name), _norm(" ".join(path))):
        for tipo, pattern in TIPOS:
            if re.search(pattern, text):
                return tipo
    return "Otros"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _norm(text)).strip("-")


def find_media_urls(obj, prefix: str = "http") -> Iterator[str]:
    """Busca en profundidad URLs de imágenes de static.*.net."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and k == "url" and v.startswith(prefix) and "/assets/public/" in v:
                yield v
            else:
                yield from find_media_urls(v, prefix)
    elif isinstance(obj, list):
        for v in obj:
            yield from find_media_urls(v, prefix)
