"""Pure deterministic month-end measurement and beneficiary reconciliation.

No persistence, clock, transport, external prices or participant-specific rules.
"""
from __future__ import annotations

import re
import json
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction

from finance_core.ledger import decimal_add, decimal_mul, decimal_sub, decimal_sum, normal_balance, quantize
from finance_core.models_v2 import canonical_decimal

LOCAL = timezone(timedelta(hours=8))


def month_end(month: str) -> date:
    year, number = map(int, month.split('-'))
    return date(year, number, monthrange(year, number)[1])


def previous_month(month: str) -> str:
    return (month_end(month).replace(day=1) - timedelta(days=1)).strftime('%Y-%m')


def effective_date(value: str) -> date:
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return date.fromisoformat(value)
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Timestamp requires a timezone.')
    return stamp.astimezone(LOCAL).date()


def active_in(item: dict, month: str) -> bool:
    return (not item.get('startMonth') or item['startMonth'] <= month) and (not item.get('endMonth') or month <= item['endMonth'])


def latest_observations(observations: list[dict]) -> dict[tuple[str, str, str], dict]:
    replaced = {item['supersedes'] for item in observations if item.get('supersedes')}
    return {(item['kind'], item['subjectId'], item['month']): item for item in observations if item['id'] not in replaced}


def arrangement_for(arrangements: list[dict], currency: str, month: str) -> dict | None:
    candidates = [item for item in arrangements if item['currency'] == currency and item['fromMonth'] <= month]
    if not candidates:
        return None
    chosen = max(candidates, key=lambda item: (item['fromMonth'], item['version']))
    return chosen if not chosen.get('toMonth') or month <= chosen['toMonth'] else None


