# Desktop financial workbench

Product/API 3.7.0. Requirement ownership: **FC_ONLY**. Contract impact:
**ADDITIVE**, no database migration, dependency installation or financial-rule
change. This supersedes the display layout in the 3.6.0 workbench notes.

## Read contract

`GET /api/v3/workspaces/{workspace_id}/t-accounts/{account_id}/postings`
requires `ledger:read` or an owner session, with existing Workspace authorization
and lifecycle locking. Archived Vaults remain readable. No unscoped endpoint or
mutation is introduced.

- `commodityCode` is required. Currencies/commodities are never combined.
- `offset` defaults to 0 and must be nonnegative. `limit` defaults to 50 and is
  bounded to 1–200. Stable ascending order is Journal entry date, entry ID,
  posting ID. `hasMore` and `count` are backend-owned pagination metadata.
- The response contains `workspaceId`, `accountId`, `commodityCode`, `readOnly:
  true`, `count`, `offset`, `limit`, `hasMore`, and `data`.
- Each row contains exactly `postingId`, `entryId`, `postingDate`, `debit`,
  `credit`. Amounts are exact decimal strings in posting units, not converted
  valuation amounts. The unused side is the string `0`.
- `postingDate` is the immutable Journal entry date. It is not `postedAt` or an
  independent posting timestamp. Drafts are excluded; linked reversals retain
  their own immutable entry dates. Description and memo are not returned.
- Unknown account/commodity returns 404; a known pair without postings returns
  an empty page. Authentication, foreign Workspace access and missing read
  scope retain existing fail-closed responses.

The existing `/t-accounts` response adds optional `firstPostingDate` and
`lastPostingDate` fields. Its required fields, decimal arithmetic, currency
grouping and normal balance are unchanged: asset/expense is debit minus credit;
liability/equity/income is credit minus debit. `Difference` is not a T-account
label; Journal validation defines it as debit total minus credit total.

## Presentation

- The shell is `min(1480px, 100% - 48px)` on desktop. Global FINCR is centered
  independently of the Workspace selector. Auth, wizard and connection Logo
  composition is retained. The global navigation is sticky at `top: 0`.
- Overview is independent of both segments and first shows cross-segment
  records for the selected month, without chart placeholders. Formal month-end
  and actual-date readouts remain separately accessible in a details layer.
- Segment sibling pages occupy a 232px line rail, becoming a menu below 850px.
  Shared base/ink are `#F7F8F5`/`#101412`; Investment surface/accent are
  `#EEF3F7`/`#3D647C`; Living uses `#F0F5EE`/`#617A58`. Semantic success,
  warning and error colors remain independent of segment colors.
- Journal, Living balances, asset valuations and Overview share `RecordRow`:
  left identity/date metadata, central value or status, fixed right actions.
  Read-only details and long histories use dialogs. Forms open only on request.
- Assets prioritize the selected month's whole-asset valuation, currency,
  valuation month and Confirmed/Pending/Disposed state. Purchase cost, ownership,
  source and separate registry/valuation Notes remain in details. Missing
  valuation is Unknown, never automatically purchase cost or zero.
- T-account summaries are four columns at 1440px and 1600px. Container queries
  reduce to three/two/one columns. Cards display backend amounts and date range;
  count is help/detail metadata. The paged detail dialog has only Posting date,
  Debit, Credit columns. Reads abort on close/unmount; results cannot repopulate
  an old Workspace after navigation.
- Ordinary panel descriptions/calculation definitions use small mouse-hover
  `?` help. No touch-specific tooltip interaction is added. Critical actions,
  errors, successful writes, unknown values, read-only and irreversible states
  remain directly visible. Escape and dialog dismissal preserve dirty-form
  confirmation and restore focus.

## Third-party component

The user supplied and approved use of React Bits LineSidebar and footer notices
for this standalone application. Source revision:
`1eeb6f105c68b964289d85dabbe84a1d551f3797`, copyright David Haz, 2026.
The [official license](https://github.com/DavidHDev/react-bits/blob/1eeb6f105c68b964289d85dabbe84a1d551f3797/LICENSE.md)
is MIT + Commons Clause: retain copyright and permission text; do not sell,
sublicense or redistribute the components themselves, including bundles/ports.
It does not require disclosure of FC source. This approval is scoped to the
supplied component/use, not future dependencies or publication.

The adaptation adds controlled route selection, native keyboard buttons,
disabled states and reduced-motion behavior; it has no additional dependency.
Build checks compare the full distributed notices and sidebar license with their
reviewed source files. The footer contains only the FC version and notice link.

## Verification and compatibility

Run `npm run build`, `npm run test:ui`, backend tests (including
`test_t_account_details.py`), version/release checks and the unchanged plugin
artifact integrity check. `tools/browser_desktop_workbench.mjs` requires an
explicitly isolated synthetic fixture, owned named browser session, and run
under ignored `.tmp`; never point it at an existing personal Vault. It checks
1440/1600 layouts, details, tooltip bounds, record overlap, segment surfaces,
Workspace changes and responsive columns. Local screenshots and measurements
are verification evidence, not human acceptance or real-data approval.

The separately authorized optional reader **1.7.0 pins API 3.7.0**. Only its
health pin, manifest, build/test expectations and local artifact change; it does
not expose the new T-account detail endpoint or expand the record whitelist.
Reader 1.6.0 remains a historical API 3.6.0 artifact. FRAG itself and its installed
pins are untouched; synchronizing that installation is separate reviewed work
before upgrading an integrated runtime. No commit, push, tag, release, production
installation or real financial data operation is included. Rollback is reverting
the workbench and additive contract changes while retaining existing Vaults;
there is no data migration to reverse.

During regression verification, a separately authorized safety fix makes draft
`updatedAt` strictly increase on update even under a repeated or backward wall
clock. This existing field is the opening workflow's reviewed-version token;
old confirmations must reject changed drafts. The writer transaction owns that
increment. It does not change posting amounts, immutable Journal entry dates,
database schemas or observation timestamp ordering. Frozen-clock tests cover
stale rejection and confirmation of the newly reviewed version. The backup
roundtrip fixture separately uses explicit receipt times rather than assuming
different Windows wall-clock ticks; its original amount assertions remain.
