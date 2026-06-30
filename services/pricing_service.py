"""
Servicio orquestador de inteligencia de precios.

Coordina el flujo completo de una consulta:
  1. Scraping paralelo de retailers (por EAN, con fallback a descripción).
  2. Cálculo de KPIs de mercado (comparison).
  3. Cálculo de márgenes por retailer (margins).
  4. Estrategias de precio para Makro (strategies).
  5. Detección de alertas (alerts).
  6. Persistencia del histórico (database.repository).

Es el punto de entrada principal usado por la capa API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from config import HOME_RETAILER, Config
from database import repository

from . import alerts as alerts_mod
from . import comparison, margins, strategies
from .home_position import compute_home_position, home_position_alert
from .makro_catalog import apply_makro_catalog, competitor_results
from scrapers import scrape_all


def _previous_avg(ean: str) -> Optional[int]:
    """Promedio de la última consulta histórica para detectar variaciones."""
    history = repository.get_history(ean=ean, limit=1)
    if history:
        return history[0].get("avg_price")
    return None


def run_query(
    ean: str,
    cost: Optional[int] = None,
    description: Optional[str] = None,
    *,
    category: Optional[str] = None,
    target_margin: Optional[float] = None,
    retailer_keys: Optional[list[str]] = None,
    priority: Optional[int] = None,
    persist: bool = True,
) -> dict:
    """
    Ejecuta una consulta de comparación completa y devuelve un informe.

    El informe contiene: producto, resultados por retailer, KPIs, márgenes,
    estrategias, alertas y metadatos. Si `persist` es True, guarda el histórico.
    """
    previous_avg = _previous_avg(ean) if persist else None

    raw_results = scrape_all(
        ean,
        description=description,
        retailer_keys=retailer_keys,
        priority=priority,
    )
    results = [r.to_dict() for r in raw_results]

    # Determinar nombre/categoría del producto a partir de los hallazgos o catálogo.
    product_name = description
    match_mode = "ean"
    catalog_product = repository.get_product_by_ean(ean)
    for r in results:
        if r.get("found"):
            product_name = product_name or r.get("product_name")
            if r.get("match_mode") == "description":
                match_mode = "description"
    if product_name is None:
        product_name = catalog_product["name"] if catalog_product else ean
        category = category or (catalog_product["category"] if catalog_product else None)
    elif catalog_product and not product_name:
        product_name = catalog_product["name"]

    # Costo: el ingresado manualmente tiene prioridad; si no, el del catálogo.
    if cost is None and catalog_product:
        cost = catalog_product.get("cost")

    # Integrar PVP Makro desde catálogo importado.
    results, catalog_product, makro_pvp = apply_makro_catalog(ean, results, category=category)

    # KPIs de mercado solo con competidores (sin Makro).
    competitor_rows = competitor_results(results)
    kpis = comparison.compute_market_kpis(competitor_rows)
    margin_rows = margins.compute_margins(results, cost)
    margin_stats = margins.margin_summary(competitor_rows, cost)
    kpis["avg_margin_pct"] = margin_stats.get("avg_margin_pct")

    home_position = compute_home_position(makro_pvp, kpis)

    price_strategies = strategies.build_strategies(kpis, cost, target_margin)
    detected_alerts = alerts_mod.detect_alerts(ean, competitor_rows, kpis, cost, previous_avg)
    pos_alert = home_position_alert(home_position, ean)
    if pos_alert:
        detected_alerts.insert(0, pos_alert)

    # Margen de Makro (retailer de referencia) destacado.
    home_row = next((m for m in margin_rows if m["retailer"] == HOME_RETAILER), None)

    report = {
        "ean": ean,
        "product_name": product_name,
        "category": category,
        "cost": cost,
        "makro_pvp": makro_pvp,
        "home_position": home_position,
        "match_mode": match_mode,
        "timestamp": datetime.utcnow().isoformat(),
        "results": results,
        "kpis": kpis,
        "margins": margin_rows,
        "margin_summary": margin_stats,
        "home_margin": home_row,
        "strategies": price_strategies,
        "alerts": detected_alerts,
    }

    if persist:
        saved = repository.save_query(
            {
                "ean": ean,
                "cost": cost,
                "category": category,
                "product_name": product_name,
                "match_mode": match_mode,
                "kpis": kpis,
                "results": results,
                "alerts": detected_alerts,
            }
        )
        report["query_id"] = saved.get("id")

    return report
