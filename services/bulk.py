"""
Carga masiva de productos desde Excel.

Procesa un archivo .xlsx con cientos de productos y ejecuta una consulta de
comparación por cada fila. Columnas reconocidas (insensible a mayúsculas/acentos):
  - ean              (obligatoria)
  - costo            (opcional)
  - descripcion      (opcional, para homologación)
  - categoria        (opcional)
  - margen_objetivo  (opcional, por fila; acepta 15 o 0.15 para 15%)

Si una fila no trae margen objetivo, se usa el valor por defecto del formulario
(o el margen global configurado en la app).

Devuelve un resumen con los informes por producto y métricas de proceso.
"""
from __future__ import annotations

import unicodedata
from typing import Optional

import pandas as pd

from . import pricing_service
from .margins import margin_for_price
from .rounding import round_pct


def _normalize_col(name: str) -> str:
    """Normaliza nombres de columna: minúsculas, sin acentos ni espacios."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return text.strip().lower().replace(" ", "_")


_COLUMN_ALIASES = {
    "ean": {"ean", "codigo", "codigo_ean", "barcode"},
    "cost": {"costo", "cost", "costo_actual", "costo_makro"},
    "description": {"descripcion", "description", "nombre", "producto"},
    "category": {"categoria", "category"},
    "target_margin": {
        "margen_objetivo",
        "margen",
        "margen_objetivo_pct",
        "margen_objetivo_porcentaje",
        "target_margin",
        "margin",
        "margin_target",
    },
}


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Mapea las columnas reales del DataFrame a las claves canónicas."""
    mapping: dict[str, str] = {}
    normalized = {_normalize_col(c): c for c in df.columns}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[canonical] = normalized[alias]
                break
    return mapping


def _to_int(value) -> Optional[int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _parse_target_margin(value) -> Optional[float]:
    """
    Convierte un margen objetivo a fracción (0.15 = 15%).

    Acepta valores en porcentaje (15) o fracción (0.15).
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        raw = str(value).strip().replace(",", ".")
        if not raw or raw.lower() == "nan":
            return None
        num = float(raw)
    except (ValueError, TypeError):
        return None
    if num < 0 or num >= 100:
        if 0 <= num < 1:
            return num
        return None
    # Valores típicos de Excel: 15 => 15%
    if num >= 1:
        return num / 100.0
    return num


def _resolve_target_margin(
    row_value,
    default_margin: Optional[float],
) -> Optional[float]:
    """Prioriza el margen de la fila; si no hay, usa el valor por defecto."""
    row_margin = _parse_target_margin(row_value)
    if row_margin is not None:
        return row_margin
    return default_margin


def _actual_margin_pct(report: dict) -> Optional[float]:
    """Margen real Makro (PVP vs costo) a partir del informe de consulta."""
    home = report.get("home_margin")
    if home and home.get("margin_pct") is not None:
        return home["margin_pct"]
    pvp = report.get("makro_pvp")
    cost = report.get("cost")
    if pvp is not None and cost is not None:
        return margin_for_price(pvp, cost).get("margin_pct")
    return None


def _validate_target_margin(report: dict, target_margin: Optional[float]) -> Optional[dict]:
    """
    Valida el margen real frente al objetivo configurado para el EAN.

    Devuelve estado: met | below | no_data
    """
    if target_margin is None:
        return None

    actual = _actual_margin_pct(report)
    target_pct = round_pct(target_margin * 100)
    if actual is None:
        return {
            "status": "no_data",
            "target_margin_pct": target_pct,
            "actual_margin_pct": None,
            "message": "Sin PVP/costo Makro para validar el margen objetivo.",
        }

    diff = actual - target_pct
    if diff >= -0.5:
        return {
            "status": "met",
            "target_margin_pct": target_pct,
            "actual_margin_pct": actual,
            "message": f"Margen actual {actual}% cumple el objetivo {target_pct}%.",
        }
    return {
        "status": "below",
        "target_margin_pct": target_pct,
        "actual_margin_pct": actual,
        "gap_pct": round_pct(diff),
        "message": (
            f"Margen actual {actual}% está por debajo del objetivo {target_pct}% "
            f"({round_pct(abs(diff))} pp)."
        ),
    }


def _target_strategy_price(report: dict) -> Optional[int]:
    """Precio sugerido del escenario 'Margen objetivo' (4.º escenario)."""
    for strategy in report.get("strategies") or []:
        if str(strategy.get("name", "")).startswith("Margen objetivo"):
            return strategy.get("suggested_price")
    return None


def process_bulk_file(
    path: str,
    *,
    target_margin: Optional[float] = None,
) -> dict:
    """
    Procesa un archivo Excel de carga masiva y devuelve un resumen consolidado.

    `target_margin` actúa como valor por defecto cuando la fila no trae margen propio.
    """
    df = pd.read_excel(path)
    if df.empty:
        return {"processed": 0, "errors": ["El archivo está vacío."], "reports": []}

    cols = _map_columns(df)
    if "ean" not in cols:
        raise ValueError(
            "El archivo debe contener una columna 'EAN'. Columnas encontradas: "
            + ", ".join(map(str, df.columns))
        )

    reports: list[dict] = []
    errors: list[str] = []

    for idx, row in df.iterrows():
        ean = str(row[cols["ean"]]).strip()
        if not ean or ean.lower() == "nan":
            continue
        if ean.endswith(".0"):
            ean = ean[:-2]

        cost = _to_int(row[cols["cost"]]) if "cost" in cols else None
        description = (
            str(row[cols["description"]]).strip() if "description" in cols else None
        )
        if description and description.lower() == "nan":
            description = None
        category = str(row[cols["category"]]).strip() if "category" in cols else None
        if category and category.lower() == "nan":
            category = None

        row_target_margin = _resolve_target_margin(
            row[cols["target_margin"]] if "target_margin" in cols else None,
            target_margin,
        )

        try:
            report = pricing_service.run_query(
                ean,
                cost=cost,
                description=description,
                category=category,
                target_margin=row_target_margin,
            )
            margin_check = _validate_target_margin(report, row_target_margin)
            reports.append(
                {
                    "ean": ean,
                    "product_name": report["product_name"],
                    "target_margin_pct": round_pct(row_target_margin * 100)
                    if row_target_margin is not None
                    else None,
                    "target_price": _target_strategy_price(report),
                    "margin_validation": margin_check,
                    "kpis": report["kpis"],
                    "home_margin": report.get("home_margin"),
                    "home_position": report.get("home_position"),
                    "makro_pvp": report.get("makro_pvp"),
                    "alerts": report["alerts"],
                    "query_id": report.get("query_id"),
                }
            )
        except Exception as exc:  # registrar, no detener el lote
            errors.append(f"Fila {idx + 2} (EAN {ean}): {exc}")

    below_target = sum(
        1 for r in reports if (r.get("margin_validation") or {}).get("status") == "below"
    )

    return {
        "processed": len(reports),
        "below_target_count": below_target,
        "errors": errors,
        "reports": reports,
    }
