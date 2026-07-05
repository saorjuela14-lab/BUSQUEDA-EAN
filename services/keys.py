"""
Clave sintética estable para productos sin EAN real (típico en Fruver:
frutas/verduras a granel no tienen código de barras de fábrica, solo un
código interno de báscula o de catálogo Makro).

Se deriva del nombre (+ peso opcional, + variant opcional). La ciudad/tienda
de la consulta se guarda aparte en PriceQuery.city — no forma parte de la
clave, para que el mismo producto acumule histórico por ubicación. Cabe en
String(20) del modelo Product.
"""
from __future__ import annotations

import hashlib
from typing import Optional


def synthetic_key(
    name: str,
    weight_g: Optional[float] = None,
    variant: Optional[str] = None,
) -> str:
    """
    Deriva una clave sintética a partir del nombre del producto.

    `weight_g` separa consultas por cantidad objetivo (500g vs 1kg).
    `variant` permite distinguir variantes adicionales si se necesita (ej. un
    código interno) sin afectar el resto de las claves ya generadas.
    """
    key = name.strip().lower()
    if weight_g and weight_g > 0:
        key += f"|{int(round(weight_g))}g"
    if variant:
        key += f"|{variant.strip().lower()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"N-{digest}"
