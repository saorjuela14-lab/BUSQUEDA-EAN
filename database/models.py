"""
Modelos ORM de la plataforma.

Esquema:
- Product         : catálogo maestro (EAN, nombre, categoría, marca, costo).
- PriceQuery      : una consulta/ejecución de comparación para un producto.
- PriceResult     : precio de un retailer dentro de una consulta (histórico).
- Alert           : alertas generadas durante una consulta.

Los precios se almacenan en pesos colombianos enteros (sin decimales),
acorde a la práctica comercial local.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Product(Base):
    """Producto del catálogo maestro identificado por EAN."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ean: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Costo actual del producto para Makro (COP).
    cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    queries: Mapped[list["PriceQuery"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ean": self.ean,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "subcategory": self.subcategory,
            "cost": self.cost,
        }


class PriceQuery(Base):
    """Una ejecución de comparación de precios para un producto en un momento dado."""

    __tablename__ = "price_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    ean: Mapped[str] = mapped_column(String(20), index=True)
    cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Estrategia de homologación usada: "ean" | "description".
    match_mode: Mapped[str] = mapped_column(String(20), default="ean")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # KPIs consolidados (snapshot del momento de la consulta).
    min_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spread: Mapped[int | None] = mapped_column(Integer, nullable=True)
    leader_retailer: Mapped[str | None] = mapped_column(String(40), nullable=True)
    most_expensive_retailer: Mapped[str | None] = mapped_column(String(40), nullable=True)
    avg_margin_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="queries")
    results: Mapped[list["PriceResult"]] = relationship(
        back_populates="query", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="query", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ean": self.ean,
            "cost": self.cost,
            "match_mode": self.match_mode,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "avg_price": self.avg_price,
            "spread": self.spread,
            "leader_retailer": self.leader_retailer,
            "most_expensive_retailer": self.most_expensive_retailer,
            "avg_margin_pct": self.avg_margin_pct,
        }


class PriceResult(Base):
    """Precio de un retailer concreto dentro de una consulta (registro histórico)."""

    __tablename__ = "price_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("price_queries.id"), index=True)
    retailer: Mapped[str] = mapped_column(String(40), index=True)
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    promo_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    promo_desc: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Score de homologación cuando se buscó por descripción (0-100).
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    query: Mapped["PriceQuery"] = relationship(back_populates="results")

    @property
    def effective_price(self) -> int | None:
        """Precio efectivo = promoción si existe, de lo contrario precio regular."""
        return self.promo_price if self.promo_price else self.price

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "retailer": self.retailer,
            "found": self.found,
            "price": self.price,
            "promo_price": self.promo_price,
            "promo_desc": self.promo_desc,
            "effective_price": self.effective_price,
            "product_name": self.product_name,
            "url": self.url,
            "match_score": self.match_score,
        }


class Alert(Base):
    """Alerta de negocio generada al analizar una consulta."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("price_queries.id"), index=True)
    ean: Mapped[str] = mapped_column(String(20), index=True)
    # Tipo: "below_cost" | "out_of_market" | "high_variation".
    level: Mapped[str] = mapped_column(String(20), default="info")  # info | warning | danger
    type: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    retailer: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    query: Mapped["PriceQuery"] = relationship(back_populates="alerts")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ean": self.ean,
            "level": self.level,
            "type": self.type,
            "message": self.message,
            "retailer": self.retailer,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
