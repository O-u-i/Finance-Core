"""Synthetic boundaries: migration, contract validation and restore atomicity."""
from __future__ import annotations

import copy
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from finance_core import schema_migration
from finance_core.ledger import decimal_sum
from finance_core.personal_finance import allocate_distribution
from test_personal_finance import MONTH, correct, data, draft, observe, seed_personal, totals
from test_v2 import client, create_and_post


def test_migration_rejects_a_writer_resumed_during_copy(tmp_path, monkeypatch):
    source, target = tmp_path/'source.sqlite3', tmp_path/'retained-failed-copy.sqlite3'
    connection = sqlite3.connect(source)
    connection.executescript((Path(__file__).parents[1]/'finance_core'/'schema.sql').read_text())
    connection.close()
    upgrade = schema_migration.upgrade

    def resumed_writer(destination):
        receipt = upgrade(destination)
        with sqlite3.connect(source) as writer:
            writer.execute("INSERT INTO living_accounts VALUES('changed','Synthetic resumed writer','CNY',1,'','2026-08-31')")
        return receipt

    monkeypatch.setattr(schema_migration, 'upgrade', resumed_writer)
    with pytest.raises(ValueError, match='Source changed'):
        schema_migration.migrate_copy(source,target,real_data_approved=True,writers_stopped=True)
    assert target.exists()  # No automatic cleanup of a failed copied Vault.
    with sqlite3.connect(target) as copied:
        assert schema_migration.schema_version(copied)==2
    with sqlite3.connect(source) as original:
        assert original.execute('SELECT COUNT(*) FROM living_accounts').fetchone()[0]==1


@pytest.mark.parametrize('amount',['0.01','1','101.07','99999999999999999999.99'])
def test_distribution_supports_arbitrary_party_count_and_zero_share(amount):
    shares=[{'partyId':f'participant-{index}','share':value} for index,value in enumerate(['0','0.1','0.2','0.3','0.4'])]
    allocation=allocate_distribution(Decimal(amount),shares,2)
    assert allocation[0][1]==0
    assert decimal_sum(value for _,value in allocation)==Decimal(amount)
    assert all(value>=0 and value.as_tuple().exponent==-2 for _,value in allocation)
    assert allocation==allocate_distribution(Decimal(amount),shares,2)


def test_four_beneficiary_agreement_and_distribution_through_public_api(tmp_path):
    with client(tmp_path) as api:
        assert api.post('/api/v2/commodities',json={'code':'CNY','kind':'currency','scale':2,'name':'Synthetic currency'}).status_code==201
        for index in range(4):
            party=f'participant-{index}'
            assert api.put('/api/v2/finance-parties/'+party,json={'id':party,'name':f'Configurable beneficiary {index}'}).status_code==200
        for identity,kind,subtype in [('cash','asset','cash'),('equity','equity',''),*[(f'payable-{index}','liability','') for index in range(4)]]:
            assert api.post('/api/v2/financial-accounts',json={'id':identity,'code':identity,'name':identity,'type':kind,'subtype':subtype,'allowedCommodityCodes':['CNY'],'segment':'investment','balanceSource':'ledger'}).status_code==201
        assert api.post('/api/v2/investment-arrangements',json={'id':'generic-pool','version':1,'currency':'CNY','fromMonth':MONTH,
            'residualShares':[{'partyId':f'participant-{index}','share':share} for index,share in enumerate(['0.1','0.2','0.3','0.4'])],
            'claims':[{'partyId':f'participant-{index}','accountId':f'payable-{index}','kind':'distribution'} for index in range(4)],
            'distributionEquityAccountId':'equity','reason':'Synthetic four-party agreement'}).status_code==201
        assert api.put('/api/v2/personal-finance-settings',json={'cutoverMonth':MONTH,'reportingPartyId':'participant-3','baselineConfirmed':True,'baselineEvidence':'Synthetic baseline'}).status_code==200
        create_and_post(api,{'id':'opening','date':'2026-08-01','description':'Synthetic opening','balancingCommodityCode':'CNY','postings':[
            {'id':'opening-d','accountId':'cash','side':'debit','units':'100','commodityCode':'CNY'},
            {'id':'opening-c','accountId':'equity','side':'credit','units':'100','commodityCode':'CNY'}]})
        report,value=totals(api)
        assert report['coverage']['complete'] and value['ownerInvestmentValue']=='40'
        response=api.post('/api/v2/investment-arrangements/generic-pool/drafts',json={'id':'distribution','date':'2026-08-20','operation':'distribution','amount':'0.01','expectedRevision':report['revision'],'reason':'Synthetic quantum allocation'})
        assert response.status_code==201,response.text
        assert api.post('/api/v2/journal-entry-drafts/distribution/validate').json()['valid']
        assert api.post('/api/v2/journal-entry-drafts/distribution/post').status_code==200
        beneficiaries=totals(api)[0]['currencies'][0]['ownerships']
        assert len(beneficiaries)==4 and next(item for item in beneficiaries if item['partyId']=='participant-3')['claims']=='0.01'
        assert decimal_sum(Decimal(item['economicValue']) for item in beneficiaries)==Decimal('100')


