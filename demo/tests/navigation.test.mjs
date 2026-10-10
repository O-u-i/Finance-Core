import test from 'node:test';
import assert from 'node:assert/strict';
import { assessSetup, mainViews, configurationViews, parseRoute, latestCompletedMonth, viewPaths } from '../src/navigation.js';
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
 assert.deepEqual(mainViews.slice(1,6),['journal','taccounts','positions','cashflow','statements']);
 assert.deepEqual(configurationViews,['master','settings']);
 assert.equal(mainViews.includes('settings'),false);
 assert.deepEqual(parseRoute('#/reports/accounts'),{view:'taccounts',tab:''});
 assert.deepEqual(parseRoute('#/reports/cash-flow'),{view:'cashflow',tab:''});
 assert.deepEqual(parseRoute('#/reports/holdings'),{view:'positions',tab:''});
 assert.deepEqual(parseRoute('#/data/import'),{view:'data',tab:'import'});
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
