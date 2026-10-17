"""Bounded financial evidence through the released HTTP seam, synthetic data only."""
import pytest
from test_v2 import client, seed, create_and_post, opening_draft


def foundation(api):
    seed(api)
    create_and_post(api, opening_draft())
    assert api.put('/api/v2/finance-parties/owner', json={'id': 'owner', 'name': 'PRIVATE OWNER'}).status_code == 200
    assert api.put('/api/v2/personal-finance-settings', json={
        'cutoverMonth': '2026-08', 'reportingPartyId': 'owner',
        'baselineConfirmed': True, 'baselineEvidence': 'PRIVATE BASELINE',
    }).status_code == 200
    assert api.post('/api/v2/financial-accounts', json={
        'id': 'living', 'code': 'living', 'name': 'PRIVATE LIVING ACCOUNT', 'type': 'asset', 'subtype': 'cash',
        'allowedCommodityCodes': ['CNY'], 'segment': 'living', 'balanceSource': 'monthly_snapshot', 'ownerPartyId': 'owner',
    }).status_code == 201
    assert api.post('/api/v2/balance-records', json={
        'id': 'living-balance', 'subjectId': 'living', 'observedDate': '2026-08-31',
        'currency': 'CNY', 'amount': '500', 'confirmed': True, 'source': 'PRIVATE STATEMENT',
    }).status_code == 201
    for identity, amount in [('one', '0.1'), ('two', '0.2')]:
        assert api.post('/api/v2/monthly-plans', json={
            'id': identity, 'name': 'PRIVATE OBLIGATION LABEL', 'kind': 'expense', 'amount': amount,
            'commodityCode': 'CNY', 'category': 'PRIVATE CATEGORY', 'dayOfMonth': 31,
            'startDate': '2026-09-01', 'note': 'PRIVATE NOTE',
        }).status_code == 201


def test_bounded_report_delivers_exact_stocks_and_dated_plan_outflows_without_private_labels(tmp_path):
    with client(tmp_path) as api:
        foundation(api)
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        path = '/api/v2/reports/economic-evidence?asOf=2026-08-31&through=2026-09-30'
        response = api.get(path)
        assert response.status_code == 200
        body = response.json()
        report = body['data']
        assert body['workspaceId'] == api.prefix.rsplit('/', 1)[1] and body['readOnly'] is True
        assert report['schemaVersion'] == 1 and report['calculationVersion'] == 'economic-evidence-v1'
        assert report['asOf'] == '2026-08-31' and report['through'] == '2026-09-30'
        assert report['balanceBasis'] == 'gross-registered-accounts'
        assert report['planBasis'] == 'planned-only-not-contractual-maturity'
        balances = {(row['segment'], row['currency']): row for row in report['balances']}
        assert balances['investment', 'CNY']['cashBalance'] == '1000'
        assert balances['living', 'CNY']['cashBalance'] == '500'
        assert all(row['liabilityBalance'] == '0' for row in balances.values())
        assert report['plannedOutflows'] == [{'dueDate': '2026-09-30', 'currency': 'CNY', 'amount': '0.3', 'count': 2}]
        assert report['coverage'] == {
            'cashStocks': True, 'liabilityBalances': True, 'datedObligations': True,
            'externalCompleteness': 'unknown', 'currenciesCombined': False, 'personalAvailabilityAssessed': False,
        }
        assert report['missingFacts'] == []
        assert 'PRIVATE' not in response.text and 'living-balance' not in response.text
        assert api.get(path).json()['data']['revision'] == report['revision']
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before


