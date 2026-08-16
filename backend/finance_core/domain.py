from __future__ import annotations

from collections import defaultdict
from typing import Any

from finance_core.models import Holding, LivingAccount, LivingAccountSnapshot, MonthlyPlan, Transaction


def signed_amount(item: Transaction) -> float:
    if item.debit is not None or item.credit is not None:
        return (item.debit or 0) - (item.credit or 0)
    return item.amount


def is_accounting_account(account: str) -> bool:
    return len(account) >= 5 and account[:4].isdigit() and account[4] == "-"


def is_cash_account(account: str) -> bool:
    return account.startswith(("1001-", "1002-")) or "银行存款" in account or "现金" in account


def is_volatile_holding(item: Holding) -> bool:
    stable_words = ("现金", "存款", "货币基金", "cash equivalent", "money market", "cash", "deposit")
    return not any(word in item.asset_type.lower() for word in stable_words)


def cashflow_buckets(transactions: list[Transaction]) -> list[dict[str, Any]]:
    buckets = {
        "salary": ["Salary / Main Income", 0.0, "income"],
        "partTimeA": ["Side Income A", 0.0, "income"],
        "partTimeB": ["Side Income B", 0.0, "income"],
        "partTimeC": ["Side Income C", 0.0, "income"],
        "investmentIncome": ["Investment Income", 0.0, "income"],
        "livingExpense": ["Living Expense", 0.0, "expense"],
        "investmentBuy": ["Investment Buy", 0.0, "investment"],
        "investmentSell": ["Investment Sell", 0.0, "investment"],
        "other": ["Other Cash Flow", 0.0, "neutral"],
    }
    for item in transactions:
        text = f"{item.source} {item.category} {item.account} {item.note}".lower()
        if any(word in text for word in ("工资", "主业", "salary")):
            key = "salary"
        elif any(word in text for word in ("兼职 a", "兼职a", "side income a")):
            key = "partTimeA"
        elif any(word in text for word in ("兼职 b", "兼职b", "side income b")):
            key = "partTimeB"
        elif any(word in text for word in ("兼职 c", "兼职c", "side income c")):
            key = "partTimeC"
        elif any(word in text for word in ("利息收入", "分红", "投资收益", "投资损失", "dividend", "interest income")):
            key = "investmentIncome"
        elif any(word in text for word in ("生活", "房租", "餐饮", "交通", "living", "rent")):
            key = "livingExpense"
        elif any(word in text for word in ("投资买入", "买入", "buy")):
            key = "investmentBuy"
        elif any(word in text for word in ("投资卖出", "卖出", "现金回收", "sell")):
            key = "investmentSell"
        else:
            key = "other"
        value = signed_amount(item)
        if key in {"livingExpense", "investmentBuy"}:
            value = -abs(value)
        elif key == "investmentSell":
            value = abs(value)
        elif key == "investmentIncome" and (item.account_code or "").startswith("6"):
            value = -abs(item.debit if item.debit is not None else value)
        elif key == "investmentIncome" and (item.account_code or "").startswith("4"):
            value = abs(item.credit if item.credit is not None else value)
        buckets[key][1] += value
    return [
        {"key": key, "label": values[0], "amount": values[1], "kind": values[2]}
        for key, values in buckets.items()
    ]


def account_flows(transactions: list[Transaction]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, float | int]] = defaultdict(
        lambda: {"inflow": 0.0, "outflow": 0.0, "net": 0.0, "count": 0}
    )
    for item in transactions:
        key = (item.account, item.currency.strip().upper())
        amount = signed_amount(item)
        groups[key]["inflow" if amount >= 0 else "outflow"] += abs(amount)
        groups[key]["net"] += amount
        groups[key]["count"] += 1
    return [
        {"account": account, "currency": currency, **values}
        for (account, currency), values in sorted(groups.items())
    ]


