# Financial-read access · API 3.10.0

## User flow

1. Open FC **Settings → Connect FRAG** in an owner session.
2. Choose one active Vault and **All / Living / Investment / Specific accounts or data items**.
3. Create the read-only connection, then **Copy FRAG configuration**. The four lines already contain the loopback API/UI addresses, token and Workspace ID. Initial FRAG record selection is empty.
4. In VS Code: `Ctrl+Shift+P` → `FRAG: Connect Finance Core`. Paste/save in the prepared private `fc.env` opened in Notepad. FRAG's matching Host prepares the official reader automatically.
5. In FRAG Settings, **Check connection**, select a smaller subset, approve and **Save authorization**. Checking reads identity, permission and item names only, not financial reports.

The configuration is shown once in the FC owner UI. It is cleared on navigation, Workspace switch or sign-out and never stored in browser storage. Keep the copied secret local; never paste it into chat, a Webview, Git, screenshots or logs. FC owner authentication is never passed to FRAG.

## Token contract

`POST /api/v3/access-tokens` retains its existing owner-session contract. Optional `readGrant` creates a dedicated financial-read token:

```json
{
  "name": "Local financial reader",
  "workspaceIds": ["selected-vault-id"],
  "scopes": ["ledger:read"],
  "readGrant": {"mode": "living", "itemIds": []}
}
```

| Mode | Authorization ceiling |
| --- | --- |
| `all` | Supported financial read projections in this one Vault, including future items and full-scope reports. |
| `living` | Living accounts, assets, cash-flow plans and transfer observations, including future items. No whole-Journal or whole-Vault report. |
| `investment` | Investment accounts/agreements and explicitly dated whole-Journal monthly/month-to-date reports. No Living or whole-Vault economic report. |
| `selected` | Exact checked current item IDs. An explicitly checked report grants its named full aggregate scope. Unknown future IDs are rejected. |

Nonselected modes require empty `itemIds`; selected mode requires distinct valid IDs, at most 500. Exactly one Workspace and read-only scope are mandatory. Duplicate or invalid item requests issue no token. The token's date-independent range is the maximum; FRAG still explicitly selects records and report dates beneath it.

The owner receives the secret once; `Cache-Control: no-store` prevents response caching. Token metadata and `GET /api/v3/access-token-self` include `readGrant` but never the secret. Existing expiry/revocation applies. New tokens are `fcv3r_…`; older FC releases reject that prefix instead of silently ignoring a scope restriction. Legacy `fcv3_…` tokens retain previous capabilities and never gain these personal reader routes.

Dedicated grants permit GET only, through the catalog/item routes or an authorized released summary. Raw Journal collections, owner financial routes, backups/restores, token management, other Vaults and writes are denied. Item membership is revalidated inside the financial read transaction. Renaming or adding records does not let a token cross its Vault/segment boundary.

## General API access and irreversible cleanup

**Settings → API access** is a separate, visible form for non-FRAG local clients.
Its **Read / Write / Both** selector maps exactly to `ledger:read`,
`ledger:write`, or both scopes. Write alone does not grant read access. These
tokens do not receive `readGrant`, owner privileges or a FRAG configuration.
The **Connect FRAG** form remains dedicated to read-only grants.

An owner session may explicitly remove inactive control-plane records:

- `DELETE /api/v3/access-tokens/{token_id}` requires a revoked or expired token
  and `{"confirmName":"exact current token name"}`. It deletes the token record
  and its optional read grant; an active token must first be revoked. Removed
  credentials cannot authenticate again.
- `POST /api/v3/workspaces/{workspace_id}/purge` requires an already quarantined
  Vault and `{"confirmName":"exact current Vault name"}`. It validates the
  quarantine operation's recorded single-file move and rejects extra files,
  changed/linked paths, hardlinks or a missing database without a matching
  prior purge intent. It removes exactly that database and the Vault record;
  it never recursively deletes directories, sidecars or backups.

