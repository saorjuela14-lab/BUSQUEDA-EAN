"""
Scraper para retailers sobre plataforma VTEX.

La mayoría de los grandes retailers colombianos (Éxito, Carulla, Jumbo, Metro,
Makro, Olímpica, Farmatodo) usan VTEX, que expone una API pública de catálogo
en JSON. Esto permite scraping rápido y confiable sin renderizar el navegador.

Endpoints usados:
  - Por EAN: /api/catalog_system/pub/products/search?fq=alternateIds_Ean:{ean}
  - Por texto: /api/catalog_system/pub/products/search?ft={query}

Si la red falla, el retailer se reporta como no encontrado con el error.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

import requests

from config import Config
from services.matching import MatchCandidate
from services.rounding import round_cop

from .base import BaseScraper, RetailerResult


class VtexScraper(BaseScraper):
    """Scraper genérico para tiendas VTEX."""

    def _session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({"User-Agent": Config.USER_AGENT, "Accept": "application/json"})
        return s

    def _best_offer(self, product: dict) -> Optional[dict]:
        """
        Recorre items/sellers y devuelve la mejor oferta disponible.

        Prioriza ofertas disponibles (IsAvailable) y, entre ellas, el menor
        precio efectivo. Esto cubre el caso de múltiples sellers/presentaciones.
        """
        best = None
        for item in product.get("items") or []:
            for seller in item.get("sellers") or []:
                offer = seller.get("commertialOffer") or {}
                price = offer.get("Price")
                if not price:
                    continue
                available = offer.get("IsAvailable", True)
                key = (0 if available else 1, price)  # disponibles primero, luego menor precio
                if best is None or key < best[0]:
                    best = (key, offer)
        return best[1] if best else None

    def _parse_product(self, product: dict) -> Optional[RetailerResult]:
        """Convierte un producto VTEX en RetailerResult (mejor oferta disponible)."""
        offer = self._best_offer(product)
        if not offer:
            return None
        price = offer.get("Price")
        list_price = offer.get("ListPrice") or offer.get("PriceWithoutDiscount")

        promo_price = None
        promo_desc = None
        # Si hay descuento (ListPrice > Price) se modela como promoción.
        if list_price and list_price > price:
            promo_price = round_cop(price)
            price_regular = round_cop(list_price)
            teasers = offer.get("Teasers") or []
            promo_desc = teasers[0].get("name") if teasers else "Precio con descuento"
        else:
            price_regular = round_cop(price)

        return RetailerResult(
            retailer=self.key,
            retailer_name=self.name,
            found=True,
            price=price_regular,
            promo_price=promo_price,
            promo_desc=promo_desc,
            product_name=product.get("productName"),
            url=product.get("link") or product.get("linkText"),
            match_mode="ean",
        )

    def _fetch_by_ean(self, ean: str) -> Optional[RetailerResult]:
        url = f"{self.base_url}/api/catalog_system/pub/products/search"
        params = {"fq": f"alternateIds_Ean:{ean}"}
        resp = self._session().get(url, params=params, timeout=Config.SCRAPER_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return RetailerResult(retailer=self.key, retailer_name=self.name, found=False)
        return self._parse_product(data[0])

    def _fetch_candidates(self, description: str) -> list[tuple[MatchCandidate, RetailerResult]]:
        url = f"{self.base_url}/api/catalog_system/pub/products/search"
        params = {"ft": quote(description), "_from": 0, "_to": 19}
        resp = self._session().get(url, params=params, timeout=Config.SCRAPER_TIMEOUT)
        resp.raise_for_status()
        data = resp.json() or []
        out: list[tuple[MatchCandidate, RetailerResult]] = []
        for product in data:
            result = self._parse_product(product)
            if result and result.product_name:
                result.found = False  # se marcará found tras homologar
                out.append(
                    (MatchCandidate(name=result.product_name, payload={}), result)
                )
        return out
