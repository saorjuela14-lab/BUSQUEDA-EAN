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
    # Umbral reducido para Fruver: nombres cortos y genéricos ("AGUACATE KG")
    # vs. nombres comerciales con variedad/marca ("Aguacate Hass x Kg") bajan
    # el score de similitud aunque sea el mismo producto. Ver services/matching.py.
    MATCH_THRESHOLD_FRUVER: int = int(os.getenv("MATCH_THRESHOLD_FRUVER", "68"))
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
    "fruver": {"label": "Fruver", "emoji": "🥬", "color": "#5cb85c"},
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
    "fruver": [
        "Verduras - Granel", "Verduras - Empaque", "Frutas - Granel", "Frutas - Empaque",
        "Tubérculos", "Hierbas y Aromáticas", "Frutas Exóticas", "Ensaladas y Mezclas",
    ],
}

# ──────────────────────────────────────────────────────────────────────────
# TIENDAS MAKRO (ubicación, NSE, tamaño)
# Clave = código de tienda, TAL COMO aparece en tus reportes reales (columna
# "# Tienda" en las hojas Profimetrics, Análisis, CAMBIO, Ciudades-Region).
#
# La tienda 21 (Puente Aranda) YA NO EXISTE: se deja en el maestro con
# active=False para no perder trazabilidad histórica, pero `active_stores()`
# la excluye y `resolve_location()` la rechaza para consultas nuevas.
# ──────────────────────────────────────────────────────────────────────────
STORES: dict[int, dict] = {
    1:  {"name": "Villa del Río",     "city": "Bogotá",       "department": "Cundinamarca",      "nse": "Multiestrato", "size": "Grande",  "region_group": "CENTRO",           "active": True},
    2:  {"name": "Cumará",            "city": "Bogotá",       "department": "Cundinamarca",      "nse": "Multiestrato", "size": "Grande",  "region_group": "CENTRO",           "active": True},
    3:  {"name": "Valle de Lili",     "city": "Cali",         "department": "Valle del Cauca",   "nse": "Bajo",         "size": "Mediano", "region_group": "OCCIDENTE",        "active": True},
    4:  {"name": "Villa Santos",      "city": "Barranquilla", "department": "Atlántico",         "nse": "Alto",         "size": "Grande",  "region_group": "COSTA",            "active": True},
    5:  {"name": "San Juan",          "city": "Medellín",     "department": "Antioquia",         "nse": "Alto",         "size": "Grande",  "region_group": "ANTIOQUIA",        "active": True},
    7:  {"name": "Dosquebradas",      "city": "Dosquebradas", "department": "Risaralda",         "nse": "Medio",        "size": "Mediano", "region_group": "OCCIDENTE",        "active": True},
    8:  {"name": "Av. Boyacá",        "city": "Bogotá",       "department": "Cundinamarca",      "nse": "Multiestrato", "size": "Grande",  "region_group": "CENTRO",           "active": True},
    9:  {"name": "Ibagué",            "city": "Ibagué",       "department": "Tolima",            "nse": "Bajo",         "size": "Grande",  "region_group": "CENTRO",           "active": True},
    10: {"name": "Cartagena",         "city": "Cartagena",    "department": "Bolívar",           "nse": "Alto",         "size": "Grande",  "region_group": "COSTA",            "active": True},
    11: {"name": "Calle 30",          "city": "Barranquilla", "department": "Atlántico",         "nse": "Alto",         "size": "Mediano", "region_group": "COSTA",            "active": True},
    12: {"name": "Villavicencio",     "city": "Villavicencio","department": "Meta",              "nse": "Medio",        "size": "Mediano", "region_group": "CENTRO",           "active": True},
    13: {"name": "Cali Norte",        "city": "Cali",         "department": "Valle del Cauca",   "nse": "Bajo",         "size": "Grande",  "region_group": "OCCIDENTE",        "active": True},
    14: {"name": "Santa Marta",       "city": "Santa Marta",  "department": "Magdalena",         "nse": "Multiestrato", "size": "Pequeño", "region_group": "COSTA",            "active": True},
    15: {"name": "Cúcuta",            "city": "Cúcuta",       "department": "Norte de Santander","nse": "Medio",        "size": "Mediano", "region_group": "SANTANDER/COSTA",  "active": True},
    16: {"name": "Montería",          "city": "Montería",     "department": "Córdoba",           "nse": "Multiestrato", "size": "Pequeño", "region_group": "COSTA",            "active": True},
    17: {"name": "Tunja",             "city": "Tunja",        "department": "Boyacá",            "nse": "Alto",         "size": "Mediano", "region_group": "CENTRO",           "active": True},
    18: {"name": "Estación Poblado",  "city": "Medellín",     "department": "Antioquia",         "nse": "Alto",         "size": "Pequeño", "region_group": "ANTIOQUIA",        "active": True},
    19: {"name": "Floridablanca",     "city": "Floridablanca","department": "Santander",         "nse": "Medio",        "size": "Mediano", "region_group": "SANTANDER/COSTA",  "active": True},
    20: {"name": "Cajicá",            "city": "Cajicá",       "department": "Cundinamarca",      "nse": "Multiestrato", "size": "Pequeño", "region_group": "CENTRO",           "active": True},
    21: {"name": "Puente Aranda",     "city": "Bogotá",       "department": "Cundinamarca",      "nse": "Multiestrato", "size": "Pequeño", "region_group": "CENTRO",           "active": False},  # YA NO EXISTE
    22: {"name": "Valledupar",        "city": "Valledupar",   "department": "Cesar",             "nse": "Multiestrato", "size": "Mediano", "region_group": "COSTA",            "active": True},
    23: {"name": "Alto Prado",        "city": "Barranquilla", "department": "Atlántico",         "nse": "Alto",         "size": "Urbano",  "region_group": "COSTA",            "active": True},
}

