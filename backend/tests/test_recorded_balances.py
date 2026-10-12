"""Dated balances through the released Workspace HTTP boundary, synthetic data only."""
from test_v2 import client
import csv
import io

import pytest


def seed(api):
    assert api.post('/api/v2/commodities', json={'code': 'CNY', 'kind': 'currency', 'scale': 2, 'name': 'Synthetic CNY'}).status_code == 201
    assert api.put('/api/v2/finance-parties/owner', json={'id': 'owner', 'name': 'Synthetic owner'}).status_code == 200
    assert api.post('/api/v2/financial-accounts', json={
        'id': 'wallet', 'code': 'L001', 'name': 'Synthetic wallet', 'type': 'asset', 'subtype': 'cash',
        'segment': 'living', 'balanceSource': 'monthly_snapshot', 'ownerPartyId': 'owner',
        'allowedCommodityCodes': ['CNY'],
    }).status_code == 201


def record(identity='first', day='2026-08-12', amount='120.25', **extra):
    return {'id': identity, 'subjectId': 'wallet', 'observedDate': day, 'currency': 'CNY',
            'amount': amount, 'source': 'Synthetic dated statement', 'confirmed': True, **extra}


def test_balance_has_an_actual_date_and_server_receipt_timestamp(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        response = api.post('/api/v2/balance-records', json=record())
        assert response.status_code == 201, response.text
        saved = response.json()['data']
        assert saved['observedDate'] == '2026-08-12'
        assert saved['month'] == '2026-08'
        assert saved['amount'] == '120.25'
        assert saved['recordedAt'] != saved['observedDate']
        assert api.get('/api/v2/balance-records').json()['data'] == [saved]


def test_month_selects_actual_latest_date_not_submission_order_and_never_fills_gaps(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        for item in [record('early', '2026-08-02', '100'), record('later', '2026-08-12', '120.25'),
                     record('same-day', '2026-08-12', '125.35'), record('backfill', '2026-08-05', '110')]:
            assert api.post('/api/v2/balance-records', json=item).status_code == 201
        response = api.get('/api/v2/reports/living-recorded-balances?month=2026-08')
        assert response.status_code == 200, response.text
        report = response.json()['data']
        row = report['accounts'][0]
        assert (row['latestRecordId'], row['observedDate'], row['amount']) == ('same-day', '2026-08-12', '125.35')
        assert (row['previousRecordId'], row['previousDate'], row['previousAmount'], row['change']) == ('later', '2026-08-12', '120.25', '5.1')
        assert report['coverage']['balancesAreMonthEnd'] is False
        assert report['coverage']['differencesAreIncomeOrExpenses'] is False
        empty = api.get('/api/v2/reports/living-recorded-balances?month=2026-09').json()['data']
        assert empty['accounts'][0]['status'] == 'unknown'
        assert empty['accounts'][0]['amount'] is None
        assert empty['accounts'][0]['change'] is None
        assert empty['accounts'][0]['observedDate'] is None
        assert empty['coverage']['complete'] is False


def test_dated_records_do_not_rewrite_legacy_month_end_reports_or_infer_dates(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        old = {'id': 'legacy-month', 'subjectId': 'wallet', 'month': '2026-08', 'kind': 'balance',
               'currency': 'CNY', 'amount': '800', 'source': 'Synthetic old monthly observation', 'confirmed': True}
        assert api.post('/api/v2/monthly-observations', json=old).status_code == 201
        before = api.get('/api/v2/reports/personal-balance-sheet?month=2026-08').json()['data']
        assert api.post('/api/v2/balance-records', json=record()).status_code == 201
        after = api.get('/api/v2/reports/personal-balance-sheet?month=2026-08').json()['data']
        assert after == before
        stored = api.get('/api/v2/monthly-observations').json()['data']
        assert [value['id'] for value in stored] == ['legacy-month']
        assert not next(value for value in stored if value['id'] == 'legacy-month').get('observedDate')
        assert [value['id'] for value in api.get('/api/v2/balance-records').json()['data']] == ['first']


def test_backup_roundtrip_preserves_multiple_same_day_records_and_corrections(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        for item in [record('one'), record('two', amount='121.25'),
                     record('corrected', amount='122.25', supersedes='two', reason='Synthetic statement correction')]:
            assert api.post('/api/v2/balance-records', json=item).status_code == 201
        backup = api.get('/api/v2/vault-backup').json()['data']
        target = api.post('/api/v3/workspaces', json={'displayName': 'Synthetic restore', 'kind': 'sandbox'}).json()['data']['id']
        prefix = f'/api/v3/workspaces/{target}'
        response = api.post(prefix + '/vault-backup/restore', json=backup)
        assert response.status_code == 201, response.text
        assert api.get(prefix + '/vault-backup').json()['data']['sha256'] == backup['sha256']
        assert api.get(prefix + '/balance-records').json()['data'] == api.get('/api/v2/balance-records').json()['data']
        assert api.get(prefix + '/reports/living-recorded-balances?month=2026-08').json()['data']['accounts'][0]['change'] == '2'
        exported = list(csv.DictReader(io.StringIO(api.get('/api/v2/segments/living/export.csv').text.lstrip('\ufeff'))))
        assert [value['observedDate'] for value in exported] == ['2026-08-12'] * 3


@pytest.mark.parametrize('changes', [
    {'observedDate': '2026-02-30'}, {'observedDate': '20260812'}, {'observedDate': 20260812},
    {'observedDate': '2026-08-12T00:00:00Z'}, {'observedDate': '9999-12-31'},
    {'amount': 120.25}, {'amount': '0.001'}, {'currency': 'USD'}, {'subjectId': 'absent'},
    {'source': ''}, {'supersedes': 'absent', 'reason': 'Synthetic correction'},
])
def test_invalid_dates_money_or_references_fail_without_writes(tmp_path, changes):
    with client(tmp_path) as api:
        seed(api)
        response = api.post('/api/v2/balance-records', json=record(**changes))
        assert response.status_code in (409, 422), response.text
        assert api.get('/api/v2/balance-records').json()['data'] == []


def test_explicit_correction_retains_original_and_locks_used_account(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        original = api.post('/api/v2/balance-records', json=record()).json()['data']
        corrected = record('corrected', amount='123.25', supersedes='first', reason='Synthetic reviewed correction')
        assert api.post('/api/v2/balance-records', json=corrected).status_code == 201
        assert api.post('/api/v2/balance-records', json={**corrected, 'id': 'stale'}).status_code == 409
        assert api.post('/api/v2/balance-records', json=record('wrong-date', '2026-08-13', supersedes='corrected', reason='Wrong date')).status_code == 409
        assert api.post('/api/v2/balance-records', json=record('no-reason', supersedes='corrected')).status_code == 422
        assert api.get('/api/v2/balance-records').json()['data'][0] == original
        assert api.delete('/api/v2/financial-accounts/wallet').status_code == 422
        account = api.get('/api/v2/financial-accounts').json()['data'][0]
        assert api.put('/api/v2/financial-accounts/wallet', json={**account, 'endMonth': '2026-07'}).status_code == 422
        assert api.put('/api/v2/financial-accounts/wallet', json={**account, 'status': 'inactive', 'endMonth': '2026-08'}).status_code == 200
        assert api.post('/api/v2/balance-records', json=record('after-end', '2026-09-01')).status_code == 422


def test_exact_difference_across_recording_gap_and_pending_never_falls_back(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        for item in [record('before-gap', '2026-05-02', '9007199254740993.01'),
                     record('after-gap', '2026-08-12', '9007199254740993.12')]:
            assert api.post('/api/v2/balance-records', json=item).status_code == 201
        row = api.get('/api/v2/reports/living-recorded-balances?month=2026-08').json()['data']['accounts'][0]
        assert (row['previousDate'], row['change']) == ('2026-05-02', '0.11')
        assert api.get('/api/v2/reports/living-recorded-balances?month=2026-06').json()['data']['accounts'][0]['amount'] is None
        assert api.post('/api/v2/balance-records', json=record('pending', '2026-08-13', '0', confirmed=False)).status_code == 201
        report = api.get('/api/v2/reports/living-recorded-balances?month=2026-08').json()['data']
        assert (report['accounts'][0]['latestRecordId'], report['accounts'][0]['amount'], report['accounts'][0]['status']) == ('pending', '0', 'pending')
        assert report['accounts'][0]['change'] is None
        assert report['coverage']['complete'] is False


def test_historical_balances_respect_the_account_purpose_period(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        account = api.get('/api/v2/financial-accounts').json()['data'][0]
        account.update(status='inactive', startMonth='2026-08')
        assert api.put('/api/v2/financial-accounts/wallet', json=account).status_code == 200
        assert api.post('/api/v2/balance-records', json=record()).status_code == 422
        account['endMonth'] = '2026-08'
        assert api.put('/api/v2/financial-accounts/wallet', json=account).status_code == 200
        assert api.post('/api/v2/balance-records', json=record('before-start', '2026-07-31')).status_code == 422
        assert api.post('/api/v2/balance-records', json=record('within-purpose')).status_code == 201
        assert api.post('/api/v2/balance-records', json=record('after-end', '2026-09-01')).status_code == 422
        assert [value['id'] for value in api.get('/api/v2/balance-records').json()['data']] == ['within-purpose']


def test_recorded_balances_remain_owner_workspace_scoped(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        assert api.post('/api/v2/balance-records', json=record()).status_code == 201
        target = api.post('/api/v3/workspaces', json={'displayName': 'Synthetic empty', 'kind': 'sandbox'}).json()['data']['id']
        assert api.get(f'/api/v3/workspaces/{target}/balance-records').json()['data'] == []
        token = api.post('/api/v3/access-tokens', json={'name': 'Synthetic reader', 'workspaceIds': [api.prefix.rsplit('/', 1)[1]], 'scopes': ['ledger:read']}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        assert api.get('/api/v2/balance-records', headers=headers).status_code == 403
        assert api.get('/api/v2/reports/living-recorded-balances?month=2026-08', headers=headers).status_code == 403
        assert api.post('/api/v2/balance-records', json=record('denied'), headers=headers).status_code == 403
        assert api.post('/api/v2/balance-records', json=record('bad-origin'), headers={'Origin': 'https://untrusted.invalid'}).status_code == 403
