import React, { useEffect, useState } from 'react';
import { Button, Empty, Field, Panel, Select, Table } from '../components.jsx';
import { latestCompletedMonth } from '../navigation.js';

export default function MonthlyReview({ fc }) {
  const report = fc.data.monthlyReview;
  const [month, setMonth] = useState(report?.month || latestCompletedMonth());
  const [currency, setCurrency] = useState('');
  useEffect(() => { setMonth(report?.month || latestCompletedMonth()); }, [report?.month]);
  const latest = report?.months.at(-1);
  const codes = latest?.currencies.map(row => row.commodityCode) || [];
  const selected = codes.includes(currency) ? currency : codes[0];
  const current = latest?.currencies.find(row => row.commodityCode === selected);
  const rows = report?.months.map(period => ({ ...period, ...period.currencies.find(row => row.commodityCode === selected) })) || [];
  return <div className="monthly-review" aria-busy={fc.loading}>
    <section className="review-toolbar">
      <div><span className="review-eyebrow">CLOSED-MONTH REVIEW</span><h2>Your month, in context.</h2><p>Three calendar months. Posted records only. No implicit currency conversion.</p></div>
      <form onSubmit={event => { event.preventDefault(); fc.navigate(fc.route.view, month, fc.route.segment || ''); }}>
        <Field label="Completed month"><input type="month" required min="0001-03" max={latestCompletedMonth()} value={month} onChange={event => setMonth(event.target.value)}/></Field>
        <Button primary type="submit" disabled={fc.busy || fc.loading}>Review month</Button>
      </form>
    </section>
    {report && <div className="review-boundary"><span className="badge">{report.status === 'ready' ? 'Ledger calculated' : 'Calculation blocked'}</span><p>External completeness: <strong>unknown</strong>. Reconciliation is not proof that all real-world transactions were recorded. Account roles use current Master data.</p></div>}
    {report?.calculationVersion === 'monthly-activity-v1' && <p>Classified opening stock and linked opening reversals are excluded from period activity ({report.openingEntryIds.length} entries in this window). Stock reports still retain them. Ordinary unclassified history is not changed.</p>}
    {report?.status === 'blocked' && <div className="notice error" role="alert">{report.coverage.invalidDateEntryCount} posted entries have unassignable dates. Correct their source dates through a reviewed data repair before using this report; no totals are delivered.</div>}
    {report?.status === 'ready' && <>
      <div className="review-period"><h3>{report.month} <small>compared with the previous two months</small></h3>{codes.length > 0 && <Select label="Currency" value={selected} options={codes.map(code => ({ value: code, label: code }))} onChange={setCurrency}/>}</div>
      {current ? <>
        <div className="review-metrics">{[['cashNet', 'Net cash movement', 'Cash received minus cash paid'], ['income', 'Recognized income', 'Not the same as cash received'], ['expenses', 'Recognized expenses', 'Not the same as cash paid']].map(([key, title, help]) => <article key={key}><span>{title}</span><strong>{current[key]} <small>{selected}</small></strong><p>{help}</p><div>Change from prior month <b>{current[key + 'Change'] ?? '—'}</b></div></article>)}</div>
        <Panel title="Three-month comparison" description="Cash uses net movement per entry and currency, excluding internal cash transfers. Income and expenses use posted valuation amounts in each entry's balancing currency.">
          <Table caption="Three-month cash and income comparison" rows={rows} rowKey="month" columns={[["month", 'Month'], ['cashInflow', 'Cash in'], ['cashOutflow', 'Cash out'], ['cashNet', 'Net cash'], ['income', 'Income'], ['expenses', 'Expenses'], ['netIncome', 'Net income']]}/>
        </Panel>
        <Panel title="Corrections and coverage" description="Reversals affect the month of the reversal, not a silent rewrite of the original month. Signed adjustments are already included in the totals above.">
          <Table caption="Adjustment and coverage counts" rows={rows} rowKey="month" columns={[["month", 'Month'], ['cashAdjustment', 'Cash adjustment'], ['incomeAdjustment', 'Income adjustment'], ['expenseAdjustment', 'Expense adjustment'], ['postedEntryCount', 'Entries'], ['reversalEntryCount', 'Reversals'], ['otherCategoryPostingCount', 'Unclassified postings']]}/>
        </Panel>
      </> : <Empty>No posted cash, income or expense movements in this window. This does not establish real-world completeness.</Empty>}
      <details className="review-method"><summary>Calculation and source revision</summary><p>{report.windowStart} inclusive → {report.windowEndExclusive} exclusive · Asia/Shanghai calendar months. Drafts, living snapshots and undated plans are not included. Loans, investments and debt repayment are not classified as income or expenses solely because cash moved.</p><code>{report.calculationVersion} · {report.revision}</code></details>
    </>}
    <div className="actions"><Button disabled={fc.busy || fc.loading} onClick={() => fc.refresh()}>Refresh this report</Button><Button onClick={() => fc.navigate('journal')}>Review Journal</Button></div>
  </div>;
}