def test_offsetting_liability_accounts_do_not_prove_that_debt_maturities_are_unnecessary(tmp_path):
    with client(tmp_path) as api:
        foundation(api)
        for identity in ('owed', 'overpaid'):
            assert api.post('/api/v2/accounts', json={
                'id': identity, 'code': identity, 'name': 'PRIVATE DEBT', 'type': 'liability',
                'allowedCommodityCodes': ['CNY'],
            }).status_code == 201
        create_and_post(api, {'id': 'offset', 'date': '2026-08-20', 'description': 'PRIVATE DEBT DETAIL',
            'balancingCommodityCode': 'CNY', 'postings': [
                {'id': 'offset-1', 'accountId': 'owed', 'side': 'credit', 'units': '100', 'commodityCode': 'CNY'},
                {'id': 'offset-2', 'accountId': 'overpaid', 'side': 'debit', 'units': '100', 'commodityCode': 'CNY'},
            ]})
        response = api.get('/api/v2/reports/economic-evidence?asOf=2026-08-31&through=2026-09-30')
        assert response.status_code == 200
        report = response.json()['data']
        assert report['coverage']['liabilityBalances'] is True
        assert report['coverage']['datedObligations'] is False
        assert report['missingFacts'] == ['dated_obligations']
        assert 'PRIVATE' not in response.text


def test_confirmed_baseline_is_not_retroactive_before_its_cutover(tmp_path):
    with client(tmp_path) as api:
        foundation(api)
        report = api.get('/api/v2/reports/economic-evidence?asOf=2026-07-31&through=2026-08-31').json()['data']
        assert report['coverage']['liabilityBalances'] is False
        assert set(report['missingFacts']) == {'cash_stocks', 'liability_balances', 'dated_obligations'}


@pytest.mark.parametrize('as_of,through', [('2026-02-30', '2026-09-30'), ('2026-08-31', '2026-08-31'),
    ('2026-08-31', '2028-09-30'), ('2099-01-01', '2099-02-01')])
def test_invalid_or_unbounded_periods_reject_without_writing(tmp_path, as_of, through):
    with client(tmp_path) as api:
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        assert api.get(f'/api/v2/reports/economic-evidence?asOf={as_of}&through={through}').status_code == 422
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before


def test_read_scope_isolated_and_personal_owner_endpoints_stay_closed(tmp_path):
    with client(tmp_path) as api:
        foundation(api)
        wid = api.prefix.rsplit('/', 1)[1]
        record = api.post('/api/v3/access-tokens', json={'name': 'Synthetic reader', 'workspaceIds': [wid], 'scopes': ['ledger:read']}).json()
        headers = {'Authorization': 'Bearer ' + record['token']}
        path = '/reports/economic-evidence?asOf=2026-08-31&through=2026-09-30'
        assert api.get('/api/v2' + path, headers=headers).status_code == 200
        assert api.get('/api/v3/workspaces/unapproved' + path, headers=headers).status_code == 404
        assert api.get('/api/v2/financial-accounts', headers=headers).status_code == 403
        assert api.post('/api/v2/reports/economic-evidence', headers=headers).status_code == 405
        writer = api.post('/api/v3/access-tokens', json={'name': 'Synthetic write-only', 'workspaceIds': [wid], 'scopes': ['ledger:write']}).json()['token']
        assert api.get('/api/v2' + path, headers={'Authorization': 'Bearer ' + writer}).status_code == 403
        api.api.cookies.clear()
        assert api.get('/api/v2' + path).status_code == 401


def test_stale_or_unconfirmed_living_balances_remain_missing_and_revisions_change(tmp_path):
    with client(tmp_path) as api:
        foundation(api)
        exact = api.get('/api/v2/reports/economic-evidence?asOf=2026-08-31&through=2026-09-30').json()['data']
        stale = api.get('/api/v2/reports/economic-evidence?asOf=2026-09-01&through=2026-09-30').json()['data']
        assert stale['coverage']['cashStocks'] is False and 'cash_stocks' in stale['missingFacts']
        assert next(row for row in stale['balances'] if row['segment'] == 'living')['cashBalance'] is None
        assert api.post('/api/v2/balance-records', json={
            'id': 'pending', 'subjectId': 'living', 'observedDate': '2026-09-01', 'currency': 'CNY',
            'amount': '600', 'confirmed': False, 'source': 'Synthetic unreviewed record',
        }).status_code == 201
        pending = api.get('/api/v2/reports/economic-evidence?asOf=2026-09-01&through=2026-09-30').json()['data']
        assert pending['coverage']['cashStocks'] is False
        assert pending['revision'] != stale['revision'] != exact['revision']
