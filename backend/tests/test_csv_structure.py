from test_v2 import client, seed
import csv
import io


def test_duplicate_csv_headers_cannot_silently_override_account_mapping(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        csv = ('entryId,date,description,balancingCommodityCode,postingId,accountId,accountId,side,units,commodityCode\n'
               'duplicate,2026-01-01,Synthetic,CNY,p1,unknown,cash-cny,debit,1.10,CNY\n'
               'duplicate,2026-01-01,Synthetic,CNY,p2,unknown,capital,credit,1.10,CNY\n')
        response = api.post('/api/v2/import/drafts.csv', content=csv, headers={'Content-Type': 'text/csv'})
        assert response.status_code == 422
        assert api.get('/api/v2/journal-entry-drafts').json()['data'] == []


def test_posted_csv_export_can_be_checked_and_imported_as_drafts(tmp_path):
    with client(tmp_path / 'source') as source, client(tmp_path / 'target') as target:
        seed(source)
        seed(target)
        draft = {'id': 'csv-roundtrip', 'date': '2026-01-01', 'description': 'Synthetic quoted, journal',
                 'balancingCommodityCode': 'CNY', 'payee': 'Synthetic counterparty', 'source': 'synthetic-roundtrip',
                 'reference': 'Synthetic-ref', 'tags': ['test', 'roundtrip'], 'postings': [
                     {'id': 'csv-roundtrip-d', 'accountId': 'cash-cny', 'side': 'debit', 'units': '1.10', 'commodityCode': 'CNY', 'memo': 'Synthetic parent context'},
                     {'id': 'csv-roundtrip-c', 'accountId': 'capital', 'side': 'credit', 'units': '1.10', 'commodityCode': 'CNY'}]}
        assert source.post('/api/v2/journal-entry-drafts', json=draft).status_code == 201
        assert source.post('/api/v2/journal-entry-drafts/csv-roundtrip/post').status_code == 200
        exported = source.get('/api/v2/export/journal-entries.csv')
        rows = list(csv.DictReader(io.StringIO(exported.text.lstrip('\ufeff'))))
        assert len(rows) == 2
        assert all(row['balancingCommodityCode'] == 'CNY' for row in rows)
        imported = target.post('/api/v2/import/drafts.csv', content=exported.content, headers={'Content-Type': 'text/csv'})
        assert imported.status_code == 201, imported.text
        assert imported.json()['imported'] == 1
        assert target.get('/api/v2/journal-entries').json()['data'] == []
        restored = target.get('/api/v2/journal-entry-drafts').json()['data'][0]['draft']
        assert restored['description'] == draft['description']
        assert all(restored[key] == draft[key] for key in ['payee', 'source', 'reference', 'tags'])
        assert restored['postings'][0]['memo'] == 'Synthetic parent context'
        assert [p['units'] for p in restored['postings']] == ['1.1', '1.1']


def test_bad_encoding_and_extra_csv_cells_are_structured_and_atomic(tmp_path):
    with client(tmp_path) as api:
        seed(api)
        header = b'entryId,date,description,balancingCommodityCode,postingId,accountId,side,units,commodityCode\n'
        for data in [b'\xff', header + b'x,2026-01-01,Synthetic,CNY,p,cash-cny,debit,1.10,CNY,extra', header + b'x,2026-01-01,"PRIVATE_SYNTHETIC_UNCLOSED']:
            response = api.post('/api/v2/import/drafts.csv', content=data, headers={'Content-Type': 'text/csv'})
            assert response.status_code == 422
            assert 'error' in response.json()
            assert 'PRIVATE_SYNTHETIC_UNCLOSED' not in response.text
        assert api.get('/api/v2/journal-entry-drafts').json()['data'] == []
