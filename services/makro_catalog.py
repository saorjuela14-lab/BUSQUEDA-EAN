"""
Inyección del precio Makro (PVP) desde el catálogo importado.

Makro no se scrapea (requiere login). El PVP se carga vía Excel/CSV y se
integra en cada comparación para evaluar la posición frente al mercado.
"""
from __future__ import annotations

from typing import Optional

from config import HOME_RETAILER, RETAILERS
from database import repository


def build_makro_result(catalog: Optional[dict]) -> Optional[dict]:
    """Construye el resultado de Makro a partir del catálogo local."""
    if not catalog or catalog.get("pvp") is None:
        return None
    meta = RETAILERS.get(HOME_RETAILER, {})
    return {
        "retailer": HOME_RETAILER,
        "retailer_name": meta.get("name", "Makro"),
        "found": True,
        "price": catalog["pvp"],
        "promo_price": None,
        "promo_desc": None,
        "product_name": catalog.get("name"),
        "url": meta.get("base_url"),
        "match_mode": "catalog",
        "match_score": None,
        "source": "catalog",
    }


def apply_makro_catalog(
    ean: str,
    results: list[dict],
    *,
    category: Optional[str] = None,
) -> tuple[list[dict], Optional[dict], Optional[int]]:
    """
    Inyecta Makro en los resultados si el EAN está en catálogo.

    Devuelve (resultados_actualizados, producto_catálogo, pvp_makro).
    """
    catalog = repository.get_product_by_ean(ean)
    if catalog is None:
        return results, catalog, None

    # Evitar duplicados si Makro ya viniera en los resultados.
    cleaned = [r for r in results if r.get("retailer") != HOME_RETAILER]
    return cleaned + [makro], catalog, catalog["pvp"] if catalog else None


def competitor_results(results: list[dict]) -> list[dict]:
    """Filtra resultados de competidores (excluye Makro)."""
    return [r for r in results if r.get("retailer") != HOME_RETAILER]
