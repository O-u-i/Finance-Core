from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finance_core.models_v2 import (
    Account,
    Commodity,
    JournalEntryDraft,
    LivingAccountV2,
    LivingSnapshotV2,
    LotAllocation,
    MonthlyPlanV2,
    PriceQuote,
    RecurringEntryRule,
)
from finance_core.models_personal import DebtRepaymentRecord, Money, ObservedDate


class ContractModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class FlexibleContractModel(ContractModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ErrorIssue(ContractModel):
    path: str
    message: str


class ErrorDetail(ContractModel):
    code: str
    message: str
    request_id: str = Field(alias="requestId")
    issues: list[ErrorIssue] | None = None


class ErrorResponse(ContractModel):
    error: ErrorDetail


STANDARD_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    401: {
        "model": ErrorResponse,
        "description": "Authentication is required (AUTH_REQUIRED).",
    },
    403: {
        "model": ErrorResponse,
        "description": "The actor lacks the required ledger scope (TOKEN_SCOPE_DENIED).",
    },
    404: {
        "model": ErrorResponse,
        "description": "The Workspace or requested resource was not found (WORKSPACE_NOT_FOUND or RESOURCE_NOT_FOUND).",
    },
    409: {
        "model": ErrorResponse,
        "description": "The Workspace is archived, undo conflicts, or resource state conflicts (WORKSPACE_ARCHIVED, UNDO_CONFLICT, or RESOURCE_CONFLICT).",
    },
    410: {
        "model": ErrorResponse,
        "description": "The undo opportunity has expired (UNDO_EXPIRED).",
    },
    422: {
        "model": ErrorResponse,
        "description": "The request does not match the contract (INVALID_REQUEST).",
    },
}


BEARER_OR_SESSION_SECURITY = [{"BearerAccessToken": []}, {"SessionCookie": []}]
SESSION_SECURITY = [{"SessionCookie": []}]


class HealthResponse(ContractModel):
    status: Literal["ok"]
    service: Literal["finance-core"]
    service_version: str = Field(alias="serviceVersion")
    api_version: str = Field(alias="apiVersion")
    ledger_schema_version: int = Field(alias="ledgerSchemaVersion")
    registry_schema_version: int = Field(alias="registrySchemaVersion")
    supported_api_versions: list[str] = Field(alias="supportedApiVersions")
    capabilities: list[str]
    build_commit: str | None = Field(alias="buildCommit")
    release_commit: str | None = Field(alias="releaseCommit")


class Me(ContractModel):
    id: str
    display_name: str = Field(alias="displayName")
    status: Literal["active"]
    actor_kind: Literal["session", "token"] = Field(alias="actorKind")


class MeResponse(ContractModel):
    data: Me


class CurrentAccessToken(ContractModel):
    token_id: str = Field(alias="tokenId")
    actor_kind: Literal["token"] = Field(alias="actorKind")
    status: Literal["active"]
    workspace_ids: list[str] = Field(alias="workspaceIds")
    scopes: list[Literal["ledger:read", "ledger:write"]]
    expires_at: str | None = Field(alias="expiresAt")


class CurrentAccessTokenResponse(ContractModel):
    data: CurrentAccessToken


class Workspace(ContractModel):
    id: str
    slug: str
    display_name: str = Field(alias="displayName")
    kind: Literal["personal", "sandbox"]
    status: Literal["active", "archived", "quarantined"]
    owner_user_id: str = Field(alias="ownerUserId")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class UndoOperation(ContractModel):
    operation_id: str = Field(alias="operationId")
    undo_token: str = Field(alias="undoToken")
    expires_at: str = Field(alias="expiresAt")
    workspace_id: str | None = Field(alias="workspaceId")
    operation_type: str = Field(alias="operationType")


class WorkspaceListResponse(ContractModel):
    data: list[Workspace]


class WorkspaceMutationResponse(ContractModel):
    data: Workspace
    undo: UndoOperation


