from __future__ import annotations

import csv
import io
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from finance_core import __version__
from finance_core.api_v2 import create_v2_router
from finance_core.database import DEFAULT_DATABASE_PATH, RESOURCE_CONFIG, FinanceRepository, connect
from finance_core.domain import account_flows, dashboard, financial_statements, reconciliation, world_metrics
from finance_core.ledger_repository import LedgerRepository
from finance_core.models import BatchRequest, ImportBundle, ResourcePatch, UndoRequest

API_VERSION = "2.0.0"
SCHEMA_VERSION = 2
CAPABILITIES = [
    "transactions", "holdings", "account-options", "recurring-rules",
    "living-accounts", "living-snapshots", "monthly-plans", "dashboard",
    "t-accounts", "financial-statements", "reconciliation", "json-import-export",
    "csv-import-export", "atomic-batch", "single-step-undo",
]


def json_model(model: Any) -> dict[str, Any]:
    return model.model_dump(by_alias=True, exclude_none=True)


def create_legacy_app(
    *,
    connection: sqlite3.Connection | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owns_connection = connection is None
        database = connection or connect(database_path)
        app.state.database = database
        app.state.repository = FinanceRepository(database)
        app.state.ledger_repository = LedgerRepository(database)
        try:
            yield
        finally:
            if owns_connection:
                database.close()

    app = FastAPI(
        title="Finance Core API",
        version=API_VERSION,
        description="Local-first deterministic finance domain and data service.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def legacy_api_is_read_only(request: Request, call_next):
        if request.url.path.startswith("/api/v1/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            return JSONResponse(
                status_code=410,
                content={
                    "error": {
                        "code": "LEGACY_API_READ_ONLY",
                        "message": "Finance Core v1 is read-only. Use the aggregate ledger under /api/v2.",
                    }
                },
            )
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Request does not match the Finance Core API contract.",
                    "issues": [
                        {"path": ".".join(str(part) for part in item.get("loc", ())), "message": item.get("msg", "Invalid value.")}
                        for item in error.errors()
                    ],
                }
            },
        )

    @app.get("/api/v1/health")
    def health(request: Request) -> dict[str, Any]:
        request.app.state.database.execute("SELECT 1").fetchone()
        return {
            "status": "ok",
            "service": "finance-core",
            "serviceVersion": __version__,
            "apiVersion": "1.0.0",
            "schemaVersion": SCHEMA_VERSION,
            "legacyReadOnly": True,
            "capabilities": ["legacy-read", "legacy-export"],
        }

    def repository(request: Request) -> FinanceRepository:
        return request.app.state.repository

    def register_resource(resource: str) -> None:
        model_type = RESOURCE_CONFIG[resource]["model"]
        path = f"/api/v1/{resource}"

        def list_items(request: Request) -> dict[str, Any]:
            return {"data": [json_model(item) for item in repository(request).list(resource)]}

        def get_item(resource_id: str, request: Request) -> dict[str, Any]:
            item = repository(request).get(resource, resource_id)
            if item is None:
                raise HTTPException(404, detail="Resource was not found.")
            return {"data": json_model(item)}

        def create_item(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
            try:
                model = model_type.model_validate(payload)
                item, undo = repository(request).create(resource, model)
            except ValidationError as error:
                raise HTTPException(422, detail=error.errors(include_url=False)) from error
            except sqlite3.IntegrityError as error:
                raise HTTPException(409, detail="Resource already exists or violates a data constraint.") from error
            return {"data": json_model(item), "undo": undo}

        def patch_item(resource_id: str, payload: ResourcePatch, request: Request) -> dict[str, Any]:
            try:
                result = repository(request).update(resource, resource_id, payload.data)
            except ValidationError as error:
                raise HTTPException(422, detail=error.errors(include_url=False)) from error
            if result is None:
                raise HTTPException(404, detail="Resource was not found.")
            item, undo = result
            return {"data": json_model(item), "undo": undo}

        def delete_item(resource_id: str, request: Request) -> dict[str, Any]:
            result = repository(request).delete(resource, resource_id)
            if result is None:
                raise HTTPException(404, detail="Resource was not found.")
            item, undo = result
            return {"data": json_model(item), "undo": undo}

        app.add_api_route(path, list_items, methods=["GET"], name=f"list-{resource}")
        app.add_api_route(path, create_item, methods=["POST"], name=f"create-{resource}", status_code=201)
        app.add_api_route(f"{path}/{{resource_id}}", get_item, methods=["GET"], name=f"get-{resource}")
        app.add_api_route(f"{path}/{{resource_id}}", patch_item, methods=["PATCH"], name=f"patch-{resource}")
        app.add_api_route(f"{path}/{{resource_id}}", delete_item, methods=["DELETE"], name=f"delete-{resource}")

    for resource_name in RESOURCE_CONFIG:
        register_resource(resource_name)

    @app.get("/api/v1/account-options")
    def list_account_options(request: Request) -> dict[str, Any]:
        rows = request.app.state.database.execute(
            "SELECT account FROM account_options ORDER BY sort_order, account COLLATE NOCASE"
        ).fetchall()
        return {"data": [row[0] for row in rows]}

    @app.put("/api/v1/account-options")
    def replace_account_options(request: Request, payload: list[str] = Body(...)) -> dict[str, Any]:
        if any(not item.strip() for item in payload) or len(set(payload)) != len(payload):
            raise HTTPException(422, detail="Account options must be nonblank and unique.")
        repo = repository(request)
        old = [row[0] for row in request.app.state.database.execute("SELECT account FROM account_options ORDER BY sort_order")]
        from finance_core.database import transaction
        with transaction(request.app.state.database):
            request.app.state.database.execute("DELETE FROM account_options")
            request.app.state.database.executemany(
                "INSERT INTO account_options(account, sort_order) VALUES (?, ?)",
                [(account, index) for index, account in enumerate(payload)],
            )
            undo = repo._save_undo("account-options", "account-options", "account-options", {"items": old})
        return {"data": payload, "undo": undo}

    @app.get("/api/v1/export")
    def export_bundle(request: Request) -> dict[str, Any]:
        return {"data": repository(request).export_bundle(), "formatVersion": 1}

    @app.post("/api/v1/import", status_code=201)
    def import_bundle(payload: ImportBundle, request: Request) -> dict[str, Any]:
        data = payload.model_dump(by_alias=True)
        try:
            counts = repository(request).replace_bundle(data)
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, detail="Import contains duplicate ids or broken references.") from error
        return {"imported": counts, "undo": None}

    @app.get("/api/v1/transactions/export.csv")
    def export_transactions_csv(request: Request) -> Response:
        items = [json_model(item) for item in repository(request).list("transactions")]
        output = io.StringIO(newline="")
        fields = list(items[0]) if items else list(RESOURCE_CONFIG["transactions"]["model"].model_fields)
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)
        return Response(output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=transactions.csv"})

    @app.get("/api/v1/export/{resource}.csv")
    def export_resource_csv(resource: str, request: Request) -> Response:
        if resource not in {"transactions", "holdings"}:
            raise HTTPException(404, detail="CSV export is available for transactions and holdings only.")
        items = [json_model(item) for item in repository(request).list(resource)]
        model_type = RESOURCE_CONFIG[resource]["model"]
        fields = [field.alias or name for name, field in model_type.model_fields.items()]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)
        return Response(
            "\ufeff" + output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={resource}.csv"},
        )

    @app.post("/api/v1/import/{resource}.csv", status_code=201)
    async def import_resource_csv(resource: str, request: Request) -> dict[str, Any]:
        if resource not in {"transactions", "holdings"}:
            raise HTTPException(404, detail="CSV import is available for transactions and holdings only.")
        raw = (await request.body()).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(raw)))
        model_type = RESOURCE_CONFIG[resource]["model"]
        created = []
        for index, row in enumerate(rows, start=2):
            normalized = {key: (None if value == "" and key in {"rawData", "accountCode", "accountName", "responsibilityCenter", "debit", "credit"} else value) for key, value in row.items()}
            try:
                model = model_type.model_validate(normalized)
                repository(request).create(resource, model)
                created.append(model.id)
            except (ValidationError, sqlite3.IntegrityError) as error:
                raise HTTPException(422, detail=f"CSV row {index} is invalid or duplicates an existing id.") from error
        return {"importedIds": created, "count": len(created)}

    @app.post("/api/v1/recurring-rules/generate-due")
    def generate_due(request: Request, as_of: date = Body(embed=True, alias="asOf")) -> dict[str, Any]:
        repo = repository(request)
        rules = repo.list("recurring-rules")
        generated = []
        operations = []
        period = as_of.strftime("%Y-%m")
        for rule in rules:
            if not rule.enabled or period in rule.generated_periods or rule.start_date[:7] > period:
                continue
            transaction_payload = {
                "id": f"rec-{rule.id}-{period}", "date": as_of.replace(day=min(rule.day_of_month, 28)).isoformat(),
                "account": rule.account, "source": "Recurring rule", "type": "Transfer",
                "category": rule.name, "assetSymbol": "", "amount": rule.debit - rule.credit,
                "currency": rule.currency, "note": rule.description, "ref": rule.id,
                "debit": rule.debit, "credit": rule.credit,
            }
            if repo.get("transactions", transaction_payload["id"]) is not None:
                continue
            RESOURCE_CONFIG["transactions"]["model"].model_validate(transaction_payload)
            operations.extend([
                {"action": "create", "resource": "transactions", "data": transaction_payload},
                {"action": "update", "resource": "recurring-rules", "resourceId": rule.id, "data": {"generatedPeriods": [*rule.generated_periods, period]}},
            ])
            generated.append(transaction_payload["id"])
        undo_info = repo.batch(operations) if operations else None
        return {"generatedTransactionIds": generated, "period": period, "undo": undo_info}

    @app.post("/api/v1/living-accounts/{account_id}/record-balance")
    def record_balance(account_id: str, request: Request, balance: float = Body(embed=True)) -> dict[str, Any]:
        repo = repository(request)
        account = repo.get("living-accounts", account_id)
        if account is None:
            raise HTTPException(404, detail="Living account was not found.")
        now = datetime.now(timezone.utc).isoformat()
        snapshot_payload = {"id": str(uuid4()), "accountId": account_id, "balance": balance, "currency": account.currency, "recordedAt": now}
        snapshot = RESOURCE_CONFIG["living-snapshots"]["model"].model_validate(snapshot_payload)
        undo_info = repo.batch([
            {"action": "update", "resource": "living-accounts", "resourceId": account_id, "data": {"balance": balance, "updatedAt": now}},
            {"action": "create", "resource": "living-snapshots", "data": snapshot_payload},
        ])
        updated = repo.get("living-accounts", account_id)
        return {"data": json_model(updated), "snapshot": json_model(snapshot), "undo": undo_info}

    @app.post("/api/v1/undo")
    def undo(payload: UndoRequest, request: Request) -> dict[str, Any]:
        result = repository(request).undo(payload.undo_token)
        if result is None:
            raise HTTPException(409, detail="Undo token is invalid, expired, consumed, or superseded.")
        return result

    @app.post("/api/v1/batch")
    def batch(payload: BatchRequest, request: Request) -> dict[str, Any]:
        operations = [item.model_dump(by_alias=True, exclude_none=True) for item in payload.operations]
        try:
            undo_info = repository(request).batch(operations)
        except LookupError as error:
            raise HTTPException(404, detail="A batch resource was not found.") from error
        except (ValidationError, sqlite3.IntegrityError, ValueError) as error:
            raise HTTPException(422, detail="Batch operation failed validation and was rolled back.") from error
        return {"applied": len(operations), "undo": undo_info}

    def load_domain(request: Request) -> tuple[list[Any], list[Any]]:
        repo = repository(request)
        return repo.list("transactions"), repo.list("holdings")

    @app.get("/api/v1/dashboard")
    def get_dashboard(request: Request) -> dict[str, Any]:
        return {"data": dashboard(*load_domain(request))}

    @app.get("/api/v1/t-accounts")
    def get_t_accounts(request: Request) -> dict[str, Any]:
        transactions, _ = load_domain(request)
        return {"data": account_flows(transactions)}

    @app.get("/api/v1/financial-statements")
    def get_financial_statements(request: Request) -> dict[str, Any]:
        return {"data": financial_statements(*load_domain(request))}

    @app.get("/api/v1/reconciliation")
    def get_reconciliation(request: Request) -> dict[str, Any]:
        return {"data": reconciliation(*load_domain(request))}

    @app.get("/api/v1/world")
    def get_world(request: Request) -> dict[str, Any]:
        repo = repository(request)
        transactions, holdings = load_domain(request)
        return {"data": world_metrics(
            repo.list("living-accounts"),
            repo.list("living-snapshots"),
            repo.list("monthly-plans"),
            dashboard(transactions, holdings),
        )}

    app.include_router(create_v2_router())
    return app


from finance_core.app_v3 import create_app

# The legacy factory remains private for data archaeology only. The exported
# application factory and ASGI app are v3-only.
app = create_app(
    data_root=os.environ.get("FINANCE_CORE_DATA_ROOT", str(DEFAULT_DATABASE_PATH.parent / "v3")),
    admin_token=os.environ.get("FINANCE_CORE_ADMIN_TOKEN"),
)
