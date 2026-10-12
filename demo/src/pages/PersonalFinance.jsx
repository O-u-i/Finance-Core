import React, { useState } from 'react';
import { id } from '../api.js';
import { selectedMonth } from '../navigation.js';
import { Button, Field, MonthPicker, Panel, ResourceForm, Table, Tabs } from '../components.jsx';

const priorMonth = (month) => {
  const [year, number] = month.split('-').map(Number);
  return `${number === 1 ? year - 1 : year}-${String(number === 1 ? 12 : number - 1).padStart(2, '0')}`;
};
const currentObservation = (fc, kind, subject, month) => {
  const observations = fc.data.observations || [];
  const replaced = new Set(observations.map(item => item.supersedes).filter(Boolean));
  return observations.find(item => !item.observedDate && item.kind === kind && item.subjectId === subject && item.month === month && !replaced.has(item.id));
};

function Coverage({ report }) {
  if (!report) return <p>Financial report is not available.</p>;
  return <div className={`notice ${report.coverage.complete ? 'success' : ''}`} role="status">
    <p><strong>{report.coverage.complete ? 'Recorded inputs reconciled' : 'Incomplete financial inputs'}</strong> · {report.asOf} · currencies remain separate. External completeness is unknown.</p>
    {report.coverage.needsReview && <p>A confirmed close or its preceding inputs changed. Review and append a correction.</p>}
    {!!report.issues.length && <ul>{report.issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.code} · {issue.subjectId}: {issue.message}</li>)}</ul>}
  </div>;
}

export function PersonalOverview({ fc }) {
  const [perspective, setPerspective] = useState(['investment','living'].includes(fc.route.tab) ? fc.route.tab : 'consolidated');
  // Visibility only: financial totals/revisions remain entirely backend-owned.
  const visible = code => {
    const commodity = fc.data.commodities?.find(item => item.code === code);
    return commodity?.status !== 'inactive' || commodity.inUse !== false;
  };
  if (fc.migrationRequired) return <Panel className="financial-overview" title="Financial overview" description="Legacy Vault readouts. Pool assets include third-party interests; these values are not reconciled personal net worth.">
    <Table caption="Legacy balances by currency" rows={fc.data.world?.commoditySummaries.filter(item => visible(item.commodityCode))} columns={[[ 'commodityCode','Currency'],['livingBalance','Recorded Living balance'],['investmentMarketValue','Investment pool value']]}/>
    <Table caption="Investment ledger readouts" rows={fc.data.legacyDashboard?.commoditySummaries.filter(item => visible(item.commodityCode))} columns={[[ 'commodityCode','Currency'],['cash','Ledger cash'],['bookValue','Book value'],['marketValue','Market value'],['missingPriceCount','Missing prices']]}/>
  </Panel>;
  const report = fc.data.personalReport;
  const currencies = (report?.currencies || []).filter(item => visible(item.currency));
  const rows = currencies.map(item => ({ currency: item.currency, ...item.totals }));
  const columns = perspective === 'investment' ? [['currency','Currency'],['investmentAssets','Pool assets (market)'],['investmentLiabilities','Pool liabilities'],['residualEquity','Residual equity'],['ownerInvestmentValue','Your economic stake']]
    : perspective === 'living' ? [['currency','Currency'],['livingAssets','Financial assets'],['livingLiabilities','Personal liabilities'],['nonFinancialAssets','Manual asset values'],['openingCash','Opening cash'],['closingCash','Closing cash']]
      : [['currency','Currency'],['knownPersonalSubtotal','Known-input subtotal (may be partial)'],['personalNetWorth','Reconciled personal net worth'],['ownerInvestmentValue','Investment economic stake'],['livingLiabilities','Personal liabilities']];
  return <><Panel className="financial-overview" title="Financial overview" description="Read-only month-end dashboard. Pool assets are not personal wealth; currencies and third-party interests remain separate."><Tabs items={[[ 'consolidated','Consolidated'],['investment','Investment'],['living','Living']]} value={perspective} onChange={setPerspective}/><Coverage report={report}/><Table caption={`${perspective} financial overview`} rows={rows} columns={columns}/></Panel>
    {currencies.filter(item => item.ownerships.length).map(item => <Panel className="financial-overview" key={item.currency} title={`${item.currency} · beneficial ownership`}><Table rows={item.ownerships} columns={[[ 'partyId','Beneficiary', value => fc.data.parties?.find(party => party.id === value.partyId)?.name || 'Unknown beneficiary'],['claims','Accrued claims'],['residualShare','Residual share'],['residualValue','Residual value (may be negative)'],['economicValue','Economic value']]}/></Panel>)}
  </>;
}

