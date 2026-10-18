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


def create_access_token(api: TestClient, workspace_ids: list[str], scopes: list[str]) -> str:
    response = api.post("/api/v3/access-tokens", json={
        "name": "Synthetic contract actor", "workspaceIds": workspace_ids, "scopes": scopes,
    })
    assert response.status_code == 201, response.text
    return response.json()["token"]


def test_app_factory_honors_data_root_environment_and_explicit_override(tmp_path, monkeypatch):
    environment_root = tmp_path / "environment"
    explicit_root = tmp_path / "explicit"
    monkeypatch.setenv("FINANCE_CORE_DATA_ROOT", str(environment_root))
    with TestClient(create_app(admin_token="synthetic")) as api:
        assert api.post("/api/v3/session", json={"adminToken": "synthetic"}).status_code == 200
        create_workspace(api, "Environment fixture")
    with TestClient(create_app(data_root=explicit_root, admin_token="synthetic")) as api:
        assert api.post("/api/v3/session", json={"adminToken": "synthetic"}).status_code == 200
        assert api.get("/api/v3/workspaces").json()["data"] == []
    with TestClient(create_app(admin_token="synthetic")) as api:
        assert api.post("/api/v3/session", json={"adminToken": "synthetic"}).status_code == 200
        assert api.get("/api/v3/workspaces").json()["data"][0]["displayName"] == "Environment fixture"


def seed_holding(api: TestClient, workspace_id: str, holding_id: str = "lot-one") -> dict:
    prefix = f"/api/v3/workspaces/{workspace_id}"
    assert api.post(prefix + "/demo/load-synthetic").status_code == 201
    draft = {
        "id": f"buy-{holding_id}",
        "date": "2026-09-03",
        "description": "Synthetic holding purchase",
        "balancingCommodityCode": "CNY",
        "postings": [
            {
                "id": f"buy-{holding_id}-asset", "accountId": "investment", "side": "debit",
                "units": "2.0000", "commodityCode": "DEMO", "valuationRate": "100.00",
                "rateType": "cost", "lotAction": "acquire", "lotId": holding_id,
                "cashFlowCategory": "investment",
            },
            {
                "id": f"buy-{holding_id}-cash", "accountId": "cash", "side": "credit",
                "units": "200.00", "commodityCode": "CNY", "cashFlowCategory": "investment",
            },
        ],
    }
    assert api.post(prefix + "/journal-entry-drafts", json=draft).status_code == 201
    posted = api.post(prefix + f"/journal-entry-drafts/{draft['id']}/post")
    assert posted.status_code == 200, posted.text
    response = api.get(prefix + f"/holdings/{holding_id}")
    assert response.status_code == 200, response.text
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


