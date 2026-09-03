from __future__ import annotations

import csv
import io
import inspect
import json
import sqlite3
from datetime import date
from functools import wraps
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import ValidationError

from finance_core.contracts_v3 import (
    AccountListResponse,
    AccountMutationResponse,
    BEARER_OR_SESSION_SECURITY,
    CashFlowResponse,
    CommodityListResponse,
    CommodityMutationResponse,
    CompletedPostingResponse,
    DashboardResponse,
    DraftDeleteResponse,
    DraftListResponse,
    DraftMutationResponse,
    DraftSingleResponse,
    DraftValidationResponse,
    FinancialStatementListResponse,
    HoldingResponse,
    HoldingsResponse,
    JournalEntryListResponse,
    JournalEntryReversalResponse,
    JournalEntrySingleResponse,
    LatestUndoResponse,
    LedgerResponse,
    LedgerUndoResponse,
    LivingAccountListResponse,
    LivingAccountMutationResponse,
    LivingBalanceMutationResponse,
    LivingAccountDeleteResponse,
    LivingSnapshotListResponse,
    MonthlyPlanDeleteResponse,
    MonthlyPlanListResponse,
    MonthlyPlanMutationResponse,
    PriceQuoteDeleteResponse,
    PriceQuoteListResponse,
    PriceQuoteMutationResponse,
    ReconciliationResponse,
    RecurringEntryRuleDeleteResponse,
    RecurringEntryRuleListResponse,
    RecurringEntryRuleMutationResponse,
    STANDARD_ERROR_RESPONSES,
    TAccountListResponse,
    WorldResponse,
)
from finance_core.ledger_repository import LedgerRepository, dump
from finance_core.models import UndoRequest
from finance_core.models_v2 import (
    Account,
    Commodity,
    DraftImportRequest,
    JournalEntryDraft,
    LivingAccountV2,
    MonthlyPlanV2,
    MutableBatchV2,
    PriceQuote,
    RecurringEntryRule,
)


def repo(request: Request) -> LedgerRepository:
    scoped = getattr(request.state, "ledger_repository", None)
    return scoped or request.app.state.ledger_repository


def translate(error: Exception) -> HTTPException:
    if isinstance(error, LookupError):
        return HTTPException(404, detail={"code": "RESOURCE_NOT_FOUND", "message": str(error)})
    if isinstance(error, sqlite3.IntegrityError):
        return HTTPException(409, detail={
            "code": "RESOURCE_CONFLICT", "message": "Resource state conflicts with the requested operation."
        })
    if isinstance(error, (ValueError, ValidationError)):
        return HTTPException(422, detail={"code": "INVALID_REQUEST", "message": str(error)})
    return HTTPException(500, detail={
        "code": "REQUEST_FAILED", "message": "Finance Core could not complete the operation."
    })


