"""Opening stock and period activity through Workspace HTTP; no real finance data."""
import hashlib
import json
from datetime import date
import pytest

from test_personal_finance import data, seed_personal
from test_v2 import client, seed, opening_draft, create_and_post


def test_opening_cash_uses_an_explicit_equity_counterpart_and_not_period_cash_flow(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        response = api.post(api.prefix + '/opening-balance-drafts', json={
            'id': 'opening-new', 'date': '2026-08-01', 'balancingCommodityCode': 'CNY',
            'equityAccountId': 'capital', 'source': 'Synthetic opening statement',
            'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100', 'note': 'Before normal operations'}]})
        assert response.status_code == 201, response.text
        draft = response.json()['data']['draft']
        assert [(p['accountId'], p['side'], p['units']) for p in draft['postings']] == [
            ('cash-cny', 'debit', '100'), ('capital', 'credit', '100')]
        assert draft['date'] == '2026-08-01'
        assert draft['postings'][0]['memo'] == 'Before normal operations'
        assert api.post(api.prefix + '/journal-entry-drafts/opening-new/validate').json()['valid'] is True
        assert api.post(api.prefix + '/journal-entry-drafts/opening-new/post').json()['posted'] is True
        assert data(api, '/financial-statements')[0]['assets'] == '100'
        assert data(api, '/cash-flow') == [{'commodityCode': 'CNY', 'category': 'other', 'amount': '100'}]
        activity = data(api, '/reports/activity-cash-flow?month=2026-08')
        assert activity['activity'] == []
        assert activity['openingEffects'] == [{'commodityCode': 'CNY', 'category': 'other', 'amount': '100'}]


@pytest.mark.parametrize('correction', [True, False])
def test_later_reversal_cannot_reinitialize_an_earlier_opening_and_double_count_history(tmp_path, correction):
    with client(tmp_path) as api:
        seed(api)
        payload = {'id': 'baseline', 'date': '2026-08-01', 'balancingCommodityCode': 'CNY',
                   'equityAccountId': 'capital', 'source': 'Synthetic statement',
                   'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100'}]}
        assert api.post(api.prefix + '/opening-balance-drafts', json=payload).status_code == 201
        assert api.post(api.prefix + '/journal-entry-drafts/baseline/post').json()['posted']
        assert api.post(api.prefix + '/journal-entries/baseline/reverse').status_code == 201
        replacement = {**payload, 'id': 'replacement'}
        if correction:
            replacement['supersedes'] = 'baseline'
        response = api.post(api.prefix + '/opening-balance-drafts', json=replacement)
        assert response.status_code == 422, response.text
        assert len(data(api, '/journal-entries')) == 2


def test_ordinary_journal_cannot_add_a_fact_before_an_established_opening(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        payload = {'id': 'baseline', 'date': '2026-08-10', 'balancingCommodityCode': 'CNY',
                   'equityAccountId': 'capital', 'source': 'Synthetic statement',
                   'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100'}]}
        assert api.post(api.prefix + '/opening-balance-drafts', json=payload).status_code == 201
        assert api.post(api.prefix + '/journal-entry-drafts/baseline/post').json()['posted']
        earlier = {**opening_draft('backdated'), 'date': '2026-08-01'}
        assert api.post(api.prefix + '/journal-entry-drafts', json=earlier).status_code == 201
        validation = api.post(api.prefix + '/journal-entry-drafts/backdated/validate').json()
        assert validation['valid'] is False, validation
        assert api.post(api.prefix + '/journal-entry-drafts/backdated/post').status_code == 422
        assert len(data(api, '/journal-entries')) == 1


def test_generic_opening_draft_cannot_turn_currency_stock_into_a_security_lot(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        draft = {**opening_draft('currency-lot'), 'tags': ['fc:opening-balance:2026-08-17', 'fc:opening-equity:capital']}
        for posting in draft['postings']:
            posting['cashFlowCategory'] = 'other'
        draft['postings'][0].update(lotAction='acquire', lotId='fake-currency-lot', valuationRate='1', rateType='cost')
        assert api.post(api.prefix + '/journal-entry-drafts', json=draft).status_code == 201
        validation = api.post(api.prefix + '/journal-entry-drafts/currency-lot/validate').json()
        assert validation['valid'] is False, validation
        assert api.post(api.prefix + '/journal-entry-drafts/currency-lot/post').status_code == 422
        assert data(api, '/holdings') == []


def test_opening_draft_cannot_silently_drop_classification_during_journal_edit(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        response = api.post(api.prefix + '/opening-balance-drafts', json={
            'id': 'classified', 'date': '2026-08-01', 'balancingCommodityCode': 'CNY',
            'equityAccountId': 'capital', 'source': 'Synthetic statement',
            'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100'}]})
        original = response.json()['data']['draft']
        assert api.put(api.prefix + '/journal-entry-drafts/classified', json={**original, 'tags': []}).status_code == 422
        edited = {**original, 'description': 'Opening with explanatory detail'}
        assert api.put(api.prefix + '/journal-entry-drafts/classified', json=edited).status_code == 200
        assert api.post(api.prefix + '/journal-entry-drafts/classified/post').json()['posted']
        assert data(api, '/reports/activity-cash-flow?month=2026-08')['activity'] == []


