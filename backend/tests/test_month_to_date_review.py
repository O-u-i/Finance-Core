"""The public Workspace API returns an explicit, provisional single-month cut-off."""
from datetime import date, datetime, timedelta, timezone

import pytest

from test_v2 import ACCOUNTS, client, create_and_post, seed
from test_v3 import authenticated_client, create_access_token, create_workspace


def income(identifier, day, amount):
    return {
        'id': identifier, 'date': day, 'description': 'PRIVATE DESCRIPTION',
        'balancingCommodityCode': 'CNY', 'postings': [
            {'id': identifier + '-cash', 'accountId': 'cash-cny', 'side': 'debit',
             'units': amount, 'commodityCode': 'CNY'},
            {'id': identifier + '-income', 'accountId': 'gain', 'side': 'credit',
             'units': amount, 'commodityCode': 'CNY'},
        ],
    }


def test_explicit_cutoff_reads_one_partial_month_without_inventing_history(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        for identifier, day, amount in [
            ('prior', '2026-07-31', '100'), ('first', '2026-08-01', '12.34'),
            ('cutoff', '2026-08-18', '3.21'), ('later', '2026-08-19', '999'),
        ]:
            create_and_post(api, income(identifier, day, amount))
        assert api.post('/api/v2/journal-entry-drafts', json=income('pending', '2026-08-17', '500')).status_code == 201
        path = '/api/v2/reports/month-to-date?asOf=2026-08-18'
        response = api.get(path)
        assert response.status_code == 200, response.text
        body, report = response.json(), response.json()['data']
        assert body['readOnly'] is True and body['workspaceId']
        assert report['asOf'] == '2026-08-18' and report['month'] == '2026-08'
        assert report['windowStart'] == '2026-08-01'
        assert report['windowEndExclusive'] == '2026-08-19'
        assert report['calculationVersion'] == 'month-to-date-v1'
        assert report['periodStatus'] == 'partial' and report['status'] == 'ready'
        assert 'months' not in report
        assert report['period']['postedEntryCount'] == 2
        totals = report['period']['currencies'][0]
        assert totals['cashInflow'] == totals['income'] == totals['cashNet'] == '15.55'
        assert totals['cashNetChange'] is totals['incomeChange'] is totals['expensesChange'] is None
        assert report['coverage']['externalCompleteness'] == 'unknown'
        assert report['coverage']['unrecordedDays'] == 'unknown'
        assert report['coverage']['activityBasis'] == 'posted-journal-only'
        assert body == api.get(path).json()
        for private in ('PRIVATE', 'cash-cny', 'first-cash', 'pending', '999'):
            assert private not in response.text
        # The completed three-month API is unchanged, not repurposed as an MTD read.
        previous = api.get('/api/v2/reports/monthly-review?month=2026-08').json()['data']
        assert len(previous['months']) == 3 and previous['months'][2]['currencies'][0]['income'] == '1014.55'


def test_decimal_axes_and_internal_transfers_are_not_income_or_duplicate_flows(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        for identifier, kind, subtype in [('expense', 'expense', ''), ('debt', 'liability', ''), ('bank', 'asset', 'cash')]:
            assert api.post('/api/v2/accounts', json={'id': identifier, 'code': identifier, 'name': 'PRIVATE ACCOUNT',
                'type': kind, 'subtype': subtype, 'allowedCommodityCodes': ['CNY'], 'status': 'active'}).status_code == 201
        create_and_post(api, income('salary', '2026-08-01', '1000'))
        for identifier, debit, credit, amount in [('borrow', 'cash-cny', 'debt', '300'),
            ('card-spend', 'expense', 'debt', '100'), ('repay', 'debt', 'cash-cny', '100'),
            ('transfer', 'bank', 'cash-cny', '200')]:
            draft = income(identifier, '2026-08-18', amount)
            draft['postings'][0]['accountId'], draft['postings'][1]['accountId'] = debit, credit
            create_and_post(api, draft)
        report = api.get('/api/v2/reports/month-to-date?asOf=2026-08-18').json()['data']
        row = report['period']['currencies'][0]
        assert (row['cashInflow'], row['cashOutflow'], row['cashNet']) == ('1300', '100', '1200')
        assert (row['income'], row['expenses'], row['netIncome']) == ('1000', '100', '900')
        assert report['period']['postedEntryCount'] == 5


def test_cutoff_revision_and_current_classification_revalidate_without_fetching_other_periods(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        create_and_post(api, income('one', '2026-08-01', '1.01'))
        path = '/api/v2/reports/month-to-date?asOf=2026-08-18'
        original = api.get(path).json()['data']
        create_and_post(api, income('outside', '2026-08-19', '999'))
        assert api.get(path).json()['data'] == original
        assert api.get('/api/v2/reports/month-to-date?asOf=2026-08-17').json()['data']['revision'] != original['revision']
        create_and_post(api, income('inside', '2026-08-18', '2.02'))
        changed = api.get(path).json()['data']
        assert changed['revision'] != original['revision']
        assert changed['period']['currencies'][0]['income'] == '3.03'
        account = {**ACCOUNTS[0], 'subtype': 'investment'}
        assert api.put('/api/v2/accounts/cash-cny', json=account).status_code == 200
        classified = api.get(path).json()['data']
        assert classified['revision'] != changed['revision']
        assert classified['period']['currencies'][0]['cashInflow'] == '0'


def test_multiple_currencies_are_exact_and_never_converted_or_merged(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        assert api.post('/api/v2/accounts', json={**ACCOUNTS[-1], 'id': 'usd-income', 'code': 'USD-INC',
            'allowedCommodityCodes': ['USD']}).status_code == 201
        create_and_post(api, income('large', '2026-08-18', '9007199254740993.01'))
        usd = income('usd', '2026-08-18', '12.34')
        usd['balancingCommodityCode'] = 'USD'
        for row, account in zip(usd['postings'], ['cash-usd', 'usd-income'], strict=True):
            row.update(accountId=account, commodityCode='USD')
        create_and_post(api, usd)
        rows = api.get('/api/v2/reports/month-to-date?asOf=2026-08-18').json()['data']['period']['currencies']
        assert [(row['commodityCode'], row['income']) for row in rows] == [('CNY', '9007199254740993.01'), ('USD', '12.34')]


def test_current_month_reversal_retains_signed_adjustments_not_original_month_rewriting(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        create_and_post(api, income('old-income', '2025-03-01', '50'))
        reversed_entry = api.post('/api/v2/journal-entries/old-income/reverse')
        assert reversed_entry.status_code == 201
        day = reversed_entry.json()['data']['date']
        report = api.get('/api/v2/reports/month-to-date', params={'asOf': day}).json()['data']
        row = report['period']['currencies'][0]
        assert report['period']['reversalEntryCount'] == 1
        assert row['cashNet'] == row['cashAdjustment'] == row['income'] == row['incomeAdjustment'] == '-50'


@pytest.mark.parametrize('day', ['', '2026/10/18', '2026-2-03', '2026-02-29', '2026-13-01', '9999-12-31'])
def test_invalid_or_future_cutoffs_are_not_silently_changed(tmp_path, day):
    with client(tmp_path) as api:
        assert api.get('/api/v2/reports/month-to-date', params={'asOf': day}).status_code == 422


def test_current_date_empty_records_and_read_only_workspace_authorization(tmp_path):
    api = authenticated_client(tmp_path)
    try:
        one, two = create_workspace(api), create_workspace(api, 'Other')
        token = create_access_token(api, [one['id']], ['ledger:read'])
        write_only = create_access_token(api, [one['id']], ['ledger:write'])
        api.cookies.clear()
        day = datetime.now(timezone(timedelta(hours=8))).date()
        path = f"/api/v3/workspaces/{one['id']}/reports/month-to-date"
        headers = {'Authorization': 'Bearer ' + token}
        response = api.get(path, params={'asOf': day.isoformat()}, headers=headers)
        assert response.status_code == 200, response.text
        report = response.json()['data']
        assert report['period']['postedEntryCount'] == 0 and report['period']['currencies'] == []
        assert report['coverage']['externalCompleteness'] == report['coverage']['unrecordedDays'] == 'unknown'
        assert report['periodStatus'] == 'partial'
        assert api.get(path, params={'asOf': (day + timedelta(days=1)).isoformat()}, headers=headers).status_code == 422
        assert api.get(path, headers=headers).status_code == 422
        assert api.get(path, params={'asOf': day.isoformat()}).status_code == 401
        assert api.get(path, params={'asOf': day.isoformat()}, headers={'Authorization': 'Bearer ' + write_only}).status_code == 403
        other = f"/api/v3/workspaces/{two['id']}/reports/month-to-date"
        assert api.get(other, params={'asOf': day.isoformat()}, headers=headers).status_code == 404
        assert api.post(f"/api/v3/workspaces/{one['id']}/journal-entry-drafts", headers=headers, json={}).status_code == 403
        operation = api.get('/openapi.json').json()['paths']['/api/v3/workspaces/{workspace_id}/reports/month-to-date']['get']
        assert operation['x-fc-required-scope'] == 'ledger:read'
        assert operation['responses']['200']['content']['application/json']['schema']['$ref'].endswith('/MonthToDateReviewResponse')
    finally:
        api.__exit__(None, None, None)


def test_unassignable_legacy_posted_date_blocks_every_total_without_leaking_it():
    from finance_core.monthly_review import month_to_date_review
    report = month_to_date_review('2026-08-18', [{'id': 'PRIVATE-ID', 'date': 'PRIVATE-BAD-DATE',
        'balancing_commodity_code': 'CNY', 'reversal_of': None}], [])
    assert report['status'] == 'blocked' and report['period'] is None
    assert report['coverage']['invalidDateEntryCount'] == 1
    assert 'PRIVATE' not in str(report)
