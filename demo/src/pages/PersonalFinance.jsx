import React, { useState } from 'react';
import { id } from '../api.js';
import { selectedMonth } from '../navigation.js';
import { Button, Dialog, Empty, Field, Help, ListControls, MonthPicker, Panel, RecordRow, ResourceForm, Status, SummaryCards, Table, Tabs } from '../components.jsx';
import { orderedRecords } from '../records.js';
import ReportChecks from '../ReportChecks.jsx';

const priorMonth = (month) => {
  const [year, number] = month.split('-').map(Number);
  return `${number === 1 ? year - 1 : year}-${String(number === 1 ? 12 : number - 1).padStart(2, '0')}`;
};
export const currentObservation = (fc, kind, subject, month) => {
  const observations = fc.data.observations || [];
  const replaced = new Set(observations.map(item => item.supersedes).filter(Boolean));
  return observations.find(item => !item.observedDate && item.kind === kind && item.subjectId === subject && item.month === month && !replaced.has(item.id));
};

function Coverage({ report, fc }) { return <ReportChecks report={report} accounts={fc?.data.financialAccounts} parties={fc?.data.parties} assets={fc?.data.assets}/>; }

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
  return <><Panel className="financial-overview" title="Financial overview" description="Read-only month-end dashboard. Pool assets are not personal wealth; currencies and third-party interests remain separate."><Tabs items={[[ 'consolidated','Consolidated'],['investment','Investment'],['living','Living']]} value={perspective} onChange={setPerspective}/><Coverage report={report} fc={fc}/><SummaryCards label={`${perspective} financial overview`} rows={rows} columns={columns}/></Panel>
    {currencies.filter(item => item.ownerships.length).map(item => <Panel className="financial-overview" key={item.currency} title={`${item.currency} · beneficial ownership`}><Table rows={item.ownerships} columns={[[ 'partyId','Beneficiary', value => fc.data.parties?.find(party => party.id === value.partyId)?.name || 'Unknown beneficiary'],['claims','Accrued claims'],['residualShare','Residual share'],['residualValue','Residual value (may be negative)'],['economicValue','Economic value']]}/></Panel>)}
  </>;
}

function ValuationForm({ fc, asset, month, current, save }) {
  const previous = currentObservation(fc, 'valuation', asset.id, priorMonth(month));
  const [amount, setAmount] = useState(current?.amount ?? previous?.amount ?? '');
  const [confirmed, setConfirmed] = useState(false), [source, setSource] = useState(current?.source || ''), [reason, setReason] = useState('');
  const [note, setNote] = useState(current?.note || '');
  return <form className="resource-form" onChangeCapture={event => fc.markDirty(event.currentTarget)} onSubmit={async event => {
    event.preventDefault(); const form = event.currentTarget;
    const result = await save('/monthly-observations', { method:'POST', body: { id:id('valuation'), subjectId:asset.id, month, kind:'valuation', currency:asset.currency, amount, source, note, confirmed:true, ...(current ? { supersedes:current.id, reason } : {}) } }, `Valuation saved for ${month}. No Journal entry was created.`);
    if (result) { fc.clean(form); setConfirmed(false); }
  }}><fieldset disabled={fc.busy || fc.readonly}><div className="form-grid"><Field label={`Whole-asset value · ${asset.currency}`}><input name="amount" inputMode="decimal" value={amount} required onChange={event => { setAmount(event.target.value); setConfirmed(false); }}/></Field><Field label="Valuation source"><input name="source" value={source} maxLength={500} required onChange={event => { setSource(event.target.value); setConfirmed(false); }}/></Field>{current && <Field label="Correction reason"><input name="reason" value={reason} required onChange={event => { setReason(event.target.value); setConfirmed(false); }}/></Field>}<Field label="Note"><textarea name="note" rows={2} maxLength={4000} value={note} onChange={event => { setNote(event.target.value); setConfirmed(false); }}/></Field></div>
    <div className="valuation-help"><Help label="Valuation source">{current ? 'Saving appends a correction and keeps the earlier valuation. Enter a correction reason.' : previous ? 'The previous month is only a suggestion. Confirm this month’s value independently.' : 'No value is recorded for this month. Purchase cost is not an automatic valuation.'}</Help></div>
    <div className="actions"><label className="balance-confirmation"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/> I confirm this value at {month} month end, not today’s value.</label><Button type="submit" primary disabled={!confirmed}>{fc.busy ? 'Saving…' : 'Save valuation'}</Button></div></fieldset></form>;
}

