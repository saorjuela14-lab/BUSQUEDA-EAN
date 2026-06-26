"""Capa de persistencia (SQLite vía SQLAlchemy)."""
from .db import Base, SessionLocal, engine, get_session, init_db

__all__ = ["Base", "SessionLocal", "engine", "get_session", "init_db"]
