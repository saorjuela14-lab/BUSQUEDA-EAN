"""
Catálogo de coincidencias por retailer para búsquedas por nombre.

Agrupa los productos que hicieron match en cada ecommerce con sus precios,
independientemente de cuál se eligió como mejor coincidencia para KPIs/márgenes.
"""
from __future__ import annotations

from typing import Optional


def _match_from_result(result: dict) -> Optional[dict]:
    """Construye un ítem de catálogo a partir del resultado principal del retailer."""
    if not result.get("product_name"):
        return None
    price = result.get("price")
    promo = result.get("promo_price")
    return {
        "product_name": result.get("product_name"),
        "price": price,
        "promo_price": promo,
        "effective_price": result.get("effective_price") or promo or price,
        "presentation": result.get("presentation"),
        "url": result.get("url"),
        "image_url": result.get("image_url"),
        "match_score": result.get("match_score"),
    }


def build_search_catalog(results: list[dict]) -> dict[str, dict]:
    """
    Devuelve un dict retailer_key -> {
        retailer, retailer_name, found, product_count,
        best_match, products[], not_found_message, error
    }.
    """
    catalog: dict[str, dict] = {}
    for result in results:
        key = result.get("retailer") or ""
        products = list(result.get("matches") or [])

        if result.get("found") and not products:
            fallback = _match_from_result(result)
            if fallback:
                products = [fallback]

        for product in products:
            if product.get("effective_price") is None:
                product["effective_price"] = (
                    product.get("promo_price") or product.get("price")
                )

        catalog[key] = {
            "retailer": key,
            "retailer_name": result.get("retailer_name"),
            "found": bool(result.get("found")),
            "product_count": len(products),
            "best_match": products[0] if products else None,
            "products": products,
            "not_found_message": result.get("not_found_message"),
            "error": result.get("error"),
        }
    return catalog
