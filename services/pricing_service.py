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

from config import HOME_RETAILER, Config, canonical_location_key, resolve_location
from database import repository

from . import alerts as alerts_mod
from . import comparison, margins, strategies
from .home_position import compute_home_position, home_position_alert
from .makro_catalog import apply_makro_catalog, competitor_results
from .weight import enrich_result_weight_metadata, normalize_results_for_weight
from scrapers import scrape_all


def _previous_avg(ean: str, city: Optional[str] = None) -> Optional[int]:
    """Promedio de la última consulta histórica (misma ciudad) para detectar variaciones."""
    history = repository.get_history(ean=ean, city=city, limit=1)
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
    target_weight_g: Optional[float] = None,
    retailer_keys: Optional[list[str]] = None,
    priority: Optional[int] = None,
    city: Optional[str] = None,
    persist: bool = True,
) -> dict:
    """
    Ejecuta una consulta de comparación completa y devuelve un informe.

    `city` (código de tienda Makro, ej. 18, o nombre de ciudad, ej. "Bogotá" —
    ver config.STORES / config.resolve_location) regionaliza el scraping
    en retailers VTEX que tengan la función "Region" activa. `category`
    ajusta la homologación por descripción — Fruver usa un umbral más
    permisivo (ver services/matching.py).

    El informe contiene: producto, resultados por retailer, KPIs, márgenes,
    estrategias, alertas y metadatos. Si `persist` es True, guarda el histórico.
    """
    # Normaliza a una clave estable (ej. "18" o "bogota") para que el
    # histórico compare siempre igual sin importar cómo se escribió la
    # ubicación. Si no se reconoce (o es una tienda cerrada), se ignora y la
    # consulta corre sin regionalizar.
    city = canonical_location_key(city) if city else None

    previous_avg = _previous_avg(ean, city) if persist else None

    raw_results = scrape_all(
        ean,
        description=description,
        retailer_keys=retailer_keys,
        priority=priority,
        city=city,
        category=category,
    )
    results = [r.to_dict() for r in raw_results]

    if target_weight_g and target_weight_g > 0:
        results = normalize_results_for_weight(results, target_weight_g)
    else:
        results = [enrich_result_weight_metadata(r) for r in results]

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
        "target_weight_g": target_weight_g,
        "match_mode": match_mode,
        "city": city,
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
                "city": city,
                "kpis": kpis,
                "results": results,
                "alerts": detected_alerts,
            }
        )
        report["query_id"] = saved.get("id")

    return report


def run_query_multi_city(
    ean: str,
    cities: list[str],
    cost: Optional[int] = None,
    description: Optional[str] = None,
    *,
    category: Optional[str] = None,
    target_margin: Optional[float] = None,
    target_weight_g: Optional[float] = None,
    retailer_keys: Optional[list[str]] = None,
    priority: Optional[int] = None,
    persist: bool = True,
) -> dict:
    """
    Ejecuta la misma consulta en varias ciudades/tiendas y devuelve un informe
    consolidado: uno por ubicación + una tabla comparativa de KPIs.

    Útil para el caso de Fruver: un mismo producto puede tener precio
    distinto de mercado (y de Makro) según la ciudad/tienda.

    Ubicaciones no reconocidas (o tiendas cerradas, ej. 21 - Puente Aranda)
    se omiten y quedan registradas en `report["skipped"]`.
    """
    by_city: dict[str, dict] = {}
    skipped: list[dict] = []
    for city in cities:
        if resolve_location(city) is None:
            skipped.append(
                {
                    "city": city,
                    "reason": "Ubicación no reconocida o tienda cerrada (ver config.STORES).",
                }
            )
            continue
        by_city[city] = run_query(
            ean,
            cost=cost,
            description=description,
            category=category,
            target_margin=target_margin,
            target_weight_g=target_weight_g,
            retailer_keys=retailer_keys,
            priority=priority,
            city=city,
            persist=persist,
        )

    comparison_rows = []
    for city, report in by_city.items():
        loc = resolve_location(city) or {}
        comparison_rows.append(
            {
                "city": city,
                "city_label": loc.get("city") or city,
                "store_code": loc.get("store_code"),
                "store_name": loc.get("store_name"),
                "nse": loc.get("nse"),
                "makro_pvp": report.get("makro_pvp"),
                "min_price": report.get("kpis", {}).get("min_price"),
                "avg_price": report.get("kpis", {}).get("avg_price"),
                "max_price": report.get("kpis", {}).get("max_price"),
                "leader_retailer": report.get("kpis", {}).get("leader_retailer"),
                "home_position": (report.get("home_position") or {}).get("status"),
            }
        )

    return {
        "ean": ean,
        "product_name": next(
            (r.get("product_name") for r in by_city.values() if r.get("product_name")), ean
        ),
        "cities": comparison_rows,
        "reports_by_city": by_city,
        "skipped": skipped,
    }
