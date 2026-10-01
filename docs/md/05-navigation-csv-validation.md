# Navigation, identity and CSV verification

Product 3.2.0 retains API 3.1.1, ledger schema 2, registry schema 1 and the protocol-1 plugin. This refinement changes the standalone UI and rejects malformed CSV input; no dependency, public response shape or financial calculation policy changes are included.

## User-visible behavior

- Navigation uses a rectangular rail and one teal selected surface. Hover changes the label only, so clicking during hover cannot combine two fill animations. The rail, buttons and panels share modest corner radii and the established paper/ink/teal palette.
- Pages, contextual tabs and workflow steps use the same 220ms slight upward transition and measured-height container. Nested workflows skip initial animation while their parent page enters. Tabs and Journal progress reserve 104px, aligning panel origins across sections; short pages retain a common minimum content area. Reduced motion removes transitions.
- Typography stays on the existing system font stack. The approved system font stack is retained; registry context does not grant new font or licensing approval.
- The replacement `logo.png` letterforms are redrawn with straight edges and smooth cubic curves as black filled SVG paths without strokes, fonts or embedded PNG data. Assets live in `public/branding/`: `/branding/logo.svg` supplies the header wordmark and `/branding/favicon-fincr.svg` uses the complete FINCR wordmark. Transparent source padding is removed from the wordmark; the favicon centers the complete wordmark in a square canvas. The original PNG remains ignored.
- Standard CSV parsing handles UTF-8 BOM, quoted commas/newlines and escaped quotes. Duplicate/empty headers, malformed quotes and inconsistent widths are rejected. Files are decoded as strict UTF-8. Late file reads are discarded after an input/format change or unmount.
- The supported accounting template requires explicit grouping by parentless row followed by its child rows, and explicit account mapping. Matching account codes prefill the selector for review; they do not classify or create accounts. Original parent/center context stays in posting memos. Missing accounts/currencies block conversion. Mixed-currency groups require explicit rates in the standard FC format; no rates are inferred.
- A preview shows mapped drafts before the final import confirmation. Only existing backend validation may create unposted drafts. CSV checking does not post transactions or certify all financial rules.
- Backend CSV validation now catches duplicate headers before they can overwrite account IDs and handles invalid UTF-8/quoting as a structured 422. The invalid-input regressions were reproduced before their fixes. Failure leaves the ledger unchanged.

## Evidence

The provided source was read only. Its 48 data rows can form 24 two-row groups under the explicitly selected grouping rule; the source pairs balance separately by currency. The current supplied project-local file also passed the actual client mapper in memory: 24 drafts, 48 postings, all amounts retained as strings. Original data was not written into a database or copied into tests, screenshots, public documentation or production output.

The browser used a synthetic derivative preserving only headers, row structure, debit/credit placement and currencies. Dates, accounts, references, descriptions, context and amounts were replaced. A newly created empty sandbox received synthetic accounts/currencies and 24 backend-validated unposted drafts. This verifies the import workflow with synthetic content; it does not establish the real source's account classification or user-approved grouping semantics.

- Backend: 69 tests passed, including architecture, contract and CSV rejection/atomicity regressions. The existing Starlette/httpx deprecation warning remains.
- Frontend: 11 deterministic tests passed, including CSV quotes/BOM/width, explicit mapping, Decimal string preservation, orphan children, calendar validation and missing currency/rate checks.
- Browser: 27 check groups passed, including hover-click, aligned section origins, full mapping/preview/import, normal/reduced motion, delayed/failed/rapid navigation, history, posting/reversal, backup and Workspace lifecycle. All seven pages were checked at 320, 375, 768, 1024 and 1440px.
- Representative navigation, wordmark, confirmation and synthetic CSV preview screenshots were visually inspected. Browser viewport emulation is not physical-device or exhaustive screen-reader testing.
- Replacement branding was separately verified in the browser at 375px and 1440px: logo and favicon paths resolve, images render without horizontal overflow, and production SVG copies match their sources byte for byte. Obsolete root-level generated SVGs were individually moved into ignored local backup storage.
- Production build, version synchronization, release/OpenAPI and strict plugin archive checks passed. Distributed notices remain present. Public SVGs contain only vector paths and no private content.
- Horizon 3.0.0 remains unchanged; its four rendered pages and extracted text were verified. No new major-version Horizon is introduced.
- Git ignored, tracked and staged states were audited separately. Source CSV, source PNG, screenshots, local rules and synthetic fixtures remain ignored. No private/rule files are tracked and nothing is staged, committed, pushed or deployed.

## Review and run

Primary changes are `demo/src/App.jsx`, `components.jsx`, `style.css`, `state.jsx`, `csv.js`, `pages/Data.jsx`, the two SVG assets under `public/branding/`, `index.html` (favicon cache identity), `backend/finance_core/api_v2.py`, CSV regression tests and the browser smoke tool. Earlier Journal/navigation fixes in the same uncommitted working tree remain intact.

Run `npm.cmd run dev` and open the printed Vite URL. For accounting CSV, choose CSV, load a UTF-8 file, check structure, confirm the grouping rule, review each account selector, check again, review the draft preview and explicitly confirm import. Create the needed currency/accounts in Master data first. Drafts still require Journal validation and posting.

Browser testing requires a separate synthetic backend and ignored data root. `FC_UI_API_TARGET` selects that backend; `FC_UI_TEST_URL` selects the UI. Optional `FC_TEST_ACCOUNTING_CSV` must point only at a sanitized synthetic derivative. Never point tests at a personal Vault or an unredacted source CSV. Test services are stopped at handoff; the user's pre-existing service is retained.

Proposed commit message:

```text
Unify Finance Core navigation motion and support explicit accounting CSV mapping
```

```text
Cross-repo impact: NONE
Contract change: NONE
Other repo status: NOT_TOUCHED
Required compatible version: FC service 3.2.0; API 3.1.1; FRAG plugin 1.0.0; protocol 1; host >=1.0.0
Reason: FC standalone UI refinement and compatible CSV validation fixes; public finance contract retained.
Prompt for the other repo: No implementation required.
```

The later configuration navigation, session exit handling and CSV round-trip changes supersede the original page grouping above. See [the updated verification](06-configuration-csv-roundtrip.md).
