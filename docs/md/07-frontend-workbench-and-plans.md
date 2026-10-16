# Frontend workbench and planned cash flow

Historical 3.6.0 display baseline. The [3.7.0 desktop workbench](08-desktop-workbench.md)
supersedes the layout, T-account card and Note-placement descriptions below;
the monthly-plan contract and financial rules remain unchanged.

Finance Core product 3.6.0 adds the API 3.6.0 owner-session report
`GET /api/v3/workspaces/{workspace_id}/reports/monthly-plans?month=YYYY-MM`.
It is a read-only forecast, not posted cash activity. Ledger/registry schemas and
existing report semantics are unchanged. The optional reader 1.6.0 changes only
its exact API health pin; its permissions and evidence whitelist do not expand.

## Display and reconciliation

- Overview remains read-only. Month-end report checks use a compact status and
  an accessible detail dialog, with account names and optional technical IDs.
- Actual-date balances remain separate from formal month-end observations.
  A saved October observation does not prove September opening/closing stock.
  Unknown preceding values remain unknown; a difference is not spending/income.
- Current balances use a compact table; previous-date comparisons are available
  in a dialog. Snapshot history retains sources, Notes and correction provenance.
- Asset registration is independent of valuation month. Saved registry Notes
  remain visible on each asset card, separate from valuation Notes. Valuations
  explicitly refer to the selected calendar month end, not today's value.
  Saving, validation failures, corrections and disposal have local feedback;
  disposal records the last included month without deleting earlier facts.
- Lists expose search, a sort-field selector and an ascending/descending arrow.
  Financial strings are ordered without converting them to JavaScript Number.
  Snapshot ordering is applied before pagination, not just to a visible page.
- T-accounts have one vertical container per account, Credit before Debit.
  This is display order only; normal-balance calculations remain unchanged.
- Securities & positions is reserved for future API integration. Backend
  holdings/lot contracts remain available; no external connector is added.
- Ownership agreements use beneficiary/account selectors and repeatable share,
  claim and interest rows, rather than a required JSON editor. FC still validates
  exact shares, mapped accounts and append-only version boundaries.
- Atomic batches stage new commodities, Investment accounts, explicit prices or
  unposted template-based drafts. The existing endpoint is create-only, not an
  update mechanism. Existing financial and atomicity validation is unchanged.
  JSON remains a supported import/export/backup format, not required form entry.

## Monthly plans

Plans support add, edit, delete, category/flow filters, reusable category choices,
and optional Notes. UI labels distinguish CF inflow/outflow from actual cash.
Category cards and all-category currency totals come from the backend report;
plan-list filters do not alter the separately labelled totals.

`dayOfMonth=13` means one occurrence per month on day 13, not thirteen
occurrences. Days missing from a short month use that month's last valid day,
matching FC's recurring-draft convention. Occurrences must be on or after the
start date. A nonrecurring plan occurs once on its start date. The report uses
exact Decimal arithmetic per category and currency, never FX conversion. It
does not create Journal entries, record balances or confirm reconciliation.

Deletion remains resource-specific: monthly plans, recurring rules, explicit
quotes and unposted drafts use their existing endpoints; referenced accounts
and commodities retain existing history protections. Confirmed balances,
agreements and posted facts are not made physically deletable by this UI work.

Local synthetic browser/API checks are not acceptance of real financial inputs,
real-data migration, publication, or installation into FRAG.
