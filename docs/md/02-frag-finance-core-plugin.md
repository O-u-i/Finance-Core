# Optional Finance Core plugin for FRAG-harness (v1.0.0)

Finance Core 3.1.1 runs independently. FRAG-harness can install this separate, read-only plugin to show an FC dashboard and a small set of user-selected Journal records through FC's published HTTP API. FC domain, application, API, SQLite, and standalone UI do not depend on FRAG. Journal changes open FC's own UI, where FC authenticates the user and performs every write.

## Compatibility and artifact

| Item | Required version or path |
| --- | --- |
| FRAG plugin protocol | 1 |
| FRAG host | 1.0.0 or later |
| FC API | 3.1.1 |
| Plugin version | 1.0.0 |
| Archive | `docs/release/finance-core-frag-plugin-v1.0.0.zip` |
| Source | `plugins/finance-core/manifest.json`, `adapter.py`, `ui.js` |

The archive root contains exactly `manifest.json`, `adapter.py`, and `ui.js`. The manifest pins SHA-256 hashes for both code files. Run `python tools/build_frag_plugin.py --check` to obtain and verify the archive SHA-256 before installation. `.gitignore` has an explicit exception for this official ZIP. Git staging, commits, and publishing remain separate user decisions.

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

## FC read contracts

- `GET /api/v3/health` checks `service=finance-core`, `status=ok`, and `apiVersion=3.1.1`.
- `GET /api/v3/workspaces` verifies active Workspaces accessible to the read token.
- `GET /api/v3/workspaces/{workspaceId}/dashboard` reads FC-calculated dashboard values; money remains Decimal strings.
- `GET /api/v3/workspaces/{workspaceId}/journal-entries/{entryId}` and `GET /api/v3/workspaces/{workspaceId}/journal-entry-drafts/{draftId}` read only configured selected records.

No new FC endpoint or API version is required. The plugin exposes only `GET /api/plugins/finance-core/scopes` and `GET /api/plugins/finance-core/dashboard?workspaceId=...`. Its frontend calls only same-origin FRAG plugin routes. The backend rejects an invalid Workspace, unconfigured records, duplicates, and more than ten IDs. An incompatible FC API version returns 409; missing configuration, timeout, or FC outage returns 503. Responses and errors must not expose tokens, database paths, or private request bodies.

## Verify and install

```powershell
python tools/build_frag_plugin.py --check
npm.cmd test
npm.cmd run check:release
npm.cmd run check:versions
```

In the FRAG repository, use its installation process with `-ArchivePath` and the checked `-ExpectedSha256`, then restart FRAG. FRAG manages installation and enabled state; this FC repository does not modify FRAG files. FRAG's `current.json` must point to plugin `1.0.0` with `enabled: true`. Only FRAG loads the plugin routes and frontend bundle.

Historical SFOS migration notes, the 3.0.0 Horizon, and v1/v2 API notes retain their historical meaning. This document describes only the current optional plugin; it does not change FC's deterministic calculations, authentication, or database write ownership.
