"""Explicit, sequential ledger upgrades. Never upgrade an existing Vault on connect."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

CURRENT_SCHEMA = 3
V3_SCHEMA = Path(__file__).with_name('schema_v3.sql')
LEGACY_TABLES = ['transactions', 'holdings', 'account_options', 'recurring_transactions',
                 'living_accounts', 'living_account_snapshots', 'monthly_plans', 'app_metadata']
V2_TABLES = ['commodities_v2', 'accounts_v2', 'price_quotes_v2', 'journal_drafts_v2',
             'journal_entries_v2', 'postings_v2', 'lots_v2', 'lot_movements_v2',
             'recurring_entry_rules_v2', 'living_accounts_v2', 'living_snapshots_v2', 'monthly_plans_v2']
V3_TABLES = ['financial_accounts_v3', 'finance_parties_v3', 'finance_settings_v3',
             'non_financial_assets_v3', 'investment_arrangements_v3', 'monthly_observations_v3',
             'monthly_closes_v3', 'legacy_living_archive_v3', 'finance_migration_receipts_v3', 'arrangement_drafts_v3']
FINANCE_TABLES = LEGACY_TABLES + V2_TABLES + V3_TABLES


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def schema_version(connection: sqlite3.Connection) -> int:
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone():
        return 0
    return connection.execute('SELECT COALESCE(MAX(version),0) FROM schema_migrations').fetchone()[0]


def rows(connection: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY rowid')]


def archive_living(connection: sqlite3.Connection) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    for table in ('living_accounts', 'living_account_snapshots', 'living_accounts_v2', 'living_snapshots_v2'):
        for row in rows(connection, table):
            connection.execute('INSERT OR IGNORE INTO legacy_living_archive_v3 VALUES(?,?,?,?,?)',
                               (table, row['id'], canonical(row), fingerprint(row), stamp))


def register_ledger_accounts(connection: sqlite3.Connection, *, confirmed: bool = False) -> None:
    for row in rows(connection, 'accounts_v2'):
        payload = {'id': row['id'], 'code': row['code'], 'name': row['name'], 'type': row['type'],
                   'subtype': row['subtype'], 'allowedCommodityCodes': json.loads(row['allowed_commodities_json']),
                   'status': row['status'], 'segment': 'investment', 'balanceSource': 'ledger',
                   'classificationConfirmed': confirmed, 'startMonth': None, 'endMonth': None,
                   'ownerPartyId': None, 'successorOf': None, 'legacyLivingId': None}
        connection.execute('INSERT OR IGNORE INTO financial_accounts_v3 VALUES(?,?,NULL,?)',
                           (row['id'], row['id'], canonical(payload)))


def upgrade(connection: sqlite3.Connection) -> dict:
    """Caller owns an exclusive transaction; scripts do not implicitly commit it."""
    version = schema_version(connection)
    if version != 2:
        raise ValueError('Only schema 2 can be upgraded to schema 3.')
    before = {table: fingerprint(rows(connection, table)) for table in LEGACY_TABLES + V2_TABLES}
    # Each statement is complete at a semicolon; triggers contain internal semicolons.
    statement = ''
    for line in V3_SCHEMA.read_text(encoding='utf-8').splitlines(True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ''
    register_ledger_accounts(connection)
    archive_living(connection)
    connection.execute("UPDATE undo_operations_v2 SET consumed_at=? WHERE consumed_at IS NULL",
                       (datetime.now(timezone.utc).isoformat(),))
    connection.execute("UPDATE undo_operations SET consumed_at=? WHERE consumed_at IS NULL",
                       (datetime.now(timezone.utc).isoformat(),))
    after = {table: fingerprint(rows(connection, table)) for table in LEGACY_TABLES + V2_TABLES}
    if before != after or connection.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Migration changed financial facts or broke references.')
    receipt = {'fromSchema': 2, 'toSchema': 3, 'preservedTableHashes': before,
               'legacyDatesInferred': False, 'classificationRequiresConfirmation': True}
    connection.execute('INSERT INTO finance_migration_receipts_v3 VALUES(?,?)', ('schema-2-to-3', canonical(receipt)))
    connection.execute('INSERT INTO schema_migrations VALUES(3,?,?)',
                       ('unified-personal-investment', datetime.now(timezone.utc).isoformat()))
    return receipt


def migrate_copy(source: Path, target: Path | None = None, *, real_data_approved: bool = False,
                 writers_stopped: bool = False) -> dict:
    """Read-only dry run, or stopped-writer copy into an exclusive new file."""
    if not source.is_file() or source.is_symlink():
        raise ValueError('Source must be an existing regular SQLite file.')
    if target is not None and not real_data_approved:
        raise PermissionError('REAL_DATA_MIGRATION_APPROVED is required for a file migration.')
    if target is not None and not writers_stopped:
        raise PermissionError('Explicitly confirm all source Vault writers are stopped before a file migration.')
    original = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)
    original.row_factory = sqlite3.Row
    dest = None
    try:
        if schema_version(original) != 2 or original.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Source must be an intact schema 2 Vault.')
        source_version = original.execute('PRAGMA data_version').fetchone()[0]
        if target is None:
            dest = sqlite3.connect(':memory:', isolation_level=None)
        else:
            if source.resolve() == target.resolve():
                raise ValueError('Migration must retain the original Vault.')
            target.parent.mkdir(parents=True, exist_ok=True)
            # O_EXCL semantics: never overwrite a file or follow an existing link.
            with target.open('xb'):
                pass
            dest = sqlite3.connect(target, isolation_level=None)
        dest.row_factory = sqlite3.Row
        dest.execute('PRAGMA foreign_keys=ON')
        original.backup(dest)
        dest.execute('BEGIN EXCLUSIVE')
        try:
            receipt = upgrade(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Upgraded copy failed integrity validation.')
            if target is not None and original.execute('PRAGMA data_version').fetchone()[0] != source_version:
                raise ValueError('Source changed during migration. Stop writers and review the retained failed copy.')
            dest.commit()
        except Exception:
            dest.rollback()
            raise
        return {**receipt, 'dryRun': target is None, 'originalRetained': True,
                'writerStopConfirmed': writers_stopped if target is not None else False}
    finally:
        if dest is not None:
            dest.close()
        original.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--target', type=Path)
    parser.add_argument('--approval', choices=['REAL_DATA_MIGRATION_APPROVED'])
    parser.add_argument('--writers-stopped', action='store_true',
                        help='Operator confirmation that every source Vault writer has been stopped; not an OS lock.')
    args = parser.parse_args()
    print(canonical(migrate_copy(args.source, args.target, real_data_approved=args.approval is not None,
                                 writers_stopped=args.writers_stopped)))


if __name__ == '__main__':
    main()
