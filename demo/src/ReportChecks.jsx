import React, { useState } from 'react';
import { Button, Dialog, Table } from './components.jsx';

const titles = {
  OPENING_BASELINE_UNCONFIRMED: 'Opening baseline not confirmed',
  OPENING_BALANCE_MISSING: 'Opening month-end balance missing',
  CLOSING_BALANCE_MISSING: 'Closing month-end balance missing',
  OWNERSHIP_UNCLASSIFIED: 'Investment ownership not confirmed',
  TRANSFER_TOTALS_UNCONFIRMED: 'Cross-segment transfer totals not confirmed',
  TRANSFER_TOTALS_MISMATCH: 'Cross-segment transfer totals do not match',
  ASSET_VALUATION_MISSING: 'Asset month-end value missing',
  LIABILITY_BENEFICIARY_UNKNOWN: 'Liability beneficiary not classified',
  ACCOUNT_CLASSIFICATION_PENDING: 'Account classification not confirmed',
  ENDED_ACCOUNT_UNSETTLED: 'Ended account balance needs review',
  INTEREST_ACCRUAL_REVIEW_REQUIRED: 'Agreed interest needs review',
};

export default function ReportChecks({ report, accounts = [], parties = [], assets = [] }) {
  const [open, setOpen] = useState(false);
  if (!report) return <p>Financial report is not available.</p>;
  const issues = report.issues || [];
  const names = new Map([...accounts.map(item => [item.id, `${item.code} · ${item.name}`]), ...parties.map(item => [item.id, item.name]), ...assets.map(item => [item.id, item.name]), ['personal', 'Reporting baseline']]);
  return <>
    <div className={`notice coverage-summary ${report.coverage.complete ? 'success' : ''}`} role="status">
      <div><strong>{report.coverage.complete ? 'Recorded inputs reconciled' : 'Month-end report incomplete'}</strong><p>As of {report.asOf}. Actual-date balances are separate; missing inputs stay unknown.</p>{report.coverage.needsReview && <p>Inputs changed after a confirmed close. Review the checks before closing again.</p>}</div>
      <Button type="button" onClick={() => setOpen(true)}>Review data checks ({issues.length})</Button>
    </div>
    {open && <Dialog title="Month-end data checks" onClose={() => setOpen(false)}>
      <p>These checks apply to the formal report dated {report.asOf}, not to whether a later actual-date balance was saved. Incomplete inputs are not treated as zero. Investment pool ownership and transfers require their own confirmation; external completeness remains unknown.</p>
      <Table caption="Report checks" rows={issues.map((issue, index) => ({ ...issue, id: index, title: titles[issue.code] || issue.code.toLowerCase().replaceAll('_', ' '), subject: names.get(issue.subjectId) || (/^[A-Z]{3,8}$/.test(issue.subjectId) ? issue.subjectId : 'Related record') }))} columns={[
        ['title', 'Check'], ['subject', 'Account or reporting area'], ['message', 'Explanation'],
        ['details', 'Technical details', issue => <details><summary>Reference</summary><p><code>{issue.code}</code></p><p>{issue.subjectId}</p></details>],
      ]}/>
    </Dialog>}
  </>;
}
