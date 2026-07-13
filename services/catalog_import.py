"""
Importación del catálogo Makro desde Excel/CSV.

Formatos reconocidos (insensible a mayúsculas/acentos):

1. Catálogo con PVP (clásico):
   - ean, nombre, pvp (obligatorios)
   - categoria, costo (opcionales)

2. Catálogo EAN ↔ SKU Makro (PRODUCTOS_MAKRO.xlsx):
   - Regular / SKU Makro, Descripción, Ean
   - Marca, Tipo Marca (opcionales)
   - PVP no requerido: se usa el SKU para buscar en tienda.makro.com.co
"""
from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd

from config import DATA_DIR
from database import repository

logger = logging.getLogger(__name__)

_COLUMN_ALIASES = {
    "ean": {"ean", "codigo_ean", "barcode", "codigo_barras"},
    "name": {"nombre", "name", "producto", "descripcion", "description"},
    "pvp": {"pvp", "precio", "precio_venta", "precio_makro", "precio_publico", "pvp_makro", "precio_venta_publico"},
    "makro_sku": {"regular", "sku", "makro_sku", "codigo_sku", "codigo_regular", "codigo_makro", "sku_makro"},
    "category": {"categoria", "category"},
    "cost": {"costo", "cost", "costo_makro", "costo_actual"},
    "brand": {"marca", "brand"},
}

DEFAULT_MAKRO_CATALOG = DATA_DIR / "PRODUCTOS_MAKRO.xlsx"


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


def _normalize_sku(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    sku = str(value).strip()
    if sku.lower() == "nan":
        return ""
    if sku.endswith(".0"):
        sku = sku[:-2]
    return sku


def _row_to_catalog_dict(row, cols: dict[str, str]) -> Optional[dict]:
    ean = _normalize_ean(row[cols["ean"]])
    if not ean:
        return None
    name = str(row[cols["name"]]).strip() if "name" in cols else ean
    if name.lower() == "nan":
        name = ean
    pvp = _to_int(row[cols["pvp"]]) if "pvp" in cols else None
    makro_sku = _normalize_sku(row[cols["makro_sku"]]) if "makro_sku" in cols else ""
    if pvp is None and not makro_sku:
        return None
    category = str(row[cols["category"]]).strip() if "category" in cols else None
    if category and category.lower() == "nan":
        category = None
    brand = str(row[cols["brand"]]).strip() if "brand" in cols else None
    if brand and brand.lower() == "nan":
        brand = None
    cost = _to_int(row[cols["cost"]]) if "cost" in cols else None
    return {
        "ean": ean,
        "name": name,
        "pvp": pvp,
        "makro_sku": makro_sku or None,
        "category": category,
        "brand": brand,
        "cost": cost,
    }


def process_catalog_file(path: str) -> dict:
    """Lee un Excel/CSV y persiste el catálogo Makro."""
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)

    if df.empty:
        return {"imported": 0, "errors": ["El archivo está vacío."], "total_rows": 0}

    cols = _map_columns(df)
    missing = [c for c in ("ean", "name") if c not in cols]
    if missing:
        raise ValueError(
            "El archivo debe contener columnas EAN y Nombre/Descripción. "
            f"Faltan: {', '.join(missing)}. Columnas encontradas: {', '.join(map(str, df.columns))}"
        )
    if "pvp" not in cols and "makro_sku" not in cols:
        raise ValueError(
            "El archivo debe contener PVP o SKU Makro (columna Regular). "
            f"Columnas encontradas: {', '.join(map(str, df.columns))}"
        )

    rows: list[dict] = []
    skipped = 0
    for _, row in df.iterrows():
        parsed = _row_to_catalog_dict(row, cols)
        if parsed:
            rows.append(parsed)
        else:
            skipped += 1

    result = repository.import_catalog_rows(rows)
    result["skipped"] = skipped
    result["with_sku"] = sum(1 for r in rows if r.get("makro_sku"))
    return result


def ensure_default_makro_catalog() -> Optional[dict]:
    """
    Carga el Excel PRODUCTOS_MAKRO.xlsx si el catálogo aún no tiene SKUs.

    Se ejecuta al arrancar la app para habilitar búsquedas EAN → SKU en Makro.
    """
    stats = repository.catalog_stats()
    if stats.get("with_sku", 0) > 0:
        return None
    path = DEFAULT_MAKRO_CATALOG
    if not path.exists():
        logger.warning("Catálogo Makro por defecto no encontrado en %s", path)
        return None
    logger.info("Importando catálogo Makro por defecto desde %s", path)
    return process_catalog_file(str(path))
