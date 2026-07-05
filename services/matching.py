"""
Homologación inteligente de productos.

Cuando un retailer no encuentra el EAN, se busca por descripción y se calcula
la similitud con rapidfuzz. Si un EAN existe en múltiples presentaciones,
se selecciona la coincidencia más cercana usando una combinación de:
- similitud textual del nombre (token_set_ratio), y
- penalización por diferencia de tamaño/contenido (g, ml, l, kg, unidades).

Ejemplo: "Leche Alpina Entera 1100 ml" -> coincidencia 96%.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Sequence

from rapidfuzz import fuzz

from config import Config

# Unidades de medida normalizadas a una base común.
_UNIT_TO_BASE = {
    "kg": ("weight", 1000.0),
    "g": ("weight", 1.0),
    "gr": ("weight", 1.0),
    "l": ("volume", 1000.0),
    "lt": ("volume", 1000.0),
    "ml": ("volume", 1.0),
    "cc": ("volume", 1.0),
    "un": ("count", 1.0),
    "und": ("count", 1.0),
    "u": ("count", 1.0),
}

_SIZE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|gr|g|lt|l|ml|cc|und|un|u)\b", re.IGNORECASE
)


@dataclass
class MatchCandidate:
    """Candidato a homologar (resultado crudo de un retailer)."""

    name: str
    payload: dict  # datos arbitrarios asociados (precio, url, etc.)


@dataclass
class MatchResult:
    candidate: MatchCandidate
    score: float  # 0-100


# Palabras de relleno sin valor discriminante entre presentaciones de un mismo
# producto (unidad de venta, conectores). Quitarlas antes de comparar evita que
# "AGUACATE KG" pierda similitud frente a "Aguacate Hass x Kg Granel" solo por
# tokens que no describen el producto en sí. No incluye variedades/marcas
# porque esas SÍ pueden importar para otras categorías.
_NOISE_WORDS = {
    "x", "de", "del", "la", "el", "los", "las",
    "granel", "unidad", "und", "un", "u",
    "empaque", "empacado", "import", "importado",
    "fresco", "fresca", "nacional",
}


def _strip_accents(text: str) -> str:
    """Quita tildes/diéresis y normaliza ñ→n para comparación robusta en español.

    Bug corregido: antes "PLATANO VERDE" vs "Plátano Verde" scoreaba 63/100 en
    vez de ~100 solo por la tilde, lo que rechazaba homologaciones válidas de
    Fruver bajo el umbral de similitud.
    """
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _normalize(text: str, *, strip_noise: bool = False) -> str:
    text = _strip_accents(text.lower())
    text = re.sub(r"[^\w\s.,]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if strip_noise:
        text = " ".join(w for w in text.split() if w not in _NOISE_WORDS)
    return text


def extract_size(text: str) -> Optional[tuple[str, float]]:
    """
    Extrae (dimensión, magnitud_base) de un texto.

    Ej: "Leche 1100 ml" -> ("volume", 1100.0); "Pan x600g" -> ("weight", 600.0).
    """
    match = _SIZE_RE.search(text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    dim, factor = _UNIT_TO_BASE.get(unit, (None, None))
    if dim is None:
        return None
    return dim, value * factor


def _size_penalty(query: str, candidate: str) -> float:
    """
    Penalización 0..1 por diferencia de presentación (tamaño/contenido).

    0 = mismo tamaño; cuanto mayor la diferencia relativa, mayor la penalización.
    Si no se detecta tamaño en alguno, no se penaliza (retorna 0).
    """
    q = extract_size(query)
    c = extract_size(candidate)
    if not q or not c:
        return 0.0
    if q[0] != c[0]:  # dimensiones distintas (peso vs volumen) -> penaliza fuerte
        return 0.5
    qv, cv = q[1], c[1]
    if max(qv, cv) == 0:
        return 0.0
    rel_diff = abs(qv - cv) / max(qv, cv)
    return min(rel_diff, 1.0)


def resolve_threshold(category: Optional[str] = None) -> int:
    """
    Umbral mínimo de homologación según categoría.

    Fruver usa un umbral más bajo: nombres cortos/genéricos ("AGUACATE KG")
    contra nombres comerciales con variedad ("Aguacate Hass x Kg") pierden
    similitud sin ser productos distintos. Categorías con presentaciones que
    SÍ deben distinguirse por tamaño (lácteos, etc.) mantienen el umbral base.
    """
    if category and category.strip().lower() == "fruver":
        return Config.MATCH_THRESHOLD_FRUVER
    return Config.MATCH_THRESHOLD


def similarity(query: str, candidate: str, *, category: Optional[str] = None) -> float:
    """
    Score de similitud 0-100 entre dos descripciones de producto.

    Combina similitud textual (rapidfuzz, sin tildes) con penalización por
    tamaño. Para Fruver además se descartan palabras de relleno (granel,
    unidad, x, import, etc.) que no aportan al match del producto en sí.
    """
    is_fruver = bool(category and category.strip().lower() == "fruver")
    base = fuzz.token_set_ratio(
        _normalize(query, strip_noise=is_fruver),
        _normalize(candidate, strip_noise=is_fruver),
    )
    penalty = _size_penalty(query, candidate)
    # La penalización por tamaño reduce hasta un 40% del score textual.
    return round(base * (1 - 0.4 * penalty), 1)


def best_match(
    query: str,
    candidates: Sequence[MatchCandidate],
    threshold: int | None = None,
    *,
    category: Optional[str] = None,
) -> Optional[MatchResult]:
    """
    Devuelve el mejor candidato por encima del umbral, o None.

    Resuelve también el caso "EAN en múltiples presentaciones": entre varios
    candidatos del mismo retailer, elige el de mayor score (más cercano).
    Si no se pasa `threshold` explícito, se resuelve según `category`
    (Fruver usa un umbral más permisivo, ver `resolve_threshold`).
    """
    if not candidates:
        return None
    threshold = resolve_threshold(category) if threshold is None else threshold

    scored = [MatchResult(c, similarity(query, c.name, category=category)) for c in candidates]
    scored.sort(key=lambda m: m.score, reverse=True)
    top = scored[0]
    return top if top.score >= threshold else None


def rank_matches(
    query: str, candidates: Sequence[MatchCandidate], *, category: Optional[str] = None
) -> list[MatchResult]:
    """Devuelve todos los candidatos ordenados por score descendente."""
    scored = [MatchResult(c, similarity(query, c.name, category=category)) for c in candidates]
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored
