"""Owner-session-only financial foundation; existing consumer scopes do not expand."""
from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from finance_core.api_v2 import repo, translate
from finance_core.api_v3 import require_admin, workspace_context
from finance_core.contracts_v3 import SESSION_SECURITY, STANDARD_ERROR_RESPONSES, LedgerResponse
from finance_core.contracts_v3 import DraftRecord, JournalEntry, MonthlyActivityReview, OpeningCashFlow, OpeningRecords, MonthlyPlanReport
from finance_core.monthly_plans import monthly_plan_report
from finance_core.opening_balances import OpeningBalanceRequest, OpeningBalancePostRequest
from finance_core.opening_balance_operations import OpeningBalanceOperations
from finance_core.models_personal import (
    ArrangementDraftRequest, CloseRequest, FinancialAccount, FinanceSettings, InvestmentArrangement,
    MonthlyObservation, NonFinancialAsset, Party, PersonalModel, PersonalReportResponse, LegacyMappingRequest, Month,
    BalanceRecordRequest, RecordedBalance, RecordedBalanceReport,
)
from finance_core.personal_finance_repository import PersonalFinanceRepository, RevisionConflict

T = TypeVar('T')


class DataResponse(PersonalModel, Generic[T]):
    workspaceId: str
    data: T


def service(request: Request) -> PersonalFinanceRepository:
    try:
        return PersonalFinanceRepository(repo(request))
    except RevisionConflict as error:
        raise HTTPException(409, detail={'code': 'SCHEMA_MIGRATION_REQUIRED', 'message': str(error)}) from error


def operation(request: Request, method: str, *args, **kwargs) -> dict:
    try:
        result = getattr(service(request), method)(*args, **kwargs)
        return {'workspaceId': request.state.workspace_id, 'data': result}
    except RevisionConflict as error:
        raise HTTPException(409, detail={'code': 'REVISION_CONFLICT', 'message': str(error)}) from error
    except HTTPException:
        raise
    except Exception as error:
        raise translate(error) from error


