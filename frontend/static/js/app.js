/* Makro Retail Price Intelligence — lógica del dashboard (frontend). */

const API = {
  config: () => fetch('/api/config').then(r => r.json()),
  search: (body) => fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()),
  searchName: (body) => fetch('/api/search-name', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()),
  history: () => fetch('/api/history').then(r => r.json()),
  dashboard: () => fetch('/api/dashboard').then(r => r.json()),
  alerts: () => fetch('/api/alerts').then(r => r.json()),
  products: () => fetch('/api/products').then(r => r.json()),
  catalogStats: () => fetch('/api/catalog/stats').then(r => r.json()),
};

let CONFIG = { categories: {}, retailers: {}, stores: {} };
let PRODUCTS = [];
let categoryChart = null;
let LAST_REPORT = null;

// ── Utilidades ──────────────────────────────────────────────
const fmtCOP = (n) => (n == null || isNaN(n)) ? '—' : '$' + Math.round(n).toLocaleString('es-CO');
const fmtPct = (n) => (n == null || isNaN(n)) ? '—' : n.toFixed(1) + '%';
const marginColor = (p) => p == null ? '' : (p >= 20 ? 'text-green' : p >= 10 ? 'text-amber' : 'text-red');

function buildLocationOptions(stores) {
  let html = '<option value="">Nacional (sin regionalizar)</option>';
  const cities = new Set();
  Object.entries(stores || {}).forEach(([code, s]) => {
    html += `<option value="${code}">#${code} ${s.name} · ${s.city}</option>`;
    cities.add(s.city);
  });
  [...cities].sort((a, b) => a.localeCompare(b, 'es')).forEach(city => {
    html += `<option value="${city}">${city} (ciudad)</option>`;
  });
  return html;
}

function locationLabel(key) {
  if (!key) return 'Nacional';
  const store = CONFIG.stores[key];
  if (store) return `#${key} ${store.name}`;
  return key;
}

function parseCitiesList(raw) {
  return (raw || '').split(',').map(s => s.trim()).filter(Boolean);
}

// ── Navegación ──────────────────────────────────────────────
function switchView(view) {
  document.querySelectorAll('.nav-link').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  document.querySelectorAll('.view').forEach(el => el.classList.add('d-none'));
  document.getElementById('view-' + view).classList.remove('d-none');
  if (view === 'dashboard') loadDashboard();
  if (view === 'history') loadHistory();
  if (view === 'alerts') loadAlerts();
  if (view === 'catalog') loadCatalogStats();
}

// ── Inicialización ──────────────────────────────────────────
async function init() {
  CONFIG = await API.config();
  document.getElementById('modeBadge').textContent = 'SCRAPING REAL';
  document.getElementById('modeBadge').className = 'badge bg-success';

  const catOptions = Object.entries(CONFIG.categories)
    .map(([k, v]) => `<option value="${k}">${v.emoji} ${v.label}</option>`).join('');
  const sel = document.getElementById('categorySelect');
  sel.innerHTML = catOptions;
  document.getElementById('nameCategorySelect').innerHTML = catOptions;
  document.getElementById('nameCategorySelect').value = 'fruver';

  const locOpts = buildLocationOptions(CONFIG.stores);
  document.getElementById('locationSelect').innerHTML = locOpts;
  document.getElementById('nameLocationSelect').innerHTML = locOpts;

  PRODUCTS = await API.products();
  renderHints();
  sel.addEventListener('change', renderHints);

  document.querySelectorAll('.nav-link').forEach(el =>
    el.addEventListener('click', () => switchView(el.dataset.view)));
  document.querySelectorAll('.search-tab').forEach(el =>
    el.addEventListener('click', () => switchSearch(el.dataset.search)));
  document.getElementById('searchBtn').addEventListener('click', doSearch);
  document.getElementById('eanInput').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
  document.getElementById('searchNameBtn').addEventListener('click', doSearchName);
  document.getElementById('nameInput').addEventListener('keydown', e => { if (e.key === 'Enter') doSearchName(); });
  document.getElementById('bulkBtn').addEventListener('click', doBulk);
  document.getElementById('catalogBtn').addEventListener('click', doCatalogImport);
  loadCatalogStats();
}

