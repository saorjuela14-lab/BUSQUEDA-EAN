"""
Repositorio: operaciones CRUD y consultas históricas sobre la base de datos.

Aísla a la capa de servicios de los detalles de SQLAlchemy, facilitando
pruebas y futura migración de motor.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import desc, func, select

from .db import get_session
from .models import Alert, PriceQuery, PriceResult, Product


# ──────────────────────────────────────────────────────────────────────────
# PRODUCTOS
# ──────────────────────────────────────────────────────────────────────────
def upsert_product(
    ean: str,
    name: str,
    category: str,
    *,
    brand: str | None = None,
    subcategory: str | None = None,
    cost: int | None = None,
) -> dict:
    """Crea o actualiza un producto por EAN y devuelve su representación."""
    with get_session() as s:
        product = s.scalar(select(Product).where(Product.ean == ean))
        if product is None:
            product = Product(ean=ean, name=name, category=category)
            s.add(product)
        product.name = name or product.name
        product.category = category or product.category
        if brand is not None:
            product.brand = brand
        if subcategory is not None:
            product.subcategory = subcategory
        if cost is not None:
            product.cost = cost
        s.flush()
        return product.to_dict()


def get_product_by_ean(ean: str) -> Optional[dict]:
    with get_session() as s:
        product = s.scalar(select(Product).where(Product.ean == ean))
        return product.to_dict() if product else None


def list_products(category: str | None = None) -> list[dict]:
    with get_session() as s:
        stmt = select(Product)
        if category:
            stmt = stmt.where(Product.category == category)
        stmt = stmt.order_by(Product.name)
        return [p.to_dict() for p in s.scalars(stmt).all()]


def search_products_by_text(text: str, limit: int = 50) -> list[dict]:
    """Búsqueda simple por substring (homologación usa rapidfuzz aparte)."""
    like = f"%{text.strip()}%"
    with get_session() as s:
        stmt = (
            select(Product)
            .where(Product.name.ilike(like))
            .order_by(Product.name)
            .limit(limit)
        )
        return [p.to_dict() for p in s.scalars(stmt).all()]


# ──────────────────────────────────────────────────────────────────────────
# CONSULTAS / HISTÓRICO
# ──────────────────────────────────────────────────────────────────────────
def save_query(payload: dict) -> dict:
    """
    Persiste una consulta completa: cabecera + resultados + alertas.

    `payload` espera las claves: ean, cost, match_mode, kpis, results, alerts.
    Devuelve el diccionario de la consulta guardada (con id).
    """
    with get_session() as s:
        product = s.scalar(select(Product).where(Product.ean == payload["ean"]))
        if product is None:
            product = Product(
                ean=payload["ean"],
                name=payload.get("product_name") or payload["ean"],
                category=payload.get("category") or "bakery",
            )
            s.add(product)
            s.flush()
        if payload.get("cost") is not None:
            product.cost = payload["cost"]

        kpis = payload.get("kpis", {})
        query = PriceQuery(
            product_id=product.id,
            ean=payload["ean"],
            cost=payload.get("cost"),
            match_mode=payload.get("match_mode", "ean"),
            min_price=kpis.get("min_price"),
            max_price=kpis.get("max_price"),
            avg_price=kpis.get("avg_price"),
            spread=kpis.get("spread"),
            leader_retailer=kpis.get("leader_retailer"),
            most_expensive_retailer=kpis.get("most_expensive_retailer"),
            avg_margin_pct=kpis.get("avg_margin_pct"),
        )
        s.add(query)
        s.flush()

        for r in payload.get("results", []):
            s.add(
                PriceResult(
                    query_id=query.id,
                    retailer=r.get("retailer"),
                    found=bool(r.get("found")),
                    price=r.get("price"),
                    promo_price=r.get("promo_price"),
                    promo_desc=r.get("promo_desc"),
                    product_name=r.get("product_name"),
                    url=r.get("url"),
                    match_score=r.get("match_score"),
                )
            )

        for a in payload.get("alerts", []):
            s.add(
                Alert(
                    query_id=query.id,
                    ean=payload["ean"],
                    level=a.get("level", "info"),
                    type=a.get("type", "info"),
                    message=a.get("message", ""),
                    retailer=a.get("retailer"),
                )
            )

        s.flush()
        result = query.to_dict()
        result["id"] = query.id
        return result


def get_history(ean: str | None = None, limit: int = 100) -> list[dict]:
    """Devuelve el histórico de consultas, opcionalmente filtrado por EAN."""
    with get_session() as s:
        stmt = select(PriceQuery).order_by(desc(PriceQuery.created_at)).limit(limit)
        if ean:
            stmt = select(PriceQuery).where(PriceQuery.ean == ean).order_by(
                desc(PriceQuery.created_at)
            ).limit(limit)
        rows = s.scalars(stmt).all()
        out = []
        for q in rows:
            d = q.to_dict()
            d["product_name"] = q.product.name if q.product else None
            d["category"] = q.product.category if q.product else None
            out.append(d)
        return out


def get_query_detail(query_id: int) -> Optional[dict]:
    """Devuelve una consulta con resultados y alertas."""
    with get_session() as s:
        q = s.get(PriceQuery, query_id)
        if not q:
            return None
        d = q.to_dict()
        d["product_name"] = q.product.name if q.product else None
        d["category"] = q.product.category if q.product else None
        d["results"] = [r.to_dict() for r in q.results]
        d["alerts"] = [a.to_dict() for a in q.alerts]
        return d


def get_price_trend(ean: str, limit: int = 30) -> list[dict]:
    """Serie temporal de KPIs para un EAN (para gráficos de tendencia)."""
    with get_session() as s:
        stmt = (
            select(PriceQuery)
            .where(PriceQuery.ean == ean)
            .order_by(PriceQuery.created_at)
            .limit(limit)
        )
        return [
            {
                "date": q.created_at.isoformat() if q.created_at else None,
                "min_price": q.min_price,
                "avg_price": q.avg_price,
                "max_price": q.max_price,
            }
            for q in s.scalars(stmt).all()
        ]


def dashboard_metrics() -> dict:
    """KPIs agregados para el dashboard ejecutivo."""
    with get_session() as s:
        total_products = s.scalar(select(func.count(Product.id))) or 0
        total_queries = s.scalar(select(func.count(PriceQuery.id))) or 0
        total_alerts = s.scalar(select(func.count(Alert.id))) or 0
        avg_margin = s.scalar(select(func.avg(PriceQuery.avg_margin_pct)))

        # Últimas alertas.
        recent_alerts = s.scalars(
            select(Alert).order_by(desc(Alert.created_at)).limit(10)
        ).all()

        # Productos por categoría.
        by_cat_rows = s.execute(
            select(Product.category, func.count(Product.id)).group_by(Product.category)
        ).all()

        return {
            "total_products": total_products,
            "total_queries": total_queries,
            "total_alerts": total_alerts,
            "avg_margin_pct": round(avg_margin, 1) if avg_margin is not None else None,
            "products_by_category": {row[0]: row[1] for row in by_cat_rows},
            "recent_alerts": [a.to_dict() for a in recent_alerts],
        }


def list_alerts(limit: int = 100) -> list[dict]:
    with get_session() as s:
        rows = s.scalars(select(Alert).order_by(desc(Alert.created_at)).limit(limit)).all()
        return [a.to_dict() for a in rows]
