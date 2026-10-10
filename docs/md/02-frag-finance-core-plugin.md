# Optional Finance Core reader for FRAG-harness (v1.2.0)

Finance Core product 3.3.0 runs independently with API 3.2.0, ledger schema 2 and registry schema 1. Its optional protocol-2 reader exposes explicitly selected financial evidence; FC owns all calculations, authentication, storage and writes. FRAG owns authorization, bounded tool packs and reviewed Memory, not a finance runtime.

## Compatibility and artifact

| Item | Required version or path |
| --- | --- |
| FRAG plugin protocol | 2 |
| FRAG host | 1.12.1 or later |
| FC API | 3.2.0 |
| Reader version | 1.2.0 |
| Capability | `evidence.read` |
| Archive | `docs/release/finance-core-frag-plugin-v1.2.0.zip` |
| Source | `plugins/finance-core/manifest.json`, `adapter.py`, `ui.js` |
| Archive SHA-256 | `9d4f66b101183b19d5e50d807386c276cc77937517a6f7d59be813971ccd1ee6` |

The archive contains exactly those three root files. The manifest pins both code files; the host additionally pins exact package/archive bytes. `python tools/build_frag_plugin.py --check` verifies the current source and archive. Source files use LF so Git line-ending normalization cannot silently change the bytes. Earlier 1.0.0 and 1.1.0 archives remain unchanged historical artifacts. This is a local build handoff, not publication or production installation.

`ui.js` and the adapter's legacy GET dashboard routes remain archive compatibility content. Native FRAG does not mount a plugin UI, generic catalog or Dashboard. Journal changes open standalone FC and require FC authentication.

## Backend-only configuration

```dotenv
FINANCE_CORE_PLUGIN_API_URL=http://127.0.0.1:8788
FINANCE_CORE_PLUGIN_UI_URL=http://127.0.0.1:5174
FINANCE_CORE_PLUGIN_READ_TOKEN=<backend-only-ledger-read-token>
FINANCE_CORE_PLUGIN_RECORDS_JSON={"<approved-workspace>":["monthly-review:2025-03"]}
```

Use a scoped `ledger:read` token for the named Workspace. Never place credentials in browser inputs, Webview messages, tool packs, logs or Git. Endpoints must be credential-free HTTP loopback URLs. Requests do not follow redirects or inherit environment proxy settings. Installation does not authorize any source or record; humans configure the whitelist and enable the source separately.

## Evidence hooks

- `list_scopes(scope_id=None)` returns configured IDs in active, token-accessible Workspaces. Monthly labels are synthesized from exact IDs; discovery never fetches every configured report.
- `read_evidence_request(request)` accepts exactly `protocolVersion`, `pluginId`, `scopeId`, `recordIds`; protocol is integer 2. It returns the same protocol/plugin/scope and records in request order.
- One request names one Workspace and one to ten distinct configured IDs; the total configured record whitelist is also capped at ten. Arbitrary routes, wildcard months, duplicate IDs, unlisted records and cross-Workspace expansion are rejected.
- Each record has exactly `recordId`, `label`, `text`, `revision`. HTTP calls are GET only. FC health must identify `finance-core`, `ok` and API `3.2.0`; Workspace and record identity are validated.
- `source_revision()` binds supplier URL and whitelist without HTTP or credentials. The host checks package/configuration revisions before and after reads and rechecks record revisions at completion.

### Monthly report

`monthly-review:YYYY-MM` maps to `/api/v3/workspaces/{workspaceId}/reports/monthly-review?month=YYYY-MM`. It authorizes the exact completed anchor and preceding two months, not transaction details or a full Vault. A new anchor requires a human whitelist change.

FC's strict summary includes schema/calculation version, month window, stable source revision, three month rows, per-currency exact Decimal strings, changes, signed reversal adjustments and coverage. Account roles reflect current Master data; invalid posted dates block totals; real-world completeness remains unknown. Cash and recognized income/expenses are distinct axes. Currencies are not implicitly converted or combined. No account names/IDs, Journal descriptions, references or posting memos enter the summary.

The adapter rejects extra/missing/unsafe summary fields and emits the full report without its legacy 8,000-character truncation. The native host marks it required: byte fitting, tokenizer fitting and completion either retain it whole or reject delivery. A stable report revision excludes request timestamps and random snapshots.

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
