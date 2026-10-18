"""Synthetic checks for the optional FRAG plugin release."""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from finance_core.monthly_review import monthly_review

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
REPORT = "monthly-review:2025-03"


def test_dedicated_reader_catalog_and_selected_item_use_only_released_gets(monkeypatch, tmp_path):
    from test_v2 import client
    with client(tmp_path) as scoped:
        api, prefix = scoped.api, scoped.prefix
        wid = prefix.rsplit('/', 1)[1]
        assert scoped.post('/api/v2/demo/load-synthetic?profile=economic-evidence&asOf=2026-08-31').status_code == 201
        token = api.post('/api/v3/access-tokens', json={'name': 'Reader integration', 'workspaceIds': [wid],
            'scopes': ['ledger:read'], 'readGrant': {'mode': 'living', 'itemIds': []}}).json()['token']
        expected = api.get(prefix + '/reader/catalog', headers={'Authorization': 'Bearer ' + token}).json()['data']['items']
        account = next(item for item in expected if item['kind'] == 'account')
        record = 'finance-item:' + account['id']
        configured(monkeypatch, records={wid: []})
        monkeypatch.setenv('FINANCE_CORE_PLUGIN_READ_TOKEN', token)
        seen = []
        def handle(request):
            assert request.method == 'GET'
            seen.append(request.url.raw_path.decode())
            return api.get(request.url.raw_path.decode(), headers={'Authorization': request.headers['authorization']})
        monkeypatch.setattr(adapter, '_client', lambda base, secret: httpx.Client(base_url=base,
            headers={'Authorization': 'Bearer ' + secret}, transport=httpx.MockTransport(handle)))
        metadata = adapter.connection_catalog()
        assert metadata['workspace']['id'] == wid and metadata['workspace']['kind'] == 'sandbox'
        assert metadata['readGrant'] == {'mode': 'living', 'itemIds': []}
        assert metadata['items'] == expected and token not in json.dumps(metadata)
        assert not any('/reader/items/' in path or '/reports/' in path for path in seen)
        monkeypatch.setenv('FINANCE_CORE_PLUGIN_RECORDS_JSON', json.dumps({wid: [record]}))
        listing = adapter.list_scopes(wid)
        assert listing['scopes'][0]['records'] == [{'id': record, 'label': account['label']}]
        assert not any('/reader/items/' in path for path in seen)
        evidence = adapter.read_evidence(wid, [record])[0]
        data = json.loads(evidence['text'].split('\n', 1)[1])
        assert data['itemId'] == account['id'] and evidence['revision'] == data['revision']
        assert data['coverage']['financialAdviceReady'] is False
        assert token not in evidence['text'] and 'baselineEvidence' not in evidence['text']
        from urllib.parse import quote
        assert prefix + '/reader/items/' + quote(account['id'], safe='') in seen
        before = len(seen)
        with pytest.raises(ValueError):
            adapter.read_evidence(wid, ['finance-item:account:' + 'a' * 32])
        assert len(seen) == before


def test_private_reader_instances_are_isolated_and_invalid_reconfiguration_is_atomic(monkeypatch, tmp_path):
    from test_v2 import client
    with client(tmp_path) as scoped:
        api, wid = scoped.api, scoped.prefix.rsplit('/', 1)[1]
        token = api.post('/api/v3/access-tokens', json={'name': 'Private reader', 'workspaceIds': [wid],
            'scopes': ['ledger:read'], 'readGrant': {'mode': 'all', 'itemIds': []}}).json()['token']
        configured(monkeypatch)
        modules = []
        for records in ([REPORT], []):
            instance = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(instance)
            def handle(request):
                assert request.method == 'GET'
                return api.get(request.url.raw_path.decode(), headers={'Authorization': request.headers['authorization']})
            monkeypatch.setattr(instance, '_client', lambda base, secret: httpx.Client(base_url=base,
                headers={'Authorization': 'Bearer ' + secret}, transport=httpx.MockTransport(handle)))
            values = {'FINANCE_CORE_PLUGIN_API_URL': 'http://127.0.0.1:8788',
                'FINANCE_CORE_PLUGIN_UI_URL': 'http://127.0.0.1:5174',
                'FINANCE_CORE_PLUGIN_READ_TOKEN': token, 'FINANCE_CORE_PLUGIN_RECORDS_JSON': json.dumps({wid: records})}
            instance.configure_connection(values)
            values['FINANCE_CORE_PLUGIN_READ_TOKEN'] = 'caller-mutated-input'
            modules.append(instance)
        assert modules[0].connection_catalog()['selectedRecordIds'] == [REPORT]
        assert modules[1].connection_catalog()['selectedRecordIds'] == []
        invalid = {**values, 'FINANCE_CORE_PLUGIN_READ_TOKEN': 'not a token'}
        with pytest.raises(ValueError):
            modules[0].configure_connection(invalid)
        assert modules[0].connection_catalog()['selectedRecordIds'] == [REPORT]
        import os
        assert json.loads(os.environ['FINANCE_CORE_PLUGIN_RECORDS_JSON']) == {WORKSPACE: [ENTRY, DRAFT]}


