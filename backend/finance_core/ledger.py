from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN
from typing import Iterable

from finance_core.models_v2 import (
    Account,
    Commodity,
    CompletedEntry,
    CompletedPosting,
    JournalEntryDraft,
    ValidationIssue,
    canonical_decimal,
)


def quantize(value: Decimal, scale: int) -> Decimal:
    quantum = Decimal(1).scaleb(-scale)
    return value.quantize(quantum, rounding=ROUND_HALF_EVEN)


def issue(code: str, path: str, message: str, **details: object) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity="error",
        path=path,
        message=message,
        details={key: str(value) for key, value in details.items()},
    )


def complete_entry(
    draft: JournalEntryDraft,
    commodities: dict[str, Commodity],
    accounts: dict[str, Account],
) -> tuple[CompletedEntry | None, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    balancing = commodities.get(draft.balancing_commodity_code)
    if balancing is None or balancing.status != "active":
        issues.append(issue(
            "INVALID_BALANCING_COMMODITY",
            "balancingCommodityCode",
            "Balancing commodity must exist and be active.",
            commodity=draft.balancing_commodity_code,
        ))
        return None, issues

    completed: list[CompletedPosting] = []
    debit_total = Decimal(0)
    credit_total = Decimal(0)
    for index, posting in enumerate(draft.postings):
        path = f"postings.{index}"
        account = accounts.get(posting.account_id)
        commodity = commodities.get(posting.commodity_code)
        if account is None or account.status != "active":
            issues.append(issue("INVALID_ACCOUNT", f"{path}.accountId", "Account must exist and be active."))
        elif posting.commodity_code not in account.allowed_commodity_codes:
            issues.append(issue(
                "ACCOUNT_COMMODITY_NOT_ALLOWED",
                f"{path}.commodityCode",
                "Account does not allow this commodity.",
            ))
        if commodity is None or commodity.status != "active":
            issues.append(issue("INVALID_COMMODITY", f"{path}.commodityCode", "Commodity must exist and be active."))
            continue

        units = quantize(Decimal(posting.units), commodity.scale)
        if units != Decimal(posting.units):
            issues.append(issue(
                "UNITS_EXCEED_SCALE",
                f"{path}.units",
                "Units contain more fractional digits than the commodity scale allows.",
                scale=commodity.scale,
            ))

        if posting.commodity_code == balancing.code:
            if posting.valuation_rate is not None and Decimal(posting.valuation_rate) != 1:
                issues.append(issue(
                    "BASE_RATE_MUST_BE_ONE",
                    f"{path}.valuationRate",
                    "A posting in the balancing commodity must use rate 1.",
                ))
            rate = Decimal(1)
            rate_type = posting.rate_type or "exchange"
        else:
            if posting.valuation_rate is None or posting.rate_type is None:
                issues.append(issue(
                    "VALUATION_REQUIRED",
                    path,
                    "A non-balancing commodity posting requires valuationRate and rateType.",
                ))
                continue
            rate = Decimal(posting.valuation_rate)
            rate_type = posting.rate_type

        amount = quantize(units * rate, balancing.scale)
        if posting.side == "debit":
            debit_total += amount
        else:
            credit_total += amount
        completed.append(CompletedPosting(
            id=posting.id,
            accountId=posting.account_id,
            side=posting.side,
            units=canonical_decimal(units),
            commodityCode=posting.commodity_code,
            valuationRate=canonical_decimal(rate),
            valuationAmount=canonical_decimal(amount),
            rateType=rate_type,
            memo=posting.memo,
            cashFlowCategory=posting.cash_flow_category,
            lotAction=posting.lot_action,
            lotId=posting.lot_id,
            lotAllocations=posting.lot_allocations,
        ))

    difference = quantize(debit_total - credit_total, balancing.scale)
    if difference != 0:
        issues.append(issue(
            "ENTRY_NOT_BALANCED",
            "postings",
            "Debit and credit valuations must balance exactly.",
            debitTotal=canonical_decimal(debit_total),
            creditTotal=canonical_decimal(credit_total),
            difference=canonical_decimal(difference),
        ))
    if issues:
        return None, issues
    return CompletedEntry(
        id=draft.id,
        date=draft.date,
        description=draft.description,
        payee=draft.payee,
        source=draft.source,
        reference=draft.reference,
        tags=draft.tags,
        balancingCommodityCode=balancing.code,
        postings=completed,
        debitTotal=canonical_decimal(debit_total),
        creditTotal=canonical_decimal(credit_total),
        difference=canonical_decimal(difference),
    ), []


def normal_balance(account_type: str, debit: Decimal, credit: Decimal) -> Decimal:
    return debit - credit if account_type in {"asset", "expense"} else credit - debit


def sum_decimal(values: Iterable[str]) -> str:
    return canonical_decimal(sum((Decimal(value) for value in values), Decimal(0)))

