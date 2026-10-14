# Opening balances and optional Notes

Product 3.6.0 / API 3.5.0 / ledger schema 3 / registry schema 1.
This is an additive local implementation, not a public release, real-Vault
migration, FRAG installation or authorization for a financial action.

## Entry and reporting basis

Use **Master data → Opening balances**, also linked from Journal. The horizontal
navigation, brand, controls and read-only Overview remain intact.

Investment opening is stock on an explicit activation date, not period income,
spending or a capital flow. Select existing asset/liability/equity accounts, one
balancing currency, a source and an explicit equity counterpart. Positive assets
use debits; positive liabilities/equity use credits. The backend derives the exact
counterpart, then reuses ordinary draft validation, immutable posting and lots.
The GUI does not calculate money or ownership. Ownership agreements, reporting
settings and reconciliation remain separate; opening stock does not confirm them.

Save a draft, validate it, inspect the postings, and separately confirm posting.
The new confirmation path compares the reviewed `updatedAt` inside the writer
transaction before validation and insertion. A changed draft requires renewed
review. The old generic Journal post contract retains its default behavior.

Securities need positive units, explicit positive unit cost in the balancing
currency and a lot ID. A market quote is not acquisition cost. The existing lot
writer records the opening lot at the activation date; no original acquisition
date is inferred. Unsupported zero-cost securities fail explicitly. Zero currency
stock needs no invented Journal transaction. Record currencies separately rather
than inferring FX; negative currency stock uses the opposite normal side.

An opening cannot follow earlier facts for its account/commodity or overlap an
existing opening. Subsequent ordinary Journal/CSV posting also cannot introduce
facts before that baseline. Correction requires an explicit predecessor, matching
date/scope/equity and a linked reversal effective on that same date. A later-date
reversal cannot retroactively replace the earlier stock: use an actual-date
adjustment. Existing lot-consumption/reversal protections are not bypassed.

Living opening uses the existing immutable actual-date observation writer. Its
date must precede existing dated records for the account; subsequent observations
and explicit corrections use **Accounts & balances**. It accepts an explicitly
observed zero, creates no Journal entry, estimates no income/spending, does not
invent month-end values and leaves missing months unknown. Earlier monthly
observations and confirmed closes retain their original basis.

## Additive Workspace API

All paths below are under `/api/v3/workspaces/{workspaceId}` and require an owner
session. Existing bearer reader scopes are not widened.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/opening-balance-drafts` | Construct and check Investment stock; do not post |
| GET | `/opening-balances` | Classified unposted drafts, posted originals and reversals |
| POST | `/opening-balances/{draftId}/post` | Confirm the reviewed version using `confirmed: true` and `expectedUpdatedAt` |
| POST | `/opening-living-balances` | Append the first actual-date Living balance through the original writer |
| GET | `/reports/activity-cash-flow?month=YYYY-MM` | Separate `activity` and `openingEffects`, calculation `opening-activity-v1` |
| GET | `/reports/monthly-activity-review?month=YYYY-MM` | Three completed months, calculation `monthly-activity-v1`, excluded `openingEntryIds` |

Opening request example (synthetic accounts must already be registered):

```json
{
  "id": "opening-example",
  "date": "2026-08-01",
  "balancingCommodityCode": "CNY",
  "equityAccountId": "opening-equity",
  "source": "Synthetic opening statement",
  "balances": [
    {"accountId": "cash", "commodityCode": "CNY", "amount": "100", "note": "Observed before operations."}
  ]
}
```

Amounts remain finite Decimal strings. Classification uses reserved date, equity
and correction tags on the existing immutable Journal. Generic Journal validation
enforces the same stock/lot rules and cannot silently remove declared opening
classification during edits. CSV/JSON exports and Vault backup preserve it.
Restore checks classification, chronology, correction lineage, balanced exact
valuations and linked reversals, even when the canonical backup hash is correct.
Legal inactive historical accounts/commodities remain restorable.

Statements, T-accounts and positions include opening stock. GUI Cash flow uses an
explicit calendar month and separates opening effects. The Investment three-month
activity view excludes classified opening and inherited opening reversals. Old
`/cash-flow` and `/reports/monthly-review` default calculations remain unchanged,
including `monthly-review-v1` and its existing reader shape. Earlier ordinary
Journal history is never automatically reclassified. Invalid posted dates still
block reports; reports use a consistent read snapshot and never claim external
completeness.

## Optional Note

Account registration, actual-date balances, monthly observations/valuations and
monthly plans retain optional narrative context. Journal posting UI calls its
existing `memo` **Note**; wire/storage names are not renamed. The duplicate Tags
control was removed. Source, reference, confirmation and correction reasons are
different provenance fields and are not substituted by Note.

New account/observation Notes default to an empty string and are bounded to 4,000
characters. Existing JSON payloads/Note columns are reused without DDL migration.
Notes are inert text, not financial rules, agent instructions, permissions or
automatically authorized AI evidence. History folds them into details; segment
JSON, Living CSV (additional `note` column) and full Vault backup retain them.
The legacy monthly importer is unchanged; exported dated records are not its
import/restore format. No provider/model call or direct external DB access is added.

The official reader 1.5.0 / protocol 2 pins API 3.5.0, with the same GET-only
Workspace/record whitelist and unchanged Monthly Review v1 reading. Reader 1.4.0
and earlier archives remain historical artifacts. FRAG code and installed pins
are not updated or installed by this task.

## Verification and evidence limits

Workspace API regressions cover stock versus activity, cost lots, duplicate and
backdated openings, correction chronology, stale confirmation, owner/token and
Workspace isolation, exact restore validation, Note retention and old report
semantics. `tools/browser_opening_notes.mjs` requires an owned synthetic fixture
and marker, then checks early sign-in, deferred feature loading, optional Notes,
complete focus outlines, opening save/validate/confirm and desktop layouts.

Run backend tests with a fresh, non-existing repository-local pytest base temp
directory. Run UI tests, build, version/release checks and plugin archive checks.
All verification uses synthetic records. Browser/API/package verification is not
real-data migration, measured startup latency on the user's machine, or human
financial-semantic acceptance. No new dependency is introduced. Cleanup removes
no user records, source files or historical release artifacts.
