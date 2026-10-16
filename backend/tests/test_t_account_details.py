"""Additive v3 read contract, synthetic Vaults only."""
import pytest
from contextlib import contextmanager

from test_v3 import authenticated_client, create_access_token, create_workspace


@contextmanager
def owner_client(tmp_path):
    api = authenticated_client(tmp_path)
    try:
        yield api
    finally:
        api.__exit__(None, None, None)


def seed(api, prefix):
    for currency in ('CNY', 'USD'):
        assert api.post(prefix + '/commodities', json={
            'code': currency, 'name': 'Synthetic currency', 'kind': 'currency', 'scale': 2,
        }).status_code == 201
    for index, kind in enumerate(('asset', 'expense', 'liability', 'equity', 'income', 'clearing')):
        assert api.post(prefix + '/accounts', json={
            'id': kind, 'code': str(1000 + index), 'name': 'Synthetic ' + kind,
            'type': 'equity' if kind == 'clearing' else kind, 'allowedCommodityCodes': ['CNY', 'USD'],
        }).status_code == 201


def post(api, prefix, identity, day, account='asset'):
    postings = [
        {'id': identity + '-1', 'accountId': account, 'side': 'debit', 'units': '12.33', 'commodityCode': 'CNY', 'memo': 'Not part of this read contract'},
        {'id': identity + '-2', 'accountId': account, 'side': 'credit', 'units': '2.1', 'commodityCode': 'CNY'},
        {'id': identity + '-3', 'accountId': 'clearing', 'side': 'credit', 'units': '12.33', 'commodityCode': 'CNY'},
        {'id': identity + '-4', 'accountId': 'clearing', 'side': 'debit', 'units': '2.1', 'commodityCode': 'CNY'},
    ]
    assert api.post(prefix + '/journal-entry-drafts', json={
        'id': identity, 'date': day, 'description': 'Synthetic private description',
        'balancingCommodityCode': 'CNY', 'postings': postings,
    }).status_code == 201
    response = api.post(prefix + '/journal-entry-drafts/' + identity + '/post')
    assert response.status_code == 200, response.text
    return response.json()['entry']


@pytest.mark.parametrize('kind,expected', [('asset', '10.23'), ('expense', '10.23'), ('liability', '-10.23'), ('equity', '-10.23'), ('income', '-10.23')])
def test_normal_balances_and_optional_date_context(tmp_path, kind, expected):
    with owner_client(tmp_path) as api:
        workspace = create_workspace(api)
        prefix = f"/api/v3/workspaces/{workspace['id']}"
        seed(api, prefix)
        post(api, prefix, 'sample', '2026-09-12', kind)
        row = next(item for item in api.get(prefix + '/t-accounts').json()['data'] if item['accountId'] == kind)
        assert row['balance'] == expected
        assert row['debit'] == '12.33' and row['credit'] == '2.1'
        assert row['firstPostingDate'] == row['lastPostingDate'] == '2026-09-12'
        assert 'difference' not in row


def test_postings_are_scoped_paged_read_only_and_use_immutable_entry_dates(tmp_path):
    with owner_client(tmp_path) as api:
        workspace = create_workspace(api)
        other = create_workspace(api, 'Other')
        prefix = f"/api/v3/workspaces/{workspace['id']}"
        seed(api, prefix)
        newer = post(api, prefix, 'newer', '2026-09-20')
        older = post(api, prefix, 'older', '2026-09-03')
        # Unposted drafts never appear in either the summary or detail readout.
        assert api.post(prefix + '/journal-entry-drafts', json={'id': 'unposted', 'date': older['date'], 'description': 'Unposted synthetic', 'balancingCommodityCode': 'CNY', 'postings': [
            {key: value for key, value in item.items() if key in {'id', 'accountId', 'side', 'units', 'commodityCode'}}
            for item in older['postings']
        ]}).status_code == 201
        before = api.get(prefix + '/journal-entries').json()
        token = create_access_token(api, [workspace['id']], ['ledger:read'])
        headers = {'Authorization': 'Bearer ' + token}
        path = prefix + '/t-accounts/asset/postings?commodityCode=CNY'
        page = api.get(path + '&limit=2', headers=headers)
        assert page.status_code == 200, page.text
        body = page.json()
        assert body['workspaceId'] == workspace['id'] and body['readOnly'] is True
        assert body['count'] == 4 and body['offset'] == 0 and body['limit'] == 2 and body['hasMore'] is True
        assert [item['postingDate'] for item in body['data']] == [older['date']] * 2
        assert body['data'][0]['debit'] == '12.33' and body['data'][0]['credit'] == '0'
        assert body['data'][1]['debit'] == '0' and body['data'][1]['credit'] == '2.1'
        assert all(set(item) == {'postingId', 'entryId', 'postingDate', 'debit', 'credit'} for item in body['data'])
        assert 'Synthetic private description' not in page.text and 'Not part of this' not in page.text
        second = api.get(path + '&limit=2&offset=2', headers=headers).json()
        assert second['hasMore'] is False
        assert [item['postingDate'] for item in second['data']] == [newer['date']] * 2
        assert api.get(path + '&limit=2&offset=2', headers=headers).json() == second
        assert api.get(prefix + '/t-accounts/asset/postings?commodityCode=USD').json()['data'] == []
        assert api.get(prefix + '/journal-entries').json() == before
        for query in ('&limit=0', '&limit=201', '&offset=-1'):
            assert api.get(path + query).status_code == 422
        assert api.get(prefix + '/t-accounts/asset/postings').status_code == 422
        assert api.get(prefix + '/t-accounts/missing/postings?commodityCode=CNY').status_code == 404
        assert api.get(prefix + '/t-accounts/asset/postings?commodityCode=XXX').status_code == 404
        assert api.get(f"/api/v3/workspaces/{other['id']}/t-accounts/asset/postings?commodityCode=CNY", headers=headers).status_code == 404
        denied = create_access_token(api, [workspace['id']], ['ledger:write'])
        assert api.get(path, headers={'Authorization': 'Bearer ' + denied}).status_code == 403
        assert api.post(path, headers=headers).status_code == 405
        assert api.post(prefix + '/journal-entries/newer/reverse').status_code == 201
        entries = api.get(prefix + '/journal-entries').json()['data']
        reversed_entry = next(item for item in entries if item['reversalOf'] == 'newer')
        rows = api.get(path).json()['data']
        assert {item['postingDate'] for item in rows if item['entryId'] == reversed_entry['id']} == {reversed_entry['date']}
        assert api.patch(prefix, json={'status': 'archived'}).status_code == 200
        assert api.get(path, headers=headers).status_code == 200
        api.cookies.clear()
        assert api.get(path).status_code == 401


def test_openapi_declares_additive_detail_contract(tmp_path):
    with owner_client(tmp_path) as api:
        schema = api.get('/openapi.json').json()
        path = '/api/v3/workspaces/{workspace_id}/t-accounts/{account_id}/postings'
        operation = schema['paths'][path]['get']
        assert set(schema['paths'][path]) == {'get'}
        assert operation['x-fc-required-scope'] == 'ledger:read'
        assert operation['responses']['200']['content']['application/json']['schema']['$ref'].endswith('/TAccountPostingResponse')
        summary = schema['components']['schemas']['TAccount']
        assert 'firstPostingDate' not in summary['required'] and 'lastPostingDate' not in summary['required']
