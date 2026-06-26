"""
Estrategias de precio para Makro.

Genera 4 escenarios de fijación de precio y su margen resultante:
  1. Igualar el precio mínimo del mercado.
  2. Igualar el precio promedio del mercado.
  3. Igualar al líder del mercado (retailer más barato == precio mínimo).
  4. Margen objetivo configurable (precio derivado del costo y margen meta).

El precio sugerido se redondea a múltiplo comercial colombiano (góndola).
"""
from __future__ import annotations

from typing import Optional

from config import Config

from .margins import margin_for_price
from .rounding import round_commercial


def _scenario(name: str, description: str, suggested_price: Optional[int], cost: Optional[int]) -> dict:
    rounded = round_commercial(suggested_price, Config.ROUNDING_MULTIPLE)
    margin = margin_for_price(rounded, cost)
    return {
        "name": name,
        "description": description,
        "suggested_price": rounded,
        "margin_value": margin["margin_value"],
        "margin_pct": margin["margin_pct"],
    }


def build_strategies(
    kpis: dict,
    cost: Optional[int],
    target_margin: float | None = None,
) -> list[dict]:
    """
    Construye los 4 escenarios de estrategia de precio para Makro.

    `kpis` proviene de comparison.compute_market_kpis.
    `target_margin` es una fracción (0.15 = 15%); si None usa el valor por defecto.
    """
    target_margin = Config.DEFAULT_TARGET_MARGIN if target_margin is None else target_margin

    min_price = kpis.get("min_price")
    avg_price = kpis.get("avg_price")
    leader_price = min_price  # el líder es, por definición, el de menor precio

    scenarios = [
        _scenario(
            "Igualar precio mínimo",
            f"Posicionarse al nivel del retailer más económico ({kpis.get('leader_retailer') or '—'}).",
            min_price,
            cost,
        ),
        _scenario(
            "Igualar precio promedio",
            "Fijar el precio en el promedio observado del mercado.",
            avg_price,
            cost,
        ),
        _scenario(
            "Igualar líder de mercado",
            f"Empatar al líder en precio ({kpis.get('leader_retailer') or '—'}).",
            leader_price,
            cost,
        ),
    ]

    # Escenario 4: precio que produce el margen objetivo sobre precio de venta.
    # precio = costo / (1 - margen_objetivo)
    target_price = None
    if cost is not None and 0 <= target_margin < 1:
        target_price = cost / (1 - target_margin) if target_margin < 1 else None
    scenarios.append(
        _scenario(
            f"Margen objetivo {round(target_margin * 100)}%",
            "Precio derivado del costo para alcanzar el margen objetivo configurado.",
            target_price,
            cost,
        )
    )
    return scenarios
