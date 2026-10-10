import json
from datetime import datetime, timedelta, timezone

import pytest

from finance_core.monthly_review import month_window, monthly_review
from test_v2 import client, seed
from test_v3 import authenticated_client, create_access_token, create_workspace


def entry(identifier, day, currency="CNY", reversal=None):
    return {"id": identifier, "date": day, "balancing_commodity_code": currency, "reversal_of": reversal}


def posting(identifier, account_type, amount, side, currency="CNY", cash=False, category="other"):
    return {"entry_id": identifier, "type": account_type, "subtype": "cash" if cash else "",
        "units": amount, "valuation_amount": amount, "side": side,
        "commodity_code": currency, "cash_flow_category": category}


def test_three_calendar_months_leap_year_and_strict_range():
    assert month_window("2024-03") == (["2024-01", "2024-02", "2024-03"], "2024-01-01", "2024-04-01")
    assert month_window("2025-01")[0] == ["2024-11", "2024-12", "2025-01"]
    for value in ("2025-1", "2025-13", "2025-00", "0000-12", "0001-02", "9999-12", "2025-01-01"):
        with pytest.raises(ValueError):
            month_window(value)


def test_cash_and_accrual_axes_loans_repayment_transfers_and_reversals():
    entries = [entry("salary", "2025-01-01"), entry("credit-purchase", "2025-02-01"),
        entry("repay", "2025-03-01"), entry("loan", "2025-03-02"),
        entry("transfer", "2025-03-03"), entry("reverse", "2025-03-04", reversal="credit-purchase")]
    postings = [posting("salary", "asset", "1000", "debit", cash=True), posting("salary", "income", "1000", "credit"),
        posting("credit-purchase", "expense", "100", "debit"), posting("credit-purchase", "liability", "100", "credit"),
        posting("repay", "asset", "100", "credit", cash=True), posting("repay", "liability", "100", "debit"),
        posting("loan", "asset", "300", "debit", cash=True), posting("loan", "liability", "300", "credit"),
        posting("transfer", "asset", "200", "debit", cash=True), posting("transfer", "asset", "200", "credit", cash=True),
        posting("reverse", "expense", "100", "credit"), posting("reverse", "liability", "100", "debit")]
    report = monthly_review("2025-03", entries, postings)
    january, february, march = [row["currencies"][0] for row in report["months"]]
    assert january["income"] == january["cashInflow"] == "1000"
    assert february["expenses"] == "100" and february["cashOutflow"] == "0"
    assert march["cashInflow"] == "300" and march["cashOutflow"] == "100"
    assert march["cashNet"] == "200" and march["income"] == "0"
    assert march["expenses"] == march["expenseAdjustment"] == "-100"
    assert march["expensesChange"] == "-200"
    assert report["months"][2]["reversalEntryCount"] == 1
    assert report["coverage"]["externalCompleteness"] == "unknown"
    assert report["coverage"]["accountClassification"] == "current-account-definitions"
    assert report["months"][2]["otherCategoryPostingCount"] == 8


def test_fx_separation_valuation_and_precision_without_float():
    entries = [entry("fx", "2025-03-01"), entry("income", "2025-03-02")]
    postings = [posting("fx", "asset", "10.25", "debit", "USD", True), posting("fx", "asset", "72.1", "credit", "CNY", True),
        {**posting("income", "income", "9007199254740993.01", "credit", "USD"), "valuation_amount": "63050394783186951.07"}]
    report = monthly_review("2025-03", entries, postings)
    cny, usd = report["months"][2]["currencies"]
    assert cny["cashOutflow"] == "72.1" and usd["cashInflow"] == "10.25"
    assert cny["income"] == "63050394783186951.07" and usd["income"] == "0"
    assert report["months"][0]["currencies"][0]["cashNetChange"] is None


def test_cash_and_income_reversal_adjustments_are_in_reversal_month():
    entries = [entry("old", "2024-12-20"), entry("reversal", "2025-03-02", reversal="old")]
    postings = [posting("reversal", "asset", "50", "credit", cash=True), posting("reversal", "income", "50", "debit")]
    row = monthly_review("2025-03", entries, postings)["months"][2]["currencies"][0]
    assert row["cashNet"] == row["cashAdjustment"] == row["incomeAdjustment"] == "-50"


@pytest.mark.parametrize("day", ["2025-02-29", "2025-13-01", "2025/01/01", "not-a-date"])
def test_unassignable_posted_date_blocks_report_without_private_identifiers(day):
    report = monthly_review("2025-03", [entry("private-id", day)], [])
    assert report["status"] == "blocked" and report["months"] == []
    assert report["coverage"]["invalidDateEntryCount"] == 1
    assert "private-id" not in json.dumps(report) and day not in json.dumps(report)


def test_revision_is_stable_and_sensitive_to_current_account_roles():
    entries = [entry("one", "2025-03-01")]
    postings = [posting("one", "asset", "1.00", "debit", cash=True)]
    first = monthly_review("2025-03", entries, postings)
    assert first == monthly_review("2025-03", entries, postings)
    assert first["revision"] != monthly_review("2025-03", entries, [{**postings[0], "subtype": "investment"}])["revision"]
    assert len(monthly_review("2025-03", [], [])["months"]) == 3


def test_scoped_read_contract_excludes_drafts_and_source_details(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        payload = {"id": "private-draft", "date": "2025-03-01", "description": "PRIVATE DESCRIPTION",
            "reference": "PRIVATE REFERENCE", "balancingCommodityCode": "CNY", "postings": [
                {"id": "p1", "accountId": "cash-cny", "side": "debit", "units": "50", "commodityCode": "CNY"},
                {"id": "p2", "accountId": "gain", "side": "credit", "units": "50", "commodityCode": "CNY"}]}
        assert api.post("/api/v2/journal-entry-drafts", json=payload).status_code == 201
        path = "/api/v2/reports/monthly-review?month=2025-03"
        assert api.get(path).json()["data"]["months"][2]["postedEntryCount"] == 0
        assert api.post("/api/v2/journal-entry-drafts/private-draft/post").status_code == 200
        response = api.get(path)
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["readOnly"] and report["workspaceId"]
        assert report["data"]["months"][2]["currencies"][0]["income"] == "50"
        assert report == api.get(path).json()
        for private in ("PRIVATE", "private-draft", "cash-cny", "Gain"):
            assert private not in response.text
        current = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m")
        assert api.get("/api/v2/reports/monthly-review", params={"month": current}).status_code == 422
        assert api.get("/api/v2/reports/monthly-review?month=2025-3").status_code == 422


def test_read_only_token_and_workspace_isolation(tmp_path):
    api = authenticated_client(tmp_path)
    try:
        one, two = create_workspace(api), create_workspace(api, "Other")
        token = create_access_token(api, [one["id"]], ["ledger:read"])
        api.cookies.clear()
        headers = {"Authorization": "Bearer " + token}
        prefix = f"/api/v3/workspaces/{one['id']}"
        assert api.get(prefix + "/reports/monthly-review?month=2025-03", headers=headers).status_code == 200
        # FC deliberately hides Vault existence from an unauthorized actor.
        assert api.get(f"/api/v3/workspaces/{two['id']}/reports/monthly-review?month=2025-03", headers=headers).status_code == 404
        assert api.post(prefix + "/journal-entry-drafts", headers=headers, json={}).status_code == 403
        assert api.get(prefix + "/reports/monthly-review?month=2025-03").status_code == 401
    finally:
        api.__exit__(None, None, None)
