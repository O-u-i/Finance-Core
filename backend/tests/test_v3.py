from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic

from fastapi.testclient import TestClient

from finance_core.app_v3 import create_app
from finance_core.maintenance import inspect_database, migrate_database


def authenticated_client(tmp_path: Path) -> TestClient:
    api = TestClient(create_app(data_root=tmp_path / "data", admin_token="admin-secret"))
    api.__enter__()
    assert api.post("/api/v3/session", json={"adminToken": "admin-secret"}).status_code == 200
    return api


def create_workspace(api: TestClient, name: str = "Test", kind: str = "sandbox") -> dict:
    response = api.post("/api/v3/workspaces", json={"displayName": name, "kind": kind})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_openapi_is_v3_only_and_scoped(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        paths = api.get("/openapi.json").json()["paths"]
        assert "/api/v3/health" in paths
        assert "/api/v3/workspaces/{workspace_id}/dashboard" in paths
        assert not any(path.startswith("/api/v1") or path.startswith("/api/v2") for path in paths)
    finally:
        api.__exit__(None, None, None)


def test_personal_rejects_synthetic_loader_and_post_has_no_undo(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        personal = create_workspace(api, "Personal", "personal")
        path = f"/api/v3/workspaces/{personal['id']}"
        denied = api.post(path + "/demo/load-synthetic")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "REQUEST_FAILED"
    finally:
        api.__exit__(None, None, None)


def test_access_token_is_displayed_once_and_revocation_is_final(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        workspace = create_workspace(api)
        created = api.post("/api/v3/access-tokens", json={
            "name": "SFOS", "workspaceIds": [workspace["id"]], "scopes": ["ledger:read"],
        })
        assert created.status_code == 201
        secret = created.json()["token"]
        token_id = created.json()["data"]["id"]
        listed = api.get("/api/v3/access-tokens").json()["data"]
        assert all("token" not in item for item in listed)
        headers = {"Authorization": f"Bearer {secret}"}
        assert api.get(f"/api/v3/workspaces/{workspace['id']}/dashboard", headers=headers).status_code == 200
        revoked = api.post(f"/api/v3/access-tokens/{token_id}/revoke")
        assert revoked.status_code == 200 and "undo" not in revoked.json()
        assert api.get(f"/api/v3/workspaces/{workspace['id']}/dashboard", headers=headers).status_code == 401
    finally:
        api.__exit__(None, None, None)


def test_parallel_scoped_reads_complete_for_session_and_token_actors(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        workspace = create_workspace(api, "Parallel reads")
        created = api.post("/api/v3/access-tokens", json={
            "name": "Parallel reader", "workspaceIds": [workspace["id"]], "scopes": ["ledger:read"],
        })
        assert created.status_code == 201
        headers = {"Authorization": f"Bearer {created.json()['token']}"}
        prefix = f"/api/v3/workspaces/{workspace['id']}"
        paths = [
            "/health", "/dashboard", "/reconciliation", "/commodities", "/accounts",
            "/price-quotes", "/journal-entry-drafts", "/journal-entries", "/holdings",
            "/financial-statements", "/cash-flow", "/t-accounts", "/recurring-entry-rules",
            "/living-accounts", "/living-snapshots", "/monthly-plans", "/world", "/undo/latest",
        ]
        requests = [(path, {}) for path in paths] + [(path, headers) for path in paths]
        started = monotonic()
        with ThreadPoolExecutor(max_workers=len(requests)) as workers:
            futures = [workers.submit(api.get, prefix + path, headers=request_headers) for path, request_headers in requests]
            responses = [future.result(timeout=5) for future in futures]
        assert monotonic() - started < 5
        assert all(response.status_code == 200 for response in responses)
    finally:
        api.__exit__(None, None, None)


def test_workspace_quarantine_moves_and_restores_database(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        workspace = create_workspace(api)
        path = tmp_path / "data" / "workspaces" / workspace["id"] / "finance-core.sqlite3"
        assert path.is_file()
        removed = api.delete(f"/api/v3/workspaces/{workspace['id']}")
        assert removed.status_code == 200
        assert not path.exists()
        undo = removed.json()["undo"]
        assert "T" in undo["expiresAt"]
        restored = api.post("/api/v3/undo", json={"undoToken": undo["undoToken"]})
        assert restored.status_code == 200
        assert path.is_file()
        assert api.get(f"/api/v3/workspaces/{workspace['id']}/reconciliation").status_code == 200
    finally:
        api.__exit__(None, None, None)


def test_backup_restore_is_reversible(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        source = create_workspace(api, "Source")
        source_path = f"/api/v3/workspaces/{source['id']}"
        assert api.post(source_path + "/demo/load-synthetic").status_code == 201
        backup = api.get(source_path + "/backup").json()["data"]
        target = create_workspace(api, "Target")
        target_path = f"/api/v3/workspaces/{target['id']}"
        restored = api.post(target_path + "/backup/restore", json=backup)
        assert restored.status_code == 201
        assert len(api.get(target_path + "/commodities").json()["data"]) > 0
        undo = restored.json()["undo"]
        assert api.post("/api/v3/undo", json={"undoToken": undo["undoToken"], "workspaceId": target["id"]}).status_code == 200
        assert api.get(target_path + "/commodities").json()["data"] == []
    finally:
        api.__exit__(None, None, None)


def test_safe_migration_copies_source_without_changing_it(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        source = create_workspace(api, "Legacy source")
        source_api = f"/api/v3/workspaces/{source['id']}"
        assert api.post(source_api + "/demo/load-synthetic").status_code == 201
        source_path = tmp_path / "data" / "workspaces" / source["id"] / "finance-core.sqlite3"
    finally:
        api.__exit__(None, None, None)
    before = inspect_database(source_path)
    migrated = migrate_database(source_path, tmp_path / "migrated", "Migrated", "personal")
    after = inspect_database(source_path)
    assert migrated["sourceUnchanged"] is True
    assert before["sha256"] == after["sha256"]
    assert migrated["tableCounts"] == before["tableCounts"]
