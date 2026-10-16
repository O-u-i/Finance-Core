"""Exact forecast reporting. No postings, balance observations or external cash flows."""
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from finance_core.ledger import decimal_add, decimal_sub
from finance_core.models_v2 import MonthlyPlanV2, canonical_decimal


def monthly_plan_report(plans: list[MonthlyPlanV2], month: str) -> dict:
    first = date.fromisoformat(month + '-01')
    categories = defaultdict(lambda: {'inflow': Decimal(0), 'outflow': Decimal(0), 'count': 0})
    currencies = defaultdict(lambda: {'inflow': Decimal(0), 'outflow': Decimal(0), 'count': 0})
    occurrences = []
    for plan in plans:
        start = date.fromisoformat(plan.start_date)
        due = first.replace(day=min(plan.day_of_month, monthrange(first.year, first.month)[1])) if plan.recurring_monthly else start
        if due < start or due.isoformat()[:7] != month:
            continue
        direction = 'inflow' if plan.kind == 'income' else 'outflow'
        for group in (categories[(plan.category, plan.commodity_code)], currencies[plan.commodity_code]):
            group[direction] = decimal_add(group[direction], Decimal(plan.amount))
            group['count'] += 1
        occurrences.append({'planId': plan.id, 'dueDate': due.isoformat(), 'amount': plan.amount,
                            'currency': plan.commodity_code, 'category': plan.category, 'kind': plan.kind})

    def totals(values):
        return {key: canonical_decimal(values[key]) for key in ('inflow', 'outflow')} | {
            'net': canonical_decimal(decimal_sub(values['inflow'], values['outflow'])), 'count': values['count']}

    return {'month': month, 'basis': 'planned-only', 'shortMonthRule': 'last-valid-day',
            'occurrences': sorted(occurrences, key=lambda row: (row['dueDate'], row['planId'])),
            'categories': [{'category': category, 'currency': currency, **totals(values)}
                           for (category, currency), values in sorted(categories.items())],
            'currencies': [{'currency': currency, **totals(values)} for currency, values in sorted(currencies.items())]}