def test_entitlement_post_rechecks_revision_under_the_sqlite_writer_reservation(tmp_path,monkeypatch):
    with client(tmp_path) as api:
        seed_personal(api)
        draft(api,'payment','repayment','100',partyId='owner',claimAccountId='member-owner',cashAccountId='pool',post=False)
        workspace=api.prefix.rsplit('/',1)[1]
        handle=api.api.app.state.registry.vaults.get(workspace)
        validate=handle.repository.validate_draft
        checked=[]
        def reserved_validation(item):
            checked.append(handle.connection.in_transaction)
            with sqlite3.connect(api.api.app.state.registry.vaults.path_for(workspace),timeout=0) as competing_writer:
                with pytest.raises(sqlite3.OperationalError,match='locked'):
                    competing_writer.execute("INSERT INTO finance_parties_v3 VALUES('racing-party','{}')")
            return validate(item)
        monkeypatch.setattr(handle.repository,'validate_draft',reserved_validation)
        assert api.post('/api/v2/journal-entry-drafts/payment/post').status_code==200
        assert checked==[True]
        assert not any(item['id']=='racing-party' for item in data(api,'/finance-parties'))


@pytest.mark.parametrize('month',['2026-8','2026-13','2026-00','2026-08-01','not-a-month'])
def test_new_month_query_rejects_noncanonical_calendar_input(tmp_path,month):
    with client(tmp_path) as api:
        assert api.get('/api/v2/reports/personal-balance-sheet',params={'month':month}).status_code==422


@pytest.mark.parametrize('corruption',['asset-party','claim-reference','measurement-identity','duplicate-observation','close-result'])
def test_format_three_semantic_corruption_rolls_back_even_with_rehashed_payload(tmp_path,corruption):
    with client(tmp_path) as api:
        seed_personal(api)
        draft(api,'accrue','interest','5',interestAgreementId='fixed',specialPeriodConfirmed=True)
        report,_=totals(api)
        assert api.post('/api/v2/monthly-closes',json={'month':MONTH,'expectedRevision':report['revision'],'reason':'Synthetic close','confirmed':True}).status_code==201
        backup=copy.deepcopy(data(api,'/vault-backup'))
        payload=backup['payload']
        if corruption=='asset-party':
            row=payload['non_financial_assets_v3'][0]
            value=json.loads(row['payload_json']); value['ownerPartyId']='missing-party'; row['payload_json']=schema_migration.canonical(value)
        elif corruption=='claim-reference':
            row=payload['investment_arrangements_v3'][0]
            value=json.loads(row['payload_json']); value['claims'][0]['accountId']='missing-claim'; row['payload_json']=schema_migration.canonical(value)
        elif corruption=='measurement-identity':
            row=next(item for item in payload['financial_accounts_v3'] if item['id']=='living')
            value=json.loads(row['payload_json']); value.update(segment='investment',balanceSource='ledger'); row['payload_json']=schema_migration.canonical(value)
        elif corruption=='duplicate-observation':
            row=copy.deepcopy(payload['monthly_observations_v3'][0])
            value=json.loads(row['payload_json']); value['id']='disconnected'; row['id']='disconnected'; row['payload_json']=schema_migration.canonical(value)
            payload['monthly_observations_v3'].append(row)
        else:
            row=payload['monthly_closes_v3'][0]
            value=json.loads(row['result_json']); value['currencies'][0]['totals']['personalNetWorth']='999'; row['result_json']=schema_migration.canonical(value)
        backup['sha256']=schema_migration.fingerprint(payload)
        target=api.post('/api/v3/workspaces',json={'displayName':'Synthetic restore target','kind':'sandbox'}).json()['data']['id']
        path=f'/api/v3/workspaces/{target}/vault-backup'
        before=api.get(path).json()['data']['sha256']
        result=api.post(path+'/restore',json=backup)
        assert result.status_code==422,result.text
        assert api.get(path).json()['data']['sha256']==before


