# Configuration, sessions and journal CSV round trips

Finance Core service 3.2.0 retains API 3.1.1, schema 2/1 and FRAG plugin 1.0.0 / protocol 1. The published OpenAPI hash is unchanged. The CSV export receives compatible additional context columns; existing columns retain their names and order. No dependencies, finance calculation rules, personal Vaults or other repositories are changed.

## Navigation and setup

Master data and Settings occupy the configuration row above the financial navigation. Their readiness is visible through text and contrasting green Ready / amber Setup required surfaces. The Workspace kind is a compact label beside Workspace rather than a detached control. The financial sequence is Journal → T-accounts → Securities & positions → Cash flow → Statements; Overview, Living & plans and Import & export remain separate destinations. Legacy `#/reports/...` links resolve to the corresponding new destination. Report categories are independent read models from the same posted ledger, not a mandatory posting wizard.

Financial pages are blocked until an authenticated owner session and available Workspace are present, plus at least two active accounts that support the same active currency. There is no requirement to create external access tokens or security prices for ordinary currency Journal use. Missing prices remain relevant to valuation. Archived records remain readable and mutations remain prohibited. An empty sandbox can load the existing synthetic fixture; Settings can restore a backup into an empty ledger before configuration is established. Account commodity permissions can contain multiple explicitly registered codes, such as CNY and MYR.

Readiness is rechecked with scoped page refreshes and is cleared on Workspace changes and sign out. Direct hash links cannot display a financial page while setup is incomplete. This is a UI setup gate; existing backend authentication and financial validation remain authoritative.

## Session exit

An existing valid HttpOnly cookie can restore a session without asking for the admin token again. The header distinguishes a restored session from a fresh token login. Sign out immediately invalidates reads and removes visible records, Workspace state and one-time tokens. If backend revocation fails, the login page explains that the saved cookie session still requires revocation. Forget saved sign-in remains available on login and connection-error screens. A completed sign out prevents the next reload from restoring records.

## CSV input and output

Import & export opens the CSV import form by default. Journal also links directly to input and output. Standard FC posting CSV and the previously supported accounting template remain available. Accounting grouping and account mapping require explicit confirmation; no account classification or exchange rate is inferred.

Unknown, inactive or inappropriate commodity codes, and account commodity mismatches, produce a native modal rejection dialog with row-level reasons and instructions to correct Master data. Unused currency columns do not require a registration. Escape closes the dialog and retains input. Backend validation failures during CSV submission also reject the import without silently dropping input.

Downloads use the scoped API client, report errors inside the UI and lock Workspace switching during the request. CSV includes only posted Journal entries; drafts are included in JSON exports and backups. The CSV export previously omitted `balancingCommodityCode`, which its own importer requires. A failing regression reproduced that defect before the compatible repair. Export now appends balancing commodity, payee, source, reference, tags and posting memo. Native download and reimport retain decimal strings and Journal context. JSON backups remain the complete recovery format, including security-lot and reversal metadata; CSV is not a replacement for a ledger backup.

## Verification and data boundaries

- 70 backend tests passed, including architecture and contract checks. The strengthened CSV-context regression also passed separately. The existing Starlette/httpx deprecation warning remains.
- 14 frontend tests passed, including readiness, old route compatibility, missing/inactive commodity rejection and the existing Decimal/request-state regressions.
- 28 browser check groups passed across the existing synthetic lifecycle suite, with all ten pages checked at 320, 375, 768, 1024 and 1440px.
- Seven additional browser groups passed: restored-session sign out; simulated connection failure during cookie revocation and successful recovery; keyboard-dismissable commodity rejection with retained input; native CSV/JSON/backup downloads and CSV reimport; creation/editing of multi-commodity account permissions; Workspace label alignment at five widths and distinct readiness colors; nonzero Statements from the explicitly classified synthetic fixture. Revocation failure was injected at Chrome's network interception layer, not an actual backend outage.
- Browser screenshots of the upper configuration row, financial sequence and rejection dialog were visually inspected at desktop and narrow widths. Physical-device and exhaustive screen-reader testing are not claimed.
- Production build, frontend MIT notice check, version synchronization and release/OpenAPI checks passed. The existing plugin protocol and Horizon baseline are retained.

