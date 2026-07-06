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

from services.matching import MatchCandidate, filter_relevant_matches, resolve_threshold


def _is_scannable_ean(ean: str) -> bool:
    """True solo para códigos de barras reales (no claves sintéticas N-...)."""
    value = str(ean or "").strip()
    if not value or value.startswith("N-"):
        return False
    return value.isdigit() and len(value) in (8, 12, 13, 14)


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
    presentation: Optional[str] = None
    image_url: Optional[str] = None
    url: Optional[str] = None
    match_mode: str = "ean"     # "ean" | "description"
    match_score: Optional[float] = None
    # Productos pesables (VTEX: measurementUnit=kg + unitMultiplier en kg).
    measurement_unit: Optional[str] = None
    unit_multiplier: Optional[float] = None
    is_weight_based: bool = False
    price_per_kg: Optional[int] = None
    promo_price_per_kg: Optional[int] = None
    error: Optional[str] = None
    not_found_message: Optional[str] = None
    # Listado completo de coincidencias rankeadas (búsqueda por descripción).
    matches: list[dict] = field(default_factory=list)
    # Ciudad usada para regionalizar la consulta (None = nacional/por defecto).
    city: Optional[str] = None

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
    def search(
        self,
        ean: str,
        description: Optional[str] = None,
        city: Optional[str] = None,
        category: Optional[str] = None,
    ) -> RetailerResult:
        """
        Busca un producto: primero por EAN, luego por descripción (fallback).

        `city` regionaliza la consulta cuando el motor lo soporta (VTEX).
        `category` ajusta el umbral/normalización de homologación (ver
        services/matching.py) — relevante sobre todo para "fruver".
        """
        try:
            result = None
            if _is_scannable_ean(ean):
                result = self._fetch_by_ean(ean, city=city)
            if result and result.found:
                result.city = result.city or city
                return result

            if description:
                homologated = self._search_by_description(description, city=city, category=category)
                if homologated:
                    homologated.city = homologated.city or city
                    if not homologated.found:
                        homologated.not_found_message = self._not_found_message()
                    return homologated

            empty = RetailerResult(retailer=self.key, retailer_name=self.name, found=False, city=city)
            if description:
                empty.not_found_message = self._not_found_message()
            return empty
        except Exception as exc:  # nunca tumbar la comparación por un retailer
            return RetailerResult(
                retailer=self.key,
                retailer_name=self.name,
                found=False,
                error=str(exc),
                city=city,
            )

    def _not_found_message(self) -> str:
        return f"Producto no encontrado en {self.name}"

    @staticmethod
    def _result_to_match_dict(result: RetailerResult, score: float) -> dict:
        return {
            "product_name": result.product_name,
            "price": result.price,
            "promo_price": result.promo_price,
            "presentation": result.presentation,
            "url": result.url,
            "image_url": result.image_url,
            "match_score": score,
        }

    def _search_by_description(
        self,
        description: str,
        city: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[RetailerResult]:
        """Homologación por descripción: devuelve el mejor match y el listado completo."""
        candidates = self._fetch_candidates(description, city=city)
        if not candidates:
            return RetailerResult(
                retailer=self.key,
                retailer_name=self.name,
                found=False,
                city=city,
                not_found_message=self._not_found_message(),
            )

        cand_list = [c for c, _ in candidates]
        relevant = filter_relevant_matches(description, cand_list, category=category)
        threshold = resolve_threshold(category)

        if not relevant:
            return RetailerResult(
                retailer=self.key,
                retailer_name=self.name,
                found=False,
                city=city,
                not_found_message=self._not_found_message(),
            )

        matches: list[dict] = []
        best_result: Optional[RetailerResult] = None

        for match in relevant:
            for cand, result in candidates:
                if cand is not match.candidate:
                    continue
                matches.append(self._result_to_match_dict(result, match.score))
                if best_result is None:
                    best_result = result
                    best_result.found = True
                    best_result.match_mode = "description"
                    best_result.match_score = match.score
                    best_result.matches = matches
                    best_result.city = city
                break

        if best_result is None:
            return RetailerResult(
                retailer=self.key,
                retailer_name=self.name,
                found=False,
                city=city,
                not_found_message=self._not_found_message(),
            )

        # Asegurar que matches refleja todos los relevantes (por si el loop falló parcialmente).
        if len(best_result.matches) != len(relevant):
            best_result.matches = matches

        # Descartar coincidencias claramente irrelevantes del listado mostrado.
        best_result.matches = [m for m in best_result.matches if (m.get("match_score") or 0) >= threshold]
        if not best_result.matches:
            return RetailerResult(
                retailer=self.key,
                retailer_name=self.name,
                found=False,
                city=city,
                not_found_message=self._not_found_message(),
            )
        return best_result

    # ── A implementar por subclases ────────────────────────────────────
    def _fetch_by_ean(self, ean: str, city: Optional[str] = None) -> Optional[RetailerResult]:
        raise NotImplementedError

    def _fetch_candidates(
        self, description: str, city: Optional[str] = None
    ) -> list[tuple[MatchCandidate, RetailerResult]]:
        """
        Devuelve candidatos (para homologar) como pares (MatchCandidate, RetailerResult).
        Por defecto, sin candidatos.
        """
        return []
