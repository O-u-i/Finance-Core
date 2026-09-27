// The standalone Demo UI is bilingual. API values and user data remain unchanged.
const english = {
  '概览': 'Overview', '交易': 'Transactions', '持仓与报表': 'Holdings & reports',
  '生活与计划': 'Living & plans', '自动化与数据': 'Automation & data', '主数据': 'Master data', '设置': 'Settings',
  '数据空间': 'Workspace', '退出': 'Sign out', '刷新': 'Refresh', '重试': 'Retry',
  '撤销上一步普通操作': 'Undo latest operation', '装载合成示例': 'Load synthetic example',
  '草稿': 'Drafts', '已过账': 'Posted', '对账': 'Reconciliation', '按计价商品汇总': 'Summary by commodity',
  '商品': 'Commodity', '现金': 'Cash', '成本': 'Cost', '市值': 'Market value', '未实现盈亏': 'Unrealized P&L',
  '缺价': 'Missing prices', '确定性检查': 'Deterministic checks', '尚无已过账数据。': 'No posted data yet.',
  '所有财务规则由 Finance Core 后端执行；当前数据空间与其他 Vault 完全隔离。': 'Finance Core runs all finance rules on the backend. This workspace is isolated from other Vaults.',
  '确定性账本状态': 'Deterministic ledger status',
  '名称': 'Name', '账户名': 'Account name', '新增': 'Add', '停用': 'Deactivate', '删除': 'Delete',
  '暂无 commodity。': 'No commodities yet.', '类型化账户': 'Typed accounts', '暂无账户。': 'No accounts yet.',
  '显式价格': 'Explicit prices', '报价商品': 'Quote commodity', '价格': 'Price', '时间': 'Time', '来源': 'Source',
  '新增价格': 'Add price', '自动': 'Automatic', '无': 'None', '移除': 'Remove',
  '日期': 'Date', '描述': 'Description', '计价商品': 'Balancing commodity', '账户': 'Account',
  '方向': 'Side', '估值率': 'Valuation rate', '类型': 'Type', '现金流': 'Cash flow',
  '草稿不会进入账本或报表；Decimal 字符串原样提交给后端。': 'Drafts do not enter the ledger or reports. Decimal strings are sent unchanged to the backend.',
  '新草稿': 'New draft', '增加 posting': 'Add posting', '保存草稿': 'Save draft', '后端验证': 'Validate on backend',
  '确认并过账': 'Confirm and post', '验证通过': 'Validation passed', '验证失败': 'Validation failed',
  '未过账草稿': 'Unposted drafts', '暂无草稿。': 'No drafts yet.', '编辑': 'Edit', '验证': 'Validate',
  '过账': 'Post', '已过账事实不可 PATCH/DELETE；更正必须创建 linked reversal。': 'Posted facts cannot be changed or deleted. Corrections require a linked reversal.',
  '查看 postings': 'View postings', '冲销': 'Reverse', '暂无已过账交易。': 'No posted entries yet.',
  '不可变 Journal Entries': 'Immutable Journal Entries',
  '草稿与验证': 'Draft and validate', '确认过账': 'Confirm posting', '不可变账本': 'Immutable ledger',
  '剩余数量': 'Remaining units', '剩余成本': 'Remaining cost', '最新价': 'Latest price',
  '缺失': 'Missing', '财务报表': 'Financial statements', '现金流分类': 'Cash flow categories',
  '生活账户名称': 'Living account name', '备注': 'Note', '新增生活账户': 'Add living account',
  'Open lots / 派生持仓': 'Open lots / derived holdings',
  '记录余额': 'Record balance', '暂无生活账户。': 'No living accounts yet.',
  '计划名称': 'Plan name', '新增计划': 'Add plan', '暂无计划。': 'No plans yet.',
  'World 确定性汇总': 'World deterministic summary', '周期模板': 'Recurring templates',
  '保存当前草稿编辑器内容为模板；到期只生成 draft。': 'Save the current draft editor as a template. Due dates create drafts only.',
  '保存当前草稿模板': 'Save draft template', '生成本月到期草稿': 'Generate due drafts for this month',
  '启用': 'Enable', 'JSON 输入': 'JSON input', '验证并导入 JSON': 'Validate and import JSON',
  'JSON 输入 ': 'JSON input ', '；整批验证通过后只创建草稿。': '; only drafts are created after batch validation.',
  'CSV 使用 entryId/postingId/accountId/side/units 等公开列。': 'CSV uses public columns such as entryId, postingId, accountId, side and units.',
  '验证并导入 CSV': 'Validate and import CSV', '原子执行': 'Run atomic batch',
  '只允许 commodities、accounts、priceQuotes、drafts；不能绕过 post/reversal。': 'Only commodities, accounts, priceQuotes and drafts are allowed. Posting and reversal cannot be bypassed.',
  '导出与版本化备份': 'Export and versioned backup', '打开 v3 JSON export': 'Open v3 JSON export',
  '下载 postings CSV': 'Download postings CSV', '打开 SHA-256 备份': 'Open SHA-256 backup',
  '完整备份恢复只允许空 ledger，并验证 format/schema/hash；成功后提供 undo。': 'Full backup restore requires an empty ledger and validates format, schema and hash. Undo is available afterward.',
  '验证并恢复到空账本': 'Validate and restore to empty ledger',
  '新数据空间名称': 'New workspace name', '创建': 'Create', '归档': 'Archive', '恢复': 'Restore',
  '移入可恢复隔离区': 'Move to recoverable quarantine', '撤销': 'Undo',
  '本地优先 · 确定性财务系统 · 不连接银行、券商、LLM 或实时行情': 'Local first · deterministic finance · no bank, broker, LLM or live market connection',
  'v1/v2 已停止注册；历史说明和 Horizon 文档不占用主导航。': 'v1/v2 are no longer registered. Historical notes and Horizon documents are outside the main navigation.',
  'token 明文只显示一次；不要复制到浏览器代码或日志。': 'The token is shown only once. Do not copy it into browser code or logs.',
  '例如：FRAG local': 'For example: local client', '只读': 'Read only', '读写': 'Read and write',
  '创建 token': 'Create token', '仅显示一次': 'Shown once', '撤销 token': 'Revoke token',
  '尚无 access token。': 'No access tokens yet.', '关于 Finance Core 3.1.1': 'About Finance Core 3.1.1',
  '进入本地财务系统': 'Enter your local finance system',
  '管理令牌只用于换取本机 HttpOnly 会话，不会写入浏览器存储。': 'The admin token creates a local HttpOnly session. It is not stored in the browser.',
  '管理令牌': 'Admin token', '进入 Finance Core': 'Enter Finance Core',
  '创建第一个数据空间': 'Create your first workspace',
  '每个数据空间拥有独立的 Commodity、账户、草稿、账本、持仓和计划数据库。': 'Each workspace has its own database for commodities, accounts, drafts, ledger, holdings and plans.',
  '恢复已归档数据空间': 'Restore an archived workspace', 'Personal · 个人数据': 'Personal · private data',
  'Sandbox · 测试数据': 'Sandbox · test data', '创建并进入': 'Create and enter',
  '正在连接 Finance Core 3.1…': 'Connecting to Finance Core 3.1…',
  'Finance Core 暂不可用': 'Finance Core is unavailable',
  '正在处理…': 'Working…', '操作成功。': 'Operation completed.',
  '已连接，正在加载概览…': 'Connected. Loading overview…',
  '正在切换数据空间并加载概览…': 'Switching workspace and loading overview…',
  '请先创建或选择一个数据空间。': 'Create or select a workspace first.',
  '无法连接 Finance Core 后端。请确认 npm.cmd run dev 正在运行，并检查 /api/v3/health。': 'Cannot connect to the Finance Core backend. Check that npm.cmd run dev is running and inspect /api/v3/health.',
  '数据空间已创建。': 'Workspace created.', '数据空间已归档。': 'Workspace archived.',
  '数据空间已恢复。': 'Workspace restored.', 'Vault 已移入可恢复隔离区。': 'Vault moved to recoverable quarantine.',
  '控制层操作已撤销。': 'Control operation undone.', 'Access token 已创建。': 'Access token created.',
  'Access token 已撤销。': 'Access token revoked.', '已刷新。': 'Refreshed.',
  '上一步普通操作已撤销。': 'Latest operation undone.',
  '合成主数据和 opening draft 已装载。': 'Synthetic master data and opening draft loaded.',
  'Commodity 已新增。': 'Commodity added.', '账户已新增。': 'Account added.', '价格已新增。': 'Price added.',
  'Commodity 已停用。': 'Commodity deactivated.', '账户已停用。': 'Account deactivated.',
  '价格已删除。': 'Price deleted.', '草稿已保存。': 'Draft saved.', '验证完成。': 'Validation completed.',
  '交易已过账。': 'Entry posted.', '草稿已删除。': 'Draft deleted.', '冲销交易已创建。': 'Reversal created.',
  '生活账户已新增。': 'Living account added.', '余额与快照已原子记录。': 'Balance and snapshot recorded atomically.',
  '月度计划已新增。': 'Monthly plan added.', '月度计划已删除。': 'Monthly plan deleted.',
  '周期模板已保存。': 'Recurring template saved.', '到期草稿已生成。': 'Due drafts generated.',
  '周期规则状态已更新。': 'Recurring rule status updated.', '周期规则已删除。': 'Recurring rule deleted.',
  'Drafts 已验证并导入。': 'Drafts validated and imported.', 'CSV Drafts 已验证并导入。': 'CSV drafts validated and imported.',
  'Mutable batch 已原子执行。': 'Mutable batch executed atomically.', '备份已验证并恢复。': 'Backup validated and restored.',
  '请先选择 CSV 文件。': 'Select a CSV file first.', '请先选择 JSON 备份。': 'Select a JSON backup first.',
  '确认将此 Vault 移入 30 天可恢复隔离区？': 'Move this Vault to the 30-day recoverable quarantine?',
  '确认将此完整聚合写入不可变账本？': 'Post this complete aggregate to the immutable ledger?',
  '确认过账此草稿？': 'Post this draft?',
  '确认创建 linked reversal？原交易不会被删除。': 'Create a linked reversal? The original entry remains.',
  '恢复只适用于空 v2 ledger。确认验证并恢复此备份？': 'Restore requires an empty ledger. Validate and restore this backup?',
};

