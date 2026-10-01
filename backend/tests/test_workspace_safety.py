from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from finance_core.app_v3 import create_app


@pytest.fixture
def api(tmp_path):
    with TestClient(create_app(data_root=tmp_path / 'data', admin_token='synthetic-admin')) as client:
        assert client.post('/api/v3/session', json={'adminToken': 'synthetic-admin'}).status_code == 200
        yield client


def workspace(api):
    return api.post('/api/v3/workspaces', json={'displayName': 'Synthetic', 'kind': 'sandbox'}).json()['data']['id']


def test_archived_ledger_undo_is_read_only(api):
    wid = workspace(api)
    result = api.post(f'/api/v3/workspaces/{wid}/commodities', json={'code': 'USD', 'name': 'Dollar', 'kind': 'currency', 'scale': 2})
    token = result.json()['undo']['undoToken']
    api.patch(f'/api/v3/workspaces/{wid}', json={'status': 'archived'})
    response = api.post('/api/v3/undo', json={'workspaceId': wid, 'undoToken': token})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'WORKSPACE_ARCHIVED'


def test_latest_undo_never_reopens_quarantined_vault(api):
    wid = workspace(api)
    path = api.app.state.registry.vaults.path_for(wid)
    assert api.delete(f'/api/v3/workspaces/{wid}').status_code == 200
    assert not path.exists()
    assert api.get('/api/v3/undo/latest', params={'workspace_id': wid}).status_code == 404
    assert not path.exists()


def test_missing_active_vault_never_creates_replacement_database(api):
    wid = workspace(api)
    store = api.app.state.registry
    path = store.vaults.path_for(wid)
    store.vaults.close(wid)
    preserved = path.with_name('synthetic-preserved.sqlite3')
    path.replace(preserved)
    response = api.get(f'/api/v3/workspaces/{wid}/dashboard')
    assert response.status_code == 409
    assert preserved.is_file() and not path.exists()
    assert api.get('/api/v3/undo/latest', params={'workspace_id': wid}).status_code == 409
    assert not path.exists()


def test_latest_undo_requires_read_scope(api):
    wid = workspace(api)
    token = api.post('/api/v3/access-tokens', json={'name': 'Write-only', 'workspaceIds': [wid], 'scopes': ['ledger:write']}).json()['token']
    assert api.get('/api/v3/undo/latest', params={'workspace_id': wid}, headers={'Authorization': f'Bearer {token}'}).status_code == 403


def test_old_status_undo_cannot_reactivate_quarantined_workspace(api):
    wid = workspace(api)
    archived = api.patch(f'/api/v3/workspaces/{wid}', json={'status': 'archived'}).json()
    api.delete(f'/api/v3/workspaces/{wid}')
    response = api.post('/api/v3/undo', json={'undoToken': archived['undo']['undoToken']})
    assert response.status_code == 409
    assert api.app.state.registry.get_workspace(wid)['status'] == 'quarantined'
    assert not api.app.state.registry.vaults.path_for(wid).exists()


def test_cookie_mutation_rejects_foreign_origin(api):
    response = api.post('/api/v3/workspaces', json={'displayName': 'Blocked'}, headers={'Origin': 'https://untrusted.example'})
    assert response.status_code == 403
    assert api.get('/api/v3/workspaces').json()['data'] == []


def test_long_decimal_posting_and_reports_remain_exact(api):
    wid = workspace(api)
    base = f'/api/v3/workspaces/{wid}'
    assert api.post(base + '/commodities', json={'code': 'EXACT', 'name': 'Synthetic precision', 'kind': 'currency', 'scale': 18}).status_code == 201
    for identifier, kind in [('cash', 'asset'), ('capital', 'equity')]:
        assert api.post(base + '/accounts', json={'id': identifier, 'code': identifier, 'name': identifier, 'type': kind, 'subtype': 'cash' if identifier == 'cash' else '', 'allowedCommodityCodes': ['EXACT']}).status_code == 201
    amount = '123456789012345678.123456789012345678'
    draft = {'id': 'precise', 'date': '2026-09-30', 'description': 'Synthetic precision', 'balancingCommodityCode': 'EXACT', 'postings': [
        {'id': 'debit', 'accountId': 'cash', 'side': 'debit', 'units': amount, 'commodityCode': 'EXACT'},
        {'id': 'credit', 'accountId': 'capital', 'side': 'credit', 'units': amount, 'commodityCode': 'EXACT'},
    ]}
    assert api.post(base + '/journal-entry-drafts', json=draft).status_code == 201
    assert api.post(base + '/journal-entry-drafts/precise/post').status_code == 200
    statements = api.get(base + '/financial-statements').json()['data']
    assert statements[0]['assets'] == amount and statements[0]['equity'] == amount
    summary = api.get(base + '/dashboard').json()['data']['commoditySummaries'][0]
    assert summary['bookValue'] == amount and summary['marketValue'] == amount
    assert api.get(base + '/cash-flow').json()['data'][0]['amount'] == amount
    assert api.get(base + '/reconciliation').json()['data']['status'] == 'pass'
    assert api.post(base + '/journal-entries/precise/reverse').status_code == 201
    assert api.get(base + '/financial-statements').json()['data'][0]['assets'] == '0'
    assert api.get(base + '/reconciliation').json()['data']['status'] == 'pass'