// ── Selector de método de búsqueda (EAN / Nombre) ───────────
function switchSearch(mode) {
  document.querySelectorAll('.search-tab').forEach(el => el.classList.toggle('active', el.dataset.search === mode));
  document.getElementById('pane-ean').classList.toggle('d-none', mode !== 'ean');
  document.getElementById('pane-name').classList.toggle('d-none', mode !== 'name');
  document.getElementById('searchResult').innerHTML = '';
}

function renderHints() {
  const cat = document.getElementById('categorySelect').value;
  const hints = PRODUCTS.filter(p => p.category === cat).slice(0, 8);
  const box = document.getElementById('eanHints');
  if (!hints.length) { box.innerHTML = '<span class="text-muted small">Importa tu catálogo Makro o ingresa un EAN para empezar.</span>'; return; }
  box.innerHTML = hints.map(p => {
    const pvpLabel = p.pvp ? ` · PVP ${fmtCOP(p.pvp)}` : '';
    return `<span class="ean-chip" onclick="fillEan('${p.ean}', ${p.cost || 0}, ${p.pvp || 0})">${p.ean} · ${p.name}${pvpLabel}</span>`;
  }).join('');
}

function fillEan(ean, cost, pvp) {
  document.getElementById('eanInput').value = ean;
  if (cost) document.getElementById('costInput').value = cost;
}

// ── Consulta ────────────────────────────────────────────────
async function doSearch() {
  const ean = document.getElementById('eanInput').value.trim();
  const out = document.getElementById('searchResult');
  if (!ean) { out.innerHTML = '<div class="alert alert-warning">Ingresa un EAN.</div>'; return; }

  const margin = parseFloat(document.getElementById('marginInput').value);
  const city = document.getElementById('locationSelect').value || null;
  const body = {
    ean,
    cost: parseInt(document.getElementById('costInput').value) || null,
    description: document.getElementById('descInput').value.trim() || null,
    category: document.getElementById('categorySelect').value,
    target_margin: isNaN(margin) ? null : margin / 100,
    city,
  };

  out.innerHTML = '<div class="loading"><div class="spinner-border text-primary"></div><div class="mt-2">Consultando retailers...</div></div>';
  try {
    const report = await API.search(body);
    if (report.error) { out.innerHTML = `<div class="alert alert-danger">${report.error}</div>`; return; }
    LAST_REPORT = report;
    renderReport(report);
  } catch (e) {
    out.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
  }
}

function readNameWeight() {
  const raw = document.getElementById('nameWeightInput').value.trim();
  if (!raw) return { weight: null, weight_unit: null };
  const val = parseFloat(raw);
  if (isNaN(val) || val <= 0) return { weight: null, weight_unit: null };
  return {
    weight: val,
    weight_unit: document.getElementById('nameWeightUnit').value || 'g',
  };
}

// ── Consulta por nombre (independiente del EAN) ─────────────
async function doSearchName() {
  const name = document.getElementById('nameInput').value.trim();
  const out = document.getElementById('searchResult');
  if (!name) { out.innerHTML = '<div class="alert alert-warning">Ingresa el nombre del producto.</div>'; return; }

  const margin = parseFloat(document.getElementById('nameMarginInput').value);
  const { weight, weight_unit } = readNameWeight();
  const multiCities = parseCitiesList(document.getElementById('nameMultiCityInput').value);
  const body = {
    name,
    cost: parseInt(document.getElementById('nameCostInput').value) || null,
    category: document.getElementById('nameCategorySelect').value,
    target_margin: isNaN(margin) ? null : margin / 100,
    weight,
    weight_unit,
  };
  if (multiCities.length) {
    body.cities = multiCities;
  } else {
    const city = document.getElementById('nameLocationSelect').value || null;
    if (city) body.city = city;
  }

  const weightHint = weight ? ` · ${weight} ${weight_unit}` : '';
  out.innerHTML = '<div class="loading"><div class="spinner-border text-primary"></div><div class="mt-2">Buscando "' + name + '"' + weightHint + ' en los ecommerce...</div></div>';
  try {
    const report = await API.searchName(body);
    if (report.error) { out.innerHTML = `<div class="alert alert-danger">${report.error}</div>`; return; }
    LAST_REPORT = report;
    if (report.search_mode === 'name_multi_city') renderMultiCityReport(report);
    else renderReport(report);
  } catch (e) {
    out.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
  }
}

