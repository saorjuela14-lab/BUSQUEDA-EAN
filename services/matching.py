"""
Homologación inteligente de productos.

Cuando un retailer no encuentra el EAN, se busca por descripción y se calcula
un score de relevancia compuesto (no solo similitud difusa) con rapidfuzz.
Prioriza coincidencias exactas y al inicio del nombre; penaliza cuando el
término buscado aparece solo como ingrediente, sabor o descriptor secundario.

Ejemplo: "Arándanos" -> "Arándanos Kosher" antes que "Pudín con arándanos".
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

# Conectores que suelen separar el producto principal de ingredientes secundarios.
_INGREDIENT_BREAK = frozenset({"con", "y", "de", "en", "para", "sin"})

# Tipos de producto elaborado: si el nombre empieza así y el término buscado
# solo aparece después, se penaliza (ej. "Yoghurt ... Arándanos").
_SECONDARY_HEAD = frozenset(
    {
        "yoghurt", "yogurt", "yogur", "pudin", "puding", "leche", "jugo", "galleta",
        "bebida", "mezcla", "mani", "barra", "cereal", "smoothie", "helado",
        "mermelada", "confiture", "snack", "bar", "pastel", "torta", "postre",
        "granola", "mix", "chocolate", "cereal", "avena", "granola",
    }
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
# tokens que no describen el producto en sí.
_NOISE_WORDS = {
    "x", "de", "del", "la", "el", "los", "las",
    "granel", "unidad", "und", "un", "u",
    "empaque", "empacado", "import", "importado",
    "fresco", "fresca", "nacional",
}


def _strip_accents(text: str) -> str:
    """Quita tildes/diéresis y normaliza ñ→n para comparación robusta en español."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _normalize(text: str, *, strip_noise: bool = False) -> str:
    text = _strip_accents(text.lower())
    text = re.sub(r"[^\w\s.,]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if strip_noise:
        text = " ".join(w for w in text.split() if w not in _NOISE_WORDS)
    return text


def _primary_tokens(name: str, *, strip_noise: bool = False) -> list[str]:
    """Tokens del nombre principal (antes de conectores de ingrediente)."""
    tokens = _normalize(name, strip_noise=strip_noise).split()
    primary: list[str] = []
    for token in tokens:
        if token in _INGREDIENT_BREAK:
            break
        primary.append(token)
    return primary


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
    if q[0] != c[0]:
        return 0.5
    qv, cv = q[1], c[1]
    if max(qv, cv) == 0:
        return 0.0
    rel_diff = abs(qv - cv) / max(qv, cv)
    return min(rel_diff, 1.0)


def _relevance_adjustments(query: str, candidate: str, *, strip_noise: bool) -> float:
    """
    Bonificaciones y penalizaciones de relevancia semántica (-40..+45).

  - Coincidencia exacta o al inicio del nombre: bonus alto.
  - Término solo tras "con"/"y"/"de": penalización fuerte.
  - Producto elaborado cuyo sabor coincide pero no el producto base: penalización.
    """
    q_norm = _normalize(query, strip_noise=strip_noise)
    c_norm = _normalize(candidate, strip_noise=strip_noise)
    q_tokens = q_norm.split()
    primary = _primary_tokens(candidate, strip_noise=strip_noise)
    delta = 0.0

    if q_norm == c_norm:
        return 45.0
    if c_norm.startswith(q_norm):
        delta += 20.0
    if primary and q_tokens and primary[0] == q_tokens[0]:
        delta += 18.0
    elif primary and q_tokens and all(t in primary for t in q_tokens):
        delta += 10.0

    if all(re.search(rf"\b{re.escape(t)}\b", c_norm) for t in q_tokens):
        delta += 5.0
    else:
        delta -= 10.0

    if re.search(rf"\b(con|y|de|en)\s+.*\b{re.escape(q_norm)}\b", c_norm):
        delta -= 30.0
    if " con " in f" {c_norm} " and not all(t in primary for t in q_tokens):
        delta -= 25.0

    if (
        primary
        and primary[0] in _SECONDARY_HEAD
        and primary[0] not in q_tokens
        and any(t in primary[1:] for t in q_tokens)
    ):
        delta -= 30.0

    if primary and q_tokens and q_tokens[0] not in primary[:2] and any(t in primary[2:] for t in q_tokens):
        delta -= 15.0

    if primary and q_tokens and primary[0].startswith(q_tokens[0]) and primary[0] != q_tokens[0]:
        delta -= 8.0

    return delta


def resolve_threshold(category: Optional[str] = None) -> int:
    """
    Umbral mínimo de homologación según categoría.

    Fruver usa un umbral más bajo: nombres cortos/genéricos ("AGUACATE KG")
    contra nombres comerciales con variedad ("Aguacate Hass x Kg") pierden
    similitud sin ser productos distintos.
    """
    if category and category.strip().lower() == "fruver":
        return Config.MATCH_THRESHOLD_FRUVER
    return Config.MATCH_THRESHOLD


def similarity(query: str, candidate: str, *, category: Optional[str] = None) -> float:
    """
    Score de similitud 0-100 entre dos descripciones de producto.

    Combina similitud textual (rapidfuzz), ajustes de relevancia semántica
    y penalización por diferencia de presentación/tamaño.
    """
    is_fruver = bool(category and category.strip().lower() == "fruver")
    q_norm = _normalize(query, strip_noise=is_fruver)
    c_norm = _normalize(candidate, strip_noise=is_fruver)

    base = float(fuzz.token_set_ratio(q_norm, c_norm))
    base += _relevance_adjustments(query, candidate, strip_noise=is_fruver)

    penalty = _size_penalty(query, candidate)
    score = base * (1 - 0.4 * penalty)
    return round(min(100.0, max(0.0, score)), 1)


def best_match(
    query: str,
    candidates: Sequence[MatchCandidate],
    threshold: int | None = None,
    *,
    category: Optional[str] = None,
) -> Optional[MatchResult]:
    """
    Devuelve el mejor candidato por encima del umbral, o None.

    Entre varios candidatos del mismo retailer, elige el de mayor score.
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


def filter_relevant_matches(
    query: str,
    candidates: Sequence[MatchCandidate],
    *,
    category: Optional[str] = None,
    threshold: int | None = None,
) -> list[MatchResult]:
    """Candidatos por encima del umbral, ordenados por relevancia."""
    threshold = resolve_threshold(category) if threshold is None else threshold
    ranked = rank_matches(query, candidates, category=category)
    return [m for m in ranked if m.score >= threshold]
