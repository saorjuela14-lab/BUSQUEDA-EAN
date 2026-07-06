"""Utilidades compartidas para scrapers basados en Playwright."""
from __future__ import annotations

from config import Config


def launch_chromium(playwright):
    """Lanza Chromium con mensaje claro si el binario no está instalado."""
    try:
        return playwright.chromium.launch(headless=Config.SCRAPER_HEADLESS)
    except Exception as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "browserType.launch" in message:
            raise RuntimeError(
                "Playwright Chromium no está instalado en el servidor. "
                "En despliegue use la imagen Docker del proyecto o ejecute: "
                "python -m playwright install chromium"
            ) from exc
        raise
