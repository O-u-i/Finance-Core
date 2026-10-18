"""Explicit synthetic profile: empty schema-3 sandboxes only, through HTTP."""
from test_v2 import client


def test_economic_demo_profile_is_opt_in_atomic_and_never_loads_personal(tmp_path):
    with client(tmp_path) as api:
        wid = api.prefix.rsplit('/', 1)[1]
        token = api.post('/api/v3/access-tokens', json={'name': 'Synthetic acceptance', 'workspaceIds': [wid],
            'scopes': ['ledger:read', 'ledger:write']}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        endpoint = '/api/v2/demo/load-synthetic?profile=economic-evidence&asOf=2026-08-31'
        result = api.post(endpoint, headers=headers)
        assert result.status_code == 201
        assert result.json()['profile'] == 'economic-evidence'
        report = api.get('/api/v2/reports/economic-evidence?asOf=2026-08-31&through=2026-09-30', headers=headers).json()['data']
        assert report['missingFacts'] == []
        assert report['debtRepayments'] == [{'dueDate': '2026-09-07', 'currency': 'CNY', 'amount': '200', 'count': 1}]
        assert report['debtOutsideHorizon'] == [{'currency': 'CNY', 'amount': '1000', 'count': 1}]
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        assert api.post(endpoint, headers=headers).status_code == 409
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before
        personal = api.post('/api/v3/workspaces', json={'displayName': 'Synthetic personal target', 'kind': 'personal'}).json()['data']
        api.prefix = '/api/v3/workspaces/' + personal['id']
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        assert api.post(endpoint).status_code == 403
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before