function AssetCard({ fc, asset, month }) {
  const current = currentObservation(fc, 'valuation', asset.id, month);
  const [feedback, setFeedback] = useState(null), [layer, setLayer] = useState('');
  const owner = fc.data.parties?.find(party => party.id === asset.ownerPartyId)?.name || 'Unknown beneficiary';
  const disposalScope = `disposal:${asset.id}`;
  const closeLayer = () => { if (!fc.busy && fc.canLeave()) { fc.discardChanges(); setLayer(''); } };
  const save = async (path, options, message) => {
    setFeedback(null);
    const result = await fc.run(async (api, workspaceId) => {
      try { return await api.ledger(workspaceId, path, options); }
      catch (error) { setFeedback({ error: true, text: error.message }); throw error; }
    }, message);
    if (result) setFeedback({ text: message });
    return result;
  };
  return <><RecordRow className="asset-record" title={asset.name} meta={<>{asset.assetType} · Valuation {month}{asset.disposedMonth && <span> · Disposed {asset.disposedMonth}</span>}</>}
    amount={current?.amount ?? 'Unknown'} currency={asset.currency} status={<Status state={asset.disposedMonth ? 'error' : current?.confirmed ? 'success' : 'warning'}>{asset.disposedMonth ? 'Disposed' : current?.confirmed ? 'Confirmed' : 'Pending'}</Status>}
    actions={<><Button disabled={fc.busy} onClick={() => setLayer('details')}>Details</Button>{(!asset.disposedMonth || month <= asset.disposedMonth) && <Button disabled={fc.busy || fc.readonly} onClick={() => setLayer('valuation')}>{current ? 'Edit valuation' : 'Record valuation'}</Button>}</>}/>
    {layer === 'details' && <Dialog title={asset.name} onClose={closeLayer}><div className="detail-context"><Status>Read only</Status></div>
      <dl className="record-details"><dt>Asset type</dt><dd>{asset.assetType}</dd><dt>Purchase date</dt><dd>{asset.purchasedDate}</dd><dt>Purchase cost</dt><dd>{asset.purchaseCost} {asset.currency}</dd><dt>Beneficiary</dt><dd>{owner}</dd><dt>Ownership share</dt><dd>{asset.ownershipShare}</dd>
        <dt>Saved valuation · {month}</dt><dd>{current?.amount ?? 'Unknown'} {asset.currency} · {current?.confirmed ? 'Confirmed' : 'Pending'}</dd><dt>Source</dt><dd>{current?.source || 'Unknown'}</dd>{current?.note && <><dt>Valuation note</dt><dd className="note-text">{current.note}</dd></>}{asset.disposedMonth && <><dt>Disposal recorded</dt><dd>{asset.disposedMonth}</dd></>}
      </dl>{asset.note && <div className="saved-note"><h3>Note</h3><p className="note-text">{asset.note}</p></div>}
      {!asset.disposedMonth && <Button disabled={fc.busy || fc.readonly} onClick={() => setLayer('disposal')}>Record disposal</Button>}
    </Dialog>}
    {layer === 'valuation' && <Dialog title={`Valuation · ${asset.name}`} onClose={closeLayer} dismissible={!fc.busy}>
      <p className="detail-context">{month} · {asset.currency} · Value at month end</p><ValuationForm key={`${month}/${current?.id || ''}`} fc={fc} asset={asset} month={month} current={current} save={save}/>
      {feedback && <p className={`notice ${feedback.error ? 'error' : 'success'}`} role={feedback.error ? 'alert' : 'status'}>{feedback.text}</p>}
    </Dialog>}
    {layer === 'disposal' && <Dialog title={`Record disposal · ${asset.name}`} onClose={closeLayer} dismissible={!fc.busy}>
      <p>This records the last month included in the asset register, not a deletion or a cash receipt. Its valuation for that month is still needed; later months exclude it.</p>
      <form onChangeCapture={() => fc.markDirty(disposalScope)} onSubmit={async event => {
        event.preventDefault(); const form = event.currentTarget, disposedMonth = new FormData(form).get('disposedMonth');
        const result = await save(`/non-financial-assets/${encodeURIComponent(asset.id)}`, { method: 'PUT', body: { ...asset, disposedMonth } }, `Disposal recorded for ${disposedMonth}. Earlier valuations and Note are retained.`);
        if (result) { fc.clean(disposalScope); setLayer(''); }
      }}><fieldset disabled={fc.busy || fc.readonly}><Field label="Last included month"><input name="disposedMonth" type="month" min={asset.purchasedDate.slice(0, 7)} defaultValue={month} required/></Field>
        <div className="actions"><Button type="submit" primary>Save disposal</Button><Button type="button" onClick={closeLayer}>Cancel</Button></div>
      </fieldset></form>{feedback?.error && <p className="notice error" role="alert">{feedback.text}</p>}
    </Dialog>}
  </>;
}

