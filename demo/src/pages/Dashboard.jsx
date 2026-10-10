import React from 'react';
import { Button, Panel, Table } from '../components.jsx';

export function Overview({ fc }) {
  const summary = fc.data.dashboard;
  return <>
    <section className="overview-intro"><div><h1>Your ledger,<br/><span>in clear view.</span></h1><p>One workspace. Your recorded financial picture.<br/>Recorded locally and calculated with precision.</p></div><div className="intro-status"><span className={`status-dot ${fc.data.reconciliation?.status === 'pass' ? 'good' : ''}`}/><strong>{fc.data.reconciliation?.status || 'Checking ledger'}</strong><small>Ledger reconciliation</small></div></section>
    <div className="stats">{[['Unposted drafts', summary?.draftCount], ['Posted entries', summary?.entryCount], ['Open lots', summary?.openLotCount], ['Workspace', fc.workspace.kind === 'sandbox' ? 'Sandbox' : 'Personal']].map(([label, value]) => <article key={label}><span>{label}</span><strong>{value ?? '—'}</strong></article>)}</div>
    <div className="dashboard-grid"><Panel className="wide" title="Financial position" description="Each commodity stays separate. Prices and rates are explicitly recorded." action={<Button onClick={() => fc.navigate('statements')}>View reports</Button>}><Table caption="Summary by commodity" rows={summary?.commoditySummaries} columns={[
      ['commodityCode', 'Commodity'], ['cash', 'Cash'], ['holdingCostBasis', 'Cost basis'], ['marketValue', 'Market value'], ['unrealizedPnL', 'Unrealized P&L'], ['missingPriceCount', 'Missing prices'],
    ]}/></Panel><Panel title="Next actions"><div className="quick-actions"><Button primary onClick={() => fc.navigate('journal')}>Record a transaction</Button><Button onClick={() => fc.navigate('planning')}>Review living plans</Button><Button onClick={() => fc.navigate('master')}>Manage accounts & prices</Button><Button onClick={() => fc.navigate('data', 'backup')}>Export or back up</Button></div></Panel><Panel title="Ledger checks" description="Deterministic checks from Finance Core."><div className="checks">{fc.data.reconciliation?.checks?.map((check) => <div key={check.id}><span className={`status-dot ${check.status === 'pass' ? 'good' : ''}`}/><div><strong>{check.id.replaceAll('_', ' ')}</strong><small>{check.detail}</small></div><span className="badge">{check.status}</span></div>)}</div></Panel><Panel title="Workspace tools" description={fc.readonly ? 'This workspace is archived and read-only.' : 'Changes belong only to this workspace.'}><div className="quick-actions"><Button disabled={fc.busy} onClick={() => fc.refresh()}>Refresh records</Button><Button disabled={!fc.data.undo || fc.busy || fc.readonly} onClick={() => fc.run((api, wid) => api.request('/api/v3/undo', { method: 'POST', body: { workspaceId: wid, undoToken: fc.data.undo.undoToken } }), 'Latest operation undone.')}>Undo latest operation</Button>{fc.workspace.kind === 'sandbox' && <Button disabled={fc.busy || fc.readonly || !summary || summary.entryCount !== 0 || summary.draftCount !== 0} onClick={() => { if (confirm('Load synthetic data into this empty sandbox?')) fc.ledger('/demo/load-synthetic', { method: 'POST' }, 'Synthetic example loaded.'); }}>Load synthetic example</Button>}</div></Panel></div>
  </>;
}

export function Reports({ fc }) {
  const tab = { positions: 'holdings', statements: 'statements', cashflow: 'cash-flow', taccounts: 'accounts' }[fc.route.view];
  return <><div className="report-context"><p>Posted Journal entries → T-accounts · Securities & positions · Cash flow → Statements</p><div className="actions"><Button disabled={fc.busy || fc.loading} onClick={() => fc.refresh()}>Refresh reports</Button><Button onClick={() => fc.navigate('journal')}>Open Journal</Button><Button onClick={() => fc.navigate('data', 'backup')}>Export records</Button></div></div>
    {tab === 'holdings' && <Panel title="Securities & positions" description="All supported security positions and open lots, derived from posted entries and explicit allocations. Missing prices require an explicit quote in Master data."><Table caption="Securities and open lots" rows={fc.data.holdings} columns={[
      ['lotId', 'Lot'], ['accountId', 'Account'], ['commodityCode', 'Commodity'], ['remainingUnits', 'Remaining units'], ['remainingCost', 'Remaining cost'], ['costCommodityCode', 'Cost commodity'], ['latestPrice', 'Latest price'], ['marketValue', 'Market value'], ['unrealizedPnL', 'Unrealized P&L'],
    ]}/></Panel>}
    {tab === 'statements' && <Panel title="Financial statements" description="Amounts are grouped by their balancing commodity."><Table rows={fc.data.statements} columns={[
      ['commodityCode', 'Commodity'], ['assets', 'Assets'], ['liabilities', 'Liabilities'], ['equity', 'Equity'], ['income', 'Income'], ['expenses', 'Expenses'], ['netIncome', 'Net income'],
    ]}/></Panel>}
    {tab === 'cash-flow' && <Panel title="Cash flow" description="Posted movements in cash accounts, by category."><Table rows={fc.data.cashFlow} columns={[['commodityCode', 'Commodity'], ['category', 'Category'], ['amount', 'Amount']]}/></Panel>}
    {tab === 'accounts' && <Panel title="T-accounts"><Table rows={fc.data.tAccounts} columns={[['accountCode', 'Code'], ['accountName', 'Account'], ['commodityCode', 'Commodity'], ['debit', 'Debit'], ['credit', 'Credit'], ['balance', 'Normal balance']]}/></Panel>}
  </>;
}
