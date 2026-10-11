"""Synthetic reference arrangements; production code must work with arbitrary parties."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from finance_core.database import connect
from finance_core.models_personal import InvestmentArrangement
from finance_core.personal_finance import allocate_distribution
from finance_core.schema_migration import migrate_copy, schema_version
from test_v2 import client, create_and_post

MONTH = '2026-08'


def data(api, path):
    response = api.get('/api/v2' + path)
    assert response.status_code == 200, response.text
    return response.json()['data']


def totals(api):
    report = data(api, f'/reports/personal-balance-sheet?month={MONTH}')
    return report, next(item['totals'] for item in report['currencies'] if item['currency'] == 'CNY')


def observe(api, subject, month, kind, amount=None, **changes):
    payload = {'id': f'observe-{subject}-{month}-{len(data(api,"/monthly-observations"))}', 'subjectId': subject,
               'month': month, 'kind': kind, 'currency': 'CNY', 'source': 'Synthetic monthly statement', 'confirmed': True, **changes}
    if amount is not None:
        payload['amount'] = amount
    response = api.post('/api/v2/monthly-observations', json=payload)
    assert response.status_code == 201, response.text
    return response.json()['data']


def seed_personal(api, *, shares=('0.5','0.5'), names=('A','B','Self')):
    assert api.post('/api/v2/commodities', json={'code':'CNY','kind':'currency','scale':2,'name':'Synthetic currency'}).status_code == 201
    for party, name in zip(('creditor','partner','owner'), names):
        assert api.put(f'/api/v2/finance-parties/{party}', json={'id':party,'name':name}).status_code == 200
    for identity, kind, subtype in [('pool','asset','cash'),('capital','equity',''),('loan','liability',''),('interest','liability',''),
                                    ('member-partner','liability',''),('member-owner','liability',''),('dist-partner','liability',''),('dist-owner','liability',''),('interest-expense','expense',''),('loss','expense','')]:
        response = api.post('/api/v2/financial-accounts', json={'id':identity,'code':identity,'name':identity,'type':kind,'subtype':subtype,
                           'allowedCommodityCodes':['CNY'],'segment':'investment','balanceSource':'ledger'})
        assert response.status_code == 201, response.text
    for identity, kind, subtype in [('living','asset','cash'),('debt','liability','')]:
        assert api.post('/api/v2/financial-accounts', json={'id':identity,'code':identity,'name':identity,'type':kind,'subtype':subtype,
                   'allowedCommodityCodes':['CNY'],'segment':'living','balanceSource':'monthly_snapshot','ownerPartyId':'owner'}).status_code == 201
    arrangement = {'id':'pool-policy','version':1,'currency':'CNY','fromMonth':MONTH,
                   'residualShares':[{'partyId':'partner','share':shares[0]},{'partyId':'owner','share':shares[1]}],
                   'claims':[{'accountId':identity,'partyId':party,'kind':kind} for identity,party,kind in
                             [('loan','creditor','loan'),('interest','creditor','interest'),('member-partner','partner','member'),
                              ('member-owner','owner','member'),('dist-partner','partner','distribution'),('dist-owner','owner','distribution')]],
                   'interestAgreements':[{'id':'fixed','partyId':'creditor','principalAccountId':'loan','payableAccountId':'interest',
                                          'expenseAccountId':'interest-expense','monthlyAmount':'5','fromMonth':MONTH}],
                   'distributionEquityAccountId':'capital','reason':'Synthetic configurable agreement'}
    response = api.post('/api/v2/investment-arrangements', json=arrangement)
    assert response.status_code == 201, response.text
    assert api.put('/api/v2/personal-finance-settings', json={'cutoverMonth':MONTH,'reportingPartyId':'owner',
                   'baselineConfirmed':True,'baselineEvidence':'Synthetic opening cash, lots, liabilities and beneficiaries confirmed'}).status_code == 200
    assert api.post('/api/v2/non-financial-assets', json={'id':'vehicle','name':'Synthetic vehicle','assetType':'vehicle','currency':'CNY',
                   'purchasedDate':'2026-07-01','purchaseCost':'1000','ownerPartyId':'owner'}).status_code == 201
    for month in ('2026-07', MONTH):
        observe(api,'living',month,'balance','1000')
        observe(api,'debt',month,'balance','100')
    observe(api,'vehicle',MONTH,'valuation','500')
    observe(api,'CNY',MONTH,'transfer',incoming='0',outgoing='0')
    create_and_post(api, {'id':'opening','date':'2026-07-31','description':'Synthetic opening','balancingCommodityCode':'CNY',
                    'postings':[{'id':'open-cash','accountId':'pool','side':'debit','units':'10000','commodityCode':'CNY'},
                                *[{'id':'open-'+identity,'accountId':identity,'side':'credit','units':amount,'commodityCode':'CNY'}
                                  for identity, amount in [('loan','2000'),('member-partner','200'),('member-owner','300'),('capital','7500')]]]})
    return arrangement


def draft(api, identity, operation, amount, *, post=True, **changes):
    report, _ = totals(api)
    response = api.post('/api/v2/investment-arrangements/pool-policy/drafts', json={
        'id': identity, 'date':'2026-08-20','operation':operation,'amount':amount,
        'expectedRevision':report['revision'],'reason':'Synthetic reviewed operation', **changes})
    assert response.status_code == 201, response.text
    if post:
        validation = api.post(f'/api/v2/journal-entry-drafts/{identity}/validate')
        assert validation.json()['valid'] is True, validation.text
        result = api.post(f'/api/v2/journal-entry-drafts/{identity}/post')
        assert result.status_code == 200, result.text
    return response.json()['data']


def correct(api, subject, kind, amount=None, **changes):
    current = next(item for item in reversed(data(api,'/monthly-observations')) if item['subjectId'] == subject and item['month'] == MONTH and item['kind'] == kind)
    return observe(api,subject,MONTH,kind,amount,supersedes=current['id'],reason='Synthetic source correction',**changes)


def test_reference_loans_interest_entitlements_and_personal_wealth_conservation(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        incomplete, _ = totals(api)
        assert incomplete['coverage']['complete'] is False
        assert 'INTEREST_ACCRUAL_REVIEW_REQUIRED' in {issue['code'] for issue in incomplete['issues']}
        draft(api,'accrue','interest','5',interestAgreementId='fixed',specialPeriodConfirmed=True)
        report, before = totals(api)
        assert report['coverage']['complete'] is True, report['issues']
        assert before['investmentLiabilities'] == '2505'
        assert before['residualEquity'] == '7495'
        assert before['ownerInvestmentValue'] == '4047.5'
        assert before['personalNetWorth'] == '5447.5'
        draft(api,'member-fund','funding','600',partyId='owner',claimAccountId='member-owner',cashAccountId='pool',fromLiving=True)
        correct(api,'living','balance','400')
        correct(api,'CNY','transfer',incoming='0',outgoing='600')
        assert totals(api)[1]['personalNetWorth'] == before['personalNetWorth']
        draft(api,'member-repay','repayment','200',partyId='owner',claimAccountId='member-owner',cashAccountId='pool',fromLiving=True)
        correct(api,'living','balance','600')
        correct(api,'CNY','transfer',incoming='200',outgoing='600')
        assert totals(api)[1]['personalNetWorth'] == before['personalNetWorth']
        draft(api,'distribute','distribution','200')
        assert totals(api)[1]['personalNetWorth'] == before['personalNetWorth']
        draft(api,'pay-owner','distribution_payment','100',partyId='owner',claimAccountId='dist-owner',cashAccountId='pool',fromLiving=True)
        correct(api,'living','balance','700')
        correct(api,'CNY','transfer',incoming='300',outgoing='600')
        report, after = totals(api)
        assert after['personalNetWorth'] == before['personalNetWorth']
        assert after['unexplainedCashChange'] == '0'
        partner = next(item for item in report['currencies'][0]['ownerships'] if item['partyId']=='partner')
        assert partner['claims'] == '300'  # Unpaid distribution plus member funding.
        draft(api,'pay-interest','interest_payment','5',partyId='creditor',claimAccountId='interest',cashAccountId='pool')
        assert totals(api)[1]['personalNetWorth'] == before['personalNetWorth']
        assert data(api,'/reconciliation')['status'] == 'pass'  # Old contract remains unchanged.


def test_arbitrary_participants_non_equal_shares_and_rounding(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api, shares=('0.3','0.7'), names=('Organization','Team member','Another owner'))
        draft(api,'accrue','interest','5',interestAgreementId='fixed',specialPeriodConfirmed=True)
        assert totals(api)[1]['ownerInvestmentValue'] == '5546.5'
        draft(api,'tiny-distribution','distribution','0.01')
        entries = data(api,'/journal-entries')
        distribution = next(entry for entry in entries if entry['id']=='tiny-distribution')
        assert [item['units'] for item in distribution['postings']] == ['0.01','0.01']
    result = allocate_distribution(Decimal('100000000000000000000.01'), [{'partyId':'x','share':'0.333333333333333333'},{'partyId':'y','share':'0.666666666666666667'}], 2)
    from finance_core.ledger import decimal_sum
    assert decimal_sum(value for _, value in result) == Decimal('100000000000000000000.01')
    with pytest.raises(ValueError):
        InvestmentArrangement.model_validate({'id':'wrong','version':1,'currency':'CNY','fromMonth':MONTH,'reason':'test','residualShares':[{'partyId':'x','share':'0.4'}]})


def test_overpayment_stale_draft_and_special_interest_rejected(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        report, _ = totals(api)
        common = {'date':'2026-08-20','amount':'5','operation':'interest','expectedRevision':report['revision'],'interestAgreementId':'fixed','reason':'test'}
        assert api.post('/api/v2/investment-arrangements/pool-policy/drafts',json={'id':'not-confirmed',**common}).status_code == 422
        draft(api,'stale','repayment','300',partyId='owner',claimAccountId='member-owner',cashAccountId='pool',post=False)
        draft(api,'pay','repayment','300',partyId='owner',claimAccountId='member-owner',cashAccountId='pool')
        assert api.post('/api/v2/journal-entry-drafts/stale/post').status_code == 422
        report, _ = totals(api)
        response = api.post('/api/v2/investment-arrangements/pool-policy/drafts', json={'id':'excess','date':'2026-08-21','operation':'repayment','amount':'0.01','partyId':'owner','claimAccountId':'member-owner','cashAccountId':'pool','expectedRevision':report['revision'],'reason':'test'})
        assert response.status_code == 422


def test_close_is_revision_bound_immutable_and_append_corrected(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        draft(api,'accrue','interest','5',interestAgreementId='fixed',specialPeriodConfirmed=True)
        report, before = totals(api)
        payload = {'month':MONTH,'expectedRevision':report['revision'],'reason':'Synthetic close','confirmed':True}
        first = api.post('/api/v2/monthly-closes',json=payload)
        assert first.status_code == 201, first.text
        original = first.json()['data']
        correct(api,'living','balance','1100')
        assert totals(api)[0]['coverage']['needsReview'] is True
        stale = api.post('/api/v2/monthly-closes',json={**payload,'supersedes':original['id']})
        assert stale.status_code == 409
        report, after = totals(api)
        second = api.post('/api/v2/monthly-closes',json={**payload,'expectedRevision':report['revision'],'supersedes':original['id'],'reason':'Corrected source'})
        assert second.status_code == 201, second.text
        closes = data(api,'/monthly-closes')
        assert closes[0]['report']['currencies'][0]['totals']['personalNetWorth'] == before['personalNetWorth']
        assert Decimal(after['personalNetWorth']) - Decimal(before['personalNetWorth']) == 100
        assert len(closes) == 2 and closes[1]['revision'] == 2
        assert data(api,'/undo/latest') is None


def test_unknowns_negative_equity_and_invalid_dates_are_not_zero(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        draft(api,'accrue','interest','5',interestAgreementId='fixed',specialPeriodConfirmed=True)
        create_and_post(api, {'id':'loss-entry','date':'2026-08-25','description':'Synthetic loss','balancingCommodityCode':'CNY','postings':[
            {'id':'loss-d','accountId':'loss','side':'debit','units':'9900','commodityCode':'CNY'},
            {'id':'loss-c','accountId':'pool','side':'credit','units':'9900','commodityCode':'CNY'}]})
        report, value = totals(api)
        assert report['coverage']['complete'] is True
        assert value['residualEquity'] == '-2405' and value['ownerInvestmentValue'] == '-902.5'
        create_and_post(api, {'id':'undated','date':'not-a-date','description':'Synthetic invalid legacy date','balancingCommodityCode':'CNY','postings':[
            {'id':'invalid-d','accountId':'pool','side':'debit','units':'1','commodityCode':'CNY'},
            {'id':'invalid-c','accountId':'capital','side':'credit','units':'1','commodityCode':'CNY'}]})
        report, value = totals(api)
        assert value['personalNetWorth'] is None
        assert 'INVALID_POSTED_DATE' in {issue['code'] for issue in report['issues']}


def test_owner_only_new_contract_and_format_three_roundtrip(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        draft(api,'accrue','interest','5',interestAgreementId='fixed',specialPeriodConfirmed=True)
        report, _ = totals(api)
        assert api.post('/api/v2/monthly-closes',json={'month':MONTH,'expectedRevision':report['revision'],'reason':'test','confirmed':True}).status_code == 201
        backup = data(api,'/vault-backup')
        assert backup['formatVersion']==3 and 'living_account_snapshots' in backup['payload']
        assert not {'sessions','access_tokens','undo_operations_v2'} & set(backup['payload'])
        token = api.post('/api/v3/access-tokens',json={'name':'reader','workspaceIds':[api.prefix.rsplit('/',1)[1]],'scopes':['ledger:read']}).json()['token']
        assert api.get('/api/v2/financial-accounts',headers={'Authorization':'Bearer '+token}).status_code == 403
        assert api.get('/api/v2/reports/monthly-review?month=2026-08',headers={'Authorization':'Bearer '+token}).status_code == 200
        workspace = api.post('/api/v3/workspaces',json={'displayName':'Restore target','kind':'sandbox'}).json()['data']['id']
        restored = api.post(f'/api/v3/workspaces/{workspace}/vault-backup/restore',json=backup)
        assert restored.status_code == 201, restored.text
        assert api.get(f'/api/v3/workspaces/{workspace}/vault-backup').json()['data']['sha256'] == backup['sha256']
        assert api.get(f'/api/v3/workspaces/{workspace}/reports/personal-balance-sheet?month={MONTH}').json()['data']['revision'] == report['revision']
        assert api.get(f'/api/v3/workspaces/{workspace}/undo/latest').json()['data'] is None


def test_schema_two_dry_run_copy_preserves_original_and_refuses_implicit_upgrade(tmp_path):
    source = tmp_path/'old.sqlite3'
    old = sqlite3.connect(source, isolation_level=None)
    old.executescript((Path(__file__).parents[1]/'finance_core'/'schema.sql').read_text())
    old.execute("INSERT INTO living_accounts VALUES('old','Synthetic legacy','CNY',15,'','2026-07-20')")
    old.close()
    dry = migrate_copy(source)
    assert dry['dryRun'] is True and dry['legacyDatesInferred'] is False
    connection = connect(source)
    assert schema_version(connection)==2
    assert not connection.execute("SELECT 1 FROM sqlite_master WHERE name='financial_accounts_v3'").fetchone()
    connection.close()
    # Opening/closing WAL may change the SQLite journal header, but no financial rows/schema.
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(PermissionError):
        migrate_copy(source,tmp_path/'unauthorized.sqlite3')
    target = tmp_path/'new.sqlite3'
    with pytest.raises(PermissionError):
        migrate_copy(source,target,real_data_approved=True)
    assert not target.exists()
    migrate_copy(source,target,real_data_approved=True,writers_stopped=True)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    connection = connect(target)
    assert schema_version(connection)==3
    archived = connection.execute('SELECT payload_json FROM legacy_living_archive_v3').fetchone()[0]
    assert json.loads(archived)['balance']==15
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute('DELETE FROM legacy_living_archive_v3')
    connection.close()
    with pytest.raises(FileExistsError):
        migrate_copy(source,target,real_data_approved=True,writers_stopped=True)