def test_allocation_rounding_is_exact_half_even():
    from decimal import Decimal, localcontext
    from finance_core.ledger import decimal_mul, quantize_ratio
    with localcontext() as context:
        context.prec = 6
        assert quantize_ratio(Decimal('1'), Decimal('8'), 2) == Decimal('0.12')
        assert quantize_ratio(Decimal('3'), Decimal('8'), 2) == Decimal('0.38')
        cost = Decimal('123456789012345678.123456789012345678')
        assert quantize_ratio(decimal_mul(cost, Decimal('2')), Decimal('2'), 18) == cost


def test_csv_validation_error_does_not_echo_private_input(api):
    wid = workspace(api)
    marker = 'SYNTHETIC_PRIVATE_VALUE'
    csv = 'entryId,date,description,balancingCommodityCode,postingId,accountId,side,units,commodityCode\n'
    csv += f'bad,2026-09-30,Synthetic,USD,p1,cash,debit,{marker},USD\n'
    csv += 'bad,2026-09-30,Synthetic,USD,p2,capital,credit,1,USD\n'
    response = api.post(f'/api/v3/workspaces/{wid}/import/drafts.csv', content=csv, headers={'Content-Type': 'text/csv'})
    assert response.status_code == 422
    assert marker not in response.text


@pytest.mark.parametrize('kind', ['ledger', 'registry'])
def test_commit_failure_rolls_back_transaction(kind):
    import sqlite3
    from finance_core.database import transaction
    connection = sqlite3.connect(':memory:', isolation_level=None)
    connection.execute('CREATE TABLE synthetic(value TEXT)')
    class FailingCommit:
        execute = connection.execute
        rollback = connection.rollback
        def commit(self):
            raise sqlite3.OperationalError('synthetic commit failure')
    if kind == 'registry':
        from threading import RLock
        from types import SimpleNamespace
        from finance_core.registry import Registry
        operation = Registry.transaction(SimpleNamespace(connection=FailingCommit(), lock=RLock()))
    else:
        operation = transaction(FailingCommit())
    try:
        with pytest.raises(sqlite3.OperationalError):
            with operation:
                connection.execute("INSERT INTO synthetic VALUES ('synthetic')")
        assert not connection.in_transaction
        assert connection.execute('SELECT COUNT(*) FROM synthetic').fetchone()[0] == 0
    finally:
        connection.close()


def test_batch_error_does_not_echo_record_identifier(api):
    wid = workspace(api)
    marker = 'SYNTHETIC_PRIVATE_IDENTIFIER'
    response = api.post(f'/api/v3/workspaces/{wid}/batch', json={'accounts': [{'id': marker, 'code': 'synthetic', 'name': 'Synthetic', 'type': 'asset', 'allowedCommodityCodes': ['MISSING']}]})
    assert response.status_code == 422
    assert marker not in response.text


def test_recurring_drafts_wait_until_due_and_use_actual_month_end(api):
    wid = workspace(api)
    base = f'/api/v3/workspaces/{wid}'
    draft = {'id': 'template', 'date': '2028-02-01', 'description': 'Synthetic monthly', 'balancingCommodityCode': 'USD', 'postings': [
        {'id': 'p1', 'accountId': 'cash', 'side': 'debit', 'units': '1', 'commodityCode': 'USD'},
        {'id': 'p2', 'accountId': 'capital', 'side': 'credit', 'units': '1', 'commodityCode': 'USD'},
    ]}
    rule = {'id': 'month-end', 'name': 'Synthetic month end', 'enabled': True, 'frequency': 'monthly', 'dayOfMonth': 31, 'startDate': '2028-02-01', 'template': draft, 'generatedPeriods': []}
    assert api.post(base + '/recurring-entry-rules', json=rule).status_code == 201
    early = api.post(base + '/recurring-entry-rules/generate-due', json={'asOf': '2028-02-28'})
    assert early.json()['generatedDraftIds'] == []
    due = api.post(base + '/recurring-entry-rules/generate-due', json={'asOf': '2028-02-29'})
    assert len(due.json()['generatedDraftIds']) == 1
    stored = api.get(base + '/journal-entry-drafts').json()['data'][0]['draft']
    assert stored['date'] == '2028-02-29'
    assert api.post(base + '/recurring-entry-rules/generate-due', json={'asOf': '2028-02-29'}).json()['generatedDraftIds'] == []


def test_quarantine_waits_for_inflight_ledger_read(api, monkeypatch):
    wid = workspace(api)
    repo = api.app.state.registry.vaults.get(wid).repository
    entered, release, deleting = Event(), Event(), Event()
    original = repo.dashboard
    def blocked():
        entered.set()
        assert release.wait(5)
        return original()
    monkeypatch.setattr(repo, 'dashboard', blocked)
    def quarantine():
        deleting.set()
        return api.delete(f'/api/v3/workspaces/{wid}')
    with ThreadPoolExecutor(max_workers=2) as pool:
        read = pool.submit(api.get, f'/api/v3/workspaces/{wid}/dashboard')
        assert entered.wait(5)
        deletion = pool.submit(quarantine)
        assert deleting.wait(5)
        release.set()
        assert read.result(timeout=5).status_code == 200
        assert deletion.result(timeout=5).status_code == 200


