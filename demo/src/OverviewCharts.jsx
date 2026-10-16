import React from 'react';
import { Empty, Panel } from './components.jsx';

// Counts describe the displayed records, never money, returns or cross-currency totals.
export default function OverviewCharts({ records }) {
  const mix = [
    {label:'Investment Journal',count:records.filter(item => item.entry).length,color:'#3D647C'},
    {label:'Living balances',count:records.filter(item => item.balance).length,color:'#547447'},
    {label:'Manual valuations',count:records.filter(item => item.asset).length,color:'#946831'},
  ];
  const states = ['Posted','Linked reversal','Confirmed','Pending','Unknown','Disposed'].map(label => ({label,count:records.filter(item => item.status === label).length}));
  const total = records.length, circumference = 2 * Math.PI * 64;
  let offset = 0;
  return <div className="overview-charts">
    <Panel title="Record mix" description="Record counts, not financial totals. Counts describe displayed items, including Unknown account readouts, not transactions or source completeness.">
      {!total ? <Empty>Add or select records to see the mix. No sample money is shown.</Empty> : <div className="mix-chart">
        <svg viewBox="0 0 180 180" role="img" aria-label={`${total} records: ${mix.map(item => `${item.label} ${item.count}`).join(', ')}`}>
          {mix.filter(item => item.count).map(item => { const length = item.count / total * circumference, start = offset; offset += length;
            return <circle key={item.label} cx="90" cy="90" r="64" fill="none" stroke={item.color} strokeWidth="20" strokeDasharray={`${length} ${circumference}`} strokeDashoffset={-start} transform="rotate(-90 90 90)"/>;
          })}<text x="90" y="88" textAnchor="middle" className="chart-total">{total}</text><text x="90" y="111" textAnchor="middle">records</text>
        </svg><dl className="chart-legend">{mix.map(item => <div key={item.label}><dt><i style={{background:item.color}} aria-hidden="true"/>{item.label}</dt><dd>{item.count} <small>{Math.round(item.count / total * 100)}%</small></dd></div>)}</dl>
      </div>}
    </Panel>
    <Panel title="Record states" description="Counts of displayed records, not financial amounts. A confirmed observation is not a complete monthly close.">
      {!total ? <Empty>No record states for this month.</Empty> : <dl className="bar-chart">{states.map(item => <div key={item.label}><dt>{item.label}</dt><dd><span className="bar-track" aria-hidden="true"><i style={{width:`${item.count / total * 100}%`}}/></span><strong>{item.count}</strong></dd></div>)}</dl>}
    </Panel>
  </div>;
}