def create_personal_router() -> APIRouter:
    router = APIRouter(prefix='/api/v3/workspaces/{workspace_id}',
                       dependencies=[Depends(require_admin), Depends(workspace_context, scope='function')],
                       responses=STANDARD_ERROR_RESPONSES)
    extra = {'security': SESSION_SECURITY, 'x-fc-required-actor': 'owner-session'}

    @router.get('/reports/monthly-plans', response_model=DataResponse[MonthlyPlanReport], openapi_extra=extra)
    def planned_cash_flow(request: Request, month: str = Query(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')):
        try:
            return {'data': monthly_plan_report(repo(request).list_monthly_plans(), month), 'workspaceId': request.state.workspace_id}
        except Exception as error:
            raise translate(error) from error

    @router.post('/opening-balance-drafts', response_model=DataResponse[DraftRecord], status_code=201, openapi_extra=extra)
    def opening_draft(item: OpeningBalanceRequest, request: Request):
        try:
            return {'data': OpeningBalanceOperations(repo(request)).create_draft(item), 'workspaceId': request.state.workspace_id}
        except Exception as error:
            raise translate(error) from error

    @router.get('/opening-balances', response_model=DataResponse[OpeningRecords], openapi_extra=extra)
    def opening_records(request: Request):
        try:
            return {'data': OpeningBalanceOperations(repo(request)).records(), 'workspaceId': request.state.workspace_id}
        except Exception as error:
            raise translate(error) from error

    @router.post('/opening-balances/{draft_id}/post', response_model=DataResponse[JournalEntry], openapi_extra=extra)
    def post_opening(draft_id: str, item: OpeningBalancePostRequest, request: Request):
        try:
            return {'data': OpeningBalanceOperations(repo(request)).post(draft_id, item), 'workspaceId': request.state.workspace_id}
        except Exception as error:
            raise translate(error) from error

    @router.post('/opening-living-balances', response_model=DataResponse[RecordedBalance], status_code=201, openapi_extra=extra)
    def opening_living(item: BalanceRecordRequest, request: Request):
        try:
            return {'data': OpeningBalanceOperations(repo(request)).record_living(item), 'workspaceId': request.state.workspace_id}
        except Exception as error:
            raise translate(error) from error

    @router.get('/reports/activity-cash-flow', response_model=DataResponse[OpeningCashFlow], openapi_extra=extra)
    def activity_cash_flow(request: Request, month: str = Query(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')):
        try:
            return {'data': OpeningBalanceOperations(repo(request)).cash_flow(month), 'workspaceId': request.state.workspace_id}
        except Exception as error:
            raise translate(error) from error

    @router.get('/reports/monthly-activity-review', response_model=DataResponse[MonthlyActivityReview], openapi_extra=extra)
    def monthly_activity(request: Request, month: str = Query(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')):
        try:
            return {'data': OpeningBalanceOperations(repo(request)).monthly_activity(month), 'workspaceId': request.state.workspace_id}
        except Exception as error:
            raise translate(error) from error

    @router.get('/financial-accounts', response_model=DataResponse[list[FinancialAccount]], openapi_extra=extra)
    def accounts(request: Request):
        return operation(request, 'accounts')

    @router.post('/financial-accounts', response_model=DataResponse[FinancialAccount], status_code=201, openapi_extra=extra)
    def create_account(item: FinancialAccount, request: Request):
        return operation(request, 'save_account', item, create=True)

    @router.put('/financial-accounts/{account_id}', response_model=DataResponse[FinancialAccount], openapi_extra=extra)
    def update_account(account_id: str, item: FinancialAccount, request: Request):
        if account_id != item.id:
            raise HTTPException(422, detail='Account id cannot change.')
        return operation(request, 'save_account', item, create=False)

    @router.delete('/financial-accounts/{account_id}', response_model=DataResponse[FinancialAccount], openapi_extra=extra)
    def delete_account(account_id: str, request: Request):
        return operation(request, 'delete_account', account_id)

    @router.get('/finance-parties', response_model=DataResponse[list[Party]], openapi_extra=extra)
    def parties(request: Request):
        return operation(request, 'parties')

    @router.put('/finance-parties/{party_id}', response_model=DataResponse[Party], openapi_extra=extra)
    def party(party_id: str, item: Party, request: Request):
        if party_id != item.id:
            raise HTTPException(422, detail='Party id cannot change.')
        return operation(request, 'save_party', item)

    @router.get('/personal-finance-settings', response_model=DataResponse[FinanceSettings | None], openapi_extra=extra)
    def settings(request: Request):
        return operation(request, 'settings')

    @router.put('/personal-finance-settings', response_model=DataResponse[FinanceSettings], openapi_extra=extra)
    def save_settings(item: FinanceSettings, request: Request):
        return operation(request, 'save_settings', item)

    @router.get('/legacy-living-mapping', response_model=LedgerResponse, openapi_extra=extra)
    def legacy(request: Request):
        return operation(request, 'legacy_living')

    @router.post('/legacy-living-mapping/{legacy_id}', response_model=DataResponse[FinancialAccount], openapi_extra=extra)
    def map_legacy(legacy_id: str, item: LegacyMappingRequest, request: Request):
        return operation(request, 'map_legacy', legacy_id, item)

    @router.get('/non-financial-assets', response_model=DataResponse[list[NonFinancialAsset]], openapi_extra=extra)
    def assets(request: Request):
        return operation(request, 'assets')

    @router.post('/non-financial-assets', response_model=DataResponse[NonFinancialAsset], status_code=201, openapi_extra=extra)
    def create_asset(item: NonFinancialAsset, request: Request):
        return operation(request, 'save_asset', item, create=True)

    @router.put('/non-financial-assets/{asset_id}', response_model=DataResponse[NonFinancialAsset], openapi_extra=extra)
    def update_asset(asset_id: str, item: NonFinancialAsset, request: Request):
        if asset_id != item.id:
            raise HTTPException(422, detail='Asset id cannot change.')
        return operation(request, 'save_asset', item, create=False)

    @router.get('/investment-arrangements', response_model=DataResponse[list[InvestmentArrangement]], openapi_extra=extra)
    def arrangements(request: Request):
        return operation(request, 'arrangements')

    @router.post('/investment-arrangements', response_model=DataResponse[InvestmentArrangement], status_code=201, openapi_extra=extra)
    def create_arrangement(item: InvestmentArrangement, request: Request):
        return operation(request, 'save_arrangement', item)

    @router.post('/investment-arrangements/{arrangement_id}/drafts', response_model=LedgerResponse, status_code=201, openapi_extra=extra)
    def draft(arrangement_id: str, item: ArrangementDraftRequest, request: Request):
        return operation(request, 'generate_draft', arrangement_id, item)

    @router.get('/monthly-observations', response_model=LedgerResponse, openapi_extra=extra)
    def observations(request: Request):
        return operation(request, 'observations')

    @router.post('/monthly-observations', response_model=DataResponse[MonthlyObservation], status_code=201, openapi_extra=extra)
    def observe(item: MonthlyObservation, request: Request):
        if item.observed_date:
            raise HTTPException(422, detail='Use /balance-records for actual-date balances; monthly observations retain their month-end basis.')
        return operation(request, 'record_observation', item)

    @router.get('/monthly-closes', response_model=LedgerResponse, openapi_extra=extra)
    def closes(request: Request):
        return operation(request, 'closes')

    @router.get('/balance-records', response_model=DataResponse[list[RecordedBalance]], openapi_extra=extra)
    def balance_records(request: Request):
        return operation(request, 'balance_records')

    @router.post('/balance-records', response_model=DataResponse[RecordedBalance], status_code=201, openapi_extra=extra)
    def balance_record(item: BalanceRecordRequest, request: Request):
        return operation(request, 'record_balance', item)

    @router.get('/reports/living-recorded-balances', response_model=DataResponse[RecordedBalanceReport], openapi_extra=extra)
    def recorded_balances(request: Request, month: Month = Query(..., description='Latest actual-date balance within YYYY-MM; missing months remain unknown.')):
        return operation(request, 'recorded_balance_report', month)

    @router.post('/monthly-closes', response_model=LedgerResponse, status_code=201, openapi_extra=extra)
    def close(item: CloseRequest, request: Request):
        return operation(request, 'close_month', item)

    @router.get('/reports/personal-balance-sheet', response_model=PersonalReportResponse, openapi_extra=extra)
    @router.get('/reports/living-monthly-review', response_model=PersonalReportResponse, openapi_extra=extra)
    @router.get('/reports/investment-monthly-review', response_model=PersonalReportResponse, openapi_extra=extra)
    @router.get('/reconciliation/personal-finance', response_model=PersonalReportResponse, openapi_extra=extra)
    def report(request: Request, month: Month = Query(..., min_length=7, max_length=7,
               pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$', description='Month-end in Asia/Shanghai, YYYY-MM.')):
        return operation(request, 'report', month)

    @router.get('/segments/{segment}/export', response_model=LedgerResponse, openapi_extra=extra)
    def segment_export(segment: str, request: Request):
        if segment not in {'investment','living'}:
            raise HTTPException(422, detail='Unknown segment.')
        return operation(request, 'export_segment', segment)

    @router.get('/segments/{segment}/export.csv', response_class=Response, openapi_extra={**extra,'responses':{'200':{'content':{'text/csv':{'schema':{'type':'string'}}}}}})
    def segment_csv(segment: str, request: Request):
        if segment not in {'investment','living'}:
            raise HTTPException(422,detail='Unknown segment.')
        return Response(service(request).export_segment_csv(segment),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename={segment}-export.csv'})

    @router.post('/import/living-monthly/validate', response_model=LedgerResponse, openapi_extra=extra)
    async def preview_csv(request: Request):
        data = await request.body()
        if len(data) > 2 * 1024 * 1024:
            raise HTTPException(422, detail='CSV exceeds the 2 MiB preview limit.')
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as error:
            raise HTTPException(422, detail='CSV must be UTF-8.') from error
        return operation(request, 'preview_living_csv', text)

    @router.post('/import/living-monthly', response_model=LedgerResponse, status_code=201, openapi_extra=extra)
    def import_pending(request: Request, items: list[MonthlyObservation] = Body(..., min_length=1, max_length=1000)):
        if any(item.observed_date for item in items):
            raise HTTPException(422, detail='Actual-date balances are not legacy monthly imports. Use /balance-records.')
        if any(item.confirmed for item in items):
            raise HTTPException(422, detail='Imported monthly data must remain unconfirmed until individual review.')
        return operation(request, 'record_observations', items)

    @router.get('/vault-backup', response_model=LedgerResponse, openapi_extra=extra)
    def backup(request: Request):
        service(request)
        return {'workspaceId': request.state.workspace_id, 'data': repo(request).create_backup(format_version=3)}

    @router.post('/vault-backup/restore', response_model=LedgerResponse, status_code=201, openapi_extra=extra)
    def restore(request: Request, payload: dict = Body(...)):
        service(request)
        try:
            return {'workspaceId': request.state.workspace_id, 'restored': repo(request).restore_backup(payload)}
        except Exception as error:
            raise translate(error) from error

    return router
