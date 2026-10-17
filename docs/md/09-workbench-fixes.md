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
  for the document. Different content lengths still scroll naturally. Global notifications are fixed-position feedback, and loading status sits outside document flow; neither inserts a temporary row that shifts the workspace or page content. Geometry regressions confirmed these existing feedback rules; no duplicate override was needed.
- **BranchedMenu owns both navigation levels. LineSidebar is retired.** The outer trunk, inset curved branches, gliding active marker and selected path follow the approved component. Hover changes color only; it does not add a background box or translate labels. CSS grid folds use the supplied eased transition. Closed branches are inert and absent from the accessibility tree.
- Feature-owned definitions in `navigation.js` drive both rail destinations and internal tabs. The shell keeps tab controls mounted while replacing their content, preserving keyboard focus. DOM changes are used only to wait for a lazy scroll target, never to infer menu structure. Single-section pages do not repeat their only heading as a child.
- Branch selection first commits the correct page/tab, then uses interruptible native smooth scrolling near 25% of the viewport, below the sticky navigation. Document bounds can clamp the target. No heading focus or scroll-spy can select another branch. Reduced-motion uses immediate positioning and no fold/highlight transition.
- Failed navigation clears its pending destination. A later ordinary visit cannot replay the failed branch scroll. Master data and Settings use one-level entries from the same component.
- Primary page navigation uses a stable Workspace-scoped Suspense boundary and React's existing transition support. The previous page remains visible until both the scoped read and destination module are ready; changing Workspace never retains another Workspace's page. Page switches no longer replay the form-step fade, disable/dim the whole rail during reads, or scroll a visible heading back to the document header. Longer reads show feedback after 180 ms and keep stale page controls inert; write and invalid-configuration restrictions remain. Newer read destinations still cancel older requests. No hidden page cache or browser-storage persistence is introduced.
- Workspace and Sign out use a compact real-control gap instead of a fixed empty wrapper. Master data and Settings have text-labeled green Ready / red Needs attention states. Unknown initial checks are not shown as verified green. Failed configuration reads invalidate readiness and disable financial navigation while repair controls remain available.

## Compatibility and editor lifecycle

The reported Living menu collapse was a schema-2 compatibility branch, not random tab state. Legacy Vaults now retain Accounts & balances, Assets & liabilities, Cash-flow plans, Monthly review and Import & export. Original accounts/snapshots, plans, balance summaries and legacy exports remain available. Unsupported asset ownership and dated/month-close functions explain the required reviewed migration without creating one. Historical record dates and values are not inferred or silently converted.

The Journal editor previously reinitialized on every New draft click and unmounted on navigation. Close now retains its input in Workspace-scoped session memory; Resume draft restores it after page changes. Discard draft explicitly clears unfinished input. Discard changes on a saved draft retains the backend record; deletion remains a separate confirmed action in Unposted drafts. Reload, Workspace changes, session expiry and sign-out clear transient input. Reload and deliberate Workspace/sign-out actions warn about unsaved input; authentication expiry clears it fail-closed. Deleting a saved draft also clears its matching retained editor. Save draft remains the durable persistence action. No browser-storage autosave is introduced.

Closing/resuming clears validation previews and posting confirmation. Every edit still invalidates validation. Posting requires fresh backend validation, current exact editor matching and explicit human confirmation; no close, resume or discard implicitly posts or saves an unchecked draft.

## Readouts and English controls

Legacy activity reviews use a compact month toolbar, visible completeness boundary, three metrics and comparison table; calculation details and correction counts are progressive disclosure. Empty reviews retain the same useful destinations. Formal reviews separate currency readouts, data checks and immutable-close actions. Monthly reviews and financial readouts use the same account/currency card
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
English application labels and the selected filename. Hidden native file controls do not create a duplicate localized accessible button; the custom English chooser remains labelable. The external operating
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
keyboard buttons and reduced-motion behavior without an animation dependency or custom per-frame scrolling loop.

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
column widths, plan persistence and English application controls. `tools/browser_navigation_followup.mjs` additionally verifies actual fold/scroll samples, interrupted motion, sidebar/tab agreement, transient editor lifecycle, fail-closed status indicators and schema-2 browsing. Its fixture must explicitly contain an isolated legacy Workspace. Run the production preview on `::1:5174` with the synthetic API target; launch the owned browser with `AGENT_BROWSER_ARGS="--host-resolver-rules=MAP localhost [::1]"`. Both browser scripts require this pin so a concurrently running IPv4 development server cannot receive test requests. Prelaunch the named browser session directly with the CLI and the same profile/namespace/arguments before the Node runners; this avoids the observed Windows 0.39.0 first-daemon startup timeout.

Screenshots and data stay ignored and synthetic. Automated checks, image-based
visual review, human acceptance and production behavior are distinct. No real
Vault, original CSV, credential or user's browser session is used.

`tools/browser_page_transitions.mjs` samples painted frames during a cold module load, rather than testing only settled pages. Its owned synthetic preview must provide one-shot `POST /__test/delay` controls accepting `{path, ms}` for its own asset or Workspace API paths. It checks content/shell continuity, rail brightness, absence of whole-pane step animations, workbench scroll position, rapid read/module cancellation, Workspace clearing and reduced motion. Delay controls belong only to the isolated test preview, never the product server. The retained local run includes the standard-library preview helper and red/green evidence. React's [transition documentation](https://react.dev/reference/react/useTransition) describes the native mechanism; no animation or router dependency was added.

Rollback reverts this fix while preserving Vaults and backups; there is no DDL
migration to reverse. If extended schedules exist, do not run an older writer:
it cannot interpret their metadata. Preserve a format-3 backup and explicitly
review/convert or remove those forecasts using the current UI before downgrade.

```text
Cross-repo impact: NONE
Contract change: NONE (this interaction follow-up)
Other repo status: NOT_TOUCHED
Required compatible version: FC product 3.7.1 / API 3.7.0 / reader 1.7.0 / protocol 2
Reason: This follow-up changes standalone UI behavior only; the existing optional plan field, reader endpoints and exact API pin remain unchanged.
```
