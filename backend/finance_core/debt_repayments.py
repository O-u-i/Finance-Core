"""Explicit debt timing over existing balances; never posts or settles a Journal entry."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from finance_core.database import transaction
from finance_core.economic_evidence import balance_facts
from finance_core.ledger import decimal_sum
from finance_core.models_personal import DebtRepaymentRecord, valid_observed_date
from finance_core.models_v2 import canonical_decimal
from finance_core.personal_finance_snapshot import PersonalFinanceSnapshot, RevisionConflict, SchemaMigrationRequired, dump
from finance_core.schema_migration import canonical, fingerprint, rows, schema_version


TABLE = 'debt_repayment_arrangements_v3'


def table_exists(connection):
    return bool(connection.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('table', TABLE)).fetchone())


def create_table(connection):
    if not connection.in_transaction:
        raise RuntimeError('Debt storage extension requires an explicit writer transaction.')
    connection.execute(f'CREATE TABLE IF NOT EXISTS {TABLE}(id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)')


def records(connection):
    if not table_exists(connection):
        return []  # Older schema-3 Vaults remain untouched. Missing dates remain unknown.
    return [dump(DebtRepaymentRecord.model_validate(json.loads(row['payload_json'])))
            for row in connection.execute(f'SELECT * FROM {TABLE} ORDER BY id')]


def balance_snapshot(connection, as_of):
    if schema_version(connection) != 3:
        raise SchemaMigrationRequired('Schema 3 is required for debt balance review.')
    valid_observed_date(as_of)
    if as_of > datetime.now(timezone(timedelta(hours=8))).date().isoformat():
        raise ValueError('Balance review requires a non-future as-of date (Asia/Shanghai).')
    snapshot = PersonalFinanceSnapshot(connection)
    state, observations = snapshot.state(as_of[:7]), snapshot.observations()
    revision = fingerprint({'asOf': as_of, 'state': state, 'observations': observations})
    return state, observations, revision


def balance_quote(connection, account_id, currency, as_of):
    state, observations, revision = balance_snapshot(connection, as_of)
    facts, _ = balance_facts(state, observations, as_of)
    fact = next((value for value in facts if value['accountId'] == account_id and value['currency'] == currency
                 and value['key'] == 'liabilityBalance'), None)
    if fact is None:
        raise ValueError('Select a registered liability account and its currency.')
    return {'accountId': account_id, 'currency': currency, 'asOf': as_of, 'known': fact['known'],
            'balance': canonical_decimal(fact['amount']) if fact['known'] else None, 'balanceRevision': revision}


def active_record(values, account_id, currency):
    confirmed = [value for value in values if value['status'] == 'confirmed']
    superseded = {value.get('supersedes') for value in confirmed}
    active = [value for value in confirmed if value['accountId'] == account_id and value['currency'] == currency
              and value['id'] not in superseded]
    if len(active) > 1:
        raise ValueError('Debt arrangements contain conflicting confirmed versions.')
    return active[0] if active else None


def validate_history(connection):
    """Restore validates retained facts, not their freshness against today's ledger."""
    values = records(connection)
    by_id = {value['id']: value for value in values}
    accounts = {value['id']: value for value in PersonalFinanceSnapshot(connection).accounts()}
    commodities = {value['code']: value for value in rows(connection, 'commodities_v2')}
    for row in connection.execute(f'SELECT * FROM {TABLE}') if table_exists(connection) else []:
        if row['id'] != json.loads(row['payload_json'])['id']:
            raise ValueError('Debt arrangement identity does not match its retained row.')
    for value in values:
        account = accounts.get(value['accountId'])
        commodity = commodities.get(value['currency'])
        if not account or account['type'] != 'liability' or value['currency'] not in account['allowedCommodityCodes'] or not commodity or commodity['kind'] != 'currency':
            raise ValueError('Debt arrangement references an incompatible liability or currency.')
        if Decimal(value['balance']) <= 0 or decimal_sum(Decimal(item['amount']) for item in value['payments']) != Decimal(value['balance']):
            raise ValueError('Debt arrangement payments do not cover their recorded balance.')
        if any(Decimal(item['amount']).as_tuple().exponent < -commodity['scale'] for item in value['payments']):
            raise ValueError('Debt arrangement exceeds currency scale.')
        if value['revision'] != (2 if value['status'] == 'confirmed' else 1) or bool(value.get('confirmedAt')) != (value['status'] == 'confirmed'):
            raise ValueError('Debt arrangement confirmation history is invalid.')
        datetime.fromisoformat(value['createdAt'])
        if value.get('confirmedAt'):
            datetime.fromisoformat(value['confirmedAt'])
        parent = value.get('supersedes')
        seen = {value['id']}
        while parent:
            previous = by_id.get(parent)
            if parent in seen or not previous or previous['status'] != 'confirmed' or (previous['accountId'], previous['currency']) != (value['accountId'], value['currency']):
                raise ValueError('Debt arrangement correction chain is invalid.')
            seen.add(parent)
            parent = previous.get('supersedes')
        active_record(values, value['accountId'], value['currency'])