The supplied project-local CSV was read only through the actual client checker and mapper: 48 rows → 24 drafts / 48 postings, all amounts kept as strings. Mapping used temporary in-memory account identities and confirmed row-order grouping for structural verification only. This does not certify real account classification. Original rows were not imported, posted or copied into browser evidence, fixtures or public artifacts.

The independent test service contains a sandbox named **journal-test** with CNY/MYR and five explicitly classified synthetic accounts (two assets, equity, income and expense). Its 48-row sanitized derivative produced 24 drafts, which were posted for export testing. The UI downloaded 48 postings; the downloaded CSV was imported into another sandbox as 24 unposted drafts with no posted entries. Dates, account identities, descriptions, context and amounts in these persisted test records are synthetic. They do not represent the original CSV's financial results.

The existing standard API service rejected this task's available administrator credential with HTTP 401. No Workspace was created there and no existing personal Vault was changed. The `journal-test` sandbox belongs to the separate test service, not the standard API service.

## Local handoff

The independent test service uses API port 18788; Vite uses 5174 with `FC_UI_API_TARGET` pointed to that API. Test services are retained for review. Their database and screenshots remain under ignored `.tmp/` paths. To resume the same private synthetic test data, run the API and UI in separate PowerShell terminals from the repository root:

```powershell
$env:FINANCE_CORE_DATA_ROOT = Join-Path (Get-Location).Path '.tmp/journal-test-run-20261001'
$env:FINANCE_CORE_ADMIN_TOKEN = 'synthetic-browser-admin' # This is only the synthetic test credential.
uv run --offline --no-sync --project backend --cache-dir .tmp/uv-cache uvicorn finance_core.main:app --host 127.0.0.1 --port 18788 --no-access-log
```

```powershell
$env:FC_UI_API_TARGET = 'http://127.0.0.1:18788'
npm.cmd run dev:demo
```

Open the printed Vite URL, use the synthetic test credential, and select journal-test. Returning to the ordinary service requires restarting Vite with its normal API target and using that service's own configured admin credential. Never point automated browser checks at a personal Vault or supply original CSV data to `FC_TEST_ACCOUNTING_CSV`.

Changes are in the existing App, state, shared controls and business pages, plus `demo/src/navigation.js`, `pages/Setup.jsx`, CSV rejection/readiness tests, the compatible CSV exporter, and browser regression tools. Public documents contain only generic design and verification results. Local rules, source CSV/PNG, test data and screenshots remain ignored; tracked and staged paths are audited separately. No commit, push or deployment is performed.

Proposed commit message: `Reorganize Finance Core setup and financial navigation and fix CSV round trips`

```text
Cross-repo impact: NONE
Contract change: ADDITIVE
Other repo status: NOT_TOUCHED
Required compatible version: FC service 3.2.0; API 3.1.1; FRAG plugin 1.0.0; protocol 1; host >=1.0.0
Reason: Compatible CSV export context columns; JSON/OpenAPI and financial semantics retained.
Prompt for the other repo: No implementation required. Existing protocol-1 scoped reads remain compatible; no CSV integration is required.
```

The FINCR wordmark and complete-wordmark favicon use the supplied spacing reference's gap-to-cap-height proportions. Letter outlines remain the original local vector paths; no reference-brand glyphs or fonts are copied. Display widths increase slightly to preserve glyph height while adding tracking.

The original CSV transport fixture assigned all accounts to asset. Its per-account T-account movements were nonzero, while category totals netted to zero. The independent synthetic journal-test fixture was corrected through scoped account APIs; posted entries, units and dates were preserved. Browser regression now checks that Statements has nonzero category totals. The login page explains Forget saved sign-in and separates it from the primary login action. Reports include an explicit refresh action.
