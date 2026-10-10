import test from 'node:test';
import assert from 'node:assert/strict';
import { readCSV, checkImportCSV, mapAccountingCSV } from '../src/csv.js';

const header = '日期,会计科目,责任中心,参考号（Ref.),摘要（Description）,借（Debit）CNY,借（Debit）MYR,贷（Credit）CNY,贷（Credit）MYR,父记录';
const csv = [header,['2026/01/01','9001 Cash','Unit A','','Synthetic opening','1.10','','','',''].join(','),['2026/01/01','9002 Capital','','','','','','1.10','','Synthetic parent'].join(',')].join('\n');
const accounts = ['9001','9002'].map((code,i)=>({id:`a${i}`,code,status:'active',allowedCommodityCodes:['CNY','MYR']}));
const commodities = ['CNY','MYR'].map(code=>({code,status:'active'}));
const config = {groupingConfirmed:true,accountMap:{9001:'a0',9002:'a1'},accounts,commodities,prefix:'synthetic'};

test('single-currency journal requires explicit currency and consecutive key grouping',()=>{
  const single = '日期,会计科目,责任中心,参考号（Ref.),摘要（Description）,借（Debit）,贷（Credit）\n2025/3/1,9001 Cash,,r1,Synthetic entry,1.10,\n2025/3/1,9002 Capital,,r1,Synthetic entry,,1.10';
  const source = checkImportCSV(single).source;
  assert.throws(()=>mapAccountingCSV(source,config),/Choose an active source currency/);
  const result = mapAccountingCSV(source,{...config,sourceCurrency:'CNY',groupingRule:'same-key',commodities:commodities.map(item=>({...item,kind:'currency'}))});
  assert.equal(result.drafts.length,1); assert.equal(result.drafts[0].date,'2025-03-01');
  assert.equal(result.drafts[0].postings[0].units,'1.10');
  assert.throws(()=>mapAccountingCSV(source,{...config,sourceCurrency:'CNY',groupingConfirmed:false}),/Confirm/);
  assert.throws(()=>mapAccountingCSV(checkImportCSV(single.replace('9002 Capital,,r1','9002 Capital,,r2')).source,{...config,sourceCurrency:'CNY',groupingRule:'same-key',commodities:commodities.map(item=>({...item,kind:'currency'}))}),/non-zero postings/);
  const parentDescription = checkImportCSV(single.replace('9002 Capital,,r1,Synthetic entry','9002 Capital,,r1,')).source;
  assert.equal(mapAccountingCSV(parentDescription,{...config,sourceCurrency:'CNY',commodities:commodities.map(item=>({...item,kind:'currency'}))}).drafts.length,1);
});

test('CSV supports BOM, escaped quotes, comma and newline within a quoted field',()=>{
  const parsed=readCSV('\ufeffid,note\r\nx,"first,\nsecond ""quoted"""\r\n');
  assert.equal(parsed.rows[0].note,'first,\nsecond "quoted"');
});
test('ambiguous CSV headers, malformed quotes and unequal row widths are rejected',()=>{
  for(const input of ['a,a\n1,2','a,b\n1','a,b\n1,"unfinished','a,b\n1,"closed"extra']) assert.throws(()=>readCSV(input));
});
test('accounting CSV requires explicit grouping and active mapped accounts',()=>{
  const profile=checkImportCSV(csv); assert.equal(profile.kind,'accounting');
  assert.throws(()=>mapAccountingCSV(profile.source,{...config,groupingConfirmed:false}),/Confirm/);
  assert.throws(()=>mapAccountingCSV(profile.source,{...config,accountMap:{}}),/Map every/);
});
test('mapping preserves decimal strings, date, currency and source context without posting',()=>{
  const result=mapAccountingCSV(readCSV(csv),config), draft=result.drafts[0];
  assert.equal(draft.date,'2026-01-01'); assert.equal(draft.postings[0].units,'1.10');
  assert.equal(draft.postings[1].units,'1.10'); assert.equal(draft.postings[0].memo,'Unit A');
  assert.equal(draft.postings[1].memo,'Synthetic parent'); assert.equal(draft.balancingCommodityCode,'CNY');
  const precise=mapAccountingCSV(readCSV(csv.replaceAll('1.10','9007199254740993.001')),config);
  assert.equal(precise.drafts[0].postings[0].units,'9007199254740993.001');
});
test('orphan children, invalid dates and mixed currencies never infer grouping or rates',()=>{
  const orphan=readCSV(csv); orphan.rows[0]['父记录']='orphan';
  assert.throws(()=>mapAccountingCSV(orphan,config),/preceding parent/);
  assert.throws(()=>mapAccountingCSV(readCSV(csv.replaceAll('2026/01/01','2026/02/30')),config),/calendar/);
  const mixed=readCSV(csv); mixed.rows[1]['贷（Credit）MYR']=mixed.rows[1]['贷（Credit）CNY']; mixed.rows[1]['贷（Credit）CNY']='';
  assert.throws(()=>mapAccountingCSV(mixed,config),/valuation rates/);
});
test('missing currency and unsupported account currency block mapping',()=>{
  assert.throws(()=>mapAccountingCSV(readCSV(csv),{...config,commodities:[]}),/source currency/);
  assert.throws(()=>mapAccountingCSV(readCSV(csv),{...config,accounts:accounts.map(a=>({...a,allowedCommodityCodes:['MYR']}))}),/support/);
});

test('explicit grouping overrides parent captions; balanced mapping preserves individual rows for FC',()=>{
  const source = readCSV(csv); source.rows[1]['摘要（Description）'] = 'Different caption';
  const sameDate = mapAccountingCSV(source,{...config,groupingRule:'date'});
  assert.equal(sameDate.drafts.length,1);
  const balanced = mapAccountingCSV(source,{...config,groupingRule:'balanced'});
  assert.equal(balanced.rows.length,2); assert.equal(balanced.drafts,undefined);
  assert.equal(balanced.rows[1].description,'Different caption');
  assert.equal(balanced.rows[1].postings[0].units,'1.10');
});
