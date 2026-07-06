"""
Inyección del precio Makro (PVP) desde el catálogo importado.

La tienda online de Makro se scrapea por separado. El PVP del catálogo importado
se integra como fuente complementaria cuando existe un EAN en catálogo local.
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
    Integra Makro en los resultados.

    - Si Makro ya fue encontrado por scraping, conserva ese resultado y añade
      `catalog_pvp` cuando el EAN está en catálogo importado.
    - Si no hay scraping pero sí catálogo, inyecta el PVP del catálogo.

    Devuelve (resultados_actualizados, producto_catálogo, pvp_makro).
    """
    catalog = repository.get_product_by_ean(ean)
    makro_catalog = build_makro_result(catalog)
    pvp = catalog["pvp"] if catalog else None

    existing = next((r for r in results if r.get("retailer") == HOME_RETAILER), None)
    if existing and existing.get("found"):
        if makro_catalog:
            existing["catalog_pvp"] = makro_catalog["price"]
            existing["catalog_product_name"] = makro_catalog.get("product_name")
            if existing.get("match_mode") != "catalog":
                existing["source"] = existing.get("source") or "scrape"
        return results, catalog, pvp or existing.get("catalog_pvp")

    if makro_catalog is None:
        return results, catalog, None

    cleaned = [r for r in results if r.get("retailer") != HOME_RETAILER]
    return cleaned + [makro_catalog], catalog, pvp


def competitor_results(results: list[dict]) -> list[dict]:
    """Filtra resultados de competidores (excluye Makro)."""
    return [r for r in results if r.get("retailer") != HOME_RETAILER]
