from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from finance_core.api_v3 import create_v3_routers
from finance_core.registry import Registry


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = ROOT / ".local-data" / "v3"
COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{7,64}$")


def error_payload(code: str, message: str, request_id: str, issues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, "requestId": request_id}
    if issues:
        error["issues"] = issues
    return {"error": error}


def is_reversible_ledger_mutation(request: Request) -> bool:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    path = request.url.path
    return not any((
        path.endswith("/validate"), path.endswith("/post"), path.endswith("/reverse"),
        path.endswith("/undo"),
    ))


def public_commit(value: str | None) -> str | None:
    """Expose only commit-shaped metadata, never arbitrary environment contents."""
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized if COMMIT_PATTERN.fullmatch(normalized) else None


def create_app(
    *,
    data_root: str | Path | None = None,
    admin_token: str | None = None,
    build_commit: str | None = None,
    release_commit: str | None = None,
) -> FastAPI:
    configured_data_root = data_root if data_root is not None else os.environ.get("FINANCE_CORE_DATA_ROOT", str(DEFAULT_DATA_ROOT))
    configured_admin_token = admin_token if admin_token is not None else os.environ.get("FINANCE_CORE_ADMIN_TOKEN", "")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Registry(configured_data_root)
        app.state.registry = store
        try:
            yield
        finally:
            store.close()

    app = FastAPI(
        title="Finance Core API",
        version="3.2.0",
        description="Local-first deterministic finance domain and multi-vault data service.",
        lifespan=lifespan,
    )
    app.state.build_commit = public_commit(
        build_commit if build_commit is not None else os.environ.get("FINANCE_CORE_BUILD_COMMIT")
    )
    app.state.release_commit = public_commit(
        release_commit if release_commit is not None else os.environ.get("FINANCE_CORE_RELEASE_COMMIT")
    )
    global_router, scoped_router = create_v3_routers(configured_admin_token)
    app.include_router(global_router)
    app.include_router(scoped_router)

    original_openapi = app.openapi

    def contract_openapi() -> dict[str, Any]:
        schema = original_openapi()
        schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
        schemes.update({
            "BearerAccessToken": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "FC access token",
                "description": "Workspace-limited access token. Required ledger scope is declared per operation.",
            },
            "SessionCookie": {
                "type": "apiKey",
                "in": "cookie",
                "name": "fc_session",
                "description": "HttpOnly local admin session cookie.",
            },
        })
        schema["components"].setdefault("schemas", {})["CsvDocument"] = {
            "title": "CsvDocument",
            "type": "string",
        }
        return schema

    app.openapi = contract_openapi  # type: ignore[method-assign]

    @app.middleware("http")
    async def workspace_response_contract(request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        workspace_id = getattr(request.state, "workspace_id", None)
        if workspace_id is None:
            return response
        response.headers["X-FC-Workspace-ID"] = workspace_id
        if "application/json" not in response.headers.get("content-type", ""):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return response
        if isinstance(payload, dict):
            if payload.get("workspaceId") is None:
                payload["workspaceId"] = workspace_id
            if response.status_code < 400 and is_reversible_ledger_mutation(request) and "undo" not in payload:
                item = getattr(request.state, "operation_undo", None)
                if item:
                    operation_type = f"ledger.{request.method.lower()}.{request.url.path.rsplit('/', 1)[-1]}"
                    payload["undo"] = {
                        **item, "operationId": item["undoToken"], "workspaceId": workspace_id,
                        "operationType": operation_type,
                    }
            actor = getattr(request.state, "actor", None)
            if actor is not None and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                request.app.state.registry.audit(
                    request_id, actor, workspace_id,
                    f"{request.method} {request.url.path.split(workspace_id, 1)[-1]}",
                    "success" if response.status_code < 400 else "failure",
                )
        headers = {key: value for key, value in response.headers.items() if key.lower() != "content-length"}
        return JSONResponse(payload, status_code=response.status_code, headers=headers)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        if isinstance(error.detail, dict):
            code = str(error.detail.get("code", "REQUEST_FAILED"))
            message = str(error.detail.get("message", "Finance Core could not complete the request."))
        else:
            code = "REQUEST_FAILED"
            message = str(error.detail)
        return JSONResponse(error_payload(code, message, request_id), status_code=error.status_code, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        issues = [
            {"path": ".".join(str(part) for part in item.get("loc", ())), "message": item.get("msg", "Invalid value.")}
            for item in error.errors()
        ]
        return JSONResponse(
            error_payload("INVALID_REQUEST", "Request does not match the Finance Core API contract.", request_id, issues),
            status_code=422,
        )

    return app


app = create_app(
    data_root=os.environ.get("FINANCE_CORE_DATA_ROOT", str(DEFAULT_DATA_ROOT)),
    admin_token=os.environ.get("FINANCE_CORE_ADMIN_TOKEN"),
)