def test_opening_equity_counterpart_is_retained_even_when_its_net_posting_is_zero(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        liability = {'id': 'loan', 'code': '2001', 'name': 'Synthetic loan', 'type': 'liability', 'allowedCommodityCodes': ['CNY']}
        assert api.post(api.prefix + '/accounts', json=liability).status_code == 201
        response = api.post(api.prefix + '/opening-balance-drafts', json={
            'id': 'zero-equity', 'date': '2026-08-01', 'balancingCommodityCode': 'CNY',
            'equityAccountId': 'capital', 'source': 'Synthetic loan statement', 'balances': [
                {'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100'},
                {'accountId': 'loan', 'commodityCode': 'CNY', 'amount': '100'}]})
        assert response.status_code == 201, response.text
        assert api.delete(api.prefix + '/accounts/capital').status_code == 422
        assert api.post(api.prefix + '/journal-entry-drafts/zero-equity/post').json()['posted']
        assert api.delete(api.prefix + '/accounts/capital').status_code == 422


@pytest.mark.parametrize('change', ['orphan', 'bad_date', 'currency_lot', 'valuation', 'nonfinite'])
def test_rehashed_backup_still_rejects_invalid_opening_classification(tmp_path, change):
    with client(tmp_path / 'source') as api:
        seed(api)
        request = {'id': 'baseline', 'date': '2026-08-01', 'balancingCommodityCode': 'CNY',
                   'equityAccountId': 'capital', 'source': 'Synthetic statement',
                   'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100'}]}
        assert api.post(api.prefix + '/opening-balance-drafts', json=request).status_code == 201
        assert api.post(api.prefix + '/journal-entry-drafts/baseline/post').json()['posted']
        backup = data(api, '/vault-backup')
    entry = backup['payload']['journal_entries_v2'][0]
    if change == 'orphan':
        entry['tags_json'] = json.dumps(['fc:opening-equity:capital'])
    elif change == 'bad_date':
        entry['date'] = 'not-a-date'
    elif change == 'currency_lot':
        backup['payload']['postings_v2'][0]['lot_json'] = json.dumps({'lotAction': 'acquire', 'lotId': 'fake'})
    else:
        backup['payload']['postings_v2'][0]['valuation_amount'] = '999' if change == 'valuation' else 'NaN'
    backup['sha256'] = hashlib.sha256(json.dumps(backup['payload'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    with client(tmp_path / 'target') as api:
        response = api.post(api.prefix + '/vault-backup/restore', json=backup)
        assert response.status_code == 422, response.text
        assert data(api, '/journal-entries') == []
        assert data(api, '/commodities') == []


def test_stock_remains_in_statements_but_period_income_and_cash_exclude_opening(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        response = api.post(api.prefix + '/opening-balance-drafts', json={
            'id': 'baseline', 'date': '2026-08-01', 'balancingCommodityCode': 'CNY',
            'equityAccountId': 'capital', 'source': 'Synthetic statement',
            'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100'}]})
        assert response.status_code == 201, response.text
        assert api.post(api.prefix + '/journal-entry-drafts/baseline/post').json()['posted']
        receipt = opening_draft('receipt')
        receipt['date'] = '2026-08-01'
        receipt['postings'][0].update(units='20', cashFlowCategory='income')
        receipt['postings'][1].update(accountId='gain', units='20', cashFlowCategory='income')
        create_and_post(api, receipt)
        statement = data(api, '/financial-statements')[0]
        assert (statement['assets'], statement['equity'], statement['income']) == ('120', '100', '20')
        old = data(api, '/reports/monthly-review?month=2026-08')['months'][-1]
        current = data(api, '/reports/monthly-activity-review?month=2026-08')
        assert old['currencies'][0]['cashInflow'] == '120'
        assert current['months'][-1]['currencies'][0]['cashInflow'] == '20'
        assert current['months'][-1]['currencies'][0]['income'] == '20'
        assert current['months'][-1]['postedEntryCount'] == 1
        assert current['openingEntryIds'] == ['baseline']
        assert current['revision'] == data(api, '/reports/monthly-activity-review?month=2026-08')['revision']
        reversal = api.post(api.prefix + '/journal-entries/baseline/reverse')
        assert reversal.status_code == 201
        today = date.today().strftime('%Y-%m')
        assert data(api, '/reports/activity-cash-flow?month=' + today)['activity'] == []
        assert data(api, '/reports/activity-cash-flow?month=' + today)['openingEffects'][0]['amount'] == '-100'


def test_opening_securities_use_explicit_cost_lots_not_market_quotes_and_backup_roundtrips(tmp_path):
    with client(tmp_path / 'source') as api:
        seed(api)
        request = {'id': 'opening-cost', 'date': '2026-08-01', 'balancingCommodityCode': 'CNY',
                   'equityAccountId': 'capital', 'source': 'Synthetic custody statement', 'balances': [
                       {'accountId': 'investment', 'commodityCode': 'DEMO', 'amount': '2', 'unitCost': '100', 'lotId': 'opening-lot', 'note': 'Original cost, not a market quote.'}]}
        assert api.post(api.prefix + '/opening-balance-drafts', json=request).status_code == 201
        assert api.post(api.prefix + '/journal-entry-drafts/opening-cost/post').json()['posted']
        assert api.post(api.prefix + '/price-quotes', json={
            'id': 'quote', 'commodityCode': 'DEMO', 'quoteCommodityCode': 'CNY', 'price': '130',
            'asOf': '2026-08-02T00:00:00Z', 'source': 'Synthetic market observation'}).status_code == 201
        holding = data(api, '/holdings')[0]
        assert holding['remainingUnits'] == '2' and holding['remainingCost'] == '200'
        assert holding['marketValue'] == '260'
        backup = data(api, '/vault-backup')
        assert 'Original cost, not a market quote.' in json.dumps(backup)
    with client(tmp_path / 'target') as api:
        assert api.post(api.prefix + '/vault-backup/restore', json=backup).status_code == 201
        assert data(api, '/holdings') == [holding]
        assert data(api, '/opening-balances')['entries'][0]['tags'] == ['fc:opening-balance:2026-08-01', 'fc:opening-equity:capital']
        assert data(api, '/reports/activity-cash-flow?month=2026-08')['activity'] == []


def test_living_opening_is_an_actual_date_record_and_never_a_journal_or_month_end_value(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        before = data(api, '/journal-entries')
        request = {'id': 'living-opening', 'subjectId': 'living', 'observedDate': '2026-09-12',
                   'currency': 'CNY', 'amount': '0', 'source': 'Synthetic actual-date statement', 'confirmed': True, 'note': 'An explicitly observed zero.'}
        assert api.post(api.prefix + '/opening-living-balances', json=request).status_code == 201
        assert data(api, '/journal-entries') == before
        assert data(api, '/balance-records')[0]['note'] == request['note']
        recorded = data(api, '/reports/living-recorded-balances?month=2026-09')['accounts']
        living = next(item for item in recorded if item['accountId'] == 'living')
        assert living['amount'] == '0' and living['observedDate'] == '2026-09-12'
        assert api.post(api.prefix + '/opening-living-balances', json={**request, 'id': 'later', 'observedDate': '2026-09-13'}).status_code == 422
        assert api.post(api.prefix + '/balance-records', json={**request, 'id': 'later', 'observedDate': '2026-09-13', 'amount': '25'}).status_code == 201
        missing = data(api, '/reports/living-recorded-balances?month=2026-10')['accounts']
        assert next(item for item in missing if item['accountId'] == 'living')['amount'] is None


def test_opening_confirmation_rejects_a_draft_changed_after_the_reviewed_version(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        request = {'id': 'reviewed', 'date': '2026-08-01', 'balancingCommodityCode': 'CNY',
                   'equityAccountId': 'capital', 'source': 'Synthetic statement',
                   'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100'}]}
        stored = api.post(api.prefix + '/opening-balance-drafts', json=request).json()['data']
        assert api.post(api.prefix + '/journal-entry-drafts/reviewed/validate').json()['valid']
        revised = stored['draft']
        for posting in revised['postings']:
            posting['units'] = '120'
        updated = api.put(api.prefix + '/journal-entry-drafts/reviewed', json=revised).json()['data']
        response = api.post(api.prefix + '/opening-balances/reviewed/post', json={
            'confirmed': True, 'expectedUpdatedAt': stored['updatedAt']})
        assert response.status_code == 422, response.text
        assert data(api, '/journal-entries') == []
        response = api.post(api.prefix + '/opening-balances/reviewed/post', json={
            'confirmed': True, 'expectedUpdatedAt': updated['updatedAt']})
        assert response.status_code == 200, response.text
        assert response.json()['data']['postings'][0]['units'] == '120'


def test_same_date_opening_correction_and_later_inactivation_restore_with_full_provenance(tmp_path):
    with client(tmp_path / 'source') as api:
        seed(api)
        request = {'id': 'original', 'date': date.today().isoformat(), 'balancingCommodityCode': 'CNY',
                   'equityAccountId': 'capital', 'source': 'Synthetic original source',
                   'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100'}]}
        original = api.post(api.prefix + '/opening-balance-drafts', json=request).json()['data']['draft']
        assert api.put(api.prefix + '/journal-entry-drafts/original', json={**original, 'tags': original['tags'] + ['synthetic-context']}).status_code == 200
        assert api.post(api.prefix + '/journal-entry-drafts/original/post').json()['posted']
        assert api.post(api.prefix + '/journal-entries/original/reverse').status_code == 201
        replacement = api.post(api.prefix + '/opening-balance-drafts', json={**request, 'id': 'replacement', 'supersedes': 'original',
                         'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '120'}]})
        assert replacement.status_code == 201, replacement.text
        assert api.post(api.prefix + '/journal-entry-drafts/replacement/post').json()['posted']
        account = next(item for item in data(api, '/accounts') if item['id'] == 'cash-cny')
        assert api.put(api.prefix + '/accounts/cash-cny', json={**account, 'status': 'inactive'}).status_code == 200
        commodity = data(api, '/commodities')[0]
        assert api.put(api.prefix + '/commodities/CNY', json={**commodity, 'status': 'inactive'}).status_code == 200
        backup = data(api, '/vault-backup')
    with client(tmp_path / 'target') as api:
        assert api.post(api.prefix + '/vault-backup/restore', json=backup).status_code == 201
        assert data(api, '/financial-statements')[0]['assets'] == '120'
        assert len(data(api, '/opening-balances')['entries']) == 3


def test_duplicate_drafts_recheck_opening_scope_at_post_and_new_routes_remain_owner_only(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        request = {'id': 'first', 'date': '2026-08-01', 'balancingCommodityCode': 'CNY',
                   'equityAccountId': 'capital', 'source': 'Synthetic statement',
                   'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100'}]}
        for identity in ('first', 'stale'):
            assert api.post(api.prefix + '/opening-balance-drafts', json={**request, 'id': identity}).status_code == 201
            assert api.post(api.prefix + '/journal-entry-drafts/' + identity + '/validate').json()['valid']
        assert api.post(api.prefix + '/journal-entry-drafts/first/post').json()['posted']
        assert api.post(api.prefix + '/journal-entry-drafts/stale/post').status_code == 422
        token = api.post('/api/v3/access-tokens', json={'name': 'Synthetic reader', 'workspaceIds': [api.prefix.rsplit('/', 1)[1]], 'scopes': ['ledger:read']}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        for path in ('/opening-balances', '/reports/activity-cash-flow?month=2026-08', '/reports/monthly-activity-review?month=2026-08'):
            assert api.get(api.prefix + path, headers=headers).status_code == 403
        assert api.post(api.prefix + '/opening-balance-drafts', json={**request, 'id': 'forbidden'}, headers=headers).status_code == 403
        workspace = api.post('/api/v3/workspaces', json={'displayName': 'Synthetic independent Vault', 'kind': 'sandbox'}).json()['data']['id']
        assert api.get('/api/v3/workspaces/' + workspace + '/opening-balances').json()['data'] == {'drafts': [], 'entries': []}


@pytest.mark.parametrize('change', ['zero', 'float', 'expense', 'fx', 'security_cost', 'future', 'equity_scope'])
def test_opening_intake_fails_closed_for_unsupported_or_ambiguous_stock(tmp_path, change):
    with client(tmp_path) as api:
        seed(api)
        request = {'id': 'invalid', 'date': '2026-08-01', 'balancingCommodityCode': 'CNY',
                   'equityAccountId': 'capital', 'source': 'Synthetic source',
                   'balances': [{'accountId': 'cash-cny', 'commodityCode': 'CNY', 'amount': '100'}]}
        row = request['balances'][0]
        if change == 'zero': row['amount'] = '0'
        if change == 'float': row['amount'] = 100.0
        if change == 'expense': row['accountId'] = 'gain'
        if change == 'fx': row.update(accountId='cash-usd', commodityCode='USD')
        if change == 'security_cost': row.update(accountId='investment', commodityCode='DEMO', lotId='uncosted-lot')
        if change == 'future': request['date'] = '2099-01-01'
        if change == 'equity_scope': request['equityAccountId'] = 'gain'
        response = api.post(api.prefix + '/opening-balance-drafts', json=request)
        assert response.status_code == 422, response.text
        assert data(api, '/journal-entry-drafts') == []
