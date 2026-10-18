# Economic evidence and explicit debt timing

Product/API **3.9.0**, ledger schema **3**, registry schema **1**. Ownership: **BOTH** for the released summary/reader contract; repayment recording, calculations, storage and standalone UI are **FC_ONLY**. No new dependency or financial connector.

## Recorded facts, not personal affordability

`GET /api/v3/workspaces/{workspaceId}/reports/economic-evidence?asOf=YYYY-MM-DD&through=YYYY-MM-DD` requires `ledger:read`. The as-of date is non-future in Asia/Shanghai; the explicit future horizon is 1–366 days. A coherent read snapshot returns separate segment/currency gross cash and liability stocks, actual observation dates, planned outflows, confirmed repayment dates, out-of-horizon debt amounts/counts, coverage, missing-fact codes and a stable revision. Names, account IDs, sources, notes, parties and raw postings are absent.

The applicable baseline and account classification must be confirmed. Living balances must be confirmed on the exact as-of date; no carry-forward or retrospective baseline inference. Retired accounts cannot hide outstanding balances. Offsetting individual debts do not prove that no maturity information is needed. Unknown balances remain null, never zero.

Monthly plans are forecasts, not contractual maturities or posted payments. Confirmed debt arrangements allocate exactly the **current recorded liability balance** to explicitly sourced dates. Future charges, external completeness and personal disposable availability remain unknown; currencies are never combined. Overdue dates remain overdue. `debtOutsideHorizon` retains the amount/count beyond the selected horizon rather than silently omitting that debt or treating it as zero. A wider date window requires explicit selection.

Missing historical maturity dates remain **unknown, pending input**. No migration invents them, no plan substitutes for them and no history needs re-entry. `missingFacts` blocks dependent evidence acceptance. Passing recorded-scope coverage is not a complete personal balance sheet, prediction, investment recommendation or permission to pay.

## Explicit recording and confirmation

All paths below are Workspace-scoped under `/api/v3/workspaces/{workspaceId}`:

| Method/path | Scope | Behavior |
| --- | --- | --- |
| `GET /debt-repayment-balance?accountId=...&currency=...&asOf=...` | `ledger:read` | Known/unknown liability balance and exact balance revision for review. |
| `GET /debt-repayment-arrangements` | `ledger:read` | Retained drafts and confirmations. |
| `GET /debt-repayment-arrangements/{id}` | `ledger:read` | One saved version for review. |
| `POST /debt-repayment-arrangements` | `ledger:write` | Save a sourced, dated draft against the reviewed balance revision. |
| `POST /debt-repayment-arrangements/{id}/confirm` | `ledger:write` | Require strict boolean `confirmed: true`, exact draft revision and balance revision; recheck atomically. |

Draft requests contain `id`, `accountId`, `currency`, `asOf`, `balanceRevision`, 1–100 `payments` (`dueDate`, decimal-string `amount`), `source`, `reason` and optional `supersedes`. Positive payments must sum exactly to the known positive recorded balance and respect the currency scale. Future interest or fees must not be invented to fill a difference.

Confirmation is once-only. Corrections save a new draft explicitly naming the current confirmed arrangement; only a confirmed successor supersedes it. Original confirmations cannot be edited or deleted. A changed financial basis/date invalidates old timing evidence until a reviewed replacement is confirmed. Draft creation/confirmation invalidates ordinary undo opportunities, but never changes balances, settles debt or posts Journal entries. Referenced accounts and currencies retain their provenance protections.

The standalone UI exposes this workflow in **Master data → Debt repayments**, for registered Investment and Living liabilities. Missing dates remain visible as unknown. Review the saved dates, amounts, source and reason before the explicit confirmation checkbox/button. Existing owner-session-only personal routes remain owner-only. FRAG receives neither these detail/write routes nor an owner credential.

## Compatible persistence and backups

Schema-3 Vault reads never create a new table. The optional `debt_repayment_arrangements_v3` table is created only inside an explicit debt-write or full-restore transaction. Existing financial rows and immutable closes are unchanged. Existing schema-2 Vaults receive `409 SCHEMA_MIGRATION_REQUIRED` for the new foundation, not an implicit upgrade or an internal error. Their existing ledger reads still work.

A full Vault backup with this extension uses **format 4 / ledger schema 3**, includes debt history and validates record identities, liability/currency references, exact sums, confirmation states and correction chains on restore. Older format-2/3 backups remain accepted into eligible empty Vaults. A nonempty target, invalid history or failed restore leaves the target unchanged. Legacy format-2 export refuses to discard debt arrangements. Preserve a full backup before using an older writer; disabling the reader/feature is safer than removing history.

Full-Vault formats **3 and 4 require an owner session on every restore entry point**, including legacy `/backup/restore`; a Workspace ledger token receives `403 TOKEN_SCOPE_DENIED` without changing the target. Format-2 ledger restore retains its existing scope contract. Invalid format/schema version types return 422, not an internal error or partial restore. This closes an alternate-route authorization bypass; it grants neither the reader nor a test token owner access.

If a personal schema-2 source needs schema 3, use the separately authorized stopped-writer **copy migration**: retain the original and backup, migrate a new copy, then check integrity, foreign keys and unchanged historical facts. Never upgrade in place, replace the original silently or request whole-ledger re-entry. No production migration is performed by this feature.

## Synthetic acceptance profile

`POST /demo/load-synthetic?profile=economic-evidence&asOf=YYYY-MM-DD` is an explicit opt-in for an **entirely empty schema-3 sandbox only**. It assembles fixed virtual balances, a baseline, a dated Living record, opening stock, a plan and a confirmed debt arrangement off-target, then restores them atomically. Personal Vaults and any existing financial data are rejected. The original default demo loader remains unchanged. This is not an import of real history or authority to seed a personal Vault.

## Reader and verification boundaries

Official reader **1.9.0 / protocol 2**, API **3.9.0**, minimum FRAG **1.13.3**, retains `economic-evidence:YYYY-MM-DD:YYYY-MM-DD` selected summary records introduced in 3.8.0. The separate [month-to-date report](11-month-to-date-review.md) does not replace this stock/obligation contract. Discovery derives labels without fetching reports. Calendar/horizon/whitelist checks occur before HTTP; the adapter validates an exact summary-only wire shape and retains the whole report. FC arithmetic is not reimplemented in FRAG. Read tokens remain read-only; test write tokens are only for isolated FC HTTP acceptance.

Synthetic HTTP regressions cover explicit confirmation, persistence/restart, concurrent double confirmation, correction history, stale revisions, invalid dates/amounts, scope isolation, unknown dates, backup preservation/atomic rejection and sandbox restrictions. Official adapter tests cover exact GETs, wire/privacy validation and no eager report fetch. Offline regression, isolated loopback integration, native-window observation and human financial acceptance are separate evidence layers. A missing-data refusal is not a complete positive Slice B acceptance.
