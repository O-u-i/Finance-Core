# Finance Core 3.2.0 UI interaction fixes

This records the first interaction-fix pass. [Navigation, identity and CSV verification](05-navigation-csv-validation.md) describes the subsequent refinement and current acceptance results.

This follow-up fixes the standalone interface while retaining product 3.2.0, API 3.1.1, ledger schema 2, registry schema 1 and plugin protocol 1. No backend, dependency, database or plugin changes are included.

## Behavior

- Every form select uses the shared desktop dropdown: dark surface, 180ms opening, 220ms moving highlight, optional tags, viewport-aware placement and keyboard controls. A portalled menu avoids clipping in animated step containers. Native controls preserve named form values, reset behavior and delegated change tracking. At 600px and below, the native control is visible.
- The main navigation uses black pills separated by white, a teal selected pill, a moving selection indicator and a rising hover surface. Reduced motion disables animation.
- Journal advances through editing, validation, a review/confirmation page and the posted result. Editing removes prior validation and confirmation. Import advances through input, structural checks, confirmation and the result; backend validation remains authoritative.
- Page navigation retains the current scoped records while fetching the destination. Only the latest request can commit the target route and its data. The prior page is inert during loading. Failed navigation preserves its forms and dirty state. Workspace changes still clear the prior Workspace's records.
- Clicking the current route does not discard unsaved changes. Accepted tab changes remount their form; cancelled changes preserve it. Warm session/Workspace refresh does not replace the app with a connection screen. Notifications and loading indicators are fixed overlays.
- Initial Journal defaults cannot reseed an editor after editing has started.

React Bits is a visual/interaction reference only; its component source is not copied. No new third-party items or licensing obligations are introduced. The previously reviewed React distribution notices remain in the production bundle.

## Changed files

| File | Responsibility |
| --- | --- |
| `demo/src/components.jsx` | Shared select, native form bridge, step progress and animated content |
| `demo/src/App.jsx` | Navigation labels, inert loading content and per-tab form remount |
| `demo/src/state.jsx` | Atomic page/data navigation, history and dirty-state handling |
| `demo/src/pages/Journal.jsx` | Review/result stages and untouched-editor initialization |
| `demo/src/pages/Data.jsx` | Import stages and repeat-import action |
| `demo/src/style.css` | Dropdown, pill navigation, step motion and stable overlays |
| `tools/browser_smoke.mjs` | Synthetic interaction regressions and configurable test URL |
| `README.md` | Current interaction behavior |
| `docs/md/04-ui-interaction-fixes.md` | This handoff |

## Verification

- Backend: 67 tests passed, including architecture/contract tests. One existing Starlette/httpx deprecation warning remains. The initial default Windows Temp run was denied access; the successful run uses a fresh project-local synthetic `--basetemp`.
- Deterministic frontend state/client checks: 5 passed.
- Chrome synthetic browser: 25 check groups passed, including actual custom form selection, posting and reversal, failed/successful imports, backup restore, Workspace lifecycle, keyboard/Escape focus, normal and reduced motion, confirmed tab discard, failed navigation input/dirty-state retention, 250ms network latency, rapid superseded navigation and history back/forward.
- All seven pages checked at 320, 375, 768, 1024 and 1440px. Representative navigation, dropdown and confirmation screenshots inspected. These are Chrome viewport checks, not physical-device or exhaustive screen-reader acceptance.
- Production build and dependency notice verification, version synchronization, release artifact/OpenAPI check and strict plugin archive check passed. API and plugin hashes are unchanged.
- The untouched Horizon 3.0.0 PDF rendered four pages; text extraction and all-page visual inspection passed. Poppler emitted nonfatal display-font warnings.
- Git ignored/tracked/staged audits and whitespace checks passed. Screenshots, profiles and synthetic fixtures remain ignored; no rules, real financial data or credentials were added to Git. Nothing is staged, committed, pushed or deployed.

For normal use, run `npm.cmd run dev` and open the Vite address. For browser verification, first run a separately configured backend with a fresh ignored synthetic data root; route the Vite proxy with `FC_UI_API_TARGET` and optionally point the browser script with `FC_UI_TEST_URL`. Use a trusted local origin on port 5174. The test must never target a personal Vault. Test services are stopped at handoff; any pre-existing user service is left running.

Proposed commit message:

```text
Polish Finance Core UI controls and fix navigation state transitions
```

```text
Cross-repo impact: NONE
Contract change: NONE
Other repo status: NOT_TOUCHED
Required compatible version: FC service 3.2.0; API 3.1.1; FRAG plugin 1.0.0; protocol 1; host >=1.0.0
Reason: FC standalone UI interaction fixes; public finance contract retained.
Prompt for the other repo: No implementation required.
```