def test_quarantine_registry_failure_restores_files(api, monkeypatch):
    wid = workspace(api)
    store = api.app.state.registry
    path = store.vaults.path_for(wid)
    original = store._save_control_undo
    def fail(*args, **kwargs):
        if args[0] == 'workspace.quarantine':
            raise OSError('synthetic failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(store, '_save_control_undo', fail)
    with pytest.raises(ValueError, match='quarantine'):
        store.quarantine_workspace(wid)
    assert path.exists()
    assert store.get_workspace(wid)['status'] == 'active'
    assert store.vaults.get(wid).connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_restore_preflights_all_files_and_preserves_token(api):
    wid = workspace(api)
    store = api.app.state.registry
    result = api.delete(f'/api/v3/workspaces/{wid}').json()
    path = store.vaults.path_for(wid)
    path.write_bytes(b'synthetic conflict')
    response = api.post('/api/v3/undo', json={'undoToken': result['undo']['undoToken']})
    assert response.status_code == 409
    assert path.read_bytes() == b'synthetic conflict'
    assert store.get_workspace(wid)['status'] == 'quarantined'
    row = store.connection.execute('SELECT consumed_at FROM control_undo WHERE operation_id=?', (result['undo']['operationId'],)).fetchone()
    assert row['consumed_at'] is None


def test_quarantine_partial_move_failure_compensates(api, monkeypatch):
    wid = workspace(api)
    store = api.app.state.registry
    path = store.vaults.path_for(wid)
    original = Path.replace
    def fail_target(source, target):
        if 'quarantine' in Path(target).parts:
            raise OSError('synthetic move failure')
        return original(source, target)
    monkeypatch.setattr(Path, 'replace', fail_target)
    with pytest.raises(ValueError, match='quarantine'):
        store.quarantine_workspace(wid)
    assert path.is_file()
    assert store.get_workspace(wid)['status'] == 'active'


def test_restore_commit_failure_returns_files_to_quarantine(api, monkeypatch):
    from contextlib import contextmanager
    wid = workspace(api)
    store = api.app.state.registry
    result = api.delete(f'/api/v3/workspaces/{wid}').json()
    path = store.vaults.path_for(wid)
    @contextmanager
    def failing_transaction():
        with store.lock:
            store.connection.execute('BEGIN IMMEDIATE')
            try:
                yield
                raise OSError('synthetic commit failure')
            finally:
                store.connection.rollback()
    monkeypatch.setattr(store, 'transaction', failing_transaction)
    with pytest.raises(ValueError, match='restore'):
        store.undo_control(result['undo']['undoToken'])
    assert not path.exists()
    assert store.get_workspace(wid)['status'] == 'quarantined'
    row = store.connection.execute('SELECT consumed_at FROM control_undo WHERE operation_id=?', (result['undo']['operationId'],)).fetchone()
    assert row['consumed_at'] is None


def test_response_undo_is_captured_under_operation_lock(api, monkeypatch):
    wid = workspace(api)
    handle = api.app.state.registry.vaults.get(wid)
    original = handle.repository.latest_undo
    captures = []
    def capture():
        assert handle.lock.locked()
        result = original()
        captures.append(result['undoToken'] if result else None)
        return result
    monkeypatch.setattr(handle.repository, 'latest_undo', capture)
    def create(code):
        return api.post(f'/api/v3/workspaces/{wid}/commodities', json={'code': code, 'name': code, 'kind': 'currency', 'scale': 2})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(create, ['USD', 'EUR']))
    tokens = [result.json()['undo']['undoToken'] for result in responses]
    assert len(set(tokens)) == 2
    assert set(tokens) == set(captures)


def test_file_plan_preflight_and_partial_compensation(tmp_path, monkeypatch):
    from finance_core.registry import Registry
    store = Registry(tmp_path)
    source_a, source_b = tmp_path / 'synthetic-a', tmp_path / 'synthetic-b'
    target_a, target_b = tmp_path / 'moved-a', tmp_path / 'moved-b'
    source_a.write_bytes(b'a'); source_b.write_bytes(b'b')
    original = Path.replace
    def fail_second(source, target):
        if source == source_b:
            raise OSError('synthetic second move failure')
        return original(source, target)
    monkeypatch.setattr(Path, 'replace', fail_second)
    try:
        with pytest.raises(OSError):
            with store.move_files([{'source': str(source_a), 'target': str(target_a)}, {'source': str(source_b), 'target': str(target_b)}]):
                pass
        assert source_a.read_bytes() == b'a' and source_b.read_bytes() == b'b'
        assert not target_a.exists() and not target_b.exists()
    finally:
        store.close()
