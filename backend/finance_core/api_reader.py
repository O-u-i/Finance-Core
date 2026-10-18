"""Explicit financial reader contract; owner endpoints remain owner-only."""
from fastapi import APIRouter, Depends, HTTPException, Request

from finance_core.api_v3 import workspace_context
from finance_core.contracts_v3 import ReaderCatalogResponse, ReaderItemResponse, BEARER_OR_SESSION_SECURITY, STANDARD_ERROR_RESPONSES
from finance_core.reader_reports import catalog, item_evidence


def create_reader_router():
    router = APIRouter(prefix='/api/v3/workspaces/{workspace_id}', dependencies=[Depends(workspace_context, scope='function')],
                       responses=STANDARD_ERROR_RESPONSES)
    extra = {'security': BEARER_OR_SESSION_SECURITY, 'x-fc-required-scope': 'ledger:read', 'x-fc-required-grant': 'financial-read-grant'}

    @router.get('/reader/catalog', response_model=ReaderCatalogResponse, openapi_extra=extra)
    def reader_catalog(request: Request):
        actor = request.state.actor
        if not actor.is_admin and actor.read_grant is None:
            raise HTTPException(403, detail={'code': 'TOKEN_SCOPE_DENIED', 'message': 'Create an explicit financial read grant in Settings.'})
        try:
            value = catalog(request.state.database, actor.read_grant or {'mode': 'all', 'itemIds': []})
        except ValueError as error:
            raise HTTPException(409, detail={'code': 'READER_SETUP_REQUIRED', 'message': 'Financial reader setup or display capacity requires review.'}) from error
        return {'workspaceId': request.state.workspace_id, 'data': value, 'readOnly': True}

    @router.get('/reader/items/{item_id}', response_model=ReaderItemResponse, openapi_extra=extra)
    def reader_item(item_id: str, request: Request):
        actor = request.state.actor
        if not actor.is_admin and actor.read_grant is None:
            raise HTTPException(403, detail={'code': 'TOKEN_SCOPE_DENIED', 'message': 'An explicit financial read grant is required.'})
        try:
            value = item_evidence(request.state.ledger_repository, actor.read_grant or {'mode': 'all', 'itemIds': []}, item_id)
        except PermissionError as error:
            raise HTTPException(403, detail={'code': 'TOKEN_SCOPE_DENIED', 'message': str(error)}) from error
        except ValueError as error:
            raise HTTPException(409, detail={'code': 'READER_SETUP_REQUIRED', 'message': 'Financial reader data requires review.'}) from error
        return {'workspaceId': request.state.workspace_id, 'data': value, 'readOnly': True}

    return router
