"""
ASGI entrypoint for FastAPI Cloud.

The business app remains Flask (`app.py`). FastAPI Cloud expects an ASGI app
and the `fastapi` CLI (`fastapi[standard]`). This module wraps the Flask WSGI
app so the same codebase runs on FastAPI Cloud and on Railway (gunicorn).
"""
from __future__ import annotations

from a2wsgi import WSGIMiddleware
from fastapi import FastAPI

# Flask application lives in app.py as `app`.
from app import app as flask_app

fastapi_app = FastAPI(
    title="BUSQUEDA-EAN",
    description="Retail Price Intelligence Colombia",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
fastapi_app.mount("/", WSGIMiddleware(flask_app))

# FastAPI Cloud / `fastapi run` look for a variable named `app`.
app = fastapi_app
