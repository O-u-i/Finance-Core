# Optional Finance Core plugin for FRAG-harness (v1.1.0)

Finance Core product 3.2.0 runs independently and exposes released API 3.1.1. FRAG-harness can install this separate, read-only plugin to show an FC dashboard and a small set of user-selected Journal records through FC's published HTTP API. FC domain, application, API, SQLite, and standalone UI do not depend on FRAG. Journal changes open FC's own UI, where FC authenticates the user and performs every write.

## Compatibility and artifact

| Item | Required version or path |
| --- | --- |
| FRAG plugin protocol | 2 |
| FRAG host | 1.8.0 or later |
| FC API | 3.1.1 |
| Plugin version | 1.1.0 |
| Capability | `evidence.read` |
| Archive | `docs/release/finance-core-frag-plugin-v1.1.0.zip` |
| Source | `plugins/finance-core/manifest.json`, `adapter.py`, `ui.js` |

The archive root contains exactly `manifest.json`, `adapter.py`, and `ui.js`. The manifest pins SHA-256 hashes for both code files and declares the generic read-only evidence capability. Run `python tools/build_frag_plugin.py --check` to obtain and verify the archive SHA-256 before installation. `.gitignore` has an explicit exception for this official ZIP. Git staging, commits, and publishing remain separate user decisions.

The original `docs/release/finance-core-frag-plugin-v1.0.0.zip` remains byte-identical, with protocol 1 and minimum host 1.0.0. Hosts retain protocol 1 support; the new protocol 2 artifact requires host 1.8.0. FC product, API, database and plugin versions remain independent.

Existing protocol 1 runtime memories remain visible in history under their original identity. FRAG host 1.8.0 binds FC evidence identities to the configured supplier and selected candidate list for both protocols. Old unqualified protocol 1 memories are not automatically recommended or injected after upgrading the host, including when continuing to use the original protocol 1 archive. Reusing an applicable lesson requires a new candidate from the current source and explicit human review/promotion. The host never silently rebinds historical memory to a new supplier.

FRAG leads host policy, registries, CLI, evaluation, model providers, common plugin interfaces and integration acceptance. FC owns this plugin's editable source, its released HTTP contracts and all financial calculations, storage, authentication and standalone UI. FRAG installs pinned build output; it does not maintain a second editable FC adapter.

## Backend-only configuration

Configure these variables in the FRAG backend environment. Create an FC access token scoped to the intended Workspace with `ledger:read` only. Never place it in browser code, a URL, logs, screenshots, or Git.

```text
FINANCE_CORE_PLUGIN_API_URL=http://127.0.0.1:8788
FINANCE_CORE_PLUGIN_UI_URL=http://127.0.0.1:5174
FINANCE_CORE_PLUGIN_READ_TOKEN=<backend-only-scoped-read-token>
FINANCE_CORE_PLUGIN_RECORDS_JSON={"<workspace-uuid>":["entry:<entry-id>","draft:<draft-id>"]}
```

`FINANCE_CORE_PLUGIN_RECORDS_JSON` is an explicit candidate list selected by the local user. Across all Workspaces it may contain at most ten distinct record IDs. The plugin does not scan entire Journal lists or open the FC Registry or Vault SQLite. With no candidates, `GET /scopes` returns an empty list. Without a token, or while FC is unavailable, it returns an unavailable state. API and UI URLs must be loopback HTTP addresses.

`entry:` and `draft:` IDs map to FC 3.1.1 single-record read endpoints. `GET /scopes` shows only active Workspaces accessible to the token and their configured records. `read_evidence(workspace_id, record_ids)` accepts one Workspace and one to ten distinct configured IDs. It returns one dictionary per requested ID, in the same order, with exactly `recordId`, `label`, `text`, and `revision`. The revision is the SHA-256 of FC's canonical JSON for that record. Each text is limited to 8,000 characters and summarizes date, description, status, and bounded posting fields. It is not a full ledger export.

## Protocol 2 evidence interface

`list_scopes(scope_id=None)` returns `{"scopes": [...]}` with the same `id`, `label` and `records` fields used by the existing scope route. Each record has `id` and `label`. An optional scope ID restricts discovery to one configured, active Workspace; invalid or unconfigured IDs are rejected before any HTTP request. Discovery reads only configured records, never a complete Journal list.

`read_evidence_request(request)` accepts exactly these four fields:

```json
{
  "protocolVersion": 2,
  "pluginId": "finance-core",
  "scopeId": "synthetic-workspace",
  "recordIds": ["entry:synthetic-entry", "draft:synthetic-draft"]
}
```

The response contains exactly `protocolVersion`, `pluginId`, `scopeId` and `records`. Its scope and plugin match the request, and its records retain the requested order and the four legacy evidence fields. The host validates this envelope before binding evidence to a prepared request. These interfaces grant no authority to expand the selected Workspace or records, choose arbitrary endpoints, execute model calls or write financial data. The legacy `read_evidence` hook remains available in the adapter; protocol 2 delegates to that same bounded read implementation.

`source_revision()` returns a lowercase SHA-256 of a canonical JSON descriptor containing the configured read API URL (without a trailing slash) and the exact configured candidate-list JSON. It requires no token and makes no HTTP request. Credentials, authentication headers and the standalone UI URL are excluded; descriptor values are not returned or stored as part of this interface. The host pins this revision when loading the plugin, binds it into prepared source identities and parser versions, and rejects configuration changes before or during a read. After changing the supplier or configured candidates, restart FRAG and select sources again for a fresh preview and approval. A matching record-content revision alone does not preserve approval across a source-configuration change.

## FC read contracts

- `GET /api/v3/health` checks `service=finance-core`, `status=ok`, and `apiVersion=3.1.1`.
- `GET /api/v3/workspaces` verifies active Workspaces accessible to the read token.
- `GET /api/v3/workspaces/{workspaceId}/dashboard` reads FC-calculated dashboard values; money remains Decimal strings.
- `GET /api/v3/workspaces/{workspaceId}/journal-entries/{entryId}` and `GET /api/v3/workspaces/{workspaceId}/journal-entry-drafts/{draftId}` read only configured selected records.

No new FC endpoint or API version is required. The plugin exposes only `GET /api/plugins/finance-core/scopes` and `GET /api/plugins/finance-core/dashboard?workspaceId=...`. Its frontend calls only same-origin FRAG plugin routes. The backend rejects an invalid Workspace, unconfigured records, duplicates, and more than ten IDs. An incompatible FC API version returns 409; missing configuration, timeout, or FC outage returns 503. Responses and errors must not expose tokens, database paths, or private request bodies.

## Verify and install

```powershell
backend\.venv\Scripts\python.exe tools/build_frag_plugin.py --check
npm.cmd test
npm.cmd run check:release
npm.cmd run check:versions
```

In the FRAG repository, use its installation process with `-ArchivePath` and the checked `-ExpectedSha256`, then restart FRAG. FRAG manages installation and enabled state; this FC repository does not modify FRAG files. FRAG's `current.json` must point to plugin `1.1.0` with `enabled: true`. Only FRAG loads the plugin routes and frontend bundle. Synthetic plugin tests verify protocol 2 discovery and request rejection, source-configuration changes with identical record content, credential exclusion, its actual released FC read API, the legacy archive hash and the unchanged read-only routes. Real financial records are not test fixtures.

Historical SFOS migration notes, the 3.0.0 Horizon, and v1/v2 API notes retain their historical meaning. This document describes only the current optional plugin; it does not change FC's deterministic calculations, authentication, or database write ownership.