function ObservationForm({ fc, kind, subject, currency, label }) {
  const month = selectedMonth(fc.route), current = currentObservation(fc, kind, subject, month);
  const previous = currentObservation(fc, kind, subject, priorMonth(month));
  const [amount, setAmount] = useState(current?.amount ?? previous?.amount ?? '');
  const [confirmed, setConfirmed] = useState(false), [source, setSource] = useState(current?.source || ''), [reason, setReason] = useState('');
  return <form className="resource-form" onChangeCapture={event => fc.markDirty(event.currentTarget)} onSubmit={async event => {
    event.preventDefault(); const form = event.currentTarget;
    const result = await fc.ledger('/monthly-observations', { method:'POST', body: { id:id(kind), subjectId:subject, month, kind, currency, amount, source, confirmed:true, ...(current ? { supersedes:current.id, reason } : {}) } }, 'Monthly observation appended; no Journal entry was created.');
    if (result) { fc.clean(form); setConfirmed(false); }
  }}><fieldset disabled={fc.busy || fc.readonly}><div className="form-grid"><Field label={`${label} · ${currency}`}><input inputMode="decimal" value={amount} required onChange={event => setAmount(event.target.value)}/></Field><Field label="Valuation / statement source"><input value={source} required onChange={event => setSource(event.target.value)}/></Field>{current && <Field label="Correction reason"><input value={reason} required onChange={event => setReason(event.target.value)}/></Field>}</div>
    <p>{current ? `Current observation is ${current.confirmed ? 'confirmed' : 'pending'}; saving appends a correction.` : previous ? 'Previous-month value is a suggestion, not a new observation.' : 'No opening or prior value is known. Enter the observed amount explicitly.'}</p>
    <label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/> I observed and confirm this value at {month} month end.</label><Button primary disabled={!confirmed}>Confirm {kind}</Button></fieldset></form>;
}

export function AssetsLiabilities({ fc }) {
  const partyOptions = (fc.data.parties || []).map(item => ({ value:item.id,label:item.name }));
  const currencyOptions = (fc.data.commodities || []).filter(item => item.kind === 'currency').map(item => ({ value:item.code,label:item.code }));
  return <><Panel title="Non-financial asset registry" description="Identity and acquisition cost are separate from manually confirmed market value. No depreciation or live valuation is inferred."><MonthPicker fc={fc}/><ResourceForm fc={fc} initial={{ ownershipShare:'1' }} fields={[[ 'name','Asset name'],['assetType','Asset type'],['currency','Currency','text',currencyOptions],['purchasedDate','Purchase date','date'],['purchaseCost','Purchase cost'],['ownerPartyId','Beneficiary','text',partyOptions],['ownershipShare','Ownership share (0–1)'],['linkedAccountId','Linked Living asset account (optional)'],['valuationMethod','Valuation basis','text',[{value:'manual_market_value',label:'Manual market value'},{value:'cost',label:'Manually confirmed cost'}]],['note','Note']]} submitLabel="Register asset" onSave={values => fc.ledger('/non-financial-assets',{method:'POST',body:{...values,id:id('asset'),linkedAccountId:values.linkedAccountId || null}},'Asset registered; enter its month-end valuation separately.')}/></Panel>
    {(fc.data.assets || []).map(item => <Panel key={item.id} title={item.name} description={`${item.assetType} · cost ${item.purchaseCost} ${item.currency} · owner ${item.ownerPartyId} × ${item.ownershipShare}`}><ObservationForm key={`${item.id}/${selectedMonth(fc.route)}/${currentObservation(fc,'valuation',item.id,selectedMonth(fc.route))?.id || ''}`} fc={fc} kind="valuation" subject={item.id} currency={item.currency} label="Whole-asset manual value"/>{!item.disposedMonth && <Button disabled={fc.busy || fc.readonly} onClick={() => { if (confirm(`Record disposal after ${selectedMonth(fc.route)}? The current month's value must still be confirmed.`)) fc.ledger(`/non-financial-assets/${encodeURIComponent(item.id)}`,{method:'PUT',body:{...item,disposedMonth:selectedMonth(fc.route)}},'Disposal month recorded.'); }}>Record disposal month</Button>}</Panel>)}
    <Panel title="Personal liabilities" description="Liabilities use actual-date balance records, not a second transaction system."><Table rows={(fc.data.financialAccounts || []).filter(item => item.segment === 'living' && item.type === 'liability')} columns={[[ 'name','Liability'],['ownerPartyId','Debtor'],['allowedCommodityCodes','Currency']]}/><Button onClick={() => fc.navigate('balances','','living')}>Record liability balances</Button></Panel></>;
}

