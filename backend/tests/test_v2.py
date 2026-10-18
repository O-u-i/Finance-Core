from pathlib import Path

from fastapi.testclient import TestClient

from finance_core.main import create_app


class ScopedClient:
    def __init__(self, data_root: Path):
        self.api = TestClient(create_app(data_root=data_root, admin_token="test-admin"))
        self.prefix = ""

    def __enter__(self):
        self.api.__enter__()
        assert self.api.post("/api/v3/session", json={"adminToken": "test-admin"}).status_code == 200
        response = self.api.post("/api/v3/workspaces", json={"displayName": "Test", "kind": "sandbox"})
        assert response.status_code == 201, response.text
        self.prefix = f"/api/v3/workspaces/{response.json()['data']['id']}"
        return self

    def __exit__(self, *args):
        return self.api.__exit__(*args)

    def _path(self, path: str) -> str:
        return self.prefix + path[len("/api/v2"):] if path.startswith("/api/v2") else path

    def get(self, path: str, **kwargs):
        return self.api.get(self._path(path), **kwargs)

    def post(self, path: str, **kwargs):
        return self.api.post(self._path(path), **kwargs)

    def put(self, path: str, **kwargs):
        return self.api.put(self._path(path), **kwargs)

    def patch(self, path: str, **kwargs):
        return self.api.patch(self._path(path), **kwargs)

    def delete(self, path: str, **kwargs):
        return self.api.delete(self._path(path), **kwargs)


def client(tmp_path: Path) -> ScopedClient:
    return ScopedClient(tmp_path / "v3-data")


COMMODITIES = [
    {"code": "CNY", "kind": "currency", "scale": 2, "name": "Chinese Yuan", "status": "active"},
    {"code": "USD", "kind": "currency", "scale": 2, "name": "US Dollar", "status": "active"},
    {"code": "DEMO", "kind": "security", "scale": 4, "name": "Synthetic Fund", "status": "active"},
]

ACCOUNTS = [
    {"id": "cash-cny", "code": "1001-CNY", "name": "CNY Cash", "type": "asset", "subtype": "cash", "allowedCommodityCodes": ["CNY"], "status": "active"},
    {"id": "cash-usd", "code": "1001-USD", "name": "USD Cash", "type": "asset", "subtype": "cash", "allowedCommodityCodes": ["USD"], "status": "active"},
    {"id": "investment", "code": "1101", "name": "Investment", "type": "asset", "subtype": "investment", "allowedCommodityCodes": ["DEMO"], "status": "active"},
    {"id": "capital", "code": "3001", "name": "Capital", "type": "equity", "subtype": "", "allowedCommodityCodes": ["CNY"], "status": "active"},
    {"id": "gain", "code": "4001", "name": "Gain", "type": "income", "subtype": "realized-gain", "allowedCommodityCodes": ["CNY"], "status": "active"},
]


def seed(api: TestClient) -> None:
    for item in COMMODITIES:
        assert api.post("/api/v2/commodities", json=item).status_code == 201
    for item in ACCOUNTS:
        assert api.post("/api/v2/accounts", json=item).status_code == 201


def opening_draft(entry_id: str = "opening") -> dict:
    return {
        "id": entry_id,
        "date": "2026-08-17",
        "description": "Synthetic opening",
        "balancingCommodityCode": "CNY",
        "postings": [
            {"id": f"{entry_id}-1", "accountId": "cash-cny", "side": "debit", "units": "1000.00", "commodityCode": "CNY", "cashFlowCategory": "financing"},
            {"id": f"{entry_id}-2", "accountId": "capital", "side": "credit", "units": "1000", "commodityCode": "CNY", "cashFlowCategory": "financing"},
        ],
    }


def create_and_post(api: TestClient, payload: dict) -> dict:
    assert api.post("/api/v2/journal-entry-drafts", json=payload).status_code == 201
    validation = api.post(f"/api/v2/journal-entry-drafts/{payload['id']}/validate")
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid"] is True, validation.json()
    posted = api.post(f"/api/v2/journal-entry-drafts/{payload['id']}/post")
    assert posted.status_code == 200, posted.text
    return posted.json()["entry"]