function homePositionClass(level) {
  return ({ success: 'alert-success', warning: 'alert-warning', danger: 'alert-danger', info: 'alert-info' }[level] || 'alert-info');
}

function renderMultiCityReport(report) {
  const rows = report.cities || [];
  const skipped = report.skipped || [];
  let html = `<div class="d-flex justify-content-between align-items-center flex-wrap mb-3">
    <div>
      <span class="badge bg-danger">Comparación multi-ciudad</span>
      <span class="fw-bold ms-2">${report.product_name || report.search_name || ''}</span>
    </div>
  </div>`;
  if (skipped.length) {
    html += `<div class="alert alert-warning">${skipped.map(s => `Omitida: ${s.city} — ${s.reason}`).join('<br>')}</div>`;
  }
  if (!rows.length) {
    html += '<div class="alert alert-warning">No se obtuvieron resultados por ciudad.</div>';
    document.getElementById('searchResult').innerHTML = html;
    return;
  }
  html += `<div class="card"><div class="card-body table-responsive">
    <table class="table table-sm align-middle"><thead><tr>
      <th>Ciudad / tienda</th><th>PVP Makro</th><th>Mín</th><th>Prom</th><th>Máx</th><th>Líder</th><th>Posición Makro</th><th></th>
    </tr></thead><tbody>
    ${rows.map(r => {
      const pos = r.home_position || '—';
      const posLabel = pos === 'leader' ? '✅ Más barato' : pos === 'most_expensive' ? '🔴 Más caro'
        : pos === 'above_avg' ? '⚠️ Sobre prom.' : pos === 'competitive' ? '🟡 Competitivo' : '—';
      const label = r.store_name ? `#${r.store_code} ${r.store_name}` : (r.city_label || r.city);
      return `<tr>
        <td>${label}</td><td>${fmtCOP(r.makro_pvp)}</td>
        <td>${fmtCOP(r.min_price)}</td><td>${fmtCOP(r.avg_price)}</td><td>${fmtCOP(r.max_price)}</td>
        <td>${r.leader_retailer || '—'}</td><td>${posLabel}</td>
        <td><button class="btn btn-sm btn-outline-primary" onclick='showCityDetail(${JSON.stringify(r.city)})'>Detalle</button></td>
      </tr>`;
    }).join('')}
    </tbody></table></div></div>`;
  document.getElementById('searchResult').innerHTML = html;
}

function showCityDetail(cityKey) {
  const report = (LAST_REPORT && LAST_REPORT.reports_by_city) ? LAST_REPORT.reports_by_city[cityKey] : null;
  if (!report) return;
  renderReport({ ...report, search_mode: 'name', search_name: LAST_REPORT.search_name || report.product_name });
  const box = document.getElementById('searchResult');
  box.insertAdjacentHTML('afterbegin', `<div class="alert alert-info mb-3">
    <button class="btn btn-sm btn-outline-secondary float-end" onclick='renderMultiCityReport(LAST_REPORT)'>← Volver a comparación</button>
    Detalle para <strong>${locationLabel(cityKey)}</strong>
  </div>`);
}

function renderReport(report) {
  const k = report.kpis || {};
  const cat = CONFIG.categories[report.category] || {};
  const found = report.results.filter(r => r.found);
  const notFound = report.results.filter(r => !r.found && (r.not_found_message || r.error));
  const competitors = found.filter(r => r.retailer !== 'makro');
  const pos = report.home_position || {};
  const byName = report.search_mode === 'name';
  const catalogHasProducts = byName && Object.values(report.search_catalog || {}).some(e => (e.product_count || 0) > 0);
  if (!competitors.length && !pos.available && !notFound.length && !catalogHasProducts) {
    document.getElementById('searchResult').innerHTML =
      `<div class="alert alert-warning">No se encontró el producto en ningún retailer. Importa el catálogo Makro o prueba con descripción para homologar.</div>`;
    return;
  }
  // Precio de referencia para escalar barras: SIEMPRE el precio regular (sin descuento).
  const chartRows = found.filter(r => r.price || r.promo_price);
  const regularPrice = (r) => r.price ?? r.promo_price;
  const maxEff = chartRows.length ? Math.max(...chartRows.map(regularPrice)) : 1;

  // En búsqueda por nombre el EAN es sintético: no lo mostramos.
  const eanLabel = byName ? '' : `<span class="text-muted ms-2">EAN: ${report.ean}</span>`;
  const modeBadge = byName
    ? '<span class="badge bg-danger ms-2">Búsqueda por nombre</span>'
    : (report.match_mode === 'description' ? '<span class="badge bg-warning text-dark ms-2">Homologado por descripción</span>' : '');
  const weightBadge = report.weight_label
    ? `<span class="badge bg-info text-dark ms-2">Peso: ${report.weight_label}</span>`
    : '';
  const cityBadge = report.city
    ? `<span class="badge bg-secondary ms-2">${locationLabel(report.city)}</span>`
    : '';
  const weightNote = report.target_weight_g
    ? `<span class="text-muted fw-normal small"> · precios normalizados a ${report.weight_label || report.target_weight_g + ' g'}</span>`
    : '';
  // El export re-ejecuta la consulta: en modo nombre necesita la descripción.
  const exportDesc = byName ? report.product_name : (report.match_mode === 'description' ? report.product_name : null);
  const hasPerKg = found.some(r => r.price_per_kg);

  const kpiCards = [
    ['Precio mínimo mercado', fmtCOP(k.min_price), k.leader_retailer, 'text-green'],
    ['Precio máximo mercado', fmtCOP(k.max_price), k.most_expensive_retailer, 'text-red'],
    ['Promedio competencia', fmtCOP(k.avg_price), `${k.available_count || 0} retailers`, 'text-amber'],
    ['PVP Makro', fmtCOP(report.makro_pvp), pos.available ? pos.status : 'Sin catálogo', report.makro_pvp ? '' : 'text-muted'],
    ['Spread mercado', fmtCOP(k.spread), 'Rango competencia', ''],
  ];

  let html = '';
  if (pos.available) {
    html += `<div class="alert ${homePositionClass(pos.level)} mb-3">
      <strong>Posición Makro:</strong> ${pos.message}
      <div class="small mt-1">PVP Makro ${fmtCOP(pos.makro_pvp)} · Mín. mercado ${fmtCOP(pos.market_min)} · Prom. ${fmtCOP(pos.market_avg)}</div>
    </div>`;
  } else if (report.makro_pvp == null) {
    html += `<div class="alert alert-info mb-3"><i class="bi bi-info-circle"></i> Importa el catálogo Makro con el PVP de este producto para ver si estás más caro que la competencia.</div>`;
  }

  html += `
    <div class="d-flex justify-content-between align-items-center flex-wrap mb-3">
      <div>
        <span class="badge-cat" style="background:${(cat.color||'#888')}22;color:${cat.color||'#888'}">${cat.emoji||''} ${cat.label||''}</span>
        <span class="fw-bold ms-2">${report.product_name}</span>
        ${eanLabel}
        ${modeBadge}
        ${weightBadge}
        ${cityBadge}
      </div>
      <button class="btn btn-outline-success btn-sm" onclick='exportExcel(${JSON.stringify(report.ean)}, ${report.cost}, ${JSON.stringify(report.category)}, ${JSON.stringify(exportDesc)}, ${JSON.stringify(report.city || null)})'>
        <i class="bi bi-file-earmark-excel"></i> Exportar Excel
      </button>
    </div>
    <div class="kpi-grid">
      ${kpiCards.map(([l, v, s, c]) => `<div class="kpi-card"><div class="kpi-label">${l}</div><div class="kpi-value ${c}">${v}</div><div class="kpi-sub">${s||''}</div></div>`).join('')}
    </div>`;

  // Distribución de precios (basada en el precio regular, sin descuento)
  const sorted = [...found].sort((a, b) => regularPrice(a) - regularPrice(b));
  html += `<div class="card mt-3"><div class="card-body"><h6 class="card-title">Distribución de precios por cadena <span class="text-muted fw-normal small">(precio regular, sin descuento${weightNote})</span></h6>`;
  sorted.forEach(r => {
    const reg = regularPrice(r);
    const w = Math.max(8, Math.round((reg / (maxEff * 1.05)) * 100));
    const color = (CONFIG.retailers[r.retailer] || {}).color || '#e2001a';
    const isMakro = r.retailer === 'makro';
    const isMin = !isMakro && reg === k.min_price;
    const makroTag = isMakro ? ' <span class="badge bg-danger">MAKRO</span>' : '';
    const skuTag = isMakro && r.makro_sku ? ` <span class="badge bg-secondary" title="SKU Makro (Regular)">SKU ${r.makro_sku}</span>` : '';
    const perKg = r.price_per_kg ? `<span class="text-muted small ms-1">(${fmtCOP(r.price_per_kg)}/kg)</span>` : '';
    html += `<div class="pbar-row">
      <div class="pbar-name">${isMin ? '🏆 ' : (isMakro ? '🏠 ' : '')}${r.retailer_name}${makroTag}${skuTag}</div>
      <div class="pbar-track"><div class="pbar-fill" style="width:${w}%;background:${color}">${fmtCOP(reg)}${perKg}</div></div>
      ${r.promo_price ? `<span class="pbar-tag" title="Precio con descuento de la competencia">PROMO ${fmtCOP(r.promo_price)}</span>` : '<span style="width:46px"></span>'}
    </div>`;
  });
  html += `</div></div>`;

  // Catálogo completo por retailer (búsqueda por nombre)
  if (byName) {
    html += renderSearchCatalog(report);
  }

  // Retailers sin coincidencias (solo en búsqueda por EAN; en nombre ya está en el catálogo)
  if (!byName && notFound.length) {
    html += `<div class="alert alert-secondary mt-3"><strong>Sin coincidencias:</strong><ul class="mb-0 mt-1">`;
    html += notFound.map(r => `<li>${r.not_found_message || r.error || (r.retailer_name + ': no encontrado')}</li>`).join('');
    html += `</ul></div>`;
  }

  // Tabla de márgenes
  const perKgHeader = hasPerKg ? '<th>$/kg</th>' : '';
  html += `<h2 class="section-title">Comparativo de márgenes <span class="text-muted fw-normal small">(margen calculado sobre el precio regular${weightNote})</span></h2>
    <div class="card"><div class="card-body table-responsive">
    <table class="table table-sm align-middle"><thead><tr>
      <th>Retailer</th><th>Precio regular</th><th>Precio con descuento</th>${perKgHeader}<th>Costo</th><th>Margen $</th><th>Margen %</th></tr></thead><tbody>
    ${report.margins.filter(m => m.found).map(m => {
      const isMakro = m.retailer === 'makro';
      const res = found.find(r => r.retailer === m.retailer) || {};
      const perKgCell = hasPerKg ? `<td>${res.price_per_kg ? fmtCOP(res.price_per_kg) : '<span class="text-muted">—</span>'}</td>` : '';
      return `<tr class="${isMakro ? 'table-danger' : ''}">
      <td>${isMakro ? '<strong>Makro</strong> <span class="badge bg-danger">PVP</span>' : m.retailer}</td><td>${fmtCOP(m.effective_price)}</td>
      <td>${m.promo_price ? `<span class="text-red fw-bold">${fmtCOP(m.promo_price)}</span>` : '<span class="text-muted">—</span>'}</td>
      ${perKgCell}
      <td>${fmtCOP(report.cost)}</td>
      <td>${fmtCOP(m.margin_value)}</td><td class="${marginColor(m.margin_pct)} fw-bold">${fmtPct(m.margin_pct)}</td></tr>`;
    }).join('')}
    </tbody></table></div></div>`;

  // Estrategias Makro
  html += `<h2 class="section-title">Estrategias de precio Makro</h2><div class="strategy-grid">`;
  report.strategies.forEach(s => {
    html += `<div class="strategy-card">
      <div class="strategy-name">${s.name}</div>
      <div class="strategy-price">${fmtCOP(s.suggested_price)}</div>
      <div class="${marginColor(s.margin_pct)} fw-bold">Margen ${fmtPct(s.margin_pct)} · ${fmtCOP(s.margin_value)}</div>
      <div class="text-muted small mt-1">${s.description}</div>
    </div>`;
  });
  html += `</div>`;

  // Alertas
  if (report.alerts && report.alerts.length) {
    html += `<h2 class="section-title">Alertas</h2><div class="alert-list">`;
    html += report.alerts.map(a => `<div class="alert-item ${a.level}">${a.message}</div>`).join('');
    html += `</div>`;
  }

  document.getElementById('searchResult').innerHTML = html;
}

function renderSearchCatalog(report) {
  const catalog = report.search_catalog || {};
  const entries = Object.values(catalog).sort((a, b) => {
    const pa = (CONFIG.retailers[a.retailer] || {}).priority || 9;
    const pb = (CONFIG.retailers[b.retailer] || {}).priority || 9;
    return pa - pb || (a.retailer_name || '').localeCompare(b.retailer_name || '', 'es');
  });

  if (!entries.length) return '';

  let html = `<h2 class="section-title">Catálogo por cadena <span class="text-muted fw-normal small">(todas las coincidencias con precio)</span></h2>`;

  entries.forEach(entry => {
    const color = (CONFIG.retailers[entry.retailer] || {}).color || '#888';
    const count = entry.product_count || 0;
    const header = `<div class="d-flex justify-content-between align-items-center mb-2">
      <span class="fw-bold" style="color:${color}">${entry.retailer_name}</span>
      <span class="badge ${count ? 'bg-success' : 'bg-secondary'}">${count} producto${count === 1 ? '' : 's'}</span>
    </div>`;

    if (!entry.found || !count) {
      const msg = entry.error || entry.not_found_message || 'Sin coincidencias';
      html += `<div class="card mb-2 border-secondary"><div class="card-body py-2">${header}
        <div class="text-muted small">${msg}</div></div></div>`;
      return;
    }

    const products = entry.products || [];
    html += `<div class="card mb-2"><div class="card-body py-2">${header}
      <div class="table-responsive"><table class="table table-sm mb-0"><thead><tr>
        <th>#</th><th>Producto</th><th>Precio regular</th><th>Precio promo</th><th>Presentación</th><th>Relevancia</th>
      </tr></thead><tbody>
      ${products.map((m, i) => {
        const eff = m.effective_price || m.promo_price || m.price;
        const isBest = i === 0 ? ' class="table-success"' : '';
        return `<tr${isBest}>
          <td>${i + 1}</td>
          <td>${m.url ? `<a href="${m.url}" target="_blank" rel="noopener">${m.product_name}</a>` : m.product_name}</td>
          <td>${fmtCOP(m.price)}</td>
          <td>${m.promo_price ? `<span class="text-red fw-bold">${fmtCOP(m.promo_price)}</span>` : '<span class="text-muted">—</span>'}</td>
          <td class="text-muted small">${m.presentation || '—'}</td>
          <td>${m.match_score != null ? m.match_score + '%' : '—'}</td>
        </tr>`;
      }).join('')}
      </tbody></table></div></div></div>`;
  });

  return html;
}

async function exportExcel(ean, cost, category, description, city) {
  const margin = parseFloat(document.getElementById('marginInput').value);
  const body = {
    ean, cost, category,
    description: description || null,
    target_margin: isNaN(margin) ? null : margin / 100,
    city: city || document.getElementById('locationSelect').value || null,
  };
  const resp = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!resp.ok) { alert('Error al exportar'); return; }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `makro_precios_${ean}.xlsx`; a.click();
  URL.revokeObjectURL(url);
}

// ── Dashboard ───────────────────────────────────────────────
async function loadDashboard() {
  const d = await API.dashboard();
  document.getElementById('dashboardKpis').innerHTML = [
    ['Productos', d.total_products, ''],
    ['Consultas', d.total_queries, ''],
    ['Alertas', d.total_alerts, 'text-red'],
    ['Margen promedio', fmtPct(d.avg_margin_pct), marginColor(d.avg_margin_pct)],
  ].map(([l, v, c]) => `<div class="kpi-card"><div class="kpi-label">${l}</div><div class="kpi-value ${c}">${v}</div></div>`).join('');

  const alertsBox = document.getElementById('dashboardAlerts');
  alertsBox.innerHTML = (d.recent_alerts || []).length
    ? d.recent_alerts.map(a => `<div class="alert-item ${a.level}">${a.message}</div>`).join('')
    : '<div class="text-muted small">Sin alertas registradas.</div>';

  const labels = Object.keys(d.products_by_category || {}).map(k => (CONFIG.categories[k] || {}).label || k);
  const values = Object.values(d.products_by_category || {});
  if (categoryChart) categoryChart.destroy();
  categoryChart = new Chart(document.getElementById('categoryChart'), {
    type: 'bar',
    data: { labels, datasets: [{ label: 'Productos', data: values, backgroundColor: '#e2001a' }] },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });
}

// ── Histórico ───────────────────────────────────────────────
async function loadHistory() {
  const rows = await API.history();
  const tbody = document.querySelector('#historyTable tbody');
  tbody.innerHTML = rows.length ? rows.map(h => `<tr>
    <td>${(h.created_at || '').replace('T', ' ').slice(0, 16)}</td>
    <td>${h.product_name || '—'}</td><td>${h.ean}</td>
    <td>${locationLabel(h.city)}</td>
    <td>${fmtCOP(h.min_price)}</td><td>${fmtCOP(h.avg_price)}</td><td>${fmtCOP(h.max_price)}</td>
    <td class="${marginColor(h.avg_margin_pct)}">${fmtPct(h.avg_margin_pct)}</td>
    <td><button class="btn btn-sm btn-outline-primary" onclick='reload(${JSON.stringify(h.ean)}, ${h.cost || 0}, ${JSON.stringify(h.category || '')}, ${JSON.stringify(h.product_name || '')}, ${JSON.stringify(h.city || '')})'>Ver</button></td>
  </tr>`).join('') : '<tr><td colspan="9" class="text-muted text-center">Sin histórico.</td></tr>';
}

function reload(ean, cost, category, productName, city) {
  switchView('search');
  // Los EAN sintéticos (N-...) corresponden a búsquedas por nombre.
  if (typeof ean === 'string' && ean.startsWith('N-')) {
    switchSearch('name');
    document.getElementById('nameInput').value = productName || '';
    if (cost) document.getElementById('nameCostInput').value = cost;
    if (category) document.getElementById('nameCategorySelect').value = category;
    if (city) document.getElementById('nameLocationSelect').value = city;
    doSearchName();
    return;
  }
  switchSearch('ean');
  fillEan(ean, cost);
  if (category) document.getElementById('categorySelect').value = category;
  if (city) document.getElementById('locationSelect').value = city;
  doSearch();
}

// ── Alertas ─────────────────────────────────────────────────
async function loadAlerts() {
  const alerts = await API.alerts();
  document.getElementById('alertsList').innerHTML = alerts.length
    ? alerts.map(a => `<div class="alert-item ${a.level}"><strong>${a.type}</strong> · ${a.message} <span class="text-muted">(${(a.created_at||'').slice(0,10)})</span></div>`).join('')
    : '<div class="text-muted">Sin alertas.</div>';
}

// ── Catálogo Makro ──────────────────────────────────────────
async function loadCatalogStats() {
  const box = document.getElementById('catalogStats');
  if (!box) return;
  const stats = await API.catalogStats();
  box.innerHTML = `<div class="row g-2">
    <div class="col-md-3"><div class="kpi-card"><div class="kpi-label">Productos</div><div class="kpi-value">${stats.total_products || 0}</div></div></div>
    <div class="col-md-3"><div class="kpi-card"><div class="kpi-label">Con SKU Makro</div><div class="kpi-value">${stats.with_sku || 0}</div></div></div>
    <div class="col-md-3"><div class="kpi-card"><div class="kpi-label">Con PVP</div><div class="kpi-value">${stats.with_pvp || 0}</div></div></div>
    <div class="col-md-3"><div class="kpi-card"><div class="kpi-label">Última importación</div><div class="kpi-value" style="font-size:14px">${stats.last_updated ? stats.last_updated.replace('T', ' ').slice(0, 16) : '—'}</div></div></div>
  </div>`;
}

async function doCatalogImport() {
  const fileInput = document.getElementById('catalogFile');
  const out = document.getElementById('catalogResult');
  if (!fileInput.files.length) { out.innerHTML = '<div class="alert alert-warning">Selecciona un archivo.</div>'; return; }
  const fd = new FormData();
  fd.append('file', fileInput.files[0]);
  out.innerHTML = '<div class="loading"><div class="spinner-border text-primary"></div><div class="mt-2">Importando catálogo...</div></div>';
  const res = await fetch('/api/catalog/import', { method: 'POST', body: fd }).then(r => r.json());
  if (res.error) { out.innerHTML = `<div class="alert alert-danger">${res.error}</div>`; return; }
  let html = `<div class="alert alert-success">Importados: <strong>${res.imported}</strong> de ${res.total_rows} filas.</div>`;
  if (res.with_sku != null) html += `<div class="text-muted small">Con SKU Makro: ${res.with_sku}</div>`;
  if (res.errors && res.errors.length) html += `<div class="alert alert-warning">${res.errors.slice(0, 10).join('<br>')}${res.errors.length > 10 ? '<br>…' : ''}</div>`;
  out.innerHTML = html;
  PRODUCTS = await API.products();
  renderHints();
  loadCatalogStats();
}

// ── Carga masiva ────────────────────────────────────────────
async function doBulk() {
  const fileInput = document.getElementById('bulkFile');
  const out = document.getElementById('bulkResult');
  if (!fileInput.files.length) { out.innerHTML = '<div class="alert alert-warning">Selecciona un archivo.</div>'; return; }
  const fd = new FormData();
  fd.append('file', fileInput.files[0]);
  const margin = parseFloat(document.getElementById('bulkMargin').value);
  if (!isNaN(margin)) fd.append('target_margin', margin / 100);
  const bulkCities = document.getElementById('bulkCities').value.trim();
  if (bulkCities) fd.append('cities', bulkCities);

  out.innerHTML = '<div class="loading"><div class="spinner-border text-primary"></div><div class="mt-2">Procesando...</div></div>';
  const res = await fetch('/api/bulk', { method: 'POST', body: fd }).then(r => r.json());
  if (res.error) { out.innerHTML = `<div class="alert alert-danger">${res.error}</div>`; return; }

  let html = `<div class="alert alert-success">Procesados: <strong>${res.processed}</strong> productos.</div>`;
  if (res.below_target_count > 0) {
    html += `<div class="alert alert-warning"><strong>${res.below_target_count}</strong> producto(s) con margen actual por debajo del objetivo.</div>`;
  }
  if (res.errors && res.errors.length) html += `<div class="alert alert-warning">${res.errors.join('<br>')}</div>`;
  if (res.reports && res.reports.length) {
    html += `<div class="table-responsive"><table class="table table-sm"><thead><tr>
      <th>EAN / clave</th><th>Producto</th><th>Ciudad</th><th>PVP Makro</th><th>Posición</th>
      <th>Margen obj.</th><th>Margen actual</th><th>Validación</th><th>Precio obj.</th>
      <th>Mín</th><th>Prom</th></tr></thead><tbody>
      ${res.reports.map(r => {
        const pos = r.home_position || {};
        const posLabel = pos.available
          ? (pos.status === 'leader' ? '✅ Más barato' : pos.status === 'most_expensive' ? '🔴 Más caro' : pos.status === 'above_avg' ? '⚠️ Sobre prom.' : '🟡 Competitivo')
          : '—';
        const v = r.margin_validation || {};
        const valLabel = v.status === 'met' ? '✅ Cumple'
          : v.status === 'below' ? '⚠️ Bajo obj.'
          : v.status === 'no_data' ? '—' : '—';
        const valClass = v.status === 'below' ? 'text-red fw-bold' : v.status === 'met' ? 'text-green' : '';
        return `<tr><td>${r.ean || r.query_key || '—'}</td><td>${r.product_name||'—'}</td>
        <td>${locationLabel(r.city)}</td>
        <td>${fmtCOP(r.makro_pvp)}</td><td>${posLabel}</td>
        <td>${fmtPct(r.target_margin_pct)}</td>
        <td class="${marginColor(v.actual_margin_pct)}">${fmtPct(v.actual_margin_pct)}</td>
        <td class="${valClass}" title="${v.message || ''}">${valLabel}</td>
        <td>${fmtCOP(r.target_price)}</td>
        <td>${fmtCOP(r.kpis.min_price)}</td><td>${fmtCOP(r.kpis.avg_price)}</td></tr>`;
      }).join('')}
      </tbody></table></div>`;
  }
  out.innerHTML = html;
  loadHistory();
}

document.addEventListener('DOMContentLoaded', init);
