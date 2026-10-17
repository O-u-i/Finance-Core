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


def economic_evidence(state: dict, observations: list[dict], plans: list, as_of: str, through: str, revision: str) -> dict:
    first, last = evidence_window(as_of, through)
    ledger, issues = ledger_at(state, first)
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
    totals = defaultdict(lambda: {'cashBalance': Decimal(0), 'liabilityBalance': Decimal(0), 'observedDates': set()})
    known = {'cashBalance': baseline and ledger_valid, 'liabilityBalance': baseline and ledger_valid}
    unknown_groups = set()
    cash_count = 0
    nonzero_liability = False
    for account in state['accounts']:
        if account.get('startMonth') and account['startMonth'] > as_of[:7]:
            continue
        key = 'liabilityBalance' if account['type'] == 'liability' else 'cashBalance' if account['type'] == 'asset' and account['subtype'] == 'cash' else None
        if key is None:
            continue
        if key == 'cashBalance':
            cash_count += 1
        for currency in account['allowedCommodityCodes']:
            if currency not in currencies:
                known[key] = False
                continue
            group = (account['segment'], currency)
            total = totals[group]
            valid = baseline and account['classificationConfirmed'] and ledger_valid
            if account['segment'] == 'investment':
                amount, observed = ledger['balances'].get((account['id'], currency), Decimal(0)), as_of
            else:
                row = living.get(account['id'])
                valid = valid and bool(row and row['status'] == 'confirmed' and row['observedDate'] == as_of and account.get('ownerPartyId'))
                amount = Decimal(row['amount']) if row and row['amount'] is not None else Decimal(0)
                observed = row['observedDate'] if row else None
            if key == 'liabilityBalance' and amount != 0:
                nonzero_liability = True
            if not valid:
                known[key] = False
                unknown_groups.add((group, key))
            total[key] = decimal_add(total[key], amount)
            if observed:
                total['observedDates'].add(observed)
    known['cashBalance'] = known['cashBalance'] and cash_count > 0
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
    # Plans are not contractual debt maturities. Outstanding debt without such a
    # source keeps timing unknown; a zero registered debt balance needs no maturity.
    dated_obligations = known['liabilityBalance'] and not nonzero_liability
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
        'coverage': coverage, 'missingFacts': [fact for fact, flag in facts if not coverage[flag]],
    }
