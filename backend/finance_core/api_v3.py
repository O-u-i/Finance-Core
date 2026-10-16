from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Literal
from uuid import uuid4

from fastapi import APIRouter, Body, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from finance_core import __version__
from finance_core.api_v2 import create_v2_router
from finance_core.contracts_v3 import (
    BEARER_OR_SESSION_SECURITY,
    HealthResponse,
    LedgerResponse,
    MeResponse,
    SESSION_SECURITY,
    STANDARD_ERROR_RESPONSES,
    WorkspaceListResponse,
    WorkspaceMutationResponse,
)
from finance_core.registry import Actor, OWNER_USER_ID, REGISTRY_SCHEMA_VERSION, Registry


SESSION_COOKIE = "fc_session"


class V3Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SessionRequest(V3Model):
    admin_token: str = Field(alias="adminToken", min_length=1)


class WorkspaceCreate(V3Model):
    display_name: str = Field(alias="displayName", min_length=1, max_length=120)
    kind: Literal["personal", "sandbox"] = "personal"


class WorkspaceUpdate(V3Model):
    display_name: str | None = Field(default=None, alias="displayName", min_length=1, max_length=120)
    status: Literal["active", "archived"] | None = None


class AccessTokenCreate(V3Model):
    name: str = Field(min_length=1, max_length=120)
    workspace_ids: list[str] = Field(alias="workspaceIds", min_length=1)
    scopes: list[Literal["ledger:read", "ledger:write"]] = Field(min_length=1)
    expires_at: datetime | None = Field(default=None, alias="expiresAt")


class V3UndoRequest(V3Model):
    undo_token: str = Field(alias="undoToken", min_length=1)
    workspace_id: str | None = Field(default=None, alias="workspaceId")


def registry(request: Request) -> Registry:
    return request.app.state.registry


