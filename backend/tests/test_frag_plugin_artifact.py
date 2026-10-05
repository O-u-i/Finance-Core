"""Synthetic checks for the optional FRAG plugin release."""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from build_frag_plugin import ARCHIVE, LEGACY_ARCHIVE, SOURCE, check, expected_manifest, sha256  # noqa: E402

spec = importlib.util.spec_from_file_location("fc_frag_plugin", SOURCE / "adapter.py")
assert spec is not None and spec.loader is not None
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

WORKSPACE = "synthetic-workspace"
ENTRY = "entry:synthetic-entry"
DRAFT = "draft:synthetic-draft"


def configured(monkeypatch: pytest.MonkeyPatch, *, records: dict | None = None) -> None:
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_READ_TOKEN", "synthetic-read-token")
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:8788")
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_UI_URL", "http://127.0.0.1:5174")
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_RECORDS_JSON", json.dumps(records or {WORKSPACE: [ENTRY, DRAFT]}))


def fake_fc(monkeypatch: pytest.MonkeyPatch, *, version: str = "3.1.1", available: bool = True):
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        assert request.method == "GET"
        if not available:
            raise httpx.ConnectError("synthetic outage", request=request)
        assert request.headers["authorization"] == "Bearer synthetic-read-token"
        path = request.url.path
        if path == "/api/v3/health":
            return httpx.Response(200, json={"status": "ok", "service": "finance-core", "apiVersion": version})
        if path == "/api/v3/workspaces":
            return httpx.Response(200, json={"data": [
                {"id": WORKSPACE, "displayName": "Synthetic Workspace", "status": "active"},
                {"id": "other-workspace", "displayName": "Other", "status": "active"},
            ]})
        if path == f"/api/v3/workspaces/{WORKSPACE}/dashboard":
            return httpx.Response(200, json={"workspaceId": WORKSPACE, "data": {
                "entryCount": 1, "draftCount": 1, "openLotCount": 0,
                "commoditySummaries": [{"commodityCode": "USD", "cash": "12.34", "bookValue": "12.34",
                                         "marketValue": "12.34", "unrealizedPnL": "0"}],
            }})
        if path == f"/api/v3/workspaces/{WORKSPACE}/journal-entries/synthetic-entry":
            return httpx.Response(200, json={"workspaceId": WORKSPACE, "data": {
                "id": "synthetic-entry", "date": "2026-01-01", "description": "Synthetic entry",
                "postedAt": "2026-01-01T00:00:00Z", "postings": [
                    {"accountId": "cash", "side": "debit", "units": "12.34", "commodityCode": "USD"},
                    {"accountId": "income", "side": "credit", "units": "12.34", "commodityCode": "USD"},
                ],
            }})
        if path == f"/api/v3/workspaces/{WORKSPACE}/journal-entry-drafts/synthetic-draft":
            return httpx.Response(200, json={"workspaceId": WORKSPACE, "data": {
                "draft": {"id": "synthetic-draft", "date": "2026-01-02", "description": "Synthetic draft", "postings": []},
                "status": "draft", "updatedAt": "2026-01-02T00:00:00Z",
            }})
        return httpx.Response(404, json={"error": {"code": "RESOURCE_NOT_FOUND"}})

    def client(base: str, token: str) -> httpx.Client:
        return httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"},
                            transport=httpx.MockTransport(handle))

    monkeypatch.setattr(adapter, "_client", client)
    return seen


def test_archive_integrity_and_exact_contract():
    digest = check()
    assert len(digest) == 64 and digest == sha256(ARCHIVE.read_bytes())
    with zipfile.ZipFile(ARCHIVE) as package:
        assert package.namelist() == ["manifest.json", "adapter.py", "ui.js"]
        manifest = json.loads(package.read("manifest.json"))
        assert manifest == expected_manifest()
        assert manifest["protocolVersion"] == 2
        assert manifest["version"] == "1.1.0"
        assert manifest["minHostVersion"] == "1.8.0"
        assert manifest["name"] == "Finance Core"
        assert manifest["capabilities"] == ["evidence.read"]
        assert manifest["fcApiVersion"] == "3.1.1"
    assert "synthetic-read-token" not in (SOURCE / "ui.js").read_text(encoding="utf-8")
    assert "FINANCE_CORE_PLUGIN_READ_TOKEN" not in (SOURCE / "ui.js").read_text(encoding="utf-8")