Both routes require an owner session, retain same-origin protection and audit
history, return no credentials or private paths, and have **no undo**. No
access token, including Write or Both, can call them. The UI displays the
record ID and requires typing the exact name before enabling the destructive
button, so duplicate names can be distinguished.

Vault purge persists its irreversible intent, consumes the Vault's workspace
undo records and revokes tokens containing that Vault **before** unlinking.
Failure may therefore leave undo unavailable even if the file remains; a
failure after unlinking can leave a quarantined metadata row. Refresh and
review before explicitly confirming a retry. A matching prior intent allows
that retry to finish metadata cleanup; FC does not retry automatically.
Empty directories, audit history, backups and exported copies remain. This
does not promise secure erasure, backup deletion or restoration of deleted data.

## Released read endpoints

### `GET /api/v3/workspaces/{workspaceId}/reader/catalog`

Owner session or dedicated financial-read grant; legacy tokens are denied. Returns:

- `workspaceId`, `readOnly: true`;
- `data.schemaVersion: 1`, `data.readGrant`;
- authorized `items`: exact opaque `id`, human-readable `label`, `kind`, `segment`.

No balances, postings, dates or report facts are fetched for this discovery. Catalog limit: 500 items and 60 KiB of item JSON; overflow refuses, never silently truncates. Ledger schema 3 is required; reads never migrate a Vault or require historical re-entry.

Items include `account`, `asset`, `plan`, `arrangement`, `transfer` and the report families `report:monthly-review`, `report:month-to-date`, `report:economic-evidence`. Monthly reports describe the whole Journal; economic evidence describes its whole-Vault recorded scope. Report dates remain explicit in the existing report endpoints.

### `GET /api/v3/workspaces/{workspaceId}/reader/items/{itemId}`

Returns one complete safe projection, with `schemaVersion`, exact `itemId`, `label`, `kind`, `segment`, content-bound SHA-256 `revision`, `content` and:

```json
{"selectionOnly": true, "externalCompleteness": "unknown", "financialAdviceReady": false}
```

| Item | Safe content |
| --- | --- |
| Account | Account metadata, its balance observations, its own ledger posting lines when ledger-backed, its recorded repayment arrangements. |
| Asset | Asset metadata and its valuation observations. |
| Plan | Cash-flow plan identity, exact amount/currency, schedule and category. |
| Arrangement | Agreement metadata, claims, interest arrangements and residual shares. |
| Transfer | Living transfer observations for the selected currency. |

No notes, free-form sources/reasons, baseline evidence, or other-side Journal postings are included. Account lines are **not balanced whole entries**. Existing missing debt dates remain unknown; no maturity or personal disposable amount is inferred. Financial amounts stay exact decimal strings, with no reader/UI recalculation. Full owner reports and arbitrary fields are not exposed by an `all` grant.

Revision binds the exact emitted projection, not request time or the token. The official adapter validates allowlisted shapes, identity, membership references, decimal strings and revision before emitting the whole record. FRAG marks each selected financial item required; byte/token overflow refuses delivery instead of trimming it.

## Versions, storage and rollback

FC product/API **3.10.0**, official reader **1.10.0 / protocol 2**, minimum FRAG Host **1.13.4**. The [reader artifact contract](02-frag-finance-core-plugin.md) records exact bytes; no floating latest.

Financial ledger schema remains **3**; existing records, debt history and dates are unchanged. Registry schema version remains **1** with an additive `access_token_read_grants` child table created atomically only when an owner explicitly creates the first dedicated token. Startup and legacy-token use do not create it. Tokens are control-plane state, not data imported into a Vault backup.

Revoke an issued grant in **Settings → Issued access**. No financial records are changed. Retain registry/Vault backups and old installations for a reviewed rollback; never replace new scoped tokens with unrestricted legacy ones to defeat their restriction. FRAG preserves an explicit reader disable and can disable the source without FC being online. No automatic commit, release, production installation, real financial Run or Slice C is included.

Synthetic HTTP regression, official-reader compatibility, isolated loopback integration, native-window verification and human financial-semantic acceptance are distinct. Selected item facts do not prove complete economic coverage, recommendation correctness, model consumption or human adoption.
