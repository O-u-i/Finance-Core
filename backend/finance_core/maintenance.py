from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from finance_core.registry import Registry


def inspect_database(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Source database was not found.")
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        migrations = [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")]
        tables = [
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table.replace(chr(34), chr(34) * 2)}"').fetchone()[0]
            for table in tables
        }
    finally:
        connection.close()
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "integrity": integrity,
        "foreignKeyViolations": len(foreign_keys),
        "schemaMigrations": migrations,
        "tableCounts": counts,
        "sha256": checksum,
    }


def migrate_database(source: Path, data_root: Path, display_name: str, kind: str) -> dict[str, Any]:
    inspection = inspect_database(source)
    if inspection["integrity"] != "ok" or inspection["foreignKeyViolations"]:
        raise ValueError("Source database failed validation.")
    store = Registry(data_root)
    try:
        workspace, undo = store.create_workspace(display_name, kind)
        target = store.vaults.path_for(workspace["id"])
        store.vaults.close(workspace["id"])
        source_connection = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
        target_connection = sqlite3.connect(target)
        try:
            source_connection.backup(target_connection)
            if target_connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Target database failed integrity validation.")
            if target_connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Target database failed foreign-key validation.")
        finally:
            source_connection.close()
            target_connection.close()
        target_inspection = inspect_database(target)
        if target_inspection["tableCounts"] != inspection["tableCounts"]:
            raise ValueError("Target row counts do not match the source database.")
        return {
            "workspace": workspace,
            "sourceSha256": inspection["sha256"],
            "targetSha256": target_inspection["sha256"],
            "tableCounts": target_inspection["tableCounts"],
            "undo": undo,
            "sourceUnchanged": True,
        }
    finally:
        store.close()


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Finance Core v3 safe database maintenance.")
    subcommands = command.add_subparsers(dest="command", required=True)
    inspect = subcommands.add_parser("inspect", help="Validate a source database without changing it.")
    inspect.add_argument("--source", type=Path, required=True)
    migrate = subcommands.add_parser("migrate", help="Copy a validated v2 database into a new v3 workspace.")
    migrate.add_argument("--source", type=Path, required=True)
    migrate.add_argument("--data-root", type=Path, required=True)
    migrate.add_argument("--display-name", required=True)
    migrate.add_argument("--kind", choices=("personal", "sandbox"), default="personal")
    migrate.add_argument("--dry-run", action="store_true")
    quarantine = subcommands.add_parser("quarantine", help="Move one validated SQLite file set into recoverable quarantine.")
    quarantine.add_argument("--source", type=Path, required=True)
    quarantine.add_argument("--data-root", type=Path, required=True)
    quarantine.add_argument("--dry-run", action="store_true")
    restore = subcommands.add_parser("restore", help="Restore a quarantined source using its private recovery file.")
    restore.add_argument("--data-root", type=Path, required=True)
    restore.add_argument("--recovery-file", type=Path, required=True)
    return command


def main() -> None:
    args = parser().parse_args()
    if args.command == "inspect":
        print(json.dumps(inspect_database(args.source), ensure_ascii=False, indent=2))
        return
    if args.command == "restore":
        recovery = json.loads(args.recovery_file.read_text(encoding="utf-8"))
        store = Registry(args.data_root)
        try:
            result = store.undo_control(recovery["undoToken"])
        finally:
            store.close()
        if result is None:
            raise RuntimeError("Recovery token is invalid, expired, or already used.")
        print(json.dumps({"restored": True, "operationId": result["operationId"]}, ensure_ascii=False, indent=2))
        return
    inspection = inspect_database(args.source)
    if args.dry_run:
        print(json.dumps({"dryRun": True, "validation": inspection, "changed": False}, ensure_ascii=False, indent=2))
        return
    if args.command == "migrate":
        result = migrate_database(args.source, args.data_root, args.display_name, args.kind)
    else:
        store = Registry(args.data_root)
        try:
            result = store.quarantine_legacy_database(args.source)
        finally:
            store.close()
        operation_id = result["undo"]["operationId"]
        recovery_file = args.data_root.resolve() / "quarantine" / operation_id / "recovery.json"
        recovery_file.write_text(
            json.dumps({"undoToken": result["undo"]["undoToken"]}, ensure_ascii=False), encoding="utf-8"
        )
        result = {
            "quarantinedFiles": result["quarantinedFiles"],
            "operationId": operation_id,
            "expiresAt": result["undo"]["expiresAt"],
            "recoveryFileCreated": True,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
