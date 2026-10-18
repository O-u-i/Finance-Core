"""Pure, bounded gross balances and planned outflows; never personal affordability."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from finance_core.ledger import decimal_add
from finance_core.models_v2 import canonical_decimal
from finance_core.monthly_plans import monthly_plan_report
from finance_core.personal_finance import ledger_at, month_end
from finance_core.recorded_balances import calculate_recorded_balances


def evidence_window(as_of: str, through: str) -> tuple[date, date]:
    first, last = date.fromisoformat(as_of), date.fromisoformat(through)
    if first.isoformat() != as_of or last.isoformat() != through or not 0 < (last - first).days <= 366:
        raise ValueError('Economic evidence requires ISO dates and a future horizon of 1 to 366 days.')
    return first, last


def balance_facts(state: dict, observations: list[dict], as_of: str) -> tuple[list[dict], bool]:
    """One balance selection for summaries and the explicit debt-review workflow."""
    ledger, issues = ledger_at(state, date.fromisoformat(as_of))
    currencies = {value['code'] for value in state['commodities'] if value['kind'] == 'currency'}
    baseline = bool(state['settings'] and state['settings']['baselineConfirmed']
                    and state['settings']['cutoverMonth'] <= as_of[:7] and not state['unmappedLegacyLiving'])
    ledger_valid = not any(issue['code'] in {'INVALID_POSTED_DATE', 'UNREGISTERED_ACCOUNT', 'POSTING_SOURCE_CONFLICT'} for issue in issues)
    # A confirmed month-end observation has an actual boundary; never carry it forward.
    dated = []
    for value in observations:
        if value['kind'] != 'balance':
            continue
        day = value.get('observedDate') or month_end(value['month']).isoformat()
        if day <= as_of:
            dated.append({**value, 'observedDate': day})
    # Retired accounts cannot hide an unsettled balance just by ending their purpose.
    living = calculate_recorded_balances(as_of[:7], [{**a, 'endMonth': None} for a in state['accounts']], dated)
    living = {value['accountId']: value for value in living['accounts']}
    facts = []
    for account in state['accounts']:
        if account.get('startMonth') and account['startMonth'] > as_of[:7]:
            continue
        key = 'liabilityBalance' if account['type'] == 'liability' else 'cashBalance' if account['type'] == 'asset' and account['subtype'] == 'cash' else None
        if key is None:
            continue
        for currency in account['allowedCommodityCodes']:
            valid = baseline and account['classificationConfirmed'] and ledger_valid and currency in currencies
            if account['segment'] == 'investment':
                amount, observed = ledger['balances'].get((account['id'], currency), Decimal(0)), as_of
            else:
                row = living.get(account['id'])
                valid = valid and bool(row and row['status'] == 'confirmed' and row['observedDate'] == as_of and account.get('ownerPartyId'))
                amount = Decimal(row['amount']) if row and row['amount'] is not None else Decimal(0)
                observed = row['observedDate'] if row else None
            facts.append({'accountId': account['id'], 'currency': currency, 'segment': account['segment'],
                          'key': key, 'known': valid, 'amount': amount, 'observedDate': observed})
    return facts, baseline and ledger_valid


def economic_evidence(state: dict, observations: list[dict], plans: list, as_of: str, through: str, revision: str,
                      repayments: list[dict] = (), balance_revision: str = '') -> dict:
    first, last = evidence_window(as_of, through)
    facts, baseline = balance_facts(state, observations, as_of)
    currencies = {value['code'] for value in state['commodities'] if value['kind'] == 'currency'}
    known = {key: baseline and all(fact['known'] for fact in facts if fact['key'] == key)
             for key in ('cashBalance', 'liabilityBalance')}
    known['cashBalance'] = known['cashBalance'] and any(fact['key'] == 'cashBalance' for fact in facts)
    totals = defaultdict(lambda: {'cashBalance': Decimal(0), 'liabilityBalance': Decimal(0), 'observedDates': set()})
    unknown_groups = set()
    for fact in facts:
        group, key = (fact['segment'], fact['currency']), fact['key']
        totals[group][key] = decimal_add(totals[group][key], fact['amount'])
        if not fact['known']:
            unknown_groups.add((group, key))
        if fact['observedDate']:
            totals[group]['observedDates'].add(fact['observedDate'])
    outflows = defaultdict(lambda: {'amount': Decimal(0), 'count': 0})
    month = first.year * 12 + first.month - 1
    final_month = last.year * 12 + last.month - 1
    while month <= final_month:
        period = f'{month // 12:04d}-{month % 12 + 1:02d}'
        for item in monthly_plan_report(plans, period)['occurrences']:
            if item['kind'] == 'expense' and as_of < item['dueDate'] <= through:
                if item['currency'] not in currencies:
                    raise ValueError('Economic evidence requires registered currency plans.')
                group = outflows[(item['dueDate'], item['currency'])]
                group['amount'] = decimal_add(group['amount'], Decimal(item['amount']))
                group['count'] += 1
        month += 1
    # A forecast is never a debt maturity. Only an explicit confirmed arrangement
    # for the unchanged recorded balance can establish timing for that balance.
    confirmed = [value for value in repayments if value['status'] == 'confirmed']
    superseded = {value.get('supersedes') for value in confirmed}
    active = {(value['accountId'], value['currency']): value for value in confirmed if value['id'] not in superseded}
    dated_obligations = known['liabilityBalance']
    debt_dates = defaultdict(lambda: {'amount': Decimal(0), 'count': 0})
    outside = defaultdict(lambda: {'amount': Decimal(0), 'count': 0})
    for fact in facts:
        if fact['key'] != 'liabilityBalance' or fact['amount'] == 0:
            continue
        record = active.get((fact['accountId'], fact['currency']))
        if not (fact['known'] and fact['amount'] > 0 and record and record['asOf'] == as_of
                and record['balanceRevision'] == balance_revision and Decimal(record['balance']) == fact['amount']):
            dated_obligations = False
            continue
        for payment in record['payments']:
            day, currency = payment['dueDate'], record['currency']
            target = debt_dates[(day, currency)] if day <= through else outside[currency]
            target['amount'] = decimal_add(target['amount'], Decimal(payment['amount']))
            target['count'] += 1
    coverage = {'cashStocks': known['cashBalance'], 'liabilityBalances': known['liabilityBalance'],
                'datedObligations': dated_obligations, 'externalCompleteness': 'unknown',
                'currenciesCombined': False, 'personalAvailabilityAssessed': False}
    facts = [('cash_stocks', 'cashStocks'), ('liability_balances', 'liabilityBalances'), ('dated_obligations', 'datedObligations')]
    return {
        'schemaVersion': 1, 'calculationVersion': 'economic-evidence-v1', 'asOf': as_of, 'through': through,
        'revision': revision, 'balanceBasis': 'gross-registered-accounts', 'planBasis': 'planned-only-not-contractual-maturity',
        'balances': [{'segment': segment, 'currency': currency,
                      **{key: None if ((segment, currency), key) in unknown_groups else canonical_decimal(value[key]) for key in ('cashBalance', 'liabilityBalance')},
                      'observedDates': sorted(value['observedDates'])}
                     for (segment, currency), value in sorted(totals.items())],
        'plannedOutflows': [{'dueDate': day, 'currency': currency, 'amount': canonical_decimal(value['amount']), 'count': value['count']}
                            for (day, currency), value in sorted(outflows.items())],
        'debtBasis': 'confirmed-current-balance-only-future-charges-unknown',
        # Overdue dates are retained verbatim, not shifted into the future.
        'debtRepayments': [{'dueDate': day, 'currency': currency, 'amount': canonical_decimal(value['amount']), 'count': value['count']}
                           for (day, currency), value in sorted(debt_dates.items())],
        'debtOutsideHorizon': [{'currency': currency, 'amount': canonical_decimal(value['amount']), 'count': value['count']}
                               for currency, value in sorted(outside.items())],
        'coverage': coverage, 'missingFacts': [fact for fact, flag in facts if not coverage[flag]],
    }