def test_health_and_decimal_aggregate_lifecycle(tmp_path: Path):
    with client(tmp_path) as api:
        health = api.get("/api/v2/health").json()
        assert health["apiVersion"] == "3.10.0"
        assert health["ledgerSchemaVersion"] == 3
        seed(api)
        payload = opening_draft()
        assert api.post("/api/v2/journal-entry-drafts", json=payload).status_code == 201
        assert api.get("/api/v2/dashboard").json()["data"]["entryCount"] == 0
        preview = api.post("/api/v2/journal-entry-drafts/opening/validate").json()
        assert preview["valid"] is True
        assert preview["preview"]["debitTotal"] == "1000"
        assert preview["preview"]["difference"] == "0"
        assert api.post("/api/v2/journal-entry-drafts/opening/post").status_code == 200
        assert api.put("/api/v2/journal-entry-drafts/opening", json=payload).status_code == 404
        assert api.patch("/api/v2/journal-entries/opening", json={"description": "changed"}).status_code == 405
        assert api.get("/api/v2/dashboard").json()["data"]["commoditySummaries"][0]["cash"] == "1000"
        reversed_entry = api.post("/api/v2/journal-entries/opening/reverse")
        assert reversed_entry.status_code == 201
        cash_flow = api.get("/api/v2/t-accounts").json()["data"]
        assert next(item for item in cash_flow if item["accountId"] == "cash-cny")["balance"] == "0"


def test_unbalanced_and_scale_errors_are_structured(tmp_path: Path):
    with client(tmp_path) as api:
        seed(api)
        payload = opening_draft("invalid")
        payload["postings"][0]["units"] = "1000.001"
        payload["postings"][1]["units"] = "999"
        assert api.post("/api/v2/journal-entry-drafts", json=payload).status_code == 201
        result = api.post("/api/v2/journal-entry-drafts/invalid/validate").json()
        codes = {item["code"] for item in result["issues"]}
        assert "UNITS_EXCEED_SCALE" in codes
        assert "ENTRY_NOT_BALANCED" in codes
        assert api.post("/api/v2/journal-entry-drafts/invalid/post").status_code == 422
        assert api.get("/api/v2/journal-entries").json()["data"] == []


def test_fx_is_valued_in_balancing_commodity(tmp_path: Path):
    with client(tmp_path) as api:
        seed(api)
        payload = {
            "id": "fx", "date": "2026-08-17", "description": "Synthetic FX", "balancingCommodityCode": "CNY",
            "postings": [
                {"id": "fx-1", "accountId": "cash-usd", "side": "debit", "units": "10", "commodityCode": "USD", "valuationRate": "7.00", "rateType": "exchange", "cashFlowCategory": "transfer"},
                {"id": "fx-2", "accountId": "cash-cny", "side": "credit", "units": "70", "commodityCode": "CNY", "cashFlowCategory": "transfer"},
            ],
        }
        entry = create_and_post(api, payload)
        assert entry["postings"][0]["valuationAmount"] == "70"
        assert api.get("/api/v2/reconciliation").json()["data"]["status"] == "pass"


