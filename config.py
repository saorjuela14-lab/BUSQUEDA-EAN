"""
Configuración central de la plataforma Retail Price Intelligence Colombia.

Carga variables desde el entorno (.env) y expone constantes del dominio:
retailers, categorías y parámetros de negocio para compradores de Makro Colombia.

Todo el módulo está documentado para facilitar mantenimiento y escalabilidad.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Cargar variables de entorno desde .env (si existe) lo más temprano posible.
load_dotenv()

# ──────────────────────────────────────────────────────────────────────────
# RUTAS DEL PROYECTO
# ──────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

# Crear carpetas de trabajo si no existen (idempotente).
for _d in (DATA_DIR, UPLOADS_DIR, REPORTS_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class Config:
    """Configuración de la aplicación basada en variables de entorno."""

    # Flask
    SECRET_KEY: str = os.getenv("SECRET_KEY", "makro-retail-intelligence-dev-key")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "5000"))

    # Base de datos
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'retail_intelligence.db').as_posix()}"
    )

    # Scraping (siempre real: VTEX por requests + Playwright para el resto).
    SCRAPER_TIMEOUT: int = int(os.getenv("SCRAPER_TIMEOUT", "20"))  # segundos
    SCRAPER_MAX_WORKERS: int = int(os.getenv("SCRAPER_MAX_WORKERS", "8"))
    SCRAPER_HEADLESS: bool = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true"
    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    )

    # Negocio
    # Homologación por descripción: umbral mínimo de similitud (0-100).
    MATCH_THRESHOLD: int = int(os.getenv("MATCH_THRESHOLD", "80"))
    # Múltiplo de redondeo comercial colombiano para precios sugeridos.
    ROUNDING_MULTIPLE: int = int(os.getenv("ROUNDING_MULTIPLE", "50"))
    # Variación de precio que dispara alerta (fracción, 0.10 = 10%).
    ALERT_VARIATION_THRESHOLD: float = float(os.getenv("ALERT_VARIATION_THRESHOLD", "0.10"))
    # Margen objetivo por defecto para el escenario 4 (fracción).
    DEFAULT_TARGET_MARGIN: float = float(os.getenv("DEFAULT_TARGET_MARGIN", "0.15"))


# ──────────────────────────────────────────────────────────────────────────
# CATEGORÍAS DEL NEGOCIO
# clave interna -> (etiqueta visible, emoji, color hex)
# ──────────────────────────────────────────────────────────────────────────
CATEGORIES: dict[str, dict[str, str]] = {
    "dairy": {"label": "Dairy", "emoji": "🥛", "color": "#4f7fff"},
    "bakery": {"label": "Bakery", "emoji": "🍞", "color": "#d98c3f"},
    "fresh_bakery": {"label": "Fresh Bakery", "emoji": "🥐", "color": "#e0b35c"},
    "cold_meat": {"label": "Cold Meat", "emoji": "🥓", "color": "#f05252"},
    "frozen": {"label": "Frozen", "emoji": "🧊", "color": "#38bdf8"},
    "seafood": {"label": "Seafood", "emoji": "🦐", "color": "#22c88a"},
}

# Subcategorías de referencia (homologación / clasificación).
SUBCATEGORIES: dict[str, list[str]] = {
    "dairy": [
        "Leche", "Yogurt", "Kumis", "Bebidas lácteas", "Crema de leche", "Mantequilla",
        "Quesos frescos", "Quesos maduros", "Quesos procesados",
    ],
    "bakery": ["Pan tajado", "Pan artesanal", "Pan industrial", "Tostadas", "Galletas panadería"],
    "fresh_bakery": ["Pan fresco", "Croissants", "Hojaldres", "Tortas", "Recién horneados"],
    "cold_meat": ["Jamones", "Mortadelas", "Salchichas", "Chorizos", "Tocineta"],
    "frozen": ["Pollo congelado", "Vegetales congelados", "Papas congeladas", "Helados", "Comidas preparadas"],
    "seafood": ["Camarones", "Pescados", "Atún", "Salmón", "Mariscos congelados"],
}

# ──────────────────────────────────────────────────────────────────────────
# RETAILERS
# clave interna -> metadatos (nombre, prioridad, color, dominio, tecnología)
# tech:   "vtex" (API JSON pública) | "html" (Playwright/BeautifulSoup)
# scrape: si False, no se consulta (referencia propia o sin canal scrapeable)
# Notas de campo (validadas contra los sitios reales en jun-2026):
#   - Jumbo Colombia (Cencosud) publica su catálogo VTEX en jumbocolombia.com.
#   - Metro comparte el MISMO canal online (jumbocolombia.com); se desactiva su
#     scraping para no duplicar precios y mantener la precisión del promedio.
#   - Makro es la referencia propia: su tienda exige "Pasaporte Makro" (login),
#     no expone API pública y el costo lo aporta el comprador → no se scrapea.
#   - Alkosto usa buscador Algolia (API JSON, claves públicas de cliente).
#   - PriceSmart es club de membresía: su API Bloomreach devuelve precio 0 a
#     invitados (precios requieren login) → no se scrapea.
#   - Farmatodo no usa VTEX (sitio propio) → se trata como HTML (Playwright).
# ──────────────────────────────────────────────────────────────────────────
RETAILERS: dict[str, dict] = {
    "exito": {"name": "Éxito", "priority": 1, "color": "#ffe600", "base_url": "https://www.exito.com", "tech": "vtex", "scrape": True},
    "carulla": {"name": "Carulla", "priority": 1, "color": "#8bc63f", "base_url": "https://www.carulla.com", "tech": "vtex", "scrape": True},
    "jumbo": {"name": "Jumbo", "priority": 1, "color": "#2db84d", "base_url": "https://www.jumbocolombia.com", "tech": "vtex", "scrape": True},
    "metro": {"name": "Metro", "priority": 1, "color": "#e2231a", "base_url": "https://www.jumbocolombia.com", "tech": "vtex", "scrape": False},
    "makro": {"name": "Makro", "priority": 1, "color": "#e2001a", "base_url": "https://www.makro.com.co", "tech": "vtex", "scrape": False},
    "alkosto": {"name": "Alkosto", "priority": 1, "color": "#e30613", "base_url": "https://www.alkosto.com", "tech": "algolia", "scrape": True},
    "olimpica": {"name": "Olímpica", "priority": 1, "color": "#ed1c24", "base_url": "https://www.olimpica.com", "tech": "vtex", "scrape": True},
    "pricesmart": {"name": "PriceSmart", "priority": 1, "color": "#004b8d", "base_url": "https://www.pricesmart.com", "tech": "bloomreach", "scrape": False},
    # Prioridad 2
    "d1": {"name": "D1", "priority": 2, "color": "#e30613", "base_url": "https://domicilios.tiendasd1.com", "tech": "html", "scrape": True},
    "ara": {"name": "Ara", "priority": 2, "color": "#00a94f", "base_url": "https://aratiendas.com", "tech": "html", "scrape": True},
    "isimo": {"name": "Ísimo", "priority": 2, "color": "#ff6600", "base_url": "https://www.isimo.com.co", "tech": "html", "scrape": True},
    "farmatodo": {"name": "Farmatodo", "priority": 2, "color": "#005baa", "base_url": "https://www.farmatodo.com.co", "tech": "html", "scrape": True},
}

# Retailer de referencia para estrategias de precio (nuestra empresa).
HOME_RETAILER = "makro"


def scrapable_retailers(priority: int | None = None) -> dict[str, dict]:
    """Retailers que SÍ se consultan (scrape=True), opcional por prioridad."""
    items = {k: v for k, v in RETAILERS.items() if v.get("scrape", True)}
    if priority is not None:
        items = {k: v for k, v in items.items() if v["priority"] == priority}
    return items


def retailers_by_priority(priority: int | None = None) -> dict[str, dict]:
    """Devuelve los retailers, opcionalmente filtrados por prioridad (1 o 2)."""
    if priority is None:
        return dict(RETAILERS)
    return {k: v for k, v in RETAILERS.items() if v["priority"] == priority}