class Holding(ContractModel):
    lot_id: str = Field(alias="lotId")
    account_id: str = Field(alias="accountId")
    commodity_code: str = Field(alias="commodityCode")
    acquired_date: str = Field(alias="acquiredDate")
    original_units: str = Field(alias="originalUnits")
    remaining_units: str = Field(alias="remainingUnits")
    original_cost: str = Field(alias="originalCost")
    remaining_cost: str = Field(alias="remainingCost")
    cost_commodity_code: str = Field(alias="costCommodityCode")
    latest_price: str | None = Field(alias="latestPrice")
    price_as_of: str | None = Field(alias="priceAsOf")
    market_value: str | None = Field(alias="marketValue")
    unrealized_pnl: str | None = Field(alias="unrealizedPnL")


class HoldingsResponse(ContractModel):
    data: list[Holding]
    read_only: Literal[True] = Field(alias="readOnly")
    workspace_id: str | None = Field(default=None, alias="workspaceId")


class HoldingResponse(ContractModel):
    data: Holding
    read_only: Literal[True] = Field(alias="readOnly")
    workspace_id: str | None = Field(default=None, alias="workspaceId")


class LedgerResponse(FlexibleContractModel):
    """Named response boundary for heterogeneous deterministic ledger operations."""

    data: Any | None = None
    workspace_id: str | None = Field(default=None, alias="workspaceId")


class LivingAccountDeleteResponse(FlexibleContractModel):
    data: Any
    deleted_snapshot_count: int = Field(alias="deletedSnapshotCount", ge=0)
    undo: UndoOperation
    workspace_id: str | None = Field(default=None, alias="workspaceId")


class WorkspaceLedgerResponse(ContractModel):
    workspace_id: str = Field(alias="workspaceId")


