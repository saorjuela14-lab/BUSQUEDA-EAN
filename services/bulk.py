"""
Carga masiva de productos desde Excel.

Procesa un archivo .xlsx con cientos de productos y ejecuta una consulta de
comparación por cada fila. Columnas reconocidas (insensible a mayúsculas/acentos):
  - ean         (obligatoria)
  - costo       (opcional)
  - descripcion (opcional, para homologación)
  - categoria   (opcional)

Devuelve un resumen con los informes por producto y métricas de proceso.
"""
from __future__ import annotations

import unicodedata
from typing import Optional

import pandas as pd

from . import pricing_service


def _normalize_col(name: str) -> str:
    """Normaliza nombres de columna: minúsculas, sin acentos ni espacios."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return text.strip().lower().replace(" ", "_")


_COLUMN_ALIASES = {
    "ean": {"ean", "codigo", "codigo_ean", "barcode"},
    "cost": {"costo", "cost", "costo_actual", "costo_makro"},
    "description": {"descripcion", "description", "nombre", "producto"},
    "category": {"categoria", "category"},
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


def process_bulk_file(
    path: str,
    *,
    target_margin: Optional[float] = None,
) -> dict:
    """
    Procesa un archivo Excel de carga masiva y devuelve un resumen consolidado.
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
        # Algunos Excel guardan el EAN como float (1.23e12); normalizamos.
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

        try:
            report = pricing_service.run_query(
                ean,
                cost=cost,
                description=description,
                category=category,
                target_margin=target_margin,
            )
            reports.append(
                {
                    "ean": ean,
                    "product_name": report["product_name"],
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

    return {
        "processed": len(reports),
        "errors": errors,
        "reports": reports,
    }
