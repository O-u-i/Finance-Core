"""Synthetic Workspace HTTP checks: plans are forecasts, never actual ledger cash flows."""
from test_v2 import client, seed
import pytest


def plan(api, **values):
    payload = dict(id='salary', name='Synthetic salary', kind='income', amount='0.10',
                   commodityCode='CNY', category='Work', recurringMonthly=True,
                   dayOfMonth=13, startDate='2026-01-01', note='Forecast context')
    payload.update(values)
    response = api.post('/api/v2/monthly-plans', json=payload)
    assert response.status_code == 201, response.text
    return payload


def test_monthly_day_is_a_date_and_category_totals_are_exact_separate_currency_forecasts(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        plan(api)
        plan(api, id='bonus', amount='0.20')
        plan(api, id='rent', kind='expense', amount='0.07', category='Home')
        plan(api, id='usd', commodityCode='USD', amount='99999999999999999999.99')
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        response = api.get(api.prefix + '/reports/monthly-plans?month=2026-02')
        assert response.status_code == 200, response.text
        report = response.json()['data']
        assert report['basis'] == 'planned-only'
        assert next(row for row in report['occurrences'] if row['planId'] == 'salary')['dueDate'] == '2026-02-13'
        assert report['currencies'] == [
            {'currency': 'CNY', 'inflow': '0.3', 'outflow': '0.07', 'net': '0.23', 'count': 3},
            {'currency': 'USD', 'inflow': '99999999999999999999.99', 'outflow': '0', 'net': '99999999999999999999.99', 'count': 1},
        ]
        assert next(row for row in report['categories'] if row['category'] == 'Work' and row['currency'] == 'CNY')['inflow'] == '0.3'
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before


def test_schedules_respect_start_dates_once_only_and_short_months(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        plan(api, startDate='2026-02-14')
        plan(api, id='month-end', dayOfMonth=31)
        plan(api, id='once', recurringMonthly=False, startDate='2026-02-07', dayOfMonth=1)
        report = api.get(api.prefix + '/reports/monthly-plans?month=2026-02').json()['data']
        assert {row['planId']: row['dueDate'] for row in report['occurrences']} == {'month-end': '2026-02-28', 'once': '2026-02-07'}
        next_month = api.get(api.prefix + '/reports/monthly-plans?month=2026-03').json()['data']
        assert {row['planId']: row['dueDate'] for row in next_month['occurrences']} == {'salary': '2026-03-13', 'month-end': '2026-03-31'}
        leap = api.get(api.prefix + '/reports/monthly-plans?month=2028-02').json()['data']
        assert next(row for row in leap['occurrences'] if row['planId'] == 'month-end')['dueDate'] == '2028-02-29'


@pytest.mark.parametrize('interval,months', [(3, ['2026-02', '2026-05', '2026-08', '2026-11', '2027-02']),
                                          (6, ['2026-02', '2026-08', '2027-02']),
                                          (12, ['2026-02', '2027-02'])])
def test_periodic_plans_keep_the_start_month_anchor_and_original_due_day(tmp_path, interval, months):
    with client(tmp_path) as api:
        seed(api)
        plan(api, startDate='2026-02-01', dayOfMonth=31, repeatEveryMonths=interval)
        saved = api.get('/api/v2/monthly-plans').json()['data'][0]
        assert saved['repeatEveryMonths'] == interval
        scheduled = {}
        for month in ['2026-01', '2026-02', '2026-03', '2026-05', '2026-08', '2026-11', '2027-02']:
            report = api.get(api.prefix + '/reports/monthly-plans?month=' + month).json()['data']
            if report['occurrences']:
                scheduled[month] = report['occurrences'][0]['dueDate']
        assert list(scheduled) == months
        assert scheduled['2026-02'] == '2026-02-28'
        if interval == 3:
            assert scheduled['2026-05'] == '2026-05-31'
        assert api.get('/api/v2/journal-entries').json()['data'] == []


def test_plan_edits_deletes_and_high_precision_totals_never_change_journal(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        first = plan(api, amount='99999999999999999999.99')
        plan(api, id='small', amount='0.02')
        assert api.get(api.prefix + '/reports/monthly-plans?month=2026-02').json()['data']['currencies'][0]['inflow'] == '100000000000000000000.01'
        assert api.put('/api/v2/monthly-plans/salary', json={**first, 'amount': '0.11', 'category': 'Updated'}).status_code == 200
        assert api.delete('/api/v2/monthly-plans/small').status_code == 200
        report = api.get(api.prefix + '/reports/monthly-plans?month=2026-02').json()['data']
        assert report['categories'] == [{'category': 'Updated', 'currency': 'CNY', 'inflow': '0.11', 'outflow': '0', 'net': '0.11', 'count': 1}]
        assert api.get('/api/v2/journal-entries').json()['data'] == []


def test_periodic_schedule_survives_edit_undo_and_full_backup_without_changing_the_note(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        first = plan(api, repeatEveryMonths=12)
        edited = api.put('/api/v2/monthly-plans/salary', json={**first, 'repeatEveryMonths': 3}).json()
        assert api.post('/api/v2/undo', json={'undoToken': edited['undo']['undoToken']}).status_code == 200
        assert api.get('/api/v2/monthly-plans').json()['data'][0]['repeatEveryMonths'] == 12
        backup = api.get(api.prefix + '/vault-backup').json()['data']
        other = api.api.post('/api/v3/workspaces', json={'displayName': 'Restored synthetic plans', 'kind': 'sandbox'}).json()['data']['id']
        target = f'/api/v3/workspaces/{other}'
        assert api.post(target + '/vault-backup/restore', json=backup).status_code == 201
        restored = api.get(target + '/monthly-plans').json()['data'][0]
        assert restored['repeatEveryMonths'] == 12
        assert restored['note'] == 'Forecast context'
        deleted = api.delete('/api/v2/monthly-plans/salary').json()
        assert api.post('/api/v2/undo', json={'undoToken': deleted['undo']['undoToken']}).status_code == 200
        assert api.get('/api/v2/monthly-plans').json()['data'][0]['repeatEveryMonths'] == 12
        assert api.get('/api/v2/backup').status_code == 409  # Legacy format cannot silently lose schedules.


@pytest.mark.parametrize('changes', [{'repeatEveryMonths': 2}, {'repeatEveryMonths': 0},
                                   {'recurringMonthly': False, 'repeatEveryMonths': 3},
                                   {'startDate': '2026-02-30'}, {'startDate': '20260201'}])
def test_invalid_periodic_schedules_are_rejected_without_writes(tmp_path, changes):
    with client(tmp_path) as api:
        seed(api)
        before = api.get(api.prefix + '/vault-backup').json()['data']['sha256']
        response = api.post('/api/v2/monthly-plans', json=dict(id='bad', name='Bad schedule', kind='income',
            amount='1', commodityCode='CNY', category='Test', recurringMonthly=True, dayOfMonth=1,
            startDate='2026-01-01') | changes)
        assert response.status_code == 422
        assert api.get(api.prefix + '/vault-backup').json()['data']['sha256'] == before


@pytest.mark.parametrize('month', ['2026-13', '0000-01', 'not-a-month'])
def test_invalid_plan_report_month_is_rejected(tmp_path, month):
    with client(tmp_path) as api:
        assert api.get(api.prefix + '/reports/monthly-plans?month=' + month).status_code == 422


def test_plan_report_is_workspace_scoped_and_owner_only(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        plan(api)
        other = api.api.post('/api/v3/workspaces', json={'displayName': 'Other synthetic', 'kind': 'sandbox'}).json()['data']['id']
        assert api.get(f'/api/v3/workspaces/{other}/reports/monthly-plans?month=2026-02').json()['data']['occurrences'] == []
        token = api.api.post('/api/v3/access-tokens', json={'name': 'Synthetic read client', 'workspaceIds': [api.prefix.rsplit('/', 1)[-1]], 'scopes': ['ledger:read']}).json()['token']
        api.api.delete('/api/v3/session')
        assert api.get(api.prefix + '/reports/monthly-plans?month=2026-02').status_code == 401
        assert api.get(api.prefix + '/reports/monthly-plans?month=2026-02', headers={'Authorization': 'Bearer ' + token}).status_code == 403
