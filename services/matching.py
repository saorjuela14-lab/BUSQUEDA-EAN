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


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s.,]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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


def similarity(query: str, candidate: str) -> float:
    """
    Score de similitud 0-100 entre dos descripciones de producto.

    Combina similitud textual (rapidfuzz) con penalización por tamaño.
    """
    base = fuzz.token_set_ratio(_normalize(query), _normalize(candidate))
    penalty = _size_penalty(query, candidate)
    # La penalización por tamaño reduce hasta un 40% del score textual.
    return round(base * (1 - 0.4 * penalty), 1)


def best_match(
    query: str,
    candidates: Sequence[MatchCandidate],
    threshold: int | None = None,
) -> Optional[MatchResult]:
    """
    Devuelve el mejor candidato por encima del umbral, o None.

    Resuelve también el caso "EAN en múltiples presentaciones": entre varios
    candidatos del mismo retailer, elige el de mayor score (más cercano).
    """
    if not candidates:
        return None
    threshold = Config.MATCH_THRESHOLD if threshold is None else threshold

    scored = [MatchResult(c, similarity(query, c.name)) for c in candidates]
    scored.sort(key=lambda m: m.score, reverse=True)
    top = scored[0]
    return top if top.score >= threshold else None


def rank_matches(query: str, candidates: Sequence[MatchCandidate]) -> list[MatchResult]:
    """Devuelve todos los candidatos ordenados por score descendente."""
    scored = [MatchResult(c, similarity(query, c.name)) for c in candidates]
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored
