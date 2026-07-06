"""
Scraper para la tienda online de Makro Colombia (tienda.makro.com.co).

La plataforma Instaleap/Next.js no expone una API pública de búsqueda estable;
se usa Playwright para renderizar resultados y extraer tarjetas del DOM.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

from config import Config
from services.matching import MatchCandidate
from services.rounding import round_cop

from .base import BaseScraper, RetailerResult

_PRICE_LINE_RE = re.compile(r"^\$[\d.,]+$")
_PROMO_LINE_RE = re.compile(r"^\(\$[\d.,]+\)$")
_PRESENTATION_RE = re.compile(r"\b\d+\s*(?:g|kg|ml|l|lt|u|und)\b.*\ba\s*\$", re.IGNORECASE)


def _parse_cop_price(text: str) -> Optional[int]:
    if not text:
        return None
    raw = text.strip().lstrip("$").strip("()")
    raw = raw.replace(".", "").replace(",", "")
    try:
        return round_cop(int(raw))
    except ValueError:
        return None


def _parse_makro_body(text: str) -> list[dict]:
    """Extrae productos del texto visible de la página de resultados."""
    if "No Products Found" in text or "No se encontr" in text:
        return []

    products: list[dict] = []
    for chunk in text.split("Agregar")[:-1]:
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        if not lines:
            continue

        prices = [line for line in lines if _PRICE_LINE_RE.match(line)]
        promos = [line for line in lines if _PROMO_LINE_RE.match(line)]
        if not prices:
            continue

        current = _parse_cop_price(prices[0])
        list_price = _parse_cop_price(promos[0]) if promos else None
        if current is None:
            continue

        presentation = next((line for line in lines if _PRESENTATION_RE.search(line)), None)

        name = None
        for line in reversed(lines):
            if _PRICE_LINE_RE.match(line) or _PROMO_LINE_RE.match(line):
                continue
            if _PRESENTATION_RE.search(line):
                continue
            if line.startswith("Resultados") or line.startswith("Ordenar"):
                continue
            if re.fullmatch(r"\(\d+\)", line):
                continue
            name = line
            break

        if not name:
            continue

        promo_price = None
        regular_price = current
        if list_price and list_price > current:
            regular_price = list_price
            promo_price = current

        products.append(
            {
                "product_name": name,
                "price": regular_price,
                "promo_price": promo_price,
                "presentation": presentation,
            }
        )
    return products


class MakroTiendaScraper(BaseScraper):
    """Makro tienda online (tienda.makro.com.co)."""

    def _not_found_message(self) -> str:
        return "Producto no encontrado en Makro"

    def _render_search(self, query: str) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright no está instalado. Ejecute: pip install playwright && playwright install chromium"
            ) from exc

        search_url = f"{self.base_url}/search?name={quote(str(query))}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=Config.SCRAPER_HEADLESS)
            try:
                page = browser.new_page(user_agent=Config.USER_AGENT)
                # Visitar home primero para fijar tienda por defecto (Av. Boyacá).
                page.goto(self.base_url, timeout=Config.SCRAPER_TIMEOUT * 1000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                page.goto(search_url, timeout=Config.SCRAPER_TIMEOUT * 1000, wait_until="domcontentloaded")
                page.wait_for_timeout(3500)
                return page.inner_text("body")
            finally:
                browser.close()

    def _items_from_query(self, query: str) -> list[dict]:
        body = self._render_search(query)
        return _parse_makro_body(body)

    def _item_to_result(self, item: dict, *, found: bool, query: str, city: Optional[str]) -> RetailerResult:
        return RetailerResult(
            retailer=self.key,
            retailer_name=self.name,
            found=found,
            price=item.get("price"),
            promo_price=item.get("promo_price"),
            product_name=item.get("product_name"),
            presentation=item.get("presentation"),
            url=f"{self.base_url}/search?name={quote(str(query))}",
            match_mode="ean",
            city=city,
        )

    def _fetch_by_ean(self, ean: str, city: Optional[str] = None) -> Optional[RetailerResult]:
        items = self._items_from_query(ean)
        if not items:
            return RetailerResult(retailer=self.key, retailer_name=self.name, found=False, city=city)
        return self._item_to_result(items[0], found=True, query=ean, city=city)

    def _fetch_candidates(
        self, description: str, city: Optional[str] = None
    ) -> list[tuple[MatchCandidate, RetailerResult]]:
        out: list[tuple[MatchCandidate, RetailerResult]] = []
        for item in self._items_from_query(description):
            name = item.get("product_name")
            if not name:
                continue
            result = self._item_to_result(item, found=False, query=description, city=city)
            out.append((MatchCandidate(name=name, payload={}), result))
        return out
