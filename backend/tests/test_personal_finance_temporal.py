from __future__ import annotations

import json
from pathlib import Path

from test_v2 import client, create_and_post
from test_personal_finance import MONTH, data, draft, observe, seed_personal, totals


def buy(api):
    assert api.post('/api/v2/commodities',json={'code':'UNIT','kind':'security','scale':4,'name':'Synthetic units'}).status_code==201
    assert api.post('/api/v2/financial-accounts',json={'id':'security','code':'security','name':'Synthetic security','type':'asset','subtype':'investment','allowedCommodityCodes':['UNIT'],'segment':'investment','balanceSource':'ledger'}).status_code==201
    create_and_post(api,{'id':'buy','date':'2026-08-05','description':'Synthetic buy','balancingCommodityCode':'CNY','postings':[
        {'id':'buy-units','accountId':'security','side':'debit','units':'10','commodityCode':'UNIT','valuationRate':'10','rateType':'price','lotAction':'acquire','lotId':'lot'},
        {'id':'buy-cash','accountId':'pool','side':'credit','units':'100','commodityCode':'CNY'}]})


def price(api, identity, value, asof):
    assert api.post('/api/v2/price-quotes',json={'id':identity,'commodityCode':'UNIT','quoteCommodityCode':'CNY','price':value,'asOf':asof,'source':'Synthetic dated price'}).status_code==201


