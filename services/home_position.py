"""
Posición de Makro frente al mercado de competidores.

Compara el PVP Makro (importado del catálogo) contra los KPIs del mercado
calculados solo con retailers competidores (sin Makro).
"""
from __future__ import annotations

from typing import Optional

from .rounding import format_cop, round_pct


def compute_home_position(makro_pvp: Optional[int], kpis: dict) -> dict:
    """
    Evalúa si Makro está más caro, más barato o alineado vs el mercado.

    Devuelve status: leader | competitive | above_avg | most_expensive
    """
    min_p = kpis.get("min_price")
    avg_p = kpis.get("avg_price")
    max_p = kpis.get("max_price")

    if makro_pvp is None or min_p is None:
        return {"available": False}

    vs_min = makro_pvp - min_p
    vs_min_pct = (vs_min / min_p * 100) if min_p else None
    vs_avg = (makro_pvp - avg_p) if avg_p else None
    vs_avg_pct = (vs_avg / avg_p * 100) if avg_p and vs_avg is not None else None
    vs_max = (makro_pvp - max_p) if max_p else None

    leader = kpis.get("leader_retailer")

    if makro_pvp <= min_p:
        status = "leader"
        level = "success"
        message = f"Makro tiene el precio más bajo del mercado ({format_cop(makro_pvp)})."
    elif max_p and makro_pvp >= max_p:
        status = "most_expensive"
        level = "danger"
        message = (
            f"Makro es el más caro ({format_cop(makro_pvp)}), "
            f"+{round_pct(vs_min_pct)}% vs {leader} ({format_cop(min_p)})."
        )
    elif avg_p and makro_pvp > avg_p:
        status = "above_avg"
        level = "warning"
        message = (
            f"Makro está por encima del promedio del mercado "
            f"({format_cop(makro_pvp)} vs prom. {format_cop(avg_p)}, +{round_pct(vs_avg_pct)}%)."
        )
    else:
        status = "competitive"
        level = "info"
        message = (
            f"Makro está por encima del mínimo (+{round_pct(vs_min_pct)}% vs {leader}) "
            f"pero por debajo o cerca del promedio ({format_cop(avg_p)})."
        )

    return {
        "available": True,
        "makro_pvp": makro_pvp,
        "status": status,
        "level": level,
        "message": message,
        "vs_min": vs_min,
        "vs_min_pct": round_pct(vs_min_pct),
        "vs_avg": vs_avg,
        "vs_avg_pct": round_pct(vs_avg_pct),
        "vs_max": vs_max,
        "market_min": min_p,
        "market_avg": avg_p,
        "market_max": max_p,
        "cheapest_retailer": leader,
    }


def home_position_alert(position: dict, ean: str) -> Optional[dict]:
    """Genera una alerta principal sobre la posición de Makro."""
    if not position.get("available"):
        return None
    status = position.get("status")
    if status == "leader":
        return {
            "type": "makro_leader",
            "level": "info",
            "retailer": "makro",
            "message": position["message"],
        }
    if status == "most_expensive":
        return {
            "type": "makro_expensive",
            "level": "danger",
            "retailer": "makro",
            "message": position["message"],
        }
    if status == "above_avg":
        return {
            "type": "makro_above_avg",
            "level": "warning",
            "retailer": "makro",
            "message": position["message"],
        }
    return {
        "type": "makro_competitive",
        "level": "info",
        "retailer": "makro",
        "message": position["message"],
    }
