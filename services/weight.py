"""
Normalización de precios para productos pesables (por kg / granel).

En VTEX, los productos vendidos por peso exponen measurementUnit=kg y
unitMultiplier como el peso del paquete en kg. El precio listado corresponde
a ese peso, no necesariamente a 1 kg.

Ejemplo: "Pechuga de Pollo x600g" → unitMultiplier=0.6, Price=25980
         → precio por kg = 25980 / 0.6 = 43300 COP/kg

Cuando el comprador indica un peso objetivo (ej. 1 kg, 500 g), escalamos los
precios de cada retailer a esa cantidad para comparar manzanas con manzanas.
"""
from __future__ import annotations

from typing import Optional

from services.matching import extract_size
from services.rounding import round_cop


def parse_weight(value, unit: str = "g") -> Optional[float]:
    """
    Convierte un valor de peso a gramos.

    Acepta unit en g, gr, kg. Retorna None si el valor es inválido.
    """
    if value in (None, ""):
        return None
    try:
        num = float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None
    if num <= 0:
        return None
    u = (unit or "g").lower().strip()
    if u in ("kg", "kilo", "kilos"):
        return num * 1000.0
    return num


def format_weight_label(grams: float) -> str:
    """Etiqueta legible: 1000 → '1 kg', 500 → '500 g'."""
    if grams >= 1000 and grams % 1000 == 0:
        return f"{int(grams / 1000)} kg"
    if grams >= 1000:
        kg = grams / 1000.0
        return f"{kg:g} kg".replace(".", ",")
    return f"{int(round(grams))} g"


def format_weight_for_query(grams: float) -> str:
    """Texto para enriquecer la búsqueda/homologación."""
    if grams >= 1000 and grams % 1000 == 0:
        return f"{int(grams / 1000)} kg"
    return f"{int(round(grams))}g"


def _price_per_kg_from_package(price: Optional[int], package_kg: float) -> Optional[int]:
    if price is None or not package_kg or package_kg <= 0:
        return None
    return round_cop(price / package_kg)


def _infer_package_grams(product_name: Optional[str]) -> Optional[float]:
    """Infiere el peso del empaque desde el nombre del producto."""
    if not product_name:
        return None
    size = extract_size(product_name)
    if size and size[0] == "weight":
        return size[1]
    return None


def enrich_result_weight_metadata(result: dict) -> dict:
    """
    Completa price_per_kg / promo_price_per_kg en un resultado si es posible.

    Prioridad: metadatos VTEX (measurement_unit=kg) → inferencia por nombre.
    """
    if not result.get("found"):
        return result

    price = result.get("price")
    promo = result.get("promo_price")
    unit = (result.get("measurement_unit") or "").lower()
    mult = result.get("unit_multiplier")

    package_kg: Optional[float] = None
    if unit == "kg" and mult and float(mult) > 0:
        package_kg = float(mult)
        result["is_weight_based"] = True
    else:
        package_g = _infer_package_grams(result.get("product_name"))
        if package_g and package_g > 0:
            package_kg = package_g / 1000.0
            result["is_weight_based"] = True

    if package_kg:
        result["package_weight_g"] = round(package_kg * 1000)
        result["price_per_kg"] = _price_per_kg_from_package(price, package_kg)
        if promo is not None:
            result["promo_price_per_kg"] = _price_per_kg_from_package(promo, package_kg)

    return result


def normalize_results_for_weight(results: list[dict], target_grams: float) -> list[dict]:
    """
    Escala precios de cada retailer al peso objetivo indicado por el comprador.

    Guarda los precios originales en price_original / promo_price_original.
    """
    if not target_grams or target_grams <= 0:
        return results

    target_kg = target_grams / 1000.0
    for r in results:
        enrich_result_weight_metadata(r)
        if not r.get("found"):
            continue

        ppk = r.get("price_per_kg")
        if ppk is None:
            continue

        r["price_original"] = r.get("price")
        r["promo_price_original"] = r.get("promo_price")
        r["price"] = round_cop(ppk * target_kg)

        promo_ppk = r.get("promo_price_per_kg")
        if promo_ppk is not None:
            r["promo_price"] = round_cop(promo_ppk * target_kg)

        r["weight_normalized"] = True
        r["target_weight_g"] = target_grams

    return results