class LedgerContractRouter(APIRouter):
    """Apply the v3 consumer contract to every reused workspace ledger route."""

    def add_api_route(self, path: str, endpoint: Any, **kwargs: Any) -> None:
        methods = {method.upper() for method in kwargs.get("methods") or ["GET"]}
        write = bool(methods & {"POST", "PUT", "PATCH", "DELETE"}) and not path.endswith("/validate")
        scope = "ledger:write" if write else "ledger:read"
        extra = dict(kwargs.get("openapi_extra") or {})
        extra.update({
            "security": BEARER_OR_SESSION_SECURITY,
            "x-fc-required-scope": scope,
        })
        kwargs["openapi_extra"] = extra
        kwargs["responses"] = {**STANDARD_ERROR_RESPONSES, **(kwargs.get("responses") or {})}
        method = next(iter(methods))
        response_models: dict[tuple[str, str], Any] = {
            ("/commodities", "GET"): CommodityListResponse,
            ("/commodities", "POST"): CommodityMutationResponse,
            ("/commodities/{code}", "PUT"): CommodityMutationResponse,
            ("/accounts", "GET"): AccountListResponse,
            ("/accounts", "POST"): AccountMutationResponse,
            ("/accounts/{account_id}", "PUT"): AccountMutationResponse,
            ("/price-quotes", "GET"): PriceQuoteListResponse,
            ("/price-quotes", "POST"): PriceQuoteMutationResponse,
            ("/price-quotes/{quote_id}", "DELETE"): PriceQuoteDeleteResponse,
            ("/living-accounts", "GET"): LivingAccountListResponse,
            ("/living-accounts", "POST"): LivingAccountMutationResponse,
            ("/living-accounts/{account_id}", "PUT"): LivingAccountMutationResponse,
            ("/living-accounts/{account_id}/record-balance", "POST"): LivingBalanceMutationResponse,
            ("/living-snapshots", "GET"): LivingSnapshotListResponse,
            ("/monthly-plans", "GET"): MonthlyPlanListResponse,
            ("/monthly-plans", "POST"): MonthlyPlanMutationResponse,
            ("/monthly-plans/{plan_id}", "PUT"): MonthlyPlanMutationResponse,
            ("/monthly-plans/{plan_id}", "DELETE"): MonthlyPlanDeleteResponse,
            ("/journal-entry-drafts", "GET"): DraftListResponse,
            ("/journal-entry-drafts", "POST"): DraftMutationResponse,
            ("/journal-entry-drafts/{draft_id}", "GET"): DraftSingleResponse,
            ("/journal-entry-drafts/{draft_id}", "PUT"): DraftMutationResponse,
            ("/journal-entry-drafts/{draft_id}", "DELETE"): DraftDeleteResponse,
            ("/journal-entry-drafts/{draft_id}/validate", "POST"): DraftValidationResponse,
            ("/journal-entry-drafts/{draft_id}/post", "POST"): CompletedPostingResponse,
            ("/journal-entries", "GET"): JournalEntryListResponse,
            ("/journal-entries/{entry_id}", "GET"): JournalEntrySingleResponse,
            ("/journal-entries/{entry_id}/reverse", "POST"): JournalEntryReversalResponse,
            ("/recurring-entry-rules", "GET"): RecurringEntryRuleListResponse,
            ("/recurring-entry-rules", "POST"): RecurringEntryRuleMutationResponse,
            ("/recurring-entry-rules/{rule_id}", "PUT"): RecurringEntryRuleMutationResponse,
            ("/recurring-entry-rules/{rule_id}", "DELETE"): RecurringEntryRuleDeleteResponse,
            ("/t-accounts", "GET"): TAccountListResponse,
            ("/dashboard", "GET"): DashboardResponse,
            ("/financial-statements", "GET"): FinancialStatementListResponse,
            ("/cash-flow", "GET"): CashFlowResponse,
            ("/reconciliation", "GET"): ReconciliationResponse,
            ("/world", "GET"): WorldResponse,
            ("/undo/latest", "GET"): LatestUndoResponse,
            ("/undo", "POST"): LedgerUndoResponse,
        }
        if path == "/holdings" and "GET" in methods:
            kwargs["response_model"] = HoldingsResponse
        elif path == "/holdings/{holding_id}" and "GET" in methods:
            kwargs["response_model"] = HoldingResponse
        elif path == "/living-accounts/{account_id}" and "DELETE" in methods:
            kwargs["response_model"] = LivingAccountDeleteResponse
        elif path == "/export/journal-entries.csv":
            kwargs["response_model"] = None
            kwargs["response_class"] = Response
            kwargs["responses"] = {
                **kwargs["responses"],
                200: {
                    "description": "UTF-8 CSV export.",
                    "content": {"text/csv": {"schema": {"$ref": "#/components/schemas/CsvDocument"}}},
                },
            }
        elif (path, method) in response_models:
            kwargs["response_model"] = response_models[(path, method)]
        else:
            kwargs["response_model"] = LedgerResponse
        kwargs["response_model_exclude_unset"] = True

        if inspect.iscoroutinefunction(endpoint):
            @wraps(endpoint)
            async def workspace_endpoint(*args: Any, **call_kwargs: Any) -> Any:
                result = await endpoint(*args, **call_kwargs)
                request = call_kwargs.get("request")
                if isinstance(result, dict) and request is not None:
                    return {**result, "workspaceId": request.state.workspace_id}
                return result
        else:
            @wraps(endpoint)
            def workspace_endpoint(*args: Any, **call_kwargs: Any) -> Any:
                result = endpoint(*args, **call_kwargs)
                request = call_kwargs.get("request")
                if isinstance(result, dict) and request is not None:
                    return {**result, "workspaceId": request.state.workspace_id}
                return result

        super().add_api_route(path, workspace_endpoint, **kwargs)