export function AssetsLiabilities({ fc }) {
  const month = selectedMonth(fc.route), monthEnd = new Date(`${month}-01T00:00:00Z`);
  monthEnd.setUTCMonth(monthEnd.getUTCMonth() + 1, 0);
  const [query, setQuery] = useState(''), [sort, setSort] = useState('name'), [descending, setDescending] = useState(false);
  const [registering, setRegistering] = useState(false);
  const closeRegistry = () => { if (fc.canLeave()) { fc.discardChanges(); setRegistering(false); } };
  const partyOptions = (fc.data.parties || []).map(item => ({ value:item.id,label:item.name }));
  const currencyOptions = (fc.data.commodities || []).filter(item => item.kind === 'currency' && item.status === 'active').map(item => ({ value:item.code,label:item.code }));
  const linkedOptions = [{ value: '', label: 'No linked account' }, ...(fc.data.financialAccounts || []).filter(item => item.segment === 'living' && item.type === 'asset' && item.status === 'active').map(item => ({ value: item.id, label: `${item.code} · ${item.name}` }))];
  const columns = [['name', 'Asset name'], ['assetType', 'Asset type'], ['currency', 'Currency'], ['purchasedDate', 'Purchase date'], ['purchaseCost', 'Purchase cost']];
  const visibleAssets = orderedRecords(fc.data.assets || [], columns, sort, descending, query);
  return <>
    {registering && <Dialog title="Register asset" onClose={closeRegistry} dismissible={!fc.busy}><ResourceForm fc={fc} initial={{ ownershipShare:'1' }} fields={[[ 'name','Asset name'],['assetType','Asset type'],['currency','Currency','text',currencyOptions],['purchasedDate','Purchase date','date'],['purchaseCost','Purchase cost'],['ownerPartyId','Beneficiary','text',partyOptions],['ownershipShare','Ownership share (0–1)'],['linkedAccountId','Linked Living asset account (optional)','text',linkedOptions],['valuationMethod','Valuation basis','text',[{value:'manual_market_value',label:'Manual market value'},{value:'cost',label:'Manually confirmed cost'}]],['note','Note','textarea']]} submitLabel="Register asset" onSave={async values => { const result = await fc.ledger('/non-financial-assets',{method:'POST',body:{...values,id:id('asset'),linkedAccountId:values.linkedAccountId || null}},'Asset registered. Add a valuation separately.'); if(result) setRegistering(false); return result; }}/></Dialog>}
    <Panel className="asset-valuations" title="Asset valuations" description={`Whole-asset values at ${monthEnd.toISOString().slice(0, 10)}, not today. Purchase cost is not an automatic valuation. Unknown is not zero.`} action={<Button primary disabled={fc.busy || fc.readonly} onClick={() => setRegistering(true)}>Register asset</Button>}>
      <MonthPicker fc={fc} label="Valuation month"/><ListControls label="Assets" columns={columns} sort={sort} setSort={setSort} descending={descending} setDescending={setDescending} query={query} setQuery={setQuery}/>
      <div className="workbench-records">{visibleAssets.map(item => <AssetCard key={item.id} fc={fc} asset={item} month={month}/>)}</div>{!visibleAssets.length && <Empty>{fc.data.assets?.length ? 'No assets match these filters.' : 'No assets registered.'}</Empty>}
    </Panel>
    <Panel title="Personal liabilities" description="Liabilities use actual-date balance records, not a second transaction system."><Table rows={(fc.data.financialAccounts || []).filter(item => item.segment === 'living' && item.type === 'liability')} columns={[[ 'name','Liability'],['ownerPartyId','Debtor', item => fc.data.parties?.find(party => party.id === item.ownerPartyId)?.name || 'Unknown beneficiary'],['allowedCommodityCodes','Currency']]}/><Button onClick={() => fc.navigate('balances','','living')}>Record liability balances</Button></Panel></>;
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
  }}><fieldset disabled={fc.busy || fc.readonly}><div className="form-grid">{[['incoming','Incoming to Living'],['outgoing','Outgoing from Living'],['fees','Transfer fees (separate)'],['inTransit','In transit at month end']].map(([name,label]) => <Field key={name} label={label}><input name={name} required inputMode="decimal" defaultValue={current?.[name] ?? ''}/></Field>)}<Field label="Confirmation source"><input name="source" required defaultValue={current?.source || ''}/></Field>{current && <Field label="Correction reason"><input name="reason" required/></Field>}<Field label="Note"><textarea name="note" rows={2} maxLength={4000} defaultValue={current?.note || ''}/></Field></div><label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/> Confirm these totals, including any explicit zeros.</label><Button primary disabled={!confirmed}>Confirm totals</Button></fieldset></form></Panel>;
}

