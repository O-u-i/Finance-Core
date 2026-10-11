"""Account lifecycle at the Workspace HTTP boundary; synthetic data only."""
import pytest

from test_personal_finance import data, observe, seed_personal
from test_v2 import client, create_and_post, opening_draft, seed


@pytest.mark.parametrize('resource', ['accounts', 'financial-accounts'])
def test_unused_account_delete_removes_both_registry_and_ledger_identity(tmp_path, resource):
    with client(tmp_path) as api:
        seed(api)
        result = api.delete('/api/v2/' + resource + '/cash-usd')
        assert result.status_code == 200, result.text
        assert result.json()['data']['id'] == 'cash-usd'
        for path in ('/accounts', '/financial-accounts'):
            assert 'cash-usd' not in {item['id'] for item in api.get('/api/v2' + path).json()['data']}
        assert api.delete('/api/v2/' + resource + '/cash-usd').status_code == 404


def test_ended_living_account_keeps_history_and_allows_only_in_period_corrections(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        account = next(item for item in data(api, '/financial-accounts') if item['id'] == 'living')
        account.update(status='inactive', endMonth='2026-08')
        history = data(api, '/monthly-observations')
        assert api.put('/api/v2/financial-accounts/living', json=account).status_code == 200
        assert data(api, '/monthly-observations') == history
        response = api.post('/api/v2/monthly-observations', json={
            'id': 'after-end', 'subjectId': 'living', 'month': '2026-09', 'kind': 'balance',
            'currency': 'CNY', 'amount': '1', 'source': 'Synthetic statement', 'confirmed': True})
        assert response.status_code == 422, response.text
        current = next(item for item in history if item['subjectId'] == 'living' and item['month'] == '2026-08')
        observe(api, 'living', '2026-08', 'balance', '900', supersedes=current['id'], reason='Historical correction')
        assert api.delete('/api/v2/financial-accounts/living').status_code == 422
        assert len(data(api, '/monthly-observations')) == len(history) + 1


def test_safe_legacy_living_delete_refuses_snapshot_history_but_deletes_unused_account(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        for identity in ('unused-wallet', 'used-wallet'):
            assert api.post('/api/v2/living-accounts', json={
                'id': identity, 'name': 'Synthetic wallet', 'commodityCode': 'CNY',
                'balance': '0', 'updatedAt': '2026-08-01T00:00:00Z'}).status_code == 201
        assert api.delete('/api/v2/living-accounts/unused-wallet?preserveHistory=true').status_code == 200
        api.post('/api/v2/living-accounts/used-wallet/record-balance', json={'balance': '20'})
        history = data(api, '/living-snapshots')
        response = api.delete('/api/v2/living-accounts/used-wallet?preserveHistory=true')
        assert response.status_code == 422, response.text
        assert data(api, '/living-snapshots') == history
        assert [item['id'] for item in data(api, '/living-accounts')] == ['used-wallet']


def test_end_month_cannot_hide_later_recorded_observations(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        account = next(item for item in data(api, '/financial-accounts') if item['id'] == 'living')
        response = api.put('/api/v2/financial-accounts/living', json={**account, 'status': 'inactive', 'endMonth': '2026-07'})
        assert response.status_code == 422, response.text
        assert next(item for item in data(api, '/financial-accounts') if item['id'] == 'living') == account


def test_ending_a_nonzero_living_balance_is_not_a_silent_writeoff(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        before = data(api, '/reports/personal-balance-sheet?month=2026-08')['currencies']
        account = next(item for item in data(api, '/financial-accounts') if item['id'] == 'living')
        assert api.put('/api/v2/financial-accounts/living', json={**account, 'status': 'inactive', 'endMonth': '2026-08'}).status_code == 200
        assert data(api, '/reports/personal-balance-sheet?month=2026-08')['currencies'] == before
        report = data(api, '/reports/personal-balance-sheet?month=2026-09')
        assert 'ENDED_ACCOUNT_UNSETTLED' in {item['code'] for item in report['issues']}
        assert report['currencies'][0]['totals']['personalNetWorth'] is None


def test_safe_legacy_delete_retains_nonzero_initial_balance(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        assert api.post('/api/v2/living-accounts', json={'id': 'initial', 'name': 'Synthetic initial balance',
                       'commodityCode': 'CNY', 'balance': '10', 'updatedAt': '2026-08-01T00:00:00Z'}).status_code == 201
        response = api.delete('/api/v2/living-accounts/initial?preserveHistory=true')
        assert response.status_code == 422, response.text
        assert data(api, '/living-accounts')[0]['balance'] == '10'


def test_ledger_delete_cannot_bypass_owner_only_monthly_account_contract(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        assert api.put('/api/v2/finance-parties/owner', json={'id': 'owner', 'name': 'Synthetic owner'}).status_code == 200
        assert api.post('/api/v2/financial-accounts', json={'id': 'monthly', 'code': 'monthly', 'name': 'Synthetic monthly',
                       'type': 'asset', 'allowedCommodityCodes': ['CNY'], 'segment': 'living',
                       'balanceSource': 'monthly_snapshot', 'ownerPartyId': 'owner'}).status_code == 201
        workspace_id = api.prefix.rsplit('/', 1)[1]
        token = api.post('/api/v3/access-tokens', json={'name': 'Synthetic ledger writer', 'workspaceIds': [workspace_id], 'scopes': ['ledger:write']}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        assert api.delete('/api/v2/accounts/monthly', headers=headers).status_code == 404
        assert api.delete('/api/v2/financial-accounts/monthly', headers=headers).status_code == 403
        assert api.delete('/api/v2/financial-accounts/monthly').status_code == 200


@pytest.mark.parametrize('reference', ['draft', 'recurring', 'posted'])
def test_account_delete_preserves_drafts_recurring_templates_and_posted_facts(tmp_path, reference):
    with client(tmp_path) as api:
        seed(api)
        draft = opening_draft('referenced')
        draft['description'] = 'An unrelated cash-usd mention is not an account reference'
        if reference == 'posted':
            create_and_post(api, draft)
        elif reference == 'recurring':
            assert api.post('/api/v2/recurring-entry-rules', json={'id': 'rule', 'name': 'Synthetic disabled template',
                            'enabled': False, 'dayOfMonth': 1, 'startDate': '2026-08-01', 'template': draft}).status_code == 201
        else:
            assert api.post('/api/v2/journal-entry-drafts', json=draft).status_code == 201
        before = api.get('/api/v2/vault-backup').json()['data']['sha256']
        assert api.delete('/api/v2/financial-accounts/cash-cny').status_code == 422
        assert api.get('/api/v2/vault-backup').json()['data']['sha256'] == before
        assert api.delete('/api/v2/financial-accounts/cash-usd').status_code == 200
