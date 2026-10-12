"""Commodity lifecycle through the public Workspace API; synthetic data only."""
import pytest

from test_personal_finance import MONTH, data, draft, seed_personal, totals
from test_v2 import client


def test_unused_commodity_can_be_deleted_without_deleting_other_codes(tmp_path):
    with client(tmp_path) as api:
        for code, status in [('1', 'inactive'), ('2', 'active')]:
            response = api.post(api.prefix + '/commodities', json={
                'code': code, 'name': 'Synthetic unused currency', 'kind': 'currency',
                'scale': 2, 'status': status})
            assert response.status_code == 201, response.text
        token = data(api, '/undo/latest')['undoToken']
        response = api.delete(api.prefix + '/commodities/1')
        assert response.status_code == 200, response.text
        assert response.json()['data']['code'] == '1'
        assert [item['code'] for item in data(api, '/commodities')] == ['2']
        assert api.delete(api.prefix + '/commodities/1').status_code == 404
        assert data(api, '/undo/latest') is None
        assert api.post(api.prefix + '/undo', json={'undoToken': token}).status_code == 410
        assert [item['code'] for item in data(api, '/commodities')] == ['2']


def test_opt_in_usage_distinguishes_typed_references_from_free_text_without_writes(tmp_path):
    with client(tmp_path) as api:
        for code in ('1', '2'):
            assert api.post(api.prefix + '/commodities', json={
                'code': code, 'name': 'Synthetic currency', 'kind': 'currency', 'scale': 2}).status_code == 201
        assert {item['code']: item['inUse'] for item in data(api, '/commodities?includeUsage=true')} == {'1': False, '2': False}
        assert api.post(api.prefix + '/accounts', json={
            'id': 'account', 'code': '1', 'name': 'The text 1 is not a commodity reference',
            'type': 'asset', 'allowedCommodityCodes': ['2']}).status_code == 201
        before = data(api, '/vault-backup')['sha256']
        plain = data(api, '/commodities')
        assert all('inUse' not in item for item in plain), 'The original list shape remains unchanged.'
        usage = data(api, '/commodities?includeUsage=true')
        assert {item['code']: item['inUse'] for item in usage} == {'1': False, '2': True}
        assert data(api, '/vault-backup')['sha256'] == before
        blocked = api.delete(api.prefix + '/commodities/2')
        assert blocked.status_code == 422, blocked.text
        assert 'Deactivate' in blocked.json()['error']['message']
        assert data(api, '/commodities') == plain
        assert data(api, '/vault-backup')['sha256'] == before
        assert api.delete(api.prefix + '/commodities/1').status_code == 200


@pytest.mark.parametrize('reference', ['living_account', 'asset', 'agreement', 'transfer', 'draft', 'recurring', 'price', 'plan', 'legacy_wallet'])
def test_referenced_commodity_deletion_preserves_configuration_and_history(tmp_path, reference):
    with client(tmp_path) as api:
        for code in ('TARGET', 'BASE'):
            assert api.post(api.prefix + '/commodities', json={
                'code': code, 'name': 'Synthetic currency', 'kind': 'currency', 'scale': 2}).status_code == 201
        assert api.put(api.prefix + '/finance-parties/owner', json={'id': 'owner', 'name': 'Synthetic owner'}).status_code == 200
        if reference == 'living_account':
            path, body = '/financial-accounts', {
                'id': 'wallet', 'code': 'wallet', 'name': 'Synthetic wallet', 'type': 'asset',
                'allowedCommodityCodes': ['TARGET'], 'segment': 'living',
                'balanceSource': 'monthly_snapshot', 'ownerPartyId': 'owner'}
        elif reference == 'asset':
            path, body = '/non-financial-assets', {
                'id': 'asset', 'name': 'Synthetic asset', 'assetType': 'vehicle', 'currency': 'TARGET',
                'purchasedDate': '2026-07-01', 'purchaseCost': '0', 'ownerPartyId': 'owner'}
        elif reference == 'agreement':
            path, body = '/investment-arrangements', {
                'id': 'agreement', 'version': 1, 'currency': 'TARGET', 'fromMonth': MONTH,
                'residualShares': [{'partyId': 'owner', 'share': '1'}], 'reason': 'Synthetic agreement'}
        elif reference == 'transfer':
            path, body = '/monthly-observations', {
                'id': 'transfer', 'subjectId': 'TARGET', 'currency': 'TARGET', 'month': MONTH,
                'kind': 'transfer', 'incoming': '0', 'outgoing': '0', 'confirmed': True, 'source': 'Synthetic transfer'}
        elif reference in {'draft', 'recurring'}:
            template = {'id': 'draft', 'date': '2026-08-01', 'description': 'Synthetic unposted entry',
                        'balancingCommodityCode': 'TARGET', 'postings': [
                            {'id': 'debit', 'accountId': 'unregistered', 'side': 'debit', 'units': '1', 'commodityCode': 'BASE'},
                            {'id': 'credit', 'accountId': 'unregistered', 'side': 'credit', 'units': '1', 'commodityCode': 'BASE'}]}
            path, body = '/journal-entry-drafts', template
            if reference == 'recurring':
                path, body = '/recurring-entry-rules', {'id': 'rule', 'name': 'Synthetic disabled rule',
                    'enabled': False, 'dayOfMonth': 1, 'startDate': '2026-08-01', 'template': template}
        elif reference == 'price':
            path, body = '/price-quotes', {'id': 'quote', 'commodityCode': 'BASE', 'quoteCommodityCode': 'TARGET',
                'price': '1', 'asOf': '2026-08-01T00:00:00Z', 'source': 'Synthetic price'}
        elif reference == 'plan':
            path, body = '/monthly-plans', {'id': 'plan', 'kind': 'income', 'name': 'Synthetic plan', 'amount': '0',
                'commodityCode': 'TARGET', 'category': 'test', 'recurringMonthly': True, 'dayOfMonth': 1, 'startDate': '2026-08-01'}
        else:
            path, body = '/living-accounts', {'id': 'legacy', 'name': 'Synthetic legacy wallet',
                'commodityCode': 'TARGET', 'balance': '0', 'updatedAt': '2026-08-01T00:00:00Z'}
        response = api.post(api.prefix + path, json=body)
        assert response.status_code == 201, response.text
        item = next(value for value in data(api, '/commodities') if value['code'] == 'TARGET')
        assert api.put(api.prefix + '/commodities/TARGET', json={**item, 'status': 'inactive'}).status_code == 200
        before = data(api, '/vault-backup')['sha256']
        assert next(item for item in data(api, '/commodities?includeUsage=true') if item['code'] == 'TARGET')['inUse'] is True
        response = api.delete(api.prefix + '/commodities/target')
        assert response.status_code == 422, response.text
        assert 'Deactivate' in response.json()['error']['message']
        assert data(api, '/vault-backup')['sha256'] == before


