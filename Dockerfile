# Imagen con Chromium y dependencias de sistema preinstaladas para Playwright.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

CMD gunicorn app:app --bind 0.0.0.0:${PORT} --workers 2 --timeout 120
