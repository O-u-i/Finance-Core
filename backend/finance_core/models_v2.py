from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def canonical_decimal(value: object) -> str:
    """Return a finite, non-exponent decimal string suitable for public contracts."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Value must be a decimal string.") from error
    if not number.is_finite():
        raise ValueError("Value must be finite.")
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


class V2Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Commodity(V2Model):
    code: str
    kind: Literal["currency", "security", "other"]
    scale: int = Field(ge=0, le=18)
    name: str
    status: Literal["active", "inactive"] = "active"

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value or len(value) > 24:
            raise ValueError("Commodity code must contain 1 to 24 characters.")
        return value


class Account(V2Model):
    id: str
    code: str
    name: str
    type: Literal["asset", "liability", "equity", "income", "expense"]
    subtype: str = ""
    allowed_commodity_codes: list[str] = Field(alias="allowedCommodityCodes", min_length=1)
    status: Literal["active", "inactive"] = "active"

    @field_validator("id", "code", "name")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("String must not be blank.")
        return value

    @field_validator("allowed_commodity_codes")
    @classmethod
    def normalize_commodities(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().upper() for value in values]
        if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("Allowed commodity codes must be nonblank and unique.")
        return normalized


class PriceQuote(V2Model):
    id: str
    commodity_code: str = Field(alias="commodityCode")
    quote_commodity_code: str = Field(alias="quoteCommodityCode")
    price: str
    as_of: str = Field(alias="asOf")
    source: str = "manual"

    @field_validator("commodity_code", "quote_commodity_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("price")
    @classmethod
    def validate_price(cls, value: object) -> str:
        result = canonical_decimal(value)
        if Decimal(result) <= 0:
            raise ValueError("Price must be greater than zero.")
        return result


class LotAllocation(V2Model):
    lot_id: str = Field(alias="lotId")
    units: str

    @field_validator("units")
    @classmethod
    def validate_units(cls, value: object) -> str:
        result = canonical_decimal(value)
        if Decimal(result) <= 0:
            raise ValueError("Allocated units must be greater than zero.")
        return result


class PostingDraft(V2Model):
    id: str
    account_id: str = Field(alias="accountId")
    side: Literal["debit", "credit"]
    units: str
    commodity_code: str = Field(alias="commodityCode")
    valuation_rate: str | None = Field(default=None, alias="valuationRate")
    rate_type: Literal["exchange", "price", "cost"] | None = Field(default=None, alias="rateType")
    memo: str = ""
    cash_flow_category: Literal[
        "income", "expense", "investment", "financing", "transfer", "other"
    ] = Field(default="other", alias="cashFlowCategory")
    lot_action: Literal["acquire", "dispose"] | None = Field(default=None, alias="lotAction")
    lot_id: str | None = Field(default=None, alias="lotId")
    lot_allocations: list[LotAllocation] = Field(default_factory=list, alias="lotAllocations")

    @field_validator("units")
    @classmethod
    def validate_units(cls, value: object) -> str:
        result = canonical_decimal(value)
        if Decimal(result) <= 0:
            raise ValueError("Posting units must be greater than zero.")
        return result

    @field_validator("valuation_rate")
    @classmethod
    def validate_rate(cls, value: object | None) -> str | None:
        if value is None:
            return None
        result = canonical_decimal(value)
        if Decimal(result) <= 0:
            raise ValueError("Valuation rate must be greater than zero.")
        return result

    @field_validator("commodity_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_lot_shape(self) -> "PostingDraft":
        if self.lot_action == "acquire" and (not self.lot_id or self.lot_allocations):
            raise ValueError("Lot acquisition requires lotId and no allocations.")
        if self.lot_action == "dispose" and (self.lot_id or not self.lot_allocations):
            raise ValueError("Lot disposal requires explicit lotAllocations.")
        if self.lot_action is None and (self.lot_id or self.lot_allocations):
            raise ValueError("Lot data requires lotAction.")
        return self


class JournalEntryDraft(V2Model):
    id: str
    date: str
    description: str
    payee: str = ""
    source: str = "manual"
    reference: str = ""
    tags: list[str] = Field(default_factory=list)
    balancing_commodity_code: str = Field(alias="balancingCommodityCode")
    postings: list[PostingDraft] = Field(min_length=2, max_length=200)

    @field_validator("id", "date", "description")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("String must not be blank.")
        return value

    @field_validator("balancing_commodity_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def unique_posting_ids(self) -> "JournalEntryDraft":
        ids = [posting.id for posting in self.postings]
        if len(ids) != len(set(ids)):
            raise ValueError("Posting ids must be unique within an entry.")
        return self


class RecurringEntryRule(V2Model):
    id: str
    name: str
    enabled: bool = True
    frequency: Literal["monthly"] = "monthly"
    day_of_month: int = Field(alias="dayOfMonth", ge=1, le=31)
    start_date: str = Field(alias="startDate")
    template: JournalEntryDraft
    generated_periods: list[str] = Field(default_factory=list, alias="generatedPeriods")


class ValidationIssue(V2Model):
    code: str
    severity: Literal["error", "warning"]
    path: str
    message: str
    details: dict[str, str] = Field(default_factory=dict)


class CompletedPosting(V2Model):
    id: str
    account_id: str = Field(alias="accountId")
    side: Literal["debit", "credit"]
    units: str
    commodity_code: str = Field(alias="commodityCode")
    valuation_rate: str = Field(alias="valuationRate")
    valuation_amount: str = Field(alias="valuationAmount")
    rate_type: Literal["exchange", "price", "cost"] = Field(alias="rateType")
    memo: str
    cash_flow_category: str = Field(alias="cashFlowCategory")
    lot_action: str | None = Field(default=None, alias="lotAction")
    lot_id: str | None = Field(default=None, alias="lotId")
    lot_allocations: list[LotAllocation] = Field(default_factory=list, alias="lotAllocations")


class CompletedEntry(V2Model):
    id: str
    date: str
    description: str
    payee: str
    source: str
    reference: str
    tags: list[str]
    balancing_commodity_code: str = Field(alias="balancingCommodityCode")
    postings: list[CompletedPosting]
    debit_total: str = Field(alias="debitTotal")
    credit_total: str = Field(alias="creditTotal")
    difference: str


class DraftImportRequest(V2Model):
    drafts: list[JournalEntryDraft] = Field(min_length=1, max_length=500)


class LivingAccountV2(V2Model):
    id: str
    name: str
    commodity_code: str = Field(alias="commodityCode")
    balance: str
    note: str = ""
    updated_at: str = Field(alias="updatedAt")

    @field_validator("commodity_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("balance")
    @classmethod
    def validate_balance(cls, value: object) -> str:
        return canonical_decimal(value)


class LivingSnapshotV2(V2Model):
    id: str
    account_id: str = Field(alias="accountId")
    balance: str
    commodity_code: str = Field(alias="commodityCode")
    recorded_at: str = Field(alias="recordedAt")

    @field_validator("commodity_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("balance")
    @classmethod
    def validate_balance(cls, value: object) -> str:
        return canonical_decimal(value)


class MonthlyPlanV2(V2Model):
    id: str
    kind: Literal["income", "expense"]
    name: str
    amount: str
    commodity_code: str = Field(alias="commodityCode")
    category: str
    recurring_monthly: bool = Field(default=True, alias="recurringMonthly")
    day_of_month: int = Field(alias="dayOfMonth", ge=1, le=31)
    start_date: str = Field(alias="startDate")
    note: str = ""

    @field_validator("commodity_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: object) -> str:
        result = canonical_decimal(value)
        if Decimal(result) < 0:
            raise ValueError("Plan amount must not be negative.")
        return result


class MutableBatchV2(V2Model):
    commodities: list[Commodity] = Field(default_factory=list, max_length=100)
    accounts: list[Account] = Field(default_factory=list, max_length=500)
    price_quotes: list[PriceQuote] = Field(default_factory=list, alias="priceQuotes", max_length=500)
    drafts: list[JournalEntryDraft] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def require_operation(self) -> "MutableBatchV2":
        if not any((self.commodities, self.accounts, self.price_quotes, self.drafts)):
            raise ValueError("Mutable batch must contain at least one resource.")
        return self
