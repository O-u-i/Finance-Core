const collator = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });

// Presentation ordering only: never convert a financial value to Number.
export function compareValues(left, right) {
  const a = String(left), b = String(right), decimal = /^-?\d+(?:\.\d+)?$/;
  if (!decimal.test(a) || !decimal.test(b)) return collator.compare(a, b);
  const negativeA = a.startsWith('-') && /[1-9]/.test(a), negativeB = b.startsWith('-') && /[1-9]/.test(b);
  if (negativeA !== negativeB) return negativeA ? -1 : 1;
  const [integerA, fractionA = ''] = a.replace('-', '').split('.');
  const [integerB, fractionB = ''] = b.replace('-', '').split('.');
  const x = integerA.replace(/^0+(?=\d)/, ''), y = integerB.replace(/^0+(?=\d)/, '');
  const length = Math.max(fractionA.length, fractionB.length);
  const result = x.length - y.length || (x < y ? -1 : x > y ? 1 : 0)
    || (fractionA.padEnd(length, '0') < fractionB.padEnd(length, '0') ? -1 : fractionA.padEnd(length, '0') > fractionB.padEnd(length, '0') ? 1 : 0);
  return negativeA ? -result : result;
}

export function recordValue(row, column) {
  const value = column[3] ? column[3](row) : row[column[0]];
  return Array.isArray(value) ? value.join(', ') : value;
}

export function orderedRecords(rows, columns, key, descending = false, query = '') {
  const column = columns.find(item => item[0] === key), text = query.trim().toLocaleLowerCase();
  const filtered = rows.filter(row => !text || columns.some(item => String(recordValue(row, item) ?? '').toLocaleLowerCase().includes(text)));
  return column ? [...filtered].sort((a, b) => {
    const left = recordValue(a, column), right = recordValue(b, column);
    if (left == null || right == null) return left == null ? right == null ? 0 : 1 : -1;
    return compareValues(left, right) * (descending ? -1 : 1);
  }) : filtered;
}
