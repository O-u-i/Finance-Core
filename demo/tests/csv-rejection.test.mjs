import test from 'node:test';
import assert from 'node:assert/strict';
import { checkImportCSV, csvCommodityIssues } from '../src/csv.js';
const header='entryId,date,description,balancingCommodityCode,postingId,accountId,side,units,commodityCode\n';
test('CSV rejects missing or inactive commodity registration and incompatible mapped account',()=>{
 const inspected=checkImportCSV(header+'x,2026-01-01,Synthetic,CNY,p1,cash,debit,1.10,UNKNOWN\n');
 const issues=csvCommodityIssues(inspected,[{code:'CNY',kind:'currency',status:'active'}]);
 assert.ok(issues.some(text=>text.includes('UNKNOWN') && text.includes('not registered')));
 const inactive=csvCommodityIssues(inspected,[{code:'CNY',kind:'currency',status:'inactive'},{code:'UNKNOWN',kind:'security',status:'active'}]);
 assert.ok(inactive.some(text=>text.includes('CNY') && text.includes('inactive')));
 const standard=checkImportCSV(header+'x,2026-01-01,Synthetic,CNY,p1,cash,debit,1.10,CNY\n');
 assert.ok(csvCommodityIssues(standard,[{code:'CNY',kind:'currency',status:'active'}],[{id:'cash',status:'active',allowedCommodityCodes:['MYR']}]).some(text=>text.includes('does not allow')));
});