# Código postal representativo por ciudad (para regionalizar precios VTEX vía
# Session Manager API — ver `_apply_region` en scrapers/vtex.py). Claves en
# minúsculas y sin tildes (ver `_fold`); no depende de cómo se escriba la
# ciudad al llamarlo.
CITY_POSTAL_CODES: dict[str, str] = {
    "bogota": "110111",
    "medellin": "050001",
    "cali": "760001",
    "barranquilla": "080001",
    "cartagena": "130001",
    "tunja": "150001",
    "valledupar": "200001",
    "monteria": "230001",
    "cajica": "250001",
    "villavicencio": "500001",
    "santa marta": "470001",
    "cucuta": "540001",
    "dosquebradas": "660004",
    "floridablanca": "680002",
    "ibague": "730001",
}


def _fold(text: str) -> str:
    """Minúsculas y sin tildes, para comparar nombres de ciudad sin depender de acentos."""
    import unicodedata

    normalized = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in normalized if not unicodedata.combining(c)).strip().lower()


def active_stores() -> dict[int, dict]:
    """Tiendas Makro vigentes (excluye la 21 - Puente Aranda, ya cerrada)."""
    return {code: meta for code, meta in STORES.items() if meta.get("active", True)}


def store_info(store_code) -> dict | None:
    """Metadatos de una tienda por su código (acepta int o str numérico)."""
    try:
        code = int(store_code)
    except (TypeError, ValueError):
        return None
    return STORES.get(code)


def resolve_location(key) -> dict | None:
    """
    Resuelve una clave de ubicación a metadatos de ciudad/tienda.

    Acepta: código de tienda (ej. 18 o "18") o nombre de ciudad (ej.
    "Bogotá", "bogota", "BOGOTA" — insensible a tildes/mayúsculas). Devuelve
    None si no reconoce la clave, o si corresponde a la tienda 21
    (Puente Aranda, cerrada) — así ninguna consulta nueva se regionaliza
    accidentalmente contra una tienda que ya no existe.
    """
    if key is None or key == "":
        return None

    store = store_info(key)
    if store is not None:
        if not store.get("active", True):
            return None
        city = store["city"]
        return {
            "store_code": int(key),
            "store_name": store["name"],
            "city": city,
            "postal_code": CITY_POSTAL_CODES.get(_fold(city)),
            "nse": store.get("nse"),
            "size": store.get("size"),
            "region_group": store.get("region_group"),
        }

    # No es un código de tienda válido: intentar como nombre de ciudad.
    postal = CITY_POSTAL_CODES.get(_fold(key))
    if postal:
        return {
            "store_code": None,
            "store_name": None,
            "city": str(key),
            "postal_code": postal,
            "nse": None,
            "size": None,
            "region_group": None,
        }
    return None


