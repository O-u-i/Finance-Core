"""Additive API 3.4 contracts. Money is a string, never a JSON float."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from finance_core.models_v2 import canonical_decimal
from finance_core.ledger import decimal_sum


def money(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('Amounts must be decimal strings.')
    return canonical_decimal(value)


Money = Annotated[str, BeforeValidator(money)]


def valid_month(value: str) -> str:
    if not isinstance(value,str):
        raise ValueError('Month must be YYYY-MM.')
    try:
        date.fromisoformat(value + '-01')
    except ValueError as error:
        raise ValueError('Month must be a real YYYY-MM calendar month.') from error
    return value


Month = Annotated[str, BeforeValidator(valid_month), Field(pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$')]


def valid_observed_date(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('Balance date must be YYYY-MM-DD.')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError('Balance date must be a real YYYY-MM-DD calendar date.') from error
    if parsed.isoformat() != value:
        raise ValueError('Balance date must be YYYY-MM-DD.')
    return value


ObservedDate = Annotated[str, BeforeValidator(valid_observed_date)]


class PersonalModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    @field_validator('currency',check_fields=False)
    @classmethod
    def currency_code(cls,value):
        return value.strip().upper()

    @field_validator('id','name','subject_id','party_id',check_fields=False)
    @classmethod
    def text_identity(cls,value):
        if not value.strip():
            raise ValueError('Identity and name must be nonblank.')
        return value.strip()


class Party(PersonalModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    kind: Literal['person', 'organization'] = 'person'


class FinancialAccount(PersonalModel):
    id: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    type: Literal['asset', 'liability', 'equity', 'income', 'expense']
    subtype: str = ''
    allowed_commodity_codes: list[str] = Field(alias='allowedCommodityCodes', min_length=1)
    status: Literal['active', 'inactive'] = 'active'
    segment: Literal['investment', 'living']
    balance_source: Literal['ledger', 'monthly_snapshot'] = Field(alias='balanceSource')
    classification_confirmed: bool = Field(default=True, alias='classificationConfirmed')
    owner_party_id: str | None = Field(default=None, alias='ownerPartyId')
    start_month: Month | None = Field(default=None, alias='startMonth')
    end_month: Month | None = Field(default=None, alias='endMonth')
    successor_of: str | None = Field(default=None, alias='successorOf')
    legacy_living_id: str | None = Field(default=None, alias='legacyLivingId')

    @field_validator('allowed_commodity_codes')
    @classmethod
    def commodities(cls, values: list[str]) -> list[str]:
        result = [value.strip().upper() for value in values]
        if any(not value for value in result) or len(result) != len(set(result)):
            raise ValueError('Commodity codes must be nonblank and unique.')
        return result

    @model_validator(mode='after')
    def shape(self):
        if self.segment == 'living' and (self.balance_source != 'monthly_snapshot' or self.type not in {'asset', 'liability'}):
            raise ValueError('Living uses recorded asset/liability balances, not Journal postings.')
        if self.segment == 'investment' and self.balance_source != 'ledger':
            raise ValueError('Investment accounts use the ledger.')
        if self.start_month and self.end_month and self.end_month < self.start_month:
            raise ValueError('Account endMonth precedes startMonth.')
        return self


class NonFinancialAsset(PersonalModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    asset_type: str = Field(alias='assetType', min_length=1, max_length=120)
    currency: str
    purchased_date: date = Field(alias='purchasedDate')
    purchase_cost: Money = Field(alias='purchaseCost')
    owner_party_id: str = Field(alias='ownerPartyId')
    ownership_share: Money = Field(default='1', alias='ownershipShare')
    linked_account_id: str | None = Field(default=None, alias='linkedAccountId')
    disposed_month: Month | None = Field(default=None, alias='disposedMonth')
    valuation_method: Literal['manual_market_value', 'cost'] = Field(default='manual_market_value', alias='valuationMethod')
    note: str = ''

    @model_validator(mode='after')
    def amounts(self):
        if Decimal(self.purchase_cost) < 0 or not 0 <= Decimal(self.ownership_share) <= 1:
            raise ValueError('Cost must be nonnegative; ownershipShare must be between zero and one.')
        return self


class ResidualShare(PersonalModel):
    party_id: str = Field(alias='partyId')
    share: Money


class Claim(PersonalModel):
    account_id: str = Field(alias='accountId')
    party_id: str = Field(alias='partyId')
    kind: Literal['loan', 'member', 'interest', 'distribution', 'external']


class InterestAgreement(PersonalModel):
    id: str = Field(min_length=1)
    party_id: str = Field(alias='partyId')
    principal_account_id: str = Field(alias='principalAccountId')
    payable_account_id: str = Field(alias='payableAccountId')
    expense_account_id: str = Field(alias='expenseAccountId')
    monthly_amount: Money = Field(alias='monthlyAmount')
    from_month: Month = Field(alias='fromMonth')
    to_month: Month | None = Field(default=None, alias='toMonth')

    @model_validator(mode='after')
    def amount(self):
        if Decimal(self.monthly_amount) < 0 or (self.to_month and self.to_month < self.from_month):
            raise ValueError('Interest schedule is invalid.')
        return self


class InvestmentArrangement(PersonalModel):
    id: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    currency: str
    from_month: Month = Field(alias='fromMonth')
    to_month: Month | None = Field(default=None, alias='toMonth')
    residual_shares: list[ResidualShare] = Field(alias='residualShares', min_length=1)
    claims: list[Claim] = Field(default_factory=list)
    interest_agreements: list[InterestAgreement] = Field(default_factory=list, alias='interestAgreements')
    distribution_equity_account_id: str | None = Field(default=None, alias='distributionEquityAccountId')
    reason: str = Field(min_length=1)

    @model_validator(mode='after')
    def allocation(self):
        if any(Decimal(item.share) < 0 for item in self.residual_shares) or decimal_sum(Decimal(item.share) for item in self.residual_shares) != 1:
            raise ValueError('Nonnegative residual shares must sum exactly to one.')
        if len({item.party_id for item in self.residual_shares}) != len(self.residual_shares):
            raise ValueError('Residual parties must be unique.')
        if len({item.account_id for item in self.claims}) != len(self.claims):
            raise ValueError('Each liability account must have one beneficiary classification.')
        if len({item.id for item in self.interest_agreements}) != len(self.interest_agreements):
            raise ValueError('Interest agreement ids must be unique.')
        if self.to_month and self.to_month < self.from_month:
            raise ValueError('Agreement end precedes start.')
        return self


class FinanceSettings(PersonalModel):
    cutover_month: Month = Field(alias='cutoverMonth')
    reporting_party_id: str = Field(alias='reportingPartyId')
    baseline_confirmed: bool = Field(alias='baselineConfirmed')
    baseline_evidence: str = Field(alias='baselineEvidence', min_length=1)


class MonthlyObservation(PersonalModel):
    id: str = Field(min_length=1, max_length=120)
    subject_id: str = Field(alias='subjectId', min_length=1)
    month: Month
    observed_date: ObservedDate | None = Field(default=None, alias='observedDate')
    kind: Literal['balance', 'valuation', 'transfer']
    currency: str
    amount: Money | None = None
    incoming: Money | None = None
    outgoing: Money | None = None
    fees: Money = '0'
    in_transit: Money = Field(default='0', alias='inTransit')
    confirmed: bool = False
    source: str = Field(min_length=1, max_length=500)
    supersedes: str | None = None
    reason: str = ''

    @model_validator(mode='after')
    def shape(self):
        if self.observed_date and (self.kind != 'balance' or self.month != self.observed_date[:7]):
            raise ValueError('Only balances have an actual date; month must match observedDate.')
        if self.kind == 'transfer':
            if self.amount is not None or self.incoming is None or self.outgoing is None or self.subject_id != self.currency:
                raise ValueError('Transfer totals require subjectId=currency, incoming and outgoing, not amount.')
        elif self.amount is None or self.incoming is not None or self.outgoing is not None:
            raise ValueError('Balance/valuation requires amount only.')
        for value in (self.incoming, self.outgoing, self.fees, self.amount if self.kind == 'valuation' else None):
            if value is not None and Decimal(value) < 0:
                raise ValueError('Transfer and valuation amounts must be nonnegative.')
        if self.supersedes and not self.reason.strip():
            raise ValueError('Corrections require a reason.')
        return self


class BalanceRecordRequest(PersonalModel):
    id: str = Field(min_length=1, max_length=120)
    subject_id: str = Field(alias='subjectId', min_length=1)
    observed_date: ObservedDate = Field(alias='observedDate')
    currency: str
    amount: Money
    confirmed: bool = False
    source: str = Field(min_length=1, max_length=500)
    supersedes: str | None = None
    reason: str = ''


class RecordedBalance(MonthlyObservation):
    observed_date: ObservedDate = Field(alias='observedDate')
    kind: Literal['balance'] = 'balance'
    recorded_at: str = Field(alias='recordedAt')


class RecordedBalanceSummary(PersonalModel):
    account_id: str = Field(alias='accountId')
    code: str
    name: str
    type: Literal['asset', 'liability']
    owner_party_id: str = Field(alias='ownerPartyId')
    currency: str
    status: Literal['confirmed', 'pending', 'unknown']
    latest_record_id: str | None = Field(alias='latestRecordId')
    observed_date: ObservedDate | None = Field(alias='observedDate')
    amount: Money | None
    previous_record_id: str | None = Field(alias='previousRecordId')
    previous_date: ObservedDate | None = Field(alias='previousDate')
    previous_amount: Money | None = Field(alias='previousAmount')
    change: Money | None


class RecordedBalanceReport(PersonalModel):
    schema_version: Literal[1] = Field(alias='schemaVersion')
    calculation_version: Literal['recorded-balances-v1'] = Field(alias='calculationVersion')
    month: Month
    selection_basis: Literal['latest-actual-date-within-month'] = Field(alias='selectionBasis')
    accounts: list[RecordedBalanceSummary]
    coverage: dict[str, str | bool]


class CloseRequest(PersonalModel):
    month: Month
    expected_revision: str = Field(alias='expectedRevision', min_length=1)
    supersedes: str | None = None
    reason: str = Field(min_length=1)
    confirmed: Literal[True]


class ArrangementDraftRequest(PersonalModel):
    id: str = Field(min_length=1, max_length=100)
    date: date
    operation: Literal['funding', 'repayment', 'interest', 'interest_payment', 'distribution', 'distribution_payment']
    amount: Money
    party_id: str | None = Field(default=None, alias='partyId')
    cash_account_id: str | None = Field(default=None, alias='cashAccountId')
    claim_account_id: str | None = Field(default=None, alias='claimAccountId')
    interest_agreement_id: str | None = Field(default=None, alias='interestAgreementId')
    expected_revision: str = Field(alias='expectedRevision')
    special_period_confirmed: bool = Field(default=False, alias='specialPeriodConfirmed')
    reason: str = Field(min_length=1)
    from_living: bool = Field(default=False, alias='fromLiving')

    @field_validator('amount')
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError('Draft amount must be positive.')
        return value


class FinanceIssue(PersonalModel):
    code: str
    subject_id: str = Field(alias='subjectId')
    message: str


class LegacyMappingRequest(PersonalModel):
    target_account_id: str = Field(alias='targetAccountId')
    reason: str = Field(min_length=1)
    same_economic_account_confirmed: Literal[True] = Field(alias='sameEconomicAccountConfirmed')


class CurrencySummary(PersonalModel):
    currency: str
    totals: dict[str, Money | None]
    ownerships: list[dict[str, str | None]] = Field(default_factory=list)


class PersonalReport(PersonalModel):
    schema_version: Literal[1] = Field(alias='schemaVersion')
    calculation_version: Literal['personal-finance-v1'] = Field(alias='calculationVersion')
    month: Month
    as_of: str = Field(alias='asOf')
    revision: str
    valuation_basis: Literal['manual-market-and-ledger-quotes'] = Field(alias='valuationBasis')
    coverage: dict[str, str | bool]
    issues: list[FinanceIssue]
    currencies: list[CurrencySummary]


class PersonalReportResponse(PersonalModel):
    workspace_id: str = Field(alias='workspaceId')
    data: PersonalReport
