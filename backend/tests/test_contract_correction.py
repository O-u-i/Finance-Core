from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from finance_core import __version__
from finance_core.app_v3 import create_app


def resolve(schema: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        node: Any = document
        for part in schema["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        schema = node
    return schema


def assert_matches_schema(value: Any, schema: dict[str, Any], document: dict[str, Any], path: str = "$") -> None:
    schema = resolve(schema, document)
    if "anyOf" in schema:
        failures = []
        for option in schema["anyOf"]:
            try:
                assert_matches_schema(value, option, document, path)
                return
            except AssertionError as error:
                failures.append(str(error))
        raise AssertionError(f"{path} matched no anyOf option: {failures}")
    if "const" in schema:
        assert value == schema["const"], f"{path} must equal {schema['const']!r}"
    if "enum" in schema:
        assert value in schema["enum"], f"{path} must be one of {schema['enum']!r}"
    expected_type = schema.get("type")
    if expected_type == "object":
        assert isinstance(value, dict), f"{path} must be an object"
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        assert not missing, f"{path} is missing required properties {sorted(missing)}"
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            assert not extra, f"{path} has undeclared properties {sorted(extra)}"
        for key, item in value.items():
            if key in properties:
                assert_matches_schema(item, properties[key], document, f"{path}.{key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                assert_matches_schema(item, schema["additionalProperties"], document, f"{path}.{key}")
    elif expected_type == "array":
        assert isinstance(value, list), f"{path} must be an array"
        assert len(value) >= schema.get("minItems", 0), f"{path} has too few items"
        if "maxItems" in schema:
            assert len(value) <= schema["maxItems"], f"{path} has too many items"
        for index, item in enumerate(value):
            assert_matches_schema(item, schema.get("items", {}), document, f"{path}[{index}]")
    elif expected_type == "string":
        assert isinstance(value, str), f"{path} must be a string"
    elif expected_type == "boolean":
        assert isinstance(value, bool), f"{path} must be a boolean"
    elif expected_type == "integer":
        assert isinstance(value, int) and not isinstance(value, bool), f"{path} must be an integer"
    elif expected_type == "null":
        assert value is None, f"{path} must be null"


def assert_success_contract(response: Any, openapi: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    assert response.status_code in {200, 201}, response.text
    operation = openapi["paths"][path][method.lower()]
    declared = operation["responses"][str(response.status_code)]["content"]["application/json"]["schema"]
    payload = response.json()
    assert_matches_schema(payload, declared, openapi)
    return payload


def client_and_workspace(tmp_path: Path) -> tuple[TestClient, dict[str, Any]]:
    api = TestClient(create_app(data_root=tmp_path / "data", admin_token="synthetic-admin"))
    api.__enter__()
    assert api.post("/api/v3/session", json={"adminToken": "synthetic-admin"}).status_code == 200
    workspace = api.post("/api/v3/workspaces", json={"displayName": "Contract", "kind": "sandbox"}).json()["data"]
    return api, workspace


def balanced_draft(identifier: str, units: str = "10") -> dict[str, Any]:
    return {
        "id": identifier,
        "date": "2026-09-03",
        "description": "Synthetic contract entry",
        "balancingCommodityCode": "CNY",
        "postings": [
            {"id": f"{identifier}-d", "accountId": "cash", "side": "debit", "units": units, "commodityCode": "CNY"},
            {"id": f"{identifier}-c", "accountId": "capital", "side": "credit", "units": units, "commodityCode": "CNY"},
        ],
    }


def test_journal_success_responses_match_generated_openapi(tmp_path: Path) -> None:
    api, workspace = client_and_workspace(tmp_path)
    try:
        openapi = api.get("/openapi.json").json()
        prefix = f"/api/v3/workspaces/{workspace['id']}"
        contract_prefix = "/api/v3/workspaces/{workspace_id}"
        assert api.post(prefix + "/demo/load-synthetic").status_code == 201

        draft = balanced_draft("contract-draft")
        created = assert_success_contract(
            api.post(prefix + "/journal-entry-drafts", json=draft), openapi,
            contract_prefix + "/journal-entry-drafts", "post",
        )
        assert created["data"]["postedEntryId"] is None
        assert created["data"]["draft"]["postings"][0]["units"] == "10"

        updated_draft = {**draft, "description": "Synthetic updated contract entry"}
        assert_success_contract(
            api.put(prefix + "/journal-entry-drafts/contract-draft", json=updated_draft), openapi,
            contract_prefix + "/journal-entry-drafts/{draft_id}", "put",
        )
        assert_success_contract(
            api.get(prefix + "/journal-entry-drafts"), openapi,
            contract_prefix + "/journal-entry-drafts", "get",
        )
        assert_success_contract(
            api.get(prefix + "/journal-entry-drafts/contract-draft"), openapi,
            contract_prefix + "/journal-entry-drafts/{draft_id}", "get",
        )
        valid = assert_success_contract(
            api.post(prefix + "/journal-entry-drafts/contract-draft/validate"), openapi,
            contract_prefix + "/journal-entry-drafts/{draft_id}/validate", "post",
        )
        assert valid["valid"] is True and valid["preview"] is not None and valid["issues"] == []
        posted = assert_success_contract(
            api.post(prefix + "/journal-entry-drafts/contract-draft/post"), openapi,
            contract_prefix + "/journal-entry-drafts/{draft_id}/post", "post",
        )
        assert posted["posted"] is True
        assert_success_contract(
            api.get(prefix + "/journal-entries"), openapi,
            contract_prefix + "/journal-entries", "get",
        )
        assert_success_contract(
            api.get(prefix + "/journal-entries/contract-draft"), openapi,
            contract_prefix + "/journal-entries/{entry_id}", "get",
        )
        reversal = assert_success_contract(
            api.post(prefix + "/journal-entries/contract-draft/reverse"), openapi,
            contract_prefix + "/journal-entries/{entry_id}/reverse", "post",
        )
        assert reversal["data"]["reversalOf"] == "contract-draft"

        removable = balanced_draft("removable")
        assert api.post(prefix + "/journal-entry-drafts", json=removable).status_code == 201
        deleted = assert_success_contract(
            api.delete(prefix + "/journal-entry-drafts/removable"), openapi,
            contract_prefix + "/journal-entry-drafts/{draft_id}", "delete",
        )
        assert deleted["deleted"] is True
    finally:
        api.__exit__(None, None, None)


def test_validation_false_null_preview_and_issue_shape(tmp_path: Path) -> None:
    api, workspace = client_and_workspace(tmp_path)
    try:
        openapi = api.get("/openapi.json").json()
        prefix = f"/api/v3/workspaces/{workspace['id']}"
        contract_path = "/api/v3/workspaces/{workspace_id}/journal-entry-drafts/{draft_id}/validate"
        assert api.post(prefix + "/demo/load-synthetic").status_code == 201
        invalid = balanced_draft("invalid")
        invalid["postings"][0]["accountId"] = "missing-account"
        assert api.post(prefix + "/journal-entry-drafts", json=invalid).status_code == 201
        payload = assert_success_contract(
            api.post(prefix + "/journal-entry-drafts/invalid/validate"), openapi, contract_path, "post"
        )
        assert payload["valid"] is False
        assert payload["preview"] is None
        assert payload["issues"]
        assert set(payload["issues"][0]) == {"code", "severity", "path", "message", "details"}
    finally:
        api.__exit__(None, None, None)


def test_consumer_read_models_and_undo_match_named_schemas(tmp_path: Path) -> None:
    api, workspace = client_and_workspace(tmp_path)
    try:
        openapi = api.get("/openapi.json").json()
        draft_schema = openapi["components"]["schemas"]["JournalEntryDraft"]["properties"]
        assert draft_schema["postings"]["minItems"] == 2
        assert draft_schema["postings"]["maxItems"] == 200
        for schema_name, field_names in {
            "PostingDraft": ["units", "valuationRate"],
            "LotAllocation": ["units"],
            "CompletedPosting": ["units", "valuationRate", "valuationAmount"],
            "FinancialStatement": ["assets", "liabilities", "equity", "income", "expenses", "netIncome"],
            "CashFlowItem": ["amount"],
        }.items():
            properties = openapi["components"]["schemas"][schema_name]["properties"]
            for field_name in field_names:
                rendered = properties[field_name]
                allowed = {item.get("type") for item in rendered.get("anyOf", [])}
                assert rendered.get("type") == "string" or allowed == {"string", "null"}
        issue_schema = openapi["components"]["schemas"]["ValidationIssue"]
        assert set(issue_schema["required"]) == {"code", "severity", "path", "message", "details"}
        assert issue_schema["additionalProperties"] is False
        assert issue_schema["properties"]["severity"]["enum"] == ["error", "warning"]
        assert issue_schema["properties"]["details"]["additionalProperties"] == {"type": "string"}
        prefix = f"/api/v3/workspaces/{workspace['id']}"
        contract_prefix = "/api/v3/workspaces/{workspace_id}"
        assert api.post(prefix + "/demo/load-synthetic").status_code == 201
        paths = [
            "/commodities", "/accounts", "/price-quotes", "/t-accounts", "/dashboard",
            "/financial-statements", "/cash-flow", "/reconciliation", "/living-accounts",
            "/living-snapshots", "/monthly-plans", "/recurring-entry-rules", "/world", "/undo/latest",
        ]
        for suffix in paths:
            payload = assert_success_contract(api.get(prefix + suffix), openapi, contract_prefix + suffix, "get")
            assert payload["workspaceId"] == workspace["id"]
            success_schema = openapi["paths"][contract_prefix + suffix]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
            assert success_schema["$ref"] != "#/components/schemas/LedgerResponse"

        latest = api.get(prefix + "/undo/latest").json()["data"]
        undone = assert_success_contract(
            api.post(prefix + "/undo", json={"undoToken": latest["undoToken"]}), openapi,
            contract_prefix + "/undo", "post",
        )
        assert undone["undone"] is True
    finally:
        api.__exit__(None, None, None)


def test_decimal_precision_scope_archival_and_workspace_isolation(tmp_path: Path) -> None:
    api, first = client_and_workspace(tmp_path)
    try:
        second = api.post("/api/v3/workspaces", json={"displayName": "Second", "kind": "sandbox"}).json()["data"]
        first_prefix = f"/api/v3/workspaces/{first['id']}"
        second_prefix = f"/api/v3/workspaces/{second['id']}"
        commodity = {"code": "HPX", "kind": "currency", "scale": 18, "name": "Synthetic precision unit"}
        assert api.post(first_prefix + "/commodities", json=commodity).status_code == 201
        for account_id, account_type in (("hpx-cash", "asset"), ("hpx-equity", "equity")):
            account = {
                "id": account_id, "code": account_id, "name": account_id,
                "type": account_type, "allowedCommodityCodes": ["HPX"],
            }
            assert api.post(first_prefix + "/accounts", json=account).status_code == 201
        precise = balanced_draft("precise", "0.123456789012345678")
        precise["balancingCommodityCode"] = "HPX"
        precise["postings"][0].update({"accountId": "hpx-cash", "commodityCode": "HPX"})
        precise["postings"][1].update({"accountId": "hpx-equity", "commodityCode": "HPX"})
        created = api.post(first_prefix + "/journal-entry-drafts", json=precise)
        assert created.status_code == 201
        assert created.json()["data"]["draft"]["postings"][0]["units"] == "0.123456789012345678"
        assert api.get(second_prefix + "/journal-entry-drafts").json()["data"] == []

        token = api.post("/api/v3/access-tokens", json={
            "name": "Read only", "workspaceIds": [first["id"]], "scopes": ["ledger:read"],
        }).json()["token"]
        denied = api.post(first_prefix + "/journal-entry-drafts", json=balanced_draft("denied"), headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "TOKEN_SCOPE_DENIED"
        assert api.patch(f"/api/v3/workspaces/{first['id']}", json={"status": "archived"}).status_code == 200
        blocked = api.put(first_prefix + "/journal-entry-drafts/precise", json=precise)
        assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "WORKSPACE_ARCHIVED"
    finally:
        api.__exit__(None, None, None)


def test_published_openapi_is_semantically_identical_to_runtime(tmp_path: Path) -> None:
    artifact = Path(__file__).resolve().parents[2] / "docs" / "release" / f"finance-core-v{__version__}-openapi.json"
    expected = json.loads(artifact.read_text(encoding="utf-8"))
    with TestClient(create_app(data_root=tmp_path / "data", admin_token="synthetic-admin")) as api:
        assert api.get("/openapi.json").json() == expected
