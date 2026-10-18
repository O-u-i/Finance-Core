# Provisional month-to-date review

FC product/API **3.9.0**, official reader **1.9.0 / protocol 2**, minimum FRAG **1.13.3**.

`GET /api/v3/workspaces/{workspaceId}/reports/month-to-date?asOf=YYYY-MM-DD`

- Requires `ledger:read` for that Workspace; no owner session or write scope is needed.
- The date is exact ISO, nonfuture in Asia/Shanghai, and inclusive. The interval starts on that month's first day and ends exclusively on the day after `asOf`.
- This is a separate provisional contract, not a change to `monthly-review:YYYY-MM` or its three completed months. Historical cutoffs remain reproducible; no floating "today" or wildcard date is authorized.

## Meaning and limits

The summary reuses FC's established exact Decimal cash-movement and accounting income/expense axes. Internal cash transfers are netted per entry/currency. Borrowing and debt repayment are not income/expenses; signed reversals stay in their posting period. Currencies are separate, and current account classification is part of the revision basis. Unposted drafts and entries outside the exact window are excluded. Unassignable posted dates block all totals without exposing the corrupt row.

`periodStatus: partial` always identifies this provisional report; it does not certify a formal month close. The response has one `period`, not invented preceding months. Whole-month comparison fields are null, because a partial month is not a comparable completed period.

`coverage.activityBasis` is `posted-journal-only`. Posted opening equity entries may move cash without creating income. Living balance observations, asset valuations and forecast plans are not Journal income/spending and are not inferred into these totals. This is not a balance sheet or an assessment of personal available funds.

`externalCompleteness` and `unrecordedDays` remain `unknown`. Empty records produce zero posted-entry counts and an empty currency list, not proof that real-world activity was zero. No history needs re-entry or a schema migration.

## Evidence and verification

The official record is `month-to-date:YYYY-MM-DD`. Its exact date must be explicitly whitelisted. Discovery does not fetch its financial report. The adapter accepts only the strict summary shape; account IDs/names, descriptions, references, notes and raw postings are not allowed.

The complete report is required evidence in FRAG byte/token fitting and completion. Overflow refuses delivery rather than truncating currencies or coverage. Source/configuration/record revisions are revalidated. This new factual report does not satisfy economic-stock/obligation prerequisites or enable a recommendation carrier.

Synthetic Workspace HTTP tests cover cutoff inclusion/exclusion, drafts, stable/changed revisions, currency precision, cash versus accrual, loans/repayment/transfers, reversals, invalid/future dates and token/Workspace isolation. Official-reader tests cover exact GETs, safe discovery, full formatting and malformed/private fields. These are distinct from live sandbox, native model continuation and human acceptance. No real financial Run is executed by a test.