def test_dashboard_and_scopes_use_only_bounded_reads(monkeypatch: pytest.MonkeyPatch):
    configured(monkeypatch)
    seen = fake_fc(monkeypatch)
    app = FastAPI()
    app.include_router(adapter.create_router())
    with TestClient(app) as client:
        scopes = client.get("/api/plugins/finance-core/scopes")
        assert scopes.status_code == 200
        assert scopes.json() == {"workspaces": [{"id": WORKSPACE, "label": "Synthetic Workspace", "records": [
            {"id": ENTRY, "label": "Synthetic entry"}, {"id": DRAFT, "label": "Synthetic draft"},
        ]}]}
        dashboard = client.get("/api/plugins/finance-core/dashboard", params={"workspaceId": WORKSPACE})
        assert dashboard.status_code == 200
        assert dashboard.json()["data"]["commoditySummaries"][0]["cash"] == "12.34"
        assert dashboard.json()["journalUrl"] == "http://127.0.0.1:5174"
        assert client.post("/api/plugins/finance-core/dashboard").status_code == 405
        assert client.get("/api/plugins/finance-core/dashboard", params={"workspaceId": "other-workspace"}).status_code == 404
    assert not any(path.endswith("/journal-entries") or path.endswith("/journal-entry-drafts") for path in seen)
    assert all(route.methods <= {"GET", "HEAD"} for route in adapter.create_router().routes)


def test_evidence_is_ordered_bounded_and_workspace_scoped(monkeypatch: pytest.MonkeyPatch):
    configured(monkeypatch)
    seen = fake_fc(monkeypatch)
    result = adapter.read_evidence(WORKSPACE, [DRAFT, ENTRY])
    assert [item["recordId"] for item in result] == [DRAFT, ENTRY]
    assert all(set(item) == {"recordId", "label", "text", "revision"} for item in result)
    assert "12.34" in result[1]["text"]
    assert len(result[0]["revision"]) == 64
    with pytest.raises(ValueError):
        adapter.read_evidence("other-workspace", [ENTRY])
    with pytest.raises(ValueError):
        adapter.read_evidence(WORKSPACE, [ENTRY] * 11)
    with pytest.raises(ValueError):
        adapter.read_evidence(WORKSPACE, [ENTRY, ENTRY])
    assert seen.count(f"/api/v3/workspaces/{WORKSPACE}/journal-entries/synthetic-entry") == 1


def test_disabled_unavailable_and_incompatible_fc(monkeypatch: pytest.MonkeyPatch):
    configured(monkeypatch)
    app = FastAPI()
    app.include_router(adapter.create_router())
    fake_fc(monkeypatch, version="3.1.0")
    with TestClient(app) as client:
        assert client.get("/api/plugins/finance-core/scopes").status_code == 409
    fake_fc(monkeypatch, available=False)
    with TestClient(app) as client:
        assert client.get("/api/plugins/finance-core/scopes").status_code == 503
    monkeypatch.delenv("FINANCE_CORE_PLUGIN_READ_TOKEN")
    with TestClient(app) as client:
        assert client.get("/api/plugins/finance-core/scopes").status_code == 503
    with pytest.raises(adapter.FcUnavailable):
        adapter.read_evidence(WORKSPACE, [ENTRY])


def test_protocol1_archive_remains_the_pinned_legacy_release():
    assert sha256(LEGACY_ARCHIVE.read_bytes()) == (
        "79918f940b29dd6def5a3702bf043719eebbe0a9ece28da67f0d806a0428a6bd"
    )
    with zipfile.ZipFile(LEGACY_ARCHIVE) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["protocolVersion"] == 1
        assert manifest["version"] == "1.0.0"
        assert manifest["minHostVersion"] == "1.0.0"
        for name, digest in manifest["files"].items():
            assert sha256(package.read(name)) == digest


