import './style.css';

const app = document.querySelector('#app');

function money(value, currency) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(value);
}

function renderLoading() {
  app.innerHTML = '<section class="status">Loading local Finance Core data…</section>';
}

function renderError(error) {
  app.innerHTML = `
    <section class="status error">
      <h1>Finance Core is unavailable</h1>
      <p>${error instanceof Error ? error.message : 'Cannot connect to the local API.'}</p>
      <button id="retry">Retry</button>
    </section>`;
  document.querySelector('#retry').addEventListener('click', load);
}

function render(health, dashboard, holdings, transactions) {
  const cards = dashboard.currencySummaries.map((item) => `
    <article class="card">
      <span>${item.currency}</span>
      <strong>${money(item.marketValue, item.currency)}</strong>
      <small>Cash ${money(item.cash, item.currency)} · Unrealized P&amp;L ${money(item.unrealizedPnL, item.currency)}</small>
    </article>`).join('') || '<p class="empty">No data yet. Synthetic sample data can be imported through the API.</p>';

  app.innerHTML = `
    <header>
      <div><p class="eyebrow">LOCAL-FIRST DOMAIN SERVICE</p><h1>Finance Core</h1></div>
      <span class="badge">API ${health.apiVersion} · Schema ${health.schemaVersion}</span>
    </header>
    <section class="intro">
      <div><h2>Deterministic finance data and calculations</h2><p>This read-only page shows FC's version, capabilities, and aggregate results. Use an authorized API client for writes.</p></div>
      <dl><div><dt>Journal</dt><dd>${transactions.length}</dd></div><div><dt>Holdings</dt><dd>${holdings.length}</dd></div><div><dt>Currencies</dt><dd>${dashboard.currencySummaries.length}</dd></div></dl>
    </section>
    <section><h2>Asset overview</h2><div class="grid">${cards}</div></section>
    <section class="formula"><h2>Public formulas and boundaries</h2><ul>${Object.entries(dashboard.formulas).map(([key, value]) => `<li><code>${key}</code><span>${value}</span></li>`).join('')}</ul><p>${dashboard.assumptions.join(' ')}</p></section>
    <footer>Finance Core does not connect to banks or brokers, execute trades, or provide investment advice.</footer>`;
}

async function request(path) {
  const response = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

async function load() {
  renderLoading();
  try {
    const [health, dashboardResponse, holdingsResponse, transactionsResponse] = await Promise.all([
      request('/api/v1/health'), request('/api/v1/dashboard'), request('/api/v1/holdings'), request('/api/v1/transactions'),
    ]);
    render(health, dashboardResponse.data, holdingsResponse.data, transactionsResponse.data);
  } catch (error) {
    renderError(error);
  }
}

void load();