export function PersonalMonthlyReview({ fc, month = selectedMonth(fc.route) }) {
  const report = fc.data.personalReport;
  const rows = (report?.currencies || []).map(item => ({currency:item.currency,...item.totals}));
  const latest = (fc.data.closes || []).filter(item => item.month === month).at(-1);
  return <div className="monthly-review"><Panel className="monthly-review-summary" action={<MonthPicker fc={fc} value={month} label="Review month"/>} title={fc.route.segment === 'investment' ? 'Investment monthly review' : 'Legacy Living month-end review'} description="Balance movement is not income, consumption or savings. Unexplained change remains explicitly unexplained."><p className="review-boundary-copy">Balance change is not income or spending. External completeness remains unknown.</p><Coverage report={report} fc={fc}/><SummaryCards controls={rows.length > 3} label="Monthly review by currency" rows={rows} columns={fc.route.segment === 'investment' ? [[ 'currency','Currency'],['investmentIncome','Ledger income'],['investmentExpenses','Ledger expenses'],['residualEquity','Month-end residual equity'],['ownerInvestmentValue','Owner economic stake']] : [[ 'currency','Currency'],['openingCash','Opening cash'],['closingCash','Closing cash'],['ledgerTransferIncoming','Tagged incoming'],['ledgerTransferOutgoing','Tagged outgoing'],['transferIncomingDifference','Incoming difference'],['transferOutgoingDifference','Outgoing difference'],['unexplainedCashChange','Unexplained cash change']]}/>{fc.route.segment === 'investment' && <Button onClick={() => fc.navigate('legacyreview',month,'investment')}>Read three-month activity report</Button>}</Panel>
    {fc.route.segment !== 'investment' && <TransferTotals fc={fc} month={month}/>}
    <Panel className="review-close" title="Immutable month close" description="Confirmation rechecks the exact input revision atomically. Corrections retain the original result and require a reason."><p className="review-boundary-copy">Close only after every required input is reconciled. Earlier confirmed results are retained.</p><form onChangeCapture={event => fc.markDirty(event.currentTarget)} onSubmit={async event => {
      event.preventDefault(); const form = event.currentTarget;
      const result = await fc.ledger('/monthly-closes',{method:'POST',body:{month,expectedRevision:report.revision,reason:new FormData(form).get('reason'),confirmed:true,...(latest ? {supersedes:latest.id} : {})}},'Month close appended. Earlier results remain immutable.');
      if(result) { fc.clean(form); form.reset(); }
    }}><fieldset disabled={fc.busy || fc.readonly}><Field label="Close / correction reason"><input name="reason" required/></Field><label><input type="checkbox" required/> I reviewed balances, dated prices, liabilities, beneficiary agreements and reconciliation.</label><Button primary disabled={!report?.coverage.complete}>{latest ? 'Append corrected close' : 'Confirm month close'}</Button></fieldset></form><Table rows={fc.data.closes} columns={[[ 'month','Month'],['revision','Close version'],['reason','Reason'],['supersedes','Corrects'],['confirmedAt','Confirmed at']]}/></Panel></div>;
}