def test_close_continuity_and_prior_correction_require_explicit_reconfirmation(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        draft(api,'accrue','interest','5',interestAgreementId='fixed',specialPeriodConfirmed=True)
        for subject,kind,amount in [('living','balance','1000'),('debt','balance','100'),('vehicle','valuation','450')]:
            observe(api,subject,'2026-09',kind,amount)
        observe(api,'CNY','2026-09','transfer',incoming='0',outgoing='0')
        path='/reports/personal-balance-sheet?month=2026-09'
        report=data(api,path)
        request={'id':'september-interest','date':'2026-09-20','operation':'interest','amount':'4','interestAgreementId':'fixed','expectedRevision':report['revision'],'reason':'Synthetic ordinary interest'}
        assert api.post('/api/v2/investment-arrangements/pool-policy/drafts',json=request).status_code==422
        assert api.post('/api/v2/investment-arrangements/pool-policy/drafts',json={**request,'amount':'5'}).status_code==201
        assert api.post('/api/v2/journal-entry-drafts/september-interest/post').status_code==200
        report=data(api,path)
        close={'month':'2026-09','expectedRevision':report['revision'],'reason':'Synthetic September close','confirmed':True}
        assert api.post('/api/v2/monthly-closes',json=close).status_code==422
        august=api.post('/api/v2/monthly-closes',json={'month':MONTH,'expectedRevision':totals(api)[0]['revision'],'reason':'Synthetic August close','confirmed':True}).json()['data']
        september=api.post('/api/v2/monthly-closes',json=close)
        assert september.status_code==201,september.text
        correct(api,'living','balance','1100')
        report=data(api,path)
        assert report['coverage']['needsReview']
        close.update(expectedRevision=report['revision'],supersedes=september.json()['data']['id'])
        assert api.post('/api/v2/monthly-closes',json=close).status_code==422
        assert api.post('/api/v2/monthly-closes',json={'month':MONTH,'expectedRevision':totals(api)[0]['revision'],'reason':'Synthetic corrected August close','confirmed':True,'supersedes':august['id']}).status_code==201
        assert api.post('/api/v2/monthly-closes',json=close).status_code==201
        assert not data(api,path)['coverage']['needsReview']


def test_journal_and_backup_do_not_construct_personal_command_service(tmp_path, monkeypatch):
    from finance_core import ledger_backup
    from finance_core.personal_finance_repository import PersonalFinanceRepository

    with client(tmp_path) as api:
        seed_personal(api)
        draft(api, 'isolated-payment', 'repayment', '100', partyId='owner',
              claimAccountId='member-owner', cashAccountId='pool', post=False)
        registry = api.api.app.state.registry
        source = registry.vaults.get(api.prefix.rsplit('/', 1)[1])
        target_id = api.post('/api/v3/workspaces', json={'displayName':'Synthetic restore target','kind':'sandbox'}).json()['data']['id']
        target = registry.vaults.get(target_id)

        def command_service_not_needed(*args, **kwargs):
            raise AssertionError('Read validation must not construct the personal command service.')

        restore = ledger_backup.restore_backup
        reserved = []

        def restore_under_reservation(connection, payload):
            reserved.append(connection.in_transaction)
            with sqlite3.connect(registry.vaults.path_for(target_id), timeout=0) as writer:
                with pytest.raises(sqlite3.OperationalError, match='locked'):
                    writer.execute("INSERT INTO finance_parties_v3 VALUES('racing-restore','{}')")
            return restore(connection, payload)

        monkeypatch.setattr(PersonalFinanceRepository, '__init__', command_service_not_needed)
        monkeypatch.setattr(ledger_backup, 'restore_backup', restore_under_reservation)
        assert api.post('/api/v2/journal-entry-drafts/isolated-payment/validate').json()['valid']
        assert api.post('/api/v2/journal-entry-drafts/isolated-payment/post').status_code == 200
        backup = source.repository.create_backup(format_version=3)
        assert api.post(f'/api/v3/workspaces/{target_id}/backup/restore', json=backup).status_code == 201
        assert reserved == [True]
        assert target.repository.create_backup(format_version=3)['sha256'] == backup['sha256']
