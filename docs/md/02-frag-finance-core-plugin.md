# Optional Finance Core reader for FRAG-harness (v1.10.0)

Finance Core product 3.10.0 runs independently with API 3.10.0, ledger schema 3 and registry schema 1. Its optional protocol-2 reader exposes explicitly selected financial evidence; FC owns all calculations, authentication, storage and writes. FRAG owns authorization, bounded tool packs and reviewed Memory, not a finance runtime.

## Compatibility and artifact

| Item | Required version or path |
| --- | --- |
| FRAG plugin protocol | 2 |
| FRAG host | 1.13.4 or later |
| FC API | 3.10.0 |
| Reader version | 1.10.0 |
| Capability | `evidence.read` |
| Archive | `docs/release/finance-core-frag-plugin-v1.10.0.zip` |
| Source | `plugins/finance-core/manifest.json`, `adapter.py`, `ui.js` |
| Archive SHA-256 | `99379f5e7cb384eae4d767d861df1a807b8fe83c14a77f9762a58ffebe6caa1c` |

The archive contains exactly those three root files. The manifest pins both code files; the host additionally pins exact package/archive bytes. `python tools/build_frag_plugin.py --check` verifies the current source and archive. Source files use LF so Git line-ending normalization cannot silently change the bytes. Earlier 1.0.0 through 1.9.0 archives remain unchanged historical artifacts. This is a local build handoff, not publication or production installation. The current BOTH task synchronizes FRAG 1.13.4 exact pins; no production installation is implied.

`ui.js` and the adapter's legacy GET dashboard routes remain archive compatibility content. Native FRAG does not mount a plugin UI, generic catalog or Dashboard. Journal changes open standalone FC and require FC authentication.

## One-flow connection

In **FC Settings → Connect FRAG**, choose one Vault and a range: **All / Living / Investment / Specific accounts or data items**. Create and **Copy FRAG configuration**. API/UI addresses, read token and Workspace ID are assembled automatically; the initial record selection is empty. The secret is shown once in this owner UI and never stored in browser storage.

In VS Code: `Ctrl+Shift+P` → `FRAG: Connect Finance Core`. The matching Host already includes the exact reader and opens its private `fc.env` in Notepad. Paste/save, then **Check connection**, select the smaller FRAG subset and explicitly **Save authorization**. No standalone reader installation or JSON editing. Keep credentials out of chat, Webviews, logs, screenshots and Git. [API/grant contract and rollback](12-financial-reader-access.md).

Connection checking fetches metadata only: health, token-self claims, active Workspace and authorized item names. The new backend-only `configure_connection(values)` configures an isolated reader instance without mutating process environment; invalid configuration leaves its previous settings intact. `connection_catalog()` is a management hook, not another model tool. Existing environment-based legacy integration retains its prior read boundary.

## Evidence hooks

- `list_scopes(scope_id=None)` returns configured IDs in active, token-accessible Workspaces. Monthly, month-to-date and economic labels are synthesized from exact IDs; discovery never fetches every configured report.
- `read_evidence_request(request)` accepts exactly `protocolVersion`, `pluginId`, `scopeId`, `recordIds`; protocol is integer 2. It returns the same protocol/plugin/scope and records in request order.
- One request names one Workspace and one to ten distinct configured IDs; the total configured record whitelist is also capped at ten. Arbitrary routes, wildcard dates/months, duplicate IDs, unlisted records and cross-Workspace expansion are rejected.
- Each record has exactly `recordId`, `label`, `text`, `revision`. HTTP calls are GET only. FC health must identify `finance-core`, `ok` and API `3.10.0`; Workspace and record identity are validated.
- `source_revision()` binds supplier URL and whitelist without HTTP or credentials. The host checks package/configuration revisions before and after reads and rechecks record revisions at completion.

### Monthly report

`monthly-review:YYYY-MM` maps to `/api/v3/workspaces/{workspaceId}/reports/monthly-review?month=YYYY-MM`. It authorizes the exact completed anchor and preceding two months, not transaction details or a full Vault. A new anchor requires a human whitelist change.

FC's strict summary includes schema/calculation version, month window, stable source revision, three month rows, per-currency exact Decimal strings, changes, signed reversal adjustments and coverage. Account roles reflect current Master data; invalid posted dates block totals; real-world completeness remains unknown. Cash and recognized income/expenses are distinct axes. Currencies are not implicitly converted or combined. No account names/IDs, Journal descriptions, references or posting memos enter the summary.

