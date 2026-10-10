"""Optional FRAG protocol 2 adapter for Finance Core API 3.2.0.

The legacy read hook remains available. FRAG loads this module; FC does not.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from urllib.parse import quote, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Query

PREFIX = "/api/plugins/finance-core"
API_VERSION = "3.2.0"
RECORD_ID = re.compile(r"^(?:(entry|draft):([A-Za-z0-9][A-Za-z0-9._-]{0,127})|monthly-review:([0-9]{4}-(?:0[1-9]|1[0-2])))$")
WORKSPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_RECORDS = 10


class FcUnavailable(Exception):
    pass


class FcIncompatible(Exception):
    pass


def _loopback_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid_port = parsed.port is not None
    except ValueError as error:
        raise FcUnavailable("Finance Core configuration is unavailable.") from error
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment or not valid_port):
        raise FcUnavailable("Finance Core configuration is unavailable.")
    return value.rstrip("/")


def _settings() -> tuple[str, str, str, dict[str, list[str]]]:
    token = os.environ.get("FINANCE_CORE_PLUGIN_READ_TOKEN", "")
    if not token or any(character.isspace() for character in token):
        raise FcUnavailable("Finance Core is not configured.")
    base = _loopback_url(os.environ.get("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:8788"))
    ui_url = _loopback_url(os.environ.get("FINANCE_CORE_PLUGIN_UI_URL", "http://127.0.0.1:5174"))
    try:
        selected = json.loads(os.environ.get("FINANCE_CORE_PLUGIN_RECORDS_JSON", "{}"))
    except ValueError as error:
        raise FcUnavailable("Finance Core selection configuration is invalid.") from error
    if not isinstance(selected, dict) or len(selected) > MAX_RECORDS:
        raise FcUnavailable("Finance Core selection configuration is invalid.")
    total = 0
    for workspace_id, ids in selected.items():
        if (not isinstance(workspace_id, str) or not WORKSPACE_ID.fullmatch(workspace_id)
                or not isinstance(ids, list)):
            raise FcUnavailable("Finance Core selection configuration is invalid.")
        if len(ids) != len(set(item for item in ids if isinstance(item, str))):
            raise FcUnavailable("Finance Core selection configuration is invalid.")
        total += len(ids)
        if any(not isinstance(item, str) or not RECORD_ID.fullmatch(item) for item in ids):
            raise FcUnavailable("Finance Core selection configuration is invalid.")
    if total > MAX_RECORDS:
        raise FcUnavailable("Finance Core selection configuration exceeds ten records.")
    return base, token, ui_url, selected


def _get(client: httpx.Client, path: str) -> dict:
    try:
        response = client.get(path)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise FcUnavailable("Finance Core is unavailable or denied the read request.") from error
    if not isinstance(payload, dict):
        raise FcUnavailable("Finance Core returned an invalid response.")
    return payload


def _client(base: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=base, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=3.0, follow_redirects=False, trust_env=False,
    )


def _check_health(client: httpx.Client) -> None:
    health = _get(client, "/api/v3/health")
    if (health.get("status") != "ok" or health.get("service") != "finance-core"
            or health.get("apiVersion") != API_VERSION):
        raise FcIncompatible("Finance Core API 3.2.0 is required.")


def _workspaces(client: httpx.Client) -> dict[str, dict]:
    payload = _get(client, "/api/v3/workspaces")
    values = payload.get("data")
    if not isinstance(values, list):
        raise FcUnavailable("Finance Core returned an invalid Workspace list.")
    return {item["id"]: item for item in values if isinstance(item, dict)
            and isinstance(item.get("id"), str) and item.get("status") == "active"}


def _monthly_report(data: object, month: str) -> dict:
    """Validate the summary-only wire shape without importing the FC runtime."""
    def shape(value: object, fields: str) -> None:
        if not isinstance(value, dict) or set(value) != set(fields.split()):
            raise FcUnavailable("Finance Core returned an invalid monthly summary.")

    def require(condition: bool) -> None:
        if not condition:
            raise FcUnavailable("Finance Core returned an invalid monthly summary.")

    shape(data, "schemaVersion calculationVersion month windowStart windowEndExclusive status revision months coverage")
    year, number = map(int, month.split("-"))
    ordinal = year * 12 + number - 1
    require(year >= 1 and ordinal >= 14 and ordinal < 9999 * 12 + 11)
    periods = [f"{value // 12:04d}-{value % 12 + 1:02d}" for value in range(ordinal - 2, ordinal + 1)]
    require(type(data["schemaVersion"]) is int and data["schemaVersion"] == 1
        and data["calculationVersion"] == "monthly-review-v1" and data["month"] == month
        and data["windowStart"] == periods[0] + "-01"
        and data["windowEndExclusive"] == f"{(ordinal + 1) // 12:04d}-{(ordinal + 1) % 12 + 1:02d}-01"
        and isinstance(data["revision"], str) and re.fullmatch(r"[a-f0-9]{64}", data["revision"]) is not None)
    coverage = data["coverage"]
    shape(coverage, "ledgerCalculation externalCompleteness accountClassification invalidDateEntryCount")
    require(coverage["externalCompleteness"] == "unknown"
        and coverage["accountClassification"] == "current-account-definitions"
        and type(coverage["invalidDateEntryCount"]) is int and coverage["invalidDateEntryCount"] >= 0
        and isinstance(data["months"], list))
    if data["status"] == "blocked":
        require(data["months"] == [] and coverage["ledgerCalculation"] == "blocked" and coverage["invalidDateEntryCount"] > 0)
        return data
    require(data["status"] == "ready" and coverage["ledgerCalculation"] == "complete"
        and coverage["invalidDateEntryCount"] == 0 and len(data["months"]) == 3)
    amounts = "cashInflow cashOutflow cashNet income expenses netIncome cashAdjustment incomeAdjustment expenseAdjustment".split()
    changes = "cashNetChange incomeChange expensesChange".split()
    previous_codes = None
    for index, period in enumerate(data["months"]):
        shape(period, "month postedEntryCount reversalEntryCount otherCategoryPostingCount currencies")
        require(period["month"] == periods[index] and isinstance(period["currencies"], list))
        for key in ("postedEntryCount", "reversalEntryCount", "otherCategoryPostingCount"):
            require(type(period[key]) is int and period[key] >= 0)
        require(period["reversalEntryCount"] <= period["postedEntryCount"])
        codes = []
        for currency in period["currencies"]:
            shape(currency, "commodityCode " + " ".join(amounts + changes))
            code = currency["commodityCode"]
            require(isinstance(code, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,23}", code) is not None)
            codes.append(code)
            for key in amounts + changes:
                value = currency[key]
                if key in changes and index == 0:
                    require(value is None)
                else:
                    require(isinstance(value, str) and re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", value) is not None)
            require(not currency["cashInflow"].startswith("-") and not currency["cashOutflow"].startswith("-"))
        require(codes == sorted(set(codes)) and (previous_codes is None or codes == previous_codes))
        previous_codes = codes
    return data


def _record(client: httpx.Client, workspace_id: str, record_id: str) -> dict:
    match = RECORD_ID.fullmatch(record_id)
    if match is None:
        raise ValueError("Invalid record ID.")
    kind, raw_id, month = match.groups()
    if month is not None:
        path = f"/api/v3/workspaces/{quote(workspace_id, safe='')}/reports/monthly-review?month={month}"
        payload = _get(client, path)
        if payload.get("workspaceId") != workspace_id or payload.get("readOnly") is not True:
            raise FcUnavailable("Finance Core returned a mismatched Workspace response.")
        return _monthly_report(payload.get("data"), month)
    resource = "journal-entries" if kind == "entry" else "journal-entry-drafts"
    path = f"/api/v3/workspaces/{quote(workspace_id, safe='')}/{resource}/{quote(raw_id, safe='')}"
    payload = _get(client, path)
    if payload.get("workspaceId") != workspace_id or not isinstance(payload.get("data"), dict):
        raise FcUnavailable("Finance Core returned a mismatched Workspace response.")
    data = payload["data"]
    item = data if kind == "entry" else data.get("draft")
    if not isinstance(item, dict) or item.get("id") != raw_id:
        raise FcUnavailable("Finance Core returned a mismatched record.")
    return data


def _label(record_id: str, data: dict) -> str:
    if record_id.startswith("monthly-review:"):
        return f"Monthly review {record_id.split(':')[1]} (three months; posted ledger only)"
    item = data if record_id.startswith("entry:") else data["draft"]
    description = item.get("description")
    return description[:120] if isinstance(description, str) and description else record_id


def _evidence(record_id: str, data: dict) -> dict[str, str]:
    if record_id.startswith("monthly-review:"):
        # A required report is atomic: the host must reject an insufficient
        # budget, never truncate its months, warnings, currencies or coverage.
        return {"recordId": record_id, "label": _label(record_id, data),
            "text": "Deterministic monthly review. External completeness is unknown.\n" + json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2),
            "revision": data["revision"]}
    item = data if record_id.startswith("entry:") else data["draft"]
    label = _label(record_id, data)
    fields = [f"Date: {item.get('date', '')}", f"Description: {label}"]
    if record_id.startswith("draft:"):
        fields.append(f"Status: {data.get('status', 'draft')}")
    else:
        fields.append(f"Posted at: {item.get('postedAt', '')}")
    postings = item.get("postings", [])
    if not isinstance(postings, list):
        raise FcUnavailable("Finance Core returned an invalid record.")
    for posting in postings[:200]:
        if not isinstance(posting, dict):
            raise FcUnavailable("Finance Core returned an invalid record.")
        fields.append("Posting: " + " | ".join(str(posting.get(key, "")) for key in
                          ("accountId", "side", "units", "commodityCode")))
    text = "\n".join(fields)[:8000]
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    revision = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {"recordId": record_id, "label": label, "text": text, "revision": revision}


def read_evidence(workspace_id: str, record_ids: list[str]) -> list[dict[str, str]]:
    if (not isinstance(workspace_id, str) or not WORKSPACE_ID.fullmatch(workspace_id)
            or not isinstance(record_ids, list) or not 1 <= len(record_ids) <= MAX_RECORDS
            or any(not isinstance(item, str) or not RECORD_ID.fullmatch(item) for item in record_ids)):
        raise ValueError("Invalid Workspace scope or record count.")
    base, token, _ui_url, selected = _settings()
    allowed = selected.get(workspace_id)
    if allowed is None or len(set(record_ids)) != len(record_ids) or any(item not in allowed for item in record_ids):
        raise ValueError("Invalid Workspace scope or record selection.")
    with _client(base, token) as client:
        _check_health(client)
        if workspace_id not in _workspaces(client):
            raise ValueError("Invalid Workspace scope.")
        return [_evidence(record_id, _record(client, workspace_id, record_id)) for record_id in record_ids]


def read_evidence_request(request: dict) -> dict:
    """Read a strict protocol 2 request through the existing selected-record path."""
    if (not isinstance(request, dict)
            or set(request) != {"protocolVersion", "pluginId", "scopeId", "recordIds"}
            or type(request.get("protocolVersion")) is not int
            or request["protocolVersion"] != 2 or request.get("pluginId") != "finance-core"):
        raise ValueError("Invalid evidence request.")
    records = read_evidence(request["scopeId"], request["recordIds"])
    return {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": request["scopeId"],
            "records": records}


def source_revision() -> str:
    """Bind read configuration without requiring credentials or accessing FC."""
    configuration = {
        "apiUrl": os.environ.get("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:8788").rstrip("/"),
        "recordsJson": os.environ.get("FINANCE_CORE_PLUGIN_RECORDS_JSON", "{}"),
    }
    canonical = json.dumps(configuration, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def list_scopes(scope_id: str | None = None) -> dict:
    """List configured read candidates, optionally restricted to one Workspace."""
    if scope_id is not None and (not isinstance(scope_id, str) or not WORKSPACE_ID.fullmatch(scope_id)):
        raise ValueError("Invalid Workspace scope.")
    base, token, _ui_url, selected = _settings()
    if scope_id is not None:
        if scope_id not in selected:
            raise ValueError("Invalid Workspace scope.")
        selected = {scope_id: selected[scope_id]}
    with _client(base, token) as client:
        _check_health(client)
        workspaces = _workspaces(client)
        result = []
        for workspace_id, ids in selected.items():
            workspace = workspaces.get(workspace_id)
            if workspace is None:
                if scope_id is not None:
                    raise ValueError("Invalid Workspace scope.")
                continue
            records = [{"id": item, "label": _label(item, {} if item.startswith("monthly-review:") else _record(client, workspace_id, item))}
                       for item in ids]
            result.append({"id": workspace_id, "label": workspace.get("displayName", workspace_id),
                           "records": records})
        return {"scopes": result}


def create_router() -> APIRouter:
    router = APIRouter(prefix=PREFIX)

    @router.get("/scopes")
    def scopes() -> dict:
        try:
            return {"workspaces": list_scopes()["scopes"]}
        except FcIncompatible as error:
            raise HTTPException(409, detail=str(error)) from error
        except FcUnavailable as error:
            raise HTTPException(503, detail=str(error)) from error

    @router.get("/dashboard")
    def dashboard(workspace_id: str = Query(alias="workspaceId")) -> dict:
        try:
            base, token, ui_url, selected = _settings()
            if workspace_id not in selected:
                raise HTTPException(404, detail="Workspace is unavailable.")
            with _client(base, token) as client:
                _check_health(client)
                if workspace_id not in _workspaces(client):
                    raise HTTPException(404, detail="Workspace is unavailable.")
                payload = _get(client, f"/api/v3/workspaces/{quote(workspace_id, safe='')}/dashboard")
                if payload.get("workspaceId") != workspace_id or not isinstance(payload.get("data"), dict):
                    raise FcUnavailable("Finance Core returned a mismatched Workspace response.")
                return {"workspaceId": workspace_id, "data": payload["data"], "readOnly": True,
                        "journalUrl": ui_url}
        except FcIncompatible as error:
            raise HTTPException(409, detail=str(error)) from error
        except FcUnavailable as error:
            raise HTTPException(503, detail=str(error)) from error

    return router
