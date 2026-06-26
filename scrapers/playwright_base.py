"""
Scraper basado en Playwright para retailers con render dinámico (no-VTEX).

Aplica a sitios como Alkosto, PriceSmart, D1, Ara, Ísimo, donde el catálogo se
construye con JavaScript. Navega la página de búsqueda, espera el render y
extrae precios con BeautifulSoup.

Requisitos para uso real:
    pip install playwright
    playwright install chromium

Si Playwright no está disponible o el render falla, se lanza una excepción y el
retailer se reporta como no encontrado (con el detalle del error).
"""
from __future__ import annotations

import re
from typing import Optional

from config import Config
from services.matching import MatchCandidate
from services.rounding import round_cop

from .base import BaseScraper, RetailerResult

_PRICE_RE = re.compile(r"\$?\s*([\d.,]{3,})")


def _parse_price(text: str) -> Optional[int]:
    """Extrae un precio entero en COP desde un texto de góndola."""
    if not text:
        return None
    m = _PRICE_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    # Formato colombiano: '.' separa miles, ',' decimales. Quitamos ambos a entero.
    raw = raw.replace(".", "").replace(",", "")
    try:
        return round_cop(int(raw))
    except ValueError:
        return None


class PlaywrightScraper(BaseScraper):
    """
    Scraper genérico Playwright.

    Las subclases concretas pueden sobrescribir `search_path` y los selectores
    CSS (`card_selector`, `name_selector`, `price_selector`) para cada sitio.
    """

    search_path: str = "/search?q={query}"
    card_selector: str = "[data-testid='product-card'], .product-card, article"
    name_selector: str = "h3, h2, .product-title, [class*='name']"
    price_selector: str = "[class*='price'], .price, [data-price]"

    def _build_search_url(self, query: str) -> str:
        from urllib.parse import quote

        return self.base_url + self.search_path.format(query=quote(str(query)))

    def _render(self, url: str) -> str:
        """Renderiza la URL y devuelve el HTML resultante."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright no está instalado. Ejecute: pip install playwright && playwright install chromium"
            ) from exc

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=Config.SCRAPER_HEADLESS)
            try:
                page = browser.new_page(user_agent=Config.USER_AGENT)
                page.goto(url, timeout=Config.SCRAPER_TIMEOUT * 1000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)  # margen para render de precios
                return page.content()
            finally:
                browser.close()

    def _extract(self, html: str) -> list[tuple[str, Optional[int]]]:
        """Extrae pares (nombre, precio) de las tarjetas de producto del HTML."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        results: list[tuple[str, Optional[int]]] = []
        for card in soup.select(self.card_selector):
            name_el = card.select_one(self.name_selector)
            price_el = card.select_one(self.price_selector)
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            price = _parse_price(price_el.get_text(strip=True)) if price_el else None
            if name and price:
                results.append((name, price))
        return results

    def _fetch_by_ean(self, ean: str) -> Optional[RetailerResult]:
        html = self._render(self._build_search_url(ean))
        items = self._extract(html)
        if not items:
            return RetailerResult(retailer=self.key, retailer_name=self.name, found=False)
        name, price = items[0]
        return RetailerResult(
            retailer=self.key,
            retailer_name=self.name,
            found=True,
            price=price,
            product_name=name,
            url=self._build_search_url(ean),
            match_mode="ean",
        )

    def _fetch_candidates(self, description: str) -> list[tuple[MatchCandidate, RetailerResult]]:
        html = self._render(self._build_search_url(description))
        out: list[tuple[MatchCandidate, RetailerResult]] = []
        for name, price in self._extract(html):
            result = RetailerResult(
                retailer=self.key,
                retailer_name=self.name,
                found=False,
                price=price,
                product_name=name,
                url=self._build_search_url(description),
            )
            out.append((MatchCandidate(name=name, payload={}), result))
        return out