def monthly_fixture():
    return monthly_review("2025-03", [{"id": "private-entry", "date": "2025-03-01", "balancing_commodity_code": "CNY", "reversal_of": None}], [
        {"entry_id": "private-entry", "type": "asset", "subtype": "cash", "side": "debit", "units": "1.25",
            "valuation_amount": "1.25", "commodity_code": f"C{index:02d}", "cash_flow_category": "other"}
        for index in range(12)])


def test_month_to_date_uses_only_the_exact_whitelisted_summary_get(monkeypatch, tmp_path):
    from test_v2 import client, create_and_post, seed
    from test_month_to_date_review import income

    record = 'month-to-date:2026-08-18'
    with client(tmp_path) as scoped:
        seed(scoped)
        create_and_post(scoped, income('mtd-private', '2026-08-18', '12.34'))
        api, wid = scoped.api, scoped.prefix.rsplit('/', 1)[1]
        token = api.post('/api/v3/access-tokens', json={'name': 'Synthetic MTD reader',
            'workspaceIds': [wid], 'scopes': ['ledger:read']}).json()['token']
        api.cookies.clear()
        configured(monkeypatch, records={wid: [record]})
        monkeypatch.setenv('FINANCE_CORE_PLUGIN_READ_TOKEN', token)
        seen = []
        def handle(request):
            assert request.method == 'GET'
            seen.append(request.url.raw_path.decode())
            return api.get(request.url.raw_path.decode(), headers={'Authorization': request.headers['authorization']})
        monkeypatch.setattr(adapter, '_client', lambda base, secret: httpx.Client(base_url=base,
            headers={'Authorization': 'Bearer ' + secret}, transport=httpx.MockTransport(handle)))
        assert adapter.list_scopes(wid)['scopes'][0]['records'][0]['id'] == record
        assert not any('/reports/' in path for path in seen)
        result = adapter.read_evidence_request({'protocolVersion': 2, 'pluginId': 'finance-core', 'scopeId': wid, 'recordIds': [record]})
        evidence = result['records'][0]
        report = json.loads(evidence['text'].split('\n', 1)[1])
        assert report['asOf'] == '2026-08-18' and report['periodStatus'] == 'partial'
        assert report['period']['currencies'][0]['income'] == '12.34'
        assert evidence['revision'] == report['revision']
        assert 'PRIVATE' not in evidence['text'] and 'mtd-private' not in evidence['text'] and token not in evidence['text']
        assert set(seen) == {'/api/v3/health', '/api/v3/workspaces', scoped.prefix + '/reports/month-to-date?asOf=2026-08-18'}
        seen.clear()
        with pytest.raises(ValueError):
            adapter.read_evidence(wid, ['month-to-date:2026-08-17'])
        assert seen == []


def test_monthly_discovery_does_not_fetch_reports_and_read_is_full_and_stable(monkeypatch):
    configured(monkeypatch, records={WORKSPACE: [REPORT]})
    report = monthly_fixture()
    seen = fake_fc(monkeypatch, report=report)
    listing = adapter.list_scopes(WORKSPACE)
    assert listing["scopes"][0]["records"][0]["id"] == REPORT
    assert not any("/reports/" in path for path in seen)
    evidence = adapter.read_evidence(WORKSPACE, [REPORT])[0]
    assert len(evidence["text"]) > 8000
    assert evidence["text"].endswith("}") and "2025-01" in evidence["text"] and "2025-03" in evidence["text"]
    assert "private-entry" not in evidence["text"]
    assert "unknown" in evidence["text"] and "current-account-definitions" in evidence["text"]
    assert evidence["revision"] == report["revision"]
    assert adapter.read_evidence(WORKSPACE, [REPORT])[0] == evidence
    with pytest.raises(ValueError):
        adapter.read_evidence(WORKSPACE, ["monthly-review:2025-04"])


