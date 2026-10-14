# Unified personal and investment accounting (3.6.0)

Product 3.6.0 / API 3.5.0 / ledger schema 3 / registry schema 1.
This is an additive local implementation, not a production migration or publication.

## Measurement and ownership

One Vault has an Investment ledger and Living actual-date balance records. Register each
real account once, with an independent accounting type, segment and balance source.
Investment uses immutable posted double-entry aggregates. Living uses explicit
actual-date asset/liability balances, not detailed spending transactions or generated
balancing entries. A registered party is an economic beneficiary, not a login User.

Missing opening balances, months, ownership, prices or valuations are unknown, not
zero. Dated balances are never prefilled from a prior month. Imported legacy monthly CSV rows
are pending until individually confirmed. Planned amounts remain plans, not actual
income, expenses or savings. All currencies remain separate; there is no FX total.

The horizontal shell retains global Overview / Master data / Settings, then an
Investment / Living switch and horizontal segment navigation. Living has no
detailed Transactions page. Hash routes carry segment, view and month. Existing
legacy report links remain supported.

Overview is a display-only dashboard: its local Consolidated / Investment / Living
tabs change the readout, not the route or financial settings. Its global navigation
button is light blue and has no readiness badge. The horizontal segment navigation
sticks below the viewport edge with a translucent, blurred background. Master data
section tabs preserve scroll position; changing feature pages still starts at the top.

Master data owns account registration for both segments, using the existing Glide
Select; its registry follows the selected segment and natural ascending code order.
Search, account type, commodity and status filters combine without changing data or
discarding the registration form. Snapshot readouts show account names,
short dates/months and the latest record per account (ten accounts per page). Full
history, IDs, precise timestamps and correction evidence remain available in
expandable, paged details. Pending observations remain visibly pending; decimal
strings are displayed unchanged, including amounts beyond JavaScript integer precision.
Superseded observations appear only in history, not the latest readout.
Equal legacy timestamps are resolved against the account's current recorded balance,
not random snapshot IDs; no historical dates or transaction order are invented.

## Actual-date Living balances (API 3.4)

`observedDate` is the user-observed `YYYY-MM-DD`; `recordedAt` is the server's
receipt timestamp. Neither is inferred from the other. Same-day and same-month
records append independently. New records may backfill an earlier real date;
future dates are refused in Asia/Shanghai. Account purpose periods, one registered
currency, Decimal scale and beneficiary validation still apply. Explicit corrections
require an unreplaced record with the same account, currency and actual date plus
a reason; originals cannot be overwritten, undone or deleted.

Monthly dated review selects the greatest `(observedDate, recordedAt, id)` within
that calendar month. A backfilled earlier date cannot become the latest balance.
No record in the selected month means Unknown, even if an older balance exists.
The comparison is with the preceding actual-date record, which may be in a different
month or on the same day. Both dates are displayed. FC computes the exact Decimal
difference only when both records are confirmed; pending latest values stay pending
and do not fall back to an older confirmed value. Differences are not classified as
income, consumption or savings. Currencies and account beneficiaries are not combined.

The existing immutable schema-3 observation table already supports multiple roots.
This is a logical payload extension, not a physical schema upgrade: dated balances
add `observedDate` and use `month` only as a query bucket. Existing records keep their
original payloads and unknown actual dates. Schema-2 migration still requires separate
approval. Full format-3 backup/restore retains each dated record and correction chain;
JSON segment export adds `balanceRecords`, and CSV adds an `observedDate` column.
The legacy monthly CSV importer does not accept dated balances.

The old `/monthly-observations`, v1 personal reports and immutable month closes keep
their month-end meaning and exclude dated balances. Overview shows dated Living
readouts separately from formal month-end net worth, never adding them twice. Living
Monthly review defaults to the current month and shows the actual latest record date;
the old reconciliation/close controls remain in an explicitly labelled folded section.
The obsolete month-end Living entry page and its unused styling are retired.

## Additive owner-only API

All paths below are under `/api/v3/workspaces/{workspaceId}` and require an owner
session. Existing scoped bearer tokens do **not** gain these personal-data reads.