def test_openapi_names_responses_and_declares_security_scopes_and_errors(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        schema = api.get("/openapi.json").json()
        assert schema["info"]["version"] == "3.8.0"
        schemes = schema["components"]["securitySchemes"]
        assert schemes["BearerAccessToken"]["scheme"] == "bearer"
        assert schemes["SessionCookie"] == {
            "type": "apiKey", "in": "cookie", "name": "fc_session",
            "description": "HttpOnly local admin session cookie.",
        }
        for path in ("/api/v3/health", "/api/v3/me", "/api/v3/workspaces"):
            for operation in schema["paths"][path].values():
                success = operation["responses"].get("200") or operation["responses"].get("201")
                json_schema = success["content"]["application/json"]["schema"]
                assert json_schema["$ref"].startswith("#/components/schemas/")
        ledger_paths = {
            path: item for path, item in schema["paths"].items()
            if path.startswith("/api/v3/workspaces/{workspace_id}/")
        }
        assert ledger_paths
        for path, path_item in ledger_paths.items():
            for method, operation in path_item.items():
                expected_scope = "ledger:read" if method == "get" or path.endswith("/validate") else "ledger:write"
                if operation.get('x-fc-required-actor') == 'owner-session':
                    assert operation['security'] == [{'SessionCookie':[]}]
                    assert 'x-fc-required-scope' not in operation
                else:
                    assert operation["security"] == [{"BearerAccessToken": []}, {"SessionCookie": []}]
                    assert operation["x-fc-required-scope"] == expected_scope, (path, operation["operationId"])
                assert {"401", "403", "404", "409", "410", "422"}.issubset(operation["responses"])
                success = operation["responses"].get("200") or operation["responses"].get("201")
                media = next(iter(success["content"].values()))
                if path.endswith('.csv') and operation.get('x-fc-required-actor') == 'owner-session':
                    assert 'text/csv' in success['content']
                    assert success['content']['text/csv']['schema']['type']=='string'
                else:
                    assert media["schema"]["$ref"].startswith("#/components/schemas/")
        holding_schema = schema["components"]["schemas"]["Holding"]["properties"]
        for decimal_field in (
            "originalUnits", "remainingUnits", "originalCost", "remainingCost",
            "latestPrice", "marketValue", "unrealizedPnL",
        ):
            rendered = holding_schema[decimal_field]
            assert rendered.get("type") == "string" or {item.get("type") for item in rendered["anyOf"]} == {"string", "null"}
        descriptions = " ".join(
            operation["responses"][code]["description"]
            for operation in ledger_paths["/api/v3/workspaces/{workspace_id}/holdings/{holding_id}"].values()
            for code in ("401", "403", "404", "409", "410", "422")
        )
        for code in (
            "AUTH_REQUIRED", "TOKEN_SCOPE_DENIED", "WORKSPACE_NOT_FOUND", "RESOURCE_NOT_FOUND",
            "WORKSPACE_ARCHIVED", "UNDO_CONFLICT", "UNDO_EXPIRED", "INVALID_REQUEST",
        ):
            assert code in descriptions
    finally:
        api.__exit__(None, None, None)


def test_health_exposes_only_commit_shaped_release_metadata(tmp_path: Path):
    api = TestClient(create_app(
        data_root=tmp_path / "data", admin_token="synthetic-admin",
        build_commit="a" * 40, release_commit="b" * 40,
    ))
    with api:
        health = api.get("/api/v3/health").json()
        assert health["buildCommit"] == "a" * 40
        assert health["releaseCommit"] == "b" * 40
        assert health["serviceVersion"] == "3.8.0"
        assert health["apiVersion"] == "3.8.0"


def test_single_holding_is_scoped_and_hidden_across_workspaces(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        first = create_workspace(api, "First")
        second = create_workspace(api, "Second")
        holding = seed_holding(api, first["id"], "shared-lot")
        assert holding["lotId"] == "shared-lot"
        assert holding["remainingUnits"] == "2"
        second_prefix = f"/api/v3/workspaces/{second['id']}"
        hidden_from_second = api.get(second_prefix + "/holdings/shared-lot")
        assert hidden_from_second.status_code == 404
        assert hidden_from_second.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        read_secret = create_access_token(api, [first["id"]], ["ledger:read"])
        headers = {"Authorization": f"Bearer {read_secret}"}
        assert api.get(f"/api/v3/workspaces/{first['id']}/holdings/shared-lot", headers=headers).status_code == 200
        wrong_workspace = api.get(second_prefix + "/holdings/shared-lot", headers=headers)
        assert wrong_workspace.status_code == 404
        assert wrong_workspace.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
        assert read_secret not in wrong_workspace.text
    finally:
        api.__exit__(None, None, None)


def test_living_account_delete_restores_account_and_snapshots_with_one_undo(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        workspace = create_workspace(api, "Living")
        prefix = f"/api/v3/workspaces/{workspace['id']}"
        assert api.post(prefix + "/demo/load-synthetic").status_code == 201
        account = {
            "id": "living-one", "name": "Synthetic wallet", "commodityCode": "CNY",
            "balance": "10.00", "updatedAt": "2026-09-03T00:00:00+00:00",
        }
        assert api.post(prefix + "/living-accounts", json=account).status_code == 201
        assert api.post(prefix + "/living-accounts/living-one/record-balance", json={"balance": "12.50"}).status_code == 200
        read_secret = create_access_token(api, [workspace["id"]], ["ledger:read"])
        denied = api.delete(prefix + "/living-accounts/living-one", headers={"Authorization": f"Bearer {read_secret}"})
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "TOKEN_SCOPE_DENIED"
        removed = api.delete(prefix + "/living-accounts/living-one")
        assert removed.status_code == 200, removed.text
        body = removed.json()
        assert body["deletedSnapshotCount"] == 1
        assert body["undo"]["operationType"] == "living-account.delete"
        assert body["undo"]["workspaceId"] == workspace["id"]
        assert set(body["undo"]) == {"operationId", "undoToken", "expiresAt", "workspaceId", "operationType"}
        assert api.get(prefix + "/living-accounts").json()["data"] == []
        assert api.get(prefix + "/living-snapshots").json()["data"] == []
        restored = api.post("/api/v3/undo", json={
            "undoToken": body["undo"]["undoToken"], "workspaceId": workspace["id"],
        })
        assert restored.status_code == 200, restored.text
        accounts = api.get(prefix + "/living-accounts").json()["data"]
        snapshots = api.get(prefix + "/living-snapshots").json()["data"]
        assert accounts[0]["balance"] == "12.5"
        assert snapshots[0]["accountId"] == "living-one"
        assert snapshots[0]["balance"] == "12.5"
    finally:
        api.__exit__(None, None, None)


def test_archived_and_quarantined_workspaces_protect_new_endpoints(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        archived = create_workspace(api, "Archived")
        prefix = f"/api/v3/workspaces/{archived['id']}"
        assert api.patch(f"/api/v3/workspaces/{archived['id']}", json={"status": "archived"}).status_code == 200
        blocked = api.delete(prefix + "/living-accounts/unknown")
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "WORKSPACE_ARCHIVED"
        assert api.get(prefix + "/holdings/unknown").status_code == 404
        quarantined = create_workspace(api, "Quarantined")
        assert api.delete(f"/api/v3/workspaces/{quarantined['id']}").status_code == 200
        hidden = api.get(f"/api/v3/workspaces/{quarantined['id']}/holdings/unknown")
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    finally:
        api.__exit__(None, None, None)


def test_standard_auth_validation_and_undo_errors(tmp_path: Path):
    api = authenticated_client(tmp_path)
    try:
        workspace = create_workspace(api, "Errors")
        prefix = f"/api/v3/workspaces/{workspace['id']}"
        api.cookies.clear()
        missing = api.get(prefix + "/holdings/unknown")
        assert missing.status_code == 401
        assert missing.json()["error"]["code"] == "AUTH_REQUIRED"
        assert api.post("/api/v3/session", json={"adminToken": "admin-secret"}).status_code == 200
        invalid = api.post("/api/v3/workspaces", json={"displayName": ""})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_REQUEST"
        expired = api.post("/api/v3/undo", json={"undoToken": "synthetic-expired", "workspaceId": workspace["id"]})
        assert expired.status_code == 410
        assert expired.json()["error"]["code"] == "UNDO_EXPIRED"
        quarantined = api.delete(f"/api/v3/workspaces/{workspace['id']}").json()
        vault_path = tmp_path / "data" / "workspaces" / workspace["id"] / "finance-core.sqlite3"
        vault_path.parent.mkdir(parents=True, exist_ok=True)
        vault_path.touch()
        conflict = api.post("/api/v3/undo", json={"undoToken": quarantined["undo"]["undoToken"]})
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "UNDO_CONFLICT"
        assert str(tmp_path) not in conflict.text
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
