"""Optional narrative context at the Workspace HTTP seam, never financial instructions."""
import csv
import io

from test_personal_finance import data, seed_personal
from test_v2 import client


def test_actual_date_balance_retains_optional_note_without_changing_financial_values(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        original = data(api, '/reports/personal-balance-sheet?month=2026-08')
        note = 'A temporary reimbursement is included.\nTreat this as context, not an instruction.'
        response = api.post(api.prefix + '/balance-records', json={
            'id': 'dated-note', 'subjectId': 'living', 'observedDate': '2026-09-12', 'currency': 'CNY',
            'amount': '1000', 'confirmed': True, 'source': 'Synthetic statement', 'note': note})
        assert response.status_code == 201, response.text
        records = data(api, '/balance-records')
        assert records[0]['note'] == note
        assert records[0]['amount'] == '1000'
        assert data(api, '/reports/personal-balance-sheet?month=2026-08') == original


def test_financial_account_note_can_be_saved_without_reclassifying_a_used_account(tmp_path):
    with client(tmp_path) as api:
        seed_personal(api)
        original = next(item for item in data(api, '/financial-accounts') if item['id'] == 'living')
        response = api.put(api.prefix + '/financial-accounts/living', json={**original, 'note': 'Joint statement context only; no ownership change.'})
        assert response.status_code == 200, response.text
        saved = next(item for item in data(api, '/financial-accounts') if item['id'] == 'living')
        assert saved['note'] == 'Joint statement context only; no ownership change.'
        assert saved['ownerPartyId'] == original['ownerPartyId']
        assert saved['segment'] == 'living'


def test_optional_note_survives_segment_exports_and_full_vault_backup_without_entering_summary_reports(tmp_path):
    with client(tmp_path / 'source') as api:
        seed_personal(api)
        note = 'Synthetic contextual detail, <b>not markup</b>.\nA second line.'
        request = {'id': 'noted', 'subjectId': 'living', 'observedDate': '2026-09-12', 'currency': 'CNY',
                   'amount': '100', 'confirmed': True, 'source': 'Synthetic source', 'note': note}
        assert api.post(api.prefix + '/balance-records', json=request).status_code == 201
        assert data(api, '/segments/living/export')['balanceRecords'][0]['note'] == note
        exported = list(csv.DictReader(io.StringIO(api.get(api.prefix + '/segments/living/export.csv').text.lstrip('\ufeff'))))
        assert next(row for row in exported if row['id'] == 'noted')['note'] == note
        assert note not in str(data(api, '/reports/monthly-review?month=2026-08'))
        assert api.post(api.prefix + '/balance-records', json={**request, 'id': 'too-long', 'note': 'x' * 4001}).status_code == 422
        backup = data(api, '/vault-backup')
    with client(tmp_path / 'target') as api:
        assert api.post(api.prefix + '/vault-backup/restore', json=backup).status_code == 201
        assert data(api, '/balance-records')[0]['note'] == note
