from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from finance_core.database import FinanceRepository, connect
from finance_core.models import ImportBundle


def open_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def rows(connection: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query)]


def extract_legacy_bundle(connection: sqlite3.Connection) -> ImportBundle:
    transactions = rows(connection, """
        SELECT id, date, account, source, type, category, asset_symbol AS assetSymbol,
          amount, currency, note, ref, raw_data AS rawData, account_code AS accountCode,
          account_name AS accountName, responsibility_center AS responsibilityCenter,
          debit, credit FROM transactions ORDER BY date DESC, id
    """)
    holdings = rows(connection, """
        SELECT id, symbol, name, asset_type AS assetType, quantity,
          average_cost AS averageCost, current_price AS currentPrice,
          currency, sector, thesis_note AS thesisNote FROM holdings ORDER BY id
    """)
    recurring = rows(connection, """
        SELECT id, name, account, debit, credit, currency, description, frequency,
          day_of_month AS dayOfMonth, start_date AS startDate, enabled,
          generated_periods_json FROM recurring_transactions ORDER BY id
    """)
    for item in recurring:
        item["enabled"] = bool(item["enabled"])
        item["generatedPeriods"] = json.loads(item.pop("generated_periods_json"))
    living_accounts = rows(connection, """
        SELECT id, name, currency, balance, note, updated_at AS updatedAt
        FROM living_accounts ORDER BY id
    """)
    snapshots = rows(connection, """
        SELECT id, account_id AS accountId, balance, currency, recorded_at AS recordedAt
        FROM living_account_snapshots ORDER BY id
    """)
    plans = rows(connection, """
        SELECT id, kind, name, amount, currency, category,
          recurring_monthly AS recurringMonthly, day_of_month AS dayOfMonth,
          start_date AS startDate, note FROM monthly_plans ORDER BY id
    """)
    for item in plans:
        item["recurringMonthly"] = bool(item["recurringMonthly"])
    accounts = [row[0] for row in connection.execute(
        "SELECT account FROM account_options ORDER BY sort_order, account COLLATE NOCASE"
    )]
    return ImportBundle.model_validate({
        "transactions": transactions,
        "holdings": holdings,
        "accountOptions": accounts,
        "recurringRules": recurring,
        "livingAccounts": living_accounts,
        "livingSnapshots": snapshots,
        "monthlyIncomePlans": [item for item in plans if item["kind"] == "income"],
        "monthlyExpensePlans": [item for item in plans if item["kind"] == "expense"],
    })


def counts(bundle: ImportBundle) -> dict[str, int]:
    return {
        "transactions": len(bundle.transactions),
        "holdings": len(bundle.holdings),
        "accountOptions": len(bundle.account_options),
        "recurringRules": len(bundle.recurring_rules),
        "livingAccounts": len(bundle.living_accounts),
        "livingSnapshots": len(bundle.living_snapshots),
        "monthlyIncomePlans": len(bundle.monthly_income_plans),
        "monthlyExpensePlans": len(bundle.monthly_expense_plans),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely migrate legacy SFOS finance tables into a new Finance Core database.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error("The source database file does not exist.")
    with open_read_only(args.source) as source:
        bundle = extract_legacy_bundle(source)
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "validated": counts(bundle)}, ensure_ascii=False))
    if not args.apply:
        return
    if args.target is None:
        parser.error("--target is required with --apply.")
    if args.target.exists():
        parser.error("The target already exists; migration refuses to overwrite it.")
    target = connect(args.target)
    try:
        FinanceRepository(target).replace_bundle(bundle.model_dump(by_alias=True))
        integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = target.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign_keys:
            raise RuntimeError("Migrated database failed SQLite integrity checks.")
    finally:
        target.close()
    print(json.dumps({"status": "ok", "migrated": counts(bundle)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
