"""
Scraper para PriceSmart Colombia vía API pública Bloomreach Discovery.

El buscador del sitio consume `getProductsByKeyword` con credenciales públicas
de cliente. No requiere Playwright ni sesión de socio para precios.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

import requests

from config import Config
from services.matching import MatchCandidate
from services.rounding import round_cop

from .base import BaseScraper, RetailerResult

_API_URL = "https://www.pricesmart.com/api/br_discovery/getProductsByKeyword"
_ACCOUNT_ID = "7024"
_AUTH_KEY = "ev7libhybjg5h1d1"
_DOMAIN_KEY = "pricesmart_bloomreach_io_es"
_VIEW_ID = "CO"
_FIELDS = (
    "pid,title,thumb_image,sign_price_CO,price_per_uom_CO,uom_description_CO,brand,slug"
)


class PriceSmartScraper(BaseScraper):
    """PriceSmart Colombia (Bloomreach Discovery API)."""

    def _search_payload(self, query: str, rows: int = 24) -> list[dict]:
        encoded = quote(str(query))
        return [
            {
                "url": f"https://www.pricesmart.com/es-co/busqueda?q={encoded}",
                "start": 0,
                "q": str(query),
                "search_type": "keyword",
                "rows": rows,
                "account_id": _ACCOUNT_ID,
                "auth_key": _AUTH_KEY,
                "domain_key": _DOMAIN_KEY,
                "view_id": _VIEW_ID,
                "fl": _FIELDS,
            }
        ]

    def _query(self, query: str, rows: int = 24) -> list[dict]:
        resp = requests.post(
            _API_URL,
            json=self._search_payload(query, rows=rows),
            headers={"User-Agent": Config.USER_AGENT, "Accept": "application/json"},
            timeout=Config.SCRAPER_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("response", {}).get("docs", []) or []

    @staticmethod
    def _parse_price_cop(raw) -> Optional[int]:
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        # sign_price_CO viene en centavos (ej. 990000 -> $9.900 COP).
        return round_cop(int(round(value / 100)))

    def _doc_to_result(self, doc: dict, *, found: bool = True) -> Optional[RetailerResult]:
        price = self._parse_price_cop(doc.get("sign_price_CO"))
        if price is None:
            return None

        slug = doc.get("slug") or ""
        pid = doc.get("pid") or ""
        url = f"https://www.pricesmart.com/es-co/producto/{slug}/{pid}" if slug and pid else None

        uom = doc.get("uom_description_CO")
        per_uom = doc.get("price_per_uom_CO")
        presentation = None
        if uom and per_uom is not None:
            presentation = f"${per_uom}/{uom}"

        return RetailerResult(
            retailer=self.key,
            retailer_name=self.name,
            found=found,
            price=price,
            product_name=doc.get("title"),
            presentation=presentation,
            image_url=doc.get("thumb_image"),
            url=url,
            match_mode="ean",
        )

    def _fetch_by_ean(self, ean: str, city: Optional[str] = None) -> Optional[RetailerResult]:
        docs = self._query(ean, rows=5)
        if not docs:
            return RetailerResult(retailer=self.key, retailer_name=self.name, found=False, city=city)
        result = self._doc_to_result(docs[0])
        if result:
            result.city = city
        return result

    def _fetch_candidates(
        self, description: str, city: Optional[str] = None
    ) -> list[tuple[MatchCandidate, RetailerResult]]:
        out: list[tuple[MatchCandidate, RetailerResult]] = []
        for rank, doc in enumerate(self._query(description, rows=24)):
            result = self._doc_to_result(doc, found=False)
            if result and result.product_name:
                result.city = city
                out.append(
                    (
                        MatchCandidate(
                            name=result.product_name,
                            payload={"catalog_rank": rank},
                        ),
                        result,
                    )
                )
        return out
