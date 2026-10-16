"""Existing ledger read projections; not the month-end personal balance sheet."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from finance_core.ledger import decimal_add, decimal_mul, decimal_sub, decimal_sum, normal_balance, quantize
from finance_core.models_v2 import LivingSnapshotV2, canonical_decimal

if TYPE_CHECKING:
    from finance_core.ledger_repository import LedgerRepository


def account_flows(repo: LedgerRepository) -> list[dict[str, Any]]:
    accounts = {item.id: item for item in repo.list_accounts()}
    groups: dict[tuple[str, str], dict[str, Decimal | int]] = defaultdict(
        lambda: {"debit": Decimal(0), "credit": Decimal(0), "count": 0}
    )
    rows = repo.connection.execute(
        "SELECT p.account_id,p.commodity_code,p.side,p.units,e.date "
        "FROM postings_v2 p JOIN journal_entries_v2 e ON e.id=p.entry_id"
    ).fetchall()
    dates: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        group = groups[(row["account_id"], row["commodity_code"])]
        group[row["side"]] = decimal_add(group[row["side"]], Decimal(row["units"]))
        group["count"] += 1
        dates[(row["account_id"], row["commodity_code"])].append(row["date"])
    output = []
    for (account_id, commodity), values in sorted(groups.items()):
        account = accounts[account_id]
        debit, credit = values["debit"], values["credit"]
        output.append({
            "accountId": account_id,
            "accountCode": account.code,
            "accountName": account.name,
            "accountType": account.type,
            "commodityCode": commodity,
            "debit": canonical_decimal(debit),
            "credit": canonical_decimal(credit),
            "balance": canonical_decimal(normal_balance(account.type, debit, credit)),
            "count": values["count"],
            "firstPostingDate": min(dates[(account_id, commodity)]),
            "lastPostingDate": max(dates[(account_id, commodity)]),
        })
    return output


def account_postings(repo: LedgerRepository, account_id: str, commodity: str, offset: int, limit: int) -> dict[str, Any]:
    """Read immutable entry dates and exact units; never invent a posting clock."""
    account = repo.get_account(account_id)
    if account is None or repo.get_commodity(commodity) is None:
        raise LookupError("Account or commodity was not found.")
    rows = repo.connection.execute(
        "SELECT p.id,p.entry_id,e.date,p.side,p.units FROM postings_v2 p "
        "JOIN journal_entries_v2 e ON e.id=p.entry_id "
        "WHERE p.account_id=? AND p.commodity_code=? ORDER BY e.date,e.id,p.id LIMIT ? OFFSET ?",
        (account_id, commodity, limit, offset),
    ).fetchall()
    count = repo.connection.execute(
        "SELECT COUNT(*) FROM postings_v2 WHERE account_id=? AND commodity_code=?", (account_id, commodity)
    ).fetchone()[0]
    return {"data": [{"postingId": row["id"], "entryId": row["entry_id"], "postingDate": row["date"],
                      "debit": row["units"] if row["side"] == "debit" else "0",
                      "credit": row["units"] if row["side"] == "credit" else "0"} for row in rows],
            "accountId": account_id, "commodityCode": commodity, "count": count,
            "offset": offset, "limit": limit, "hasMore": offset + len(rows) < count, "readOnly": True}


def holdings(repo: LedgerRepository) -> list[dict[str, Any]]:
    rows = repo.connection.execute(
        "SELECT * FROM lots_v2 ORDER BY commodity_code,acquired_date,id"
    ).fetchall()
    result = []
    for row in rows:
        if Decimal(row["remaining_units"]) <= 0:
            continue
        quote = repo.connection.execute(
            "SELECT * FROM price_quotes_v2 WHERE commodity_code=? AND quote_commodity_code=? ORDER BY as_of DESC,id DESC LIMIT 1",
            (row["commodity_code"], row["cost_commodity_code"]),
        ).fetchone()
        market_value = None
        unrealized = None
        if quote:
            cost_commodity = repo.get_commodity(row["cost_commodity_code"])
            assert cost_commodity is not None
            market_value_decimal = quantize(decimal_mul(Decimal(row["remaining_units"]), Decimal(quote["price"])), cost_commodity.scale)
            market_value = canonical_decimal(market_value_decimal)
            unrealized = canonical_decimal(decimal_sub(market_value_decimal, Decimal(row["remaining_cost"])))
        result.append({
            "lotId": row["id"],
            "accountId": row["account_id"],
            "commodityCode": row["commodity_code"],
            "acquiredDate": row["acquired_date"],
            "originalUnits": row["original_units"],
            "remainingUnits": row["remaining_units"],
            "originalCost": row["original_cost"],
            "remainingCost": row["remaining_cost"],
            "costCommodityCode": row["cost_commodity_code"],
            "latestPrice": quote["price"] if quote else None,
            "priceAsOf": quote["as_of"] if quote else None,
            "marketValue": market_value,
            "unrealizedPnL": unrealized,
        })
    return result


def dashboard(repo: LedgerRepository) -> dict[str, Any]:
    flows = repo.account_flows()
    holdings = repo.holdings()
    cash: dict[str, Decimal] = defaultdict(Decimal)
    for flow in flows:
        account = repo.get_account(flow["accountId"])
        if account and account.type == "asset" and account.subtype.lower() == "cash":
            cash[flow["commodityCode"]] = decimal_add(cash[flow["commodityCode"]], Decimal(flow["balance"]))
    holding_cost: dict[str, Decimal] = defaultdict(Decimal)
    holding_market: dict[str, Decimal] = defaultdict(Decimal)
    missing_prices: dict[str, int] = defaultdict(int)
    realized: dict[str, Decimal] = defaultdict(Decimal)
    for item in holdings:
        currency = item["costCommodityCode"]
        holding_cost[currency] = decimal_add(holding_cost[currency], Decimal(item["remainingCost"]))
        if item["marketValue"] is None:
            missing_prices[currency] += 1
        else:
            holding_market[currency] = decimal_add(holding_market[currency], Decimal(item["marketValue"]))
    realized_rows = repo.connection.execute(
        "SELECT p.side,p.valuation_amount,e.balancing_commodity_code FROM postings_v2 p JOIN journal_entries_v2 e ON e.id=p.entry_id JOIN accounts_v2 a ON a.id=p.account_id WHERE a.type='income' AND lower(a.subtype) IN ('realized-gain','investment-gain')"
    ).fetchall()
    for row in realized_rows:
        amount = Decimal(row["valuation_amount"])
        realized[row["balancing_commodity_code"]] = decimal_add(realized[row["balancing_commodity_code"]], amount if row["side"] == "credit" else amount.copy_negate())
    currencies = sorted(set(cash) | set(holding_cost) | set(holding_market) | set(realized))
    summaries = []
    for currency in currencies:
        summaries.append({
            "commodityCode": currency,
            "cash": canonical_decimal(cash[currency]),
            "holdingCostBasis": canonical_decimal(holding_cost[currency]),
            "holdingMarketValue": canonical_decimal(holding_market[currency]),
            "bookValue": canonical_decimal(decimal_add(cash[currency], holding_cost[currency])),
            "marketValue": canonical_decimal(decimal_add(cash[currency], holding_market[currency])),
            "unrealizedPnL": canonical_decimal(decimal_sub(holding_market[currency], holding_cost[currency])),
            "realizedPnL": canonical_decimal(realized[currency]),
            "missingPriceCount": missing_prices[currency],
        })
    return {
        "entryCount": repo.connection.execute("SELECT COUNT(*) FROM journal_entries_v2").fetchone()[0],
        "draftCount": repo.connection.execute("SELECT COUNT(*) FROM journal_drafts_v2 WHERE status='draft'").fetchone()[0],
        "openLotCount": len(holdings),
        "commoditySummaries": summaries,
        "formulas": {
            "accountBalance": "asset/expense: debit-credit; liability/equity/income: credit-debit",
            "holdingCostBasis": "sum(open lot remainingCost)",
            "holdingMarketValue": "sum(open lot remainingUnits * latest explicit price quote)",
        },
        "assumptions": [
            "Decimal strings are authoritative.",
            "No implicit FX conversion or external market data is used.",
        ],
    }


def financial_statements(repo: LedgerRepository) -> list[dict[str, Any]]:
    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    rows = repo.connection.execute(
        "SELECT p.side,p.valuation_amount,e.balancing_commodity_code,a.type FROM postings_v2 p JOIN journal_entries_v2 e ON e.id=p.entry_id JOIN accounts_v2 a ON a.id=p.account_id"
    ).fetchall()
    for row in rows:
        amount = Decimal(row["valuation_amount"])
        debit = amount if row["side"] == "debit" else Decimal(0)
        credit = amount if row["side"] == "credit" else Decimal(0)
        totals[(row["balancing_commodity_code"], row["type"])] = decimal_add(totals[(row["balancing_commodity_code"], row["type"])], normal_balance(row["type"], debit, credit))
    currencies = sorted({key[0] for key in totals})
    return [{
        "commodityCode": currency,
        "assets": canonical_decimal(totals[(currency, "asset")]),
        "liabilities": canonical_decimal(totals[(currency, "liability")]),
        "equity": canonical_decimal(totals[(currency, "equity")]),
        "income": canonical_decimal(totals[(currency, "income")]),
        "expenses": canonical_decimal(totals[(currency, "expense")]),
        "netIncome": canonical_decimal(decimal_sub(totals[(currency, "income")], totals[(currency, "expense")])),
    } for currency in currencies]


def cash_flow(repo: LedgerRepository) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    rows = repo.connection.execute(
        "SELECT p.side,p.units,p.commodity_code,p.cash_flow_category,a.type,a.subtype FROM postings_v2 p JOIN accounts_v2 a ON a.id=p.account_id WHERE a.type='asset' AND lower(a.subtype)='cash'"
    ).fetchall()
    for row in rows:
        value = Decimal(row["units"]) if row["side"] == "debit" else Decimal(row["units"]).copy_negate()
        groups[(row["commodity_code"], row["cash_flow_category"])] = decimal_add(groups[(row["commodity_code"], row["cash_flow_category"])], value)
    return [
        {"commodityCode": commodity, "category": category, "amount": canonical_decimal(value)}
        for (commodity, category), value in sorted(groups.items())
    ]


def reconciliation(repo: LedgerRepository) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    unbalanced = []
    for row in repo.connection.execute("SELECT id FROM journal_entries_v2"):
        postings = repo.connection.execute("SELECT side,valuation_amount FROM postings_v2 WHERE entry_id=?", (row[0],)).fetchall()
        debit = decimal_sum(Decimal(item["valuation_amount"]) for item in postings if item["side"] == "debit")
        credit = decimal_sum(Decimal(item["valuation_amount"]) for item in postings if item["side"] == "credit")
        if debit != credit:
            unbalanced.append(row[0])
    invalid_lots = []
    for lot in repo.connection.execute("SELECT * FROM lots_v2"):
        movements = repo.connection.execute(
            "SELECT action,units,cost FROM lot_movements_v2 WHERE lot_id=?", (lot["id"],)
        ).fetchall()
        acquire_count = sum(1 for item in movements if item["action"] == "acquire")
        units = Decimal(lot["original_units"])
        cost = Decimal(lot["original_cost"])
        for movement in movements:
            if movement["action"] == "dispose":
                units = decimal_sub(units, Decimal(movement["units"]))
                cost = decimal_sub(cost, Decimal(movement["cost"]))
            elif movement["action"] == "restore":
                units = decimal_add(units, Decimal(movement["units"]))
                cost = decimal_add(cost, Decimal(movement["cost"]))
            elif movement["action"] == "reverse-acquire":
                units = decimal_sub(units, Decimal(movement["units"]))
                cost = decimal_sub(cost, Decimal(movement["cost"]))
        if (
            acquire_count != 1
            or units != Decimal(lot["remaining_units"])
            or cost != Decimal(lot["remaining_cost"])
            or units < 0
            or cost < 0
        ):
            invalid_lots.append(lot["id"])
    checks.append({
        "id": "entry-balance",
        "status": "pass" if not unbalanced else "error",
        "detail": "All posted entries balance exactly." if not unbalanced else f"Unbalanced entries: {len(unbalanced)}",
    })
    checks.append({
        "id": "lot-conservation",
        "status": "pass" if not invalid_lots else "error",
        "detail": "Lot movements reconcile exactly to every open balance." if not invalid_lots else f"Invalid lots: {len(invalid_lots)}",
    })
    fk = repo.connection.execute("PRAGMA foreign_key_check").fetchall()
    checks.append({
        "id": "foreign-keys",
        "status": "pass" if not fk else "error",
        "detail": "Foreign-key check passed." if not fk else f"Foreign-key violations: {len(fk)}",
    })
    missing_prices = sum(1 for item in repo.holdings() if item["latestPrice"] is None)
    checks.append({
        "id": "price-availability",
        "status": "pass" if missing_prices == 0 else "warning",
        "detail": "All open lots have an explicit price quote." if missing_prices == 0 else f"Open lots without a price: {missing_prices}",
    })
    return {"status": "error" if any(item["status"] == "error" for item in checks) else "pass", "checks": checks}


def world(repo: LedgerRepository) -> dict[str, Any]:
    living: dict[str, Decimal] = defaultdict(Decimal)
    income: dict[str, Decimal] = defaultdict(Decimal)
    expense: dict[str, Decimal] = defaultdict(Decimal)
    for item in repo.list_living_accounts():
        living[item.commodity_code] = decimal_add(living[item.commodity_code], Decimal(item.balance))
    for item in repo.list_monthly_plans():
        target = income if item.kind == "income" else expense
        target[item.commodity_code] = decimal_add(target[item.commodity_code], Decimal(item.amount))
    market = {
        item["commodityCode"]: Decimal(item["holdingMarketValue"])
        for item in repo.dashboard()["commoditySummaries"]
    }
    currencies = sorted(set(living) | set(income) | set(expense) | set(market))
    grouped: dict[str, list[LivingSnapshotV2]] = defaultdict(list)
    for item in repo.list_living_snapshots():
        grouped[item.recorded_at].append(item)
    latest: dict[str, tuple[str, Decimal]] = {}
    series: dict[str, list[dict[str, str]]] = defaultdict(list)
    for recorded_at in sorted(grouped):
        for item in grouped[recorded_at]:
            latest[item.account_id] = (item.commodity_code, Decimal(item.balance))
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for commodity, value in latest.values():
            totals[commodity] = decimal_add(totals[commodity], value)
        for commodity, value in totals.items():
            previous = Decimal(series[commodity][-1]["value"]) if series[commodity] else value
            series[commodity].append({
                "recordedAt": recorded_at,
                "value": canonical_decimal(value),
                "delta": canonical_decimal(decimal_sub(value, previous)),
            })
    return {
        "commoditySummaries": [{
            "commodityCode": commodity,
            "livingBalance": canonical_decimal(living[commodity]),
            "investmentMarketValue": canonical_decimal(market.get(commodity, Decimal(0))),
            "combinedValue": canonical_decimal(decimal_add(living[commodity], market.get(commodity, Decimal(0)))),
            "expectedIncome": canonical_decimal(income[commodity]),
            "expectedExpense": canonical_decimal(expense[commodity]),
            "expectedNet": canonical_decimal(decimal_sub(income[commodity], expense[commodity])),
        } for commodity in currencies],
        "balanceSeries": [
            {"commodityCode": commodity, "points": points} for commodity, points in sorted(series.items())
        ],
    }
