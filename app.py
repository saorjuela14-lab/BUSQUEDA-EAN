"""
Retail Price Intelligence Colombia — Aplicación Flask.

Punto de entrada único de la plataforma. Expone:
  - El dashboard web (frontend).
  - Una API REST para consulta de precios, históricos, dashboard, alertas,
    exportación a Excel y carga masiva.

Ejecutar con:
    pip install -r requirements.txt
    python app.py
"""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import (
    CATEGORIES,
    HOME_RETAILER,
    LOGS_DIR,
    RETAILERS,
    STATIC_DIR,
    SUBCATEGORIES,
    TEMPLATES_DIR,
    UPLOADS_DIR,
    Config,
    active_stores,
)
from database import init_db, repository
from export import export_report
from services import bulk, catalog_import, pricing_service
from services.keys import synthetic_key
from services.weight import format_weight_for_query, format_weight_label, parse_weight

# ──────────────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("app")

# ──────────────────────────────────────────────────────────────────────────
# APP FACTORY
# ──────────────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
)
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB para cargas masivas
CORS(app)

# Inicializar base de datos al arrancar.
init_db()


# ──────────────────────────────────────────────────────────────────────────
# FRONTEND
# ──────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    """Sirve el dashboard principal."""
    return render_template("index.html")


# ──────────────────────────────────────────────────────────────────────────
# API: METADATOS
# ──────────────────────────────────────────────────────────────────────────
@app.get("/api/config")
def api_config():
    """Devuelve categorías, subcategorías, retailers y tiendas Makro para poblar la UI."""
    return jsonify(
        {
            "categories": CATEGORIES,
            "subcategories": SUBCATEGORIES,
            "retailers": RETAILERS,
            "home_retailer": HOME_RETAILER,
            "stores": active_stores(),
        }
    )


# ──────────────────────────────────────────────────────────────────────────
# API: CONSULTA INDIVIDUAL
# ──────────────────────────────────────────────────────────────────────────
@app.post("/api/search")
def api_search():
    """
    Ejecuta una consulta de comparación de precios.

    Body JSON: { ean, cost?, description?, category?, target_margin?, priority? }
    """
    data = request.get_json(silent=True) or {}
    ean = str(data.get("ean", "")).strip()
    if not ean:
        return jsonify({"error": "El campo 'ean' es obligatorio."}), 400

    try:
        report = pricing_service.run_query(
            ean,
            cost=_int_or_none(data.get("cost")),
            description=data.get("description") or None,
            category=data.get("category") or None,
            target_margin=_float_or_none(data.get("target_margin")),
            priority=_int_or_none(data.get("priority")),
            city=(data.get("city") or None),
        )
        report["search_mode"] = "ean"
        return jsonify(report)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error en /api/search")
        return jsonify({"error": str(exc)}), 500


# ──────────────────────────────────────────────────────────────────────────
# API: CONSULTA POR NOMBRE (independiente del EAN)
# ──────────────────────────────────────────────────────────────────────────
@app.post("/api/search-name")
def api_search_name():
    """
    Ejecuta una consulta de comparación buscando SOLO por nombre del producto.

    Pensado para cuando no se tiene el EAN: homologa el producto por descripción
    en cada ecommerce (típico en Fruver a granel). Internamente usa una clave
    sintética estable derivada del nombre para poder persistir el histórico
    sin colisionar con EAN reales.

    Body JSON: { name, cost?, category?, target_margin?, weight?, weight_unit?,
                 city?, cities? }

    - `city`: una sola ciudad o código de tienda (ej. "Bogotá" o 18) para
      regionalizar la búsqueda.
    - `cities`: lista de ciudades/tiendas (ej. ["Bogotá","Medellín"] o [1,5,18])
      para comparar el mismo producto en varias ubicaciones a la vez (ver
      config.STORES). Si se envía `cities`, tiene prioridad sobre `city` y la respuesta incluye un
      informe por ciudad más una tabla comparativa.
    """
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "El campo 'name' es obligatorio."}), 400

    weight_g = parse_weight(data.get("weight"), data.get("weight_unit", "g"))
    # VTEX y otros buscadores fallan con sufijos de peso en la query (ej. "500g").
    # Se consulta solo por nombre; el peso se usa para homologar y normalizar precios.
    search_description = name
    match_description = name
    if weight_g:
        match_description = f"{name} {format_weight_for_query(weight_g)}"

    cities = data.get("cities")
    try:
        if cities:
            report = pricing_service.run_query_multi_city(
                synthetic_key(name, weight_g),
                cities=[str(c).strip() for c in cities],
                cost=_int_or_none(data.get("cost")),
                description=search_description,
                match_description=match_description,
                category=data.get("category") or None,
                target_margin=_float_or_none(data.get("target_margin")),
                target_weight_g=weight_g,
            )
            report["search_mode"] = "name_multi_city"
            report["search_name"] = name
            if weight_g:
                report["weight_label"] = format_weight_label(weight_g)
            return jsonify(report)

        report = pricing_service.run_query(
            synthetic_key(name, weight_g),
            cost=_int_or_none(data.get("cost")),
            description=search_description,
            match_description=match_description,
            category=data.get("category") or None,
            target_margin=_float_or_none(data.get("target_margin")),
            target_weight_g=weight_g,
            city=(data.get("city") or None),
        )
        report["search_mode"] = "name"
        report["search_name"] = name
        if weight_g:
            report["weight_label"] = format_weight_label(weight_g)
        return jsonify(report)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error en /api/search-name")
        return jsonify({"error": str(exc)}), 500


