# Retail Price Intelligence Colombia 🇨🇴

Plataforma de inteligencia de precios para **compradores comerciales de Makro Colombia**.
Compara precios por **EAN** (o por **descripción** mediante homologación inteligente) en los
principales retailers colombianos, calcula **márgenes**, propone **estrategias de precio**,
genera **alertas**, guarda **histórico** y exporta a **Excel corporativo**.

---

## 🚀 Ejecución rápida

```bash
pip install -r requirements.txt
python -m playwright install chromium   # solo para retailers no-VTEX (Alkosto, PriceSmart, D1, Ara, Ísimo, Farmatodo)
python app.py
```

Abre http://127.0.0.1:5000 e ingresa un **EAN real**.

> El sistema hace **scraping real** (sin datos demo). Requiere conexión a internet.
> Los retailers **VTEX** (Éxito, Carulla, Jumbo, Olímpica) funcionan vía API JSON
> sin navegador; los demás usan **Playwright** (instala Chromium con el comando de arriba).

### ⚠️ Notas de cobertura real (validadas jun-2026)

| Retailer | Estado | Detalle |
|----------|--------|---------|
| Éxito, Carulla, Jumbo, Olímpica | ✅ VTEX | Consulta por EAN directa y confiable (API JSON) |
| **Alkosto** | ✅ Algolia | Buscador Algolia con claves públicas de cliente (API JSON, sin navegador) |
| Farmatodo, D1, Ara, Ísimo | ⚙️ Playwright | Requiere Chromium; selectores pueden necesitar ajuste por sitio |
| **Metro** | ⛔ No se consulta | Su canal online es **jumbocolombia.com** (Cencosud); scrapearlo duplicaría a Jumbo |
| **Makro** | ⛔ No se consulta | **Referencia propia**: exige "Pasaporte Makro" (login), sin API pública. El costo lo ingresa el comprador |
| **PriceSmart** | ⛔ No se consulta | Club de membresía: su API (Bloomreach) devuelve **precio 0 a invitados**; los precios requieren login de socio |

Para ajustar qué retailers se consultan, edita el flag `scrape` en `RETAILERS` (`config.py`).

---

## 🧱 Arquitectura (por capas)

```
app.py                 → Aplicación Flask + API REST + servidor del frontend
config.py              → Configuración y catálogo de retailers/categorías
/scrapers              → Obtención de precios por retailer
   base.py             → Contrato + flujo EAN→descripción
   vtex.py             → Motor VTEX (Éxito, Carulla, Jumbo, Olímpica)
   algolia.py          → Motor Algolia (Alkosto)
   playwright_base.py  → Motor Playwright (Farmatodo, D1, Ara, Ísimo)
   retailers.py        → Clases concretas por retailer
   registry.py         → Orquestación en paralelo + fallback
/services              → Lógica de negocio
   rounding.py         → Redondeo comercial colombiano (COP enteros, múltiplos)
   matching.py         → Homologación por descripción (rapidfuzz) + presentación
   comparison.py       → KPIs de mercado (mín/máx/prom/spread/líder)
   margins.py          → Margen $ y % por retailer
   strategies.py       → 4 escenarios de precio Makro
   alerts.py           → Alertas (bajo costo, fuera de mercado, variación)
   pricing_service.py  → Orquestador de consulta completa
   bulk.py             → Carga masiva desde Excel
/database              → Persistencia (SQLAlchemy + SQLite)
   db.py · models.py · repository.py
/export                → Excel corporativo (openpyxl)
/frontend              → Dashboard (Bootstrap + Chart.js)
   /templates · /static
/uploads /reports /logs /data
```

---

## 📡 API REST

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET  | `/api/config` | Categorías, subcategorías y retailers |
| POST | `/api/search` | Consulta de comparación (`{ean, cost?, description?, category?, target_margin?, priority?}`) |
| GET  | `/api/history` | Histórico de consultas (`?ean=`) |
| GET  | `/api/history/<id>` | Detalle de una consulta |
| GET  | `/api/trend/<ean>` | Serie temporal de precios |
| GET  | `/api/dashboard` | KPIs ejecutivos |
| GET  | `/api/alerts` | Listado de alertas |
| GET  | `/api/products` | Catálogo |
| POST | `/api/export` | Descarga Excel del informe |
| POST | `/api/bulk` | Carga masiva (form-data `file`) |

---

## ✨ Funcionalidades

- **Consulta individual** por EAN con costo Makro.
- **Homologación inteligente**: si el EAN no existe, busca por descripción y
  calcula similitud (rapidfuzz). Entre múltiples presentaciones, elige la más
  cercana penalizando diferencias de tamaño/contenido.
- **Comparativo de precios y márgenes** por retailer.
- **4 estrategias de precio Makro**: igualar mínimo, promedio, líder y margen objetivo.
- **Alertas**: precio bajo costo, fuera de mercado, variación > 10%.
- **Histórico** en SQLite y **dashboard** ejecutivo.
- **Exportación Excel** corporativa multi-hoja.
- **Carga masiva** de cientos de productos.

## 🛒 Cobertura

- **Categorías**: Dairy, Cheese, Bakery, Fresh Bakery, Cold Meat, Frozen, Seafood.
- **Retailers P1**: Éxito, Carulla, Jumbo, Metro, Makro, Alkosto, Olímpica, PriceSmart.
- **Retailers P2**: D1, Ara, Ísimo, Farmatodo.

## 💲 Redondeo financiero

Todos los valores monetarios se manejan en **pesos colombianos enteros**
(`ROUND_HALF_UP`). Los precios sugeridos se redondean a **múltiplo comercial**
(50 COP por defecto), acorde a la práctica de góndola; los márgenes a 1 decimal.