class DebtRepayments:
    def __init__(self, ledger):
        self.ledger = ledger
        self.connection = ledger.connection

    def list(self):
        if schema_version(self.connection) != 3:
            raise SchemaMigrationRequired('Schema 3 is required for debt arrangements.')
        return records(self.connection)

    def quote(self, account_id, currency, as_of):
        self.connection.execute('SAVEPOINT debt_balance_read')
        try:
            return balance_quote(self.connection, account_id, currency, as_of)
        finally:
            self.connection.execute('RELEASE debt_balance_read')

    def _check(self, item):
        quote = balance_quote(self.connection, item.account_id, item.currency, item.as_of)
        if quote['balanceRevision'] != item.balance_revision:
            raise RevisionConflict('The reviewed balance changed.')
        if not quote['known'] or Decimal(quote['balance']) <= 0:
            raise ValueError('Confirmation requires a known positive recorded liability balance.')
        if decimal_sum(Decimal(payment.amount) for payment in item.payments) != Decimal(quote['balance']):
            raise ValueError('Dated payments must cover exactly the current recorded balance; do not invent future charges.')
        current = active_record(self.list(), item.account_id, item.currency)
        if item.supersedes != (current['id'] if current else None):
            raise RevisionConflict('Select the current confirmed arrangement explicitly when replacing it.')
        commodities = {value['code']: value for value in PersonalFinanceSnapshot(self.connection).state(item.as_of[:7])['commodities']}
        scale = commodities[item.currency]['scale']
        if any(Decimal(payment.amount).as_tuple().exponent < -scale for payment in item.payments):
            raise ValueError('Repayment amount exceeds the registered currency scale.')
        return quote

    def create(self, item):
        with transaction(self.connection):
            quote = self._check(item)
            record = {**dump(item), 'balance': quote['balance'], 'status': 'draft', 'revision': 1,
                      'createdAt': datetime.now(timezone.utc).isoformat()}
            create_table(self.connection)
            self.connection.execute(f'INSERT INTO {TABLE}(id,payload_json) VALUES (?,?)', (item.id, canonical(record)))
            self.ledger._invalidate_undo()
        return record

    def confirm(self, identity, confirmation):
        with transaction(self.connection):
            record = next((value for value in self.list() if value['id'] == identity), None)
            if record is None:
                raise LookupError('Debt arrangement was not found.')
            if record['status'] != 'draft' or record['revision'] != confirmation.expected_revision:
                raise RevisionConflict('Only the reviewed draft can be confirmed once.')
            if record['balanceRevision'] != confirmation.expected_balance_revision:
                raise RevisionConflict('The balance review does not match this draft.')
            self._check(DebtRepaymentRecord.model_validate(record))
            record = {**record, 'status': 'confirmed', 'revision': record['revision'] + 1,
                      'confirmedAt': datetime.now(timezone.utc).isoformat()}
            self.connection.execute(f'UPDATE {TABLE} SET payload_json=? WHERE id=?', (canonical(record), identity))
            self.ledger._invalidate_undo()
        return record
