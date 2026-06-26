"""
Motor de alertas de negocio.

Genera alertas a partir de los resultados de una consulta:
- below_cost     : algún retailer vende por debajo del costo de Makro.
- out_of_market  : un precio se aleja fuertemente del promedio (outlier).
- high_variation : variación del precio efectivo > umbral vs. la consulta previa.

Niveles: info | warning | danger.
"""
from __future__ import annotations

from typing import Optional

from config import Config

from .comparison import _effective
from .rounding import format_cop, round_pct


def detect_alerts(
    ean: str,
    results: list[dict],
    kpis: dict,
    cost: Optional[int],
    previous_avg: Optional[int] = None,
) -> list[dict]:
    """Devuelve la lista de alertas detectadas para una consulta."""
    alerts: list[dict] = []
    avg_price = kpis.get("avg_price")

    # 1) Precio por debajo del costo.
    if cost is not None:
        for r in results:
            price = _effective(r)
            if price is not None and price < cost:
                alerts.append(
                    {
                        "type": "below_cost",
                        "level": "danger",
                        "retailer": r.get("retailer"),
                        "message": (
                            f"{r.get('retailer')} vende a {format_cop(price)}, "
                            f"por debajo del costo ({format_cop(cost)})."
                        ),
                    }
                )

    # 2) Precio fuera de mercado (outlier > 25% respecto al promedio).
    if avg_price:
        for r in results:
            price = _effective(r)
            if price is None:
                continue
            deviation = abs(price - avg_price) / avg_price
            if deviation > 0.25:
                alerts.append(
                    {
                        "type": "out_of_market",
                        "level": "warning",
                        "retailer": r.get("retailer"),
                        "message": (
                            f"{r.get('retailer')} está {round_pct(deviation * 100)}% "
                            f"fuera del promedio del mercado ({format_cop(avg_price)})."
                        ),
                    }
                )

    # 3) Variación del promedio respecto a la consulta histórica anterior.
    if previous_avg and avg_price:
        variation = (avg_price - previous_avg) / previous_avg
        if abs(variation) >= Config.ALERT_VARIATION_THRESHOLD:
            direction = "subió" if variation > 0 else "bajó"
            alerts.append(
                {
                    "type": "high_variation",
                    "level": "warning",
                    "retailer": None,
                    "message": (
                        f"El precio promedio {direction} {round_pct(abs(variation) * 100)}% "
                        f"frente a la consulta anterior."
                    ),
                }
            )

    return alerts
