"""FC-owned financial item catalog and safe projections, not a generic DB export."""
from hashlib import sha256
import json

from finance_core.contracts_v3 import ReaderGrant
from finance_core.personal_finance_snapshot import PersonalFinanceSnapshot, dump
from finance_core.schema_migration import schema_version
from finance_core.debt_repayments import records as debt_records


ACCOUNT_FIELDS = 'id code name type subtype allowedCommodityCodes status segment balanceSource classificationConfirmed startMonth endMonth'
OBSERVATION_FIELDS = 'id subjectId month observedDate kind currency amount incoming outgoing fees inTransit confirmed supersedes recordedAt'
POSTING_FIELDS = 'id accountId side units commodityCode valuationRate valuationAmount rateType cashFlowCategory lotAction lotId lotAllocations'
DEBT_FIELDS = 'id accountId currency asOf balance payments status revision supersedes'


def select(value, fields):
    return {key: value[key] for key in fields.split() if key in value}


REPORTS = {'monthly-review': 'Three completed months · Journal',
           'month-to-date': 'Month to date · Journal',
           'economic-evidence': 'Whole-Vault cash, debt and planned obligations'}


def item_key(kind, identity):
    return kind + ':' + sha256((kind + '\0' + identity).encode('utf-8')).hexdigest()[:32]


def catalog(connection, grant):
    if schema_version(connection) != 3:
        raise ValueError('Financial read setup requires ledger schema 3; no automatic migration is performed.')
    snapshot = PersonalFinanceSnapshot(connection)
    items = [{'id': item_key('account', account['id']), 'label': account['name'],
              'kind': 'account', 'segment': account['segment']} for account in snapshot.accounts()]
    for kind, values, segment in [('asset', snapshot.assets(), 'living'),
        ('arrangement', snapshot.arrangements(), 'investment')]:
        items.extend({'id': item_key(kind, value['id']), 'label': value.get('name') or
            f"Agreement · {value['currency']} · v{value['version']} · {value['id']}", 'kind': kind, 'segment': segment} for value in values)
    # These are explicitly the Living cash-flow plans, not inferred debt maturities.
    from finance_core.ledger_repository import LedgerRepository
    items.extend({'id': item_key('plan', plan.id), 'label': plan.name, 'kind': 'plan', 'segment': 'living'}
                 for plan in LedgerRepository(connection).list_monthly_plans())
    items.extend({'id': item_key('transfer', currency), 'label': 'Living transfer totals · ' + currency,
                  'kind': 'transfer', 'segment': 'living'} for currency in
                 sorted({value['currency'] for value in snapshot.observations() if value['kind'] == 'transfer'}))
    items.extend({'id': 'report:' + name, 'label': label, 'kind': 'report',
                  'segment': None if name == 'economic-evidence' else 'investment'} for name, label in REPORTS.items())
    grant = ReaderGrant.model_validate(grant).model_dump(by_alias=True)
    if grant['mode'] in {'living', 'investment'}:
        items = [item for item in items if item['segment'] == grant['mode']]
    elif grant['mode'] == 'selected':
        allowed = set(grant['itemIds'])
        items = [item for item in items if item['id'] in allowed]
    if len(items) > 500 or len(json.dumps(items, ensure_ascii=False).encode()) > 60 * 1024:
        raise ValueError('The financial item catalog exceeds its safe display capacity; choose a narrower read grant.')
    return {'schemaVersion': 1, 'readGrant': grant, 'items': sorted(items, key=lambda item: (item['label'].casefold(), item['id']))}


def permits_path(grant, suffix, method):
    if method != 'GET':
        return False
    if suffix == '/reader/catalog' or suffix.startswith('/reader/items/'):
        return True  # Item membership is revalidated inside the read transaction.
    for name in REPORTS:
        if suffix == '/reports/' + name:
            return (grant['mode'] == 'all' or (grant['mode'] == 'investment' and name != 'economic-evidence')
                    or (grant['mode'] == 'selected' and 'report:' + name in grant['itemIds']))
    return False


def item_evidence(ledger, grant, item_id):
    connection = ledger.connection
    connection.execute('SAVEPOINT financial_reader')
    try:
        item = next((value for value in catalog(connection, grant)['items'] if value['id'] == item_id and value['kind'] != 'report'), None)
        if item is None:
            raise PermissionError('The financial item is outside this read grant or no longer available.')
        kind = item['kind']
        snapshot = PersonalFinanceSnapshot(connection)
        def chosen(values):
            return next(value for value in values if item_key(kind, value['id']) == item_id)
        if kind == 'account':
            account = chosen(snapshot.accounts())
            identity = account['id']
            postings = []
            # Never expose the other side of a cross-account entry, its notes or description.
            for entry in ledger.list_entries() if account['balanceSource'] == 'ledger' else []:
                for posting in entry['postings']:
                    if posting['accountId'] == identity:
                        postings.append({**select(posting, POSTING_FIELDS), 'entryId': entry['id'],
                            'date': entry['date'], 'balancingCommodityCode': entry['balancingCommodityCode'],
                            'isReversal': bool(entry.get('reversalOf'))})
            content = {'account': select(account, ACCOUNT_FIELDS),
                'observations': [select(value, OBSERVATION_FIELDS) for value in snapshot.observations() if value['subjectId'] == identity and value['kind'] == 'balance'],
                'postings': postings,
                'repayments': [select(value, DEBT_FIELDS) for value in debt_records(connection) if value['accountId'] == identity]}
        elif kind == 'asset':
            asset = chosen(snapshot.assets())
            content = {'asset': select(asset, 'id name assetType currency purchasedDate purchaseCost ownershipShare linkedAccountId disposedMonth valuationMethod'),
                'observations': [select(value, OBSERVATION_FIELDS) for value in snapshot.observations() if value['subjectId'] == asset['id'] and value['kind'] == 'valuation']}
        elif kind == 'plan':
            plan = chosen([dump(value) for value in ledger.list_monthly_plans()])
            content = {'plan': select(plan, 'id name kind amount commodityCode category recurringMonthly dayOfMonth startDate repeatEveryMonths')}
        elif kind == 'arrangement':
            value = chosen(snapshot.arrangements())
            content = {'arrangement': select(value, 'id version currency fromMonth toMonth distributionEquityAccountId'),
                'claims': [select(row, 'accountId partyId kind') for row in value.get('claims', [])],
                'interestAgreements': [select(row, 'id principalAccountId payableAccountId expenseAccountId partyId monthlyAmount fromMonth toMonth') for row in value.get('interestAgreements', [])],
                'residualShares': [select(row, 'partyId share') for row in value.get('residualShares', [])]}
        else:
            content = {'observations': [select(value, OBSERVATION_FIELDS) for value in snapshot.observations()
                if value['kind'] == 'transfer' and item_key(kind, value['currency']) == item_id]}
        evidence = {'schemaVersion': 1, 'itemId': item_id, 'label': item['label'], 'kind': kind,
            'segment': item['segment'], 'content': content,
            'coverage': {'selectionOnly': True, 'externalCompleteness': 'unknown', 'financialAdviceReady': False}}
        evidence['revision'] = sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        return evidence
    finally:
        connection.execute('RELEASE financial_reader')
