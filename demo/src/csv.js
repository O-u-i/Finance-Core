// CSV structure and explicit source mapping only; financial validation stays on FC.
export function readCSV(text) {
  const rows = []; let row = [], cell = '', quoted = false, closed = false;
  const raw = text.replace(/^\uFEFF/, '');
  const finish = () => { row.push(cell); if (row.some((value) => value.trim())) rows.push(row); row = []; cell = ''; closed = false; };
  for (let i = 0; i < raw.length; i++) {
    const char = raw[i];
    if (quoted) {
      if (char === '"' && raw[i + 1] === '"') { cell += '"'; i++; }
      else if (char === '"') { quoted = false; closed = true; }
      else cell += char;
    } else if (char === '"') {
      if (cell || closed) throw new Error('CSV contains a misplaced quote.');
      quoted = true;
    } else if (char === ',') { row.push(cell); cell = ''; closed = false; }
    else if (char === '\n' || char === '\r') { finish(); if (char === '\r' && raw[i + 1] === '\n') i++; }
    else { if (closed) throw new Error('CSV contains text after a closing quote.'); cell += char; }
  }
  if (quoted) throw new Error('CSV contains an unclosed quoted field.');
  finish();
  if (rows.length < 2) throw new Error('CSV needs a header and at least one data row.');
  const header = rows.shift().map((value) => value.trim());
  if (header.some((value) => !value) || new Set(header).size !== header.length) throw new Error('CSV headers must be non-empty and unique.');
  if (rows.some((values) => values.length !== header.length)) throw new Error('CSV row widths do not match the header.');
  return { header, rows: rows.map((values) => Object.fromEntries(header.map((name, i) => [name, values[i]]))) };
}

const sourceColumns = ['日期', '会计科目', '责任中心', '参考号（Ref.)', '摘要（Description）', '借（Debit）CNY', '借（Debit）MYR', '贷（Credit）CNY', '贷（Credit）MYR', '父记录'];
export const isAccountingCSV = ({ header }) => sourceColumns.every((name) => header.includes(name));
export const sourceAccountCodes = (source) => [...new Set(source.rows.map((row) => {
  const code = row['会计科目'].trim().match(/^\d+/)?.[0];
  if (!code) throw new Error('Each source account needs an explicit leading account code.');
  return code;
}))];

export function checkImportCSV(text) {
  const source = readCSV(text);
  if (isAccountingCSV(source)) return { kind: 'accounting', source, codes: sourceAccountCodes(source) };
  const required = ['entryId', 'date', 'description', 'balancingCommodityCode', 'postingId', 'accountId', 'side', 'units', 'commodityCode'];
  if (!required.every((name) => source.header.includes(name))) throw new Error('Use FC posting CSV columns, or the supported accounting journal template. Other layouts need an explicit mapping.');
  return { kind: 'standard', source, count: new Set(source.rows.map((row) => row.entryId)).size };
}

export function csvCommodityIssues(inspected, commodities, accounts = []) {
  const issues = new Set();
  const check = (code, row, balancing = false) => {
    const item = commodities.find(item => item.code === code);
    if (!item) issues.add(`Row ${row}: commodity code ${code || '(empty)'} is not registered in this Workspace. Add it in Master data.`);
    else if (item.status !== 'active') issues.add(`Row ${row}: commodity code ${code} is inactive. Activate it in Master data.`);
    else if (balancing && item.kind !== 'currency') issues.add(`Row ${row}: balancing commodity ${code} must be a currency.`);
  };
  inspected.source.rows.forEach((row, index) => {
    if (inspected.kind === 'accounting') {
      for (const code of ['CNY', 'MYR']) {
        if ([`借（Debit）${code}`, `贷（Credit）${code}`].some(column => row[column]?.trim() && !/^0+(\.0+)?$/.test(row[column].trim()))) check(code, index + 2, true);
      }
    } else {
      const code = row.commodityCode.trim(); check(code, index + 2); check(row.balancingCommodityCode.trim(), index + 2, true);
      const account = accounts.find(item => item.id === row.accountId.trim() && item.status === 'active');
      if (account && !account.allowedCommodityCodes?.includes(code)) issues.add(`Row ${index + 2}: the selected account does not allow commodity ${code}. Update its allowed commodities in Master data.`);
    }
  });
  return [...issues];
}

