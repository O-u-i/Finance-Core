from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from finance_core.database import connect
from finance_core.ledger_repository import LedgerRepository


REGISTRY_SCHEMA_VERSION = 1
OWNER_USER_ID = "local-owner"
TOKEN_PREFIX = "fcv3_"


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def workspace_slug(display_name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
    return value[:48] or "workspace"


def synchronized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapper


@dataclass(frozen=True)
class Actor:
    kind: str
    actor_id: str
    user_id: str
    workspace_ids: frozenset[str]
    scopes: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return self.kind == "session"


@dataclass
class VaultHandle:
    connection: sqlite3.Connection
    repository: LedgerRepository
    lock: asyncio.Lock


class VaultManager:
    def __init__(self, data_root: Path):
        self.data_root = data_root.resolve()
        self._handles: dict[str, VaultHandle] = {}
        self._lifecycle_locks: dict[str, asyncio.Lock] = {}
        self._guard = threading.RLock()

    def lock_for(self, workspace_id: str) -> asyncio.Lock:
        # The lock survives connection closure and quarantine/restore.
        with self._guard:
            return self._lifecycle_locks.setdefault(workspace_id, asyncio.Lock())

    def path_for(self, workspace_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f-]{36}", workspace_id):
            raise ValueError("Workspace id is invalid.")
        path = (self.data_root / "workspaces" / workspace_id / "finance-core.sqlite3").resolve()
        expected = (self.data_root / "workspaces").resolve()
        if expected not in path.parents:
            raise ValueError("Workspace path escaped the configured data root.")
        return path

    def provision(self, workspace_id: str) -> None:
        path = self.path_for(workspace_id)
        connection = connect(path)
        try:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("New workspace failed SQLite integrity validation.")
        finally:
            connection.close()

    def get(self, workspace_id: str) -> VaultHandle:
        with self._guard:
            handle = self._handles.get(workspace_id)
            if handle is None:
                connection = connect(self.path_for(workspace_id))
                handle = VaultHandle(connection, LedgerRepository(connection), self.lock_for(workspace_id))
                self._handles[workspace_id] = handle
            return handle

    def close(self, workspace_id: str) -> None:
        with self._guard:
            handle = self._handles.pop(workspace_id, None)
            if handle is not None:
                handle.connection.close()

    def close_all(self) -> None:
        with self._guard:
            for handle in self._handles.values():
                handle.connection.close()
            self._handles.clear()


class Registry:
    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root).resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.path = self.data_root / "registry.sqlite3"
        self.connection = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.lock = threading.RLock()
        self.vaults = VaultManager(self.data_root)
        self._initialize()

    @synchronized
    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS registry_migrations(
              version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
            ) STRICT;
            CREATE TABLE IF NOT EXISTS users(
              id TEXT PRIMARY KEY, display_name TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            ) STRICT;
            CREATE TABLE IF NOT EXISTS workspaces(
              id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
              kind TEXT NOT NULL CHECK(kind IN ('personal','sandbox')),
              status TEXT NOT NULL CHECK(status IN ('active','archived','quarantined')),
              owner_user_id TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              FOREIGN KEY(owner_user_id) REFERENCES users(id)
            ) STRICT;
            CREATE TABLE IF NOT EXISTS access_tokens(
              id TEXT PRIMARY KEY, name TEXT NOT NULL, token_digest TEXT NOT NULL UNIQUE,
              workspace_ids_json TEXT NOT NULL, scopes_json TEXT NOT NULL,
              created_at TEXT NOT NULL, expires_at TEXT, revoked_at TEXT, last_used_at TEXT
            ) STRICT;
            CREATE TABLE IF NOT EXISTS sessions(
              id TEXT PRIMARY KEY, session_digest TEXT NOT NULL UNIQUE, user_id TEXT NOT NULL,
              created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT,
              FOREIGN KEY(user_id) REFERENCES users(id)
            ) STRICT;
            CREATE TABLE IF NOT EXISTS control_undo(
              token_digest TEXT PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE,
              operation_type TEXT NOT NULL, workspace_id TEXT,
              inverse_json TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
              consumed_at TEXT
            ) STRICT;
            CREATE TABLE IF NOT EXISTS audit_events(
              id TEXT PRIMARY KEY, request_id TEXT NOT NULL, actor_kind TEXT NOT NULL,
              actor_id TEXT NOT NULL, workspace_id TEXT, operation TEXT NOT NULL,
              result TEXT NOT NULL, created_at TEXT NOT NULL
            ) STRICT;
            INSERT OR IGNORE INTO registry_migrations(version,name,applied_at)
            VALUES(1,'finance-core-v3-registry','1970-01-01T00:00:00.000Z');
            """
        )
        timestamp = now_iso()
        self.connection.execute(
            "INSERT OR IGNORE INTO users(id,display_name,status,created_at,updated_at) VALUES(?,?,?,?,?)",
            (OWNER_USER_ID, "Local owner", "active", timestamp, timestamp),
        )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    @staticmethod
    def _workspace(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "slug": row["slug"], "displayName": row["display_name"],
            "kind": row["kind"], "status": row["status"], "ownerUserId": row["owner_user_id"],
            "createdAt": row["created_at"], "updatedAt": row["updated_at"],
        }

    @synchronized
    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        return self._workspace(row) if row else None

    @synchronized
    def list_workspaces(self, actor: Actor | None = None) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM workspaces ORDER BY created_at,id").fetchall()
        items = [self._workspace(row) for row in rows]
        if actor is not None and not actor.is_admin:
            items = [item for item in items if item["id"] in actor.workspace_ids]
        return items

    @synchronized
    def _unique_slug(self, display_name: str) -> str:
        base = workspace_slug(display_name)
        candidate = base
        index = 2
        while self.connection.execute("SELECT 1 FROM workspaces WHERE slug=?", (candidate,)).fetchone():
            candidate = f"{base[:42]}-{index}"
            index += 1
        return candidate

    @synchronized
    def create_workspace(self, display_name: str, kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("Workspace display name is required.")
        if kind not in {"personal", "sandbox"}:
            raise ValueError("Workspace kind must be personal or sandbox.")
        workspace_id = str(uuid4())
        self.vaults.provision(workspace_id)
        timestamp = now_iso()
        with self.transaction():
            self.connection.execute(
                "INSERT INTO workspaces(id,slug,display_name,kind,status,owner_user_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (workspace_id, self._unique_slug(display_name), display_name, kind, "active", OWNER_USER_ID, timestamp, timestamp),
            )
            undo = self._save_control_undo(
                "workspace.create", workspace_id, {"action": "quarantine-created"}, timedelta(minutes=10)
            )
        return self.get_workspace(workspace_id), undo  # type: ignore[return-value]

    @synchronized
    def update_workspace(self, workspace_id: str, *, display_name: str | None, status: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
        before = self.get_workspace(workspace_id)
        if before is None:
            raise LookupError("Workspace was not found.")
        if before["status"] == "quarantined":
            raise ValueError("A quarantined workspace must be restored through undo.")
        next_name = display_name.strip() if display_name is not None else before["displayName"]
        if not next_name:
            raise ValueError("Workspace display name is required.")
        next_status = status or before["status"]
        if next_status not in {"active", "archived"}:
            raise ValueError("Workspace status must be active or archived.")
        with self.transaction():
            self.connection.execute(
                "UPDATE workspaces SET display_name=?,status=?,updated_at=? WHERE id=?",
                (next_name, next_status, now_iso(), workspace_id),
            )
            undo = self._save_control_undo(
                "workspace.update", workspace_id,
                {"action": "workspace-update", "displayName": before["displayName"], "status": before["status"]},
                timedelta(minutes=10),
            )
        return self.get_workspace(workspace_id), undo  # type: ignore[return-value]

    @synchronized
    def quarantine_workspace(self, workspace_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        workspace = self.get_workspace(workspace_id)
        if workspace is None:
            raise LookupError("Workspace was not found.")
        if workspace["status"] == "quarantined":
            raise ValueError("Workspace is already quarantined.")
        self.vaults.close(workspace_id)
        source = self.vaults.path_for(workspace_id)
        if source.exists():
            connection = sqlite3.connect(source)
            try:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Workspace failed SQLite integrity validation.")
                if connection.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Workspace failed foreign-key validation.")
            finally:
                connection.close()
        operation_id = str(uuid4())
        quarantine_root = (self.data_root / "quarantine" / operation_id).resolve()
        quarantine_root.mkdir(parents=True, exist_ok=False)
        moved: list[dict[str, str]] = []
        for suffix in ("", "-wal", "-shm"):
            item = Path(f"{source}{suffix}")
            if item.exists():
                target = quarantine_root / item.name
                moved.append({"source": str(item), "target": str(target)})
        try:
            with self.move_files(moved):
                with self.transaction():
                    self.connection.execute(
                        "UPDATE workspaces SET status='quarantined',updated_at=? WHERE id=?", (now_iso(), workspace_id)
                    )
                    undo = self._save_control_undo(
                        "workspace.quarantine", workspace_id,
                        {"action": "workspace-restore", "status": workspace["status"], "moved": moved},
                        timedelta(days=30), operation_id=operation_id,
                    )
        except Exception as error:
            raise ValueError("Workspace quarantine failed; preserved files require review before retrying.") from error
        return self.get_workspace(workspace_id), undo  # type: ignore[return-value]

    @contextmanager
    def move_files(self, pairs: list[dict[str, str]]) -> Iterator[None]:
        """Preflight all paths, move explicit files, compensate on commit failure."""
        paths = [(Path(pair['source']).resolve(), Path(pair['target']).resolve()) for pair in pairs]
        seen: set[Path] = set()
        for source, target in paths:
            if self.data_root not in source.parents or self.data_root not in target.parents:
                raise ValueError("Workspace file is outside its configured root.")
            if source in seen or target in seen or source == target:
                raise ValueError("Workspace file plan contains conflicting paths.")
            seen.update((source, target))
            if not source.is_file() or target.exists():
                raise ValueError("Workspace files changed; automatic movement is unsafe.")
        completed: list[tuple[Path, Path]] = []
        try:
            for source, target in paths:
                target.parent.mkdir(parents=True, exist_ok=True)
                source.replace(target)
                completed.append((source, target))
            yield
        except Exception:
            for source, target in reversed(completed):
                if source.exists() or not target.is_file():
                    raise ValueError("Workspace file recovery requires manual review.") from None
                try:
                    target.replace(source)
                except OSError:
                    raise ValueError("Workspace file recovery requires manual review.") from None
            raise

    @synchronized
    def control_workspace_id(self, token: str) -> str | None:
        row = self.connection.execute(
            "SELECT workspace_id FROM control_undo WHERE token_digest=?", (digest(token),)
        ).fetchone()
        return row['workspace_id'] if row else None

    @synchronized
    def _save_control_undo(
        self, operation_type: str, workspace_id: str | None, inverse: dict[str, Any], lifetime: timedelta,
        *, operation_id: str | None = None,
    ) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        created = now()
        expires = created + lifetime
        operation_id = operation_id or str(uuid4())
        self.connection.execute(
            "INSERT INTO control_undo(token_digest,operation_id,operation_type,workspace_id,inverse_json,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
            (digest(token), operation_id, operation_type, workspace_id, json.dumps(inverse, ensure_ascii=False), created.isoformat(), expires.isoformat()),
        )
        return {
            "operationId": operation_id, "undoToken": token, "expiresAt": expires.isoformat(),
            "workspaceId": workspace_id, "operationType": operation_type,
        }

    @synchronized
    def undo_control(self, token: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM control_undo WHERE token_digest=?", (digest(token),)
        ).fetchone()
        if row is None or row["consumed_at"] is not None or datetime.fromisoformat(row["expires_at"]) <= now():
            return None
        inverse = json.loads(row["inverse_json"])
        workspace_id = row["workspace_id"]
        action = inverse["action"]
        if action == "workspace-update":
            workspace = self.get_workspace(workspace_id)
            if workspace is None or workspace["status"] == "quarantined":
                raise ValueError("Workspace state changed; undo its quarantine before restoring status.")
            with self.transaction():
                self.connection.execute(
                    "UPDATE workspaces SET display_name=?,status=?,updated_at=? WHERE id=?",
                    (inverse["displayName"], inverse["status"], now_iso(), workspace_id),
                )
                self.connection.execute("UPDATE control_undo SET consumed_at=? WHERE token_digest=?", (now_iso(), row["token_digest"]))
        elif action == "workspace-restore":
            pairs = [{"source": pair['target'], "target": pair['source']} for pair in inverse['moved']]
            try:
                with self.move_files(pairs):
                    with self.transaction():
                        self.connection.execute(
                            "UPDATE workspaces SET status=?,updated_at=? WHERE id=?",
                            (inverse["status"], now_iso(), workspace_id),
                        )
                        self.connection.execute("UPDATE control_undo SET consumed_at=? WHERE token_digest=?", (now_iso(), row["token_digest"]))
            except Exception as error:
                raise ValueError("Quarantined workspace restore failed; files and undo require review.") from error
        elif action == "quarantine-created":
            self.quarantine_workspace(workspace_id)
            with self.transaction():
                self.connection.execute("UPDATE control_undo SET consumed_at=? WHERE token_digest=?", (now_iso(), row["token_digest"]))
        elif action == "legacy-source-restore":
            for pair in inverse["moved"]:
                source = Path(pair["source"]).resolve()
                target = Path(pair["target"]).resolve()
                source.parent.mkdir(parents=True, exist_ok=True)
                if source.exists() or not target.exists():
                    raise ValueError("Quarantined legacy files changed; automatic undo is unsafe.")
                target.replace(source)
            with self.transaction():
                self.connection.execute("UPDATE control_undo SET consumed_at=? WHERE token_digest=?", (now_iso(), row["token_digest"]))
        else:
            raise ValueError("Undo operation is not supported.")
        return {
            "undone": True, "operationId": row["operation_id"], "workspaceId": workspace_id,
            "operationType": row["operation_type"],
        }

    @synchronized
    def quarantine_legacy_database(self, source: str | Path) -> dict[str, Any]:
        source_path = Path(source).resolve()
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError("Legacy database was not found.")
        connection = sqlite3.connect(source_path)
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Legacy database failed SQLite integrity validation.")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Legacy database failed foreign-key validation.")
        finally:
            connection.close()
        operation_id = str(uuid4())
        quarantine_root = (self.data_root / "quarantine" / operation_id).resolve()
        quarantine_root.mkdir(parents=True, exist_ok=False)
        moved: list[dict[str, str]] = []
        for suffix in ("", "-wal", "-shm"):
            item = Path(f"{source_path}{suffix}")
            if item.exists():
                target = quarantine_root / item.name
                item.replace(target)
                moved.append({"source": str(item), "target": str(target)})
        with self.transaction():
            undo = self._save_control_undo(
                "legacy-source.quarantine", None,
                {"action": "legacy-source-restore", "moved": moved},
                timedelta(days=30), operation_id=operation_id,
            )
        return {"quarantinedFiles": len(moved), "undo": undo}

    @synchronized
    def create_session(self, admin_token: str, configured_admin_token: str) -> tuple[str, dict[str, Any]]:
        if not configured_admin_token or not secrets.compare_digest(admin_token, configured_admin_token):
            raise PermissionError("Admin token is invalid.")
        secret = secrets.token_urlsafe(32)
        timestamp = now()
        expires = timestamp + timedelta(hours=12)
        session_id = str(uuid4())
        with self.transaction():
            self.connection.execute(
                "INSERT INTO sessions(id,session_digest,user_id,created_at,expires_at) VALUES(?,?,?,?,?)",
                (session_id, digest(secret), OWNER_USER_ID, timestamp.isoformat(), expires.isoformat()),
            )
        return secret, {"userId": OWNER_USER_ID, "expiresAt": expires.isoformat()}

    @synchronized
    def authenticate_session(self, secret: str | None) -> Actor | None:
        if not secret:
            return None
        row = self.connection.execute(
            "SELECT * FROM sessions WHERE session_digest=? AND revoked_at IS NULL", (digest(secret),)
        ).fetchone()
        if row is None or datetime.fromisoformat(row["expires_at"]) <= now():
            return None
        return Actor("session", row["id"], row["user_id"], frozenset(), frozenset({"ledger:read", "ledger:write", "workspace:manage"}))

    @synchronized
    def revoke_session(self, secret: str | None) -> None:
        if secret:
            self.connection.execute("UPDATE sessions SET revoked_at=? WHERE session_digest=?", (now_iso(), digest(secret)))

    @synchronized
    def create_access_token(
        self, name: str, workspace_ids: list[str], scopes: list[str], expires_at: str | None,
    ) -> tuple[dict[str, Any], str]:
        allowed_scopes = {"ledger:read", "ledger:write"}
        if not name.strip() or not workspace_ids or not set(scopes).issubset(allowed_scopes) or not scopes:
            raise ValueError("Token requires a name, workspaces, and valid ledger scopes.")
        for workspace_id in workspace_ids:
            if self.get_workspace(workspace_id) is None:
                raise LookupError("Workspace was not found.")
        secret = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token_id = str(uuid4())
        created = now_iso()
        with self.transaction():
            self.connection.execute(
                "INSERT INTO access_tokens(id,name,token_digest,workspace_ids_json,scopes_json,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
                (token_id, name.strip(), digest(secret), json.dumps(sorted(set(workspace_ids))), json.dumps(sorted(set(scopes))), created, expires_at),
            )
        return self.get_access_token(token_id), secret  # type: ignore[return-value]

    @synchronized
    def get_access_token(self, token_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM access_tokens WHERE id=?", (token_id,)).fetchone()
        return self._token_metadata(row) if row else None

    @staticmethod
    def _token_metadata(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "name": row["name"], "workspaceIds": json.loads(row["workspace_ids_json"]),
            "scopes": json.loads(row["scopes_json"]), "createdAt": row["created_at"],
            "expiresAt": row["expires_at"], "revokedAt": row["revoked_at"], "lastUsedAt": row["last_used_at"],
        }

    @synchronized
    def list_access_tokens(self) -> list[dict[str, Any]]:
        return [self._token_metadata(row) for row in self.connection.execute("SELECT * FROM access_tokens ORDER BY created_at,id")]

    @synchronized
    def authenticate_token(self, secret: str | None) -> Actor | None:
        if not secret or not secret.startswith(TOKEN_PREFIX):
            return None
        row = self.connection.execute(
            "SELECT * FROM access_tokens WHERE token_digest=? AND revoked_at IS NULL", (digest(secret),)
        ).fetchone()
        if row is None or (row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= now()):
            return None
        self.connection.execute("UPDATE access_tokens SET last_used_at=? WHERE id=?", (now_iso(), row["id"]))
        return Actor(
            "token", row["id"], OWNER_USER_ID,
            frozenset(json.loads(row["workspace_ids_json"])), frozenset(json.loads(row["scopes_json"])),
        )

    @synchronized
    def revoke_access_token(self, token_id: str) -> dict[str, Any]:
        if self.get_access_token(token_id) is None:
            raise LookupError("Access token was not found.")
        self.connection.execute("UPDATE access_tokens SET revoked_at=? WHERE id=?", (now_iso(), token_id))
        return self.get_access_token(token_id)  # type: ignore[return-value]

    @synchronized
    def audit(self, request_id: str, actor: Actor, workspace_id: str | None, operation: str, result: str) -> None:
        self.connection.execute(
            "INSERT INTO audit_events(id,request_id,actor_kind,actor_id,workspace_id,operation,result,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (str(uuid4()), request_id, actor.kind, actor.actor_id, workspace_id, operation, result, now_iso()),
        )

    @synchronized
    def close(self) -> None:
        self.vaults.close_all()
        self.connection.close()