MonthlyAmount = Annotated[str, Field(pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")]


class MonthlyReviewCurrency(ContractModel):
    commodity_code: str = Field(alias="commodityCode")
    cash_inflow: MonthlyAmount = Field(alias="cashInflow")
    cash_outflow: MonthlyAmount = Field(alias="cashOutflow")
    cash_net: MonthlyAmount = Field(alias="cashNet")
    income: MonthlyAmount
    expenses: MonthlyAmount
    net_income: MonthlyAmount = Field(alias="netIncome")
    cash_adjustment: MonthlyAmount = Field(alias="cashAdjustment")
    income_adjustment: MonthlyAmount = Field(alias="incomeAdjustment")
    expense_adjustment: MonthlyAmount = Field(alias="expenseAdjustment")
    cash_net_change: MonthlyAmount | None = Field(alias="cashNetChange")
    income_change: MonthlyAmount | None = Field(alias="incomeChange")
    expenses_change: MonthlyAmount | None = Field(alias="expensesChange")


class MonthlyReviewMonth(ContractModel):
    month: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    posted_entry_count: int = Field(alias="postedEntryCount", ge=0)
    reversal_entry_count: int = Field(alias="reversalEntryCount", ge=0)
    other_category_posting_count: int = Field(alias="otherCategoryPostingCount", ge=0)
    currencies: list[MonthlyReviewCurrency]


class MonthlyReviewCoverage(ContractModel):
    ledger_calculation: Literal["complete", "blocked"] = Field(alias="ledgerCalculation")
    external_completeness: Literal["unknown"] = Field(alias="externalCompleteness")
    account_classification: Literal["current-account-definitions"] = Field(alias="accountClassification")
    invalid_date_entry_count: int = Field(alias="invalidDateEntryCount", ge=0)


class MonthlyReview(ContractModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    calculation_version: Literal["monthly-review-v1"] = Field(alias="calculationVersion")
    month: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    window_start: str = Field(alias="windowStart")
    window_end_exclusive: str = Field(alias="windowEndExclusive")
    status: Literal["ready", "blocked"]
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    months: list[MonthlyReviewMonth] = Field(max_length=3)
    coverage: MonthlyReviewCoverage


class MonthlyReviewResponse(WorkspaceLedgerResponse):
    data: MonthlyReview
    read_only: Literal[True] = Field(alias="readOnly")


class MonthToDateCoverage(MonthlyReviewCoverage):
    activity_basis: Literal['posted-journal-only'] = Field(alias='activityBasis')
    unrecorded_days: Literal['unknown'] = Field(alias='unrecordedDays')


class MonthToDateReview(ContractModel):
    schema_version: Literal[1] = Field(alias='schemaVersion')
    calculation_version: Literal['month-to-date-v1'] = Field(alias='calculationVersion')
    month: str = Field(pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$')
    as_of: str = Field(alias='asOf')
    window_start: str = Field(alias='windowStart')
    window_end_exclusive: str = Field(alias='windowEndExclusive')
    period_status: Literal['partial'] = Field(alias='periodStatus')
    status: Literal['ready', 'blocked']
    revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    period: MonthlyReviewMonth | None
    coverage: MonthToDateCoverage


class MonthToDateReviewResponse(WorkspaceLedgerResponse):
    data: MonthToDateReview
    read_only: Literal[True] = Field(alias='readOnly')


class EconomicBalance(ContractModel):
    segment: Literal['investment', 'living']
    currency: str
    cash_balance: MonthlyAmount | None = Field(alias='cashBalance')
    liability_balance: MonthlyAmount | None = Field(alias='liabilityBalance')
    observed_dates: list[str] = Field(alias='observedDates')


class PlannedOutflow(ContractModel):
    due_date: str = Field(alias='dueDate')
    currency: str
    amount: MonthlyAmount
    count: int = Field(ge=1)


class EconomicCoverage(ContractModel):
    cash_stocks: bool = Field(alias='cashStocks', strict=True)
    liability_balances: bool = Field(alias='liabilityBalances', strict=True)
    dated_obligations: bool = Field(alias='datedObligations', strict=True)
    external_completeness: Literal['unknown'] = Field(alias='externalCompleteness')
    currencies_combined: Literal[False] = Field(alias='currenciesCombined')
    personal_availability_assessed: Literal[False] = Field(alias='personalAvailabilityAssessed')


class DebtOutsideHorizon(ContractModel):
    currency: str
    amount: MonthlyAmount
    count: int = Field(ge=1)


class EconomicEvidence(ContractModel):
    schema_version: Literal[1] = Field(alias='schemaVersion')
    calculation_version: Literal['economic-evidence-v1'] = Field(alias='calculationVersion')
    as_of: str = Field(alias='asOf')
    through: str
    revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    balance_basis: Literal['gross-registered-accounts'] = Field(alias='balanceBasis')
    plan_basis: Literal['planned-only-not-contractual-maturity'] = Field(alias='planBasis')
    balances: list[EconomicBalance]
    planned_outflows: list[PlannedOutflow] = Field(alias='plannedOutflows')
    debt_basis: Literal['confirmed-current-balance-only-future-charges-unknown'] = Field(alias='debtBasis')
    debt_repayments: list[PlannedOutflow] = Field(alias='debtRepayments')
    debt_outside_horizon: list[DebtOutsideHorizon] = Field(alias='debtOutsideHorizon')
    coverage: EconomicCoverage
    missing_facts: list[Literal['cash_stocks', 'liability_balances', 'dated_obligations']] = Field(alias='missingFacts')


class EconomicEvidenceResponse(WorkspaceLedgerResponse):
    data: EconomicEvidence
    read_only: Literal[True] = Field(alias='readOnly')


class DebtBalanceQuote(ContractModel):
    account_id: str = Field(alias='accountId')
    currency: str
    as_of: ObservedDate = Field(alias='asOf')
    balance_revision: str = Field(alias='balanceRevision', pattern=r'^[a-f0-9]{64}$')
    known: bool = Field(strict=True)
    balance: Money | None


class DebtBalanceResponse(WorkspaceLedgerResponse):
    data: DebtBalanceQuote
    read_only: Literal[True] = Field(alias='readOnly')


class DebtRepaymentListResponse(WorkspaceLedgerResponse):
    data: list[DebtRepaymentRecord]


class DebtRepaymentResponse(WorkspaceLedgerResponse):
    data: DebtRepaymentRecord


class AccountingCsvPreviewResponse(WorkspaceLedgerResponse):
    drafts: list[JournalEntryDraft]
    read_only: Literal[True] = Field(alias="readOnly")


class ReversibleWorkspaceLedgerResponse(WorkspaceLedgerResponse):
    undo: UndoOperation | None = None


class DraftRecord(ContractModel):
    draft: JournalEntryDraft
    status: Literal["draft", "posted"]
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    posted_entry_id: str | None = Field(alias="postedEntryId")


class ValidationIssue(ContractModel):
    code: str
    severity: Literal["error", "warning"]
    path: str
    message: str
    details: dict[str, str]


class CompletedPosting(ContractModel):
    id: str
    account_id: str = Field(alias="accountId")
    side: Literal["debit", "credit"]
    units: str
    commodity_code: str = Field(alias="commodityCode")
    valuation_rate: str = Field(alias="valuationRate")
    valuation_amount: str = Field(alias="valuationAmount")
    rate_type: Literal["exchange", "price", "cost"] = Field(alias="rateType")
    memo: str
    cash_flow_category: Literal[
        "income", "expense", "investment", "financing", "transfer", "other"
    ] = Field(alias="cashFlowCategory")
    lot_action: Literal["acquire", "dispose"] | None = Field(default=None, alias="lotAction")
    lot_id: str | None = Field(default=None, alias="lotId")
    lot_allocations: list[LotAllocation] = Field(default_factory=list, alias="lotAllocations")
    action: Literal["reversal"] | None = None
    of_posting_id: str | None = Field(default=None, alias="ofPostingId")


class JournalEntry(ContractModel):
    id: str
    date: str
    description: str
    payee: str
    source: str
    reference: str
    tags: list[str]
    balancing_commodity_code: str = Field(alias="balancingCommodityCode")
    postings: list[CompletedPosting] = Field(min_length=2, max_length=200)
    posted_at: str | None = Field(default=None, alias="postedAt")
    reversal_of: str | None = Field(default=None, alias="reversalOf")
    debit_total: str | None = Field(default=None, alias="debitTotal")
    credit_total: str | None = Field(default=None, alias="creditTotal")
    difference: str | None = None


class DraftValidationResponse(WorkspaceLedgerResponse):
    valid: bool
    issues: list[ValidationIssue]
    preview: JournalEntry | None


class DraftListResponse(WorkspaceLedgerResponse):
    data: list[DraftRecord]


class DraftSingleResponse(WorkspaceLedgerResponse):
    data: DraftRecord


class DraftMutationResponse(ReversibleWorkspaceLedgerResponse):
    data: DraftRecord


class DraftDeleteResponse(ReversibleWorkspaceLedgerResponse):
    deleted: Literal[True]
    id: str


class CompletedPostingResponse(WorkspaceLedgerResponse):
    posted: Literal[True]
    entry: JournalEntry
    issues: list[ValidationIssue]


class JournalEntryListResponse(WorkspaceLedgerResponse):
    data: list[JournalEntry]


class JournalEntrySingleResponse(WorkspaceLedgerResponse):
    data: JournalEntry


class JournalEntryReversalResponse(WorkspaceLedgerResponse):
    data: JournalEntry


class CommodityRead(Commodity):
    in_use: bool | None = Field(default=None, alias='inUse', description='Included only when includeUsage=true; configuration or retained history references this code.')


class OpeningRecords(ContractModel):
    drafts: list[DraftRecord]
    entries: list[JournalEntry]


class MonthlyActivityReview(MonthlyReview):
    calculation_version: Literal['monthly-activity-v1'] = Field(alias='calculationVersion')
    opening_entry_ids: list[str] = Field(alias='openingEntryIds')


class CommodityListResponse(WorkspaceLedgerResponse):
    data: list[CommodityRead]


class CommodityMutationResponse(ReversibleWorkspaceLedgerResponse):
    data: Commodity


class AccountListResponse(WorkspaceLedgerResponse):
    data: list[Account]


class AccountMutationResponse(ReversibleWorkspaceLedgerResponse):
    data: Account


class PriceQuoteListResponse(WorkspaceLedgerResponse):
    data: list[PriceQuote]


class PriceQuoteMutationResponse(ReversibleWorkspaceLedgerResponse):
    data: PriceQuote


class PriceQuoteDeleteResponse(ReversibleWorkspaceLedgerResponse):
    deleted: Literal[True]
    id: str


class TAccount(ContractModel):
    account_id: str = Field(alias="accountId")
    account_code: str = Field(alias="accountCode")
    account_name: str = Field(alias="accountName")
    account_type: Literal["asset", "liability", "equity", "income", "expense"] = Field(alias="accountType")
    commodity_code: str = Field(alias="commodityCode")
    debit: str
    credit: str
    balance: str
    count: int = Field(ge=0)

    first_posting_date: str | None = Field(default=None, alias="firstPostingDate")
    last_posting_date: str | None = Field(default=None, alias="lastPostingDate")


class TAccountListResponse(WorkspaceLedgerResponse):
    data: list[TAccount]


class TAccountPosting(ContractModel):
    posting_id: str = Field(alias="postingId")
    entry_id: str = Field(alias="entryId")
    posting_date: str = Field(alias="postingDate", description="Immutable Journal entry date, not a posting timestamp.")
    debit: str
    credit: str


class TAccountPostingResponse(WorkspaceLedgerResponse):
    data: list[TAccountPosting]
    account_id: str = Field(alias="accountId")
    commodity_code: str = Field(alias="commodityCode")
    count: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    has_more: bool = Field(alias="hasMore")
    read_only: Literal[True] = Field(alias="readOnly")


class DashboardCommoditySummary(ContractModel):
    commodity_code: str = Field(alias="commodityCode")
    cash: str
    holding_cost_basis: str = Field(alias="holdingCostBasis")
    holding_market_value: str = Field(alias="holdingMarketValue")
    book_value: str = Field(alias="bookValue")
    market_value: str = Field(alias="marketValue")
    unrealized_pnl: str = Field(alias="unrealizedPnL")
    realized_pnl: str = Field(alias="realizedPnL")
    missing_price_count: int = Field(alias="missingPriceCount", ge=0)


class DashboardFormulas(ContractModel):
    account_balance: str = Field(alias="accountBalance")
    holding_cost_basis: str = Field(alias="holdingCostBasis")
    holding_market_value: str = Field(alias="holdingMarketValue")


class Dashboard(ContractModel):
    entry_count: int = Field(alias="entryCount", ge=0)
    draft_count: int = Field(alias="draftCount", ge=0)
    open_lot_count: int = Field(alias="openLotCount", ge=0)
    commodity_summaries: list[DashboardCommoditySummary] = Field(alias="commoditySummaries")
    formulas: DashboardFormulas
    assumptions: list[str]


class DashboardResponse(WorkspaceLedgerResponse):
    data: Dashboard


class FinancialStatement(ContractModel):
    commodity_code: str = Field(alias="commodityCode")
    assets: str
    liabilities: str
    equity: str
    income: str
    expenses: str
    net_income: str = Field(alias="netIncome")


class FinancialStatementListResponse(WorkspaceLedgerResponse):
    data: list[FinancialStatement]


class CashFlowItem(ContractModel):
    commodity_code: str = Field(alias="commodityCode")
    category: Literal["income", "expense", "investment", "financing", "transfer", "other"]
    amount: str


class OpeningCashFlow(ContractModel):
    schema_version: Literal[1] = Field(alias='schemaVersion')
    calculation_version: Literal['opening-activity-v1'] = Field(alias='calculationVersion')
    month: str
    window_start: str = Field(alias='windowStart')
    window_end_exclusive: str = Field(alias='windowEndExclusive')
    activity: list[CashFlowItem]
    opening_effects: list[CashFlowItem] = Field(alias='openingEffects')
    external_completeness: Literal['unknown'] = Field(alias='externalCompleteness')
    revision: str


class CashFlowResponse(WorkspaceLedgerResponse):
    data: list[CashFlowItem]


class ReconciliationCheck(ContractModel):
    id: Literal["entry-balance", "lot-conservation", "foreign-keys", "price-availability"]
    status: Literal["pass", "warning", "error"]
    detail: str


class Reconciliation(ContractModel):
    status: Literal["pass", "error"]
    checks: list[ReconciliationCheck]


class ReconciliationResponse(WorkspaceLedgerResponse):
    data: Reconciliation


class LivingAccountListResponse(WorkspaceLedgerResponse):
    data: list[LivingAccountV2]


class LivingAccountMutationResponse(ReversibleWorkspaceLedgerResponse):
    data: LivingAccountV2


class LivingSnapshotListResponse(WorkspaceLedgerResponse):
    data: list[LivingSnapshotV2]


class LivingBalanceMutationResponse(ReversibleWorkspaceLedgerResponse):
    data: LivingAccountV2
    snapshot: LivingSnapshotV2


class MonthlyPlanListResponse(WorkspaceLedgerResponse):
    data: list[MonthlyPlanV2]


class MonthlyPlanMutationResponse(ReversibleWorkspaceLedgerResponse):
    data: MonthlyPlanV2


class MonthlyPlanDeleteResponse(ReversibleWorkspaceLedgerResponse):
    deleted: Literal[True]
    id: str


class PlannedCashTotal(ContractModel):
    currency: str
    inflow: str
    outflow: str
    net: str
    count: int


class PlannedCategoryTotal(PlannedCashTotal):
    category: str


class PlannedOccurrence(ContractModel):
    plan_id: str = Field(alias='planId')
    due_date: str = Field(alias='dueDate')
    amount: str
    currency: str
    category: str
    kind: Literal['income', 'expense']


class MonthlyPlanReport(ContractModel):
    month: str
    basis: Literal['planned-only']
    short_month_rule: Literal['last-valid-day'] = Field(alias='shortMonthRule')
    occurrences: list[PlannedOccurrence]
    categories: list[PlannedCategoryTotal]
    currencies: list[PlannedCashTotal]


class RecurringEntryRuleListResponse(WorkspaceLedgerResponse):
    data: list[RecurringEntryRule]


class RecurringEntryRuleMutationResponse(ReversibleWorkspaceLedgerResponse):
    data: RecurringEntryRule


class RecurringEntryRuleDeleteResponse(ReversibleWorkspaceLedgerResponse):
    deleted: Literal[True]
    id: str


class WorldCommoditySummary(ContractModel):
    commodity_code: str = Field(alias="commodityCode")
    living_balance: str = Field(alias="livingBalance")
    investment_market_value: str = Field(alias="investmentMarketValue")
    combined_value: str = Field(alias="combinedValue")
    expected_income: str = Field(alias="expectedIncome")
    expected_expense: str = Field(alias="expectedExpense")
    expected_net: str = Field(alias="expectedNet")


class WorldBalancePoint(ContractModel):
    recorded_at: str = Field(alias="recordedAt")
    value: str
    delta: str


class WorldBalanceSeries(ContractModel):
    commodity_code: str = Field(alias="commodityCode")
    points: list[WorldBalancePoint]


class World(ContractModel):
    commodity_summaries: list[WorldCommoditySummary] = Field(alias="commoditySummaries")
    balance_series: list[WorldBalanceSeries] = Field(alias="balanceSeries")


class WorldResponse(WorkspaceLedgerResponse):
    data: World


class LatestUndo(ContractModel):
    undo_token: str = Field(alias="undoToken")
    expires_at: str = Field(alias="expiresAt")


class LatestUndoResponse(WorkspaceLedgerResponse):
    data: LatestUndo | None


class LedgerUndoResponse(WorkspaceLedgerResponse):
    undone: Literal[True]
    undo_token: str = Field(alias="undoToken")
