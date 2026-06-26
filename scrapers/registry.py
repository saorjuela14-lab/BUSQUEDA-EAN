"""
Registro y orquestación de scrapers (scraping real).

Responsabilidades:
- Construir el scraper adecuado para cada retailer (VTEX o Playwright).
- Ejecutar el scraping de todos los retailers en paralelo (velocidad).
- Aislar fallos: si un retailer falla, se reporta como no encontrado con el
  detalle del error, sin afectar al resto de la comparación.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from config import RETAILERS, Config

from .base import BaseScraper, RetailerResult
from .retailers import SCRAPER_CLASSES

logger = logging.getLogger(__name__)


def get_scraper(key: str) -> BaseScraper:
    """Devuelve una instancia de scraper real para el retailer `key`."""
    meta = RETAILERS[key]
    scraper_cls = SCRAPER_CLASSES.get(key)
    if scraper_cls is None:
        raise ValueError(f"No hay scraper implementado para el retailer '{key}'.")
    return scraper_cls(key, meta["name"], meta["base_url"])


def get_scrapers(
    retailer_keys: Optional[list[str]] = None,
    priority: Optional[int] = None,
) -> list[BaseScraper]:
    """
    Construye la lista de scrapers a ejecutar según filtros.

    Excluye retailers marcados con scrape=False (referencia propia o sin canal
    consultable) salvo que se soliciten explícitamente por `retailer_keys`.
    """
    if retailer_keys:
        keys = [k for k in retailer_keys if k in RETAILERS]
    else:
        keys = [k for k, v in RETAILERS.items() if v.get("scrape", True)]
    if priority is not None:
        keys = [k for k in keys if RETAILERS[k]["priority"] == priority]
    return [get_scraper(k) for k in keys if k in SCRAPER_CLASSES]


def scrape_all(
    ean: str,
    description: Optional[str] = None,
    retailer_keys: Optional[list[str]] = None,
    priority: Optional[int] = None,
) -> list[RetailerResult]:
    """
    Ejecuta el scraping real de todos los retailers en paralelo.

    Devuelve una lista de RetailerResult (uno por retailer consultado).
    """
    scrapers = get_scrapers(retailer_keys, priority)
    results: list[RetailerResult] = []

    with ThreadPoolExecutor(max_workers=Config.SCRAPER_MAX_WORKERS) as pool:
        futures = {pool.submit(sc.search, ean, description): sc for sc in scrapers}
        for fut in as_completed(futures):
            sc = futures[fut]
            try:
                results.append(fut.result())
            except Exception as exc:  # robustez total
                logger.warning("Scraper %s falló: %s", sc.key, exc)
                results.append(
                    RetailerResult(
                        retailer=sc.key, retailer_name=sc.name, found=False, error=str(exc)
                    )
                )

    # Orden estable por prioridad y nombre para presentación consistente.
    results.sort(key=lambda r: (RETAILERS[r.retailer]["priority"], r.retailer_name))
    return results
