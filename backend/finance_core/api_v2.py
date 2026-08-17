from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request, Response
from pydantic import ValidationError

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
    return request.app.state.ledger_repository


def translate(error: Exception) -> HTTPException:
    if isinstance(error, LookupError):
        return HTTPException(404, detail=str(error))
    if isinstance(error, sqlite3.IntegrityError):
        return HTTPException(409, detail="Resource already exists or violates a data constraint.")
    if isinstance(error, (ValueError, ValidationError)):
        return HTTPException(422, detail=str(error))
    return HTTPException(500, detail="Finance Core could not complete the operation.")


def create_v2_router() -> APIRouter:
    router = APIRouter(prefix="/api/v2")

    @router.get("/health")
    def health(request: Request) -> dict[str, Any]:
        request.app.state.database.execute("SELECT 1").fetchone()
        return {
            "status": "ok",
            "service": "finance-core",
            "serviceVersion": "2.0.0",
            "apiVersion": "2.0.0",
            "schemaVersion": 2,
            "supportedApiVersions": ["1.0.0-read-only", "2.0.0"],
            "capabilities": [
                "decimal-strings", "commodities", "typed-accounts", "price-quotes",
                "journal-drafts", "aggregate-validation", "atomic-post", "linked-reversal",
                "explicit-fx-valuation", "explicit-lot-allocation", "derived-holdings",
                "t-accounts", "financial-statements", "cash-flow", "reconciliation",
                "recurring-drafts", "draft-import", "living-world", "monthly-plans",
                "json-export", "csv-import-export", "hashed-backup-restore",
                "single-step-undo", "atomic-mutable-batch",
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
        except Exception as error:
            raise translate(error) from error
        if result is None:
            raise HTTPException(409, detail="Undo token is invalid, expired, consumed, or superseded.")
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