The adapter rejects extra/missing/unsafe summary fields and emits the full report without its legacy 8,000-character truncation. The native host marks it required: byte fitting, tokenizer fitting and completion either retain it whole or reject delivery. A stable report revision excludes request timestamps and random snapshots.

### Provisional month-to-date report

`month-to-date:YYYY-MM-DD` maps only to `/api/v3/workspaces/{workspaceId}/reports/month-to-date?asOf=YYYY-MM-DD`. It selects the first day of that month through the exact nonfuture date, inclusive. It needs only `ledger:read`, never an owner credential. Discovery does not fetch the report. The strict whole summary rejects extra/private fields, floats and unjustified completeness claims; insufficient Host capacity refuses delivery. See the [month-to-date contract](11-month-to-date-review.md).

The report is explicitly partial and covers posted Journal activity only. It does not imply zero real activity on unrecorded days, compare a partial month with whole months, derive spending from balance observations or provide a balance sheet. No change to the completed-month contract or write capability is included.

### Bounded economic evidence

`economic-evidence:YYYY-MM-DD:YYYY-MM-DD` maps only to `/api/v3/workspaces/{workspaceId}/reports/economic-evidence?asOf=...&through=...`. Both dates and their 1–366 day horizon are validated before HTTP. No wildcard, inferred current window, owner route or debt-detail read is available. The token needs only `ledger:read`.

The strict summary includes gross per-segment/per-currency balances, observed dates, planned outflows, confirmed current-balance repayment dates, debt outside the selected horizon and explicit coverage/missing facts. Null/unknown facts never become zero. Forecast plans are not debt maturities; future charges, external completeness and personal disposable availability remain unknown. No account IDs/names, agreements, free-text sources or private notes enter the summary. See [economic evidence and debt timing](10-economic-evidence-and-debt-timing.md).

The adapter rejects extra/missing/unsafe wire fields without recalculating finance values, and emits the entire report. FRAG 1.13.4 marks it required through byte fitting, token fitting and completion; insufficient capacity refuses delivery. A draft or stale repayment arrangement cannot satisfy dated-obligation coverage. The reader has no financial mutation or confirmation capability.

### Explicit detail records

`entry:<approved-id>` and `draft:<approved-id>` map to their existing single-record endpoints. Their prior bounded formatting is unchanged, including an 8,000-character text limit. These IDs require separate explicit whitelist authorization; a report does not authorize automatic detail reads. Parent/reference source fields are context, not agent instructions or permissions.

## Build and verification

```powershell
python tools/build_frag_plugin.py
python tools/build_frag_plugin.py --check
npm.cmd run check:release
npm.cmd run check:versions
```

Default tests are synthetic: archive/file integrity, protocol validation, GET-only scope isolation, no HTTP on invalid requests, safe discovery, complete monthly formatting, strict field rejection and stable revisions. Explicit private CSV acceptance uses isolated ignored Vaults without modifying originals or calling providers; sources, raw logs, reports, databases and screenshots stay out of Git. Local contract, browser, live loopback, provider and human financial-semantic acceptance are different claims. Both repositories may be updated directly under the current unified authorization; commits, pushes, tags, public release and production installation remain separate human actions.

### Selected financial items

`finance-item:<kind>:<opaque-id>` maps only to `GET /api/v3/workspaces/{workspaceId}/reader/items/{itemId}`. The schema-1 whole safe projection supports accounts with their own observations/posting lines/repayments, assets with valuations, cash-flow plans, agreements and per-currency Living transfer observations. Notes, source text, baseline evidence and other-side Journal postings are excluded. Account posting lines are not a balanced whole entry. No values are recalculated in the adapter.

`reader/catalog` returns authorized names and kinds only; item discovery never fetches every record. All selected item evidence is whole required content in FRAG, with strict shape/revision/identity validation; overflow refuses rather than windows. Selection-only coverage explicitly retains external completeness unknown and financialAdviceReady false. It is not a substitute for the complete economic-evidence contract.

Dedicated financial-read grants are enforced server-side before ledger access and again at item read. Living excludes Investment/whole-Journal reports; Investment excludes Living and whole-Vault economic reports; specific grants see only checked items, including an explicitly selected full-scope report when applicable. All means supported financial read projections inside one Vault, including future items, not arbitrary owner endpoints or backups. Legacy tokens never gain these new routes. [Contract](12-financial-reader-access.md).

All other owner-session routes remain owner-only, including full personal balance-sheet, reconciliation and management paths. The official reader is GET-only; debt recording and all financial mutations stay in FC. This local artifact is not publication or production installation. Real financial Run and human acceptance remain separate authorized steps.
