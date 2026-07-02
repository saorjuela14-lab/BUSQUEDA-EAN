"""
Importación del catálogo Makro desde Excel/CSV.

Columnas reconocidas (insensible a mayúsculas/acentos):
  - ean    (obligatoria)
  - nombre (obligatoria)
  - pvp    (obligatoria) — precio de venta al público Makro
  - categoria (opcional)
  - costo  (opcional)
"""
from __future__ import annotations

import unicodedata
from typing import Optional

import pandas as pd

from database import repository

_COLUMN_ALIASES = {
    "ean": {"ean", "codigo", "codigo_ean", "barcode", "codigo_barras"},
    "name": {"nombre", "name", "producto", "descripcion", "description"},
    "pvp": {"pvp", "precio", "precio_venta", "precio_makro", "precio_publico", "pvp_makro", "precio_venta_publico"},
    "category": {"categoria", "category"},
    "cost": {"costo", "cost", "costo_makro", "costo_actual"},
}


def _normalize_col(name: str) -> str:
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return text.strip().lower().replace(" ", "_")


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
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
        raw = str(value).strip().replace("$", "").replace(".", "").replace(",", "")
        if not raw or raw.lower() == "nan":
            return None
        return int(float(raw))
    except (ValueError, TypeError):
        return None


def _normalize_ean(value) -> str:
    ean = str(value).strip()
    if ean.lower() == "nan":
        return ""
    if ean.endswith(".0"):
        ean = ean[:-2]
    return ean


def process_catalog_file(path: str) -> dict:
    """Lee un Excel/CSV y persiste el catálogo Makro."""
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)

    if df.empty:
        return {"imported": 0, "errors": ["El archivo está vacío."], "total_rows": 0}

    cols = _map_columns(df)
    missing = [c for c in ("ean", "name", "pvp") if c not in cols]
    if missing:
        raise ValueError(
            "El archivo debe contener columnas EAN, Nombre y PVP. "
            f"Faltan: {', '.join(missing)}. Columnas encontradas: {', '.join(map(str, df.columns))}"
        )

    rows: list[dict] = []
    for idx, row in df.iterrows():
        ean = _normalize_ean(row[cols["ean"]])
        if not ean:
            continue
        name = str(row[cols["name"]]).strip()
        if name.lower() == "nan":
            name = ean
        pvp = _to_int(row[cols["pvp"]])
        category = str(row[cols["category"]]).strip() if "category" in cols else None
        if category and category.lower() == "nan":
            category = None
        cost = _to_int(row[cols["cost"]]) if "cost" in cols else None
        rows.append({"ean": ean, "name": name, "pvp": pvp, "category": category, "cost": cost})

    result = repository.import_catalog_rows(rows)
    result["skipped"] = len(rows) - result["imported"]
    return result
