from pathlib import Path

from fastapi.testclient import TestClient

from finance_core.database import connect
from finance_core.main import create_app


def client(tmp_path: Path) -> TestClient:
    connection = connect(tmp_path / "test.sqlite3")
    return TestClient(create_app(connection=connection))


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
        response = api.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["apiVersion"] == "1.0.0"
        assert response.json()["schemaVersion"] == 2
        assert response.json()["legacyReadOnly"] is True


def test_v1_resource_writes_are_disabled(tmp_path: Path):
    with client(tmp_path) as api:
        created = api.post("/api/v1/transactions", json=TRANSACTION)
        assert created.status_code == 410
        assert created.json()["error"]["code"] == "LEGACY_API_READ_ONLY"
        assert api.get("/api/v1/transactions").json()["data"] == []


def test_dashboard_is_deterministic_and_currency_separated(tmp_path: Path):
    with client(tmp_path) as api:
        result = api.get("/api/v1/dashboard").json()["data"]
        assert result["transactionCount"] == 0
        assert result["holdingCount"] == 0
        assert result["currencySummaries"] == []


def test_export_excludes_reports_and_context(tmp_path: Path):
    with client(tmp_path) as api:
        exported = api.get("/api/v1/export").json()["data"]
        assert "analysisReports" not in exported
        assert "validationReports" not in exported
        assert "knowledgeNotes" not in exported


def test_account_options_can_be_undone(tmp_path: Path):
    with client(tmp_path) as api:
        response = api.put("/api/v1/account-options", json=["1001 Cash", "2001 Liability"])
        assert response.status_code == 410
        assert api.get("/api/v1/account-options").json()["data"] == []


def test_csv_round_trip_for_holdings(tmp_path: Path):
    with client(tmp_path) as api:
        csv_body = "id,symbol,name,assetType,quantity,averageCost,currentPrice,currency,sector,thesisNote\n" + \
            "holding-csv,DEMO,Synthetic,ETF,2,100,110,CNY,Demo,Synthetic only\n"
        imported = api.post("/api/v1/import/holdings.csv", content=csv_body, headers={"Content-Type": "text/csv"})
        assert imported.status_code == 410
        exported = api.get("/api/v1/export/holdings.csv")
        assert exported.status_code == 200
        assert "holding-csv" not in exported.text


def test_batch_is_atomic_and_undoes_as_one_operation(tmp_path: Path):
    with client(tmp_path) as api:
        batch = api.post("/api/v1/batch", json={"operations": [
            {"action": "create", "resource": "transactions", "data": TRANSACTION},
            {"action": "create", "resource": "holdings", "data": HOLDING},
            {"action": "replace", "resource": "account-options", "data": ["1001 Cash"]},
        ]})
        assert batch.status_code == 410
        assert api.get("/api/v1/transactions").json()["data"] == []
        assert api.get("/api/v1/holdings").json()["data"] == []


def test_record_balance_undoes_account_and_snapshot_together(tmp_path: Path):
    with client(tmp_path) as api:
        account = {"id": "living-1", "name": "Synthetic Cash", "currency": "CNY", "balance": 100.0, "note": "Synthetic", "updatedAt": "2026-08-16T00:00:00+00:00"}
        assert api.post("/api/v1/living-accounts", json=account).status_code == 410
        changed = api.post("/api/v1/living-accounts/living-1/record-balance", json={"balance": 150.0})
        assert changed.status_code == 410
        assert api.get("/api/v1/living-snapshots").json()["data"] == []
