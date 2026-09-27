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
from build_frag_plugin import ARCHIVE, SOURCE, check, expected_manifest, sha256  # noqa: E402

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
        assert manifest["protocolVersion"] == 1
        assert manifest["minHostVersion"] == "1.0.0"
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