def test_lot_acquisition_disposal_price_and_reversal(tmp_path: Path):
    with client(tmp_path) as api:
        seed(api)
        create_and_post(api, opening_draft())
        purchase = {
            "id": "buy", "date": "2026-08-17", "description": "Synthetic purchase", "balancingCommodityCode": "CNY",
            "postings": [
                {"id": "buy-1", "accountId": "investment", "side": "debit", "units": "2", "commodityCode": "DEMO", "valuationRate": "100", "rateType": "cost", "lotAction": "acquire", "lotId": "lot-1", "cashFlowCategory": "investment"},
                {"id": "buy-2", "accountId": "cash-cny", "side": "credit", "units": "200", "commodityCode": "CNY", "cashFlowCategory": "investment"},
            ],
        }
        create_and_post(api, purchase)
        quote = {"id": "quote-1", "commodityCode": "DEMO", "quoteCommodityCode": "CNY", "price": "110", "asOf": "2026-08-17T12:00:00Z", "source": "synthetic"}
        assert api.post("/api/v2/price-quotes", json=quote).status_code == 201
        holding = api.get("/api/v2/holdings").json()["data"][0]
        assert holding["remainingUnits"] == "2"
        assert holding["marketValue"] == "220"
        assert holding["unrealizedPnL"] == "20"

        sale = {
            "id": "sell", "date": "2026-08-17", "description": "Synthetic sale", "balancingCommodityCode": "CNY",
            "postings": [
                {"id": "sell-1", "accountId": "cash-cny", "side": "debit", "units": "110", "commodityCode": "CNY", "cashFlowCategory": "investment"},
                {"id": "sell-2", "accountId": "investment", "side": "credit", "units": "1", "commodityCode": "DEMO", "valuationRate": "100", "rateType": "cost", "lotAction": "dispose", "lotAllocations": [{"lotId": "lot-1", "units": "1"}], "cashFlowCategory": "investment"},
                {"id": "sell-3", "accountId": "gain", "side": "credit", "units": "10", "commodityCode": "CNY", "cashFlowCategory": "income"},
            ],
        }
        create_and_post(api, sale)
        holding = api.get("/api/v2/holdings").json()["data"][0]
        assert holding["remainingUnits"] == "1"
        assert holding["remainingCost"] == "100"
        assert api.get("/api/v2/dashboard").json()["data"]["commoditySummaries"][0]["realizedPnL"] == "10"
        assert api.post("/api/v2/journal-entries/sell/reverse").status_code == 201
        holding = api.get("/api/v2/holdings").json()["data"][0]
        assert holding["remainingUnits"] == "2"
        assert holding["remainingCost"] == "200"
        assert api.get("/api/v2/reconciliation").json()["data"]["status"] == "pass"


def test_import_and_recurring_create_drafts_only(tmp_path: Path):
    with client(tmp_path) as api:
        seed(api)
        draft = opening_draft("imported")
        imported = api.post("/api/v2/import/drafts", json={"drafts": [draft]})
        assert imported.status_code == 201
        assert api.get("/api/v2/journal-entries").json()["data"] == []
        template = opening_draft("template")
        rule = {
            "id": "monthly", "name": "Synthetic monthly", "dayOfMonth": 15, "startDate": "2026-01-01",
            "template": template, "generatedPeriods": [],
        }
        assert api.post("/api/v2/recurring-entry-rules", json=rule).status_code == 201
        due = api.post("/api/v2/recurring-entry-rules/generate-due", json={"asOf": "2026-08-17"})
        assert due.status_code == 200
        assert due.json()["generatedDraftIds"] == ["rec-monthly-2026-08"]
        assert api.get("/api/v2/dashboard").json()["data"]["entryCount"] == 0
        assert api.get("/api/v2/dashboard").json()["data"]["draftCount"] == 2


def test_csv_import_creates_validated_draft_only(tmp_path: Path):
    with client(tmp_path) as api:
        seed(api)
        csv_body = (
            "entryId,date,description,payee,source,reference,tags,balancingCommodityCode,postingId,accountId,side,units,commodityCode,valuationRate,rateType,cashFlowCategory,memo,lotAction,lotId,lotAllocationsJson\n"
            "csv-entry,2026-08-17,Synthetic CSV,,csv,,,CNY,csv-p1,cash-cny,debit,10,CNY,,,income,,,,\n"
            "csv-entry,2026-08-17,Synthetic CSV,,csv,,,CNY,csv-p2,capital,credit,10,CNY,,,income,,,,\n"
        )
        response = api.post("/api/v2/import/drafts.csv", content=csv_body, headers={"Content-Type": "text/csv"})
        assert response.status_code == 201, response.text
        assert response.json()["imported"] == 1
        assert api.get("/api/v2/journal-entries").json()["data"] == []


