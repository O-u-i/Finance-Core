from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class FlexibleContractModel(ContractModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ErrorIssue(ContractModel):
    path: str
    message: str


class ErrorDetail(ContractModel):
    code: str
    message: str
    request_id: str = Field(alias="requestId")
    issues: list[ErrorIssue] | None = None


class ErrorResponse(ContractModel):
    error: ErrorDetail


STANDARD_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    401: {
        "model": ErrorResponse,
        "description": "Authentication is required (AUTH_REQUIRED).",
    },
    403: {
        "model": ErrorResponse,
        "description": "The actor lacks the required ledger scope (TOKEN_SCOPE_DENIED).",
    },
    404: {
        "model": ErrorResponse,
        "description": "The Workspace or requested resource was not found (WORKSPACE_NOT_FOUND or RESOURCE_NOT_FOUND).",
    },
    409: {
        "model": ErrorResponse,
        "description": "The Workspace is archived, undo conflicts, or resource state conflicts (WORKSPACE_ARCHIVED, UNDO_CONFLICT, or RESOURCE_CONFLICT).",
    },
    410: {
        "model": ErrorResponse,
        "description": "The undo opportunity has expired (UNDO_EXPIRED).",
    },
    422: {
        "model": ErrorResponse,
        "description": "The request does not match the contract (INVALID_REQUEST).",
    },
}


BEARER_OR_SESSION_SECURITY = [{"BearerAccessToken": []}, {"SessionCookie": []}]
SESSION_SECURITY = [{"SessionCookie": []}]


class HealthResponse(ContractModel):
    status: Literal["ok"]
    service: Literal["finance-core"]
    service_version: str = Field(alias="serviceVersion")
    api_version: str = Field(alias="apiVersion")
    ledger_schema_version: int = Field(alias="ledgerSchemaVersion")
    registry_schema_version: int = Field(alias="registrySchemaVersion")
    supported_api_versions: list[str] = Field(alias="supportedApiVersions")
    capabilities: list[str]
    build_commit: str | None = Field(alias="buildCommit")
    release_commit: str | None = Field(alias="releaseCommit")


class Me(ContractModel):
    id: str
    display_name: str = Field(alias="displayName")
    status: Literal["active"]
    actor_kind: Literal["session", "token"] = Field(alias="actorKind")


class MeResponse(ContractModel):
    data: Me


class Workspace(ContractModel):
    id: str
    slug: str
    display_name: str = Field(alias="displayName")
    kind: Literal["personal", "sandbox"]
    status: Literal["active", "archived", "quarantined"]
    owner_user_id: str = Field(alias="ownerUserId")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class UndoOperation(ContractModel):
    operation_id: str = Field(alias="operationId")
    undo_token: str = Field(alias="undoToken")
    expires_at: str = Field(alias="expiresAt")
    workspace_id: str | None = Field(alias="workspaceId")
    operation_type: str = Field(alias="operationType")


class WorkspaceListResponse(ContractModel):
    data: list[Workspace]


class WorkspaceMutationResponse(ContractModel):
    data: Workspace
    undo: UndoOperation


class Holding(ContractModel):
    lot_id: str = Field(alias="lotId")
    account_id: str = Field(alias="accountId")
    commodity_code: str = Field(alias="commodityCode")
    acquired_date: str = Field(alias="acquiredDate")
    original_units: str = Field(alias="originalUnits")
    remaining_units: str = Field(alias="remainingUnits")
    original_cost: str = Field(alias="originalCost")
    remaining_cost: str = Field(alias="remainingCost")
    cost_commodity_code: str = Field(alias="costCommodityCode")
    latest_price: str | None = Field(alias="latestPrice")
    price_as_of: str | None = Field(alias="priceAsOf")
    market_value: str | None = Field(alias="marketValue")
    unrealized_pnl: str | None = Field(alias="unrealizedPnL")


class HoldingsResponse(ContractModel):
    data: list[Holding]
    read_only: Literal[True] = Field(alias="readOnly")
    workspace_id: str | None = Field(default=None, alias="workspaceId")


class HoldingResponse(ContractModel):
    data: Holding
    read_only: Literal[True] = Field(alias="readOnly")
    workspace_id: str | None = Field(default=None, alias="workspaceId")


class LedgerResponse(FlexibleContractModel):
    """Named response boundary for heterogeneous deterministic ledger operations."""

    data: Any | None = None
    workspace_id: str | None = Field(default=None, alias="workspaceId")


class LivingAccountDeleteResponse(FlexibleContractModel):
    data: Any
    deleted_snapshot_count: int = Field(alias="deletedSnapshotCount", ge=0)
    undo: UndoOperation
    workspace_id: str | None = Field(default=None, alias="workspaceId")
