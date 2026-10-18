"""Finance-only backup formats. The repository owns restore transactions and undo."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from finance_core.personal_finance_snapshot import PersonalFinanceSnapshot
from finance_core.debt_repayments import TABLE, create_table, table_exists, validate_history
from finance_core.schema_migration import (
    FINANCE_TABLES, V2_TABLES, archive_living, fingerprint, register_ledger_accounts, rows, schema_version,
)


def create_backup(connection: sqlite3.Connection, *, format_version: int = 2) -> dict:
    if format_version == 3:
        if schema_version(connection) != 3:
            raise ValueError('Full Vault backup requires schema 3.')
        tables = FINANCE_TABLES
        if table_exists(connection):
            # Old readers must refuse rather than silently discard the extension.
            format_version, tables = 4, FINANCE_TABLES + [TABLE]
    elif format_version == 2:
        if table_exists(connection) and connection.execute(f'SELECT 1 FROM {TABLE} LIMIT 1').fetchone():
            raise ValueError('Debt arrangements require a full Vault backup (format 4); legacy export would lose reviewed timing.')
        if connection.execute("SELECT 1 FROM app_metadata WHERE key LIKE 'plan-repeat-months:%' LIMIT 1").fetchone():
            raise ValueError('Periodic plans require a full Vault backup (format 3); legacy format 2 would lose their schedules.')
        tables = V2_TABLES
    else:
        raise ValueError('Unsupported backup format.')
    payload = {table: rows(connection, table) for table in tables}
    return {'formatVersion': format_version, 'schemaVersion': 3 if format_version == 4 else format_version,
            'createdAt': datetime.now(timezone.utc).isoformat(), 'payload': payload,
            'sha256': fingerprint(payload)}


def restore_backup(connection: sqlite3.Connection, backup: dict) -> dict[str, int]:
    """Validate and insert within the caller's existing writer reservation."""
    if not connection.in_transaction:
        raise RuntimeError('Restore requires the repository writer transaction.')
    version = backup.get('formatVersion')
    if type(version) is not int or version not in {2, 3, 4} or type(backup.get('schemaVersion')) is not int or backup['schemaVersion'] != (3 if version == 4 else version):
        raise ValueError('Backup must use format/schema 2/2, 3/3, or 4/3 (debt timing extension).')
    payload = backup.get('payload')
    if not isinstance(payload, dict):
        raise ValueError('Backup payload is missing.')
    if fingerprint(payload) != backup.get('sha256'):
        raise ValueError('Backup SHA-256 does not match its canonical payload.')
    current_schema = schema_version(connection)
    if version in {3, 4} and current_schema != 3:
        raise ValueError('Restore a full backup into a new schema 3 Vault.')
    insert_order = FINANCE_TABLES + ([TABLE] if version == 4 else []) if version in {3, 4} else V2_TABLES
    if set(payload) != set(insert_order):
        raise ValueError('Backup contains missing or unknown tables.')
    empty_tables = (FINANCE_TABLES + ([TABLE] if table_exists(connection) else [])) if current_schema == 3 else insert_order
    if any(connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone()
           for table in empty_tables if table != 'finance_migration_receipts_v3'):
        raise ValueError('Backup restore requires an empty financial Vault, including all segments.')
    if version in {3, 4}:
        connection.execute('DELETE FROM finance_migration_receipts_v3')
    if version == 4:
        create_table(connection)
    counts = {}
    for table in insert_order:
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info({table})')]
        values = payload[table]
        if not isinstance(values, list):
            raise ValueError(f'Backup table {table} must be a row list.')
        for row in values:
            if not isinstance(row, dict) or set(row) != set(columns):
                raise ValueError(f'Backup row shape for {table} does not match its ledger schema.')
            placeholders = ','.join('?' for _ in columns)
            connection.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES ({placeholders})",
                               tuple(row[column] for column in columns))
        counts[table] = len(values)
    if connection.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Restored backup failed foreign-key validation.')
    if version == 2 and current_schema == 3:
        register_ledger_accounts(connection)
        archive_living(connection)
    elif version in {3, 4}:
        PersonalFinanceSnapshot(connection).validate_restored_state()
        validate_history(connection)
    return counts