| Resource | Operations |
| --- | --- |
| `/financial-accounts` | list, register; PUT a named identity; DELETE an unused identity |
| `/finance-parties` | list; PUT a named beneficiary |
| `/personal-finance-settings` | get/confirm reporting beneficiary, cutover and opening baseline |
| `/legacy-living-mapping` | inspect explicit IDs; POST a same-economic-account mapping with evidence |
| `/non-financial-assets` | register identity, purchase date/cost, ownership and optional linked account |
| `/investment-arrangements` | append consecutive effective-month agreement versions |
| `/investment-arrangements/{id}/drafts` | create funding, repayment, interest, interest-payment, distribution or payment drafts |
| `/monthly-observations` | append pending/confirmed balances, valuations or aggregate cross-segment totals |
| `/balance-records` | list/append actual-date Living balances, including same-day records and explicit corrections |
| `/reports/living-recorded-balances?month=YYYY-MM` | latest actual-date balance within month, preceding record/date and exact balance-only change |
| `/monthly-closes` | atomically confirm exact input revision; append corrected close with supersedes and reason |
| `/reports/personal-balance-sheet` | dated per-currency personal economic values and coverage |
| `/reports/investment-monthly-review` | same reconciled foundation, with ledger income/expenses and pool stake |
| `/reports/living-monthly-review` | balance changes and transfer reconciliation, not inferred consumption |
| `/reconciliation/personal-finance` | foundation checks separate from old reconciliation contract |
| `/segments/{segment}/export[.csv]` | separate JSON/CSV, not a complete Vault backup |
| `/import/living-monthly/validate` | read-only UTF-8 monthly CSV preview |
| `/import/living-monthly` | atomic pending-observation import, never automatic confirmation |
| `/vault-backup` and `/vault-backup/restore` | full format-3 finance history; empty-target restore only |

Amounts, prices and shares are finite decimal strings. FC alone calculates. Reports
carry month, asOf, revision, valuation basis, issues, known-input subtotals and
coverage; incomplete inputs never produce an unconditional personalNetWorth.
External completeness always remains unknown. The released OpenAPI is authoritative.

Implementation separates command writes (`personal_finance_repository.py`) from
read-only input snapshots and provenance checks (`personal_finance_snapshot.py`).
Journal draft validation uses that same snapshot without constructing the personal
command service. Existing ledger projections live in `ledger_reports.py`; backup
formats and restore validation live in `ledger_backup.py`. Restore still reserves
the SQLite writer before checking target emptiness and inserting any rows. No
plugin framework, duplicate financial calculator or new dependency is required.

Existing `/world`, Statements, Dashboard, Monthly Review v1 and old Reconciliation
calculations/response shapes are unchanged. In particular Monthly Review v1 remains
posted-Journal-only, three completed Shanghai calendar months, and uses current
account definitions. Its old aggregate is **not** a personal balance sheet.

### Account lifecycle and deletion

`DELETE /financial-accounts/{id}` is owner-only and removes only an unused identity.
The additive legacy-ledger `DELETE /accounts/{id}` retains the existing ledger-write
authorization and cannot reach monthly-only accounts. Both reserve the SQLite
writer before checking references. Posted entries, lots, drafts, disabled recurring
templates, observations, asset/ownership mappings, successors, migration receipts
and immutable closes block deletion. A refused deletion leaves finance history
unchanged. These new unused-account deletions invalidate undo; they do not offer a
generic history-erasing undo operation.

End purpose changes status instead of deleting history. For Schema 3, `endMonth`
is inclusive and cannot precede recorded observations or posted facts. Later balance
observations are refused, while corrections inside the recorded period remain
possible. A final nonzero, pending or missing balance without an active dated
successor is `ENDED_ACCOUNT_UNSETTLED`, not a write-off or a zero contribution to
personal net worth. Historical reports remain available.

### Commodity lifecycle and Overview visibility

The additive Workspace `DELETE /commodities/{code}` removes only an unreferenced
registry entry and invalidates undo. The reference check and deletion share the
SQLite writer reservation. Ledger/Living account configurations, prices, posted
facts/lots, unposted drafts, disabled recurring templates, plans, manual assets,
all agreement versions, observations (including actual-date balances), legacy
archives and confirmed close inputs prevent deletion. A zero amount or inactive
status is not permission to erase provenance. Retire a referenced code by
deactivating it instead.