@pytest.mark.parametrize("mutation", ["extra-private-field", "missing-month", "wrong-period", "wrong-coverage", "float-amount", "private-amount", "private-code"])
def test_monthly_summary_contract_rejects_extra_missing_or_unsafe_fields(monkeypatch, mutation):
    report = deepcopy(monthly_fixture())
    if mutation == "extra-private-field": report["privateDescription"] = "Do not forward"
    if mutation == "missing-month": report["months"].pop()
    if mutation == "wrong-period": report["month"] = "2025-04"
    if mutation == "wrong-coverage": report["coverage"]["externalCompleteness"] = "complete"
    if mutation == "float-amount": report["months"][0]["currencies"][0]["income"] = 1.25
    if mutation == "private-amount": report["months"][0]["currencies"][0]["income"] = "private words"
    if mutation == "private-code": report["months"][0]["currencies"][0]["commodityCode"] = "private words"
    configured(monkeypatch, records={WORKSPACE: [REPORT]})
    fake_fc(monkeypatch, report=report)
    with pytest.raises(adapter.FcUnavailable, match="invalid monthly summary"):
        adapter.read_evidence(WORKSPACE, [REPORT])


def test_previous_protocol2_archive_is_unchanged():
    assert sha256((ROOT / "docs/release/finance-core-frag-plugin-v1.1.0.zip").read_bytes()) == "a96d5d2c4c8e4c8a7232db4be825925d37fb80052e74f6eab450744c62ccfacb"
    assert sha256((ROOT / "docs/release/finance-core-frag-plugin-v1.2.0.zip").read_bytes()) == "9d4f66b101183b19d5e50d807386c276cc77937517a6f7d59be813971ccd1ee6"
    assert sha256((ROOT / "docs/release/finance-core-frag-plugin-v1.4.0.zip").read_bytes()) == "f95049d6b411131b56612f0b40b3105f90e0cac7c528a0a01faa412fd3514ba3"


def configured(monkeypatch: pytest.MonkeyPatch, *, records: dict | None = None) -> None:
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_READ_TOKEN", "synthetic-read-token")
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:8788")
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_UI_URL", "http://127.0.0.1:5174")
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_RECORDS_JSON", json.dumps(records or {WORKSPACE: [ENTRY, DRAFT]}))


def fake_fc(monkeypatch: pytest.MonkeyPatch, *, version: str = "3.10.0", available: bool = True, report: dict | None = None):
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
        if path == f"/api/v3/workspaces/{WORKSPACE}/reports/monthly-review":
            assert request.url.params["month"] == "2025-03"
            return httpx.Response(200, json={"workspaceId": WORKSPACE, "readOnly": True, "data": report})
        if path == f'/api/v3/workspaces/{WORKSPACE}/reports/month-to-date':
            assert dict(request.url.params) == {'asOf': '2026-08-18'}
            return httpx.Response(200, json={'workspaceId': WORKSPACE, 'readOnly': True, 'data': report})
        if path == f'/api/v3/workspaces/{WORKSPACE}/reports/economic-evidence':
            assert dict(request.url.params) == {'asOf': '2026-08-31', 'through': '2026-09-30'}
            return httpx.Response(200, json={'workspaceId': WORKSPACE, 'readOnly': True, 'data': report})
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
        assert manifest["version"] == "1.10.0"
        assert manifest["minHostVersion"] == "1.13.4"
        assert manifest["name"] == "Finance Core"
        assert manifest["capabilities"] == ["evidence.read"]
        assert manifest["fcApiVersion"] == "3.10.0"
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


