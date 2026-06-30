"""
Inicialización del motor de base de datos y gestión de sesiones.

Usa SQLAlchemy 2.0 sobre SQLite. Expone un context manager `get_session`
para uso seguro de transacciones desde la capa de servicios.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import Config


class Base(DeclarativeBase):
    """Clase base declarativa para todos los modelos ORM."""


# `check_same_thread=False` permite usar la conexión SQLite desde el pool
# de hilos del scraper. `future=True` activa el estilo 2.0.
engine = create_engine(
    Config.DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if Config.DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def init_db() -> None:
    """Crea todas las tablas declaradas si aún no existen."""
    # Importar modelos para registrarlos en el metadata antes de create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_schema()


def _migrate_schema() -> None:
    """Añade columnas nuevas en bases SQLite existentes (sin Alembic)."""
    if not Config.DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "products" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("products")}
    alters = []
    if "pvp" not in existing:
        alters.append("ALTER TABLE products ADD COLUMN pvp INTEGER")
    if "catalog_updated_at" not in existing:
        alters.append("ALTER TABLE products ADD COLUMN catalog_updated_at DATETIME")
    if not alters:
        return
    with engine.begin() as conn:
        for stmt in alters:
            conn.execute(text(stmt))


@contextmanager
def get_session() -> Iterator[Session]:
    """Provee una sesión transaccional; hace commit/rollback automáticamente."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
