"""
Resolución EAN → SKU Makro para búsquedas en tienda.makro.com.co.

Makro no indexa productos por EAN en su tienda online; usa el código interno
"Regular" (SKU). Este módulo consulta el catálogo importado para traducir
códigos de barras a SKU antes del scraping.
"""
from __future__ import annotations

from typing import Optional

from database import repository


def lookup_makro_sku(ean: str) -> Optional[dict]:
    """
    Busca un producto del catálogo Makro por EAN.

    Devuelve dict con ean, name, makro_sku, pvp, brand o None si no existe.
    """
    if not ean or str(ean).startswith("N-"):
        return None
    product = repository.get_product_by_ean(str(ean).strip())
    if not product or not product.get("makro_sku"):
        return None
    return product


def makro_search_query_for_ean(ean: str) -> tuple[Optional[str], Optional[dict]]:
    """
    Devuelve (query_para_buscar, producto_catálogo).

  - Si hay SKU en catálogo → query = SKU.
  - Si no hay mapeo → query = None.
    """
    product = lookup_makro_sku(ean)
    if not product:
        return None, None
    return str(product["makro_sku"]), product
