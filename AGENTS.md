# AGENTS.md

## Project identity

Finance Core (FC) is a reusable, local-first finance domain and data service used by SFOS and its own generic demo UI. It must remain independently understandable and runnable.

FC owns finance entities, deterministic calculations, application operations, versioned HTTP contracts, SQLite, CSV, and operation-level undo. FC must not depend on SFOS, Context/Inference LLMs, OpenAI, Ollama, or private research files.

Explain work in beginner-friendly Chinese. English identifiers and code comments are appropriate.

## Architecture boundary

- Domain code does not import FastAPI, SQLite, React, HTTP clients, repositories, or SFOS code.
- Application operations depend on domain models and repository ports; FastAPI, SQLite, CSV, and demo UI are adapters.
- Public APIs are rooted at `/api/v1`.
- Patch releases are compatible fixes. Minor releases may add endpoints or optional fields. Removing, renaming, changing requiredness, or changing semantics requires a new major version.
- FC is the only runtime allowed to write its finance SQLite.
- Demo UI is generic and uses only synthetic data. Do not copy SFOS branding, Context, Position Review, or LLM features.

## Cross-repository protocol

Before and after every change, output:

```text
Cross-repo impact: NONE | SFOS_SYNC_REQUIRED | FC_SYNC_REQUIRED | BOTH_REQUIRED
Contract change: NONE | ADDITIVE | BREAKING
Other repo status: NOT_TOUCHED | UPDATED | BLOCKED_PENDING_RELEASE
Required compatible version:
Reason:
Prompt for the other repo:
```

- Contract changes consumed by SFOS require an exact SFOS prompt with version, endpoint, fields, tests, and privacy constraints.
- Do not edit SFOS unless it is explicitly writable in the current task.
- Do not add SFOS-only behavior to FC merely to satisfy one screen; define a generic finance capability.
- Release order is FC contract and synthetic tests first, then SFOS client/UI.

## Authorization and Git safety

- Review, explanation, diagnosis, and planning are `READ_ONLY`.
- Only explicit `IMPLEMENT_APPROVED` authorizes edits.
- Real data migration additionally requires `REAL_DATA_MIGRATION_APPROVED`.
- Never run `git push` automatically.
- Before every commit, show exact intended files and ask for confirmation. Never commit without it.
- Never run `git reset --hard` without explicit risk confirmation.
- Keep FC and SFOS commits, approvals, pushes, tags, and releases separate.

## File and data safety

禁止批量删除文件或目录。不要使用 `del /s`, `rd /s`, `rmdir /s`, `Remove-Item -Recurse`, or `rm -rf`.

When deletion is approved, delete only one explicit file path at a time. If multiple files or a directory must be removed, stop and ask the user to do it manually.

- Never commit real finance data, journals, holdings, bank/broker records, screenshots, Office/PDF/CSV exports, SQLite/WAL/SHM/backups, or personal planning files.
- Never expose keys, passwords, tokens, credentials, database paths, SQL parameters, request bodies, or private rows.
- `.env.example` is allowed; `.env` and `.env.*` remain ignored.
- Tests use synthetic fixtures and temporary/in-memory SQLite only.
- Do not edit real SQLite directly. Stop writers, back up safely, obtain approval, then run integrity and foreign-key checks.

## Development workflow

1. Run relevant architecture checks, backend tests, demo build, and contract tests.
2. Verify API contract changes and SemVer classification.
3. Update README and compatibility notes.
4. Report the cross-repo impact block and exact other-repo prompt.
5. Show scoped Git status and diff. Do not commit or push without separate approval.
