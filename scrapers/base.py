"""
Contrato base para todos los scrapers de retailers.

Cada scraper implementa la búsqueda por EAN y, como fallback, la búsqueda por
descripción (homologación). El resultado se normaliza en `RetailerResult`.

Diseño:
- `search(ean, description)` orquesta: intenta por EAN; si no encuentra y hay
  descripción, intenta homologar por texto.
- Las subclases implementan `_fetch_by_ean` y `_fetch_candidates`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from services.matching import MatchCandidate, best_match


@dataclass
class RetailerResult:
    """Resultado normalizado de un retailer para un producto."""

    retailer: str               # clave interna del retailer
    retailer_name: str          # nombre visible
    found: bool = False
    price: Optional[int] = None
    promo_price: Optional[int] = None
    promo_desc: Optional[str] = None
    product_name: Optional[str] = None
    url: Optional[str] = None
    match_mode: str = "ean"     # "ean" | "description"
    match_score: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class BaseScraper:
    """Clase base abstracta de scraper de retailer."""

    #: clave interna y metadatos (se inyectan al instanciar desde el registry).
    key: str = ""
    name: str = ""
    base_url: str = ""

    def __init__(self, key: str, name: str, base_url: str):
        self.key = key
        self.name = name
        self.base_url = base_url

    # ── API pública ────────────────────────────────────────────────────
    def search(self, ean: str, description: Optional[str] = None) -> RetailerResult:
        """
        Busca un producto: primero por EAN, luego por descripción (fallback).
        """
        try:
            result = self._fetch_by_ean(ean)
            if result and result.found:
                return result

            if description:
                homologated = self._search_by_description(description)
                if homologated and homologated.found:
                    return homologated

            return RetailerResult(retailer=self.key, retailer_name=self.name, found=False)
        except Exception as exc:  # nunca tumbar la comparación por un retailer
            return RetailerResult(
                retailer=self.key,
                retailer_name=self.name,
                found=False,
                error=str(exc),
            )

    def _search_by_description(self, description: str) -> Optional[RetailerResult]:
        """Homologación por descripción usando rapidfuzz sobre candidatos."""
        candidates = self._fetch_candidates(description)
        if not candidates:
            return None
        match = best_match(description, [c for c, _ in candidates])
        if not match:
            return None
        # Recuperar el RetailerResult asociado al candidato ganador.
        for cand, result in candidates:
            if cand is match.candidate:
                result.found = True
                result.match_mode = "description"
                result.match_score = match.score
                return result
        return None

    # ── A implementar por subclases ────────────────────────────────────
    def _fetch_by_ean(self, ean: str) -> Optional[RetailerResult]:
        raise NotImplementedError

    def _fetch_candidates(self, description: str) -> list[tuple[MatchCandidate, RetailerResult]]:
        """
        Devuelve candidatos (para homologar) como pares (MatchCandidate, RetailerResult).
        Por defecto, sin candidatos.
        """
        return []