def allocate_distribution(amount: Decimal, shares: list[dict], scale: int) -> list[tuple[str, Decimal]]:
    """Largest remainder in integer currency quanta; ties follow declared party order."""
    if amount != quantize(amount, scale) or amount <= 0:
        raise ValueError('Distribution must be positive and fit currency scale.')
    ratios = [Fraction(Decimal(item['share'])) for item in shares]
    if not ratios or any(value < 0 for value in ratios) or sum(ratios) != 1:
        raise ValueError('Residual shares must be nonnegative and sum exactly to one.')
    numerator, divisor = amount.as_integer_ratio()
    quanta = numerator * 10 ** scale // divisor
    quotas = [value * quanta for value in ratios]
    allocated = [value.numerator // value.denominator for value in quotas]
    order = sorted(range(len(shares)), key=lambda index: (-(quotas[index] - allocated[index]), index))
    for index in order[:quanta - sum(allocated)]:
        allocated[index] += 1
    return [(item['partyId'], Decimal((0, tuple(map(int,str(value))), -scale))) for item, value in zip(shares,allocated)]


def ledger_at(state: dict, as_of: date) -> tuple[dict, list[dict]]:
    """Replay original posting units and immutable lot movements, not current lots."""
    issues = []
    accounts = {item['id']: item for item in state['accounts']}
    commodities = {item['code']: item for item in state['commodities']}
    entries = {}
    all_dates = {}
    for entry in state['entries']:
        try:
            day = effective_date(entry['date'])
            all_dates[entry['id']] = day
            if day <= as_of:
                entries[entry['id']] = entry
        except (ValueError, TypeError):
            issues.append({'code': 'INVALID_POSTED_DATE', 'subjectId': entry['id'], 'message': 'Posted date is unclassifiable; totals are incomplete.'})
    balances = defaultdict(Decimal)
    monthly = defaultdict(Decimal)
    cash_by_entry = defaultdict(lambda: defaultdict(Decimal))
    for posting in state['postings']:
        if posting['entry_id'] not in entries:
            continue
        account = accounts.get(posting['account_id'])
        if account is None:
            issues.append({'code': 'UNREGISTERED_ACCOUNT', 'subjectId': posting['account_id'], 'message': 'A posted account lacks unified registration.'})
            continue
        if account['segment'] != 'investment' or account['balanceSource'] != 'ledger':
            issues.append({'code': 'POSTING_SOURCE_CONFLICT', 'subjectId': account['id'], 'message': 'Journal and snapshot authority overlap.'})
            continue
        value = Decimal(posting['units'])
        signed = normal_balance(account['type'], value if posting['side'] == 'debit' else Decimal(0), value if posting['side'] == 'credit' else Decimal(0))
        key = (account['id'], posting['commodity_code'])
        balances[key] = decimal_add(balances[key], signed)
        day = all_dates[posting['entry_id']]
        if day.strftime('%Y-%m') == as_of.strftime('%Y-%m'):
            monthly[key] = decimal_add(monthly[key], signed)
        if account['type'] == 'asset' and account['subtype'] == 'cash':
            cash_by_entry[posting['entry_id']][posting['commodity_code']] = decimal_add(cash_by_entry[posting['entry_id']][posting['commodity_code']], signed)
    lots = {item['id']: item for item in state['lots']}
    replay = defaultdict(lambda: {'units': Decimal(0), 'cost': Decimal(0)})
    included = [item for item in state['movements'] if item['entry_id'] in entries]
    included.sort(key=lambda item: (all_dates[item['entry_id']], entries[item['entry_id']]['posted_at'], item['id']))
    for movement in included:
        lot = lots[movement['lot_id']]
        try:
            acquired = effective_date(lot['acquired_date'])
            if acquired > all_dates[movement['entry_id']]:
                raise ValueError('Movement before acquisition.')
        except (ValueError, TypeError):
            issues.append({'code': 'INVALID_LOT_DATE', 'subjectId': lot['id'], 'message': 'Lot acquisition or disposal chronology is invalid.'})
        sign = Decimal(1) if movement['action'] in {'acquire', 'restore'} else Decimal(-1)
        item = replay[lot['id']]
        item['units'] = decimal_add(item['units'], decimal_mul(sign, Decimal(movement['units'])))
        item['cost'] = decimal_add(item['cost'], decimal_mul(sign, Decimal(movement['cost'])))
        if item['units'] < 0 or item['cost'] < 0:
            issues.append({'code': 'NEGATIVE_HISTORICAL_LOT', 'subjectId': lot['id'], 'message': 'Historical lot units or cost became negative.'})
    lot_units = defaultdict(Decimal)
    values = defaultdict(Decimal)
    quote_rows = []
    for quote in state['quotes']:
        try:
            stamp = datetime.fromisoformat(quote['as_of'].replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                raise ValueError('Price timezone is unknown.')
            if stamp.astimezone(LOCAL).date() <= as_of:
                quote_rows.append((stamp, quote['id'], quote))
        except (ValueError, TypeError):
            issues.append({'code': 'INVALID_PRICE_DATE', 'subjectId': quote['id'], 'message': 'A price timestamp has no reliable as-of boundary.'})
    quote_rows.sort(key=lambda item: (item[0], item[1]))
    quotes = {(item['commodity_code'], item['quote_commodity_code']): item for _, _, item in quote_rows}
    for lot_id, balance in replay.items():
        lot = lots[lot_id]
        key = (lot['account_id'], lot['commodity_code'])
        lot_units[key] = decimal_add(lot_units[key], balance['units'])
        if not balance['units']:
            continue
        quote = quotes.get((lot['commodity_code'], lot['cost_commodity_code']))
        if quote is None:
            issues.append({'code': 'MISSING_AS_OF_PRICE', 'subjectId': lot_id, 'message': 'No price existed at this month end; market value is unknown.'})
            continue
        scale = commodities[lot['cost_commodity_code']]['scale']
        value = quantize(decimal_mul(balance['units'], Decimal(quote['price'])), scale)
        values[lot['cost_commodity_code']] = decimal_add(values[lot['cost_commodity_code']], value)
    for key in set(balances) | set(lot_units):
        if commodities[key[1]]['kind'] == 'security' and balances[key] != lot_units[key]:
            issues.append({'code': 'SECURITY_UNITS_MISMATCH', 'subjectId': key[0], 'message': 'Ledger security units do not match historical lot units.'})
    return {'balances': balances, 'monthly': monthly, 'securityValues': values, 'cashByEntry': cash_by_entry,
            'entries': entries, 'dates': all_dates, 'lotBalances': replay}, issues


def calculate_report(month: str, state: dict, revision: str) -> dict:
    end = month_end(month)
    ledger, issues = ledger_at(state, end)
    prior = previous_month(month)
    observations = latest_observations(state['observations'])
    owner = (state.get('settings') or {}).get('reportingPartyId')
    settings = state.get('settings') or {}
    if not settings.get('baselineConfirmed') or month < settings.get('cutoverMonth', '9999-12'):
        issues.append({'code': 'OPENING_BASELINE_UNCONFIRMED', 'subjectId': 'personal', 'message': 'Confirm a cutover month and opening financial/ownership baseline.'})
    active_assets = [item for item in state['assets'] if effective_date(item['purchasedDate']) <= end
                     and (not item.get('disposedMonth') or item['disposedMonth'] >= month)]
    linked = {item['linkedAccountId'] for item in active_assets if item.get('linkedAccountId')}
    currencies = {item['code'] for item in state['commodities'] if item['kind'] == 'currency'}
    totals = {code: defaultdict(Decimal) for code in currencies}

    def problem(code, subject, message):
        issues.append({'code': code, 'subjectId': subject, 'message': message})

    for account in state['accounts']:
        if not account.get('classificationConfirmed'):
            problem('ACCOUNT_CLASSIFICATION_PENDING', account['id'], 'Confirm the migrated account classification without rewriting history.')
        if account['segment'] == 'living':
            if account.get('endMonth') and account['endMonth'] < month and account.get('ownerPartyId') == owner and account['id'] not in linked:
                final = observations.get(('balance', account['id'], account['endMonth']))
                successor = any(item.get('successorOf') == account['id'] and active_in(item, month) for item in state['accounts'])
                if not successor and (not final or not final['confirmed'] or Decimal(final['amount']) != 0):
                    problem('ENDED_ACCOUNT_UNSETTLED', account['id'], 'An ended account has no confirmed zero closing balance or active successor. Ending is not a write-off.')
            if not active_in(account, month) or account['id'] in linked:
                continue
            if not account.get('ownerPartyId'):
                problem('LIVING_OWNER_UNKNOWN', account['id'], 'Snapshot ownership must be explicit.')
            if account.get('ownerPartyId') != owner:
                continue
            for code in account['allowedCommodityCodes']:
                current = observations.get(('balance', account['id'], month))
                opening = observations.get(('balance', account['id'], prior))
                for value, kind in ((current, 'CLOSING_BALANCE_MISSING'), (opening, 'OPENING_BALANCE_MISSING')):
                    if not value or not value['confirmed']:
                        problem(kind, account['id'], 'Missing or unconfirmed monthly balance; no carry-forward assumption was made.')
                if current and current['confirmed']:
                    key = 'livingAssets' if account['type'] == 'asset' else 'livingLiabilities'
                    totals[code][key] = decimal_add(totals[code][key], Decimal(current['amount']))
                if account['type'] == 'asset' and account['subtype'] == 'cash':
                    if current and current['confirmed']:
                        totals[code]['closingCash'] = decimal_add(totals[code]['closingCash'], Decimal(current['amount']))
                    if opening and opening['confirmed']:
                        totals[code]['openingCash'] = decimal_add(totals[code]['openingCash'], Decimal(opening['amount']))
        else:
            for code in account['allowedCommodityCodes']:
                balance = ledger['balances'].get((account['id'], code), Decimal(0))
                if code not in totals:
                    if balance and next(item for item in state['commodities'] if item['code'] == code)['kind'] != 'security':
                        problem('UNVALUED_COMMODITY', account['id'], 'A non-currency asset has no supported market valuation.')
                    continue
                key = {'asset': 'investmentAssets', 'liability': 'investmentLiabilities'}.get(account['type'])
                if key:
                    totals[code][key] = decimal_add(totals[code][key], balance)
                if account['type'] in {'income', 'expense'}:
                    key = 'investmentIncome' if account['type'] == 'income' else 'investmentExpenses'
                    totals[code][key] = decimal_add(totals[code][key], ledger['monthly'].get((account['id'], code), Decimal(0)))
    for code, value in ledger['securityValues'].items():
        totals[code]['investmentAssets'] = decimal_add(totals[code]['investmentAssets'], value)
    for asset in active_assets:
        if asset['ownerPartyId'] != owner:
            continue
        observation = observations.get(('valuation', asset['id'], month))
        if not observation or not observation['confirmed']:
            problem('ASSET_VALUATION_MISSING', asset['id'], 'Confirm a manual monthly asset valuation; book cost is not silently substituted.')
        else:
            value = decimal_mul(Decimal(observation['amount']), Decimal(asset['ownershipShare']))
            scale = next(item['scale'] for item in state['commodities'] if item['code'] == asset['currency'])
            totals[asset['currency']]['nonFinancialAssets'] = decimal_add(totals[asset['currency']]['nonFinancialAssets'], quantize(value, scale))
    ownerships = {}
    for code in sorted(currencies):
        result = totals[code]
        residual = decimal_sub(result['investmentAssets'], result['investmentLiabilities'])
        result['residualEquity'] = residual
        arrangement = arrangement_for(state['arrangements'], code, month)
        relevant = any(item['segment'] == 'investment' and code in item['allowedCommodityCodes'] for item in state['accounts']) or result['investmentAssets'] != 0
        if relevant and arrangement is None:
            problem('OWNERSHIP_UNCLASSIFIED', code, 'An effective beneficiary agreement is required for the investment pool.')
        ownerships[code] = []
        if arrangement:
            classified = {item['accountId']: item for item in arrangement['claims']}
            for account in state['accounts']:
                if account['segment'] == 'investment' and account['type'] == 'liability' and code in account['allowedCommodityCodes'] and account['id'] not in classified:
                    problem('LIABILITY_BENEFICIARY_UNKNOWN', account['id'], 'Classify every pool liability once, including external creditors.')
            shares = {item['partyId']: Decimal(item['share']) for item in arrangement['residualShares']}
            claim_totals = defaultdict(Decimal)
            for claim in arrangement['claims']:
                balance = ledger['balances'].get((claim['accountId'], code), Decimal(0))
                if balance < 0:
                    problem('CLAIM_OVERPAYMENT', claim['accountId'], 'A beneficiary claim is negative; do not silently classify excess withdrawal as repayment.')
                claim_totals[claim['partyId']] = decimal_add(claim_totals[claim['partyId']], balance)
            for party in sorted(set(shares) | set(claim_totals)):
                equity = decimal_mul(residual, shares.get(party, Decimal(0)))
                value = decimal_add(claim_totals[party], equity)
                ownerships[code].append({'partyId': party, 'claims': canonical_decimal(claim_totals[party]),
                                         'residualShare': canonical_decimal(shares.get(party, Decimal(0))),
                                         'residualValue': canonical_decimal(equity), 'economicValue': canonical_decimal(value)})
                if party == owner:
                    result['ownerInvestmentValue'] = value
            # Interest drafts are never automatically posted. Missing accrual blocks a close.
            for agreement in arrangement['interestAgreements']:
                if agreement['fromMonth'] <= month and (not agreement.get('toMonth') or month <= agreement['toMonth']):
                    tag = f"interest:{arrangement['id']}:{agreement['id']}:{month}"
                    tagged = {entry_id for entry_id, entry in ledger['entries'].items() if tag in json.loads(entry['tags_json']) and ledger['dates'][entry_id].strftime('%Y-%m') == month}
                    accrued = decimal_sum(Decimal(posting['units']) if posting['side'] == 'debit' else -Decimal(posting['units'])
                                          for posting in state['postings'] if posting['entry_id'] in tagged and posting['account_id'] == agreement['expenseAccountId'] and posting['commodity_code'] == code)
                    confirmations = [value for value in state.get('interestConfirmations', []) if value['id'] in tagged and value.get('interestAgreementId') == agreement['id']]
                    principal_changes = any(value['account_id'] == agreement['principalAccountId'] and ledger['dates'].get(value['entry_id'], date.min).strftime('%Y-%m') == month for value in state['postings'])
                    special = month in {agreement['fromMonth'], agreement.get('toMonth')} or principal_changes
                    confirmed = [value for value in confirmations if value['specialPeriodConfirmed']]
                    expected = decimal_sum(Decimal(value['amount']) for value in confirmed) if special and confirmed else Decimal(agreement['monthlyAmount'])
                    if Decimal(agreement['monthlyAmount']) and (not tagged or accrued != expected or (special and not confirmed)):
                        problem('INTEREST_ACCRUAL_REVIEW_REQUIRED', agreement['id'], 'Review the fixed interest draft and explicitly validate/post the agreed monthly accrual; reversed accruals and unconfirmed special periods are not complete.')
        expected_in = expected_out = Decimal(0)
        for entry_id, entry in ledger['entries'].items():
            if ledger['dates'][entry_id].strftime('%Y-%m') != month:
                continue
            tags = json.loads(entry['tags_json'])
            net = ledger['cashByEntry'][entry_id].get(code, Decimal(0))
            if f'personal-transfer:in:{code}' in tags:
                expected_in = decimal_sub(expected_in, net)
            if f'personal-transfer:out:{code}' in tags:
                expected_out = decimal_add(expected_out, net)
            if any(tag.startswith('personal-transfer:') for tag in tags) and len(ledger['cashByEntry'][entry_id]) > 1:
                problem('CROSS_CURRENCY_TRANSFER_REVIEW', entry_id, 'Cross-currency transfer legs require separate explicit reconciliation; no FX total is inferred.')
        transfer = observations.get(('transfer', code, month))
        living_cash = any(item['segment'] == 'living' and item.get('ownerPartyId') == owner and item['type'] == 'asset' and item['subtype'] == 'cash' and code in item['allowedCommodityCodes'] and active_in(item, month) for item in state['accounts'])
        if living_cash and (not transfer or not transfer['confirmed']):
            problem('TRANSFER_TOTALS_UNCONFIRMED', code, 'Explicitly confirm monthly cross-segment incoming/outgoing totals, including zero.')
        result['ledgerTransferIncoming'] = expected_in
        result['ledgerTransferOutgoing'] = expected_out
        if transfer and transfer['confirmed']:
            result['transferIncomingDifference'] = decimal_sub(Decimal(transfer['incoming']), expected_in)
            result['transferOutgoingDifference'] = decimal_sub(Decimal(transfer['outgoing']), expected_out)
            result['transferFees'] = Decimal(transfer['fees'])
            result['inTransit'] = Decimal(transfer['inTransit'])
            result['unexplainedCashChange'] = decimal_sub(decimal_sub(result['closingCash'], result['openingCash']), decimal_sub(Decimal(transfer['incoming']), Decimal(transfer['outgoing'])))
            if result['transferIncomingDifference'] or result['transferOutgoingDifference']:
                problem('TRANSFER_TOTALS_MISMATCH', code, 'Living totals differ from tagged posted Investment cash movements; no adjustment was generated.')
            if result['inTransit']:
                problem('IN_TRANSIT_REVIEW_REQUIRED', code, 'Cross-month funds remain in transit; review the timing separately.')
        result['knownPersonalSubtotal'] = decimal_sum([result['livingAssets'], -result['livingLiabilities'], result['nonFinancialAssets'], result['ownerInvestmentValue']])
    complete = not issues
    summaries = []
    account_codes = {item['id']: set(item['allowedCommodityCodes']) for item in state['accounts']}
    asset_codes = {item['id']: item['currency'] for item in state['assets']}
    for code in sorted(currencies):
        values = totals[code]
        for key in ('livingAssets', 'livingLiabilities', 'nonFinancialAssets', 'investmentAssets', 'investmentLiabilities',
                    'investmentIncome', 'investmentExpenses', 'closingCash', 'openingCash', 'ownerInvestmentValue', 'knownPersonalSubtotal'):
            values[key]  # Explicit known-subtotal zero is not an asserted complete observation.
        rendered = {key: canonical_decimal(value) for key, value in values.items()}
        rendered['knownInvestmentAssetSubtotal'] = rendered['investmentAssets']
        rendered['knownLivingAssetSubtotal'] = rendered['livingAssets']
        rendered['knownNonFinancialAssetSubtotal'] = rendered['nonFinancialAssets']
        currency_issues = {item['code'] for item in issues if item['subjectId'] == code or code in account_codes.get(item['subjectId'],set()) or asset_codes.get(item['subjectId']) == code}
        if {'CLOSING_BALANCE_MISSING','LIVING_OWNER_UNKNOWN'} & currency_issues:
            rendered['livingAssets'] = rendered['livingLiabilities'] = rendered['closingCash'] = None
        if 'OPENING_BALANCE_MISSING' in currency_issues:
            rendered['openingCash'] = None
        if 'ASSET_VALUATION_MISSING' in currency_issues:
            rendered['nonFinancialAssets'] = None
        if {'OWNERSHIP_UNCLASSIFIED','LIABILITY_BENEFICIARY_UNKNOWN'} & currency_issues:
            rendered['ownerInvestmentValue'] = None
        if any(item['code'] in {'MISSING_AS_OF_PRICE','SECURITY_UNITS_MISMATCH','INVALID_POSTED_DATE','INVALID_LOT_DATE','NEGATIVE_HISTORICAL_LOT','INVALID_PRICE_DATE','UNVALUED_COMMODITY','POSTING_SOURCE_CONFLICT','UNREGISTERED_ACCOUNT'} for item in issues):
            rendered['investmentAssets'] = rendered['residualEquity'] = rendered['ownerInvestmentValue'] = None
            for ownership in ownerships[code]:
                ownership['residualValue'] = ownership['economicValue'] = None
        rendered['personalNetWorth'] = rendered['knownPersonalSubtotal'] if complete else None
        if not complete:
            rendered['unexplainedCashChange'] = None
        summaries.append({'currency': code, 'totals': rendered, 'ownerships': ownerships[code]})
    return {'schemaVersion': 1, 'calculationVersion': 'personal-finance-v1', 'month': month, 'asOf': end.isoformat(),
            'revision': revision, 'valuationBasis': 'manual-market-and-ledger-quotes',
            'coverage': {'complete': complete, 'externalCompleteness': 'unknown', 'balanceChangesAreIncomeOrExpenses': False,
                         'currenciesCombined': False, 'historicalOwnershipInferred': False}, 'issues': issues, 'currencies': summaries}