def test_living_world_uses_decimal_strings(tmp_path: Path):
    with client(tmp_path) as api:
        seed(api)
        living = {
            "id": "living", "name": "Synthetic Daily", "commodityCode": "CNY",
            "balance": "100.10", "note": "Synthetic", "updatedAt": "2026-08-17T00:00:00Z",
        }
        assert api.post("/api/v2/living-accounts", json=living).status_code == 201
        recorded = api.post("/api/v2/living-accounts/living/record-balance", json={"balance": "120.20"})
        assert recorded.status_code == 200
        assert recorded.json()["snapshot"]["balance"] == "120.2"
        plan = {
            "id": "plan", "kind": "expense", "name": "Synthetic Plan", "amount": "50.05",
            "commodityCode": "CNY", "category": "living", "recurringMonthly": True,
            "dayOfMonth": 1, "startDate": "2026-08-17", "note": "",
        }
        assert api.post("/api/v2/monthly-plans", json=plan).status_code == 201
        world = api.get("/api/v2/world").json()["data"]
        assert world["commoditySummaries"][0]["livingBalance"] == "120.2"
        assert world["commoditySummaries"][0]["expectedExpense"] == "50.05"


def test_hashed_backup_restores_only_into_empty_v2_ledger(tmp_path: Path):
    with client(tmp_path / "source") as source:
        seed(source)
        assert source.post("/api/v2/journal-entry-drafts", json=opening_draft()).status_code == 201
        backup = source.get("/api/v2/backup").json()["data"]
        assert len(backup["sha256"]) == 64
    with client(tmp_path / "target") as target:
        restored = target.post("/api/v2/backup/restore", json=backup)
        assert restored.status_code == 201, restored.text
        assert len(target.get("/api/v2/commodities").json()["data"]) == 3
        assert len(target.get("/api/v2/journal-entry-drafts").json()["data"]) == 1
        assert target.post("/api/v2/backup/restore", json=backup).status_code == 422
    tampered = {**backup, "sha256": "0" * 64}
    with client(tmp_path / "tampered") as target:
        assert target.post("/api/v2/backup/restore", json=tampered).status_code == 422


def test_v2_single_use_undo_and_post_invalidation(tmp_path: Path):
    with client(tmp_path) as api:
        commodity = COMMODITIES[0]
        assert api.post("/api/v2/commodities", json=commodity).status_code == 201
        token = api.get("/api/v2/undo/latest").json()["data"]["undoToken"]
        assert api.post("/api/v2/undo", json={"undoToken": token}).status_code == 200
        assert api.get("/api/v2/commodities").json()["data"] == []
        expired = api.post("/api/v2/undo", json={"undoToken": token})
        assert expired.status_code == 410
        assert expired.json()["error"]["code"] == "UNDO_EXPIRED"

        seed(api)
        assert api.post("/api/v2/journal-entry-drafts", json=opening_draft()).status_code == 201
        assert api.get("/api/v2/undo/latest").json()["data"] is not None
        assert api.post("/api/v2/journal-entry-drafts/opening/post").status_code == 200
        assert api.get("/api/v2/undo/latest").json()["data"] is None


def test_undo_restores_living_account_and_snapshot_together(tmp_path: Path):
    with client(tmp_path) as api:
        seed(api)
        living = {
            "id": "living", "name": "Synthetic Daily", "commodityCode": "CNY",
            "balance": "100", "note": "Synthetic", "updatedAt": "2026-08-17T00:00:00Z",
        }
        assert api.post("/api/v2/living-accounts", json=living).status_code == 201
        assert api.post("/api/v2/living-accounts/living/record-balance", json={"balance": "150"}).status_code == 200
        token = api.get("/api/v2/undo/latest").json()["data"]["undoToken"]
        assert api.post("/api/v2/undo", json={"undoToken": token}).status_code == 200
        assert api.get("/api/v2/living-accounts").json()["data"][0]["balance"] == "100"
        assert api.get("/api/v2/living-snapshots").json()["data"] == []


