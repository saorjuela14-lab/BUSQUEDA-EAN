"""
Redondeo financiero según la práctica comercial colombiana.

Reglas aplicadas:
- Los precios y valores monetarios se manejan en pesos colombianos ENTEROS
  (el COP no usa centavos en retail).
- El redondeo monetario usa ROUND_HALF_UP (redondeo comercial: 0.5 sube).
- Para precios sugeridos al consumidor se redondea a un múltiplo comercial
  (por defecto 50 COP) que es como se fijan los precios en góndola.
- Los porcentajes (márgenes) se redondean a 1 decimal.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional


def round_cop(value: Optional[float]) -> Optional[int]:
    """Redondea un valor monetario a pesos colombianos enteros (ROUND_HALF_UP)."""
    if value is None:
        return None
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_commercial(value: Optional[float], multiple: int = 50) -> Optional[int]:
    """
    Redondea a múltiplo comercial (góndola). Ej: 6987 -> 7000 con múltiplo 50.

    Se usa para PRECIOS SUGERIDOS, no para cálculos internos de margen.
    """
    if value is None:
        return None
    if multiple <= 0:
        return round_cop(value)
    d = Decimal(str(value)) / Decimal(multiple)
    rounded = d.quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal(multiple)
    return int(rounded)


def round_pct(value: Optional[float], decimals: int = 1) -> Optional[float]:
    """Redondea un porcentaje a `decimals` decimales (ROUND_HALF_UP)."""
    if value is None:
        return None
    quant = Decimal("1") if decimals == 0 else Decimal("1").scaleb(-decimals)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def format_cop(value: Optional[float]) -> str:
    """Formatea un valor como moneda colombiana: $1.234.567."""
    if value is None:
        return "—"
    n = round_cop(value)
    return "$" + f"{n:,}".replace(",", ".")
