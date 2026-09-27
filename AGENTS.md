# AGENTS.md

## Project identity

Finance Core (FC) is a reusable, local-first finance domain and data service with its own standalone UI. FRAG-harness may consume it through an optional, separately released plugin. FC must remain independently understandable and runnable.

FC owns finance entities, deterministic calculations, application operations, versioned HTTP contracts, SQLite, CSV, and operation-level undo. FC runtime modules must not import FRAG, SFOS, Context/Inference LLMs, OpenAI, Ollama, or private research files.

Explain work in beginner-friendly Chinese. English identifiers and code comments are appropriate.

## Architecture boundary

- Domain code does not import FastAPI, SQLite, React, HTTP clients, repositories, FRAG, or SFOS code.
- Application operations depend on domain models and repository ports; FastAPI, SQLite, CSV, and demo UI are adapters.
- FC 3.0.0 public APIs are rooted at `/api/v3`; every finance endpoint is explicitly scoped by `/workspaces/{workspaceId}`.
- Patch releases are compatible fixes. Minor releases may add endpoints or optional fields. Removing, renaming, changing requiredness, or changing semantics requires a new major version.
- FC is the only runtime allowed to write its finance SQLite.
- FC UI remains generic and may display the selected personal Vault. The standalone UI and FRAG plugin bundle use English only. Synthetic loading is allowed only in an empty sandbox Vault.
- A User, Workspace/Vault, and finance Account are different concepts. Each Vault owns one complete finance SQLite; never implement a process-global current database.
- Every major release must add a versioned, rendered, visually verified project Horizon PDF under `docs/pdf/`. Horizon candidates are not implemented commitments.

## Cross-repository protocol

Before and after every change, output:

```text
Cross-repo impact: NONE | FRAG_SYNC_REQUIRED | FC_SYNC_REQUIRED | BOTH_REQUIRED
Contract change: NONE | ADDITIVE | BREAKING
Other repo status: NOT_TOUCHED | UPDATED | BLOCKED_PENDING_RELEASE
Required compatible version:
Reason:
Prompt for the other repo:
```

- FRAG integration requires an exact prompt with protocol and FC API versions, routes, fields, tests, and privacy constraints.
- Do not edit FRAG unless it is explicitly writable in the current task.
- Do not add FRAG-specific behavior to FC runtime merely to satisfy one screen; keep the optional adapter in its plugin artifact.
- Release order is FC contract and synthetic tests first, then the optional plugin artifact, then FRAG installation.

### Requirement triage

- When requirement ownership is unclear, perform `READ_ONLY` triage before implementation. Do not edit either repository until the requirement is classified.
- Use a single entry point: do not ask FRAG and FC tasks to independently or concurrently design the same requirement. Host presentation starts in FRAG; reusable finance capabilities start in FC.
- Classify every requirement as exactly one of:
  - `FRAG_ONLY`: host UI, navigation, or presentation-only changes.
  - `FC_ONLY`: standalone FC UI, finance entities, deterministic calculations, persistence, CSV, undo, or generic finance APIs.
  - `BOTH`: FRAG needs a new or changed FC contract or plugin artifact.
- For `BOTH`, use **FC first**: implement and test FC, determine the compatible API and plugin protocol versions, and only then integrate in FRAG.
- Cross-repository work must produce a complete prompt that can be sent directly to the other repository. The prompt must include scope, responsibility boundaries, expected endpoints and version, required tests, privacy constraints, and `do not commit/push`.
- Do not create a local substitute implementation merely because the other repository has not implemented the required capability yet.

## Authorization and Git safety

- Review, explanation, diagnosis, and planning are `READ_ONLY`.
- Only explicit `IMPLEMENT_APPROVED` authorizes edits.
- Real data migration additionally requires `REAL_DATA_MIGRATION_APPROVED`.
- Never run `git push` automatically.
- Before every commit, show exact intended files and ask for confirmation. Never commit without it.
- Never run `git reset --hard` without explicit risk confirmation.
- Keep FC and FRAG commits, approvals, pushes, tags, and releases separate.

## File and data safety

Never delete files or directories in a batch. Do not use `del /s`, `rd /s`, `rmdir /s`, `Remove-Item -Recurse`, or `rm -rf`.

When deletion is approved, delete only one explicit file path at a time. If multiple files or a directory must be removed, stop and ask the user to do it manually.

Product-level Vault deletion is a reversible quarantine operation: checkpoint and validate first, move each explicit SQLite/WAL/SHM file separately, and never auto-purge a directory. Permanent purge remains an explicit one-file operation with no undo.

- Never commit real finance data, journals, holdings, bank/broker records, screenshots, Office/PDF/CSV exports, SQLite/WAL/SHM/backups, or personal planning files.
- Never expose keys, passwords, tokens, credentials, database paths, SQL parameters, request bodies, or private rows.
- `.env.example` is allowed; `.env` and `.env.*` remain ignored.
- Tests use synthetic fixtures and temporary/in-memory SQLite only.
- Do not edit real SQLite directly. Stop writers, back up safely, obtain approval, then run integrity and foreign-key checks.

## Development workflow

1. Run relevant architecture checks, backend tests, FC UI build, contract tests, version sync, and Horizon PDF render/text verification.
2. Verify API contract changes and SemVer classification.
3. Update README and compatibility notes.
4. Report the cross-repo impact block and exact other-repo prompt.
5. Show scoped Git status and diff. Do not commit or push without separate approval.
