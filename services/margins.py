"""
Comparativo de márgenes.

Calcula el margen en pesos y en porcentaje para cada retailer, dado el costo
del producto para Makro. Convención de margen sobre precio de venta:

    margen$  = precio_efectivo - costo
    margen%  = (precio_efectivo - costo) / precio_efectivo * 100

Todos los valores monetarios se redondean según práctica comercial colombiana.
"""
from __future__ import annotations

from typing import Optional

from .comparison import _effective
from .rounding import round_cop, round_pct


def margin_for_price(price: Optional[int], cost: Optional[int]) -> dict:
    """Margen $ y % para un precio y costo dados."""
    if price is None or cost is None or price == 0:
        return {"margin_value": None, "margin_pct": None}
    margin_value = round_cop(price - cost)
    margin_pct = round_pct((price - cost) / price * 100)
    return {"margin_value": margin_value, "margin_pct": margin_pct}


def compute_margins(results: list[dict], cost: Optional[int]) -> list[dict]:
    """
    Anexa margen $ y % a cada resultado disponible.

    Devuelve una lista de filas para tabla/exportación.
    """
    rows = []
    for r in results:
        price = _effective(r)
        m = margin_for_price(price, cost)
        rows.append(
            {
                "retailer": r.get("retailer"),
                "found": r.get("found"),
                "price": r.get("price"),
                "promo_price": r.get("promo_price"),
                "effective_price": price,
                "margin_value": m["margin_value"],
                "margin_pct": m["margin_pct"],
            }
        )
    return rows


def margin_summary(results: list[dict], cost: Optional[int]) -> dict:
    """Resumen de márgenes: mínimo, promedio y máximo (%)."""
    pcts = [
        m["margin_pct"]
        for m in (margin_for_price(_effective(r), cost) for r in results)
        if m["margin_pct"] is not None
    ]
    if not pcts:
        return {"min_margin_pct": None, "avg_margin_pct": None, "max_margin_pct": None}
    return {
        "min_margin_pct": round_pct(min(pcts)),
        "avg_margin_pct": round_pct(sum(pcts) / len(pcts)),
        "max_margin_pct": round_pct(max(pcts)),
    }