def test_protocol2_scope_and_evidence_hooks_preserve_selected_records(monkeypatch: pytest.MonkeyPatch):
    configured(monkeypatch)
    seen = fake_fc(monkeypatch)
    assert adapter.list_scopes() == {"scopes": [{
        "id": WORKSPACE, "label": "Synthetic Workspace", "records": [
            {"id": ENTRY, "label": "Synthetic entry"}, {"id": DRAFT, "label": "Synthetic draft"},
        ],
    }]}
    assert adapter.list_scopes(WORKSPACE)["scopes"][0]["id"] == WORKSPACE
    request = {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": WORKSPACE,
               "recordIds": [DRAFT, ENTRY]}
    result = adapter.read_evidence_request(request)
    assert set(result) == {"protocolVersion", "pluginId", "scopeId", "records"}
    assert result["protocolVersion"] == 2 and result["pluginId"] == "finance-core"
    assert result["scopeId"] == WORKSPACE
    assert [record["recordId"] for record in result["records"]] == [DRAFT, ENTRY]
    assert all(set(record) == {"recordId", "label", "text", "revision"} for record in result["records"])
    assert "12.34" in result["records"][1]["text"]
    assert all(len(record["revision"]) == 64 for record in result["records"])
    assert not any(path.endswith("/journal-entries") or path.endswith("/journal-entry-drafts") for path in seen)


