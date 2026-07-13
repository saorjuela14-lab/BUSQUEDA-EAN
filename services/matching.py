"""
Homologación inteligente de productos.

Prioriza coincidencias donde el término buscado describe el producto principal
(no un sabor/ingrediente secundario). Filtra candidatos irrelevantes antes de
puntuar y respeta el orden del catálogo del retailer como desempate.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Sequence

from rapidfuzz import fuzz

from config import Config

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

# Sufijos de peso/volumen en la consulta (ej. "500g", "1 kg") — no son parte del nombre.
_QUERY_WEIGHT_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:kg|gr|g|lt|l|ml|cc|und|un|u)\b", re.IGNORECASE
)

_INGREDIENT_BREAK = frozenset({"con", "y", "de", "en", "para", "sin"})

# Productos elaborados: si el nombre empieza así, el término buscado suele ser
# sabor/variante y NO el producto que el usuario quiere comparar.
_SECONDARY_HEAD = frozenset(
    {
        "yoghurt", "yogurt", "yogur", "pudin", "puding", "leche", "jugo", "galleta",
        "bebida", "mezcla", "mani", "barra", "cereal", "smoothie", "helado",
        "mermelada", "confiture", "snack", "bar", "pastel", "torta", "postre",
        "granola", "mix", "chocolate", "avena", "pan", "te", "cafe", "whisky",
        "cerveza", "aceite", "arroz", "salchicha", "queso", "papel", "barra",
        "confite", "dulce", "caramelo", "mantequilla", "margarina", "salsa",
        "jugo", "muffin", "waffle", "bagel", "mani", "frito", "lay",
        "pasaboca", "pasabocas", "snack",
    }
)


@dataclass
class MatchCandidate:
    """Candidato a homologar (resultado crudo de un retailer)."""

    name: str
    payload: dict  # catalog_rank, precio, url, etc.


@dataclass
class MatchResult:
    candidate: MatchCandidate
    score: float  # 0-100


_NOISE_WORDS = {
    "x", "de", "del", "la", "el", "los", "las",
    "granel", "unidad", "und", "un", "u",
    "empaque", "empacado", "import", "importado",
    "fresco", "fresca", "nacional",
}

# Términos de empaque/presentación que no siempre aparecen en el título del retailer.
_OPTIONAL_DESCRIPTOR_TOKENS = frozenset(
    {
        "estuche", "bandeja", "empaque", "pack", "paquete", "bolsa", "canasta",
        "congelado", "fresco", "fresca", "natural", "organico", "organica",
        "importado", "importada", "granel", "especial", "premium", "unidad",
    }
)


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _singularize_es(token: str) -> str:
    """
    Aproximación al singular en español para comparar plurales en homologación.

    Ej: arandanos → arandano, fresas → fresa, tomates → tomate.
    """
    t = token.lower().strip()
    if len(t) < 3:
        return t
    if t.endswith("s"):
        if t.endswith("es") and len(t) > 4 and t[-3] not in "aeiou":
            return t[:-2]
        if t[-2] in "aeiou":
            return t[:-1]
    return t


def _tokens_match(a: str, b: str) -> bool:
    """True si dos tokens son iguales ignorando plural y variaciones cortas."""
    if not a or not b:
        return False
    if a == b:
        return True
    sa, sb = _singularize_es(a), _singularize_es(b)
    if sa == sb:
        return True
    if len(sa) >= 4 and len(sb) >= 4 and (sa.startswith(sb) or sb.startswith(sa)):
        return True
    return False


def _token_in_text(token: str, text: str) -> bool:
    """Comprueba si un token de la consulta aparece en el texto normalizado."""
    words = text.split()
    if any(_tokens_match(token, w) for w in words):
        return True
    if len(token) >= 4:
        stem = _singularize_es(token)
        return any(
            _tokens_match(stem, w) or (len(w) >= 4 and w.startswith(stem[:4]))
            for w in words
        )
    return False


def _normalize(text: str, *, strip_noise: bool = False) -> str:
    text = _strip_accents(text.lower())
    text = re.sub(r"[^\w\s.,]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if strip_noise:
        text = " ".join(w for w in text.split() if w not in _NOISE_WORDS)
    return text


def _primary_tokens(name: str, *, strip_noise: bool = False) -> list[str]:
    tokens = _normalize(name, strip_noise=strip_noise).split()
    primary: list[str] = []
    for token in tokens:
        if token in _INGREDIENT_BREAK:
            break
        primary.append(token)
    return primary


def _query_tokens(query: str, *, strip_noise: bool = False) -> list[str]:
    return [t for t in _normalize(query, strip_noise=strip_noise).split() if t]


def _required_query_tokens(query: str, *, strip_noise: bool = False) -> list[str]:
    """
    Tokens obligatorios para relevancia.

    Palabras como 'estuche' o 'bandeja' son opcionales porque no todos los
    retailers las incluyen en el título (p. ej. PriceSmart: 'Arándanos 508 g').
    """
    tokens = _query_tokens(_name_part_query(query), strip_noise=strip_noise)
    if len(tokens) <= 1:
        return tokens
    required = [t for t in tokens if t not in _OPTIONAL_DESCRIPTOR_TOKENS]
    return required if required else tokens[:1]


def _name_part_query(query: str) -> str:
    """
    Quita peso/volumen de la consulta para homologación por nombre.

    Ej: "arandanos 500g" -> "arandanos". El peso se usa aparte (size_penalty).
    """
    cleaned = _QUERY_WEIGHT_RE.sub(" ", query)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or query.strip()


def search_query_variants(query: str) -> list[str]:
    """
    Genera variantes de búsqueda tolerantes a tildes, mayúsculas y plurales.

    Algunos retailers VTEX (p. ej. Jumbo) devuelven HTTP 400 con consultas de
  varias palabras; en esos casos conviene probar el término principal en singular.
    """
    variants: list[str] = []

    def add(value: str) -> None:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        if text and text not in variants:
            variants.append(text)

    raw = query.strip()
    name_part = _name_part_query(raw)
    add(raw)
    add(name_part)

    normalized = _normalize(name_part)
    add(normalized)

    tokens = [t for t in normalized.split() if t and t not in _NOISE_WORDS]
    if not tokens:
        return variants

    singular_tokens = [_singularize_es(t) for t in tokens]
    add(" ".join(singular_tokens))
    add(" ".join(tokens))

    # Primer token en singular: clave para Jumbo (ft=arandano vs ft=arandanos estuche).
    add(singular_tokens[0])
    add(tokens[0])

    if len(singular_tokens) > 1:
        add(singular_tokens[1])
    add(max(singular_tokens, key=len))

    return variants


def extract_size(text: str) -> Optional[tuple[str, float]]:
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


def is_relevant_candidate(
    query: str, candidate: str, *, category: Optional[str] = None
) -> bool:
    """
    Filtro duro de relevancia: descarta productos que solo comparten el término
    como sabor, ingrediente o categoría distinta a la intención del usuario.
    """
    name_query = _name_part_query(query)
    q_tokens = _required_query_tokens(name_query, strip_noise=False)
    if not q_tokens:
        return False

    # No quitar "de/con/y" aquí: se necesitan para detectar ingredientes secundarios.
    c_norm = _normalize(candidate, strip_noise=False)
    primary = _primary_tokens(candidate, strip_noise=False)

    if not all(_token_in_text(t, c_norm) for t in q_tokens):
        return False

    if len(q_tokens) == 1:
        qt = q_tokens[0]

        if re.search(rf"\b(con|y|de|en)\s+.*\b{re.escape(_singularize_es(qt))}", c_norm):
            if not (primary and _tokens_match(primary[0], qt)):
                return False

        if primary and primary[0] in _SECONDARY_HEAD:
            return False

        idx = next(
            (
                i
                for i, t in enumerate(primary)
                if _tokens_match(t, qt)
            ),
            -1,
        )
        if idx < 0:
            return c_norm.startswith(_singularize_es(qt)) or _token_in_text(qt, c_norm)

        tail = primary[idx + 1 :]
        if any(t in _SECONDARY_HEAD for t in tail):
            return False

        return idx <= 4

    if primary and primary[0] in _SECONDARY_HEAD and primary[0] not in q_tokens:
        return False

    return bool(primary and all(any(_tokens_match(t, p) for p in primary) for t in q_tokens)) or all(
        _token_in_text(t, " ".join(c_norm.split()[: max(3, len(q_tokens) + 1)])) for t in q_tokens
    )


def _relevance_adjustments(query: str, candidate: str, *, strip_noise: bool) -> float:
    q_norm = _normalize(query, strip_noise=strip_noise)
    c_norm = _normalize(candidate, strip_noise=strip_noise)
    q_tokens = q_norm.split()
    primary = _primary_tokens(candidate, strip_noise=strip_noise)
    delta = 0.0

    if q_norm == c_norm:
        return 30.0
    if primary and q_tokens and _tokens_match(primary[0], q_tokens[0]):
        delta += 15.0
    elif c_norm.startswith(q_norm):
        delta += 12.0
    if primary and q_tokens and all(any(_tokens_match(t, p) for p in primary) for t in q_tokens):
        delta += 8.0

    if primary and q_tokens and primary[0] in _SECONDARY_HEAD and primary[0] not in q_tokens:
        delta -= 35.0
    if primary and q_tokens and q_tokens[0] not in primary[:2] and any(t in primary[2:] for t in q_tokens):
        delta -= 20.0

    return delta


def resolve_threshold(category: Optional[str] = None) -> int:
    if category and category.strip().lower() == "fruver":
        return Config.MATCH_THRESHOLD_FRUVER
    return Config.MATCH_THRESHOLD


def similarity(query: str, candidate: str, *, category: Optional[str] = None) -> float:
    """
    Score 0-100. Compara el nombre del producto (sin peso en la consulta) y
    aplica penalización por diferencia de presentación usando el peso indicado.
    """
    is_fruver = bool(category and category.strip().lower() == "fruver")
    name_query = _name_part_query(query)
    q_norm = _normalize(name_query, strip_noise=is_fruver)
    c_norm = _normalize(candidate, strip_noise=is_fruver)
    q_tokens = q_norm.split()
    primary = _primary_tokens(candidate, strip_noise=is_fruver)
    primary_str = " ".join(primary)

    if len(q_tokens) <= 2:
        compare_str = primary_str or c_norm
        if q_tokens and primary:
            qt = q_tokens[0]
            if _tokens_match(primary[0], qt):
                compare_str = primary_str or c_norm
            else:
                idx = next((i for i, t in enumerate(primary) if _tokens_match(t, qt)), -1)
                if idx >= 0:
                    compare_str = " ".join(primary[idx : min(len(primary), idx + 3)])
        base = max(
            float(fuzz.ratio(q_norm, compare_str)),
            float(fuzz.partial_ratio(q_norm, c_norm)),
        )
    else:
        base = float(fuzz.token_set_ratio(q_norm, c_norm))

    base += _relevance_adjustments(name_query, candidate, strip_noise=is_fruver)
    penalty = _size_penalty(query, candidate)
    score = base * (1 - 0.35 * penalty)
    return round(min(100.0, max(0.0, score)), 1)


def _catalog_rank(candidate: MatchCandidate) -> int:
    try:
        return int(candidate.payload.get("catalog_rank", 999))
    except (TypeError, ValueError):
        return 999


def best_match(
    query: str,
    candidates: Sequence[MatchCandidate],
    threshold: int | None = None,
    *,
    category: Optional[str] = None,
) -> Optional[MatchResult]:
    ranked = filter_relevant_matches(query, candidates, category=category, threshold=threshold)
    return ranked[0] if ranked else None


def rank_matches(
    query: str, candidates: Sequence[MatchCandidate], *, category: Optional[str] = None
) -> list[MatchResult]:
    threshold = 0
    results: list[MatchResult] = []
    for candidate in candidates:
        if not is_relevant_candidate(query, candidate.name, category=category):
            continue
        results.append(MatchResult(candidate, similarity(query, candidate.name, category=category)))
    results.sort(key=lambda m: (-m.score, _catalog_rank(m.candidate)))
    return results


def filter_relevant_matches(
    query: str,
    candidates: Sequence[MatchCandidate],
    *,
    category: Optional[str] = None,
    threshold: int | None = None,
) -> list[MatchResult]:
    """Candidatos relevantes por encima del umbral, ordenados por score y ranking del retailer."""
    threshold = resolve_threshold(category) if threshold is None else threshold
    results: list[MatchResult] = []
    for candidate in candidates:
        if not is_relevant_candidate(query, candidate.name, category=category):
            continue
        score = similarity(query, candidate.name, category=category)
        if score >= threshold:
            results.append(MatchResult(candidate, score))
    results.sort(key=lambda m: (-m.score, _catalog_rank(m.candidate)))
    return results
