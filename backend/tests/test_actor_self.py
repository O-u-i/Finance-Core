"""Current-token claims through the public HTTP contract; synthetic credentials only."""
from fastapi.testclient import TestClient

from finance_core.app_v3 import create_app
from test_v3 import create_workspace


def test_token_self_returns_only_its_own_exact_claims_and_no_secret(tmp_path):
    with TestClient(create_app(data_root=tmp_path / 'data', admin_token='synthetic-owner')) as api:
        assert api.post('/api/v3/session', json={'adminToken': 'synthetic-owner'}).status_code == 200
        workspace = create_workspace(api)
        create_workspace(api, 'Other synthetic Workspace')
        created = api.post('/api/v3/access-tokens', json={
            'name': 'Synthetic private token name', 'workspaceIds': [workspace['id']],
            'scopes': ['ledger:write', 'ledger:read'], 'expiresAt': '2099-01-01T00:00:00+00:00',
        }).json()
        headers = {'Authorization': 'Bearer ' + created['token']}
        response = api.get('/api/v3/access-token-self', headers=headers)
        assert response.status_code == 200
        assert response.json() == {'data': {
            'tokenId': created['data']['id'], 'actorKind': 'token', 'status': 'active',
            'workspaceIds': [workspace['id']], 'scopes': ['ledger:read', 'ledger:write'],
            'expiresAt': '2099-01-01T00:00:00+00:00',
        }}
        assert created['token'] not in response.text
        assert 'Synthetic private token name' not in response.text
        assert api.get('/api/v3/access-token-self').status_code == 403
        assert api.get('/api/v3/access-tokens', headers=headers).status_code == 403
        assert api.post('/api/v3/access-token-self', headers=headers).status_code == 405
        assert api.post('/api/v3/access-tokens/' + created['data']['id'] + '/revoke').status_code == 200
        assert api.get('/api/v3/access-token-self', headers=headers).status_code == 401
        api.cookies.clear()
        assert api.get('/api/v3/access-token-self').status_code == 401
