from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class IdentifiedModel(ApiModel):
    id: str

    @field_validator("id")
    @classmethod
    def require_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("String must contain at least 1 character.")
        return value


class Transaction(IdentifiedModel):
    date: str
    account: str
    source: str
    type: Literal["Deposit", "Withdrawal", "Buy", "Sell", "Dividend", "Transfer", "Fee"]
    category: str
    asset_symbol: str = Field(alias="assetSymbol")
    amount: FiniteFloat
    currency: str
    note: str
    ref: str
    raw_data: str | None = Field(default=None, alias="rawData")
    account_code: str | None = Field(default=None, alias="accountCode")
    account_name: str | None = Field(default=None, alias="accountName")
    responsibility_center: str | None = Field(default=None, alias="responsibilityCenter")
    debit: FiniteFloat | None = None
    credit: FiniteFloat | None = None


class Holding(IdentifiedModel):
    symbol: str
    name: str
    asset_type: Literal["Stock", "ETF", "Bond", "Cash Equivalent", "Fund", "Other"] = Field(alias="assetType")
    quantity: FiniteFloat
    average_cost: FiniteFloat = Field(alias="averageCost")
    current_price: FiniteFloat = Field(alias="currentPrice")
    currency: str
    sector: str
    thesis_note: str = Field(alias="thesisNote")


class RecurringTransaction(IdentifiedModel):
    name: str
    account: str
    debit: FiniteFloat
    credit: FiniteFloat
    currency: str
    description: str
    frequency: Literal["monthly"]
    day_of_month: int = Field(alias="dayOfMonth", ge=1, le=31)
    start_date: str = Field(alias="startDate")
    enabled: bool
    generated_periods: list[str] = Field(alias="generatedPeriods")


class LivingAccount(IdentifiedModel):
    name: str
    currency: str
    balance: FiniteFloat
    note: str
    updated_at: str = Field(alias="updatedAt")


class LivingAccountSnapshot(IdentifiedModel):
    account_id: str = Field(alias="accountId")
    balance: FiniteFloat
    currency: str
    recorded_at: str = Field(alias="recordedAt")


class MonthlyPlan(IdentifiedModel):
    kind: Literal["income", "expense"]
    name: str
    amount: FiniteFloat
    currency: str
    category: str
    recurring_monthly: bool = Field(alias="recurringMonthly")
    day_of_month: int = Field(alias="dayOfMonth", ge=1, le=31)
    start_date: str = Field(alias="startDate")
    note: str


class AccountOption(ApiModel):
    account: str
    sort_order: int = Field(default=0, alias="sortOrder", ge=0)


class ResourcePatch(ApiModel):
    data: dict

    @field_validator("data")
    @classmethod
    def require_changes(cls, value: dict) -> dict:
        if not value:
            raise ValueError("At least one field is required.")
        if "id" in value:
            raise ValueError("Resource id cannot be changed.")
        return value


class UndoRequest(ApiModel):
    undo_token: str = Field(alias="undoToken")


class BatchOperation(ApiModel):
    action: Literal["create", "update", "delete", "replace"]
    resource: Literal[
        "transactions", "holdings", "recurring-rules", "living-accounts",
        "living-snapshots", "monthly-plans", "account-options",
    ]
    resource_id: str | None = Field(default=None, alias="resourceId")
    data: dict | list[str] | None = None

    @model_validator(mode="after")
    def require_shape(self) -> "BatchOperation":
        if self.resource == "account-options":
            if self.action != "replace" or not isinstance(self.data, list):
                raise ValueError("account-options requires replace with a string list.")
        elif self.action == "create" and not isinstance(self.data, dict):
            raise ValueError("create requires resource data.")
        elif self.action == "update" and (not self.resource_id or not isinstance(self.data, dict)):
            raise ValueError("update requires resourceId and data.")
        elif self.action == "delete" and not self.resource_id:
            raise ValueError("delete requires resourceId.")
        return self


class BatchRequest(ApiModel):
    operations: list[BatchOperation] = Field(min_length=1, max_length=500)


class ImportBundle(ApiModel):
    transactions: list[Transaction] = Field(default_factory=list)
    holdings: list[Holding] = Field(default_factory=list)
    account_options: list[str] = Field(default_factory=list, alias="accountOptions")
    recurring_rules: list[RecurringTransaction] = Field(default_factory=list, alias="recurringRules")
    living_accounts: list[LivingAccount] = Field(default_factory=list, alias="livingAccounts")
    living_snapshots: list[LivingAccountSnapshot] = Field(default_factory=list, alias="livingSnapshots")
    monthly_income_plans: list[MonthlyPlan] = Field(default_factory=list, alias="monthlyIncomePlans")
    monthly_expense_plans: list[MonthlyPlan] = Field(default_factory=list, alias="monthlyExpensePlans")

    @model_validator(mode="after")
    def validate_plan_kinds(self) -> "ImportBundle":
        if any(item.kind != "income" for item in self.monthly_income_plans):
            raise ValueError("monthlyIncomePlans may only contain income plans.")
        if any(item.kind != "expense" for item in self.monthly_expense_plans):
            raise ValueError("monthlyExpensePlans may only contain expense plans.")
        return self