def city_postal_code(location_key) -> str | None:
    """
    Código postal representativo para regionalizar precios VTEX.

    Acepta código de tienda o nombre de ciudad (ver `resolve_location`).
    """
    loc = resolve_location(location_key)
    return loc.get("postal_code") if loc else None


def canonical_location_key(location_key) -> str | None:
    """
    Normaliza una clave de ubicación (código de tienda o nombre de ciudad,
    en cualquier formato/mayúsculas/tildes) a un identificador de texto
    estable, para que el histórico en base de datos compare siempre
    "Bogotá" == "BOGOTA" == "bogota", y 18 == "18". Devuelve None si la
    ubicación no se reconoce o corresponde a una tienda cerrada.
    """
    loc = resolve_location(location_key)
    if loc is None:
        return None
    if loc.get("store_code") is not None:
        return str(loc["store_code"])
    return _fold(loc["city"])

# ──────────────────────────────────────────────────────────────────────────
# RETAILERS
# clave interna -> metadatos (nombre, prioridad, color, dominio, tecnología)
# tech:   "vtex" (API JSON pública) | "html" (Playwright/BeautifulSoup)
# scrape: si False, no se consulta (referencia propia o sin canal scrapeable)
# Notas de campo (validadas contra los sitios reales en jun-2026):
#   - Jumbo Colombia (Cencosud) publica su catálogo VTEX en jumbocolombia.com.
#   - Metro comparte el MISMO canal online (jumbocolombia.com); se desactiva su
#     scraping para no duplicar precios y mantener la precisión del promedio.
#   - Makro tienda online (tienda.makro.com.co) se consulta vía Playwright/Instaleap.
#     El PVP de catálogo importado sigue siendo una fuente complementaria.
#   - Alkosto usa buscador Algolia (API JSON, claves públicas de cliente).
#   - PriceSmart expone precios vía API Bloomreach Discovery (sin login).
#   - Farmatodo no usa VTEX (sitio propio) → se trata como HTML (Playwright).
# ──────────────────────────────────────────────────────────────────────────
RETAILERS: dict[str, dict] = {
    "exito": {"name": "Éxito", "priority": 1, "color": "#ffe600", "base_url": "https://www.exito.com", "tech": "vtex", "scrape": True},
    "carulla": {"name": "Carulla", "priority": 1, "color": "#8bc63f", "base_url": "https://www.carulla.com", "tech": "vtex", "scrape": True},
    "jumbo": {"name": "Jumbo", "priority": 1, "color": "#2db84d", "base_url": "https://www.jumbocolombia.com", "tech": "vtex", "scrape": True},
    "metro": {"name": "Metro", "priority": 1, "color": "#e2231a", "base_url": "https://www.jumbocolombia.com", "tech": "vtex", "scrape": False},
    "makro": {"name": "Makro", "priority": 1, "color": "#e2001a", "base_url": "https://tienda.makro.com.co", "tech": "makro_tienda", "scrape": True},
    "alkosto": {"name": "Alkosto", "priority": 1, "color": "#e30613", "base_url": "https://www.alkosto.com", "tech": "algolia", "scrape": True},
    "olimpica": {"name": "Olímpica", "priority": 1, "color": "#ed1c24", "base_url": "https://www.olimpica.com", "tech": "vtex", "scrape": True},
    "pricesmart": {"name": "PriceSmart", "priority": 1, "color": "#004b8d", "base_url": "https://www.pricesmart.com", "tech": "bloomreach", "scrape": True},
    # Prioridad 2
    "d1": {"name": "D1", "priority": 2, "color": "#e30613", "base_url": "https://www.d1.com.co", "tech": "vtex", "scrape": True},
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
