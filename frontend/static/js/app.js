/* Makro Retail Price Intelligence — lógica del dashboard (frontend). */

const API = {
  config: () => fetch('/api/config').then(r => r.json()),
  search: (body) => fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()),
  searchName: (body) => fetch('/api/search-name', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()),
  history: () => fetch('/api/history').then(r => r.json()),
  dashboard: () => fetch('/api/dashboard').then(r => r.json()),
  alerts: () => fetch('/api/alerts').then(r => r.json()),
  products: () => fetch('/api/products').then(r => r.json()),
};

let CONFIG = { categories: {}, retailers: {} };
let PRODUCTS = [];
let categoryChart = null;

// ── Utilidades ──────────────────────────────────────────────
const fmtCOP = (n) => (n == null || isNaN(n)) ? '—' : '$' + Math.round(n).toLocaleString('es-CO');
const fmtPct = (n) => (n == null || isNaN(n)) ? '—' : n.toFixed(1) + '%';
const marginColor = (p) => p == null ? '' : (p >= 20 ? 'text-green' : p >= 10 ? 'text-amber' : 'text-red');

// ── Navegación ──────────────────────────────────────────────
function switchView(view) {
  document.querySelectorAll('.nav-link').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  document.querySelectorAll('.view').forEach(el => el.classList.add('d-none'));
  document.getElementById('view-' + view).classList.remove('d-none');
  if (view === 'dashboard') loadDashboard();
  if (view === 'history') loadHistory();
  if (view === 'alerts') loadAlerts();
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
  if (!hints.length) { box.innerHTML = '<span class="text-muted small">Aún no hay productos consultados en esta categoría. Ingresa un EAN real para empezar.</span>'; return; }
  box.innerHTML = hints.map(p =>
    `<span class="ean-chip" onclick="fillEan('${p.ean}', ${p.cost || 0})">${p.ean} · ${p.name}</span>`).join('');
}

function fillEan(ean, cost) {
  document.getElementById('eanInput').value = ean;
  if (cost) document.getElementById('costInput').value = cost;
}

// ── Consulta ────────────────────────────────────────────────
async function doSearch() {
  const ean = document.getElementById('eanInput').value.trim();
  const out = document.getElementById('searchResult');
  if (!ean) { out.innerHTML = '<div class="alert alert-warning">Ingresa un EAN.</div>'; return; }

  const margin = parseFloat(document.getElementById('marginInput').value);
  const body = {
    ean,
    cost: parseInt(document.getElementById('costInput').value) || null,
    description: document.getElementById('descInput').value.trim() || null,
    category: document.getElementById('categorySelect').value,
    target_margin: isNaN(margin) ? null : margin / 100,
  };

  out.innerHTML = '<div class="loading"><div class="spinner-border text-primary"></div><div class="mt-2">Consultando retailers...</div></div>';
  try {
    const report = await API.search(body);
    if (report.error) { out.innerHTML = `<div class="alert alert-danger">${report.error}</div>`; return; }
    renderReport(report);
  } catch (e) {
    out.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
  }
}

// ── Consulta por nombre (independiente del EAN) ─────────────
async function doSearchName() {
  const name = document.getElementById('nameInput').value.trim();
  const out = document.getElementById('searchResult');
  if (!name) { out.innerHTML = '<div class="alert alert-warning">Ingresa el nombre del producto.</div>'; return; }

  const margin = parseFloat(document.getElementById('nameMarginInput').value);
  const body = {
    name,
    cost: parseInt(document.getElementById('nameCostInput').value) || null,
    category: document.getElementById('nameCategorySelect').value,
    target_margin: isNaN(margin) ? null : margin / 100,
  };

  out.innerHTML = '<div class="loading"><div class="spinner-border text-primary"></div><div class="mt-2">Buscando "' + name + '" en los ecommerce...</div></div>';
  try {
    const report = await API.searchName(body);
    if (report.error) { out.innerHTML = `<div class="alert alert-danger">${report.error}</div>`; return; }
    renderReport(report);
  } catch (e) {
    out.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
  }
}

