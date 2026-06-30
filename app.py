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

import hashlib
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
)
from database import init_db, repository
from export import export_report
from services import bulk, pricing_service
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
    """Devuelve categorías, subcategorías y retailers para poblar la UI."""
    return jsonify(
        {
            "categories": CATEGORIES,
            "subcategories": SUBCATEGORIES,
            "retailers": RETAILERS,
            "home_retailer": HOME_RETAILER,
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
    en cada ecommerce. Internamente usa una clave sintética estable derivada del
    nombre para poder persistir el histórico sin colisionar con EAN reales.

    Body JSON: { name, cost?, category?, target_margin?, weight?, weight_unit? }
    """
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "El campo 'name' es obligatorio."}), 400

    weight_g = parse_weight(data.get("weight"), data.get("weight_unit", "g"))
    search_description = name
    if weight_g:
        search_description = f"{name} {format_weight_for_query(weight_g)}"

    try:
        report = pricing_service.run_query(
            _name_key(name, weight_g),
            cost=_int_or_none(data.get("cost")),
            description=search_description,
            category=data.get("category") or None,
            target_margin=_float_or_none(data.get("target_margin")),
            target_weight_g=weight_g,
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
    return jsonify(repository.get_history(ean=ean, limit=int(request.args.get("limit", 100))))


@app.get("/api/history/<int:query_id>")
def api_history_detail(query_id: int):
    detail = repository.get_query_detail(query_id)
    if not detail:
        return jsonify({"error": "Consulta no encontrada."}), 404
    return jsonify(detail)


@app.get("/api/trend/<ean>")
def api_trend(ean: str):
    return jsonify(repository.get_price_trend(ean))


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
    """Procesa un Excel de carga masiva (campo de formulario 'file')."""
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
        result = bulk.process_bulk_file(str(save_path), target_margin=target_margin)
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error en /api/bulk")
        return jsonify({"error": str(exc)}), 500


# ──────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────
def _name_key(name: str, weight_g: float | None = None) -> str:
    """
    Deriva una clave sintética estable a partir del nombre del producto.

    Permite usar el flujo de consulta (basado en EAN) cuando solo se dispone del
    nombre: el mismo nombre genera siempre la misma clave, de modo que el
    histórico se acumula correctamente sin chocar con EAN reales. Cabe en
    String(20) del modelo Product.

    Si se indica peso, se incluye en la clave para separar consultas por cantidad.
    """
    key = name.strip().lower()
    if weight_g and weight_g > 0:
        key += f"|{int(round(weight_g))}g"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"N-{digest}"


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
