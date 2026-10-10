"""Explicitly confirmed balanced-row grouping for the CSV adapter."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from finance_core.ledger import decimal_add
from finance_core.models_v2 import JournalEntryDraft, PostingDraft, V2Model


class AccountingRow(V2Model):
    id: str = Field(min_length=1)
    date: str
    description: str = ""
    reference: str = ""
    postings: list[PostingDraft] = Field(min_length=1, max_length=200)


class AccountingRowsRequest(V2Model):
    rows: list[AccountingRow] = Field(min_length=1, max_length=10000)
    grouping_confirmed: Literal[True] = Field(alias="groupingConfirmed")
    date_policy: Literal["same-date", "first-row"] = Field(default="same-date", alias="datePolicy")

    @field_validator("grouping_confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Grouping confirmation must be the JSON boolean true.")
        return value


def balanced_drafts(request: AccountingRowsRequest) -> list[JournalEntryDraft]:
    drafts, group, balances = [], [], {}
    for index, row in enumerate(request.rows):
        try:
            if date.fromisoformat(row.date).isoformat() != row.date:
                raise ValueError()
        except ValueError as error:
            raise ValueError(f"CSV row {index + 2} has an invalid calendar date.") from error
        if group and request.date_policy == "same-date" and group[0].date != row.date:
            raise ValueError("A balanced group crosses source dates. Explicitly choose the first-row date policy or correct the source.")
        group.append(row)
        for posting in row.postings:
            if posting.valuation_rate is not None or posting.lot_action is not None:
                raise ValueError("Balanced-row mapping accepts currency postings without inferred rates or lot actions.")
            amount = Decimal(posting.units)
            code = posting.commodity_code
            balances[code] = decimal_add(balances.get(code, Decimal(0)), amount if posting.side == "debit" else amount.copy_negate())
        if any(balances.values()):
            continue
        if len(balances) != 1:
            raise ValueError("Mixed-currency groups need explicit valuation rates in the standard FC format.")
        description = next((item.description.strip() for item in group if item.description.strip()), "")
        postings = [posting.model_copy(update={"memo": " · ".join(filter(None, [posting.memo,
            f"Source date: {item.date}", item.description, item.reference]))}) for item in group for posting in item.postings]
        drafts.append(JournalEntryDraft(id=group[0].id, date=group[0].date, description=description,
            reference=group[0].reference, source="accounting-csv-balanced", balancingCommodityCode=next(iter(balances)), postings=postings))
        group, balances = [], {}
    if group:
        raise ValueError("CSV has trailing unbalanced rows. No drafts were imported.")
    return drafts