function renderReport(report) {
  const k = report.kpis;
  const cat = CONFIG.categories[report.category] || {};
  const found = report.results.filter(r => r.found);
  if (!found.length) {
    document.getElementById('searchResult').innerHTML =
      `<div class="alert alert-warning">No se encontró el producto en ningún retailer. Prueba con descripción para homologar.</div>`;
    return;
  }
  // Precio de referencia para escalar barras: SIEMPRE el regular (sin descuento).
  const maxEff = Math.max(...found.map(r => r.effective_price || r.price || r.promo_price));

  const byName = report.search_mode === 'name';
  // En búsqueda por nombre el EAN es sintético: no lo mostramos.
  const eanLabel = byName ? '' : `<span class="text-muted ms-2">EAN: ${report.ean}</span>`;
  const modeBadge = byName
    ? '<span class="badge bg-danger ms-2">Búsqueda por nombre</span>'
    : (report.match_mode === 'description' ? '<span class="badge bg-warning text-dark ms-2">Homologado por descripción</span>' : '');
  // El export re-ejecuta la consulta: en modo nombre necesita la descripción.
  const exportDesc = byName ? report.product_name : (report.match_mode === 'description' ? report.product_name : null);

  const kpiCards = [
    ['Precio mínimo', fmtCOP(k.min_price), k.leader_retailer, 'text-green'],
    ['Precio máximo', fmtCOP(k.max_price), k.most_expensive_retailer, 'text-red'],
    ['Precio promedio', fmtCOP(k.avg_price), `${k.available_count} de ${k.total_count} retailers`, 'text-amber'],
    ['Spread', fmtCOP(k.spread), 'Rango de mercado', ''],
    ['Margen promedio', fmtPct(k.avg_margin_pct), `Costo: ${fmtCOP(report.cost)}`, marginColor(k.avg_margin_pct)],
  ];

  let html = `
    <div class="d-flex justify-content-between align-items-center flex-wrap mb-3">
      <div>
        <span class="badge-cat" style="background:${(cat.color||'#888')}22;color:${cat.color||'#888'}">${cat.emoji||''} ${cat.label||''}</span>
        <span class="fw-bold ms-2">${report.product_name}</span>
        ${eanLabel}
        ${modeBadge}
      </div>
      <button class="btn btn-outline-success btn-sm" onclick='exportExcel(${JSON.stringify(report.ean)}, ${report.cost}, ${JSON.stringify(report.category)}, ${JSON.stringify(exportDesc)})'>
        <i class="bi bi-file-earmark-excel"></i> Exportar Excel
      </button>
    </div>
    <div class="kpi-grid">
      ${kpiCards.map(([l, v, s, c]) => `<div class="kpi-card"><div class="kpi-label">${l}</div><div class="kpi-value ${c}">${v}</div><div class="kpi-sub">${s||''}</div></div>`).join('')}
    </div>`;

  // Distribución de precios (basada en el precio regular, sin descuento)
  const sorted = [...found].sort((a, b) => (a.effective_price||a.price) - (b.effective_price||b.price));
  html += `<div class="card mt-3"><div class="card-body"><h6 class="card-title">Distribución de precios por cadena <span class="text-muted fw-normal small">(precio regular, sin descuento)</span></h6>`;
  sorted.forEach(r => {
    const reg = r.effective_price || r.price || r.promo_price;
    const w = Math.max(8, Math.round((reg / (maxEff * 1.05)) * 100));
    const color = (CONFIG.retailers[r.retailer] || {}).color || '#e2001a';
    const isMin = reg === k.min_price;
    html += `<div class="pbar-row">
      <div class="pbar-name">${isMin ? '🏆 ' : ''}${r.retailer_name}</div>
      <div class="pbar-track"><div class="pbar-fill" style="width:${w}%;background:${color}">${fmtCOP(reg)}</div></div>
      ${r.promo_price ? `<span class="pbar-tag" title="Precio con descuento de la competencia">PROMO ${fmtCOP(r.promo_price)}</span>` : '<span style="width:46px"></span>'}
    </div>`;
  });
  html += `</div></div>`;

  // Tabla de márgenes
  html += `<h2 class="section-title">Comparativo de márgenes <span class="text-muted fw-normal small">(margen calculado sobre el precio regular)</span></h2>
    <div class="card"><div class="card-body table-responsive">
    <table class="table table-sm align-middle"><thead><tr>
      <th>Retailer</th><th>Precio regular</th><th>Precio con descuento</th><th>Costo</th><th>Margen $</th><th>Margen %</th></tr></thead><tbody>
    ${report.margins.filter(m => m.found).map(m => `<tr>
      <td>${m.retailer}</td><td>${fmtCOP(m.effective_price)}</td>
      <td>${m.promo_price ? `<span class="text-red fw-bold">${fmtCOP(m.promo_price)}</span>` : '<span class="text-muted">—</span>'}</td>
      <td>${fmtCOP(report.cost)}</td>
      <td>${fmtCOP(m.margin_value)}</td><td class="${marginColor(m.margin_pct)} fw-bold">${fmtPct(m.margin_pct)}</td></tr>`).join('')}
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

async function exportExcel(ean, cost, category, description) {
  const margin = parseFloat(document.getElementById('marginInput').value);
  const body = { ean, cost, category, description: description || null, target_margin: isNaN(margin) ? null : margin / 100 };
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
    <td>${fmtCOP(h.min_price)}</td><td>${fmtCOP(h.avg_price)}</td><td>${fmtCOP(h.max_price)}</td>
    <td class="${marginColor(h.avg_margin_pct)}">${fmtPct(h.avg_margin_pct)}</td>
    <td><button class="btn btn-sm btn-outline-primary" onclick='reload(${JSON.stringify(h.ean)}, ${h.cost || 0}, ${JSON.stringify(h.category || '')}, ${JSON.stringify(h.product_name || '')})'>Ver</button></td>
  </tr>`).join('') : '<tr><td colspan="8" class="text-muted text-center">Sin histórico.</td></tr>';
}

