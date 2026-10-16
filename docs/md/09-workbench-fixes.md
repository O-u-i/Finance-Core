# Workbench fixes — product 3.7.1

Requirement ownership: **FC_ONLY**. The user selected a fix release, **3.7.1**.
API **3.7.0**, ledger schema **3**, registry schema **1**, and official reader
**1.7.0 / protocol 2** remain compatible and unchanged in version. No dependency,
production installation, migration, connector, commit or public release is added.
These presentation notes supersede the compact geometry in the 3.7.0 workbench
guide, not its financial rules or read-only posting detail contract.

## Geometry and navigation

- Desktop width is fluid with 32px outer margins, rather than capped at 1480px.
  A 264px rail and a shared main column preserve alignment across sibling pages.
  Existing narrow-screen containment remains; mobile acceptance is not claimed.
- Labels and navigation use a readable 14–16px minimum scale; panel headings are
  20px. Account and currency amounts remain exact server strings.
- Stable scrollbar gutters, natural page height and opacity-only page changes
  replace the measured-height transition. Browser scroll anchoring is disabled
  for the document. Different content lengths still scroll naturally.
- **BranchedMenu owns both navigation levels. LineSidebar is retired.** The
  outer vertical trunk, parent headings, inset curved branches, vertical active
  marker and selected path follow the supplied component. Groups retain their
  independent open state. Visiting a page discovers its actual top-level Panel
  titles; previously visited groups remain available without speculative labels.
- Selecting a retained branch first loads its page when necessary, then locates
  the exact heading. The target is positioned near 25% of the viewport, below the
  sticky navigation. Document bounds may clamp the final position. No smooth
  animation or scroll-spy can select the next branch because of inertia.
- Page-bound observers cannot attach new-page headings to an old-page group.
  Failed navigation discards its pending scroll target; a later ordinary visit
  cannot replay the failed branch selection.
  Master data uses one-level page entries; Settings uses one-level section entries.
  Neither keeps the old configuration subnavigation as a duplicate primary menu.

## Readouts and English controls

Monthly reviews and financial readouts use the same account/currency card
language as T-accounts. Filters, exact values, unknown states, dates, currency
separation and read-only detail dialogs remain available. White rows, cool
slate table headers, alternating neutral rows and explicit borders separate
Living tables from their muted green page surface. Green no longer fills every
data layer or replaces semantic status colors.

Overview has an accessible SVG donut and horizontal bars describing displayed
record items and states. Unknown readouts remain explicit. These are UI counts,
not a combined balance, source-completeness metric or financial calculation.
Empty views do not invent sample money.

Shared date/month controls expose ISO text entry and English calendar navigation;
datetime inputs retain explicit ISO local datetime strings. Invalid dates and
min/max limits fail validation with English inline feedback. File inputs expose
English application labels and the selected filename. The external operating
system file dialog retains the user's system language; the application does
not change OS or browser language settings.

## Cash-flow plans

The Living page is named **Cash-flow plans**, not Monthly plans. The existing
Workspace-scoped `/monthly-plans` routes and monthly forecast report are retained.

The optional `repeatEveryMonths` field accepts **1, 3, 6, 12**, default **1**.
Existing `recurringMonthly: true` requests without the new field retain monthly
behavior; `false` retains one occurrence on `startDate`. The UI calls this
**Repeat interval**: Monthly, Quarterly, Semi-annual, Annual, One time. A one-time
plan cannot also specify a non-default repeating interval.

The start **month** anchors repeating cycles; **Due day (1–31)** selects the
calendar day, not an occurrence count. Each due date must be on or after the
start date. A missing day uses that month's last valid day without shifting the
next cycle: a quarterly plan anchored to February with day 31 is due February
28/29, May 31, August 31 and November 30. Help is available by hover or keyboard
focus. One-time plans hide the unused Due day field.

Schedule metadata uses `app_metadata` keys `plan-repeat-months:<planId>` in the
same Vault and writer transaction as its plan. No note text, existing monthly
row, schema, posted entry, observation or close is repurposed. Create/edit/delete
and undo include schedule metadata; full format-3 Vault backups retain it.
Legacy format-2 backup refuses a Vault with extended schedules rather than
silently dropping them. Old unconsumed undo snapshots retain their prior
metadata behavior. Restore validates schedules inside its transaction.

All forecasts and per-currency/category totals remain exact backend Decimal
calculations. UI filters do not recalculate the report. Plans do not generate
payments, actual cash flows or posted Journal entries, and are not prorated or
divided into monthly spending.

## Approved component and documentation

React Bits **BranchedMenu**, revision
`d9085a5d6cb62a1c7512d8fa05a4f966736b575c`, was explicitly approved for this
application and notice handling on 2026-10-16. Its
[official MIT + Commons Clause license](https://github.com/DavidHDev/react-bits/blob/d9085a5d6cb62a1c7512d8fa05a4f966736b575c/LICENSE.md)
requires copyright/permission retention and restricts sale, sublicensing or
redistribution of the components themselves. It does not require publication
of FC source. This is not blanket approval for future items or uses.

The existing footer notice entry and distributed license are retained; the build
notice now identifies BranchedMenu instead of retired LineSidebar. The adaptation
uses no Hugeicons package, icon assets or other new dependency. It preserves
keyboard buttons and reduced-motion behavior without a per-frame layout loop.

README has one **Light / 2048px** architecture preview, generated through the
approved Archify workflow. Editable JSON and the exact checked HTML remain linked;
other render sizes/themes are local verification evidence, not README variants.
The existing Archify/OFL notices remain with their approved documentation assets.

## Verification and rollback

Run frontend render tests, synthetic backend/architecture/contract tests, the
production build and notice audit, version/release checks and the unchanged
reader artifact check. `tools/browser_layout_plans.mjs` requires an explicitly
owned synthetic fixture and named browser session. It verifies 1440×900,
1600×1000, 1920×1080 and 2560×1440 desktop layouts, independent menu groups,
cross-page branch selection, settled scroll positions, readable labels, shared
column widths, plan persistence and English application controls.

Screenshots and data stay ignored and synthetic. Automated checks, image-based
visual review, human acceptance and production behavior are distinct. No real
Vault, original CSV, credential or user's browser session is used.

Rollback reverts this fix while preserving Vaults and backups; there is no DDL
migration to reverse. If extended schedules exist, do not run an older writer:
it cannot interpret their metadata. Preserve a format-3 backup and explicitly
review/convert or remove those forecasts using the current UI before downgrade.

```text
Cross-repo impact: NONE
Contract change: ADDITIVE
Other repo status: NOT_TOUCHED
Required compatible version: FC product 3.7.1 / API 3.7.0 / reader 1.7.0 / protocol 2
Reason: Optional plan schedule metadata and standalone presentation fixes; existing reader endpoints and exact API pin remain unchanged.
```
