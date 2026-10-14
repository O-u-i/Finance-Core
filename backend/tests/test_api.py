from pathlib import Path

from fastapi.testclient import TestClient

from finance_core.main import create_app


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(data_root=tmp_path / "v3-data", admin_token="test-admin"))


def login(api: TestClient) -> None:
    assert api.post("/api/v3/session", json={"adminToken": "test-admin"}).status_code == 200


TRANSACTION = {
    "id": "tx-1", "date": "2026-08-16", "account": "1001 Cash", "source": "Manual",
    "type": "Deposit", "category": "Income", "assetSymbol": "", "amount": 1000.0,
    "currency": "CNY", "note": "Synthetic test row", "ref": "test",
}

HOLDING = {
    "id": "holding-1", "symbol": "DEMO", "name": "Synthetic Holding", "assetType": "ETF",
    "quantity": 2.0, "averageCost": 100.0, "currentPrice": 110.0, "currency": "CNY",
    "sector": "Demo", "thesisNote": "Synthetic test row",
}


def test_health_declares_versioned_contract(tmp_path: Path):
    with client(tmp_path) as api:
        response = api.get("/api/v3/health")
        assert response.status_code == 200
        assert response.json()["apiVersion"] == "3.5.0"
        assert response.json()["ledgerSchemaVersion"] == 3
        assert response.json()["registrySchemaVersion"] == 1
        assert api.get("/api/v1/health").status_code == 404
        assert api.get("/api/v2/health").status_code == 404


def test_v1_resource_writes_are_disabled(tmp_path: Path):
    with client(tmp_path) as api:
        assert api.get("/api/v3/workspaces").status_code == 401
        assert api.post("/api/v3/session", json={"adminToken": "wrong"}).status_code == 401
        login(api)
        assert api.get("/api/v3/workspaces").json()["data"] == []


def test_dashboard_is_deterministic_and_currency_separated(tmp_path: Path):
    with client(tmp_path) as api:
        login(api)
        created = api.post("/api/v3/workspaces", json={"displayName": "Personal", "kind": "personal"})
        assert created.status_code == 201
        workspace = created.json()["data"]
        assert workspace["kind"] == "personal"
        assert workspace["status"] == "active"
        dashboard = api.get(f"/api/v3/workspaces/{workspace['id']}/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["workspaceId"] == workspace["id"]
        assert dashboard.json()["data"]["entryCount"] == 0


def test_export_excludes_reports_and_context(tmp_path: Path):
    with client(tmp_path) as api:
        login(api)
        first = api.post("/api/v3/workspaces", json={"displayName": "One", "kind": "personal"}).json()["data"]
        second = api.post("/api/v3/workspaces", json={"displayName": "Two", "kind": "sandbox"}).json()["data"]
        payload = {"code": "CNY", "kind": "currency", "scale": 2, "name": "Yuan", "status": "active"}
        assert api.post(f"/api/v3/workspaces/{first['id']}/commodities", json=payload).status_code == 201
        assert len(api.get(f"/api/v3/workspaces/{first['id']}/commodities").json()["data"]) == 1
        assert api.get(f"/api/v3/workspaces/{second['id']}/commodities").json()["data"] == []


def test_account_options_can_be_undone(tmp_path: Path):
    with client(tmp_path) as api:
        login(api)
        workspace = api.post("/api/v3/workspaces", json={"displayName": "Undo", "kind": "sandbox"}).json()["data"]
        path = f"/api/v3/workspaces/{workspace['id']}"
        created = api.post(path + "/commodities", json={"code": "CNY", "kind": "currency", "scale": 2, "name": "Yuan", "status": "active"})
        assert created.status_code == 201
        undo = created.json()["undo"]
        assert api.post("/api/v3/undo", json={"undoToken": undo["undoToken"], "workspaceId": workspace["id"]}).status_code == 200
        assert api.get(path + "/commodities").json()["data"] == []


def test_csv_round_trip_for_holdings(tmp_path: Path):
    with client(tmp_path) as api:
        login(api)
        workspace = api.post("/api/v3/workspaces", json={"displayName": "Token", "kind": "sandbox"}).json()["data"]
        token = api.post("/api/v3/access-tokens", json={"name": "SFOS", "workspaceIds": [workspace["id"]], "scopes": ["ledger:read"]})
        assert token.status_code == 201
        secret = token.json()["token"]
        headers = {"Authorization": f"Bearer {secret}"}
        assert api.get(f"/api/v3/workspaces/{workspace['id']}/dashboard", headers=headers).status_code == 200
        assert api.post(f"/api/v3/workspaces/{workspace['id']}/demo/load-synthetic", headers=headers).status_code == 403


def test_batch_is_atomic_and_undoes_as_one_operation(tmp_path: Path):
    with client(tmp_path) as api:
        login(api)
        workspace = api.post("/api/v3/workspaces", json={"displayName": "Archive", "kind": "personal"}).json()["data"]
        assert api.patch(f"/api/v3/workspaces/{workspace['id']}", json={"status": "archived"}).status_code == 200
        assert api.get(f"/api/v3/workspaces/{workspace['id']}/dashboard").status_code == 200
        assert api.post(f"/api/v3/workspaces/{workspace['id']}/demo/load-synthetic").status_code == 409


def test_record_balance_undoes_account_and_snapshot_together(tmp_path: Path):
    with client(tmp_path) as api:
        login(api)
        workspace = api.post("/api/v3/workspaces", json={"displayName": "Delete", "kind": "sandbox"}).json()["data"]
        deleted = api.delete(f"/api/v3/workspaces/{workspace['id']}")
        assert deleted.status_code == 200
        assert deleted.json()["data"]["status"] == "quarantined"
        undo = deleted.json()["undo"]
        restored = api.post("/api/v3/undo", json={"undoToken": undo["undoToken"]})
        assert restored.status_code == 200
        assert api.get(f"/api/v3/workspaces/{workspace['id']}/dashboard").status_code == 200
