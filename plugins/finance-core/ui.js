export function mount(element, { apiBase }) {
  const controller = new AbortController();
  let disposed = false;
  let currentWorkspace = '';
  element.replaceChildren();

  const add = (parent, tag, value) => {
    const node = document.createElement(tag);
    node.textContent = String(value);
    parent.append(node);
    return node;
  };

  async function get(path) {
    const response = await fetch(`${apiBase}${path}`, { signal: controller.signal, credentials: 'same-origin' });
    if (!response.ok) throw new Error(response.status === 409 ? 'Finance Core API 3.10.0 is required.' : 'Finance Core is unavailable.');
    return response.json();
  }

  async function showDashboard(workspaceId) {
    currentWorkspace = workspaceId;
    const target = element.querySelector('[data-fc-dashboard]');
    target.replaceChildren();
    add(target, 'p', 'Loading dashboard…');
    try {
      const result = await get(`/dashboard?workspaceId=${encodeURIComponent(workspaceId)}`);
      if (disposed || currentWorkspace !== workspaceId) return;
      target.replaceChildren();
      const data = result.data;
      add(target, 'p', `Drafts: ${data.draftCount} · Posted entries: ${data.entryCount} · Open lots: ${data.openLotCount}`);
      for (const item of data.commoditySummaries || []) {
        add(target, 'p', `${item.commodityCode}: cash ${item.cash}, book ${item.bookValue}, market ${item.marketValue}, unrealized P&L ${item.unrealizedPnL}`);
      }
      const link = add(target, 'a', 'Open Finance Core to change Journal');
      link.href = result.journalUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
    } catch (error) {
      if (!disposed && error.name !== 'AbortError') {
        target.replaceChildren();
        add(target, 'p', error.message);
      }
    }
  }

  async function start() {
    add(element, 'h3', 'Finance Core · read-only dashboard');
    const status = add(element, 'p', 'Loading available Workspaces…');
    const panel = add(element, 'div', '');
    panel.dataset.fcDashboard = '';
    try {
      const scopes = await get('/scopes');
      if (disposed) return;
      status.remove();
      if (!scopes.workspaces.length) {
        add(panel, 'p', 'No configured Finance Core records are available.');
        return;
      }
      const label = document.createElement('label');
      label.textContent = 'Workspace ';
      const select = document.createElement('select');
      for (const workspace of scopes.workspaces) {
        const option = document.createElement('option');
        option.value = workspace.id;
        option.textContent = workspace.label;
        select.append(option);
      }
      label.append(select);
      element.insertBefore(label, panel);
      select.addEventListener('change', () => { void showDashboard(select.value); }, { signal: controller.signal });
      void showDashboard(select.value);
    } catch (error) {
      if (!disposed && error.name !== 'AbortError') status.textContent = error.message;
    }
  }

  void start();
  return () => { disposed = true; controller.abort(); element.replaceChildren(); };
}