def test_as_of_replays_lots_excludes_future_prices_and_later_disposal(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        draft(api,'interest','interest','5',interestAgreementId='fixed',specialPeriodConfirmed=True)
        buy(api)
        incomplete, value=totals(api)
        assert value['personalNetWorth'] is None and value['investmentAssets'] is None
        assert 'MISSING_AS_OF_PRICE' in {issue['code'] for issue in incomplete['issues']}
        assert all(item['economicValue'] is None and item['residualValue'] is None for item in incomplete['currencies'][0]['ownerships'])
        price(api,'august','12','2026-08-31T15:59:59Z')
        initial,value=totals(api)
        assert initial['coverage']['complete'] and value['investmentAssets']=='10020'
        price(api,'future','999','2026-08-31T16:00:00Z')  # Already September in Shanghai.
        assert totals(api)[0]['revision']==initial['revision']
        create_and_post(api,{'id':'sell','date':'2026-09-05','description':'Synthetic future disposal','balancingCommodityCode':'CNY','postings':[
            {'id':'sell-cash','accountId':'pool','side':'debit','units':'120','commodityCode':'CNY'},
            {'id':'sell-units','accountId':'security','side':'credit','units':'10','commodityCode':'UNIT','valuationRate':'10','rateType':'cost','lotAction':'dispose','lotAllocations':[{'lotId':'lot','units':'10'}]},
            {'id':'sell-profit','accountId':'loss','side':'credit','units':'20','commodityCode':'CNY'}]})
        assert data(api,'/holdings')==[]
        later,value=totals(api)
        assert later['revision']==initial['revision'] and value['investmentAssets']=='10020'


def test_later_acquisition_reversal_preserves_historical_position(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        draft(api,'interest','interest','5',interestAgreementId='fixed',specialPeriodConfirmed=True)
        buy(api)
        price(api,'august','12','2026-08-20T00:00:00Z')
        before,value=totals(api)
        assert api.post('/api/v2/journal-entries/buy/reverse').status_code==201
        assert totals(api)[0]['revision']==before['revision']
        assert totals(api)[1]['investmentAssets']==value['investmentAssets']


def test_backdated_disposal_before_acquisition_and_untracked_units_refuse_completeness(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        buy(api)
        price(api,'august','10','2026-08-20T00:00:00Z')
        create_and_post(api,{'id':'bad-dispose','date':'2026-07-01','description':'Synthetic bad chronology','balancingCommodityCode':'CNY','postings':[
            {'id':'bad-cash','accountId':'pool','side':'debit','units':'100','commodityCode':'CNY'},
            {'id':'bad-units','accountId':'security','side':'credit','units':'10','commodityCode':'UNIT','valuationRate':'10','rateType':'cost','lotAction':'dispose','lotAllocations':[{'lotId':'lot','units':'10'}]}]})
        report,value=totals(api)
        assert value['personalNetWorth'] is None
        assert {'INVALID_LOT_DATE','NEGATIVE_HISTORICAL_LOT'} <= {issue['code'] for issue in report['issues']}


def test_pending_import_atomicity_missing_opening_and_decimal_string_validation(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        assert api.post('/api/v2/monthly-observations',json={'id':'float','subjectId':'living','month':'2026-09','kind':'balance','currency':'CNY','amount':1.23,'source':'test'}).status_code==422
        csv='subjectId,month,kind,currency,amount,incoming,outgoing,source\nliving,2026-09,balance,CNY,1000,,,Synthetic statement\n'
        preview=api.post('/api/v2/import/living-monthly/validate',content=csv,headers={'Content-Type':'text/csv'})
        assert preview.status_code==200,preview.text
        items=preview.json()['data']
        assert all(item['confirmed'] is False for item in items)
        before=len(data(api,'/monthly-observations'))
        invalid={**items[0],'id':'invalid','subjectId':'not-registered'}
        response=api.post('/api/v2/import/living-monthly',json=[items[0],invalid])
        assert response.status_code==422 and len(data(api,'/monthly-observations'))==before
        assert api.post('/api/v2/import/living-monthly',json=items).status_code==201
        assert api.post('/api/v2/import/living-monthly',json=[{**items[0],'confirmed':True}]).status_code==422
        # An unconfirmed month is unknown, not a new zero or carried observation.
        report=data(api,'/reports/living-monthly-review?month=2026-09')
        assert report['currencies'][0]['totals']['closingCash'] is None
        response=api.get('/api/v2/segments/living/export.csv')
        assert response.status_code==200 and 'confirmed' in response.text and '2026-09' in response.text


def test_used_segment_lock_and_successor_carry_does_not_duplicate_assets(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        existing=next(item for item in data(api,'/financial-accounts') if item['id']=='living')
        changed={**existing,'segment':'investment','balanceSource':'ledger'}
        assert api.put('/api/v2/financial-accounts/living',json=changed).status_code==422
        assert api.put('/api/v2/financial-accounts/living',json={**existing,'endMonth':MONTH}).status_code==200
        successor={**existing,'id':'next-living','code':'next-living','name':'Successor','successorOf':'living','startMonth':'2026-09'}
        assert api.post('/api/v2/financial-accounts',json=successor).status_code==201
        wrong={'id':'wrong-carry','subjectId':'next-living','month':MONTH,'kind':'balance','currency':'CNY','amount':'999','confirmed':True,'source':'Synthetic carry'}
        assert api.post('/api/v2/monthly-observations',json=wrong).status_code==422
        observe(api,'next-living',MONTH,'balance','1000')
        observe(api,'next-living','2026-09','balance','1000')
        observe(api,'debt','2026-09','balance','100')
        observe(api,'vehicle','2026-09','valuation','450')
        observe(api,'CNY','2026-09','transfer',incoming='0',outgoing='0')
        report=data(api,'/reports/living-monthly-review?month=2026-09')
        assert report['currencies'][0]['totals']['livingAssets']=='1000'


def test_linked_asset_has_one_authority_and_legacy_identity_requires_explicit_mapping(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        assert api.post('/api/v2/financial-accounts',json={'id':'vehicle-account','code':'fixed','name':'Motor vehicle account','type':'asset','subtype':'fixed','allowedCommodityCodes':['CNY'],'segment':'living','balanceSource':'monthly_snapshot','ownerPartyId':'owner'}).status_code==201
        asset=next(value for value in data(api,'/non-financial-assets') if value['id']=='vehicle')
        # A previously valued asset cannot silently acquire a second authority.
        assert api.put('/api/v2/non-financial-assets/vehicle',json={**asset,'linkedAccountId':'vehicle-account'}).status_code==422
        assert api.post('/api/v2/non-financial-assets',json={**asset,'id':'second-vehicle','name':'Linked vehicle','linkedAccountId':'vehicle-account','purchaseCost':'200'}).status_code==201
        observe(api,'second-vehicle',MONTH,'valuation','200')
        report,value=totals(api)
        assert value['knownLivingAssetSubtotal']=='1000' and value['nonFinancialAssets']=='700'
        assert api.post('/api/v2/living-accounts',json={'id':'duplicate-pool','name':'Different name','commodityCode':'CNY','balance':'10000','note':'','updatedAt':'2026-08-20T00:00:00Z'}).status_code==201
        assert 'LEGACY_LIVING_MAPPING_REQUIRED' in {issue['code'] for issue in totals(api)[0]['issues']}
        mapping=api.post('/api/v2/legacy-living-mapping/duplicate-pool',json={'targetAccountId':'pool','sameEconomicAccountConfirmed':True,'reason':'Synthetic same-economic-account confirmation'})
        assert mapping.status_code==200,mapping.text
        assert 'LEGACY_LIVING_MAPPING_REQUIRED' not in {issue['code'] for issue in totals(api)[0]['issues']}
        assert data(api,'/legacy-living-mapping')['archivedSources']


def test_future_linked_asset_cannot_hide_an_earlier_observed_balance(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        draft(api,'accrue','interest','5',interestAgreementId='fixed',specialPeriodConfirmed=True)
        assert api.post('/api/v2/financial-accounts',json={'id':'fixed-asset','code':'fixed-asset','name':'Synthetic existing fixed asset','type':'asset','subtype':'fixed','allowedCommodityCodes':['CNY'],'segment':'living','balanceSource':'monthly_snapshot','ownerPartyId':'owner'}).status_code==201
        for month in ('2026-07',MONTH):
            observe(api,'fixed-asset',month,'balance','250')
        before,value=totals(api)
        assert before['coverage']['complete'] and value['livingAssets']=='1250'
        assert api.post('/api/v2/non-financial-assets',json={'id':'future-asset','name':'Future manual measurement','assetType':'vehicle','currency':'CNY','purchasedDate':'2026-09-01','purchaseCost':'250','ownerPartyId':'owner','linkedAccountId':'fixed-asset'}).status_code==201
        after,new_value=totals(api)
        assert after['coverage']['complete']
        assert new_value['livingAssets']==value['livingAssets'] and new_value['personalNetWorth']==value['personalNetWorth']
