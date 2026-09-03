from __future__ import annotations

import json
import hashlib
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from finance_core.database import transaction
from finance_core.ledger import complete_entry, normal_balance, quantize
from finance_core.models_v2 import (
    Account,
    Commodity,
    CompletedEntry,
    DraftImportRequest,
    JournalEntryDraft,
    LivingAccountV2,
    LivingSnapshotV2,
    MonthlyPlanV2,
    MutableBatchV2,
    PriceQuote,
    RecurringEntryRule,
    ValidationIssue,
    canonical_decimal,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(model: Any) -> dict[str, Any]:
    return model.model_dump(by_alias=True, exclude_none=True)


class LedgerRepository:
    MUTABLE_TABLES = [
        "commodities_v2", "accounts_v2", "price_quotes_v2", "journal_drafts_v2",
        "journal_entries_v2", "postings_v2", "lots_v2", "lot_movements_v2",
        "recurring_entry_rules_v2", "living_accounts_v2", "living_snapshots_v2", "monthly_plans_v2",
    ]
    MUTABLE_DELETE_ORDER = [
        "lot_movements_v2", "lots_v2", "postings_v2", "journal_entries_v2",
        "price_quotes_v2", "journal_drafts_v2", "recurring_entry_rules_v2",
        "living_snapshots_v2", "monthly_plans_v2", "living_accounts_v2", "accounts_v2", "commodities_v2",
    ]

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    # Master data ---------------------------------------------------------
    def list_commodities(self) -> list[Commodity]:
        rows = self.connection.execute("SELECT * FROM commodities_v2 ORDER BY code").fetchall()
        return [Commodity.model_validate(dict(row)) for row in rows]

    def get_commodity(self, code: str) -> Commodity | None:
        row = self.connection.execute("SELECT * FROM commodities_v2 WHERE code = ?", (code.upper(),)).fetchone()
        return Commodity.model_validate(dict(row)) if row else None

    def save_commodity(self, item: Commodity, *, create: bool) -> Commodity:
        before = self._mutable_snapshot()
        with transaction(self.connection):
            if create:
                self.connection.execute(
                    "INSERT INTO commodities_v2(code,kind,scale,name,status) VALUES (?,?,?,?,?)",
                    (item.code, item.kind, item.scale, item.name, item.status),
                )
            else:
                result = self.connection.execute(
                    "UPDATE commodities_v2 SET kind=?,scale=?,name=?,status=? WHERE code=?",
                    (item.kind, item.scale, item.name, item.status, item.code),
                )
                if result.rowcount == 0:
                    raise LookupError("Commodity was not found.")
            self._save_undo(before)
        return item

    def list_accounts(self) -> list[Account]:
        rows = self.connection.execute("SELECT * FROM accounts_v2 ORDER BY code, id").fetchall()
        return [self._account_from_row(row) for row in rows]

    def get_account(self, account_id: str) -> Account | None:
        row = self.connection.execute("SELECT * FROM accounts_v2 WHERE id = ?", (account_id,)).fetchone()
        return self._account_from_row(row) if row else None

    def save_account(self, item: Account, *, create: bool) -> Account:
        for code in item.allowed_commodity_codes:
            if self.get_commodity(code) is None:
                raise ValueError(f"Unknown commodity: {code}")
        values = (
            item.code,
            item.name,
            item.type,
            item.subtype,
            json.dumps(item.allowed_commodity_codes, ensure_ascii=False, separators=(",", ":")),
            item.status,
        )
        before = self._mutable_snapshot()
        with transaction(self.connection):
            if create:
                self.connection.execute(
                    "INSERT INTO accounts_v2(id,code,name,type,subtype,allowed_commodities_json,status) VALUES (?,?,?,?,?,?,?)",
                    (item.id, *values),
                )
            else:
                result = self.connection.execute(
                    "UPDATE accounts_v2 SET code=?,name=?,type=?,subtype=?,allowed_commodities_json=?,status=? WHERE id=?",
                    (*values, item.id),
                )
                if result.rowcount == 0:
                    raise LookupError("Account was not found.")
            self._save_undo(before)
        return item

    def list_price_quotes(self) -> list[PriceQuote]:
        rows = self.connection.execute("SELECT * FROM price_quotes_v2 ORDER BY as_of DESC, id").fetchall()
        return [self._quote_from_row(row) for row in rows]

    def create_price_quote(self, item: PriceQuote) -> PriceQuote:
        base = self.get_commodity(item.commodity_code)
        quote = self.get_commodity(item.quote_commodity_code)
        if base is None or quote is None:
            raise ValueError("Price quote commodities must exist.")
        normalized = quantize(Decimal(item.price), quote.scale)
        if normalized != Decimal(item.price):
            raise ValueError("Price contains more fractional digits than quote commodity scale.")
        before = self._mutable_snapshot()
        with transaction(self.connection):
            self.connection.execute(
                "INSERT INTO price_quotes_v2(id,commodity_code,quote_commodity_code,price,as_of,source) VALUES (?,?,?,?,?,?)",
                (item.id, item.commodity_code, item.quote_commodity_code, item.price, item.as_of, item.source),
            )
            self._save_undo(before)
        return item

    def delete_price_quote(self, quote_id: str) -> bool:
        before = self._mutable_snapshot()
        with transaction(self.connection):
            deleted = self.connection.execute("DELETE FROM price_quotes_v2 WHERE id=?", (quote_id,)).rowcount > 0
            if deleted:
                self._save_undo(before)
            return deleted

    def list_living_accounts(self) -> list[LivingAccountV2]:
        rows = self.connection.execute("SELECT * FROM living_accounts_v2 ORDER BY name,id").fetchall()
        return [LivingAccountV2.model_validate({
            "id": row["id"], "name": row["name"], "commodityCode": row["commodity_code"],
            "balance": row["balance"], "note": row["note"], "updatedAt": row["updated_at"],
        }) for row in rows]

    def save_living_account(self, item: LivingAccountV2, *, create: bool) -> LivingAccountV2:
        self._require_scale(item.balance, item.commodity_code, "balance")
        values = (item.name, item.commodity_code, item.balance, item.note, item.updated_at)
        before = self._mutable_snapshot()
        with transaction(self.connection):
            if create:
                self.connection.execute(
                    "INSERT INTO living_accounts_v2(id,name,commodity_code,balance,note,updated_at) VALUES (?,?,?,?,?,?)",
                    (item.id, *values),
                )
            else:
                result = self.connection.execute(
                    "UPDATE living_accounts_v2 SET name=?,commodity_code=?,balance=?,note=?,updated_at=? WHERE id=?",
                    (*values, item.id),
                )
                if result.rowcount == 0:
                    raise LookupError("Living account was not found.")
            self._save_undo(before)
        return item

    def list_living_snapshots(self) -> list[LivingSnapshotV2]:
        rows = self.connection.execute("SELECT * FROM living_snapshots_v2 ORDER BY recorded_at,id").fetchall()
        return [LivingSnapshotV2.model_validate({
            "id": row["id"], "accountId": row["account_id"], "balance": row["balance"],
            "commodityCode": row["commodity_code"], "recordedAt": row["recorded_at"],
        }) for row in rows]

    def record_living_balance(self, account_id: str, balance: str) -> tuple[LivingAccountV2, LivingSnapshotV2]:
        account = next((item for item in self.list_living_accounts() if item.id == account_id), None)
        if account is None:
            raise LookupError("Living account was not found.")
        normalized = canonical_decimal(balance)
        self._require_scale(normalized, account.commodity_code, "balance")
        timestamp = now_iso()
        snapshot = LivingSnapshotV2(
            id=str(uuid4()), accountId=account_id, balance=normalized,
            commodityCode=account.commodity_code, recordedAt=timestamp,
        )
        updated = account.model_copy(update={"balance": normalized, "updated_at": timestamp})
        before = self._mutable_snapshot()
        with transaction(self.connection):
            self.connection.execute(
                "UPDATE living_accounts_v2 SET balance=?,updated_at=? WHERE id=?",
                (normalized, timestamp, account_id),
            )
            self.connection.execute(
                "INSERT INTO living_snapshots_v2(id,account_id,balance,commodity_code,recorded_at) VALUES (?,?,?,?,?)",
                (snapshot.id, snapshot.account_id, snapshot.balance, snapshot.commodity_code, snapshot.recorded_at),
            )
            self._save_undo(before)
        return updated, snapshot

    def delete_living_account(self, account_id: str) -> tuple[LivingAccountV2, int, dict[str, str]] | None:
        account = next((item for item in self.list_living_accounts() if item.id == account_id), None)
        if account is None:
            return None
        before = self._mutable_snapshot()
        with transaction(self.connection):
            snapshot_count = self.connection.execute(
                "SELECT COUNT(*) FROM living_snapshots_v2 WHERE account_id=?", (account_id,)
            ).fetchone()[0]
            self.connection.execute("DELETE FROM living_snapshots_v2 WHERE account_id=?", (account_id,))
            self.connection.execute("DELETE FROM living_accounts_v2 WHERE id=?", (account_id,))
            undo = self._save_undo(before)
        return account, snapshot_count, undo

    def list_monthly_plans(self) -> list[MonthlyPlanV2]:
        rows = self.connection.execute("SELECT * FROM monthly_plans_v2 ORDER BY kind,start_date,id").fetchall()
        return [MonthlyPlanV2.model_validate({
            "id": row["id"], "kind": row["kind"], "name": row["name"], "amount": row["amount"],
            "commodityCode": row["commodity_code"], "category": row["category"],
            "recurringMonthly": bool(row["recurring_monthly"]), "dayOfMonth": row["day_of_month"],
            "startDate": row["start_date"], "note": row["note"],
        }) for row in rows]

    def save_monthly_plan(self, item: MonthlyPlanV2, *, create: bool) -> MonthlyPlanV2:
        self._require_scale(item.amount, item.commodity_code, "amount")
        values = (
            item.kind, item.name, item.amount, item.commodity_code, item.category,
            int(item.recurring_monthly), item.day_of_month, item.start_date, item.note,
        )
        before = self._mutable_snapshot()
        with transaction(self.connection):
            if create:
                self.connection.execute(
                    "INSERT INTO monthly_plans_v2(id,kind,name,amount,commodity_code,category,recurring_monthly,day_of_month,start_date,note) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (item.id, *values),
                )
            else:
                result = self.connection.execute(
                    "UPDATE monthly_plans_v2 SET kind=?,name=?,amount=?,commodity_code=?,category=?,recurring_monthly=?,day_of_month=?,start_date=?,note=? WHERE id=?",
                    (*values, item.id),
                )
                if result.rowcount == 0:
                    raise LookupError("Monthly plan was not found.")
            self._save_undo(before)
        return item

    def delete_monthly_plan(self, plan_id: str) -> bool:
        before = self._mutable_snapshot()
        with transaction(self.connection):
            deleted = self.connection.execute("DELETE FROM monthly_plans_v2 WHERE id=?", (plan_id,)).rowcount > 0
            if deleted:
                self._save_undo(before)
            return deleted

    # Drafts and posting --------------------------------------------------
    def list_drafts(self, *, include_posted: bool = False) -> list[dict[str, Any]]:
        where = "" if include_posted else "WHERE status='draft'"
        rows = self.connection.execute(
            f"SELECT * FROM journal_drafts_v2 {where} ORDER BY updated_at DESC, id"
        ).fetchall()
        return [self._draft_row(row) for row in rows]

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM journal_drafts_v2 WHERE id=?", (draft_id,)).fetchone()
        return self._draft_row(row) if row else None

    def create_draft(self, draft: JournalEntryDraft) -> dict[str, Any]:
        timestamp = now_iso()
        before = self._mutable_snapshot()
        with transaction(self.connection):
            self.connection.execute(
                "INSERT INTO journal_drafts_v2(id,payload_json,status,created_at,updated_at) VALUES (?,?,?,?,?)",
                (draft.id, json.dumps(dump(draft), ensure_ascii=False, separators=(",", ":")), "draft", timestamp, timestamp),
            )
            self._save_undo(before)
        return {
            "draft": dump(draft),
            "status": "draft",
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "postedEntryId": None,
        }

    def update_draft(self, draft_id: str, draft: JournalEntryDraft) -> dict[str, Any]:
        if draft.id != draft_id:
            raise ValueError("Draft id cannot be changed.")
        timestamp = now_iso()
        before = self._mutable_snapshot()
        with transaction(self.connection):
            result = self.connection.execute(
                "UPDATE journal_drafts_v2 SET payload_json=?,updated_at=? WHERE id=? AND status='draft'",
                (json.dumps(dump(draft), ensure_ascii=False, separators=(",", ":")), timestamp, draft_id),
            )
            if result.rowcount == 0:
                raise LookupError("Draft was not found or is already posted.")
            self._save_undo(before)
        return self.get_draft(draft_id)  # type: ignore[return-value]

    def delete_draft(self, draft_id: str) -> bool:
        before = self._mutable_snapshot()
        with transaction(self.connection):
            deleted = self.connection.execute(
                "DELETE FROM journal_drafts_v2 WHERE id=? AND status='draft'", (draft_id,)
            ).rowcount > 0
            if deleted:
                self._save_undo(before)
            return deleted

    def validate_draft(self, draft: JournalEntryDraft) -> tuple[CompletedEntry | None, list[ValidationIssue]]:
        commodities = {item.code: item for item in self.list_commodities()}
        accounts = {item.id: item for item in self.list_accounts()}
        completed, issues = complete_entry(draft, commodities, accounts)
        if completed is not None:
            issues.extend(self._validate_lot_allocations(completed))
            if issues:
                return None, issues
        return completed, issues

    def post_draft(self, draft_id: str) -> dict[str, Any]:
        stored = self.get_draft(draft_id)
        if stored is None or stored["status"] != "draft":
            raise LookupError("Draft was not found or is already posted.")
        draft = JournalEntryDraft.model_validate(stored["draft"])
        completed, issues = self.validate_draft(draft)
        if completed is None:
            return {"posted": False, "issues": [dump(item) for item in issues]}
        timestamp = now_iso()
        with transaction(self.connection):
            if self.connection.execute("SELECT 1 FROM journal_entries_v2 WHERE id=?", (completed.id,)).fetchone():
                raise ValueError("Entry id already exists.")
            self._insert_completed(completed, timestamp=timestamp, reversal_of=None)
            self._apply_lots(completed)
            result = self.connection.execute(
                "UPDATE journal_drafts_v2 SET status='posted',posted_entry_id=?,updated_at=? WHERE id=? AND status='draft'",
                (completed.id, timestamp, draft_id),
            )
            if result.rowcount != 1:
                raise ValueError("Draft state changed while posting.")
            self._invalidate_undo()
        return {"posted": True, "entry": self.get_entry(completed.id), "issues": []}

    # Immutable entries --------------------------------------------------
    def list_entries(self) -> list[dict[str, Any]]:
        ids = [row[0] for row in self.connection.execute(
            "SELECT id FROM journal_entries_v2 ORDER BY date DESC, posted_at DESC, id"
        )]
        return [self.get_entry(entry_id) for entry_id in ids]  # type: ignore[list-item]

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM journal_entries_v2 WHERE id=?", (entry_id,)).fetchone()
        if row is None:
            return None
        postings = self.connection.execute(
            "SELECT * FROM postings_v2 WHERE entry_id=? ORDER BY sort_order", (entry_id,)
        ).fetchall()
        return {
            "id": row["id"],
            "date": row["date"],
            "description": row["description"],
            "payee": row["payee"],
            "source": row["source"],
            "reference": row["reference"],
            "tags": json.loads(row["tags_json"]),
            "balancingCommodityCode": row["balancing_commodity_code"],
            "postedAt": row["posted_at"],
            "reversalOf": row["reversal_of"],
            "postings": [self._posting_from_row(item) for item in postings],
        }

    def reverse_entry(self, entry_id: str) -> dict[str, Any]:
        original = self.get_entry(entry_id)
        if original is None:
            raise LookupError("Entry was not found.")
        if original["reversalOf"] is not None:
            raise ValueError("A reversal entry cannot be reversed again.")
        if self.connection.execute("SELECT 1 FROM journal_entries_v2 WHERE reversal_of=?", (entry_id,)).fetchone():
            raise ValueError("Entry already has a reversal.")
        reverse_id = f"rev-{entry_id}-{uuid4().hex[:8]}"
        timestamp = now_iso()
        with transaction(self.connection):
            self.connection.execute(
                "INSERT INTO journal_entries_v2(id,date,description,payee,source,reference,tags_json,balancing_commodity_code,posted_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    reverse_id,
                    date.today().isoformat(),
                    f"Reversal: {original['description']}",
                    original["payee"],
                    "reversal",
                    original["reference"],
                    json.dumps(original["tags"], ensure_ascii=False),
                    original["balancingCommodityCode"],
                    timestamp,
                    entry_id,
                ),
            )
            reverse_posting_ids: dict[str, str] = {}
            for index, posting in enumerate(original["postings"]):
                posting_id = f"{reverse_id}-p{index + 1}"
                reverse_posting_ids[posting["id"]] = posting_id
                self.connection.execute(
                    "INSERT INTO postings_v2(id,entry_id,sort_order,account_id,side,units,commodity_code,valuation_rate,valuation_amount,rate_type,memo,cash_flow_category,lot_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        posting_id,
                        reverse_id,
                        index,
                        posting["accountId"],
                        "credit" if posting["side"] == "debit" else "debit",
                        posting["units"],
                        posting["commodityCode"],
                        posting["valuationRate"],
                        posting["valuationAmount"],
                        posting["rateType"],
                        f"Reversal: {posting['memo']}",
                        posting["cashFlowCategory"],
                        json.dumps({"action": "reversal", "ofPostingId": posting["id"]}),
                    ),
                )
            self._reverse_lot_movements(entry_id, reverse_id, reverse_posting_ids)
            self._invalidate_undo()
        return self.get_entry(reverse_id)  # type: ignore[return-value]

    # Recurring and import ------------------------------------------------
    def list_recurring_rules(self) -> list[RecurringEntryRule]:
        rows = self.connection.execute("SELECT payload_json FROM recurring_entry_rules_v2 ORDER BY start_date,id").fetchall()
        return [RecurringEntryRule.model_validate(json.loads(row[0])) for row in rows]

    def save_recurring_rule(self, rule: RecurringEntryRule, *, create: bool) -> RecurringEntryRule:
        payload = json.dumps(dump(rule), ensure_ascii=False, separators=(",", ":"))
        before = self._mutable_snapshot()
        with transaction(self.connection):
            if create:
                self.connection.execute(
                    "INSERT INTO recurring_entry_rules_v2(id,payload_json,enabled,day_of_month,start_date,generated_periods_json) VALUES (?,?,?,?,?,?)",
                    (rule.id, payload, int(rule.enabled), rule.day_of_month, rule.start_date, json.dumps(rule.generated_periods)),
                )
            else:
                result = self.connection.execute(
                    "UPDATE recurring_entry_rules_v2 SET payload_json=?,enabled=?,day_of_month=?,start_date=?,generated_periods_json=? WHERE id=?",
                    (payload, int(rule.enabled), rule.day_of_month, rule.start_date, json.dumps(rule.generated_periods), rule.id),
                )
                if result.rowcount == 0:
                    raise LookupError("Recurring rule was not found.")
            self._save_undo(before)
        return rule

    def delete_recurring_rule(self, rule_id: str) -> bool:
        before = self._mutable_snapshot()
        with transaction(self.connection):
            deleted = self.connection.execute("DELETE FROM recurring_entry_rules_v2 WHERE id=?", (rule_id,)).rowcount > 0
            if deleted:
                self._save_undo(before)
            return deleted

    def generate_due_drafts(self, as_of: date) -> list[str]:
        before = self._mutable_snapshot()
        period = as_of.strftime("%Y-%m")
        pending: list[tuple[RecurringEntryRule, JournalEntryDraft]] = []
        for rule in self.list_recurring_rules():
            if not rule.enabled or period in rule.generated_periods or rule.start_date[:7] > period:
                continue
            payload = dump(rule.template)
            payload["id"] = f"rec-{rule.id}-{period}"
            payload["date"] = as_of.replace(day=min(rule.day_of_month, 28)).isoformat()
            for index, posting in enumerate(payload["postings"]):
                posting["id"] = f"{payload['id']}-p{index + 1}"
            draft = JournalEntryDraft.model_validate(payload)
            if self.get_draft(draft.id) is not None:
                continue
            rule.generated_periods.append(period)
            pending.append((rule, draft))
        if pending:
            with transaction(self.connection):
                timestamp = now_iso()
                for rule, draft in pending:
                    self.connection.execute(
                        "INSERT INTO journal_drafts_v2(id,payload_json,status,created_at,updated_at) VALUES (?,?,?,?,?)",
                        (draft.id, json.dumps(dump(draft), ensure_ascii=False, separators=(",", ":")), "draft", timestamp, timestamp),
                    )
                    self.connection.execute(
                        "UPDATE recurring_entry_rules_v2 SET payload_json=?,generated_periods_json=? WHERE id=?",
                        (
                            json.dumps(dump(rule), ensure_ascii=False, separators=(",", ":")),
                            json.dumps(rule.generated_periods, ensure_ascii=False, separators=(",", ":")),
                            rule.id,
                        ),
                    )
                self._save_undo(before)
        return [draft.id for _, draft in pending]

    def import_drafts(self, request: DraftImportRequest) -> dict[str, Any]:
        reports = []
        for draft in request.drafts:
            completed, issues = self.validate_draft(draft)
            reports.append({
                "draftId": draft.id,
                "valid": completed is not None,
                "issues": [dump(item) for item in issues],
            })
        if any(not item["valid"] for item in reports):
            return {"imported": 0, "reports": reports}
        before = self._mutable_snapshot()
        with transaction(self.connection):
            timestamp = now_iso()
            for draft in request.drafts:
                self.connection.execute(
                    "INSERT INTO journal_drafts_v2(id,payload_json,status,created_at,updated_at) VALUES (?,?,?,?,?)",
                    (draft.id, json.dumps(dump(draft), ensure_ascii=False, separators=(",", ":")), "draft", timestamp, timestamp),
                )
            self._save_undo(before)
        return {"imported": len(request.drafts), "reports": reports}

    def mutable_batch(self, batch: MutableBatchV2) -> dict[str, int]:
        before = self._mutable_snapshot()
        commodity_map = {item.code: item for item in self.list_commodities()}
        commodity_map.update({item.code: item for item in batch.commodities})
        for account in batch.accounts:
            if any(code not in commodity_map for code in account.allowed_commodity_codes):
                raise ValueError(f"Batch account {account.id} references an unknown commodity.")
        timestamp = now_iso()
        with transaction(self.connection):
            for item in batch.commodities:
                self.connection.execute(
                    "INSERT INTO commodities_v2(code,kind,scale,name,status) VALUES (?,?,?,?,?)",
                    (item.code, item.kind, item.scale, item.name, item.status),
                )
            for item in batch.accounts:
                self.connection.execute(
                    "INSERT INTO accounts_v2(id,code,name,type,subtype,allowed_commodities_json,status) VALUES (?,?,?,?,?,?,?)",
                    (
                        item.id, item.code, item.name, item.type, item.subtype,
                        json.dumps(item.allowed_commodity_codes, ensure_ascii=False, separators=(",", ":")), item.status,
                    ),
                )
            for item in batch.price_quotes:
                if item.commodity_code not in commodity_map or item.quote_commodity_code not in commodity_map:
                    raise ValueError(f"Batch price quote {item.id} references an unknown commodity.")
                quote = commodity_map[item.quote_commodity_code]
                if quantize(Decimal(item.price), quote.scale) != Decimal(item.price):
                    raise ValueError(f"Batch price quote {item.id} exceeds quote commodity scale.")
                self.connection.execute(
                    "INSERT INTO price_quotes_v2(id,commodity_code,quote_commodity_code,price,as_of,source) VALUES (?,?,?,?,?,?)",
                    (item.id, item.commodity_code, item.quote_commodity_code, item.price, item.as_of, item.source),
                )
            for item in batch.drafts:
                self.connection.execute(
                    "INSERT INTO journal_drafts_v2(id,payload_json,status,created_at,updated_at) VALUES (?,?,?,?,?)",
                    (item.id, json.dumps(dump(item), ensure_ascii=False, separators=(",", ":")), "draft", timestamp, timestamp),
                )
            self._save_undo(before)
        return {
            "commodities": len(batch.commodities),
            "accounts": len(batch.accounts),
            "priceQuotes": len(batch.price_quotes),
            "drafts": len(batch.drafts),
        }

    # Derived read models -------------------------------------------------
    def account_flows(self) -> list[dict[str, Any]]:
        accounts = {item.id: item for item in self.list_accounts()}
        groups: dict[tuple[str, str], dict[str, Decimal | int]] = defaultdict(
            lambda: {"debit": Decimal(0), "credit": Decimal(0), "count": 0}
        )
        rows = self.connection.execute("SELECT account_id,commodity_code,side,units FROM postings_v2").fetchall()
        for row in rows:
            group = groups[(row["account_id"], row["commodity_code"])]
            group[row["side"]] += Decimal(row["units"])
            group["count"] += 1
        output = []
        for (account_id, commodity), values in sorted(groups.items()):
            account = accounts[account_id]
            debit, credit = values["debit"], values["credit"]
            output.append({
                "accountId": account_id,
                "accountCode": account.code,
                "accountName": account.name,
                "accountType": account.type,
                "commodityCode": commodity,
                "debit": canonical_decimal(debit),
                "credit": canonical_decimal(credit),
                "balance": canonical_decimal(normal_balance(account.type, debit, credit)),
                "count": values["count"],
            })
        return output

    def holdings(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM lots_v2 ORDER BY commodity_code,acquired_date,id"
        ).fetchall()
        result = []
        for row in rows:
            if Decimal(row["remaining_units"]) <= 0:
                continue
            quote = self.connection.execute(
                "SELECT * FROM price_quotes_v2 WHERE commodity_code=? AND quote_commodity_code=? ORDER BY as_of DESC,id DESC LIMIT 1",
                (row["commodity_code"], row["cost_commodity_code"]),
            ).fetchone()
            market_value = None
            unrealized = None
            if quote:
                cost_commodity = self.get_commodity(row["cost_commodity_code"])
                assert cost_commodity is not None
                market_value_decimal = quantize(Decimal(row["remaining_units"]) * Decimal(quote["price"]), cost_commodity.scale)
                market_value = canonical_decimal(market_value_decimal)
                unrealized = canonical_decimal(market_value_decimal - Decimal(row["remaining_cost"]))
            result.append({
                "lotId": row["id"],
                "accountId": row["account_id"],
                "commodityCode": row["commodity_code"],
                "acquiredDate": row["acquired_date"],
                "originalUnits": row["original_units"],
                "remainingUnits": row["remaining_units"],
                "originalCost": row["original_cost"],
                "remainingCost": row["remaining_cost"],
                "costCommodityCode": row["cost_commodity_code"],
                "latestPrice": quote["price"] if quote else None,
                "priceAsOf": quote["as_of"] if quote else None,
                "marketValue": market_value,
                "unrealizedPnL": unrealized,
            })
        return result

    def get_holding(self, holding_id: str) -> dict[str, Any] | None:
        return next((item for item in self.holdings() if item["lotId"] == holding_id), None)

    def dashboard(self) -> dict[str, Any]:
        flows = self.account_flows()
        holdings = self.holdings()
        cash: dict[str, Decimal] = defaultdict(Decimal)
        for flow in flows:
            account = self.get_account(flow["accountId"])
            if account and account.type == "asset" and account.subtype.lower() == "cash":
                cash[flow["commodityCode"]] += Decimal(flow["balance"])
        holding_cost: dict[str, Decimal] = defaultdict(Decimal)
        holding_market: dict[str, Decimal] = defaultdict(Decimal)
        missing_prices: dict[str, int] = defaultdict(int)
        realized: dict[str, Decimal] = defaultdict(Decimal)
        for item in holdings:
            currency = item["costCommodityCode"]
            holding_cost[currency] += Decimal(item["remainingCost"])
            if item["marketValue"] is None:
                missing_prices[currency] += 1
            else:
                holding_market[currency] += Decimal(item["marketValue"])
        realized_rows = self.connection.execute(
            "SELECT p.side,p.valuation_amount,e.balancing_commodity_code FROM postings_v2 p JOIN journal_entries_v2 e ON e.id=p.entry_id JOIN accounts_v2 a ON a.id=p.account_id WHERE a.type='income' AND lower(a.subtype) IN ('realized-gain','investment-gain')"
        ).fetchall()
        for row in realized_rows:
            amount = Decimal(row["valuation_amount"])
            realized[row["balancing_commodity_code"]] += amount if row["side"] == "credit" else -amount
        currencies = sorted(set(cash) | set(holding_cost) | set(holding_market) | set(realized))
        summaries = []
        for currency in currencies:
            summaries.append({
                "commodityCode": currency,
                "cash": canonical_decimal(cash[currency]),
                "holdingCostBasis": canonical_decimal(holding_cost[currency]),
                "holdingMarketValue": canonical_decimal(holding_market[currency]),
                "bookValue": canonical_decimal(cash[currency] + holding_cost[currency]),
                "marketValue": canonical_decimal(cash[currency] + holding_market[currency]),
                "unrealizedPnL": canonical_decimal(holding_market[currency] - holding_cost[currency]),
                "realizedPnL": canonical_decimal(realized[currency]),
                "missingPriceCount": missing_prices[currency],
            })
        return {
            "entryCount": self.connection.execute("SELECT COUNT(*) FROM journal_entries_v2").fetchone()[0],
            "draftCount": self.connection.execute("SELECT COUNT(*) FROM journal_drafts_v2 WHERE status='draft'").fetchone()[0],
            "openLotCount": len(holdings),
            "commoditySummaries": summaries,
            "formulas": {
                "accountBalance": "asset/expense: debit-credit; liability/equity/income: credit-debit",
                "holdingCostBasis": "sum(open lot remainingCost)",
                "holdingMarketValue": "sum(open lot remainingUnits * latest explicit price quote)",
            },
            "assumptions": [
                "Decimal strings are authoritative.",
                "No implicit FX conversion or external market data is used.",
            ],
        }

    def financial_statements(self) -> list[dict[str, Any]]:
        totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        rows = self.connection.execute(
            "SELECT p.side,p.valuation_amount,e.balancing_commodity_code,a.type FROM postings_v2 p JOIN journal_entries_v2 e ON e.id=p.entry_id JOIN accounts_v2 a ON a.id=p.account_id"
        ).fetchall()
        for row in rows:
            amount = Decimal(row["valuation_amount"])
            debit = amount if row["side"] == "debit" else Decimal(0)
            credit = amount if row["side"] == "credit" else Decimal(0)
            totals[(row["balancing_commodity_code"], row["type"])] += normal_balance(row["type"], debit, credit)
        currencies = sorted({key[0] for key in totals})
        return [{
            "commodityCode": currency,
            "assets": canonical_decimal(totals[(currency, "asset")]),
            "liabilities": canonical_decimal(totals[(currency, "liability")]),
            "equity": canonical_decimal(totals[(currency, "equity")]),
            "income": canonical_decimal(totals[(currency, "income")]),
            "expenses": canonical_decimal(totals[(currency, "expense")]),
            "netIncome": canonical_decimal(totals[(currency, "income")] - totals[(currency, "expense")]),
        } for currency in currencies]

    def cash_flow(self) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        rows = self.connection.execute(
            "SELECT p.side,p.units,p.commodity_code,p.cash_flow_category,a.type,a.subtype FROM postings_v2 p JOIN accounts_v2 a ON a.id=p.account_id WHERE a.type='asset' AND lower(a.subtype)='cash'"
        ).fetchall()
        for row in rows:
            value = Decimal(row["units"]) * (1 if row["side"] == "debit" else -1)
            groups[(row["commodity_code"], row["cash_flow_category"])] += value
        return [
            {"commodityCode": commodity, "category": category, "amount": canonical_decimal(value)}
            for (commodity, category), value in sorted(groups.items())
        ]

    def reconciliation(self) -> dict[str, Any]:
        checks: list[dict[str, str]] = []
        unbalanced = []
        for row in self.connection.execute("SELECT id FROM journal_entries_v2"):
            postings = self.connection.execute("SELECT side,valuation_amount FROM postings_v2 WHERE entry_id=?", (row[0],)).fetchall()
            debit = sum((Decimal(item["valuation_amount"]) for item in postings if item["side"] == "debit"), Decimal(0))
            credit = sum((Decimal(item["valuation_amount"]) for item in postings if item["side"] == "credit"), Decimal(0))
            if debit != credit:
                unbalanced.append(row[0])
        invalid_lots = []
        for lot in self.connection.execute("SELECT * FROM lots_v2"):
            movements = self.connection.execute(
                "SELECT action,units,cost FROM lot_movements_v2 WHERE lot_id=?", (lot["id"],)
            ).fetchall()
            acquire_count = sum(1 for item in movements if item["action"] == "acquire")
            units = Decimal(lot["original_units"])
            cost = Decimal(lot["original_cost"])
            for movement in movements:
                if movement["action"] == "dispose":
                    units -= Decimal(movement["units"])
                    cost -= Decimal(movement["cost"])
                elif movement["action"] == "restore":
                    units += Decimal(movement["units"])
                    cost += Decimal(movement["cost"])
                elif movement["action"] == "reverse-acquire":
                    units -= Decimal(movement["units"])
                    cost -= Decimal(movement["cost"])
            if (
                acquire_count != 1
                or units != Decimal(lot["remaining_units"])
                or cost != Decimal(lot["remaining_cost"])
                or units < 0
                or cost < 0
            ):
                invalid_lots.append(lot["id"])
        checks.append({
            "id": "entry-balance",
            "status": "pass" if not unbalanced else "error",
            "detail": "All posted entries balance exactly." if not unbalanced else f"Unbalanced entries: {len(unbalanced)}",
        })
        checks.append({
            "id": "lot-conservation",
            "status": "pass" if not invalid_lots else "error",
            "detail": "Lot movements reconcile exactly to every open balance." if not invalid_lots else f"Invalid lots: {len(invalid_lots)}",
        })
        fk = self.connection.execute("PRAGMA foreign_key_check").fetchall()
        checks.append({
            "id": "foreign-keys",
            "status": "pass" if not fk else "error",
            "detail": "Foreign-key check passed." if not fk else f"Foreign-key violations: {len(fk)}",
        })
        missing_prices = sum(1 for item in self.holdings() if item["latestPrice"] is None)
        checks.append({
            "id": "price-availability",
            "status": "pass" if missing_prices == 0 else "warning",
            "detail": "All open lots have an explicit price quote." if missing_prices == 0 else f"Open lots without a price: {missing_prices}",
        })
        return {"status": "error" if any(item["status"] == "error" for item in checks) else "pass", "checks": checks}

    def export_bundle(self) -> dict[str, Any]:
        return {
            "formatVersion": 2,
            "commodities": [dump(item) for item in self.list_commodities()],
            "accounts": [dump(item) for item in self.list_accounts()],
            "priceQuotes": [dump(item) for item in self.list_price_quotes()],
            "drafts": [item["draft"] for item in self.list_drafts()],
            "journalEntries": self.list_entries(),
            "holdings": self.holdings(),
            "livingAccounts": [dump(item) for item in self.list_living_accounts()],
            "livingSnapshots": [dump(item) for item in self.list_living_snapshots()],
            "monthlyPlans": [dump(item) for item in self.list_monthly_plans()],
        }

    def create_backup(self) -> dict[str, Any]:
        table_order = [
            "commodities_v2", "accounts_v2", "price_quotes_v2", "journal_drafts_v2",
            "journal_entries_v2", "postings_v2", "lots_v2", "lot_movements_v2",
            "recurring_entry_rules_v2", "living_accounts_v2", "living_snapshots_v2", "monthly_plans_v2",
        ]
        payload = {
            table: [dict(row) for row in self.connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in table_order
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {
            "formatVersion": 2,
            "schemaVersion": 2,
            "createdAt": now_iso(),
            "payload": payload,
            "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }

    def restore_backup(self, backup: dict[str, Any]) -> dict[str, int]:
        if backup.get("formatVersion") != 2 or backup.get("schemaVersion") != 2:
            raise ValueError("Backup formatVersion and schemaVersion must both be 2.")
        payload = backup.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("Backup payload is missing.")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if digest != backup.get("sha256"):
            raise ValueError("Backup SHA-256 does not match its canonical payload.")
        insert_order = [
            "commodities_v2", "accounts_v2", "price_quotes_v2", "journal_drafts_v2",
            "journal_entries_v2", "postings_v2", "lots_v2", "lot_movements_v2",
            "recurring_entry_rules_v2", "living_accounts_v2", "living_snapshots_v2", "monthly_plans_v2",
        ]
        expected = set(insert_order)
        if set(payload) != expected:
            raise ValueError("Backup contains missing or unknown tables.")
        if any(self.connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in insert_order):
            raise ValueError("Backup restore requires an empty v2 ledger.")
        counts: dict[str, int] = {}
        before = self._mutable_snapshot()
        with transaction(self.connection):
            for table in insert_order:
                allowed_columns = [row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")]
                rows = payload[table]
                if not isinstance(rows, list):
                    raise ValueError(f"Backup table {table} must be a row list.")
                for row in rows:
                    if not isinstance(row, dict) or set(row) != set(allowed_columns):
                        raise ValueError(f"Backup row shape for {table} does not match schema v2.")
                    placeholders = ",".join("?" for _ in allowed_columns)
                    self.connection.execute(
                        f"INSERT INTO {table}({','.join(allowed_columns)}) VALUES ({placeholders})",
                        tuple(row[column] for column in allowed_columns),
                    )
                counts[table] = len(rows)
            if self.connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Restored backup failed foreign-key validation.")
            self._save_undo(before)
        return counts

    def latest_undo(self) -> dict[str, str] | None:
        row = self.connection.execute(
            "SELECT token,expires_at FROM undo_operations_v2 WHERE consumed_at IS NULL ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return {"undoToken": row["token"], "expiresAt": row["expires_at"]} if row else None

    def undo(self, token: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM undo_operations_v2 WHERE token=?", (token,)).fetchone()
        now = datetime.now(timezone.utc)
        if row is None or row["consumed_at"] is not None or datetime.fromisoformat(row["expires_at"]) <= now:
            return None
        snapshot = json.loads(row["snapshot_json"])
        with transaction(self.connection):
            self.connection.execute("PRAGMA defer_foreign_keys=ON")
            for table in self.MUTABLE_DELETE_ORDER:
                self.connection.execute(f"DELETE FROM {table}")
            for table in self.MUTABLE_TABLES:
                columns = [item[1] for item in self.connection.execute(f"PRAGMA table_info({table})")]
                for item in snapshot[table]:
                    placeholders = ",".join("?" for _ in columns)
                    self.connection.execute(
                        f"INSERT INTO {table}({','.join(columns)}) VALUES ({placeholders})",
                        tuple(item[column] for column in columns),
                    )
            if self.connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Undo snapshot failed foreign-key validation.")
            self.connection.execute(
                "UPDATE undo_operations_v2 SET consumed_at=? WHERE token=?", (now.isoformat(), token)
            )
        return {"undone": True, "undoToken": token}

    def world(self) -> dict[str, Any]:
        living: dict[str, Decimal] = defaultdict(Decimal)
        income: dict[str, Decimal] = defaultdict(Decimal)
        expense: dict[str, Decimal] = defaultdict(Decimal)
        for item in self.list_living_accounts():
            living[item.commodity_code] += Decimal(item.balance)
        for item in self.list_monthly_plans():
            (income if item.kind == "income" else expense)[item.commodity_code] += Decimal(item.amount)
        market = {
            item["commodityCode"]: Decimal(item["holdingMarketValue"])
            for item in self.dashboard()["commoditySummaries"]
        }
        currencies = sorted(set(living) | set(income) | set(expense) | set(market))
        grouped: dict[str, list[LivingSnapshotV2]] = defaultdict(list)
        for item in self.list_living_snapshots():
            grouped[item.recorded_at].append(item)
        latest: dict[str, tuple[str, Decimal]] = {}
        series: dict[str, list[dict[str, str]]] = defaultdict(list)
        for recorded_at in sorted(grouped):
            for item in grouped[recorded_at]:
                latest[item.account_id] = (item.commodity_code, Decimal(item.balance))
            totals: dict[str, Decimal] = defaultdict(Decimal)
            for commodity, value in latest.values():
                totals[commodity] += value
            for commodity, value in totals.items():
                previous = Decimal(series[commodity][-1]["value"]) if series[commodity] else value
                series[commodity].append({
                    "recordedAt": recorded_at,
                    "value": canonical_decimal(value),
                    "delta": canonical_decimal(value - previous),
                })
        return {
            "commoditySummaries": [{
                "commodityCode": commodity,
                "livingBalance": canonical_decimal(living[commodity]),
                "investmentMarketValue": canonical_decimal(market.get(commodity, Decimal(0))),
                "combinedValue": canonical_decimal(living[commodity] + market.get(commodity, Decimal(0))),
                "expectedIncome": canonical_decimal(income[commodity]),
                "expectedExpense": canonical_decimal(expense[commodity]),
                "expectedNet": canonical_decimal(income[commodity] - expense[commodity]),
            } for commodity in currencies],
            "balanceSeries": [
                {"commodityCode": commodity, "points": points} for commodity, points in sorted(series.items())
            ],
        }

    # Internal helpers ----------------------------------------------------
    @staticmethod
    def _account_from_row(row: sqlite3.Row) -> Account:
        return Account.model_validate({
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "type": row["type"],
            "subtype": row["subtype"],
            "allowedCommodityCodes": json.loads(row["allowed_commodities_json"]),
            "status": row["status"],
        })

    @staticmethod
    def _quote_from_row(row: sqlite3.Row) -> PriceQuote:
        return PriceQuote.model_validate({
            "id": row["id"],
            "commodityCode": row["commodity_code"],
            "quoteCommodityCode": row["quote_commodity_code"],
            "price": row["price"],
            "asOf": row["as_of"],
            "source": row["source"],
        })

    @staticmethod
    def _draft_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "draft": json.loads(row["payload_json"]),
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "postedEntryId": row["posted_entry_id"],
        }

    @staticmethod
    def _posting_from_row(row: sqlite3.Row) -> dict[str, Any]:
        lot = json.loads(row["lot_json"]) if row["lot_json"] else {}
        return {
            "id": row["id"],
            "accountId": row["account_id"],
            "side": row["side"],
            "units": row["units"],
            "commodityCode": row["commodity_code"],
            "valuationRate": row["valuation_rate"],
            "valuationAmount": row["valuation_amount"],
            "rateType": row["rate_type"],
            "memo": row["memo"],
            "cashFlowCategory": row["cash_flow_category"],
            **lot,
        }

    def _insert_completed(self, completed: CompletedEntry, *, timestamp: str, reversal_of: str | None) -> None:
        self.connection.execute(
            "INSERT INTO journal_entries_v2(id,date,description,payee,source,reference,tags_json,balancing_commodity_code,posted_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                completed.id,
                completed.date,
                completed.description,
                completed.payee,
                completed.source,
                completed.reference,
                json.dumps(completed.tags, ensure_ascii=False),
                completed.balancing_commodity_code,
                timestamp,
                reversal_of,
            ),
        )
        for index, posting in enumerate(completed.postings):
            lot = None
            if posting.lot_action:
                lot = json.dumps({
                    "lotAction": posting.lot_action,
                    "lotId": posting.lot_id,
                    "lotAllocations": [dump(item) for item in posting.lot_allocations],
                }, ensure_ascii=False, separators=(",", ":"))
            self.connection.execute(
                "INSERT INTO postings_v2(id,entry_id,sort_order,account_id,side,units,commodity_code,valuation_rate,valuation_amount,rate_type,memo,cash_flow_category,lot_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    posting.id,
                    completed.id,
                    index,
                    posting.account_id,
                    posting.side,
                    posting.units,
                    posting.commodity_code,
                    posting.valuation_rate,
                    posting.valuation_amount,
                    posting.rate_type,
                    posting.memo,
                    posting.cash_flow_category,
                    lot,
                ),
            )

    def _validate_lot_allocations(self, completed: CompletedEntry) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for index, posting in enumerate(completed.postings):
            if posting.lot_action != "dispose":
                continue
            allocated = sum((Decimal(item.units) for item in posting.lot_allocations), Decimal(0))
            if allocated != Decimal(posting.units):
                issues.append(ValidationIssue(
                    code="LOT_ALLOCATION_MISMATCH",
                    severity="error",
                    path=f"postings.{index}.lotAllocations",
                    message="Allocated lot units must equal posting units.",
                    details={"allocated": canonical_decimal(allocated), "postingUnits": posting.units},
                ))
                continue
            for allocation in posting.lot_allocations:
                row = self.connection.execute("SELECT * FROM lots_v2 WHERE id=?", (allocation.lot_id,)).fetchone()
                if row is None:
                    issues.append(ValidationIssue(
                        code="LOT_NOT_FOUND", severity="error", path=f"postings.{index}.lotAllocations",
                        message="Allocated lot does not exist.", details={"lotId": allocation.lot_id},
                    ))
                elif row["account_id"] != posting.account_id or row["commodity_code"] != posting.commodity_code:
                    issues.append(ValidationIssue(
                        code="LOT_CONTEXT_MISMATCH", severity="error", path=f"postings.{index}.lotAllocations",
                        message="Allocated lot account or commodity does not match the posting.", details={"lotId": allocation.lot_id},
                    ))
                elif Decimal(row["remaining_units"]) < Decimal(allocation.units):
                    issues.append(ValidationIssue(
                        code="LOT_UNITS_INSUFFICIENT", severity="error", path=f"postings.{index}.lotAllocations",
                        message="Allocated units exceed the open lot balance.", details={"lotId": allocation.lot_id},
                    ))
        return issues

    def _apply_lots(self, completed: CompletedEntry) -> None:
        balancing = self.get_commodity(completed.balancing_commodity_code)
        assert balancing is not None
        for posting in completed.postings:
            if posting.lot_action == "acquire":
                assert posting.lot_id is not None
                self.connection.execute(
                    "INSERT INTO lots_v2(id,account_id,commodity_code,acquired_date,original_units,remaining_units,original_cost,remaining_cost,cost_commodity_code,source_entry_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        posting.lot_id,
                        posting.account_id,
                        posting.commodity_code,
                        completed.date,
                        posting.units,
                        posting.units,
                        posting.valuation_amount,
                        posting.valuation_amount,
                        completed.balancing_commodity_code,
                        completed.id,
                    ),
                )
                self.connection.execute(
                    "INSERT INTO lot_movements_v2(id,lot_id,entry_id,posting_id,action,units,cost) VALUES (?,?,?,?,?,?,?)",
                    (str(uuid4()), posting.lot_id, completed.id, posting.id, "acquire", posting.units, posting.valuation_amount),
                )
            elif posting.lot_action == "dispose":
                allocated_cost = Decimal(0)
                for allocation in posting.lot_allocations:
                    row = self.connection.execute("SELECT * FROM lots_v2 WHERE id=?", (allocation.lot_id,)).fetchone()
                    if row is None:
                        raise ValueError("Allocated lot was not found.")
                    remaining_units = Decimal(row["remaining_units"])
                    remaining_cost = Decimal(row["remaining_cost"])
                    units = Decimal(allocation.units)
                    cost = remaining_cost if units == remaining_units else quantize(
                        remaining_cost * units / remaining_units, balancing.scale
                    )
                    allocated_cost += cost
                    self.connection.execute(
                        "UPDATE lots_v2 SET remaining_units=?,remaining_cost=? WHERE id=?",
                        (canonical_decimal(remaining_units - units), canonical_decimal(remaining_cost - cost), allocation.lot_id),
                    )
                    self.connection.execute(
                        "INSERT INTO lot_movements_v2(id,lot_id,entry_id,posting_id,action,units,cost) VALUES (?,?,?,?,?,?,?)",
                        (str(uuid4()), allocation.lot_id, completed.id, posting.id, "dispose", canonical_decimal(units), canonical_decimal(cost)),
                    )
                if allocated_cost != Decimal(posting.valuation_amount):
                    raise ValueError(
                        f"Disposed asset posting valuation must equal selected lot cost: {canonical_decimal(allocated_cost)}."
                    )

    def _reverse_lot_movements(self, original_entry_id: str, reverse_entry_id: str, posting_ids: dict[str, str]) -> None:
        rows = self.connection.execute(
            "SELECT * FROM lot_movements_v2 WHERE entry_id=? ORDER BY rowid", (original_entry_id,)
        ).fetchall()
        for movement in rows:
            lot = self.connection.execute("SELECT * FROM lots_v2 WHERE id=?", (movement["lot_id"],)).fetchone()
            if lot is None:
                raise ValueError("Lot referenced by original entry no longer exists.")
            if movement["action"] == "acquire":
                if Decimal(lot["remaining_units"]) != Decimal(lot["original_units"]):
                    raise ValueError("An acquisition cannot be reversed after its lot has been consumed.")
                self.connection.execute(
                    "UPDATE lots_v2 SET remaining_units='0',remaining_cost='0' WHERE id=?", (lot["id"],)
                )
                action = "reverse-acquire"
            elif movement["action"] == "dispose":
                self.connection.execute(
                    "UPDATE lots_v2 SET remaining_units=?,remaining_cost=? WHERE id=?",
                    (
                        canonical_decimal(Decimal(lot["remaining_units"]) + Decimal(movement["units"])),
                        canonical_decimal(Decimal(lot["remaining_cost"]) + Decimal(movement["cost"])),
                        lot["id"],
                    ),
                )
                action = "restore"
            else:
                raise ValueError("Unsupported lot movement reversal.")
            self.connection.execute(
                "INSERT INTO lot_movements_v2(id,lot_id,entry_id,posting_id,action,units,cost) VALUES (?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    lot["id"],
                    reverse_entry_id,
                    posting_ids[movement["posting_id"]],
                    action,
                    movement["units"],
                    movement["cost"],
                ),
            )

    def _require_scale(self, value: str, commodity_code: str, field: str) -> None:
        commodity = self.get_commodity(commodity_code)
        if commodity is None or commodity.status != "active":
            raise ValueError(f"{field} commodity must exist and be active.")
        if quantize(Decimal(value), commodity.scale) != Decimal(value):
            raise ValueError(f"{field} contains more fractional digits than {commodity_code} allows.")

    def _mutable_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {
            table: [dict(row) for row in self.connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in self.MUTABLE_TABLES
        }

    def _save_undo(self, snapshot: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=10)
        token = str(uuid4())
        self._invalidate_undo(now.isoformat())
        self.connection.execute(
            "INSERT INTO undo_operations_v2(token,snapshot_json,created_at,expires_at) VALUES (?,?,?,?)",
            (token, json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), now.isoformat(), expires.isoformat()),
        )
        return {"undoToken": token, "expiresAt": expires.isoformat()}

    def _invalidate_undo(self, timestamp: str | None = None) -> None:
        self.connection.execute(
            "UPDATE undo_operations_v2 SET consumed_at=? WHERE consumed_at IS NULL",
            (timestamp or now_iso(),),
        )