def test_economic_record_uses_only_exact_whitelisted_gets_and_preserves_full_summary(monkeypatch, tmp_path):
    from finance_core.app_v3 import create_app
    record_id = 'economic-evidence:2026-08-31:2026-09-30'
    with TestClient(create_app(data_root=tmp_path / 'economic', admin_token='synthetic')) as api:
        api.post('/api/v3/session', json={'adminToken': 'synthetic'})
        wid = api.post('/api/v3/workspaces', json={'displayName': 'Synthetic economics', 'kind': 'sandbox'}).json()['data']['id']
        prefix = '/api/v3/workspaces/' + wid
        assert api.post(prefix + '/demo/load-synthetic?profile=economic-evidence&asOf=2026-08-31').status_code == 201
        token = api.post('/api/v3/access-tokens', json={'name': 'Synthetic official reader', 'workspaceIds': [wid], 'scopes': ['ledger:read']}).json()['token']
        api.cookies.clear()
        configured(monkeypatch, records={wid: [record_id]})
        monkeypatch.setenv('FINANCE_CORE_PLUGIN_READ_TOKEN', token)
        seen = []
        def handle(request):
            assert request.method == 'GET'
            seen.append(str(request.url))
            return api.get(request.url.raw_path.decode(), headers={'Authorization': request.headers['authorization']})
        monkeypatch.setattr(adapter, '_client', lambda base, secret: httpx.Client(base_url=base,
            headers={'Authorization': 'Bearer ' + secret}, transport=httpx.MockTransport(handle)))
        assert adapter.list_scopes(wid)['scopes'][0]['records'][0]['id'] == record_id
        assert not any('/reports/' in path for path in seen)
        evidence = adapter.read_evidence(wid, [record_id])[0]
        report = json.loads(evidence['text'].split('\n', 1)[1])
        assert report['missingFacts'] == [] and evidence['revision'] == report['revision']
        assert report['debtRepayments'][0]['amount'] == '200'
        assert report['debtOutsideHorizon'][0]['amount'] == '1000'
        assert report['coverage']['externalCompleteness'] == 'unknown'
        assert 'synthetic-owner' not in evidence['text'] and token not in evidence['text']
        seen.clear()
        with pytest.raises(ValueError):
            adapter.read_evidence(wid, ['economic-evidence:2026-08-31:2026-10-01'])
        assert seen == []


def economic_fixture():
    return {'schemaVersion': 1, 'calculationVersion': 'economic-evidence-v1', 'asOf': '2026-08-31', 'through': '2026-09-30',
        'revision': 'a' * 64, 'balanceBasis': 'gross-registered-accounts', 'planBasis': 'planned-only-not-contractual-maturity',
        'debtBasis': 'confirmed-current-balance-only-future-charges-unknown',
        'balances': [{'segment': 'investment', 'currency': 'CNY', 'cashBalance': '1500', 'liabilityBalance': '200', 'observedDates': ['2026-08-31']}],
        'plannedOutflows': [], 'debtRepayments': [{'dueDate': '2026-09-15', 'currency': 'CNY', 'amount': '200', 'count': 1}],
        'debtOutsideHorizon': [], 'coverage': {'cashStocks': True, 'liabilityBalances': True, 'datedObligations': True,
            'externalCompleteness': 'unknown', 'currenciesCombined': False, 'personalAvailabilityAssessed': False}, 'missingFacts': []}


@pytest.mark.parametrize('mutation', ['private-field','private-balance','float-money','bad-date','string-flag',
    'hidden-gap','duplicate-group','external-complete','bad-revision','null-list','malformed-segment'])
def test_economic_summary_refuses_private_or_inconsistent_wire_data(monkeypatch, mutation):
    report = economic_fixture()
    if mutation == 'private-field': report['privateNote'] = 'PRIVATE SENTINEL'
    if mutation == 'private-balance': report['balances'][0]['accountName'] = 'PRIVATE SENTINEL'
    if mutation == 'float-money': report['balances'][0]['cashBalance'] = 1500.0
    if mutation == 'bad-date': report['debtRepayments'][0]['dueDate'] = '2026-02-30'
    if mutation == 'string-flag': report['coverage']['datedObligations'] = 'true'
    if mutation == 'hidden-gap': report['coverage']['datedObligations'] = False
    if mutation == 'duplicate-group': report['balances'].append(deepcopy(report['balances'][0]))
    if mutation == 'external-complete': report['coverage']['externalCompleteness'] = 'complete'
    if mutation == 'bad-revision': report['revision'] = 'PRIVATE SENTINEL'
    if mutation == 'null-list': report['plannedOutflows'] = None
    if mutation == 'malformed-segment': report['balances'][0]['segment'] = []
    configured(monkeypatch, records={WORKSPACE: ['economic-evidence:2026-08-31:2026-09-30']})
    fake_fc(monkeypatch, report=report)
    with pytest.raises(adapter.FcUnavailable, match='invalid economic summary'):
        adapter.read_evidence(WORKSPACE, ['economic-evidence:2026-08-31:2026-09-30'])