export function mapAccountingCSV(source, { groupingConfirmed, accountMap, accounts, commodities, prefix }) {
  if (!groupingConfirmed) throw new Error('Confirm how parent and child rows form drafts before checking this template.');
  const groups = []; let group;
  source.rows.forEach((row, index) => {
    if (!row['父记录'].trim()) { group = []; groups.push(group); }
    if (!group) throw new Error(`CSV row ${index + 2} has no preceding parent row.`);
    group.push(row);
  });
  return { drafts: groups.map((rows, index) => {
    const first = rows[0], date = first['日期'].trim().replaceAll('/', '-');
    const match = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(date);
    if (!match) throw new Error(`Draft ${index + 1} needs a valid date.`);
    const iso = `${match[1]}-${match[2].padStart(2, '0')}-${match[3].padStart(2, '0')}`;
    const calendarDate = new Date(`${iso}T00:00:00Z`);
    if (Number.isNaN(calendarDate.getTime()) || calendarDate.toISOString().slice(0, 10) !== iso) throw new Error(`Draft ${index + 1} has an invalid calendar date.`);
    if (!first['摘要（Description）'].trim()) throw new Error(`Draft ${index + 1} needs a description.`);
    const draftId = `${prefix}-${index + 1}`, postings = [];
    for (const row of rows) {
      if (row['日期'].trim().replaceAll('/', '-') !== date) throw new Error(`Draft ${index + 1} contains conflicting dates.`);
      const code = sourceAccountCodes({ rows: [row] })[0], accountId = accountMap[code];
      const account = accounts.find((item) => item.id === accountId && item.status === 'active');
      if (!account) throw new Error('Map every source account to an active account in this Workspace.');
      for (const [column, side, commodityCode] of [['借（Debit）CNY','debit','CNY'], ['借（Debit）MYR','debit','MYR'], ['贷（Credit）CNY','credit','CNY'], ['贷（Credit）MYR','credit','MYR']]) {
        const units = row[column].trim(); if (!units || /^0+(\.0+)?$/.test(units)) continue;
        if (!/^\d+(\.\d+)?$/.test(units)) throw new Error('Amounts must be unsigned decimal strings without separators.');
        if (!commodities.some((item) => item.code === commodityCode && item.status === 'active')) throw Object.assign(new Error(`Create active source currency ${commodityCode} in Master data before importing.`), { code: 'CSV_COMMODITY' });
        if (!account.allowedCommodityCodes.includes(commodityCode)) throw Object.assign(new Error(`Mapped account ${code} does not support source currency ${commodityCode}. Update its allowed commodities in Master data.`), { code: 'CSV_COMMODITY' });
        postings.push({ id: `${draftId}-p${postings.length + 1}`, accountId, side, units, commodityCode, cashFlowCategory: 'other', memo: [row['责任中心'], row['父记录']].filter(Boolean).join(' · ') });
      }
    }
    if (postings.length < 2) throw new Error(`Draft ${index + 1} needs at least two non-zero postings.`);
    const currencies = new Set(postings.map((item) => item.commodityCode));
    if (currencies.size !== 1) throw new Error('Mixed-currency drafts need explicit valuation rates. Use the standard FC posting CSV for those drafts.');
    return { id: draftId, date: iso, description: first['摘要（Description）'].trim(), source: 'accounting-csv', reference: first['参考号（Ref.)'].trim(), balancingCommodityCode: postings[0].commodityCode, postings };
  }) };
}
