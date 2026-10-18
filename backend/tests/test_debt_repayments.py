"""Debt timing is explicit, revision-bound and tested through Workspace HTTP."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json

import pytest
from fastapi.testclient import TestClient

from finance_core.app_v3 import create_app
from finance_core.schema_migration import fingerprint
from test_economic_evidence import foundation
from test_v2 import client, create_and_post


REPORT = '/api/v2/reports/economic-evidence?asOf=2026-08-31&through=2026-09-30'
BALANCE = '/api/v2/debt-repayment-balance?accountId=debt&currency=CNY&asOf=2026-08-31'
ARRANGEMENTS = '/api/v2/debt-repayment-arrangements'


def debt_foundation(api):
    foundation(api)
    assert api.post('/api/v2/accounts', json={
        'id': 'debt', 'code': '2001', 'name': 'PRIVATE LENDER', 'type': 'liability',
        'allowedCommodityCodes': ['CNY'],
    }).status_code == 201
    create_and_post(api, {'id': 'borrow', 'date': '2026-08-20', 'description': 'PRIVATE BORROWING',
        'balancingCommodityCode': 'CNY', 'postings': [
            {'id': 'borrow-1', 'accountId': 'cash-cny', 'side': 'debit', 'units': '120', 'commodityCode': 'CNY'},
            {'id': 'borrow-2', 'accountId': 'debt', 'side': 'credit', 'units': '120', 'commodityCode': 'CNY'},
        ]})


def draft(api, identity='repayment', **changes):
    quote = api.get(BALANCE)
    assert quote.status_code == 200
    assert quote.json()['data']['balance'] == '120'
    return {'id': identity, 'accountId': 'debt', 'currency': 'CNY', 'asOf': '2026-08-31',
        'balanceRevision': quote.json()['data']['balanceRevision'],
        'payments': [{'dueDate': '2026-09-10', 'amount': '20'}, {'dueDate': '2026-10-10', 'amount': '100'}],
        'source': 'PRIVATE AGREEMENT', 'reason': 'PRIVATE REVIEW', **changes}


def confirm(api, item):
    return api.post(ARRANGEMENTS + '/' + item['id'] + '/confirm', json={
        'expectedRevision': item['revision'], 'expectedBalanceRevision': item['balanceRevision'], 'confirmed': True,
    })


def test_debt_draft_requires_confirmation_and_survives_restart_without_changing_journal(tmp_path):
    with client(tmp_path) as api:
        debt_foundation(api)
        journal = api.get('/api/v2/journal-entries').json()
        missing = api.get(REPORT).json()['data']
        assert missing['missingFacts'] == ['dated_obligations']
        response = api.post(ARRANGEMENTS, json=draft(api))
        assert response.status_code == 201
        pending = response.json()['data']
        assert pending['status'] == 'draft'
        assert api.get(REPORT).json()['data']['missingFacts'] == ['dated_obligations']
        response = confirm(api, pending)
        assert response.status_code == 200
        stored = response.json()['data']
        assert stored['status'] == 'confirmed'
        report = api.get(REPORT).json()['data']
        assert report['missingFacts'] == []
        assert report['debtRepayments'] == [{'dueDate': '2026-09-10', 'currency': 'CNY', 'amount': '20', 'count': 1}]
        assert report['debtOutsideHorizon'] == [{'currency': 'CNY', 'amount': '100', 'count': 1}]
        assert report['debtBasis'] == 'confirmed-current-balance-only-future-charges-unknown'
        assert 'PRIVATE' not in api.get(REPORT).text and '"accountId"' not in api.get(REPORT).text
        assert api.get('/api/v2/journal-entries').json() == journal
        prefix = api.prefix
    app = create_app(data_root=tmp_path / 'v3-data', admin_token='test-admin')
    with TestClient(app) as api:
        api.post('/api/v3/session', json={'adminToken': 'test-admin'})
        assert api.get(prefix + '/debt-repayment-arrangements').json()['data'] == [stored]
        assert api.get(prefix + REPORT[len('/api/v2'):]).json()['data']['revision'] == report['revision']


def test_full_backup_preserves_debt_history_and_legacy_export_refuses_loss(tmp_path):
    with client(tmp_path) as api:
        debt_foundation(api)
        pending = api.post(ARRANGEMENTS, json=draft(api)).json()['data']
        assert confirm(api, pending).status_code == 200
        saved = api.get(ARRANGEMENTS).json()['data']
        backup = api.get('/api/v2/vault-backup').json()['data']
        assert backup['formatVersion'] == 4 and backup['schemaVersion'] == 3
        assert api.get('/api/v2/backup').status_code == 409
        assert api.delete('/api/v2/accounts/debt').status_code == 422
        assert api.post('/api/v2/vault-backup/restore', json=backup).status_code == 422
        assert api.get(ARRANGEMENTS).json()['data'] == saved
        created = api.post('/api/v3/workspaces', json={'displayName': 'Restore target', 'kind': 'sandbox'})
        api.prefix = '/api/v3/workspaces/' + created.json()['data']['id']
        assert api.post('/api/v2/vault-backup/restore', json=backup).status_code == 201
        assert api.get(ARRANGEMENTS).json()['data'] == saved
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == backup['sha256']
        assert api.get(REPORT).json()['data']['missingFacts'] == []


def test_explicit_confirmation_is_once_only_and_corrections_preserve_confirmed_history(tmp_path):
    with client(tmp_path) as api:
        debt_foundation(api)
        pending = api.post(ARRANGEMENTS, json=draft(api)).json()['data']
        payload = {'expectedRevision': 1, 'expectedBalanceRevision': pending['balanceRevision'], 'confirmed': False}
        assert api.post(ARRANGEMENTS + '/repayment/confirm', json=payload).status_code == 422
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: confirm(api, pending), range(2)))
        assert sorted(response.status_code for response in responses) == [200, 409]
        original = next(response.json()['data'] for response in responses if response.status_code == 200)
        changed = draft(api, 'correction', supersedes='repayment', payments=[{'dueDate': '2026-08-30', 'amount': '120'}])
        correction = api.post(ARRANGEMENTS, json=changed).json()['data']
        assert api.get(REPORT).json()['data']['debtRepayments'][0]['dueDate'] == '2026-09-10'
        assert confirm(api, correction).status_code == 200
        assert next(value for value in api.get(ARRANGEMENTS).json()['data'] if value['id'] == 'repayment') == original
        assert api.get(REPORT).json()['data']['debtRepayments'] == [
            {'dueDate': '2026-08-30', 'currency': 'CNY', 'amount': '120', 'count': 1}]
        assert api.put(ARRANGEMENTS + '/repayment', json=changed).status_code == 405
        assert api.delete(ARRANGEMENTS + '/repayment').status_code == 405


def test_changed_balance_refuses_old_draft_and_marks_confirmed_timing_unknown(tmp_path):
    with client(tmp_path) as api:
        debt_foundation(api)
        pending = api.post(ARRANGEMENTS, json=draft(api)).json()['data']
        assert confirm(api, pending).status_code == 200
        correction = api.post(ARRANGEMENTS, json=draft(api, 'later', supersedes='repayment')).json()['data']
        create_and_post(api, {'id': 'payment', 'date': '2026-08-25', 'description': 'Synthetic repayment',
            'balancingCommodityCode': 'CNY', 'postings': [
                {'id': 'payment-1', 'accountId': 'debt', 'side': 'debit', 'units': '20', 'commodityCode': 'CNY'},
                {'id': 'payment-2', 'accountId': 'cash-cny', 'side': 'credit', 'units': '20', 'commodityCode': 'CNY'},
            ]})
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        assert confirm(api, correction).status_code == 409
        report = api.get(REPORT).json()['data']
        assert report['missingFacts'] == ['dated_obligations'] and report['debtRepayments'] == []
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before


@pytest.mark.parametrize('changes', [
    {'payments': [{'dueDate': None, 'amount': '120'}]},
    {'payments': [{'dueDate': '2026-02-30', 'amount': '120'}]},
    {'payments': [{'dueDate': '2026-09-01', 'amount': 120}]},
    {'payments': [{'dueDate': '2026-09-01', 'amount': '119.99'}]},
    {'payments': [{'dueDate': '2026-09-01', 'amount': '0.001'}, {'dueDate': '2026-10-01', 'amount': '119.999'}]},
    {'source': ' '}, {'accountId': 'cash-cny'}, {'supersedes': 'not-confirmed'},
])
def test_invalid_or_incomplete_schedule_never_changes_finance(tmp_path, changes):
    with client(tmp_path) as api:
        debt_foundation(api)
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        response = api.post(ARRANGEMENTS, json=draft(api, **changes))
        assert response.status_code in {409, 422}
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before
        assert api.get(ARRANGEMENTS).json()['data'] == []


def test_debt_write_is_scoped_and_read_token_cannot_create_or_confirm(tmp_path):
    with client(tmp_path) as api:
        debt_foundation(api)
        item = draft(api)
        wid = api.prefix.rsplit('/', 1)[1]
        token = api.post('/api/v3/access-tokens', json={'name': 'Synthetic reader', 'workspaceIds': [wid], 'scopes': ['ledger:read']}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        assert api.get(BALANCE, headers=headers).status_code == 200
        assert api.get(ARRANGEMENTS, headers=headers).status_code == 200
        assert api.post(ARRANGEMENTS, json=item, headers=headers).status_code == 403
        pending = api.post(ARRANGEMENTS, json=item).json()['data']
        assert api.post(ARRANGEMENTS + '/repayment/confirm', json={
            'expectedRevision': 1, 'expectedBalanceRevision': pending['balanceRevision'], 'confirmed': True,
        }, headers=headers).status_code == 403
        assert api.get('/api/v3/workspaces/unapproved/debt-repayment-arrangements', headers=headers).status_code == 404


def test_restore_refuses_tampered_confirmation_atomically(tmp_path):
    with client(tmp_path) as api:
        debt_foundation(api)
        pending = api.post(ARRANGEMENTS, json=draft(api)).json()['data']
        assert confirm(api, pending).status_code == 200
        backup = copy.deepcopy(api.get('/api/v2/vault-backup').json()['data'])
        record = json.loads(backup['payload']['debt_repayment_arrangements_v3'][0]['payload_json'])
        record['payments'][0]['amount'] = '999'
        backup['payload']['debt_repayment_arrangements_v3'][0]['payload_json'] = json.dumps(record)
        backup['sha256'] = fingerprint(backup['payload'])
        created = api.post('/api/v3/workspaces', json={'displayName': 'Tamper target', 'kind': 'sandbox'})
        api.prefix = '/api/v3/workspaces/' + created.json()['data']['id']
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        assert api.post('/api/v2/vault-backup/restore', json=backup).status_code == 422
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before


@pytest.mark.parametrize('format_version', [3, 4])
def test_legacy_restore_cannot_bypass_owner_gate_for_full_vault_history(tmp_path, format_version):
    with client(tmp_path) as api:
        if format_version == 4:
            debt_foundation(api)
            pending = api.post(ARRANGEMENTS, json=draft(api)).json()['data']
            assert confirm(api, pending).status_code == 200
        else:
            foundation(api)
        backup = api.get('/api/v2/vault-backup').json()['data']
        assert backup['formatVersion'] == format_version
        created = api.post('/api/v3/workspaces', json={'displayName': 'Scoped restore target', 'kind': 'sandbox'}).json()['data']
        api.prefix = '/api/v3/workspaces/' + created['id']
        token = api.post('/api/v3/access-tokens', json={'name': 'Synthetic ledger writer', 'workspaceIds': [created['id']],
            'scopes': ['ledger:read', 'ledger:write']}).json()['token']
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        response = api.post('/api/v2/backup/restore', json=backup, headers={'Authorization': 'Bearer ' + token})
        assert response.status_code == 403
        assert response.json()['error']['code'] == 'TOKEN_SCOPE_DENIED'
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before
        assert api.post('/api/v2/backup/restore', json=backup).status_code == 201
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == backup['sha256']


def test_invalid_backup_version_is_validation_failure_not_partial_restore_or_internal_error(tmp_path):
    with client(tmp_path) as api:
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        response = api.post('/api/v2/vault-backup/restore', json={'formatVersion': {}, 'schemaVersion': 3, 'payload': {}})
        assert response.status_code == 422
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before
