from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from finance_core.models import (
    Holding,
    LivingAccount,
    LivingAccountSnapshot,
    MonthlyPlan,
    RecurringTransaction,
    Transaction,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = ROOT / ".local-data" / "finance-core.sqlite3"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
ModelT = TypeVar("ModelT", bound=BaseModel)


RESOURCE_CONFIG: dict[str, dict[str, Any]] = {
    "transactions": {
        "table": "transactions", "model": Transaction,
        "fields": {
            "id": "id", "date": "date", "account": "account", "source": "source",
            "type": "type", "category": "category", "asset_symbol": "asset_symbol",
            "amount": "amount", "currency": "currency", "note": "note", "ref": "ref",
            "raw_data": "raw_data", "account_code": "account_code", "account_name": "account_name",
            "responsibility_center": "responsibility_center", "debit": "debit", "credit": "credit",
        }, "order": "date DESC, id",
    },
    "holdings": {
        "table": "holdings", "model": Holding,
        "fields": {
            "id": "id", "symbol": "symbol", "name": "name", "asset_type": "asset_type",
            "quantity": "quantity", "average_cost": "average_cost", "current_price": "current_price",
            "currency": "currency", "sector": "sector", "thesis_note": "thesis_note",
        }, "order": "symbol COLLATE NOCASE, id",
    },
    "recurring-rules": {
        "table": "recurring_transactions", "model": RecurringTransaction,
        "fields": {
            "id": "id", "name": "name", "account": "account", "debit": "debit", "credit": "credit",
            "currency": "currency", "description": "description", "frequency": "frequency",
            "day_of_month": "day_of_month", "start_date": "start_date", "enabled": "enabled",
            "generated_periods": "generated_periods_json",
        }, "json": {"generated_periods"}, "bool": {"enabled"}, "order": "start_date, id",
    },
    "living-accounts": {
        "table": "living_accounts", "model": LivingAccount,
        "fields": {"id": "id", "name": "name", "currency": "currency", "balance": "balance", "note": "note", "updated_at": "updated_at"},
        "order": "name COLLATE NOCASE, id",
    },
    "living-snapshots": {
        "table": "living_account_snapshots", "model": LivingAccountSnapshot,
        "fields": {"id": "id", "account_id": "account_id", "balance": "balance", "currency": "currency", "recorded_at": "recorded_at"},
        "order": "recorded_at DESC, id",
    },
    "monthly-plans": {
        "table": "monthly_plans", "model": MonthlyPlan,
        "fields": {
            "id": "id", "kind": "kind", "name": "name", "amount": "amount", "currency": "currency",
            "category": "category", "recurring_monthly": "recurring_monthly", "day_of_month": "day_of_month",
            "start_date": "start_date", "note": "note",
        }, "bool": {"recurring_monthly"}, "order": "kind, start_date, id",
    },
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def connect(path: str | Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    database_path = str(path)
    if database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if database_path != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return connection


class FinanceRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list(self, resource: str) -> list[BaseModel]:
        config = RESOURCE_CONFIG[resource]
        rows = self.connection.execute(
            f"SELECT * FROM {config['table']} ORDER BY {config['order']}"
        ).fetchall()
        return [self._from_row(config, row) for row in rows]

    def get(self, resource: str, resource_id: str) -> BaseModel | None:
        config = RESOURCE_CONFIG[resource]
        row = self.connection.execute(
            f"SELECT * FROM {config['table']} WHERE id = ?", (resource_id,)
        ).fetchone()
        return self._from_row(config, row) if row else None

    def create(self, resource: str, model: BaseModel) -> tuple[BaseModel, dict[str, str]]:
        with transaction(self.connection):
            self._insert(resource, model)
            undo = self._save_undo("delete", resource, model.model_dump()["id"], None)
        return model, undo

    def update(self, resource: str, resource_id: str, changes: dict[str, Any]) -> tuple[BaseModel, dict[str, str]] | None:
        current = self.get(resource, resource_id)
        if current is None:
            return None
        validated = type(current).model_validate({**current.model_dump(by_alias=True), **changes})
        config = RESOURCE_CONFIG[resource]
        with transaction(self.connection):
            self._replace_row(config, validated)
            undo = self._save_undo("update", resource, resource_id, current.model_dump(by_alias=True))
        return validated, undo

    def delete(self, resource: str, resource_id: str) -> tuple[BaseModel, dict[str, str]] | None:
        current = self.get(resource, resource_id)
        if current is None:
            return None
        config = RESOURCE_CONFIG[resource]
        with transaction(self.connection):
            self.connection.execute(f"DELETE FROM {config['table']} WHERE id = ?", (resource_id,))
            undo = self._save_undo("create", resource, resource_id, current.model_dump(by_alias=True))
        return current, undo

    def undo(self, token: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM undo_operations WHERE token = ?", (token,)
        ).fetchone()
        now = utc_now()
        if row is None or row["consumed_at"] is not None or datetime.fromisoformat(row["expires_at"]) <= now:
            return None
        resource = row["resource"]
        inverse = json.loads(row["inverse_json"])
        with transaction(self.connection):
            if row["action"] == "restore-bundle":
                self._replace_bundle_rows(inverse)
            elif resource == "account-options":
                self.connection.execute("DELETE FROM account_options")
                self.connection.executemany(
                    "INSERT INTO account_options(account, sort_order) VALUES (?, ?)",
                    [(account, index) for index, account in enumerate(inverse["items"])],
                )
            elif row["action"] == "delete":
                config = RESOURCE_CONFIG[resource]
                self.connection.execute(f"DELETE FROM {config['table']} WHERE id = ?", (row["resource_id"],))
            elif row["action"] == "create":
                config = RESOURCE_CONFIG[resource]
                self._insert(resource, config["model"].model_validate(inverse))
            else:
                config = RESOURCE_CONFIG[resource]
                self._replace_row(config, config["model"].model_validate(inverse))
            self.connection.execute(
                "UPDATE undo_operations SET consumed_at = ? WHERE token = ?",
                (now.isoformat(), token),
            )
        return {"undone": True, "resource": resource, "resourceId": row["resource_id"]}

    def export_bundle(self) -> dict[str, Any]:
        plans = self.list("monthly-plans")
        return {
            "transactions": self._dump_list(self.list("transactions")),
            "holdings": self._dump_list(self.list("holdings")),
            "accountOptions": [row[0] for row in self.connection.execute("SELECT account FROM account_options ORDER BY sort_order, account")],
            "recurringRules": self._dump_list(self.list("recurring-rules")),
            "livingAccounts": self._dump_list(self.list("living-accounts")),
            "livingSnapshots": self._dump_list(self.list("living-snapshots")),
            "monthlyIncomePlans": self._dump_list([item for item in plans if item.kind == "income"]),
            "monthlyExpensePlans": self._dump_list([item for item in plans if item.kind == "expense"]),
        }

    def replace_bundle(self, payload: dict[str, Any]) -> dict[str, int]:
        counts = {key: len(value) for key, value in payload.items()}
        with transaction(self.connection):
            self._replace_bundle_rows(payload)
            self.connection.execute("UPDATE undo_operations SET consumed_at = ? WHERE consumed_at IS NULL", (utc_now().isoformat(),))
        return counts

    def batch(self, operations: list[dict[str, Any]]) -> dict[str, str]:
        before = self.export_bundle()
        with transaction(self.connection):
            for operation in operations:
                resource = operation["resource"]
                action = operation["action"]
                if resource == "account-options":
                    items = operation["data"]
                    if any(not item.strip() for item in items) or len(set(items)) != len(items):
                        raise ValueError("Account options must be nonblank and unique.")
                    self.connection.execute("DELETE FROM account_options")
                    self.connection.executemany(
                        "INSERT INTO account_options(account, sort_order) VALUES (?, ?)",
                        [(account, index) for index, account in enumerate(items)],
                    )
                    continue
                config = RESOURCE_CONFIG[resource]
                resource_id = operation.get("resourceId")
                if action == "create":
                    self._insert(resource, config["model"].model_validate(operation["data"]))
                elif action == "update":
                    current = self.get(resource, resource_id)
                    if current is None:
                        raise LookupError("Resource was not found.")
                    updated = type(current).model_validate({**current.model_dump(by_alias=True), **operation["data"]})
                    self._replace_row(config, updated)
                else:
                    result = self.connection.execute(f"DELETE FROM {config['table']} WHERE id = ?", (resource_id,))
                    if result.rowcount == 0:
                        raise LookupError("Resource was not found.")
            return self._save_undo("restore-bundle", "bundle", "batch", before)

    def _replace_bundle_rows(self, payload: dict[str, Any]) -> None:
        for table in ("living_account_snapshots", "transactions", "holdings", "account_options", "recurring_transactions", "monthly_plans", "living_accounts"):
            self.connection.execute(f"DELETE FROM {table}")
        for index, account in enumerate(payload["accountOptions"]):
            self.connection.execute("INSERT INTO account_options(account, sort_order) VALUES (?, ?)", (account, index))
        mapping = {
            "transactions": "transactions", "holdings": "holdings", "recurringRules": "recurring-rules",
            "livingAccounts": "living-accounts", "livingSnapshots": "living-snapshots",
            "monthlyIncomePlans": "monthly-plans", "monthlyExpensePlans": "monthly-plans",
        }
        for key, resource in mapping.items():
            model_type = RESOURCE_CONFIG[resource]["model"]
            for item in payload[key]:
                self._insert(resource, model_type.model_validate(item))

    def _insert(self, resource: str, model: BaseModel) -> None:
        config = RESOURCE_CONFIG[resource]
        values = self._to_db(config, model)
        columns = list(values)
        placeholders = ", ".join("?" for _ in columns)
        self.connection.execute(
            f"INSERT INTO {config['table']} ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(values[column] for column in columns),
        )

    def _replace_row(self, config: dict[str, Any], model: BaseModel) -> None:
        values = self._to_db(config, model)
        assignments = ", ".join(f"{column} = ?" for column in values if column != "id")
        self.connection.execute(
            f"UPDATE {config['table']} SET {assignments} WHERE id = ?",
            tuple(value for column, value in values.items() if column != "id") + (values["id"],),
        )

    def _save_undo(self, action: str, resource: str, resource_id: str, inverse: dict[str, Any] | None) -> dict[str, str]:
        now = utc_now()
        expires = now + timedelta(minutes=10)
        token = str(uuid4())
        self.connection.execute("UPDATE undo_operations SET consumed_at = ? WHERE consumed_at IS NULL", (now.isoformat(),))
        self.connection.execute(
            "INSERT INTO undo_operations(token, action, resource, resource_id, inverse_json, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (token, action, resource, resource_id, json.dumps(inverse, ensure_ascii=False), now.isoformat(), expires.isoformat()),
        )
        return {"undoToken": token, "expiresAt": expires.isoformat()}

    @staticmethod
    def _to_db(config: dict[str, Any], model: BaseModel) -> dict[str, Any]:
        data = model.model_dump()
        result = {}
        for field, column in config["fields"].items():
            value = data[field]
            if field in config.get("json", set()):
                value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if field in config.get("bool", set()):
                value = int(value)
            result[column] = value
        return result

    @staticmethod
    def _from_row(config: dict[str, Any], row: sqlite3.Row) -> BaseModel:
        payload = {}
        for field, column in config["fields"].items():
            value = row[column]
            if field in config.get("json", set()):
                value = json.loads(value)
            if field in config.get("bool", set()):
                value = bool(value)
            payload[field] = value
        return config["model"].model_validate(payload)

    @staticmethod
    def _dump_list(items: list[BaseModel]) -> list[dict[str, Any]]:
        return [item.model_dump(by_alias=True) for item in items]