# ──────────────────────────────────────────────────────────────────────────
# API: HISTÓRICO Y TENDENCIAS
# ──────────────────────────────────────────────────────────────────────────
@app.get("/api/history")
def api_history():
    ean = request.args.get("ean")
    city = request.args.get("city")
    return jsonify(
        repository.get_history(ean=ean, city=city, limit=int(request.args.get("limit", 100)))
    )


@app.get("/api/history/<int:query_id>")
def api_history_detail(query_id: int):
    detail = repository.get_query_detail(query_id)
    if not detail:
        return jsonify({"error": "Consulta no encontrada."}), 404
    return jsonify(detail)


@app.get("/api/trend/<ean>")
def api_trend(ean: str):
    city = request.args.get("city")
    return jsonify(repository.get_price_trend(ean, city=city))


# ──────────────────────────────────────────────────────────────────────────
# API: DASHBOARD Y ALERTAS
# ──────────────────────────────────────────────────────────────────────────
@app.get("/api/dashboard")
def api_dashboard():
    return jsonify(repository.dashboard_metrics())


@app.get("/api/alerts")
def api_alerts():
    return jsonify(repository.list_alerts(limit=int(request.args.get("limit", 100))))


@app.get("/api/products")
def api_products():
    return jsonify(repository.list_products(category=request.args.get("category")))


# ──────────────────────────────────────────────────────────────────────────
# API: CATÁLOGO MAKRO (nombre, EAN, PVP)
# ──────────────────────────────────────────────────────────────────────────
@app.get("/api/catalog/stats")
def api_catalog_stats():
    """Estadísticas del catálogo Makro importado."""
    return jsonify(repository.catalog_stats())


@app.post("/api/catalog/import")
def api_catalog_import():
    """
    Importa catálogo Makro desde Excel/CSV.

    Columnas requeridas: EAN, Nombre, PVP.
    Opcionales: Categoría, Costo.
    """
    if "file" not in request.files:
        return jsonify({"error": "Adjunte un archivo en el campo 'file'."}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Archivo sin nombre."}), 400

    filename = secure_filename(file.filename)
    save_path = UPLOADS_DIR / f"catalog_{filename}"
    file.save(save_path)

    try:
        result = catalog_import.process_catalog_file(str(save_path))
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error en /api/catalog/import")
        return jsonify({"error": str(exc)}), 500


# ──────────────────────────────────────────────────────────────────────────
# API: EXPORTACIÓN EXCEL
# ──────────────────────────────────────────────────────────────────────────
@app.post("/api/export")
def api_export():
    """
    Genera un Excel corporativo. Re-ejecuta la consulta (sin persistir) con los
    mismos parámetros para construir un reporte completo y lo descarga.
    """
    data = request.get_json(silent=True) or {}
    ean = str(data.get("ean", "")).strip()
    if not ean:
        return jsonify({"error": "El campo 'ean' es obligatorio."}), 400
    try:
        report = pricing_service.run_query(
            ean,
            cost=_int_or_none(data.get("cost")),
            description=data.get("description") or None,
            category=data.get("category") or None,
            target_margin=_float_or_none(data.get("target_margin")),
            priority=_int_or_none(data.get("priority")),
            city=(data.get("city") or None),
            persist=False,
        )
        path = export_report(report)
        return send_file(path, as_attachment=True, download_name=path.name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error en /api/export")
        return jsonify({"error": str(exc)}), 500


# ──────────────────────────────────────────────────────────────────────────
# API: CARGA MASIVA
# ──────────────────────────────────────────────────────────────────────────
@app.post("/api/bulk")
def api_bulk():
    """
    Procesa un Excel de carga masiva (campo de formulario 'file').

    Acepta filas con EAN real, o sin EAN si traen 'descripcion'/'nombre'
    (caso Fruver a granel: usa homologación por nombre, ver services/bulk.py).

    Campos de formulario opcionales:
      - target_margin: margen objetivo por defecto (si la fila no trae uno propio).
      - cities: ciudades o códigos de tienda separados por coma (ej.
        "Bogotá,Medellín,Cali" o "1,5,18") para correr
        CADA fila en cada una de esas ciudades. Se ignora si el Excel ya
        trae una columna 'Ciudad' propia (esa manda).
    """
    if "file" not in request.files:
        return jsonify({"error": "Adjunte un archivo en el campo 'file'."}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Archivo sin nombre."}), 400

    filename = secure_filename(file.filename)
    save_path = UPLOADS_DIR / filename
    file.save(save_path)

    try:
        target_margin = _float_or_none(request.form.get("target_margin"))
        cities_raw = (request.form.get("cities") or "").strip()
        cities = [c.strip() for c in cities_raw.split(",") if c.strip()] or None
        result = bulk.process_bulk_file(
            str(save_path), target_margin=target_margin, cities=cities
        )
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error en /api/bulk")
        return jsonify({"error": str(exc)}), 500


# ──────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────
def _int_or_none(value):
    try:
        return int(float(value)) if value not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _float_or_none(value):
    try:
        return float(value) if value not in (None, "") else None
    except (ValueError, TypeError):
        return None


@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Recurso no encontrado."}), 404


if __name__ == "__main__":
    logger.info("Iniciando Retail Price Intelligence Colombia en %s:%s", Config.HOST, Config.PORT)
    logger.info("Modo scraping: REAL (VTEX + Playwright)")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
