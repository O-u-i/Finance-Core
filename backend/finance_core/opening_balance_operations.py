"""One opening workflow over the existing Workspace Journal/observation writer."""
from __future__ import annotations

from contextlib import contextmanager
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from finance_core.ledger import decimal_add
from finance_core.models_v2 import canonical_decimal
from finance_core.monthly_review import month_window, monthly_review
from finance_core.opening_balances import build_opening_draft, opening_date
from finance_core.personal_finance import month_end
from finance_core.personal_finance_repository import PersonalFinanceRepository
from finance_core.schema_migration import fingerprint


class OpeningBalanceOperations:
    def __init__(self, ledger):
        self.ledger = ledger

    def create_draft(self, item):
        draft = build_opening_draft(item, {a.id: a for a in self.ledger.list_accounts()},
                                    {c.code: c for c in self.ledger.list_commodities()})
        completed, issues = self.ledger.validate_draft(draft)
        if completed is None:
            raise ValueError('; '.join(issue.message for issue in issues))
        return self.ledger.create_draft(draft)

    def record_living(self, item):
        return PersonalFinanceRepository(self.ledger).record_balance(item, opening=True)

    def post(self, draft_id, item):
        stored = self.ledger.get_draft(draft_id)
        if not stored or not opening_date(stored['draft']):
            raise ValueError('Select an existing classified opening draft.')
        result = self.ledger.post_draft(draft_id, expected_updated_at=item.expected_updated_at)
        if not result['posted']:
            raise ValueError('; '.join(issue['message'] for issue in result['issues']))
        return result['entry']

    def records(self):
        drafts = [value for value in self.ledger.list_drafts() if opening_date(value['draft'])]
        entries = [value for value in self.ledger.list_entries() if opening_date(value)]
        return {'drafts': drafts, 'entries': entries}

    def cash_flow(self, month):
        with self._read_snapshot():
            end = month_end(month)
            start = month + '-01'
            next_day = (end + timedelta(days=1)).isoformat()
            entries = self.ledger.list_entries()
            selected = []
            for entry in entries:
                parsed = datetime.strptime(entry['date'], '%Y-%m-%d').date().isoformat()
                if parsed != entry['date']:
                    raise ValueError('Activity reports require real YYYY-MM-DD posted dates.')
                if start <= parsed < next_day:
                    selected.append(entry)
            accounts = {a.id: a for a in self.ledger.list_accounts()}
            groups = [defaultdict(Decimal), defaultdict(Decimal)]
            for entry in selected:
                target = groups[1 if opening_date(entry) else 0]
                for posting in entry['postings']:
                    account = accounts[posting['accountId']]
                    if account.type == 'asset' and account.subtype.lower() == 'cash':
                        value = Decimal(posting['units'])
                        if posting['side'] == 'credit':
                            value = value.copy_negate()
                        key = (posting['commodityCode'], posting['cashFlowCategory'])
                        target[key] = decimal_add(target[key], value)
            def render(values):
                return [{'commodityCode': code, 'category': category, 'amount': canonical_decimal(amount)}
                        for (code, category), amount in sorted(values.items())]
            return {'schemaVersion': 1, 'calculationVersion': 'opening-activity-v1', 'month': month,
                    'windowStart': start, 'windowEndExclusive': next_day, 'activity': render(groups[0]),
                    'openingEffects': render(groups[1]), 'externalCompleteness': 'unknown',
                    'revision': fingerprint({'entries': selected, 'accounts': [a.model_dump() for a in accounts.values()]})}

    def monthly_activity(self, month):
        with self._read_snapshot():
            if month >= datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m'):
                raise ValueError('Monthly review requires a completed calendar month (Asia/Shanghai).')
            _, start, end = month_window(month)
            records = self.ledger.list_entries()
            excluded = {entry['id'] for entry in records if opening_date(entry)}
            # Keep invalid dates in the existing fail-closed calculation rather than dropping them.
            entries = [{'id': e['id'], 'date': e['date'], 'balancing_commodity_code': e['balancingCommodityCode'],
                        'reversal_of': e['reversalOf']} for e in records]
            postings = [dict(row) for row in self.ledger.connection.execute(
                'SELECT p.id,p.entry_id,p.account_id,p.side,p.units,p.commodity_code,p.valuation_amount,'
                'p.cash_flow_category,a.type,a.subtype FROM postings_v2 p JOIN journal_entries_v2 e ON e.id=p.entry_id '
                'JOIN accounts_v2 a ON a.id=p.account_id WHERE e.date>=? AND e.date<? ORDER BY p.entry_id,p.sort_order', (start, end))
                if row['entry_id'] not in excluded]
            result = monthly_review(month, entries, postings, exclude_entry_ids=excluded)
            result['calculationVersion'] = 'monthly-activity-v1'
            result['openingEntryIds'] = sorted(e['id'] for e in records if e['id'] in excluded and start <= e['date'] < end)
            result['revision'] = fingerprint({'activityRevision': result['revision'], 'classification':
                [{'id': e['id'], 'date': e['date'], 'tags': e['tags'], 'reversalOf': e['reversalOf']} for e in records]})
            return result

    @contextmanager
    def _read_snapshot(self):
        self.ledger.connection.execute('SAVEPOINT opening_report_read')
        try:
            yield
        finally:
            self.ledger.connection.execute('RELEASE opening_report_read')
