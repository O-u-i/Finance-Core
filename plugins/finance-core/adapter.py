"""Optional FRAG protocol 2 adapter for Finance Core API 3.10.0.

The legacy read hook remains available. FRAG loads this module; FC does not.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Query

PREFIX = "/api/plugins/finance-core"
API_VERSION = "3.10.0"
RECORD_ID = re.compile(r"^(?:(entry|draft):([A-Za-z0-9][A-Za-z0-9._-]{0,127})|monthly-review:([0-9]{4}-(?:0[1-9]|1[0-2]))|economic-evidence:([0-9]{4}-[0-9]{2}-[0-9]{2}):([0-9]{4}-[0-9]{2}-[0-9]{2})|month-to-date:([0-9]{4}-[0-9]{2}-[0-9]{2}))$")
WORKSPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_RECORDS = 10
FINANCIAL_ITEM = re.compile(r'^(?:account|asset|plan|arrangement|transfer):[a-f0-9]{32}$')
REPORT_ITEM = re.compile(r'^report:(?:monthly-review|month-to-date|economic-evidence)$')
_configuration = None


def _environment():
    return _configuration if _configuration is not None else os.environ


def configure_connection(values):
    """Backend-only configuration for one reader instance; no process-env mutation."""
    global _configuration
    keys = {'FINANCE_CORE_PLUGIN_API_URL', 'FINANCE_CORE_PLUGIN_UI_URL',
            'FINANCE_CORE_PLUGIN_READ_TOKEN', 'FINANCE_CORE_PLUGIN_RECORDS_JSON'}
    if not isinstance(values, dict) or set(values) != keys or any(not isinstance(v, str) for v in values.values()):
        raise ValueError('Invalid private connection settings.')
    previous, _configuration = _configuration, dict(values)
    try:
        _settings()
    except (FcUnavailable, ValueError) as error:
        _configuration = previous
        raise ValueError('Invalid private connection settings.') from error


class FcUnavailable(Exception):
    pass


class FcIncompatible(Exception):
    pass


def _valid_record_id(value: object) -> bool:
    if isinstance(value, str) and value.startswith('finance-item:'):
        return FINANCIAL_ITEM.fullmatch(value[len('finance-item:'):]) is not None
    if not isinstance(value, str) or not (match := RECORD_ID.fullmatch(value)):
        return False
    if match[4] is not None:
        try:
            return 0 < (date.fromisoformat(match[5]) - date.fromisoformat(match[4])).days <= 366
        except ValueError:
            return False
    if match[6] is not None:
        try:
            return date.fromisoformat(match[6]) <= datetime.now(timezone(timedelta(hours=8))).date()
        except ValueError:
            return False
    return True


def _loopback_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid_port = parsed.port is not None
    except ValueError as error:
        raise FcUnavailable("Finance Core configuration is unavailable.") from error
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment or not valid_port):
        raise FcUnavailable("Finance Core configuration is unavailable.")
    return value.rstrip("/")


def _settings() -> tuple[str, str, str, dict[str, list[str]]]:
    token = _environment().get("FINANCE_CORE_PLUGIN_READ_TOKEN", "")
    if not token or any(character.isspace() for character in token):
        raise FcUnavailable("Finance Core is not configured.")
    base = _loopback_url(_environment().get("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:8788"))
    ui_url = _loopback_url(_environment().get("FINANCE_CORE_PLUGIN_UI_URL", "http://127.0.0.1:5174"))
    try:
        selected = json.loads(_environment().get("FINANCE_CORE_PLUGIN_RECORDS_JSON", "{}"))
    except ValueError as error:
        raise FcUnavailable("Finance Core selection configuration is invalid.") from error
    if not isinstance(selected, dict) or len(selected) > MAX_RECORDS:
        raise FcUnavailable("Finance Core selection configuration is invalid.")
    total = 0
    for workspace_id, ids in selected.items():
        if (not isinstance(workspace_id, str) or not WORKSPACE_ID.fullmatch(workspace_id)
                or not isinstance(ids, list)):
            raise FcUnavailable("Finance Core selection configuration is invalid.")
        if len(ids) != len(set(item for item in ids if isinstance(item, str))):
            raise FcUnavailable("Finance Core selection configuration is invalid.")
        total += len(ids)
        if any(not _valid_record_id(item) for item in ids):
            raise FcUnavailable("Finance Core selection configuration is invalid.")
    if total > MAX_RECORDS:
        raise FcUnavailable("Finance Core selection configuration exceeds ten records.")
    return base, token, ui_url, selected


def _get(client: httpx.Client, path: str) -> dict:
    try:
        response = client.get(path)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise FcUnavailable("Finance Core is unavailable or denied the read request.") from error
    if not isinstance(payload, dict):
        raise FcUnavailable("Finance Core returned an invalid response.")
    return payload


def _client(base: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=base, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=3.0, follow_redirects=False, trust_env=False,
    )


def _check_health(client: httpx.Client) -> None:
    health = _get(client, "/api/v3/health")
    if (health.get("status") != "ok" or health.get("service") != "finance-core"
            or health.get("apiVersion") != API_VERSION):
        raise FcIncompatible("Finance Core API 3.10.0 is required.")


def _workspaces(client: httpx.Client) -> dict[str, dict]:
    payload = _get(client, "/api/v3/workspaces")
    values = payload.get("data")
    if not isinstance(values, list):
        raise FcUnavailable("Finance Core returned an invalid Workspace list.")
    return {item["id"]: item for item in values if isinstance(item, dict)
            and isinstance(item.get("id"), str) and item.get("status") == "active"}


def _monthly_report(data: object, month: str) -> dict:
    """Validate the summary-only wire shape without importing the FC runtime."""
    def shape(value: object, fields: str) -> None:
        if not isinstance(value, dict) or set(value) != set(fields.split()):
            raise FcUnavailable("Finance Core returned an invalid monthly summary.")

    def require(condition: bool) -> None:
        if not condition:
            raise FcUnavailable("Finance Core returned an invalid monthly summary.")

    shape(data, "schemaVersion calculationVersion month windowStart windowEndExclusive status revision months coverage")
    year, number = map(int, month.split("-"))
    ordinal = year * 12 + number - 1
    require(year >= 1 and ordinal >= 14 and ordinal < 9999 * 12 + 11)
    periods = [f"{value // 12:04d}-{value % 12 + 1:02d}" for value in range(ordinal - 2, ordinal + 1)]
    require(type(data["schemaVersion"]) is int and data["schemaVersion"] == 1
        and data["calculationVersion"] == "monthly-review-v1" and data["month"] == month
        and data["windowStart"] == periods[0] + "-01"
        and data["windowEndExclusive"] == f"{(ordinal + 1) // 12:04d}-{(ordinal + 1) % 12 + 1:02d}-01"
        and isinstance(data["revision"], str) and re.fullmatch(r"[a-f0-9]{64}", data["revision"]) is not None)
    coverage = data["coverage"]
    shape(coverage, "ledgerCalculation externalCompleteness accountClassification invalidDateEntryCount")
    require(coverage["externalCompleteness"] == "unknown"
        and coverage["accountClassification"] == "current-account-definitions"
        and type(coverage["invalidDateEntryCount"]) is int and coverage["invalidDateEntryCount"] >= 0
        and isinstance(data["months"], list))
    if data["status"] == "blocked":
        require(data["months"] == [] and coverage["ledgerCalculation"] == "blocked" and coverage["invalidDateEntryCount"] > 0)
        return data
    require(data["status"] == "ready" and coverage["ledgerCalculation"] == "complete"
        and coverage["invalidDateEntryCount"] == 0 and len(data["months"]) == 3)
    amounts = "cashInflow cashOutflow cashNet income expenses netIncome cashAdjustment incomeAdjustment expenseAdjustment".split()
    changes = "cashNetChange incomeChange expensesChange".split()
    previous_codes = None
    for index, period in enumerate(data["months"]):
        shape(period, "month postedEntryCount reversalEntryCount otherCategoryPostingCount currencies")
        require(period["month"] == periods[index] and isinstance(period["currencies"], list))
        for key in ("postedEntryCount", "reversalEntryCount", "otherCategoryPostingCount"):
            require(type(period[key]) is int and period[key] >= 0)
        require(period["reversalEntryCount"] <= period["postedEntryCount"])
        codes = []
        for currency in period["currencies"]:
            shape(currency, "commodityCode " + " ".join(amounts + changes))
            code = currency["commodityCode"]
            require(isinstance(code, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,23}", code) is not None)
            codes.append(code)
            for key in amounts + changes:
                value = currency[key]
                if key in changes and index == 0:
                    require(value is None)
                else:
                    require(isinstance(value, str) and re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", value) is not None)
            require(not currency["cashInflow"].startswith("-") and not currency["cashOutflow"].startswith("-"))
        require(codes == sorted(set(codes)) and (previous_codes is None or codes == previous_codes))
        previous_codes = codes
    return data


def _month_to_date_report(data: object, as_of: str) -> dict:
    """Validate a whole provisional summary; never accept details or fabricate history."""
    def require(condition):
        if not condition:
            raise FcUnavailable('Finance Core returned an invalid month-to-date summary.')
    def shape(value, fields):
        require(isinstance(value, dict) and set(value) == set(fields.split()))
    shape(data, 'schemaVersion calculationVersion month asOf windowStart windowEndExclusive periodStatus status revision period coverage')
    require(type(data['schemaVersion']) is int and data['schemaVersion'] == 1
        and data['calculationVersion'] == 'month-to-date-v1' and data['asOf'] == as_of
        and data['month'] == as_of[:7] and data['windowStart'] == as_of[:7] + '-01'
        and data['windowEndExclusive'] == (date.fromisoformat(as_of) + timedelta(days=1)).isoformat()
        and data['periodStatus'] == 'partial' and isinstance(data['revision'], str)
        and re.fullmatch(r'[a-f0-9]{64}', data['revision']) is not None)
    coverage = data['coverage']
    shape(coverage, 'ledgerCalculation externalCompleteness accountClassification invalidDateEntryCount activityBasis unrecordedDays')
    require(coverage['externalCompleteness'] == coverage['unrecordedDays'] == 'unknown'
        and coverage['accountClassification'] == 'current-account-definitions'
        and coverage['activityBasis'] == 'posted-journal-only'
        and type(coverage['invalidDateEntryCount']) is int and coverage['invalidDateEntryCount'] >= 0)
    if data['status'] == 'blocked':
        require(data['period'] is None and coverage['ledgerCalculation'] == 'blocked' and coverage['invalidDateEntryCount'] > 0)
        return data
    require(data['status'] == 'ready' and coverage['ledgerCalculation'] == 'complete' and coverage['invalidDateEntryCount'] == 0)
    period = data['period']
    shape(period, 'month postedEntryCount reversalEntryCount otherCategoryPostingCount currencies')
    require(period['month'] == as_of[:7] and isinstance(period['currencies'], list))
    for key in ('postedEntryCount', 'reversalEntryCount', 'otherCategoryPostingCount'):
        require(type(period[key]) is int and period[key] >= 0)
    require(period['reversalEntryCount'] <= period['postedEntryCount'])
    amounts = 'cashInflow cashOutflow cashNet income expenses netIncome cashAdjustment incomeAdjustment expenseAdjustment'.split()
    changes = 'cashNetChange incomeChange expensesChange'.split()
    codes = []
    for currency in period['currencies']:
        shape(currency, 'commodityCode ' + ' '.join(amounts + changes))
        code = currency['commodityCode']
        require(isinstance(code, str) and re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,23}', code) is not None)
        codes.append(code)
        for key in amounts:
            require(isinstance(currency[key], str) and re.fullmatch(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?', currency[key]) is not None)
        require(not currency['cashInflow'].startswith('-') and not currency['cashOutflow'].startswith('-'))
        require(all(currency[key] is None for key in changes))
    require(codes == sorted(set(codes)))
    return data


def _economic_report(data: object, as_of: str, through: str) -> dict:
    """Summary-only wire validation, never financial recomputation or owner reads."""
    def require(condition):
        if not condition:
            raise FcUnavailable('Finance Core returned an invalid economic summary.')
    def shape(value, fields):
        require(isinstance(value, dict) and set(value) == set(fields.split()))
    def day(value):
        try:
            return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    def amount(value):
        return isinstance(value, str) and len(value) <= 128 and re.fullmatch(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?', value) is not None
    def currency(value):
        return isinstance(value, str) and re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,23}', value) is not None
    shape(data, 'schemaVersion calculationVersion asOf through revision balanceBasis planBasis balances plannedOutflows debtBasis debtRepayments debtOutsideHorizon coverage missingFacts')
    require(type(data['schemaVersion']) is int and data['schemaVersion'] == 1
            and data['calculationVersion'] == 'economic-evidence-v1' and data['asOf'] == as_of and data['through'] == through
            and isinstance(data['revision'], str) and re.fullmatch(r'[a-f0-9]{64}', data['revision']) is not None
            and data['balanceBasis'] == 'gross-registered-accounts' and data['planBasis'] == 'planned-only-not-contractual-maturity'
            and data['debtBasis'] == 'confirmed-current-balance-only-future-charges-unknown')
    coverage = data['coverage']
    shape(coverage, 'cashStocks liabilityBalances datedObligations externalCompleteness currenciesCombined personalAvailabilityAssessed')
    require(all(type(coverage[key]) is bool for key in ('cashStocks','liabilityBalances','datedObligations'))
            and coverage['externalCompleteness'] == 'unknown' and coverage['currenciesCombined'] is False
            and coverage['personalAvailabilityAssessed'] is False)
    require(data['missingFacts'] == [fact for fact, key in [('cash_stocks','cashStocks'), ('liability_balances','liabilityBalances'), ('dated_obligations','datedObligations')] if not coverage[key]])
    require(isinstance(data['balances'], list))
    groups = []
    for value in data['balances']:
        shape(value, 'segment currency cashBalance liabilityBalance observedDates')
        require(isinstance(value['segment'], str) and value['segment'] in {'investment','living'} and currency(value['currency'])
                and all(value[key] is None or amount(value[key]) for key in ('cashBalance','liabilityBalance'))
                and isinstance(value['observedDates'], list)
                and all(day(item) and item <= as_of for item in value['observedDates']))
        require(value['observedDates'] == sorted(set(value['observedDates'])))
        groups.append((value['segment'], value['currency']))
    require(groups == sorted(set(groups)))
    for key in ('plannedOutflows', 'debtRepayments', 'debtOutsideHorizon'):
        require(isinstance(data[key], list))
        groups = []
        for value in data[key]:
            dated = key != 'debtOutsideHorizon'
            shape(value, ('dueDate ' if dated else '') + 'currency amount count')
            require(currency(value['currency']) and amount(value['amount']) and not value['amount'].startswith('-')
                    and type(value['count']) is int and value['count'] >= 1)
            if dated:
                require(day(value['dueDate']) and value['dueDate'] <= through
                        and (key != 'plannedOutflows' or value['dueDate'] > as_of))
            groups.append((value['dueDate'], value['currency']) if dated else value['currency'])
        require(groups == sorted(set(groups)))
    return data


def _read_grant(value):
    if (not isinstance(value, dict) or set(value) != {'mode', 'itemIds'}
            or value['mode'] not in {'all', 'living', 'investment', 'selected'}
            or not isinstance(value['itemIds'], list) or len(value['itemIds']) > 500
            or any(not isinstance(item, str) or not (FINANCIAL_ITEM.fullmatch(item) or REPORT_ITEM.fullmatch(item)) for item in value['itemIds'])
            or len(set(value['itemIds'])) != len(value['itemIds'])
            or (value['mode'] == 'selected') != bool(value['itemIds'])):
        raise FcUnavailable('Finance Core returned an invalid financial read grant.')
    return value


def _reader_catalog(client, workspace_id):
    payload = _get(client, f"/api/v3/workspaces/{quote(workspace_id, safe='')}/reader/catalog")
    if payload.get('workspaceId') != workspace_id or payload.get('readOnly') is not True:
        raise FcUnavailable('Finance Core returned a mismatched Workspace response.')
    data = payload.get('data')
    if not isinstance(data, dict) or set(data) != {'schemaVersion', 'readGrant', 'items'} or type(data['schemaVersion']) is not int or data['schemaVersion'] != 1:
        raise FcUnavailable('Finance Core returned an invalid catalog.')
    grant = _read_grant(data['readGrant'])
    items = data['items']
    if not isinstance(items, list) or len(items) > 500:
        raise FcUnavailable('Finance Core returned an invalid catalog.')
    ids = []
    for item in items:
        if (not isinstance(item, dict) or set(item) != {'id', 'label', 'kind', 'segment'}
                or not isinstance(item['id'], str) or not (FINANCIAL_ITEM.fullmatch(item['id']) or REPORT_ITEM.fullmatch(item['id']))
                or item['kind'] != item['id'].split(':')[0]
                or not isinstance(item['label'], str) or not 1 <= len(item['label']) <= 500
                or item['segment'] not in {'living', 'investment', None}
                or (grant['mode'] in {'living', 'investment'} and item['segment'] != grant['mode'])
                or (grant['mode'] == 'selected' and item['id'] not in grant['itemIds'])):
            raise FcUnavailable('Finance Core returned an invalid catalog item.')
        ids.append(item['id'])
    if len(set(ids)) != len(ids):
        raise FcUnavailable('Finance Core returned duplicate catalog items.')
    return data


def connection_catalog():
    """Management-only names and permission metadata; never prefetch financial facts."""
    base, token, _ui, selected = _settings()
    if len(selected) != 1:
        raise FcUnavailable('Use a single-Vault connection created in Finance Core Settings.')
    wid = next(iter(selected))
    with _client(base, token) as client:
        _check_health(client)
        identity = _get(client, '/api/v3/access-token-self').get('data')
        if (not isinstance(identity, dict) or identity.get('actorKind') != 'token' or identity.get('status') != 'active'
                or identity.get('workspaceIds') != [wid] or identity.get('scopes') != ['ledger:read']):
            raise FcUnavailable('Use a dedicated read-only financial connection from Finance Core Settings.')
        grant = _read_grant(identity.get('readGrant'))
        workspace = _workspaces(client).get(wid)
        if not workspace or workspace.get('kind') not in {'personal', 'sandbox'}:
            raise FcUnavailable('The configured Vault is unavailable.')
        data = _reader_catalog(client, wid)
        if data['readGrant'] != grant:
            raise FcUnavailable('Finance Core permissions changed during connection.')
    return {'schemaVersion': 1, 'workspace': {'id': wid, 'label': workspace['displayName'], 'kind': workspace['kind']},
        'readGrant': grant, 'items': data['items'], 'selectedRecordIds': selected[wid]}


def _financial_item(data, item_id):
    def require(value):
        if not value:
            raise FcUnavailable('Finance Core returned an invalid financial item.')
    def shape(value, fields):
        require(isinstance(value, dict) and set(value) == set(fields.split()))
    def row(value, fields, required='id'):
        require(isinstance(value, dict) and set(value).issubset(fields.split()) and set(required.split()).issubset(value))
        for key, v in value.items():
            if key in {'classificationConfirmed', 'confirmed', 'isReversal', 'recurringMonthly'}:
                require(type(v) is bool)
            elif key in {'version', 'revision', 'dayOfMonth', 'repeatEveryMonths'}:
                require(type(v) is int)
            elif key in {'allowedCommodityCodes', 'lotAllocations', 'payments'}:
                require(isinstance(v, list))
                if key == 'allowedCommodityCodes': require(all(isinstance(code, str) and re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,23}', code) for code in v))
            else:
                require(v is None or isinstance(v, str))
        require(all(isinstance(value[k], str) and value[k] for k in required.split()))
    def rows(values, fields, required='id'):
        require(isinstance(values, list))
        for value in values:
            row(value, fields, required)
    shape(data, 'schemaVersion itemId label kind segment revision content coverage')
    require(type(data['schemaVersion']) is int and data['schemaVersion'] == 1 and data['itemId'] == item_id
        and data['kind'] == item_id.split(':')[0] and data['segment'] in {'living', 'investment'}
        and isinstance(data['label'], str) and 1 <= len(data['label']) <= 500
        and isinstance(data['revision'], str) and re.fullmatch('[a-f0-9]{64}', data['revision']) is not None)
    require(data['coverage'] == {'selectionOnly': True, 'externalCompleteness': 'unknown', 'financialAdviceReady': False}
        and type(data['coverage'].get('selectionOnly')) is bool and type(data['coverage'].get('financialAdviceReady')) is bool)
    c, kind = data['content'], data['kind']
    observation = 'id subjectId month observedDate kind currency amount incoming outgoing fees inTransit confirmed supersedes recordedAt'
    if kind == 'account':
        shape(c, 'account observations postings repayments')
        row(c['account'], 'id code name type subtype allowedCommodityCodes status segment balanceSource classificationConfirmed startMonth endMonth')
        rows(c['observations'], observation)
        rows(c['postings'], 'id accountId side units commodityCode valuationRate valuationAmount rateType cashFlowCategory lotAction lotId lotAllocations entryId date balancingCommodityCode isReversal')
        for p in c['postings']:
            if 'lotAllocations' in p:
                rows(p['lotAllocations'], 'lotId units', 'lotId units')
        rows(c['repayments'], 'id accountId currency asOf balance payments status revision supersedes')
        for r in c['repayments']:
            rows(r['payments'], 'dueDate amount', 'dueDate amount')
    elif kind == 'asset':
        shape(c, 'asset observations')
        row(c['asset'], 'id name assetType currency purchasedDate purchaseCost ownershipShare linkedAccountId disposedMonth valuationMethod')
        rows(c['observations'], observation)
    elif kind == 'plan':
        shape(c, 'plan')
        row(c['plan'], 'id name kind amount commodityCode category recurringMonthly dayOfMonth startDate repeatEveryMonths')
    elif kind == 'arrangement':
        shape(c, 'arrangement claims interestAgreements residualShares')
        row(c['arrangement'], 'id version currency fromMonth toMonth distributionEquityAccountId')
        rows(c['claims'], 'accountId partyId kind', 'accountId partyId kind')
        rows(c['interestAgreements'], 'id principalAccountId payableAccountId expenseAccountId partyId monthlyAmount fromMonth toMonth')
        rows(c['residualShares'], 'partyId share', 'partyId share')
    elif kind == 'transfer':
        shape(c, 'observations'); rows(c['observations'], observation)
    else:
        require(False)
    if kind == 'transfer':
        require(all('transfer:' + hashlib.sha256(('transfer\0' + v['currency']).encode()).hexdigest()[:32] == item_id for v in c['observations']))
    else:
        entity = c['account' if kind == 'account' else kind]
        require(kind + ':' + hashlib.sha256((kind + '\0' + entity['id']).encode()).hexdigest()[:32] == item_id)
        if kind == 'account':
            require(entity['segment'] == data['segment'])
            require(all(v.get('subjectId') == entity['id'] for v in c['observations']))
            require(all(v.get('accountId') == entity['id'] for v in c['postings'] + c['repayments']))
        elif kind == 'asset':
            require(all(v.get('subjectId') == entity['id'] for v in c['observations']))
    # No untyped nested objects, free-form source fields or floats can cross this contract.
    def walk(value, key=''):
        if key in {'amount', 'units', 'valuationRate', 'valuationAmount', 'fees', 'inTransit', 'incoming', 'outgoing',
                   'balance', 'purchaseCost', 'ownershipShare', 'monthlyAmount', 'share'} and value is not None:
            require(isinstance(value, str) and re.fullmatch(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?', value) is not None)
        if isinstance(value, dict):
            for k, v in value.items(): walk(v, k)
        elif isinstance(value, list):
            for v in value: walk(v)
        else:
            require(value is None or type(value) in (str, bool, int))
    walk(c)
    canonical = {key: value for key, value in data.items() if key != 'revision'}
    require(hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest() == data['revision'])
    return data


def _record(client: httpx.Client, workspace_id: str, record_id: str) -> dict:
    if record_id.startswith('finance-item:') and _valid_record_id(record_id):
        item_id = record_id[len('finance-item:'):]
        payload = _get(client, f"/api/v3/workspaces/{quote(workspace_id, safe='')}/reader/items/{quote(item_id, safe='')}")
        if payload.get('workspaceId') != workspace_id or payload.get('readOnly') is not True:
            raise FcUnavailable('Finance Core returned a mismatched Workspace response.')
        return _financial_item(payload.get('data'), item_id)
    match = RECORD_ID.fullmatch(record_id)
    if match is None:
        raise ValueError("Invalid record ID.")
    kind, raw_id, month, as_of, through, cutoff = match.groups()
    if cutoff is not None:
        path = f"/api/v3/workspaces/{quote(workspace_id, safe='')}/reports/month-to-date?asOf={cutoff}"
        payload = _get(client, path)
        if payload.get('workspaceId') != workspace_id or payload.get('readOnly') is not True:
            raise FcUnavailable('Finance Core returned a mismatched Workspace response.')
        return _month_to_date_report(payload.get('data'), cutoff)
    if as_of is not None:
        path = f"/api/v3/workspaces/{quote(workspace_id, safe='')}/reports/economic-evidence?asOf={as_of}&through={through}"
        payload = _get(client, path)
        if payload.get('workspaceId') != workspace_id or payload.get('readOnly') is not True:
            raise FcUnavailable('Finance Core returned a mismatched Workspace response.')
        return _economic_report(payload.get('data'), as_of, through)
    if month is not None:
        path = f"/api/v3/workspaces/{quote(workspace_id, safe='')}/reports/monthly-review?month={month}"
        payload = _get(client, path)
        if payload.get("workspaceId") != workspace_id or payload.get("readOnly") is not True:
            raise FcUnavailable("Finance Core returned a mismatched Workspace response.")
        return _monthly_report(payload.get("data"), month)
    resource = "journal-entries" if kind == "entry" else "journal-entry-drafts"
    path = f"/api/v3/workspaces/{quote(workspace_id, safe='')}/{resource}/{quote(raw_id, safe='')}"
    payload = _get(client, path)
    if payload.get("workspaceId") != workspace_id or not isinstance(payload.get("data"), dict):
        raise FcUnavailable("Finance Core returned a mismatched Workspace response.")
    data = payload["data"]
    item = data if kind == "entry" else data.get("draft")
    if not isinstance(item, dict) or item.get("id") != raw_id:
        raise FcUnavailable("Finance Core returned a mismatched record.")
    return data


def _label(record_id: str, data: dict) -> str:
    if record_id.startswith('finance-item:'):
        return data['label']
    if record_id.startswith('month-to-date:'):
        return f'Month-to-date through {record_id.split(":")[1]} (partial; posted Journal only)'
    if record_id.startswith('economic-evidence:'):
        _, as_of, through = record_id.split(':')
        return f'Economic evidence {as_of} through {through} (gross recorded balances; not personal affordability)'
    if record_id.startswith("monthly-review:"):
        return f"Monthly review {record_id.split(':')[1]} (three months; posted ledger only)"
    item = data if record_id.startswith("entry:") else data["draft"]
    description = item.get("description")
    return description[:120] if isinstance(description, str) and description else record_id


def _evidence(record_id: str, data: dict) -> dict[str, str]:
    if record_id.startswith('finance-item:'):
        return {'recordId': record_id, 'label': data['label'], 'revision': data['revision'],
            'text': 'Selected FC financial facts. Account-only posting lines are not whole balanced entries; notes/source text are excluded. Not a complete financial foundation or action advice.\n'
                + json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)}
    if record_id.startswith('month-to-date:'):
        return {'recordId': record_id, 'label': _label(record_id, data), 'revision': data['revision'],
            'text': 'Provisional month-to-date review. Posted Journal only; unrecorded days and external completeness remain unknown.\n'
                + json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)}
    if record_id.startswith('economic-evidence:'):
        return {'recordId': record_id, 'label': _label(record_id, data), 'revision': data['revision'],
                'text': 'Deterministic economic evidence. Gross balances; future charges and external completeness remain unknown.\n' + json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)}
    if record_id.startswith("monthly-review:"):
        # A required report is atomic: the host must reject an insufficient
        # budget, never truncate its months, warnings, currencies or coverage.
        return {"recordId": record_id, "label": _label(record_id, data),
            "text": "Deterministic monthly review. External completeness is unknown.\n" + json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2),
            "revision": data["revision"]}
    item = data if record_id.startswith("entry:") else data["draft"]
    label = _label(record_id, data)
    fields = [f"Date: {item.get('date', '')}", f"Description: {label}"]
    if record_id.startswith("draft:"):
        fields.append(f"Status: {data.get('status', 'draft')}")
    else:
        fields.append(f"Posted at: {item.get('postedAt', '')}")
    postings = item.get("postings", [])
    if not isinstance(postings, list):
        raise FcUnavailable("Finance Core returned an invalid record.")
    for posting in postings[:200]:
        if not isinstance(posting, dict):
            raise FcUnavailable("Finance Core returned an invalid record.")
        fields.append("Posting: " + " | ".join(str(posting.get(key, "")) for key in
                          ("accountId", "side", "units", "commodityCode")))
    text = "\n".join(fields)[:8000]
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    revision = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {"recordId": record_id, "label": label, "text": text, "revision": revision}


def read_evidence(workspace_id: str, record_ids: list[str]) -> list[dict[str, str]]:
    if (not isinstance(workspace_id, str) or not WORKSPACE_ID.fullmatch(workspace_id)
            or not isinstance(record_ids, list) or not 1 <= len(record_ids) <= MAX_RECORDS
            or any(not _valid_record_id(item) for item in record_ids)):
        raise ValueError("Invalid Workspace scope or record count.")
    base, token, _ui_url, selected = _settings()
    allowed = selected.get(workspace_id)
    if allowed is None or len(set(record_ids)) != len(record_ids) or any(item not in allowed for item in record_ids):
        raise ValueError("Invalid Workspace scope or record selection.")
    with _client(base, token) as client:
        _check_health(client)
        if workspace_id not in _workspaces(client):
            raise ValueError("Invalid Workspace scope.")
        return [_evidence(record_id, _record(client, workspace_id, record_id)) for record_id in record_ids]


def read_evidence_request(request: dict) -> dict:
    """Read a strict protocol 2 request through the existing selected-record path."""
    if (not isinstance(request, dict)
            or set(request) != {"protocolVersion", "pluginId", "scopeId", "recordIds"}
            or type(request.get("protocolVersion")) is not int
            or request["protocolVersion"] != 2 or request.get("pluginId") != "finance-core"):
        raise ValueError("Invalid evidence request.")
    records = read_evidence(request["scopeId"], request["recordIds"])
    return {"protocolVersion": 2, "pluginId": "finance-core", "scopeId": request["scopeId"],
            "records": records}


def source_revision() -> str:
    """Bind read configuration without requiring credentials or accessing FC."""
    configuration = {
        "apiUrl": _environment().get("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:8788").rstrip("/"),
        "recordsJson": _environment().get("FINANCE_CORE_PLUGIN_RECORDS_JSON", "{}"),
    }
    canonical = json.dumps(configuration, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def list_scopes(scope_id: str | None = None) -> dict:
    """List configured read candidates, optionally restricted to one Workspace."""
    if scope_id is not None and (not isinstance(scope_id, str) or not WORKSPACE_ID.fullmatch(scope_id)):
        raise ValueError("Invalid Workspace scope.")
    base, token, _ui_url, selected = _settings()
    if scope_id is not None:
        if scope_id not in selected:
            raise ValueError("Invalid Workspace scope.")
        selected = {scope_id: selected[scope_id]}
    with _client(base, token) as client:
        _check_health(client)
        workspaces = _workspaces(client)
        result = []
        for workspace_id, ids in selected.items():
            workspace = workspaces.get(workspace_id)
            if workspace is None:
                if scope_id is not None:
                    raise ValueError("Invalid Workspace scope.")
                continue
            names = {item['id']: item['label'] for item in _reader_catalog(client, workspace_id)['items']} if any(item.startswith('finance-item:') for item in ids) else {}
            records = [{"id": item, "label": _label(item, {'label': names[item[len('finance-item:'):]]} if item.startswith('finance-item:') else {} if item.startswith(("monthly-review:", 'economic-evidence:', 'month-to-date:')) else _record(client, workspace_id, item))}
                       for item in ids]
            result.append({"id": workspace_id, "label": workspace.get("displayName", workspace_id),
                           "records": records})
        return {"scopes": result}


def create_router() -> APIRouter:
    router = APIRouter(prefix=PREFIX)

    @router.get("/scopes")
    def scopes() -> dict:
        try:
            return {"workspaces": list_scopes()["scopes"]}
        except FcIncompatible as error:
            raise HTTPException(409, detail=str(error)) from error
        except FcUnavailable as error:
            raise HTTPException(503, detail=str(error)) from error

    @router.get("/dashboard")
    def dashboard(workspace_id: str = Query(alias="workspaceId")) -> dict:
        try:
            base, token, ui_url, selected = _settings()
            if workspace_id not in selected:
                raise HTTPException(404, detail="Workspace is unavailable.")
            with _client(base, token) as client:
                _check_health(client)
                if workspace_id not in _workspaces(client):
                    raise HTTPException(404, detail="Workspace is unavailable.")
                payload = _get(client, f"/api/v3/workspaces/{quote(workspace_id, safe='')}/dashboard")
                if payload.get("workspaceId") != workspace_id or not isinstance(payload.get("data"), dict):
                    raise FcUnavailable("Finance Core returned a mismatched Workspace response.")
                return {"workspaceId": workspace_id, "data": payload["data"], "readOnly": True,
                        "journalUrl": ui_url}
        except FcIncompatible as error:
            raise HTTPException(409, detail=str(error)) from error
        except FcUnavailable as error:
            raise HTTPException(503, detail=str(error)) from error

    return router
