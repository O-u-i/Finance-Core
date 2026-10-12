import test from 'node:test';
import assert from 'node:assert/strict';
import { assessSetup, selectedMonth, selectedRecordedMonth, segmentViews, configurationViews, parseRoute, routeHash, latestCompletedMonth, viewPaths } from '../src/navigation.js';
const workspace={id:'sandbox',status:'active'};
const actor={actorKind:'session',status:'active'};
const currency=code=>({code,kind:'currency',status:'active'});
const account=(id,codes,status='active')=>({id,status,allowedCommodityCodes:codes});
test('monthly review uses explicit closed-month routes and Shanghai rollover',()=>{
 assert.equal(latestCompletedMonth(new Date('2025-12-31T15:59:00Z')),'2025-11');
 assert.equal(latestCompletedMonth(new Date('2025-12-31T16:00:00Z')),'2025-12');
 assert.equal(viewPaths('monthlyreview','2025-03').monthlyReview,'/reports/monthly-review?month=2025-03');
 assert.equal(viewPaths('monthlyreview','invalid',new Date('2025-04-10T00:00:00Z')).monthlyReview,'/reports/monthly-review?month=2025-03');
 assert.deepEqual(parseRoute('#/monthlyreview/2025-03'),{view:'monthlyreview',tab:'2025-03'});
});
test('financial sequence follows Journal through independent readouts to Statements',()=>{
 assert.deepEqual(segmentViews.investment.slice(0,5),['journal','taccounts','positions','cashflow','statements']);
 assert.deepEqual(configurationViews,['overview','master','settings']);
 assert.equal(segmentViews.investment.includes('settings'),false);
 assert.deepEqual(parseRoute('#/reports/accounts'),{view:'taccounts',tab:''});
 assert.deepEqual(parseRoute('#/reports/cash-flow'),{view:'cashflow',tab:''});
 assert.deepEqual(parseRoute('#/reports/holdings'),{view:'positions',tab:''});
 assert.deepEqual(parseRoute('#/data/import'),{view:'data',tab:'import'});
});
test('horizontal segments have no detailed Living transactions and deep link month state',()=>{
 assert.deepEqual(segmentViews.living,['balances','assets','plans','livingreview','livingdata']);
 assert.equal(segmentViews.living.includes('transactions'),false);
 const route={segment:'living',view:'livingreview',tab:'2026-08'};
 assert.deepEqual(parseRoute(routeHash(route)),route);
 assert.deepEqual(parseRoute('#/overview/consolidated/2026-08'),{view:'overview',tab:'consolidated',month:'2026-08'});
 assert.equal(viewPaths('livingreview','2026-08',new Date(),'living').personalReport,'/reports/living-monthly-review?month=2026-08');
 assert.equal(viewPaths('monthlyreview','2026-08',new Date(),'investment').personalReport,'/reports/investment-monthly-review?month=2026-08');
 assert.equal(viewPaths('master','ownership',new Date(),'investment','2026-08').personalReport,'/reports/personal-balance-sheet?month=2026-08');
});

test('page controls and API reads use the same as-of month selection',()=>{
 const now = new Date('2026-01-31T16:00:00Z');
 assert.equal(selectedMonth({tab:'ownership',month:'2026-08'},now),'2026-08');
 assert.equal(selectedMonth({tab:'2026-07'},now),'2026-07');
 assert.equal(selectedMonth({tab:'ownership'},now),'2026-01');
 assert.equal(selectedMonth({month:'2026-13'},now),'2026-01');
 assert.equal(viewPaths('master','ownership',now,'investment').personalReport,'/reports/personal-balance-sheet?month=2026-01');
});
test('dated Living balances default to the current Shanghai month, separately from month-end reports',()=>{
 const now=new Date('2026-01-31T16:00:00Z');
 assert.equal(selectedRecordedMonth({},now),'2026-02');
 assert.equal(selectedRecordedMonth({tab:'2026-07'},now),'2026-07');
 assert.equal(viewPaths('balances','',now,'living').recordedReport,'/reports/living-recorded-balances?month=2026-02');
 assert.equal(viewPaths('livingreview','2026-08',now,'living').recordedReport,'/reports/living-recorded-balances?month=2026-08');
 assert.equal(viewPaths('livingreview','',now,'living').personalReport,'/reports/living-monthly-review?month=2026-02');
 assert.equal(viewPaths('balances','',now,'living').balanceRecords,'/balance-records');
});
test('configuration needs an authenticated session and two usable accounts for one active currency',()=>{
 const input={loaded:true,workspace,actor,commodities:[currency('CNY')],accounts:[account('cash',['CNY']),account('capital',['CNY'])]};
 assert.equal(assessSetup(input).ready,true);
 assert.equal(assessSetup({...input,actor:null}).ready,false);
 assert.equal(assessSetup({...input,loaded:false}).ready,false);
 assert.equal(assessSetup({...input,workspace:{status:'quarantined'}}).ready,false);
 assert.equal(assessSetup({...input,accounts:[account('cash',['CNY']),account('capital',['CNY'],'inactive')]}).ready,false);
 assert.equal(assessSetup({...input,commodities:[currency('CNY'),currency('MYR')],accounts:[account('cash',['CNY']),account('capital',['MYR'])]}).ready,false);
 assert.equal(assessSetup({...input,commodities:[{...currency('CNY'),status:'inactive'}]}).ready,false);
 assert.equal(assessSetup({...input,workspace:{status:'archived'}}).ready,true,'archived records stay readable while mutations remain backend-blocked');
});
