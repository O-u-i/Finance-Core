"""Deterministic, summary-only review of three calendar months.

Cash movements and recognized income/expenses are different axes. No source
names, transaction descriptions, implicit FX or completeness claims escape.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import hashlib
import json
import re

from finance_core.ledger import decimal_add, decimal_sub
from finance_core.models_v2 import canonical_decimal

CALCULATION_VERSION = "monthly-review-v1"
METRICS = ("cashInflow", "cashOutflow", "cashNet", "income", "expenses",
    "netIncome", "cashAdjustment", "incomeAdjustment", "expenseAdjustment")


def month_window(month: str) -> tuple[list[str], str, str]:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("Month must be YYYY-MM and include two preceding calendar months.")
    year, number = map(int, month.split("-"))
    ordinal = year * 12 + number - 1
    if year < 1 or ordinal < 14 or ordinal >= 9999 * 12 + 11:
        raise ValueError("Month is outside the supported calendar range.")
    months = [f"{value // 12:04d}-{value % 12 + 1:02d}" for value in range(ordinal - 2, ordinal + 1)]
    next_month = f"{(ordinal + 1) // 12:04d}-{(ordinal + 1) % 12 + 1:02d}-01"
    return months, months[0] + "-01", next_month


def monthly_review(month: str, entries: list[dict], postings: list[dict], *, exclude_entry_ids: set[str] | None = None) -> dict:
    months, start, end = month_window(month)
    invalid, selected = [], []
    for entry in entries:
        value = entry["date"]
        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) or date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except (ValueError, TypeError):
            invalid.append(entry)
            continue
        if start <= value < end and entry['id'] not in (exclude_entry_ids or set()):
            selected.append(entry)
    report = {"schemaVersion": 1, "calculationVersion": CALCULATION_VERSION,
        "month": month, "windowStart": start, "windowEndExclusive": end,
        "status": "blocked" if invalid else "ready", "months": [],
        "coverage": {"ledgerCalculation": "blocked" if invalid else "complete",
            "externalCompleteness": "unknown", "accountClassification": "current-account-definitions",
            "invalidDateEntryCount": len(invalid)}}
    # The stable source digest includes roles and amounts, never request time.
    relevant_ids = {entry["id"] for entry in selected}
    selected_postings = [row for row in postings if row["entry_id"] in relevant_ids]
    source = {"calculationVersion": CALCULATION_VERSION, "month": month,
        "entries": selected, "invalidDates": invalid, "postings": selected_postings}
    report["revision"] = hashlib.sha256(json.dumps(source, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    if invalid:
        return report
    by_entry = {entry["id"]: entry for entry in selected}
    values = defaultdict(lambda: {name: Decimal(0) for name in METRICS})
    cash = defaultdict(Decimal)
    other = defaultdict(int)
    for row in selected_postings:
        entry = by_entry[row["entry_id"]]
        period = entry["date"][:7]
        if row["cash_flow_category"] == "other":
            other[period] += 1
        if row["type"] == "asset" and row["subtype"].lower() == "cash":
            key = (entry["id"], row["commodity_code"])
            amount = Decimal(row["units"])
            cash[key] = decimal_add(cash[key], amount if row["side"] == "debit" else amount.copy_negate())
        if row["type"] in {"income", "expense"}:
            metric = "income" if row["type"] == "income" else "expenses"
            positive_side = "credit" if metric == "income" else "debit"
            amount = Decimal(row["valuation_amount"])
            signed = amount if row["side"] == positive_side else amount.copy_negate()
            group = values[(period, entry["balancing_commodity_code"])]
            group[metric] = decimal_add(group[metric], signed)
            if entry["reversal_of"]:
                adjustment = "incomeAdjustment" if metric == "income" else "expenseAdjustment"
                group[adjustment] = decimal_add(group[adjustment], signed)
    for (entry_id, commodity), amount in cash.items():
        entry = by_entry[entry_id]
        group = values[(entry["date"][:7], commodity)]
        group["cashNet"] = decimal_add(group["cashNet"], amount)
        metric = "cashInflow" if amount >= 0 else "cashOutflow"
        group[metric] = decimal_add(group[metric], amount.copy_abs())
        if entry["reversal_of"]:
            group["cashAdjustment"] = decimal_add(group["cashAdjustment"], amount)
    commodities = sorted({commodity for _, commodity in values})
    for index, period in enumerate(months):
        rows = []
        for commodity in commodities:
            group = values[(period, commodity)]
            group["netIncome"] = decimal_sub(group["income"], group["expenses"])
            item = {"commodityCode": commodity, **{key: canonical_decimal(value) for key, value in group.items()}}
            for metric in ("cashNet", "income", "expenses"):
                previous = values[(months[index - 1], commodity)][metric] if index else None
                item[metric + "Change"] = canonical_decimal(decimal_sub(group[metric], previous)) if previous is not None else None
            rows.append(item)
        period_entries = [entry for entry in selected if entry["date"][:7] == period]
        report["months"].append({"month": period, "postedEntryCount": len(period_entries),
            "reversalEntryCount": sum(bool(entry["reversal_of"]) for entry in period_entries),
            "otherCategoryPostingCount": other[period], "currencies": rows})
    return report