def test_v2_mutable_batch_is_atomic_and_undoable(tmp_path: Path):
    with client(tmp_path) as api:
        commodity = COMMODITIES[0]
        account = ACCOUNTS[0]
        invalid = api.post("/api/v2/batch", json={
            "commodities": [commodity],
            "accounts": [account, {**account, "id": "cash-duplicate"}],
        })
        assert invalid.status_code == 409
        assert api.get("/api/v2/commodities").json()["data"] == []
        valid = api.post("/api/v2/batch", json={"commodities": [commodity], "accounts": [account]})
        assert valid.status_code == 200
        token = valid.json()["undo"]["undoToken"]
        assert api.get("/api/v2/accounts").json()["data"][0]["id"] == "cash-cny"
        assert api.post("/api/v2/undo", json={"undoToken": token}).status_code == 200
        assert api.get("/api/v2/commodities").json()["data"] == []


def test_undo_master_update_preserves_posted_foreign_keys(tmp_path: Path):
    with client(tmp_path) as api:
        seed(api)
        create_and_post(api, opening_draft())
        account = next(item for item in api.get("/api/v2/accounts").json()["data"] if item["id"] == "cash-cny")
        assert api.put("/api/v2/accounts/cash-cny", json={**account, "status": "inactive"}).status_code == 200
        token = api.get("/api/v2/undo/latest").json()["data"]["undoToken"]
        assert api.post("/api/v2/undo", json={"undoToken": token}).status_code == 200
        restored = next(item for item in api.get("/api/v2/accounts").json()["data"] if item["id"] == "cash-cny")
        assert restored["status"] == "active"
        assert api.get("/api/v2/reconciliation").json()["data"]["status"] == "pass"


def test_failed_lot_child_write_rolls_back_entire_entry(tmp_path: Path):
    with client(tmp_path) as api:
        seed(api)
        create_and_post(api, opening_draft())
        create_and_post(api, {
            "id": "buy", "date": "2026-08-17", "description": "Synthetic purchase", "balancingCommodityCode": "CNY",
            "postings": [
                {"id": "buy-1", "accountId": "investment", "side": "debit", "units": "2", "commodityCode": "DEMO", "valuationRate": "100", "rateType": "cost", "lotAction": "acquire", "lotId": "lot-rollback", "cashFlowCategory": "investment"},
                {"id": "buy-2", "accountId": "cash-cny", "side": "credit", "units": "200", "commodityCode": "CNY", "cashFlowCategory": "investment"},
            ],
        })
        invalid_sale = {
            "id": "bad-sale", "date": "2026-08-17", "description": "Wrong lot cost", "balancingCommodityCode": "CNY",
            "postings": [
                {"id": "bad-sale-1", "accountId": "cash-cny", "side": "debit", "units": "90", "commodityCode": "CNY", "cashFlowCategory": "investment"},
                {"id": "bad-sale-2", "accountId": "investment", "side": "credit", "units": "1", "commodityCode": "DEMO", "valuationRate": "90", "rateType": "cost", "lotAction": "dispose", "lotAllocations": [{"lotId": "lot-rollback", "units": "1"}], "cashFlowCategory": "investment"},
            ],
        }
        assert api.post("/api/v2/journal-entry-drafts", json=invalid_sale).status_code == 201
        failed = api.post("/api/v2/journal-entry-drafts/bad-sale/post")
        assert failed.status_code == 422
        assert api.get("/api/v2/journal-entries/bad-sale").status_code == 404
        lot = next(item for item in api.get("/api/v2/holdings").json()["data"] if item["lotId"] == "lot-rollback")
        assert lot["remainingUnits"] == "2"
        assert lot["remainingCost"] == "200"


def test_openapi_contract_keeps_ledger_writes_bounded(tmp_path: Path):
    with client(tmp_path) as api:
        spec = api.get("/openapi.json").json()
        posting = spec["components"]["schemas"]["PostingDraft"]["properties"]
        assert posting["units"]["type"] == "string"
        assert posting["valuationRate"]["anyOf"][0]["type"] == "string"
        prefix = "/api/v3/workspaces/{workspace_id}"
        assert set(spec["paths"][f"{prefix}/holdings"]) == {"get"}
        assert set(spec["paths"][f"{prefix}/journal-entries/{{entry_id}}"]) == {"get"}
        assert "post" in spec["paths"][f"{prefix}/journal-entry-drafts/{{draft_id}}/post"]