def create_v2_router(
    *,
    prefix: str = "/api/v2",
    dependencies: list[Any] | None = None,
    service_version: str = "2.0.0",
    api_version: str = "2.0.0",
) -> APIRouter:
    router_type = LedgerContractRouter if prefix.startswith("/api/v3/workspaces/") else APIRouter
    router = router_type(prefix=prefix, dependencies=dependencies or [])

    @router.get("/health")
    def health(request: Request) -> dict[str, Any]:
        database = getattr(request.state, "database", None) or request.app.state.database
        database.execute("SELECT 1").fetchone()
        return {
            "status": "ok",
            "service": "finance-core",
            "serviceVersion": service_version,
            "apiVersion": api_version,
            "ledgerSchemaVersion": 2,
            "registrySchemaVersion": 1 if api_version.startswith("3.") else None,
            "supportedApiVersions": [api_version],
            "capabilities": [
                "decimal-strings", "commodities", "typed-accounts", "price-quotes",
                "journal-drafts", "aggregate-validation", "atomic-post", "linked-reversal",
                "explicit-fx-valuation", "explicit-lot-allocation", "derived-holdings",
                "t-accounts", "financial-statements", "cash-flow", "reconciliation",
                "recurring-drafts", "draft-import", "living-world", "monthly-plans",
                "json-export", "csv-import-export", "hashed-backup-restore",
                "single-step-undo", "atomic-mutable-batch", "workspace-scoped",
            ],
        }

    @router.get("/commodities")
    def list_commodities(request: Request) -> dict[str, Any]:
        return {"data": [dump(item) for item in repo(request).list_commodities()]}

    @router.get("/undo/latest")
    def latest_undo(request: Request) -> dict[str, Any]:
        return {"data": repo(request).latest_undo()}

    @router.post("/undo")
    def undo(payload: UndoRequest, request: Request) -> dict[str, Any]:
        try:
            result = repo(request).undo(payload.undo_token)
        except ValueError as error:
            raise HTTPException(409, detail={"code": "UNDO_CONFLICT", "message": str(error)}) from error
        if result is None:
            raise HTTPException(410, detail={
                "code": "UNDO_EXPIRED",
                "message": "Undo token is invalid, expired, consumed, or superseded.",
            })
        return result

    @router.post("/batch")
    def mutable_batch(payload: MutableBatchV2, request: Request) -> dict[str, Any]:
        try:
            return {"applied": repo(request).mutable_batch(payload), "undo": repo(request).latest_undo()}
        except Exception as error:
            raise translate(error) from error

    @router.post("/commodities", status_code=201)
    def create_commodity(item: Commodity, request: Request) -> dict[str, Any]:
        try:
            return {"data": dump(repo(request).save_commodity(item, create=True))}
        except Exception as error:
            raise translate(error) from error

    @router.put("/commodities/{code}")
    def update_commodity(code: str, item: Commodity, request: Request) -> dict[str, Any]:
        if item.code != code.upper():
            raise HTTPException(422, detail="Commodity code cannot be changed.")
        try:
            return {"data": dump(repo(request).save_commodity(item, create=False))}
        except Exception as error:
            raise translate(error) from error

    @router.get("/accounts")
    def list_accounts(request: Request) -> dict[str, Any]:
        return {"data": [dump(item) for item in repo(request).list_accounts()]}

    @router.post("/accounts", status_code=201)
    def create_account(item: Account, request: Request) -> dict[str, Any]:
        try:
            return {"data": dump(repo(request).save_account(item, create=True))}
        except Exception as error:
            raise translate(error) from error

    @router.put("/accounts/{account_id}")
    def update_account(account_id: str, item: Account, request: Request) -> dict[str, Any]:
        if item.id != account_id:
            raise HTTPException(422, detail="Account id cannot be changed.")
        try:
            return {"data": dump(repo(request).save_account(item, create=False))}
        except Exception as error:
            raise translate(error) from error

    @router.get("/price-quotes")
    def list_price_quotes(request: Request) -> dict[str, Any]:
        return {"data": [dump(item) for item in repo(request).list_price_quotes()]}

    @router.post("/price-quotes", status_code=201)
    def create_price_quote(item: PriceQuote, request: Request) -> dict[str, Any]:
        try:
            return {"data": dump(repo(request).create_price_quote(item))}
        except Exception as error:
            raise translate(error) from error

    @router.delete("/price-quotes/{quote_id}")
    def delete_price_quote(quote_id: str, request: Request) -> dict[str, Any]:
        if not repo(request).delete_price_quote(quote_id):
            raise HTTPException(404, detail="Price quote was not found.")
        return {"deleted": True, "id": quote_id}

    @router.get("/living-accounts")
    def list_living_accounts(request: Request) -> dict[str, Any]:
        return {"data": [dump(item) for item in repo(request).list_living_accounts()]}

    @router.post("/living-accounts", status_code=201)
    def create_living_account(item: LivingAccountV2, request: Request) -> dict[str, Any]:
        try:
            return {"data": dump(repo(request).save_living_account(item, create=True))}
        except Exception as error:
            raise translate(error) from error

    @router.put("/living-accounts/{account_id}")
    def update_living_account(account_id: str, item: LivingAccountV2, request: Request) -> dict[str, Any]:
        if item.id != account_id:
            raise HTTPException(422, detail="Living account id cannot be changed.")
        try:
            return {"data": dump(repo(request).save_living_account(item, create=False))}
        except Exception as error:
            raise translate(error) from error

    @router.delete("/living-accounts/{account_id}")
    def delete_living_account(account_id: str, request: Request) -> dict[str, Any]:
        result = repo(request).delete_living_account(account_id)
        if result is None:
            raise HTTPException(404, detail={
                "code": "RESOURCE_NOT_FOUND", "message": "Living account was not found."
            })
        account, snapshot_count, undo = result
        workspace_id = getattr(request.state, "workspace_id", None)
        operation = {
            **undo,
            "operationId": str(uuid4()),
            "workspaceId": workspace_id,
            "operationType": "living-account.delete",
        }
        return {
            "data": dump(account),
            "deletedSnapshotCount": snapshot_count,
            "undo": operation,
        }

    @router.post("/living-accounts/{account_id}/record-balance")
    def record_living_balance(account_id: str, request: Request, balance: str = Body(embed=True)) -> dict[str, Any]:
        try:
            account, snapshot = repo(request).record_living_balance(account_id, balance)
            return {"data": dump(account), "snapshot": dump(snapshot)}
        except Exception as error:
            raise translate(error) from error

    @router.get("/living-snapshots")
    def list_living_snapshots(request: Request) -> dict[str, Any]:
        return {"data": [dump(item) for item in repo(request).list_living_snapshots()]}

    @router.get("/monthly-plans")
    def list_monthly_plans(request: Request) -> dict[str, Any]:
        return {"data": [dump(item) for item in repo(request).list_monthly_plans()]}

    @router.post("/monthly-plans", status_code=201)
    def create_monthly_plan(item: MonthlyPlanV2, request: Request) -> dict[str, Any]:
        try:
            return {"data": dump(repo(request).save_monthly_plan(item, create=True))}
        except Exception as error:
            raise translate(error) from error

    @router.put("/monthly-plans/{plan_id}")
    def update_monthly_plan(plan_id: str, item: MonthlyPlanV2, request: Request) -> dict[str, Any]:
        if item.id != plan_id:
            raise HTTPException(422, detail="Monthly plan id cannot be changed.")
        try:
            return {"data": dump(repo(request).save_monthly_plan(item, create=False))}
        except Exception as error:
            raise translate(error) from error

    @router.delete("/monthly-plans/{plan_id}")
    def delete_monthly_plan(plan_id: str, request: Request) -> dict[str, Any]:
        if not repo(request).delete_monthly_plan(plan_id):
            raise HTTPException(404, detail="Monthly plan was not found.")
        return {"deleted": True, "id": plan_id}

    @router.get("/journal-entry-drafts")
    def list_drafts(request: Request) -> dict[str, Any]:
        return {"data": repo(request).list_drafts()}

    @router.post("/journal-entry-drafts", status_code=201)
    def create_draft(item: JournalEntryDraft, request: Request) -> dict[str, Any]:
        try:
            return {"data": repo(request).create_draft(item)}
        except Exception as error:
            raise translate(error) from error

    @router.get("/journal-entry-drafts/{draft_id}")
    def get_draft(draft_id: str, request: Request) -> dict[str, Any]:
        item = repo(request).get_draft(draft_id)
        if item is None:
            raise HTTPException(404, detail="Draft was not found.")
        return {"data": item}

    @router.put("/journal-entry-drafts/{draft_id}")
    def update_draft(draft_id: str, item: JournalEntryDraft, request: Request) -> dict[str, Any]:
        try:
            return {"data": repo(request).update_draft(draft_id, item)}
        except Exception as error:
            raise translate(error) from error

    @router.delete("/journal-entry-drafts/{draft_id}")
    def delete_draft(draft_id: str, request: Request) -> dict[str, Any]:
        if not repo(request).delete_draft(draft_id):
            raise HTTPException(404, detail="Draft was not found or is already posted.")
        return {"deleted": True, "id": draft_id}

    @router.post("/journal-entry-drafts/{draft_id}/validate")
    def validate_draft(draft_id: str, request: Request) -> dict[str, Any]:
        stored = repo(request).get_draft(draft_id)
        if stored is None:
            raise HTTPException(404, detail="Draft was not found.")
        item = JournalEntryDraft.model_validate(stored["draft"])
        completed, issues = repo(request).validate_draft(item)
        return {
            "valid": completed is not None,
            "preview": dump(completed) if completed else None,
            "issues": [dump(issue) for issue in issues],
        }

    @router.post("/journal-entry-drafts/{draft_id}/post")
    def post_draft(draft_id: str, request: Request) -> dict[str, Any]:
        try:
            result = repo(request).post_draft(draft_id)
        except Exception as error:
            raise translate(error) from error
        if not result["posted"]:
            raise HTTPException(422, detail={"code": "DRAFT_INVALID", "issues": result["issues"]})
        return result

    @router.get("/journal-entries")
    def list_entries(request: Request) -> dict[str, Any]:
        return {"data": repo(request).list_entries()}

    @router.get("/journal-entries/{entry_id}")
    def get_entry(entry_id: str, request: Request) -> dict[str, Any]:
        item = repo(request).get_entry(entry_id)
        if item is None:
            raise HTTPException(404, detail="Entry was not found.")
        return {"data": item}

    @router.post("/journal-entries/{entry_id}/reverse", status_code=201)
    def reverse_entry(entry_id: str, request: Request) -> dict[str, Any]:
        try:
            return {"data": repo(request).reverse_entry(entry_id)}
        except Exception as error:
            raise translate(error) from error

    @router.get("/recurring-entry-rules")
    def list_recurring_rules(request: Request) -> dict[str, Any]:
        return {"data": [dump(item) for item in repo(request).list_recurring_rules()]}

    @router.post("/recurring-entry-rules", status_code=201)
    def create_recurring_rule(item: RecurringEntryRule, request: Request) -> dict[str, Any]:
        try:
            return {"data": dump(repo(request).save_recurring_rule(item, create=True))}
        except Exception as error:
            raise translate(error) from error

    @router.put("/recurring-entry-rules/{rule_id}")
    def update_recurring_rule(rule_id: str, item: RecurringEntryRule, request: Request) -> dict[str, Any]:
        if item.id != rule_id:
            raise HTTPException(422, detail="Recurring rule id cannot be changed.")
        try:
            return {"data": dump(repo(request).save_recurring_rule(item, create=False))}
        except Exception as error:
            raise translate(error) from error

    @router.delete("/recurring-entry-rules/{rule_id}")
    def delete_recurring_rule(rule_id: str, request: Request) -> dict[str, Any]:
        if not repo(request).delete_recurring_rule(rule_id):
            raise HTTPException(404, detail="Recurring rule was not found.")
        return {"deleted": True, "id": rule_id}

    @router.post("/recurring-entry-rules/generate-due")
    def generate_due(request: Request, as_of: date = Body(embed=True, alias="asOf")) -> dict[str, Any]:
        return {"generatedDraftIds": repo(request).generate_due_drafts(as_of), "period": as_of.strftime("%Y-%m")}

    @router.post("/import/drafts", status_code=201)
    def import_drafts(payload: DraftImportRequest, request: Request) -> dict[str, Any]:
        try:
            result = repo(request).import_drafts(payload)
        except Exception as error:
            raise translate(error) from error
        if result["imported"] == 0:
            raise HTTPException(422, detail={"code": "IMPORT_INVALID", **result})
        return result

    @router.post("/import/drafts.csv", status_code=201)
    async def import_drafts_csv(request: Request) -> dict[str, Any]:
        raw = (await request.body()).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(raw)))
        grouped: dict[str, dict[str, Any]] = {}
        try:
            for line, row in enumerate(rows, start=2):
                entry_id = (row.get("entryId") or "").strip()
                if not entry_id:
                    raise ValueError(f"CSV row {line} is missing entryId.")
                draft = grouped.setdefault(entry_id, {
                    "id": entry_id,
                    "date": row.get("date", ""),
                    "description": row.get("description", ""),
                    "payee": row.get("payee", ""),
                    "source": row.get("source", "csv"),
                    "reference": row.get("reference", ""),
                    "tags": [tag.strip() for tag in row.get("tags", "").split("|") if tag.strip()],
                    "balancingCommodityCode": row.get("balancingCommodityCode", ""),
                    "postings": [],
                })
                posting: dict[str, Any] = {
                    "id": row.get("postingId", ""),
                    "accountId": row.get("accountId", ""),
                    "side": row.get("side", ""),
                    "units": row.get("units", ""),
                    "commodityCode": row.get("commodityCode", ""),
                    "memo": row.get("memo", ""),
                    "cashFlowCategory": row.get("cashFlowCategory", "other") or "other",
                }
                for csv_key, contract_key in (("valuationRate", "valuationRate"), ("rateType", "rateType"), ("lotAction", "lotAction"), ("lotId", "lotId")):
                    if row.get(csv_key):
                        posting[contract_key] = row[csv_key]
                if row.get("lotAllocationsJson"):
                    posting["lotAllocations"] = json.loads(row["lotAllocationsJson"])
                draft["postings"].append(posting)
            payload = DraftImportRequest(drafts=[JournalEntryDraft.model_validate(item) for item in grouped.values()])
            result = repo(request).import_drafts(payload)
        except Exception as error:
            raise translate(error) from error
        if result["imported"] == 0:
            raise HTTPException(422, detail={"code": "IMPORT_INVALID", **result})
        return result

    @router.get("/export")
    def export_bundle(request: Request) -> dict[str, Any]:
        return {"data": repo(request).export_bundle()}

    @router.get("/backup")
    def create_backup(request: Request) -> dict[str, Any]:
        return {"data": repo(request).create_backup()}

    @router.post("/backup/restore", status_code=201)
    def restore_backup(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            return {"restored": repo(request).restore_backup(payload)}
        except Exception as error:
            raise translate(error) from error

    @router.get("/export/journal-entries.csv")
    def export_entries_csv(request: Request) -> Response:
        output = io.StringIO(newline="")
        fields = [
            "entryId", "date", "description", "postingId", "accountId", "side", "units",
            "commodityCode", "valuationRate", "valuationAmount", "rateType", "cashFlowCategory",
        ]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for entry in repo(request).list_entries():
            for posting in entry["postings"]:
                writer.writerow({
                    "entryId": entry["id"], "date": entry["date"], "description": entry["description"],
                    "postingId": posting["id"], "accountId": posting["accountId"], "side": posting["side"],
                    "units": posting["units"], "commodityCode": posting["commodityCode"],
                    "valuationRate": posting["valuationRate"], "valuationAmount": posting["valuationAmount"],
                    "rateType": posting["rateType"], "cashFlowCategory": posting["cashFlowCategory"],
                })
        return Response(
            "\ufeff" + output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=journal-entries-v2.csv"},
        )

    @router.get("/holdings")
    def holdings(request: Request) -> dict[str, Any]:
        return {"data": repo(request).holdings(), "readOnly": True}

    @router.get("/holdings/{holding_id}")
    def get_holding(holding_id: str, request: Request) -> dict[str, Any]:
        item = repo(request).get_holding(holding_id)
        if item is None:
            raise HTTPException(404, detail={
                "code": "RESOURCE_NOT_FOUND", "message": "Holding was not found."
            })
        return {"data": item, "readOnly": True}

    @router.get("/t-accounts")
    def t_accounts(request: Request) -> dict[str, Any]:
        return {"data": repo(request).account_flows()}

    @router.get("/dashboard")
    def dashboard(request: Request) -> dict[str, Any]:
        return {"data": repo(request).dashboard()}

    @router.get("/financial-statements")
    def statements(request: Request) -> dict[str, Any]:
        return {"data": repo(request).financial_statements()}

    @router.get("/cash-flow")
    def cash_flow(request: Request) -> dict[str, Any]:
        return {"data": repo(request).cash_flow()}

    @router.get("/reconciliation")
    def reconciliation(request: Request) -> dict[str, Any]:
        return {"data": repo(request).reconciliation()}

    @router.get("/world")
    def world(request: Request) -> dict[str, Any]:
        return {"data": repo(request).world()}

    @router.post("/demo/load-synthetic", status_code=201)
    def load_synthetic(request: Request) -> dict[str, Any]:
        workspace = getattr(request.state, "workspace", None)
        if workspace is not None and workspace["kind"] != "sandbox":
            raise HTTPException(403, detail="Synthetic data can only be loaded into a sandbox workspace.")
        ledger = repo(request)
        if ledger.list_commodities() or ledger.list_accounts():
            raise HTTPException(409, detail="Synthetic demo data can only be loaded into an empty v2 ledger.")
        try:
            commodities = [
                Commodity(code="CNY", kind="currency", scale=2, name="Chinese Yuan"),
                Commodity(code="DEMO", kind="security", scale=4, name="Synthetic Fund"),
            ]
            accounts = [
                Account(id="cash", code="1001", name="Synthetic Cash", type="asset", subtype="cash", allowedCommodityCodes=["CNY"]),
                Account(id="investment", code="1101", name="Synthetic Investment", type="asset", subtype="investment", allowedCommodityCodes=["DEMO"]),
                Account(id="capital", code="3001", name="Synthetic Opening Capital", type="equity", allowedCommodityCodes=["CNY"]),
                Account(id="gain", code="4001", name="Synthetic Investment Gain", type="income", subtype="realized-gain", allowedCommodityCodes=["CNY"]),
                Account(id="expense", code="6001", name="Synthetic Expense", type="expense", allowedCommodityCodes=["CNY"]),
            ]
            draft = JournalEntryDraft.model_validate({
                "id": "demo-opening",
                "date": date.today().isoformat(),
                "description": "Synthetic opening balance",
                "balancingCommodityCode": "CNY",
                "postings": [
                    {"id": "demo-opening-p1", "accountId": "cash", "side": "debit", "units": "10000", "commodityCode": "CNY", "cashFlowCategory": "financing"},
                    {"id": "demo-opening-p2", "accountId": "capital", "side": "credit", "units": "10000", "commodityCode": "CNY", "cashFlowCategory": "financing"},
                ],
            })
            ledger.mutable_batch(MutableBatchV2(commodities=commodities, accounts=accounts, drafts=[draft]))
        except Exception as error:
            raise translate(error) from error
        return {"loaded": True, "draftId": "demo-opening"}

    return router
