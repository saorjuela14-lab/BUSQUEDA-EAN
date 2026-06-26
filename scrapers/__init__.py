"""Capa de scrapers: obtención de precios por retailer."""
from .base import BaseScraper, RetailerResult
from .registry import get_scraper, get_scrapers, scrape_all

__all__ = [
    "BaseScraper",
    "RetailerResult",
    "get_scraper",
    "get_scrapers",
    "scrape_all",
]
