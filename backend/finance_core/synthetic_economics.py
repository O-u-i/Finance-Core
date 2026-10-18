"""Opt-in virtual economic foundation, assembled off-target then restored atomically."""
from datetime import date, datetime, timedelta, timezone

from finance_core.database import connect
from finance_core.debt_repayments import DebtRepayments
from finance_core.ledger_repository import LedgerRepository
from finance_core.models_personal import (
    BalanceRecordRequest, DebtRepaymentConfirmation, DebtRepaymentRequest,
    FinancialAccount, FinanceSettings, Party, valid_observed_date,
)
from finance_core.models_v2 import Account, Commodity, MonthlyPlanV2
from finance_core.opening_balances import OpeningBalanceRequest
from finance_core.opening_balance_operations import OpeningBalanceOperations
from finance_core.personal_finance_repository import PersonalFinanceRepository


def load_economic_demo(ledger, as_of):
    valid_observed_date(as_of)
    day = date.fromisoformat(as_of)
    if day > datetime.now(timezone(timedelta(hours=8))).date():
        raise ValueError('Synthetic economic profile requires a non-future as-of date.')
    connection = connect(':memory:')
    try:
        sample = LedgerRepository(connection)
        personal = PersonalFinanceRepository(sample)
        sample.save_commodity(Commodity(code='CNY', kind='currency', scale=2, name='Synthetic currency'), create=True)
        for identity, kind, subtype in [('cash','asset','cash'), ('debt','liability',''), ('capital','equity','')]:
            sample.save_account(Account(id=identity, code=identity, name='Synthetic ' + identity, type=kind,
                                        subtype=subtype, allowedCommodityCodes=['CNY']), create=True)
        personal.save_party(Party(id='synthetic-owner', name='Synthetic reporting person'))
        personal.save_settings(FinanceSettings(cutoverMonth=as_of[:7], reportingPartyId='synthetic-owner',
            baselineConfirmed=True, baselineEvidence='Explicit synthetic example, not historical user data.'))
        personal.save_account(FinancialAccount(id='living-cash', code='living-cash', name='Synthetic Living cash',
            type='asset', subtype='cash', allowedCommodityCodes=['CNY'], segment='living',
            balanceSource='monthly_snapshot', ownerPartyId='synthetic-owner'), create=True)
        personal.record_balance(BalanceRecordRequest(id='synthetic-balance', subjectId='living-cash', observedDate=as_of,
            currency='CNY', amount='500', confirmed=True, source='Synthetic fixture'))
        opening = OpeningBalanceOperations(sample).create_draft(OpeningBalanceRequest(
            id='synthetic-opening', date=as_of, balancingCommodityCode='CNY', equityAccountId='capital', source='Synthetic fixture',
            balances=[{'accountId':'cash','commodityCode':'CNY','amount':'10000'},
                      {'accountId':'debt','commodityCode':'CNY','amount':'1200'}]))
        posted = sample.post_draft(opening['draft']['id'], expected_updated_at=opening['updatedAt'])
        if not posted['posted']:
            raise ValueError('Synthetic opening could not be validated.')
        sample.save_monthly_plan(MonthlyPlanV2(id='synthetic-plan', kind='expense', name='Synthetic planned expense',
            amount='200', commodityCode='CNY', category='Synthetic needs', startDate=(day + timedelta(days=5)).isoformat(),
            recurringMonthly=False, dayOfMonth=1), create=True)
        debt = DebtRepayments(sample)
        quote = debt.quote('debt', 'CNY', as_of)
        arrangement = debt.create(DebtRepaymentRequest(id='synthetic-repayment', accountId='debt', currency='CNY', asOf=as_of,
            balanceRevision=quote['balanceRevision'], source='Synthetic repayment agreement', reason='Synthetic acceptance fixture',
            payments=[{'dueDate':(day + timedelta(days=7)).isoformat(),'amount':'200'},
                      {'dueDate':(day + timedelta(days=35)).isoformat(),'amount':'1000'}]))
        debt.confirm(arrangement['id'], DebtRepaymentConfirmation(expectedRevision=1,
            expectedBalanceRevision=arrangement['balanceRevision'], confirmed=True))
        ledger.restore_backup(sample.create_backup(format_version=3))
    finally:
        connection.close()
    return {'loaded': True, 'profile': 'economic-evidence', 'asOf': as_of}
