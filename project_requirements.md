# Retail Price Intelligence Colombia

## Objetivo

Desarrollar una plataforma de inteligencia de precios para retail colombiano que permita comparar precios de productos utilizando EAN o descripción.

El sistema estará orientado a compradores comerciales de Makro Colombia.

---

# Categorías

## Dairy

- Leche
- Yogurt
- Kumis
- Bebidas lácteas
- Crema de leche
- Mantequilla

## Cheese

- Quesos frescos
- Quesos maduros
- Quesos procesados

## Bakery

- Pan tajado
- Pan artesanal
- Pan industrial
- Tostadas
- Galletas panadería

## Fresh Bakery

- Pan fresco
- Croissants
- Hojaldres
- Tortas
- Productos recién horneados

## Cold Meat

- Jamones
- Mortadelas
- Salchichas
- Chorizos
- Tocineta

## Frozen

- Pollo congelado
- Vegetales congelados
- Papas congeladas
- Helados
- Comidas preparadas

## Seafood

- Camarones
- Pescados
- Atún
- Salmón
- Mariscos congelados

---

# Retailers

## Prioridad 1

- Éxito
- Carulla
- Jumbo
- Metro
- Makro
- Alkosto
- Olímpica
- PriceSmart

## Prioridad 2

- D1
- Ara
- Ísimo
- Farmatodo

---

# Funcionalidades

## Consulta Individual

Input:

EAN
Costo actual

Output:

Retailer
Precio regular
Precio promoción
Link producto
Fecha consulta

---

## Comparativo de Precios

Mostrar:

Precio mínimo

Precio máximo

Precio promedio

Spread

Retailer líder

Retailer más caro

---

## Comparativo de Márgenes

Calcular:

Margen $

Margen %

Para cada retailer.

---

## Estrategias de Precio Makro

Escenario 1

Igualar precio mínimo.

Escenario 2

Igualar precio promedio.

Escenario 3

Igualar líder mercado.

Escenario 4

Margen objetivo configurable.

---

## Homologación Inteligente

Si el EAN no existe:

Buscar descripción.

Calcular similitud.

Mostrar score.

Ejemplo:

Leche Alpina Entera 1100 ml

Coincidencia 96%.

---

## Dashboard

KPIs:

Precio mínimo

Precio máximo

Promedio

Margen mínimo

Margen promedio

Margen máximo

---

## Histórico

Guardar consultas.

SQLite.

---

## Exportación

Excel.

Formato corporativo.

---

## Carga Masiva

Excel:

EAN
Costo

Procesar cientos de productos.

---

## Alertas

Precio menor al costo.

Precio fuera de mercado.

Variación superior al 10%.

---

# Tecnologías

Backend:

Python

Flask

Playwright

SQLite

Pandas

OpenPyXL

Frontend:

HTML

Bootstrap

Chart.js

---

# Estructura Proyecto

/backend

/app.py

/scrapers

/services

/database

/export

/frontend

/templates

/static

/uploads

/reports

/logs