def test_deactivated_posted_currency_still_has_its_financial_values_and_cannot_be_deleted(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        draft(api, 'interest', 'interest', '5', interestAgreementId='fixed', specialPeriodConfirmed=True)
        _, before = totals(api)
        item = data(api, '/commodities')[0]
        assert api.put(api.prefix + '/commodities/CNY', json={**item, 'status': 'inactive'}).status_code == 200
        report, after = totals(api)
        assert after == before
        assert after['personalNetWorth'] == '5447.5'
        assert api.delete(api.prefix + '/commodities/CNY').status_code == 422
        assert totals(api)[0] == report


def test_confirmed_close_keeps_even_zero_registry_input_provenance(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        assert api.post(api.prefix + '/commodities', json={
            'code': 'EMPTY', 'name': 'Synthetic empty currency', 'kind': 'currency', 'scale': 2}).status_code == 201
        assert next(item for item in data(api, '/commodities?includeUsage=true') if item['code'] == 'EMPTY')['inUse'] is False
        draft(api, 'interest', 'interest', '5', interestAgreementId='fixed', specialPeriodConfirmed=True)
        report, _ = totals(api)
        result = api.post(api.prefix + '/monthly-closes', json={
            'month': MONTH, 'expectedRevision': report['revision'], 'reason': 'Synthetic confirmed baseline', 'confirmed': True})
        assert result.status_code == 201, result.text
        before = data(api, '/vault-backup')['sha256']
        assert next(item for item in data(api, '/commodities?includeUsage=true') if item['code'] == 'EMPTY')['inUse'] is True
        assert api.delete(api.prefix + '/commodities/EMPTY').status_code == 422
        assert data(api, '/vault-backup')['sha256'] == before


def test_commodity_delete_requires_workspace_write_authorization_and_trusted_owner_origin(tmp_path):
    with client(tmp_path) as api:
        assert api.post(api.prefix + '/commodities', json={
            'code': 'EMPTY', 'name': 'Synthetic unused currency', 'kind': 'currency', 'scale': 2}).status_code == 201
        workspace = api.prefix.rsplit('/', 1)[1]
        other = api.post('/api/v3/workspaces', json={'displayName': 'Synthetic other', 'kind': 'sandbox'}).json()['data']['id']
        for ids, scopes, expected in [([workspace], ['ledger:read'], 403), ([other], ['ledger:write'], 404)]:
            token = api.post('/api/v3/access-tokens', json={'name': 'Synthetic restricted token', 'workspaceIds': ids, 'scopes': scopes}).json()['token']
            response = api.delete(api.prefix + '/commodities/EMPTY', headers={'Authorization': 'Bearer ' + token})
            assert response.status_code == expected, response.text
        assert api.delete(api.prefix + '/commodities/EMPTY', headers={'Authorization': 'Bearer invalid'}).status_code == 401
        assert api.delete(api.prefix + '/commodities/EMPTY', headers={'Origin': 'https://untrusted.example'}).status_code == 403
        assert [item['code'] for item in data(api, '/commodities')] == ['EMPTY']