const patterns = [
  [/^(.*) · 确定性账本状态$/, '$1 · Deterministic ledger status'],
  [/^恢复 (.*)$/, 'Restore $1'],
  [/^可撤销：(.*)$/, 'Undo available: $1'],
  [/^(API .*?)。v1\/v2 已停止注册；历史说明和 Horizon 文档不占用主导航。$/, '$1. v1/v2 are no longer registered. Historical notes and Horizon documents are outside the main navigation.'],
  [/^正在加载(.*)…$/, 'Loading $1…'],
  [/^请求 (.*) 超过 (\d+) 秒。请检查 FC 后端终端和 \/api\/v3\/health。$/, 'Request $1 exceeded $2 seconds. Check the FC backend terminal and /api/v3/health.'],
];

export function translate(source, language) {
  if (language !== 'en') return source;
  return english[source] || patterns.reduce((value, [pattern, replacement]) => value === source ? source.replace(pattern, replacement) : value, source);
}

export function initLanguageSwitch(root) {
  let language;
  try { language = localStorage.getItem('fc-ui-language') === 'en' ? 'en' : 'zh'; }
  catch { language = 'zh'; }
  const originalText = new WeakMap();
  const originalAttributes = new WeakMap();
  const switcher = document.createElement('div');
  switcher.className = 'language-switch';
  switcher.setAttribute('role', 'group');
  switcher.setAttribute('aria-label', 'Interface language');
  switcher.innerHTML = '<button type="button" data-language="zh" lang="zh-CN">中文</button><button type="button" data-language="en" lang="en">EN</button>';
  document.body.prepend(switcher);

  function renderNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const parent = node.parentElement;
      if (!parent || parent.closest('pre, code, .token-once, .entries strong, .list strong, .list small')) return;
      if (parent.tagName === 'OPTION' && !parent.hasAttribute('value')) return;
      const previous = originalText.get(node);
      const source = previous && previous.rendered === node.nodeValue ? previous.source : node.nodeValue;
      const trimmed = source.trim();
      const rendered = trimmed ? source.replace(trimmed, translate(trimmed, language)) : source;
      originalText.set(node, { source, rendered });
      if (node.nodeValue !== rendered) node.nodeValue = rendered;
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    for (const name of ['placeholder', 'title', 'aria-label']) {
      if (!node.hasAttribute(name)) continue;
      let entries = originalAttributes.get(node);
      if (!entries) { entries = new Map(); originalAttributes.set(node, entries); }
      const value = node.getAttribute(name);
      const previous = entries.get(name);
      const source = previous && previous.rendered === value ? previous.source : value;
      const rendered = translate(source, language);
      entries.set(name, { source, rendered });
      if (value !== rendered) node.setAttribute(name, rendered);
    }
    for (const child of node.childNodes) renderNode(child);
  }

  function applyLanguage() {
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    for (const button of switcher.querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.language === language));
    renderNode(root);
  }
  switcher.addEventListener('click', (event) => {
    const selected = event.target.closest('[data-language]')?.dataset.language;
    if (!selected || selected === language) return;
    language = selected;
    try { localStorage.setItem('fc-ui-language', language); } catch { /* The switch still works without storage. */ }
    applyLanguage();
  });
  new MutationObserver(() => renderNode(root)).observe(root, { childList: true, characterData: true, subtree: true });
  applyLanguage();
  return () => language;
}
