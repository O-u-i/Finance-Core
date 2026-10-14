import React from 'react';
import { Button, MonthPicker, Panel, Table } from '../components.jsx';
import { selectedRecordedMonth } from '../navigation.js';

export function Reports({ fc }) {
  const tab = { positions: 'holdings', statements: 'statements', cashflow: 'cash-flow', taccounts: 'accounts' }[fc.route.view];
  return <><div className="report-context"><p>Posted Journal entries → T-accounts · Securities & positions · Cash flow → Statements</p><div className="actions"><Button disabled={fc.busy || fc.loading} onClick={() => fc.refresh()}>Refresh reports</Button><Button onClick={() => fc.navigate('journal')}>Open Journal</Button><Button onClick={() => fc.navigate('data', 'backup')}>Export records</Button></div></div>
    {tab === 'holdings' && <Panel title="Securities & positions" description="All supported security positions and open lots, derived from posted entries and explicit allocations. Missing prices require an explicit quote in Master data."><Table caption="Securities and open lots" rows={fc.data.holdings} columns={[
      ['lotId', 'Lot'], ['accountId', 'Account'], ['commodityCode', 'Commodity'], ['remainingUnits', 'Remaining units'], ['remainingCost', 'Remaining cost'], ['costCommodityCode', 'Cost commodity'], ['latestPrice', 'Latest price'], ['marketValue', 'Market value'], ['unrealizedPnL', 'Unrealized P&L'],
    ]}/></Panel>}
    {tab === 'statements' && <Panel title="Financial statements" description="Stock includes opening balances. Amounts are grouped by balancing commodity; opening stock is not income or expense."><Table rows={fc.data.statements} columns={[
      ['commodityCode', 'Commodity'], ['assets', 'Assets'], ['liabilities', 'Liabilities'], ['equity', 'Equity'], ['income', 'Income'], ['expenses', 'Expenses'], ['netIncome', 'Net income'],
    ]}/></Panel>}
    {tab === 'cash-flow' && <Panel title="Current-period cash flow" description="Posted cash activity for the selected calendar month. Classified opening balances and their linked reversals are excluded; old unclassified Journal records keep their original meaning.">
      <MonthPicker fc={fc} value={selectedRecordedMonth(fc.route)} label="Activity month"/>
      <Table caption="Period cash activity" rows={fc.data.activityCashFlow?.activity} columns={[[ 'commodityCode','Commodity'],['category','Category'],['amount','Amount']]}/>
      <details className="opening-effects"><summary>Opening stock effects · excluded from period activity</summary><Table caption="Opening cash effects" rows={fc.data.activityCashFlow?.openingEffects} columns={[[ 'commodityCode','Commodity'],['category','Category'],['amount','Stock change']]}/></details>
      <small>{fc.data.activityCashFlow?.calculationVersion} · External completeness unknown.</small>
    </Panel>}
    {tab === 'accounts' && <Panel title="T-accounts"><Table rows={fc.data.tAccounts} columns={[['accountCode', 'Code'], ['accountName', 'Account'], ['commodityCode', 'Commodity'], ['debit', 'Debit'], ['credit', 'Credit'], ['balance', 'Normal balance']]}/></Panel>}
  </>;
}
