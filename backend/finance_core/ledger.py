from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext
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
    with localcontext() as context:
        context.prec = max(28, len(value.as_tuple().digits), value.adjusted() + scale + 2)
        return value.quantize(quantum, rounding=ROUND_HALF_EVEN)


def decimal_add(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(28, max(left.adjusted(), right.adjusted()) - min(left.as_tuple().exponent, right.as_tuple().exponent) + 3)
        return left + right


def decimal_sub(left: Decimal, right: Decimal) -> Decimal:
    return decimal_add(left, right.copy_negate())


def decimal_mul(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(28, len(left.as_tuple().digits) + len(right.as_tuple().digits) + 1)
        return left * right


def quantize_ratio(numerator: Decimal, denominator: Decimal, scale: int) -> Decimal:
    """Round an exact rational allocation once, using the existing half-even rule."""
    top, top_divisor = numerator.as_integer_ratio()
    bottom, bottom_divisor = denominator.as_integer_ratio()
    if not bottom:
        raise ZeroDivisionError("Allocation denominator must be nonzero.")
    signed_top = top * bottom_divisor * (10 ** scale)
    divisor = top_divisor * bottom
    negative = (signed_top < 0) != (divisor < 0)
    whole, remainder = divmod(abs(signed_top), abs(divisor))
    if remainder * 2 > abs(divisor) or (remainder * 2 == abs(divisor) and whole % 2):
        whole += 1
    return Decimal((int(negative), tuple(int(digit) for digit in str(whole)), -scale))


def decimal_sum(values: Iterable[Decimal]) -> Decimal:
    result = Decimal(0)
    for value in values:
        result = decimal_add(result, value)
    return result


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

        amount = quantize(decimal_mul(units, rate), balancing.scale)
        if posting.side == "debit":
            debit_total = decimal_add(debit_total, amount)
        else:
            credit_total = decimal_add(credit_total, amount)
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

    difference = quantize(decimal_sub(debit_total, credit_total), balancing.scale)
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
    return decimal_sub(debit, credit) if account_type in {"asset", "expense"} else decimal_sub(credit, debit)


def sum_decimal(values: Iterable[str]) -> str:
    return canonical_decimal(decimal_sum(Decimal(value) for value in values))