function reload(ean, cost, category, productName) {
  switchView('search');
  // Los EAN sintéticos (N-...) corresponden a búsquedas por nombre.
  if (typeof ean === 'string' && ean.startsWith('N-')) {
    switchSearch('name');
    document.getElementById('nameInput').value = productName || '';
    if (cost) document.getElementById('nameCostInput').value = cost;
    if (category) document.getElementById('nameCategorySelect').value = category;
    doSearchName();
    return;
  }
  switchSearch('ean');
  fillEan(ean, cost);
  if (category) document.getElementById('categorySelect').value = category;
  doSearch();
}

// ── Alertas ─────────────────────────────────────────────────
async function loadAlerts() {
  const alerts = await API.alerts();
  document.getElementById('alertsList').innerHTML = alerts.length
    ? alerts.map(a => `<div class="alert-item ${a.level}"><strong>${a.type}</strong> · ${a.message} <span class="text-muted">(${(a.created_at||'').slice(0,10)})</span></div>`).join('')
    : '<div class="text-muted">Sin alertas.</div>';
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

  out.innerHTML = '<div class="loading"><div class="spinner-border text-primary"></div><div class="mt-2">Procesando...</div></div>';
  const res = await fetch('/api/bulk', { method: 'POST', body: fd }).then(r => r.json());
  if (res.error) { out.innerHTML = `<div class="alert alert-danger">${res.error}</div>`; return; }

  let html = `<div class="alert alert-success">Procesados: <strong>${res.processed}</strong> productos.</div>`;
  if (res.errors && res.errors.length) html += `<div class="alert alert-warning">${res.errors.join('<br>')}</div>`;
  if (res.reports && res.reports.length) {
    html += `<div class="table-responsive"><table class="table table-sm"><thead><tr>
      <th>EAN</th><th>Producto</th><th>Mín</th><th>Prom</th><th>Máx</th><th>Margen Makro</th></tr></thead><tbody>
      ${res.reports.map(r => `<tr><td>${r.ean}</td><td>${r.product_name||'—'}</td>
        <td>${fmtCOP(r.kpis.min_price)}</td><td>${fmtCOP(r.kpis.avg_price)}</td><td>${fmtCOP(r.kpis.max_price)}</td>
        <td class="${marginColor(r.home_margin && r.home_margin.margin_pct)}">${r.home_margin ? fmtPct(r.home_margin.margin_pct) : '—'}</td></tr>`).join('')}
      </tbody></table></div>`;
  }
  out.innerHTML = html;
  loadHistory();
}

document.addEventListener('DOMContentLoaded', init);
