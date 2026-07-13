"""
Búsqueda multi-variante compartida para todos los retailers.

Aplica variantes tolerantes a tildes, mayúsculas y plurales (ver matching.py)
y fusiona resultados sin duplicados. Usado por VTEX, PriceSmart, Algolia,
Playwright, Makro, etc.
"""
from __future__ import annotations

import logging
from typing import Callable, Iterable, TypeVar

from .matching import search_query_variants

logger = logging.getLogger(__name__)

T = TypeVar("T")


def merge_query_search(
    description: str,
    search_fn: Callable[[str], Iterable[T]],
    *,
    dedupe_key: Callable[[T], str],
    max_variants: int | None = None,
) -> list[T]:
    """
    Ejecuta `search_fn` con cada variante de consulta y devuelve ítems únicos.

    `dedupe_key` identifica cada resultado (productId, pid, nombre, etc.).
    """
    merged: list[T] = []
    seen: set[str] = set()
    variants = search_query_variants(description)
    if max_variants is not None:
        variants = variants[:max_variants]

    for query in variants:
        try:
            batch = list(search_fn(query))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Variante de búsqueda falló (%r): %s", query, exc)
            continue
        for item in batch:
            key = dedupe_key(item)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged
