"""Dedicated read grants are enforced by FC, not a client's hidden controls."""
from test_v3 import authenticated_client, create_workspace
from contextlib import contextmanager
import pytest


@contextmanager
def owner_client(tmp_path):
    api = authenticated_client(tmp_path)
    try:
        yield api
    finally:
        api.__exit__(None, None, None)


def test_living_reader_grant_is_single_vault_read_only_and_does_not_expose_investment(tmp_path):
    with owner_client(tmp_path) as api:
        workspace = create_workspace(api)
        other = create_workspace(api, 'Other sandbox')
        prefix = '/api/v3/workspaces/' + workspace['id']
        assert api.post(prefix + '/demo/load-synthetic?profile=economic-evidence&asOf=2026-08-31').status_code == 201
        created = api.post('/api/v3/access-tokens', json={
            'name': 'Living facts', 'workspaceIds': [workspace['id']], 'scopes': ['ledger:read'],
            'readGrant': {'mode': 'living', 'itemIds': []},
        })
        assert created.status_code == 201, created.text
        headers = {'Authorization': 'Bearer ' + created.json()['token']}
        assert created.json()['data']['readGrant'] == {'mode': 'living', 'itemIds': []}
        catalog = api.get(prefix + '/reader/catalog', headers=headers)
        assert catalog.status_code == 200, catalog.text
        items = catalog.json()['data']['items']
        assert items and all(item['segment'] == 'living' for item in items)
        denied = ['/journal-entries', '/financial-accounts', '/segments/investment/export',
                  '/vault-backup', '/reports/economic-evidence?asOf=2026-08-31&through=2026-09-30']
        assert all(api.get(prefix + path, headers=headers).status_code == 403 for path in denied)
        assert api.post(prefix + '/journal-entry-drafts', headers=headers, json={}).status_code == 403
        assert api.get('/api/v3/workspaces/' + other['id'] + '/reader/catalog', headers=headers).status_code == 404
        self_info = api.get('/api/v3/access-token-self', headers=headers).json()['data']
        assert self_info['readGrant'] == {'mode': 'living', 'itemIds': []}
        assert api.post('/api/v3/access-tokens/' + created.json()['data']['id'] + '/revoke').status_code == 200
        assert api.get(prefix + '/reader/catalog', headers=headers).status_code == 401


def test_selected_item_read_is_whole_revision_bound_and_excludes_other_accounts_and_private_notes(tmp_path):
    with owner_client(tmp_path) as api:
        workspace = create_workspace(api)
        prefix = '/api/v3/workspaces/' + workspace['id']
        assert api.post(prefix + '/demo/load-synthetic?profile=economic-evidence&asOf=2026-08-31').status_code == 201
        catalog = api.get(prefix + '/reader/catalog').json()['data']['items']
        selected = next(item for item in catalog if item['kind'] == 'account' and item['segment'] == 'living')
        other = next(item for item in catalog if item['kind'] == 'account' and item['segment'] == 'investment')
        created = api.post('/api/v3/access-tokens', json={
            'name': 'One account', 'workspaceIds': [workspace['id']], 'scopes': ['ledger:read'],
            'readGrant': {'mode': 'selected', 'itemIds': [selected['id']]},
        })
        assert created.status_code == 201
        headers = {'Authorization': 'Bearer ' + created.json()['token']}
        path = prefix + '/reader/items/' + selected['id']
        response = api.get(path, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()['data']
        assert data['itemId'] == selected['id'] and data['schemaVersion'] == 1
        assert data['kind'] == 'account' and data['segment'] == 'living'
        assert data['coverage'] == {'selectionOnly': True, 'externalCompleteness': 'unknown', 'financialAdviceReady': False}
        assert data['content']['account']['name'] == selected['label']
        assert data['content']['observations']
        assert all('source' not in row and 'note' not in row and 'reason' not in row for row in data['content']['observations'])
        assert data == api.get(path, headers=headers).json()['data']
        assert api.get(prefix + '/reader/items/' + other['id'], headers=headers).status_code == 403
        assert api.get(prefix + '/reports/month-to-date?asOf=2026-08-31', headers=headers).status_code == 403
        accounts = api.get(prefix + '/financial-accounts').json()['data']
        target = next(item for item in accounts if item['name'] == selected['label'])
        assert api.post(prefix + '/balance-records', json={'id': 'new-selected-balance', 'subjectId': target['id'],
            'observedDate': '2026-09-01', 'currency': 'CNY', 'amount': '123.45', 'confirmed': True,
            'source': 'PRIVATE-SOURCE-SENTINEL', 'note': 'PRIVATE-NOTE-SENTINEL'}).status_code == 201
        updated = api.get(path, headers=headers)
        assert updated.json()['data']['revision'] != data['revision']
        assert any(row.get('amount') == '123.45' for row in updated.json()['data']['content']['observations'])
        assert 'PRIVATE-' not in updated.text and other['label'] not in updated.text


def test_selected_grant_cannot_pre_authorize_unknown_future_items(tmp_path):
    with owner_client(tmp_path) as api:
        workspace = create_workspace(api)
        response = api.post('/api/v3/access-tokens', json={'name': 'Unknown item',
            'workspaceIds': [workspace['id']], 'scopes': ['ledger:read'],
            'readGrant': {'mode': 'selected', 'itemIds': ['account:' + 'a' * 32]}})
        assert response.status_code == 422
        assert api.get('/api/v3/access-tokens').json()['data'] == []


def test_whole_vault_catalog_and_safe_records_cover_real_financial_item_shapes(tmp_path):
    from test_v2 import client
    from test_personal_finance import seed_personal
    with client(tmp_path) as scoped:
        seed_personal(scoped)
        api, prefix = scoped.api, scoped.prefix
        wid = prefix.rsplit('/', 1)[1]
        created = api.post('/api/v3/access-tokens', json={'name': 'All financial facts',
            'workspaceIds': [wid], 'scopes': ['ledger:read'], 'readGrant': {'mode': 'all', 'itemIds': []}})
        assert created.status_code == 201
        headers = {'Authorization': 'Bearer ' + created.json()['token']}
        response = api.get(prefix + '/reader/catalog', headers=headers)
        assert response.status_code == 200
        items = response.json()['data']['items']
        assert {'account', 'asset', 'arrangement', 'transfer', 'report'} <= {item['kind'] for item in items}
        for item in items:
            if item['kind'] == 'report':
                continue
            result = api.get(prefix + '/reader/items/' + item['id'], headers=headers)
            assert result.status_code == 200, result.text
            facts = result.json()['data']['content']
            if item['kind'] == 'asset':
                assert facts['asset']['purchaseCost'] == '1000' and facts['asset']['assetType'] == 'vehicle'
            if item['kind'] == 'arrangement':
                assert [row['share'] for row in facts['residualShares']] == ['0.5', '0.5']
                assert facts['interestAgreements'][0]['monthlyAmount'] == '5'
            assert 'baselineEvidence' not in result.text and 'reason' not in facts


def test_dynamic_whole_vault_grant_sees_new_accounts_but_legacy_token_gets_no_new_personal_access(tmp_path):
    from test_v3 import create_access_token
    with owner_client(tmp_path) as api:
        workspace = create_workspace(api)
        prefix = '/api/v3/workspaces/' + workspace['id']
        assert api.post(prefix + '/demo/load-synthetic?profile=economic-evidence&asOf=2026-08-31').status_code == 201
        legacy = create_access_token(api, [workspace['id']], ['ledger:read'])
        legacy_headers = {'Authorization': 'Bearer ' + legacy}
        assert api.get(prefix + '/reader/catalog', headers=legacy_headers).status_code == 403
        self_info = api.get('/api/v3/access-token-self', headers=legacy_headers).json()['data']
        assert 'readGrant' not in self_info and self_info['expiresAt'] is None
        assert api.get(prefix + '/reports/month-to-date?asOf=2026-08-31', headers=legacy_headers).status_code == 200
        created = api.post('/api/v3/access-tokens', json={'name': 'Dynamic whole Vault',
            'workspaceIds': [workspace['id']], 'scopes': ['ledger:read'], 'readGrant': {'mode': 'all', 'itemIds': []}}).json()
        headers = {'Authorization': 'Bearer ' + created['token']}
        before = api.get(prefix + '/reader/catalog', headers=headers).json()['data']['items']
        base = next(value for value in api.get(prefix + '/financial-accounts').json()['data'] if value['segment'] == 'living')
        assert api.post(prefix + '/financial-accounts', json={**base, 'id': 'later-account',
            'code': 'later-account', 'name': 'Later account'}).status_code == 201
        after = api.get(prefix + '/reader/catalog', headers=headers).json()['data']['items']
        assert len(after) == len(before) + 1 and any(row['label'] == 'Later account' for row in after)
        # Even 'all' is financial-read-only, not raw backup/owner/management access.
        assert api.get(prefix + '/vault-backup', headers=headers).status_code == 403
        assert api.get(prefix + '/financial-accounts', headers=headers).status_code == 403
        assert api.get('/api/v3/access-tokens', headers=headers).status_code == 403


@pytest.mark.parametrize('mode,items,scopes,multiple', [
    ('all', [], ['ledger:read', 'ledger:write'], False), ('all', [], ['ledger:read'], True),
    ('living', ['account:' + 'a' * 32], ['ledger:read'], False), ('selected', [], ['ledger:read'], False),
    ('selected', ['account:' + 'a' * 32] * 2, ['ledger:read'], False),
    ('selected', ['../../vault-backup'], ['ledger:read'], False), ('unknown', [], ['ledger:read'], False),
])
def test_invalid_read_grants_are_atomic_and_never_issue_a_token(tmp_path, mode, items, scopes, multiple):
    with owner_client(tmp_path) as api:
        one, two = create_workspace(api), create_workspace(api, 'Other')
        response = api.post('/api/v3/access-tokens', json={'name': 'Invalid grant',
            'workspaceIds': [one['id'], two['id']] if multiple else [one['id']], 'scopes': scopes,
            'readGrant': {'mode': mode, 'itemIds': items}})
        assert response.status_code == 422
        assert api.get('/api/v3/access-tokens').json()['data'] == []
