"""
Comparativo de precios entre retailers.

Calcula KPIs de mercado a partir de los resultados de scraping:
precio mínimo, máximo, promedio, spread, retailer líder (más barato) y
retailer más caro. Usa el precio efectivo (promo si existe, si no el regular).
"""
from __future__ import annotations

from typing import Optional

from .rounding import round_cop


def _effective(result: dict) -> Optional[int]:
    """Precio efectivo de un resultado: promo si existe, de lo contrario regular."""
    if not result.get("found"):
        return None
    promo = result.get("promo_price")
    price = result.get("price")
    return promo if promo else price


def compute_market_kpis(results: list[dict]) -> dict:
    """
    Devuelve los KPIs de mercado para una lista de resultados de retailers.

    Cada resultado es un dict con: retailer, found, price, promo_price, ...
    """
    priced = [(r, _effective(r)) for r in results]
    priced = [(r, p) for r, p in priced if p is not None]

    if not priced:
        return {
            "min_price": None,
            "max_price": None,
            "avg_price": None,
            "spread": None,
            "leader_retailer": None,
            "most_expensive_retailer": None,
            "available_count": 0,
            "total_count": len(results),
        }

    prices = [p for _, p in priced]
    min_price = min(prices)
    max_price = max(prices)
    avg_price = round_cop(sum(prices) / len(prices))
    spread = max_price - min_price

    leader = min(priced, key=lambda x: x[1])[0]
    expensive = max(priced, key=lambda x: x[1])[0]

    return {
        "min_price": min_price,
        "max_price": max_price,
        "avg_price": avg_price,
        "spread": spread,
        "leader_retailer": leader.get("retailer"),
        "most_expensive_retailer": expensive.get("retailer"),
        "available_count": len(priced),
        "total_count": len(results),
    }
