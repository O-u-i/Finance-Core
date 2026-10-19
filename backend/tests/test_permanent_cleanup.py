"""Owner-only irreversible cleanup; all Vaults and credentials here are synthetic."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
from threading import Event

import pytest
from fastapi.testclient import TestClient

from finance_core.app_v3 import create_app


@pytest.fixture
def api(tmp_path):
    with TestClient(create_app(data_root=tmp_path / 'data', admin_token='synthetic-admin')) as client:
        assert client.post('/api/v3/session', json={'adminToken': 'synthetic-admin'}).status_code == 200
        yield client


def vault(api, name='Synthetic cleanup'):
    return api.post('/api/v3/workspaces', json={'displayName': name, 'kind': 'sandbox'}).json()['data']['id']


def token(api, wid, **extra):
    return api.post('/api/v3/access-tokens', json={
        'name': 'Synthetic token', 'workspaceIds': [wid], 'scopes': ['ledger:read'], **extra,
    }).json()


def quarantined_file(api, wid):
    result = api.delete(f'/api/v3/workspaces/{wid}').json()
    row = api.app.state.registry.connection.execute('SELECT inverse_json FROM control_undo WHERE operation_id=?', (result['undo']['operationId'],)).fetchone()
    return Path(json.loads(row[0])['moved'][0]['target']), result['undo']['undoToken']


def purge(api, wid, name='Synthetic cleanup', **options):
    return api.post(f'/api/v3/workspaces/{wid}/purge', json={'confirmName': name}, **options)


def assert_no_control_undo(api, undo):
    assert api.app.state.registry.undo_control(undo) is None
    response = api.post('/api/v3/undo', json={'undoToken': undo})
    # Existing contract: an unavailable control undo without a ledger workspace is 422.
    assert response.status_code == 422 and response.json()['error']['code'] == 'INVALID_REQUEST'


def test_purge_removes_one_file_and_record_revokes_only_affected_tokens_and_cannot_undo(api):
    wid, other = vault(api), vault(api, 'Synthetic retained')
    affected, retained = token(api, wid), token(api, other)
    path, undo = quarantined_file(api, wid)
    directory = path.parent
    assert list(directory.iterdir()) == [path]
    response = purge(api, wid)
    assert response.status_code == 200 and response.json()['data']['fileRemoved'] is True
    assert not path.exists() and directory.is_dir() and list(directory.iterdir()) == []
    store = api.app.state.registry
    assert store.get_workspace(wid) is None and store.get_workspace(other)['status'] == 'active'
    assert store.get_access_token(affected['data']['id'])['revokedAt']
    assert store.get_access_token(retained['data']['id'])['revokedAt'] is None
    assert_no_control_undo(api, undo)
    assert purge(api, wid).status_code == 404
    assert str(directory) not in response.text


def test_purge_requires_quarantine_exact_name_owner_and_same_origin(api):
    wid = vault(api)
    assert purge(api, wid).status_code == 409
    credential = token(api, wid, scopes=['ledger:read', 'ledger:write'])['token']
    path, undo = quarantined_file(api, wid)
    assert purge(api, wid, 'Wrong name').status_code == 409
    assert purge(api, wid, headers={'Authorization': 'Bearer ' + credential}).status_code == 403
    assert purge(api, wid, headers={'Origin': 'https://external.example'}).status_code == 403
    assert path.is_file()
    assert api.post('/api/v3/undo', json={'undoToken': undo}).status_code == 200


@pytest.mark.parametrize('change', ['additional-file', 'hardlink', 'missing-file'])
def test_purge_refuses_unknown_or_shared_files_without_consuming_undo(api, change):
    wid = vault(api)
    path, undo = quarantined_file(api, wid)
    if change == 'additional-file':
        path.with_name(path.name + '-wal').write_bytes(b'synthetic sidecar requiring manual review')
    elif change == 'hardlink':
        os.link(path, path.parent.parent / 'synthetic-preserved.sqlite3')
    else:
        path.replace(path.parent.parent / 'synthetic-preserved.sqlite3')
    response = purge(api, wid)
    assert response.status_code == 409 and response.json()['error']['code'] == 'WORKSPACE_PURGE_REFUSED'
    assert str(path) not in response.text
    store = api.app.state.registry
    assert store.get_workspace(wid)['status'] == 'quarantined'
    assert not store.connection.execute("SELECT 1 FROM audit_events WHERE operation='workspace.purge.authorized'").fetchone()
    assert store.connection.execute('SELECT consumed_at FROM control_undo WHERE operation_type=? AND workspace_id=?', ('workspace.quarantine', wid)).fetchone()[0] is None


@pytest.mark.parametrize('failed_commit', [1, 2])
def test_purge_commit_failures_never_enable_restore_of_deleted_file_and_explicit_retry_finishes(api, monkeypatch, failed_commit):
    wid = vault(api)
    path, undo = quarantined_file(api, wid)
    store = api.app.state.registry
    original, calls = store.transaction, []
    @contextmanager
    def failing_transaction():
        calls.append(1)
        with original():
            yield
            if len(calls) == failed_commit:
                raise sqlite3.OperationalError('synthetic commit failure')
    monkeypatch.setattr(store, 'transaction', failing_transaction)
    response = purge(api, wid)
    assert response.status_code == 409 and store.get_workspace(wid)['status'] == 'quarantined'
    assert path.exists() is (failed_commit == 1)
    monkeypatch.setattr(store, 'transaction', original)
    if failed_commit == 2:
        assert_no_control_undo(api, undo)
    assert purge(api, wid).status_code == 200
    assert not path.exists() and store.get_workspace(wid) is None


def test_purge_unlink_failure_keeps_file_and_only_an_explicit_retry_removes_it(api, monkeypatch):
    wid = vault(api)
    path, undo = quarantined_file(api, wid)
    original = Path.unlink
    def fail_unlink(self, *args, **kwargs):
        if self == path:
            raise PermissionError('synthetic locked file')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', fail_unlink)
    assert purge(api, wid).status_code == 409 and path.exists()
    assert_no_control_undo(api, undo)
    monkeypatch.setattr(Path, 'unlink', original)
    assert purge(api, wid).status_code == 200 and not path.exists()


def test_purge_and_concurrent_restore_cannot_resurrect_the_deleted_database(api, monkeypatch):
    wid = vault(api)
    path, undo = quarantined_file(api, wid)
    entered, resume = Event(), Event()
    original = Path.unlink
    def paused_unlink(self, *args, **kwargs):
        if self == path:
            entered.set()
            assert resume.wait(5)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', paused_unlink)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(purge, api, wid)
        assert entered.wait(5)
        restoring = pool.submit(api.post, '/api/v3/undo', json={'undoToken': undo})
        resume.set()
        assert pending.result(timeout=10).status_code == 200
        assert restoring.result(timeout=10).status_code == 422
    assert not path.exists() and not api.app.state.registry.vaults.path_for(wid).exists()


@pytest.mark.parametrize('inactive', ['revoked', 'expired'])
def test_inactive_token_record_and_read_grant_can_be_deleted_without_authentication_revival(api, inactive):
    wid = vault(api)
    extra = {'readGrant': {'mode': 'all', 'itemIds': []}}
    if inactive == 'expired':
        extra['expiresAt'] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    issued = token(api, wid, **extra)
    tid = issued['data']['id']
    if inactive == 'revoked':
        assert api.post(f'/api/v3/access-tokens/{tid}/revoke').status_code == 200
    response = api.request('DELETE', f'/api/v3/access-tokens/{tid}', json={'confirmName': 'Synthetic token'})
    assert response.status_code == 200
    store = api.app.state.registry
    assert store.get_access_token(tid) is None and store.authenticate_token(issued['token']) is None
    assert store.connection.execute('SELECT 1 FROM access_token_read_grants WHERE token_id=?', (tid,)).fetchone() is None
    assert issued['token'] not in response.text


def test_active_token_delete_and_wrong_confirmation_are_refused_and_tokens_are_not_owners(api):
    wid = vault(api)
    issued = token(api, wid)
    url = '/api/v3/access-tokens/' + issued['data']['id']
    body = {'confirmName': 'Synthetic token'}
    assert api.request('DELETE', url, json=body).status_code == 409
    assert api.request('DELETE', url, json=body, headers={'Authorization': 'Bearer ' + issued['token']}).status_code == 403
    assert api.post(url + '/revoke').status_code == 200
    assert api.request('DELETE', url, json={'confirmName': 'Wrong name'}).status_code == 409
    assert api.app.state.registry.get_access_token(issued['data']['id']) is not None


@pytest.mark.parametrize('scopes', [['ledger:read'], ['ledger:write'], ['ledger:read', 'ledger:write']])
def test_generic_scopes_stay_exact_and_never_gain_management_or_frag_reader_grants(api, scopes):
    wid = vault(api)
    issued = token(api, wid, scopes=scopes)
    assert set(issued['data']['scopes']) == set(scopes) and 'readGrant' not in issued['data']
    headers = {'Authorization': 'Bearer ' + issued['token']}
    assert api.get(f'/api/v3/workspaces/{wid}/dashboard', headers=headers).status_code == (200 if 'ledger:read' in scopes else 403)
    assert api.post(f'/api/v3/workspaces/{wid}/commodities', json={'code': 'SYN', 'name': 'Synthetic', 'kind': 'currency', 'scale': 2}, headers=headers).status_code == (201 if 'ledger:write' in scopes else 403)
    assert api.get('/api/v3/access-tokens', headers=headers).status_code == 403