def bearer_secret(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, secret = authorization.partition(" ")
    return secret if scheme.lower() == "bearer" and secret else None


def require_local_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in {"http://127.0.0.1:5174", "http://localhost:5174", "http://127.0.0.1:8788", "http://localhost:8788"}:
        raise HTTPException(403, detail={"code": "ORIGIN_DENIED", "message": "Session operations require a trusted local origin."})


def authenticate(
    request: Request,
    authorization: str | None = Header(default=None),
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Actor:
    store = registry(request)
    explicit_bearer = bearer_secret(authorization)
    actor = store.authenticate_token(explicit_bearer) if explicit_bearer else store.authenticate_session(session)
    if actor is None:
        raise HTTPException(401, detail={"code": "AUTH_REQUIRED", "message": "Authentication is required."})
    if actor.is_admin and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        require_local_origin(request)
    request.state.actor = actor
    return actor


def require_admin(actor: Actor = Depends(authenticate)) -> Actor:
    if not actor.is_admin:
        raise HTTPException(403, detail={"code": "TOKEN_SCOPE_DENIED", "message": "An admin session is required."})
    return actor


def authorize_workspace(store: Registry, workspace_id: str, actor: Actor, *, write: bool) -> dict[str, Any]:
    workspace = store.get_workspace(workspace_id)
    if workspace is None or (not actor.is_admin and workspace_id not in actor.workspace_ids) or workspace['status'] == 'quarantined':
        raise HTTPException(404, detail={'code': 'WORKSPACE_NOT_FOUND', 'message': 'Workspace was not found.'})
    scope = 'ledger:write' if write else 'ledger:read'
    if not actor.is_admin and scope not in actor.scopes:
        raise HTTPException(403, detail={'code': 'TOKEN_SCOPE_DENIED', 'message': f'{scope} scope is required.'})
    if write and workspace['status'] == 'archived':
        raise HTTPException(409, detail={'code': 'WORKSPACE_ARCHIVED', 'message': 'Archived workspaces are read-only.'})
    return workspace


@asynccontextmanager
async def ledger_context(store: Registry, workspace_id: str, actor: Actor, *, write: bool):
    authorize_workspace(store, workspace_id, actor, write=write)
    async with store.vaults.lock_for(workspace_id):
        workspace = authorize_workspace(store, workspace_id, actor, write=write)
        if not store.vaults.path_for(workspace_id).is_file():
            raise HTTPException(409, detail={
                'code': 'WORKSPACE_FILES_UNAVAILABLE',
                'message': 'Workspace files require review before this ledger can be opened.',
            })
        handle = store.vaults.get(workspace_id)
        yield workspace, handle


async def workspace_context(
    workspace_id: str, request: Request, actor: Actor = Depends(authenticate),
) -> AsyncIterator[None]:
    write = request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and not request.url.path.endswith('/validate')
    async with ledger_context(registry(request), workspace_id, actor, write=write) as (workspace, handle):
        request.state.database = handle.connection
        request.state.ledger_repository = handle.repository
        request.state.workspace = workspace
        request.state.workspace_id = workspace_id
        yield
        # Capture before releasing the lifecycle lock; middleware must not query later.
        request.state.operation_undo = handle.repository.latest_undo() if write else None


def create_v3_routers(admin_token: str) -> tuple[APIRouter, APIRouter]:
    router = APIRouter(prefix="/api/v3")

    @router.get("/health", response_model=HealthResponse)
    def health(request: Request) -> dict[str, Any]:
        store = registry(request)
        store.connection.execute("SELECT 1").fetchone()
        return {
            "status": "ok",
            "service": "finance-core",
            "serviceVersion": __version__,
            "apiVersion": "3.7.0",
            "ledgerSchemaVersion": 3,
            "registrySchemaVersion": REGISTRY_SCHEMA_VERSION,
            "supportedApiVersions": ["3.0.0", "3.1.0", "3.1.1", "3.2.0", "3.3.0", "3.4.0", "3.5.0", "3.6.0", "3.7.0"],
            "buildCommit": request.app.state.build_commit,
            "releaseCommit": request.app.state.release_commit,
            "capabilities": [
                "workspace-vaults", "workspace-scoped-api", "scoped-access-tokens",
                "reversible-business-cud", "reversible-workspace-quarantine",
                "decimal-strings", "aggregate-ledger", "linked-reversal",
            ],
        }

    @router.post(
        "/session", response_model=LedgerResponse, response_model_exclude_unset=True,
        responses=STANDARD_ERROR_RESPONSES,
    )
    def create_session(payload: SessionRequest, response: Response, request: Request) -> dict[str, Any]:
        require_local_origin(request)
        try:
            secret, metadata = registry(request).create_session(payload.admin_token, admin_token)
        except PermissionError as error:
            raise HTTPException(401, detail={"code": "AUTH_REQUIRED", "message": str(error)}) from error
        response.set_cookie(
            SESSION_COOKIE, secret, httponly=True, samesite="strict", secure=False,
            max_age=12 * 60 * 60, path="/api/v3",
        )
        return {"data": metadata}

    @router.delete(
        "/session", response_model=LedgerResponse, response_model_exclude_unset=True,
        responses=STANDARD_ERROR_RESPONSES,
        openapi_extra={"security": SESSION_SECURITY},
    )
    def delete_session(
        request: Request, response: Response,
        session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        require_local_origin(request)
        registry(request).revoke_session(session)
        response.delete_cookie(SESSION_COOKIE, path="/api/v3")
        return {"signedOut": True}

    @router.get(
        "/me", response_model=MeResponse, responses=STANDARD_ERROR_RESPONSES,
        openapi_extra={"security": BEARER_OR_SESSION_SECURITY},
    )
    def me(actor: Actor = Depends(authenticate)) -> dict[str, Any]:
        return {
            "data": {
                "id": actor.user_id,
                "displayName": "Local owner",
                "status": "active",
                "actorKind": actor.kind,
            }
        }

    @router.get(
        "/workspaces", response_model=WorkspaceListResponse, responses=STANDARD_ERROR_RESPONSES,
        openapi_extra={"security": BEARER_OR_SESSION_SECURITY},
    )
    def list_workspaces(request: Request, actor: Actor = Depends(authenticate)) -> dict[str, Any]:
        return {"data": registry(request).list_workspaces(actor)}

    @router.post(
        "/workspaces", status_code=201, response_model=WorkspaceMutationResponse,
        responses=STANDARD_ERROR_RESPONSES, openapi_extra={"security": SESSION_SECURITY},
    )
    def create_workspace(
        payload: WorkspaceCreate, request: Request, actor: Actor = Depends(require_admin),
    ) -> dict[str, Any]:
        try:
            workspace, undo = registry(request).create_workspace(payload.display_name, payload.kind)
        except ValueError as error:
            raise HTTPException(422, detail={"code": "INVALID_REQUEST", "message": str(error)}) from error
        registry(request).audit(str(uuid4()), actor, workspace["id"], "workspace.create", "success")
        return {"data": workspace, "undo": undo}

    @router.patch(
        "/workspaces/{workspace_id}", response_model=WorkspaceMutationResponse,
        responses=STANDARD_ERROR_RESPONSES, openapi_extra={"security": SESSION_SECURITY},
    )
    async def update_workspace(
        workspace_id: str, payload: WorkspaceUpdate, request: Request,
        actor: Actor = Depends(require_admin),
    ) -> dict[str, Any]:
        try:
            store = registry(request)
            async with store.vaults.lock_for(workspace_id):
                workspace, undo = await run_in_threadpool(
                    store.update_workspace, workspace_id, display_name=payload.display_name, status=payload.status
                )
        except LookupError as error:
            raise HTTPException(404, detail={"code": "WORKSPACE_NOT_FOUND", "message": str(error)}) from error
        except ValueError as error:
            raise HTTPException(422, detail={"code": "INVALID_REQUEST", "message": str(error)}) from error
        registry(request).audit(str(uuid4()), actor, workspace_id, "workspace.update", "success")
        return {"data": workspace, "undo": undo}

    @router.delete(
        "/workspaces/{workspace_id}", response_model=WorkspaceMutationResponse,
        responses=STANDARD_ERROR_RESPONSES, openapi_extra={"security": SESSION_SECURITY},
    )
    async def delete_workspace(
        workspace_id: str, request: Request, actor: Actor = Depends(require_admin),
    ) -> dict[str, Any]:
        try:
            store = registry(request)
            async with store.vaults.lock_for(workspace_id):
                workspace, undo = await run_in_threadpool(store.quarantine_workspace, workspace_id)
        except LookupError as error:
            raise HTTPException(404, detail={"code": "WORKSPACE_NOT_FOUND", "message": str(error)}) from error
        except ValueError as error:
            raise HTTPException(409, detail={"code": "QUARANTINE_FAILED", "message": str(error)}) from error
        registry(request).audit(str(uuid4()), actor, workspace_id, "workspace.quarantine", "success")
        return {"data": workspace, "undo": undo}

    @router.get(
        "/access-tokens", response_model=LedgerResponse, response_model_exclude_unset=True,
        responses=STANDARD_ERROR_RESPONSES,
        openapi_extra={"security": SESSION_SECURITY},
    )
    def list_tokens(request: Request, _actor: Actor = Depends(require_admin)) -> dict[str, Any]:
        return {"data": registry(request).list_access_tokens()}

    @router.post(
        "/access-tokens", status_code=201, response_model=LedgerResponse, response_model_exclude_unset=True,
        responses=STANDARD_ERROR_RESPONSES, openapi_extra={"security": SESSION_SECURITY},
    )
    def create_token(
        payload: AccessTokenCreate, request: Request, actor: Actor = Depends(require_admin),
    ) -> dict[str, Any]:
        try:
            if payload.expires_at is not None and payload.expires_at.tzinfo is None:
                raise ValueError("expiresAt must include a timezone offset.")
            metadata, secret = registry(request).create_access_token(
                payload.name, payload.workspace_ids, list(payload.scopes),
                payload.expires_at.isoformat() if payload.expires_at else None,
            )
        except LookupError as error:
            raise HTTPException(404, detail={"code": "WORKSPACE_NOT_FOUND", "message": str(error)}) from error
        except ValueError as error:
            raise HTTPException(422, detail={"code": "INVALID_REQUEST", "message": str(error)}) from error
        registry(request).audit(str(uuid4()), actor, None, "access-token.create", "success")
        return {"data": metadata, "token": secret, "displayOnce": True}

    @router.post(
        "/access-tokens/{token_id}/revoke", response_model=LedgerResponse, response_model_exclude_unset=True,
        responses=STANDARD_ERROR_RESPONSES, openapi_extra={"security": SESSION_SECURITY},
    )
    def revoke_token(
        token_id: str, request: Request, actor: Actor = Depends(require_admin),
    ) -> dict[str, Any]:
        try:
            item = registry(request).revoke_access_token(token_id)
        except LookupError as error:
            raise HTTPException(404, detail={"code": "TOKEN_NOT_FOUND", "message": str(error)}) from error
        registry(request).audit(str(uuid4()), actor, None, "access-token.revoke", "success")
        return {"data": item}

    @router.get(
        "/undo/latest", response_model=LedgerResponse, response_model_exclude_unset=True,
        responses=STANDARD_ERROR_RESPONSES,
        openapi_extra={"security": BEARER_OR_SESSION_SECURITY, "x-fc-required-scope": "ledger:read"},
    )
    async def latest_undo(
        workspace_id: str, request: Request, actor: Actor = Depends(authenticate),
    ) -> dict[str, Any]:
        async with ledger_context(registry(request), workspace_id, actor, write=False) as (_, handle):
            item = await run_in_threadpool(handle.repository.latest_undo)
        return {"data": ({**item, "workspaceId": workspace_id, "operationId": item["undoToken"]} if item else None)}

    @router.post(
        "/undo", response_model=LedgerResponse, response_model_exclude_unset=True,
        responses=STANDARD_ERROR_RESPONSES,
        openapi_extra={"security": BEARER_OR_SESSION_SECURITY, "x-fc-required-scope": "ledger:write"},
    )
    async def undo(
        payload: V3UndoRequest, request: Request, actor: Actor = Depends(authenticate),
    ) -> dict[str, Any]:
        if actor.is_admin:
            try:
                store = registry(request)
                control_id = store.control_workspace_id(payload.undo_token)
                if control_id is not None:
                    async with store.vaults.lock_for(control_id):
                        control = await run_in_threadpool(store.undo_control, payload.undo_token)
                else:
                    control = await run_in_threadpool(store.undo_control, payload.undo_token)
            except ValueError as error:
                raise HTTPException(409, detail={"code": "UNDO_CONFLICT", "message": str(error)}) from error
            if control is not None:
                return control
        if payload.workspace_id is None:
            raise HTTPException(422, detail={"code": "INVALID_REQUEST", "message": "workspaceId is required for ledger undo."})
        if not actor.is_admin and (payload.workspace_id not in actor.workspace_ids or "ledger:write" not in actor.scopes):
            raise HTTPException(403, detail={"code": "TOKEN_SCOPE_DENIED", "message": "ledger:write scope is required."})
        try:
            async with ledger_context(registry(request), payload.workspace_id, actor, write=True) as (_, handle):
                result = await run_in_threadpool(handle.repository.undo, payload.undo_token)
        except ValueError as error:
            raise HTTPException(409, detail={"code": "UNDO_CONFLICT", "message": str(error)}) from error
        if result is None:
            raise HTTPException(410, detail={"code": "UNDO_EXPIRED", "message": "Undo token is invalid, expired, consumed, or superseded."})
        return {**result, "workspaceId": payload.workspace_id, "operationId": payload.undo_token}

    scoped = create_v2_router(
        prefix="/api/v3/workspaces/{workspace_id}",
        dependencies=[Depends(workspace_context, scope="function")],
        service_version=__version__,
        api_version="3.7.0",
    )
    return router, scoped