@pytest.mark.parametrize('record', ['economic-evidence:2026-02-30:2026-03-30', 'economic-evidence:2026-08-31:2026-08-31',
    'economic-evidence:2026-08-31:2028-09-30', 'economic-evidence:*:*'])
def test_invalid_economic_window_never_sends_http(monkeypatch, record):
    configured(monkeypatch, records={WORKSPACE: [record]})
    seen = fake_fc(monkeypatch)
    with pytest.raises((ValueError, adapter.FcUnavailable)):
        adapter.read_evidence(WORKSPACE, [record])
    assert seen == []


def month_to_date_fixture():
    from finance_core.monthly_review import month_to_date_review
    return month_to_date_review('2026-08-18', [{'id': 'private', 'date': '2026-08-18',
        'balancing_commodity_code': 'CNY', 'reversal_of': None}], [
        {'entry_id': 'private', 'type': 'asset', 'subtype': 'cash', 'side': 'debit', 'units': '1.25',
         'valuation_amount': '1.25', 'commodity_code': f'C{index:02d}', 'cash_flow_category': 'other'}
        for index in range(32)])


def test_month_to_date_large_summary_is_whole_and_not_an_eight_thousand_character_excerpt(monkeypatch):
    report = month_to_date_fixture()
    configured(monkeypatch, records={WORKSPACE: ['month-to-date:2026-08-18']})
    fake_fc(monkeypatch, report=report)
    result = adapter.read_evidence(WORKSPACE, ['month-to-date:2026-08-18'])[0]
    assert len(result['text']) > 8000
    assert json.loads(result['text'].split('\n', 1)[1]) == report
    assert 'private' not in result['text']


@pytest.mark.parametrize('mutation', ['extra-field', 'private-currency', 'wrong-day', 'wrong-window',
    'closed-period', 'external-complete', 'unrecorded-zero', 'float-money', 'bool-count',
    'made-up-comparison', 'duplicate-currency', 'null-period', 'bad-revision', 'blocked-with-totals'])
def test_month_to_date_wire_refuses_private_inconsistent_or_unjustified_completeness(monkeypatch, mutation):
    report = month_to_date_fixture()
    if mutation == 'extra-field': report['description'] = 'PRIVATE SENTINEL'
    if mutation == 'private-currency': report['period']['currencies'][0]['accountName'] = 'PRIVATE SENTINEL'
    if mutation == 'wrong-day': report['asOf'] = '2026-08-17'
    if mutation == 'wrong-window': report['windowEndExclusive'] = '2026-09-01'
    if mutation == 'closed-period': report['periodStatus'] = 'complete'
    if mutation == 'external-complete': report['coverage']['externalCompleteness'] = 'complete'
    if mutation == 'unrecorded-zero': report['coverage']['unrecordedDays'] = 'zero'
    if mutation == 'float-money': report['period']['currencies'][0]['income'] = 0.0
    if mutation == 'bool-count': report['period']['postedEntryCount'] = True
    if mutation == 'made-up-comparison': report['period']['currencies'][0]['incomeChange'] = '0'
    if mutation == 'duplicate-currency': report['period']['currencies'].append(deepcopy(report['period']['currencies'][0]))
    if mutation == 'null-period': report['period'] = None
    if mutation == 'bad-revision': report['revision'] = 'PRIVATE SENTINEL'
    if mutation == 'blocked-with-totals': report['status'] = 'blocked'
    configured(monkeypatch, records={WORKSPACE: ['month-to-date:2026-08-18']})
    fake_fc(monkeypatch, report=report)
    with pytest.raises(adapter.FcUnavailable, match='invalid month-to-date summary'):
        adapter.read_evidence(WORKSPACE, ['month-to-date:2026-08-18'])


@pytest.mark.parametrize('record', ['month-to-date:2026-02-29', 'month-to-date:2026-08-1',
    'month-to-date:9999-12-31', 'month-to-date:*', 'month-to-date:2026-08-18:extra'])
def test_invalid_month_to_date_record_never_sends_http(monkeypatch, record):
    configured(monkeypatch, records={WORKSPACE: [record]})
    seen = fake_fc(monkeypatch)
    with pytest.raises((ValueError, adapter.FcUnavailable)):
        adapter.read_evidence(WORKSPACE, [record])
    assert seen == []
