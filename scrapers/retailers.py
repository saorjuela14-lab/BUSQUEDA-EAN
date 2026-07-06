"""
Definiciones concretas de scrapers por retailer.

Cada retailer hereda del motor adecuado (VTEX, Algolia, Bloomreach, Playwright)
y ajusta, cuando es necesario, las rutas de búsqueda o selectores propios del
sitio. Mantener cada retailer aislado facilita el mantenimiento ante cambios de
cada e-commerce.
"""
from __future__ import annotations

from .algolia import AlgoliaScraper
from .makro_tienda import MakroTiendaScraper
from .playwright_base import PlaywrightScraper
from .pricesmart import PriceSmartScraper
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


class OlimpicaScraper(VtexScraper):
    """Supertiendas Olímpica (VTEX)."""


# ── Retailers con buscador Algolia (API JSON) ──────────────────────────────
class AlkostoScraper(AlgoliaScraper):
    """Alkosto (buscador Algolia, claves públicas de cliente)."""

    app_id = "QX5IPS1B1Q"
    api_key = "7a8800d62203ee3a9ff1cdf74f99b268"
    index_name = "alkostoIndexAlgoliaPRD"


# ── Makro tienda online (Instaleap / Playwright) ───────────────────────────
class MakroScraper(MakroTiendaScraper):
    """Makro Colombia — tienda online tienda.makro.com.co."""


# ── PriceSmart (Bloomreach API) ────────────────────────────────────────────
# PriceSmartScraper definido en scrapers/pricesmart.py


# ── Retailers con render dinámico (Playwright) ─────────────────────────────


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