@pytest.mark.parametrize("invalid_request", [
    None, [], {},
    {"protocolVersion": 1, "pluginId": "finance-core", "scopeId": WORKSPACE, "recordIds": [ENTRY]},
    {"protocolVersion": "2", "pluginId": "finance-core", "scopeId": WORKSPACE, "recordIds": [ENTRY]},
    {"protocolVersion": 2.0, "pluginId": "finance-core", "scopeId": WORKSPACE, "recordIds": [ENTRY]},
    {"protocolVersion": 2, "pluginId": "other-plugin", "scopeId": WORKSPACE, "recordIds": [ENTRY]},
    {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": WORKSPACE, "recordIds": [ENTRY],
     "endpoint": "/arbitrary-path"},
    {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": "../outside", "recordIds": [ENTRY]},
    {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": "other-workspace", "recordIds": [ENTRY]},
    {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": WORKSPACE, "recordIds": []},
    {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": WORKSPACE, "recordIds": [ENTRY, ENTRY]},
    {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": WORKSPACE, "recordIds": ["entry:../outside"]},
    {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": WORKSPACE, "recordIds": ["entry:unselected"]},
    {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": WORKSPACE, "recordIds": [ENTRY] * 11},
])
def test_protocol2_invalid_requests_do_not_send_http(monkeypatch: pytest.MonkeyPatch, invalid_request):
    configured(monkeypatch)
    seen = fake_fc(monkeypatch)
    with pytest.raises(ValueError):
        adapter.read_evidence_request(invalid_request)
    assert seen == []


@pytest.mark.parametrize("scope_id", [123, "../outside", "other-workspace"])
def test_protocol2_scope_filter_rejects_unconfigured_scopes_before_http(monkeypatch: pytest.MonkeyPatch, scope_id):
    configured(monkeypatch)
    seen = fake_fc(monkeypatch)
    with pytest.raises(ValueError):
        adapter.list_scopes(scope_id)
    assert seen == []


def test_protocol2_scope_filter_does_not_expose_unconfigured_workspaces(monkeypatch: pytest.MonkeyPatch):
    configured(monkeypatch)
    seen = fake_fc(monkeypatch)
    monkeypatch.setattr(adapter, "_workspaces", lambda _client: {})
    assert adapter.list_scopes() == {"scopes": []}
    with pytest.raises(ValueError):
        adapter.list_scopes(WORKSPACE)
    assert not any("/journal-" in path for path in seen)


def test_source_revision_requires_no_credentials_or_http(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FINANCE_CORE_PLUGIN_READ_TOKEN", raising=False)
    monkeypatch.delenv("FINANCE_CORE_PLUGIN_API_URL", raising=False)
    monkeypatch.delenv("FINANCE_CORE_PLUGIN_RECORDS_JSON", raising=False)
    monkeypatch.setattr(adapter, "_settings", lambda: pytest.fail("Source revision must not require settings or credentials."))
    monkeypatch.setattr(adapter, "_client", lambda *_args: pytest.fail("Source revision must not access HTTP."))
    expected = sha256(b'{"apiUrl":"http://127.0.0.1:8788","recordsJson":"{}"}')
    assert adapter.source_revision() == expected
    assert len(expected) == 64 and set(expected) <= set("0123456789abcdef")


def test_source_revision_changes_for_supplier_or_allowlist_with_identical_record_data(monkeypatch: pytest.MonkeyPatch):
    configured(monkeypatch)
    fake_fc(monkeypatch)
    original_revision = adapter.source_revision()
    original_record = adapter.read_evidence(WORKSPACE, [ENTRY])
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:9799")
    changed_supplier_revision = adapter.source_revision()
    assert changed_supplier_revision != original_revision
    assert adapter.read_evidence(WORKSPACE, [ENTRY]) == original_record
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_RECORDS_JSON", json.dumps({WORKSPACE: [ENTRY]}))
    assert adapter.source_revision() not in {original_revision, changed_supplier_revision}
    assert adapter.read_evidence(WORKSPACE, [ENTRY]) == original_record


def test_source_revision_excludes_credentials_ui_and_normalizes_trailing_slash(monkeypatch: pytest.MonkeyPatch):
    configured(monkeypatch)
    original_revision = adapter.source_revision()
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_READ_TOKEN", "other-synthetic-secret")
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_UI_URL", "http://127.0.0.1:6174")
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:8788/")
    assert adapter.source_revision() == original_revision


def test_protocol2_reads_the_actual_released_api_with_a_read_only_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from finance_core.app_v3 import create_app

    with TestClient(create_app(data_root=tmp_path / "data", admin_token="synthetic-admin")) as api:
        assert api.post("/api/v3/session", json={"adminToken": "synthetic-admin"}).status_code == 200
        workspace = api.post("/api/v3/workspaces", json={"displayName": "Plugin contract", "kind": "sandbox"}).json()["data"]
        workspace_id = workspace["id"]
        prefix = f"/api/v3/workspaces/{workspace_id}"
        assert api.post(prefix + "/demo/load-synthetic").status_code == 201
        draft = {"id": "plugin-draft", "date": "2026-01-01", "description": "Synthetic plugin draft",
                 "balancingCommodityCode": "CNY", "postings": [
                     {"id": "plugin-debit", "accountId": "cash", "side": "debit", "units": "12.34", "commodityCode": "CNY"},
                     {"id": "plugin-credit", "accountId": "capital", "side": "credit", "units": "12.34", "commodityCode": "CNY"},
                 ]}
        assert api.post(prefix + "/journal-entry-drafts", json=draft).status_code == 201
        token = api.post("/api/v3/access-tokens", json={"name": "Synthetic plugin", "workspaceIds": [workspace_id],
                                                       "scopes": ["ledger:read"]}).json()["token"]
        api.cookies.clear()
        configured(monkeypatch, records={workspace_id: ["draft:plugin-draft"]})
        monkeypatch.setenv("FINANCE_CORE_PLUGIN_READ_TOKEN", token)
        seen = []

        def handle(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            seen.append(request.url.path)
            return api.get(request.url.path, headers={"Authorization": request.headers["authorization"]})

        monkeypatch.setattr(adapter, "_client", lambda base, secret: httpx.Client(
            base_url=base, headers={"Authorization": f"Bearer {secret}"}, transport=httpx.MockTransport(handle),
        ))
        assert adapter.list_scopes(workspace_id)["scopes"][0]["records"][0]["id"] == "draft:plugin-draft"
        result = adapter.read_evidence_request({"protocolVersion": 2, "pluginId": "finance-core",
                                               "scopeId": workspace_id, "recordIds": ["draft:plugin-draft"]})
        assert result["scopeId"] == workspace_id and result["records"][0]["recordId"] == "draft:plugin-draft"
        assert "12.34" in result["records"][0]["text"]
        assert token not in json.dumps(result)
        assert set(seen) == {"/api/v3/health", "/api/v3/workspaces", prefix + "/journal-entry-drafts/plugin-draft"}