`GET /commodities?includeUsage=true` adds the optional read-only `inUse` flag;
the original list response remains unchanged when the option is omitted. The
standalone Master data/Overview views use it; the official reader's whitelist and
permissions do not change. Overview hides only inactive codes explicitly reported
as unused, keeps unknown/referenced currency rows, and omits empty ownership
cards. This is presentation filtering, not a new financial calculation, report
version or schema migration. Active zero currencies remain in Schema-3 Overview;
legacy readouts retain their original used-currency scope.

## General beneficiary reconciliation

An agreement has arbitrary parties, exact nonnegative residual shares summing to 1,
one creditor/kind mapping per pool liability, and optional fixed monthly interest
schedules. Loans/member contributions are liabilities, not residual-share changes.
Repayment and independent distribution/interest payments cannot exceed the accrued
party claim. Distribution accrues all beneficiaries at once; currency-quantum
rounding uses largest remainders, with declared party order breaking ties. Zero
shares receive no rounding residue.

Interest generation is draft-only. First/last/principal-change periods require
explicit agreed-amount confirmation, never invented proration. Ordinary months use
the fixed monthly amount. Stale or edited generated drafts refuse validation/posting;
posting changes the input revision and invalidates concurrent entitlement drafts.
Manual unmatched/overpaid liabilities remain reconciliation failures.

Per currency:

```text
residual equity = investment market assets - all investment liabilities
party investment value = that party's claims + share * residual equity
personal net worth = Living assets - Living liabilities
                   + owned manual asset values + reporting party investment value
```

Loans, accrued interest, member claims and distributions already appear in pool
liabilities; do not subtract them twice. Negative residual equity is retained, not
clamped, and is not evidence of a legal personal guarantee.

Quotes are filtered by real timestamp at Shanghai month end. Lot movements are
replayed using their stored costs, including historically held lots now disposed
or reversed. Later disposals/prices do not erase earlier positions. Invalid dates,
negative historical lots and security-unit mismatches refuse completeness.