def dashboard(transactions: list[Transaction], holdings: list[Holding]) -> dict[str, Any]:
    currencies = sorted(
        {item.currency.strip().upper() for item in transactions + holdings if item.currency.strip()}
    )
    summaries = []
    for currency in currencies:
        currency_transactions = [item for item in transactions if item.currency.strip().upper() == currency]
        currency_holdings = [item for item in holdings if item.currency.strip().upper() == currency]
        has_accounting = any(is_accounting_account(item.account) for item in currency_transactions)
        cash_transactions = [item for item in currency_transactions if is_cash_account(item.account)] if has_accounting else currency_transactions
        cash_in = sum(value for item in cash_transactions if (value := signed_amount(item)) > 0)
        cash_out = sum(abs(value) for item in cash_transactions if (value := signed_amount(item)) < 0)
        cash = sum(signed_amount(item) for item in cash_transactions)
        cost = sum(item.quantity * item.average_cost for item in currency_holdings)
        market = sum(item.quantity * item.current_price for item in currency_holdings)
        largest = max((item.quantity * item.current_price for item in currency_holdings), default=0)
        volatile = sum(item.quantity * item.current_price for item in currency_holdings if is_volatile_holding(item))
        stable_holding = sum(item.quantity * item.current_price for item in currency_holdings if not is_volatile_holding(item))
        buckets = cashflow_buckets(currency_transactions)
        total_income = sum(max(0.0, item["amount"]) for item in buckets if item["kind"] == "income")
        living_expense = abs(next(item["amount"] for item in buckets if item["key"] == "livingExpense"))
        investment_buy = abs(next(item["amount"] for item in buckets if item["key"] == "investmentBuy"))
        investment_sell = next(item["amount"] for item in buckets if item["key"] == "investmentSell")
        summaries.append(
            {
                "currency": currency,
                "cashIn": cash_in,
                "cashOut": cash_out,
                "cash": cash,
                "holdingCostBasis": cost,
                "holdingMarketValue": market,
                "bookValue": cash + cost,
                "marketValue": cash + market,
                "unrealizedPnL": market - cost,
                "totalIncome": total_income,
                "livingExpense": living_expense,
                "investmentContribution": investment_buy,
                "investmentWithdrawal": investment_sell,
                "volatileAssets": volatile,
                "stableAssets": cash + stable_holding,
                "largestHoldingValue": largest,
                "concentration": (largest / market * 100) if market > 0 else 0,
                "cashflowBuckets": buckets,
            }
        )
    cash_in = sum(item["cashIn"] for item in summaries)
    cash_out = sum(item["cashOut"] for item in summaries)
    cash = sum(item["cash"] for item in summaries)
    cost = sum(item["holdingCostBasis"] for item in summaries)
    market = sum(item["holdingMarketValue"] for item in summaries)
    volatile = sum(item["volatileAssets"] for item in summaries)
    stable = sum(item["stableAssets"] for item in summaries)
    total_market = cash + market
    buckets = cashflow_buckets(transactions)
    total_income = sum(max(0.0, item["amount"]) for item in buckets if item["kind"] == "income")
    investment_income = next(item["amount"] for item in buckets if item["key"] == "investmentIncome")
    sector_groups: dict[tuple[str, str], float] = defaultdict(float)
    sector_totals: dict[str, float] = defaultdict(float)
    for item in holdings:
        currency = item.currency.strip().upper()
        value = item.quantity * item.current_price
        sector_groups[(currency, item.sector or "Unclassified")] += value
        sector_totals[currency] += value
    sector_exposures = [
        {
            "currency": currency,
            "sector": sector,
            "value": value,
            "percent": value / sector_totals[currency] * 100 if sector_totals[currency] > 0 else 0,
        }
        for (currency, sector), value in sorted(sector_groups.items())
    ]
    return {
        "transactionCount": len(transactions),
        "holdingCount": len(holdings),
        "cashIn": cash_in,
        "cashOutAbs": cash_out,
        "cash": cash,
        "holdingCostBasis": cost,
        "holdingMarketValue": market,
        "bookValue": cash + cost,
        "marketValue": total_market,
        "unrealizedPnL": market - cost,
        "marketImpact": market - cost,
        "volatileAssets": volatile,
        "stableAssets": stable,
        "exposureRatio": volatile / total_market * 100 if total_market > 0 else 0,
        "stableRatio": stable / total_market * 100 if total_market > 0 else 0,
        "concentration": max((item["concentration"] for item in summaries), default=0),
        "largestHoldingValue": max((item["largestHoldingValue"] for item in summaries), default=0),
        "totalIncome": total_income,
        "nonInvestmentIncome": total_income - max(0.0, investment_income),
        "investmentIncome": investment_income,
        "livingExpense": abs(next(item["amount"] for item in buckets if item["key"] == "livingExpense")),
        "investmentContribution": abs(next(item["amount"] for item in buckets if item["key"] == "investmentBuy")),
        "investmentWithdrawal": next(item["amount"] for item in buckets if item["key"] == "investmentSell"),
        "cashflowBuckets": buckets,
        "currencySummaries": summaries,
        "sectorExposures": sector_exposures,
        "formulas": {
            "cash": "sum(debit - credit), falling back to amount",
            "holdingCostBasis": "sum(quantity * averageCost)",
            "holdingMarketValue": "sum(quantity * currentPrice)",
            "unrealizedPnL": "holdingMarketValue - holdingCostBasis",
        },
        "assumptions": ["Currencies are grouped independently; no FX conversion is performed."],
    }


