"""
Definiciones concretas de scrapers por retailer.

Cada retailer hereda del motor adecuado (VTEX o Playwright) y ajusta, cuando es
necesario, las rutas de búsqueda o selectores propios del sitio. Mantener cada
retailer aislado facilita el mantenimiento ante cambios de cada e-commerce.
"""
from __future__ import annotations

from .algolia import AlgoliaScraper
from .playwright_base import PlaywrightScraper
from .vtex import VtexScraper


# ── Retailers VTEX (API JSON; rápidos y estables) ──────────────────────────
class ExitoScraper(VtexScraper):
    """Almacenes Éxito (VTEX)."""


class CarullaScraper(VtexScraper):
    """Carulla (VTEX)."""


class JumboScraper(VtexScraper):
    """Tiendas Jumbo - Cencosud (VTEX)."""


class MetroScraper(VtexScraper):
    """Tiendas Metro - Cencosud (VTEX)."""


class MakroScraper(VtexScraper):
    """Makro Colombia (VTEX) — retailer de referencia."""


class OlimpicaScraper(VtexScraper):
    """Supertiendas Olímpica (VTEX)."""


# ── Retailers con buscador Algolia (API JSON) ──────────────────────────────
class AlkostoScraper(AlgoliaScraper):
    """Alkosto (buscador Algolia, claves públicas de cliente)."""

    app_id = "QX5IPS1B1Q"
    api_key = "7a8800d62203ee3a9ff1cdf74f99b268"
    index_name = "alkostoIndexAlgoliaPRD"


# ── Retailers con render dinámico (Playwright) ─────────────────────────────


class PriceSmartScraper(PlaywrightScraper):
    """
    PriceSmart (club de membresía).

    Nota: su buscador (Bloomreach) devuelve precio 0 a invitados; los precios
    requieren inicio de sesión de socio. Por eso está desactivado (scrape=False
    en config). Esta clase queda como base si se dispone de credenciales de socio.
    """

    search_path = "/es-co/busqueda?q={query}"
    card_selector = "[class*='ProductCard'], .product-card, article"
    name_selector = "[class*='title'], h3, h2"
    price_selector = "[class*='price'], .price"


class D1Scraper(PlaywrightScraper):
    """Tiendas D1."""

    search_path = "/search?q={query}"


class AraScraper(PlaywrightScraper):
    """Tiendas Ara."""

    search_path = "/buscar?q={query}"


class IsimoScraper(PlaywrightScraper):
    """Ísimo."""

    search_path = "/search?q={query}"


class FarmatodoScraper(PlaywrightScraper):
    """Farmatodo (sitio propio, no VTEX)."""

    search_path = "/search?product={query}"


# Mapa clave de retailer -> clase de scraper.
SCRAPER_CLASSES: dict[str, type] = {
    "exito": ExitoScraper,
    "carulla": CarullaScraper,
    "jumbo": JumboScraper,
    "metro": MetroScraper,
    "makro": MakroScraper,
    "olimpica": OlimpicaScraper,
    "farmatodo": FarmatodoScraper,
    "alkosto": AlkostoScraper,
    "pricesmart": PriceSmartScraper,
    "d1": D1Scraper,
    "ara": AraScraper,
    "isimo": IsimoScraper,
}