Living confirms incoming/outgoing monthly totals against posted cash movements
tagged `personal-transfer:in:CURRENCY` / `personal-transfer:out:CURRENCY` (direction
is from Living's perspective). No detailed Living transactions are required.

```text
unexplained cash change = closing cash - opening cash
                        - confirmed (cross-segment incoming - outgoing)
```

Fees, transit and cross-currency mismatches are separate. No auto-adjustment forces
a match. Asset registry links replace a linked Living account's valuation authority,
never add a second value. Used account segment/source/ownership cannot be rewritten;
dated successors require an explicit matching predecessor-close / successor-opening
carry. Legacy IDs are never merged by name or timestamp.

## Migration and backups

Opening a schema-2 Vault does **not** upgrade it. Old contracts still read it; new
features return SCHEMA_MIGRATION_REQUIRED. Future/unversioned schemas are refused.
New empty Vaults initialize schema 3. The sequential migration preserves all old
financial-table hashes/posted IDs, archives legacy Living rows with provenance,
invalidates old undo, and leaves classification/baseline confirmation pending.
Legacy recordedAt is never interpreted as a month-end asOf.
The GUI retains Journal review, Living/plans and format-2 backup for a schema-2
Vault, with compatibility guidance in the relevant controls instead of a page-wide
Schema banner. The centralized Master data
segment selector writes Investment to the original ledger registry and Living to
the original Living registry. It does not invent stored segment/ownership metadata
or infer month-end dates. Overview can show the original read-only ledger/pool and
Living aggregates, clearly labeled as not reconciled personal net worth.
Legacy Investment accounts can become inactive. Legacy Living has no dated inactive
state; its end-purpose lifecycle requires a new or explicitly migrated Schema 3
Vault. Legacy Living metadata edits cannot change a recorded balance or its
recording timestamp in this UI.
Its Delete unused action sends `preserveHistory=true`, refusing snapshots or a
nonzero recorded balance. The old undoable Living-delete API default remains
unchanged for compatibility, but is no longer the UI's deletion path.
It does not treat a migration refusal as authentication or configuration failure.

Read-only dry run (synthetic development or a separately authorized real source):

```powershell
python -m finance_core.schema_migration <schema-2-copy.sqlite3>
```

Real migration additionally requires **REAL_DATA_MIGRATION_APPROVED**, stopped
writers and a new target; never point this command at a running production Vault:

```powershell
python -m finance_core.schema_migration <stopped-source.sqlite3> --target <new-copy.sqlite3> --approval REAL_DATA_MIGRATION_APPROVED --writers-stopped
```

`--writers-stopped` is an explicit operator declaration, not a filesystem/process
lock. The runner also refuses a source revision change during copying/upgrading;
the operator must keep writers stopped until reviewing and selecting the copy.
The source is retained; an existing target cannot be overwritten. Upgrade checks
SQLite integrity, foreign keys and hashes of every old financial table (including
posting and lot facts). Review the receipt, explicit Living mappings and confirmed
opening baseline before choosing a migrated Vault. A failed new copy is retained
for review; no automatic file cleanup or production registry-pointer change occurs.

Format 3 includes legacy/current finance tables, mappings, observations, agreement
versions, close inputs/results and corrections; it excludes registry credentials,
sessions and undo tokens. It validates SHA-256, row schemas, foreign keys, archive
hashes and recomputed close results. Restore only into a new empty financial Vault.
Format 2 is accepted as legacy, retaining its old shapes but not new-model coverage;
the old `/backup` remains a legacy format-2 API. Immutable closes are not ordinary
undo, and a full format-3 restore has no generic undo.

Without new writes, rollback uses the retained original DB/binary. After new writes,
disable the feature and retain the new Vault; no lossless automatic downgrade is
promised. Backup is a global Settings operation, not two partial Vault backups.

## Synthetic verification

```powershell
uv run --offline --no-sync --project backend --cache-dir .tmp/uv-cache python tools/verify_personal_finance.py --basetemp .tmp/<owned-run>/new-synthetic-test-base
npm.cmd run test:ui
npm.cmd run build
npm.cmd run check:release
npm.cmd run check:versions
```

The script refuses an existing or out-of-repository pytest base directory. Reference
tests include a lender and two residual beneficiaries, as well as unrelated names,
unequal shares, large exact amounts, independent unpaid distributions, repayment,
fixed interest, negative equity, future quotes/disposals/reversals, missing inputs,
concurrency/staleness, arbitrary participant counts, rounding, stopped-writer
migration refusal, successors, pending CSV, duplicate legacy identities, format-3
roundtrip/atomic semantic rejection and preceding-close corrections. No production
DB, original CSV, model/provider or connector is used. Local tests, browser checks,
package verification, real migration and human
financial-semantic acceptance are separate outcomes.

`backend/tests/test_account_lifecycle.py` exercises account deletion, owner/token
boundaries, history preservation and dated closure through Workspace HTTP APIs.
`tools/browser_account_ui.mjs` exercises the dashboard, sticky navigation, tab
scrolling, Glide registration, lifecycle dialogs and compact snapshots in real
desktop Chrome. `tools/browser_personal_finance.mjs` covers human draft posting,
actual-date entry separated from explicit legacy month-end transfer reconciliation.
`backend/tests/test_recorded_balances.py` covers actual dates, same-day records,
backfills, month gaps, precise changes, pending inputs, corrections, period bounds,
owner/Workspace isolation, old-report preservation and complete backup roundtrips.
`tools/browser_account_registry.mjs` verifies segment visibility, natural code order
and composable read-only filters. `tools/browser_recorded_balances.mjs` verifies
date entry, monthly comparisons, unknown gaps, folded history and desktop layouts.
`backend/tests/test_commodity_lifecycle.py` verifies safe commodity deletion,
reference/provenance preservation, opt-in metadata and Workspace authorization.
`tools/browser_commodities.mjs` exercises deletion cancellation, usage guards,
deactivation/editing, Overview refresh and desktop rendering on Schema-2/3 fixtures.
All browser scripts require owned
synthetic fixtures and a synthetic-server marker before authentication; they are
not scripts for the currently running personal Vault.

The authorized official reader 1.5.0 / protocol 2 pins API 3.5.0 exactly. Its source
and new local archive are verified without changing the read whitelist. Earlier
reader archives remain unchanged; reader 1.3.0 still rejects API 3.4.0. FRAG and its
installed pins are untouched and need a separately reviewed synchronization. FRAG remains restricted
to its explicitly authorized legacy report IDs; no new personal-report whitelist,
financial calculation or recommendation runtime is added.

Opening workflows, optional Notes and compatible activity-report semantics are documented in [Opening balances and Notes](06-opening-balances-and-notes.md). Reader 1.4.0 remains a historical API 3.4.0 artifact; the new 1.5.0 archive does not expand access or change Monthly Review v1.