def world_metrics(
    living_accounts: list[LivingAccount],
    snapshots: list[LivingAccountSnapshot],
    plans: list[MonthlyPlan],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    living_totals: dict[str, float] = defaultdict(float)
    income_totals: dict[str, float] = defaultdict(float)
    expense_totals: dict[str, float] = defaultdict(float)
    for item in living_accounts:
        living_totals[item.currency.strip().upper()] += item.balance
    for item in plans:
        target = income_totals if item.kind == "income" else expense_totals
        target[item.currency.strip().upper()] += item.amount
    investments = {item["currency"]: item for item in metrics["currencySummaries"]}
    currencies = sorted(set(living_totals) | set(income_totals) | set(expense_totals) | set(investments))
    summaries = []
    for currency in currencies:
        investment = investments.get(currency, {})
        living = living_totals[currency]
        market = investment.get("holdingMarketValue", 0)
        cost = investment.get("holdingCostBasis", 0)
        pnl = investment.get("unrealizedPnL", 0)
        income = income_totals[currency]
        expense = expense_totals[currency]
        summary = {
            "currency": currency, "livingBalance": living, "investmentMarketValue": market,
            "combinedValue": living + market, "expectedIncome": income, "expectedExpense": expense,
            "expectedNet": income - expense, "holdingCostBasis": cost, "unrealizedPnL": pnl,
            "unrealizedReturnRate": pnl / cost * 100 if cost > 0 else 0,
        }
        if any(value != 0 for key, value in summary.items() if key != "currency"):
            summaries.append(summary)

    grouped: dict[str, list[LivingAccountSnapshot]] = defaultdict(list)
    for item in snapshots:
        grouped[item.recorded_at].append(item)
    latest: dict[str, tuple[str, float]] = {}
    points: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for recorded_at in sorted(grouped):
        for item in grouped[recorded_at]:
            latest[item.account_id] = (item.currency.strip().upper(), item.balance)
        totals: dict[str, float] = defaultdict(float)
        for currency, balance in latest.values():
            totals[currency] += balance
        for currency, value in totals.items():
            previous = points[currency][-1]["value"] if points[currency] else value
            points[currency].append({
                "recordedAt": recorded_at,
                "label": recorded_at[:10],
                "value": value,
                "delta": value - previous,
            })
    return {
        "currencySummaries": summaries,
        "balanceSeries": [{"currency": currency, "points": values} for currency, values in sorted(points.items())],
    }


def financial_statements(transactions: list[Transaction], holdings: list[Holding]) -> list[dict[str, Any]]:
    summaries = dashboard(transactions, holdings)["currencySummaries"]
    flows = account_flows(transactions)
    statements = []
    for summary in summaries:
        currency_flows = [item for item in flows if item["currency"] == summary["currency"]]
        sum_prefix = lambda prefix: sum(
            float(item["net"]) for item in currency_flows if str(item["account"]).strip().startswith(prefix)
        )
        revenue = abs(sum_prefix("4"))
        expense = abs(sum_prefix("6"))
        liability = abs(sum_prefix("2"))
        paid_in_capital = abs(sum_prefix("3"))
        net_income = revenue - expense
        statements.append(
            {
                "currency": summary["currency"],
                "operations": {
                    "operatingRevenue": revenue,
                    "operatingExpense": expense,
                    "netIncome": net_income,
                },
                "position": {
                    "cash": summary["cash"],
                    "holdingMarketValue": summary["holdingMarketValue"],
                    "totalAssets": summary["marketValue"],
                    "recordedLiabilities": liability,
                    "paidInCapital": paid_in_capital,
                    "retainedEarnings": net_income,
                },
            }
        )
    return statements


def reconciliation(transactions: list[Transaction], holdings: list[Holding]) -> dict[str, Any]:
    metrics = dashboard(transactions, holdings)
    flows = account_flows(transactions)
    flow_matches = all(
        abs(
            float(flow["net"])
            - sum(
                signed_amount(item)
                for item in transactions
                if item.account == flow["account"]
                and item.currency.strip().upper() == flow["currency"]
            )
        )
        <= 0.01
        for flow in flows
    )
    return {
        "status": "pass" if flow_matches else "error",
        "checks": [
            {
                "id": "account-flow-net",
                "status": "pass" if flow_matches else "error",
                "detail": "Account flow totals match transaction records by account and currency."
                if flow_matches
                else "At least one account flow total does not match transaction records.",
            },
            {
                "id": "finite-summary-values",
                "status": "pass",
                "detail": f"Calculated {len(metrics['currencySummaries'])} independent currency summaries.",
            },
        ],
    }
