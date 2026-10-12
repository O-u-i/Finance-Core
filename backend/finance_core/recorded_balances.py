"""Dated Living readouts, not month-end accounting or transaction classification."""
from decimal import Decimal

from finance_core.ledger import decimal_sub
from finance_core.models_v2 import canonical_decimal


def balance_order(value: dict) -> tuple[str, str, str]:
    return value['observedDate'], value['recordedAt'], value['id']


def calculate_recorded_balances(month: str, accounts: list[dict], observations: list[dict]) -> dict:
    replaced = {value.get('supersedes') for value in observations}
    active = [value for value in observations if value.get('observedDate') and value['id'] not in replaced]
    rows = []
    for account in sorted(accounts, key=lambda value: (value['code'].casefold(), value['id'])):
        if account['segment'] != 'living' or (account.get('startMonth') and month < account['startMonth']) or (account.get('endMonth') and month > account['endMonth']):
            continue
        records = sorted((value for value in active if value['subjectId'] == account['id'] and value['month'] <= month), key=balance_order)
        current = records[-1] if records and records[-1]['month'] == month else None
        previous = records[-2] if current and len(records) > 1 else None
        comparable = bool(current and previous and current['confirmed'] and previous['confirmed'])
        rows.append({
            'accountId': account['id'], 'code': account['code'], 'name': account['name'],
            'type': account['type'], 'ownerPartyId': account['ownerPartyId'],
            'currency': account['allowedCommodityCodes'][0],
            'status': ('confirmed' if current['confirmed'] else 'pending') if current else 'unknown',
            'latestRecordId': current['id'] if current else None,
            'observedDate': current['observedDate'] if current else None,
            'amount': current['amount'] if current else None,
            'previousRecordId': previous['id'] if previous else None,
            'previousDate': previous['observedDate'] if previous else None,
            'previousAmount': previous['amount'] if previous else None,
            'change': canonical_decimal(decimal_sub(Decimal(current['amount']), Decimal(previous['amount']))) if comparable else None,
        })
    return {'schemaVersion': 1, 'calculationVersion': 'recorded-balances-v1', 'month': month,
            'selectionBasis': 'latest-actual-date-within-month', 'accounts': rows,
            'coverage': {'complete': bool(rows) and all(value['status'] == 'confirmed' for value in rows),
                         'externalCompleteness': 'unknown', 'balancesAreMonthEnd': False,
                         'differencesAreIncomeOrExpenses': False, 'currenciesCombined': False}}
