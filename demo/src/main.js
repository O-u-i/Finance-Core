import './style.css';

const app = document.querySelector('#app');

function money(value, currency) {
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency }).format(value);
}

function renderLoading() {
  app.innerHTML = '<section class="status">正在读取本地 Finance Core 数据…</section>';
}

function renderError(error) {
  app.innerHTML = `
    <section class="status error">
      <h1>Finance Core 暂不可用</h1>
      <p>${error instanceof Error ? error.message : '无法连接本地 API。'}</p>
      <button id="retry">重试</button>
    </section>`;
  document.querySelector('#retry').addEventListener('click', load);
}

function render(health, dashboard, holdings, transactions) {
  const cards = dashboard.currencySummaries.map((item) => `
    <article class="card">
      <span>${item.currency}</span>
      <strong>${money(item.marketValue, item.currency)}</strong>
      <small>现金 ${money(item.cash, item.currency)} · 未实现盈亏 ${money(item.unrealizedPnL, item.currency)}</small>
    </article>`).join('') || '<p class="empty">暂无数据。可通过 API 导入合成示例数据。</p>';

  app.innerHTML = `
    <header>
      <div><p class="eyebrow">LOCAL-FIRST DOMAIN SERVICE</p><h1>Finance Core</h1></div>
      <span class="badge">API ${health.apiVersion} · Schema ${health.schemaVersion}</span>
    </header>
    <section class="intro">
      <div><h2>确定性财务数据与计算</h2><p>此页面只读，用来独立展示 FC 的版本、能力和聚合结果。写操作请通过受控 API 客户端执行。</p></div>
      <dl><div><dt>Journal</dt><dd>${transactions.length}</dd></div><div><dt>Holdings</dt><dd>${holdings.length}</dd></div><div><dt>Currencies</dt><dd>${dashboard.currencySummaries.length}</dd></div></dl>
    </section>
    <section><h2>资产概览</h2><div class="grid">${cards}</div></section>
    <section class="formula"><h2>公开公式与边界</h2><ul>${Object.entries(dashboard.formulas).map(([key, value]) => `<li><code>${key}</code><span>${value}</span></li>`).join('')}</ul><p>${dashboard.assumptions.join(' ')}</p></section>
    <footer>Finance Core 不连接银行或券商，不执行交易，不提供投资建议。</footer>`;
}

async function request(path) {
  const response = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`请求失败：${response.status}`);
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
