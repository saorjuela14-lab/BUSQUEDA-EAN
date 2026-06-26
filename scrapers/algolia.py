"""
Scraper para retailers cuyo buscador es Algolia.

Algolia expone una API de búsqueda JSON con claves públicas de cliente
(search-only), embebidas en el frontend del retailer. Esto permite scraping
rápido y confiable por EAN o descripción sin renderizar el navegador.

Aplica a Alkosto (índice `alkostoIndexAlgoliaPRD`). El mapeo de campos se
configura por subclase para adaptarse al esquema de cada índice.
"""
from __future__ import annotations

import json
from typing import Optional

import requests

from config import Config
from services.matching import MatchCandidate
from services.rounding import round_cop

from .base import BaseScraper, RetailerResult


class AlgoliaScraper(BaseScraper):
    """Scraper genérico basado en la API de búsqueda de Algolia."""

    # Credenciales públicas de cliente (search-only) y nombre del índice.
    app_id: str = ""
    api_key: str = ""
    index_name: str = ""

    # Mapeo de campos del índice -> concepto de negocio (sobrescribible).
    field_name: str = "name_text_es"
    field_code: str = "code_string"          # EAN
    field_price: str = "pricevalue_cop_double"
    field_base_price: str = "baseprice_cop_string"
    field_url: str = "url_es_string"
    field_stock: str = "instockflag_boolean"

    def _query(self, query: str, hits_per_page: int = 10) -> list[dict]:
        url = f"https://{self.app_id}-dsn.algolia.net/1/indexes/{self.index_name}/query"
        headers = {
            "X-Algolia-Application-Id": self.app_id,
            "X-Algolia-API-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": Config.USER_AGENT,
        }
        body = {"params": f"query={requests.utils.quote(str(query))}&hitsPerPage={hits_per_page}"}
        resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=Config.SCRAPER_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("hits", [])

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(str(value).replace("$", "").replace(".", "").replace(",", "").strip()) \
                if isinstance(value, str) and "$" in value else float(value)
        except (ValueError, TypeError):
            return None

    def _hit_to_result(self, hit: dict, *, found: bool = True) -> Optional[RetailerResult]:
        price = self._to_float(hit.get(self.field_price)) or self._to_float(hit.get("lowestprice_double"))
        base = self._to_float(hit.get(self.field_base_price))
        if not price and not base:
            return None

        # Modelar promoción: si el precio efectivo es menor al base => descuento.
        regular = round_cop(base) if base else round_cop(price)
        promo = None
        promo_desc = None
        if base and price and price < base:
            regular = round_cop(base)
            promo = round_cop(price)
            promo_desc = "Precio Alkosto"

        url = hit.get(self.field_url) or ""
        if url and url.startswith("/"):
            url = self.base_url + url

        return RetailerResult(
            retailer=self.key,
            retailer_name=self.name,
            found=found,
            price=regular,
            promo_price=promo,
            promo_desc=promo_desc,
            product_name=hit.get(self.field_name),
            url=url or None,
            match_mode="ean",
        )

    def _fetch_by_ean(self, ean: str) -> Optional[RetailerResult]:
        hits = self._query(ean, hits_per_page=5)
        if not hits:
            return RetailerResult(retailer=self.key, retailer_name=self.name, found=False)
        # Preferir el hit cuyo código coincide exactamente con el EAN.
        exact = next((h for h in hits if str(h.get(self.field_code)) == str(ean)), None)
        hit = exact or hits[0]
        if exact is None:
            return RetailerResult(retailer=self.key, retailer_name=self.name, found=False)
        return self._hit_to_result(hit)

    def _fetch_candidates(self, description: str) -> list[tuple[MatchCandidate, RetailerResult]]:
        out: list[tuple[MatchCandidate, RetailerResult]] = []
        for hit in self._query(description, hits_per_page=15):
            result = self._hit_to_result(hit, found=False)
            if result and result.product_name:
                out.append((MatchCandidate(name=result.product_name, payload={}), result))
        return out
