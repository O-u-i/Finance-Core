import pytest

from finance_core.accounting_csv import AccountingRowsRequest, balanced_drafts
from test_v2 import client, seed


def row(index, side, amount, day="2025-03-01", description="Synthetic entry"):
    return {"id": f"csv-{index}", "date": day, "description": description, "reference": "",
        "postings": [{"id": f"p-{index}", "accountId": "cash-cny" if side == "debit" else "gain",
            "side": side, "units": amount, "commodityCode": "CNY"}]}


def request(rows, policy="same-date"):
    return AccountingRowsRequest(rows=rows, groupingConfirmed=True, datePolicy=policy)


def test_balanced_grouping_handles_many_to_one_and_preserves_source_dates():
    rows = [row(1, "debit", "9007199254740993.01"), row(2, "debit", "0.02"), row(3, "credit", "9007199254740993.03", "2025-03-02", "")]
    with pytest.raises(ValueError, match="crosses source dates"):
        balanced_drafts(request(rows))
    draft = balanced_drafts(request(rows, "first-row"))[0]
    assert draft.date == "2025-03-01" and len(draft.postings) == 3
    assert "Source date: 2025-03-02" in draft.postings[-1].memo
    assert draft.postings[0].units == "9007199254740993.01"
    assert len(balanced_drafts(request([row(1,"debit","0.1"),row(2,"credit","0.1"),row(3,"debit","0.2"),row(4,"credit","0.2")]))) == 2


def test_unbalanced_invalid_date_or_unconfirmed_rows_are_rejected():
    with pytest.raises(ValueError, match="trailing unbalanced"):
        balanced_drafts(request([row(1,"debit","1"),row(2,"credit","0.99")]))
    with pytest.raises(ValueError, match="invalid calendar date"):
        balanced_drafts(request([row(1,"debit","1","2025-02-29")]))
    for value in (False, 1, "true"):
        with pytest.raises(ValueError):
            AccountingRowsRequest(rows=[row(1,"debit","1")],groupingConfirmed=value)


def test_preview_is_read_only_and_import_still_requires_separate_request(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        payload = {"rows": [row(1,"debit","10"),row(2,"credit","10")], "groupingConfirmed": True}
        result = api.post("/api/v2/import/accounting-rows/validate", json=payload)
        assert result.status_code == 200, result.text
        assert result.json()["readOnly"] is True
        assert api.get("/api/v2/journal-entry-drafts").json()["data"] == []
        assert api.post("/api/v2/import/drafts",json={"drafts":result.json()["drafts"]}).status_code == 201
        assert len(api.get("/api/v2/journal-entry-drafts").json()["data"]) == 1
        assert api.get("/api/v2/journal-entries").json()["data"] == []
        payload["rows"][0]["postings"][0]["accountId"] = "unknown"
        assert api.post("/api/v2/import/accounting-rows/validate",json=payload).status_code == 422