function TransferTotals({ fc, month }) {
  const currencies = (fc.data.commodities || []).filter(item => item.kind === 'currency');
  return currencies.map(item => <TransferForm key={`${item.code}/${month}/${currentObservation(fc,'transfer',item.code,month)?.id || ''}`} fc={fc} currency={item.code} month={month}/>);
}
function TransferForm({ fc, currency, month }) {
  const current = currentObservation(fc,'transfer',currency,month);
  const [confirmed,setConfirmed] = useState(false);
  return <Panel title={`${currency} · monthly cross-segment totals`} description="Incoming/outgoing totals are compared with tagged posted Investment cash movements. Fees and transit are shown separately and never used to force a match."><form onChangeCapture={event => fc.markDirty(event.currentTarget)} onSubmit={async event => {
    event.preventDefault(); const form = event.currentTarget, values = Object.fromEntries(new FormData(form));
    const result = await fc.ledger('/monthly-observations',{method:'POST',body:{id:id('transfer'),subjectId:currency,month,kind:'transfer',currency,...values,confirmed:true,...(current ? {supersedes:current.id} : {})}},'Monthly transfer totals confirmed.');
    if(result) { fc.clean(form); setConfirmed(false); }
  }}><fieldset disabled={fc.busy || fc.readonly}><div className="form-grid">{[['incoming','Incoming to Living'],['outgoing','Outgoing from Living'],['fees','Transfer fees (separate)'],['inTransit','In transit at month end']].map(([name,label]) => <Field key={name} label={label}><input name={name} required inputMode="decimal" defaultValue={current?.[name] ?? ''}/></Field>)}<Field label="Confirmation source"><input name="source" required defaultValue={current?.source || ''}/></Field>{current && <Field label="Correction reason"><input name="reason" required/></Field>}</div><label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/> Confirm these totals, including any explicit zeros.</label><Button primary disabled={!confirmed}>Confirm totals</Button></fieldset></form></Panel>;
}

export function PersonalMonthlyReview({ fc, month = selectedMonth(fc.route) }) {
  const report = fc.data.personalReport;
  const rows = (report?.currencies || []).map(item => ({currency:item.currency,...item.totals}));
  const latest = (fc.data.closes || []).filter(item => item.month === month).at(-1);
  return <><Panel title={fc.route.segment === 'investment' ? 'Investment monthly review' : 'Legacy Living month-end review'} description="Balance movement is not income, consumption or savings. Unexplained change remains explicitly unexplained."><MonthPicker fc={fc} value={month}/><Coverage report={report}/><Table rows={rows} columns={fc.route.segment === 'investment' ? [[ 'currency','Currency'],['investmentIncome','Ledger income'],['investmentExpenses','Ledger expenses'],['residualEquity','Month-end residual equity'],['ownerInvestmentValue','Owner economic stake']] : [[ 'currency','Currency'],['openingCash','Opening cash'],['closingCash','Closing cash'],['ledgerTransferIncoming','Tagged incoming'],['ledgerTransferOutgoing','Tagged outgoing'],['transferIncomingDifference','Incoming difference'],['transferOutgoingDifference','Outgoing difference'],['unexplainedCashChange','Unexplained cash change']]}/>{fc.route.segment === 'investment' && <Button onClick={() => fc.navigate('legacyreview',month,'investment')}>Read legacy three-month Journal report</Button>}</Panel>
    {fc.route.segment !== 'investment' && <TransferTotals fc={fc} month={month}/>}
    <Panel title="Immutable month close" description="Confirmation rechecks the exact input revision atomically. Corrections retain the original result and require a reason."><form onChangeCapture={event => fc.markDirty(event.currentTarget)} onSubmit={async event => {
      event.preventDefault(); const form = event.currentTarget;
      const result = await fc.ledger('/monthly-closes',{method:'POST',body:{month,expectedRevision:report.revision,reason:new FormData(form).get('reason'),confirmed:true,...(latest ? {supersedes:latest.id} : {})}},'Month close appended. Earlier results remain immutable.');
      if(result) { fc.clean(form); form.reset(); }
    }}><fieldset disabled={fc.busy || fc.readonly}><Field label="Close / correction reason"><input name="reason" required/></Field><label><input type="checkbox" required/> I reviewed balances, dated prices, liabilities, beneficiary agreements and reconciliation.</label><Button primary disabled={!report?.coverage.complete}>{latest ? 'Append corrected close' : 'Confirm month close'}</Button></fieldset></form><Table rows={fc.data.closes} columns={[[ 'month','Month'],['revision','Close version'],['reason','Reason'],['supersedes','Corrects'],['confirmedAt','Confirmed at']]}/></Panel></>;
}
