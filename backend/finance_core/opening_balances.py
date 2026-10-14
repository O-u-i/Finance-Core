"""Opening stock classification and exact draft construction, without storage/HTTP."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import Field, field_validator

from finance_core.ledger import decimal_add, decimal_mul, quantize
from finance_core.models_personal import Money, ObservedDate, PersonalModel
from finance_core.models_v2 import JournalEntryDraft, canonical_decimal

OPENING_TAG = 'fc:opening-balance:'
EQUITY_TAG = 'fc:opening-equity:'
CORRECTION_TAG = 'fc:opening-corrects:'


class OpeningBalanceLine(PersonalModel):
    account_id: str = Field(alias='accountId', min_length=1)
    commodity_code: str = Field(alias='commodityCode', min_length=1)
    amount: Money
    unit_cost: Money | None = Field(default=None, alias='unitCost')
    lot_id: str | None = Field(default=None, alias='lotId')
    note: str = Field(default='', max_length=4000)

    @field_validator('commodity_code')
    @classmethod
    def normalize_code(cls, value):
        return value.strip().upper()


class OpeningBalanceRequest(PersonalModel):
    id: str = Field(min_length=1)
    date: ObservedDate
    balancing_commodity_code: str = Field(alias='balancingCommodityCode', min_length=1)
    equity_account_id: str = Field(alias='equityAccountId', min_length=1)
    source: str = Field(min_length=1, max_length=500)
    balances: list[OpeningBalanceLine] = Field(min_length=1, max_length=100)
    supersedes: str | None = None

    @field_validator('balancing_commodity_code')
    @classmethod
    def normalize_code(cls, value):
        return value.strip().upper()


class OpeningBalancePostRequest(PersonalModel):
    confirmed: Literal[True]
    expected_updated_at: str = Field(alias='expectedUpdatedAt', min_length=1, max_length=100)


def opening_date(entry: dict) -> str | None:
    markers = [tag[len(OPENING_TAG):] for tag in entry.get('tags', []) if tag.startswith(OPENING_TAG)]
    if not markers:
        if any(tag.startswith('fc:opening-') for tag in entry.get('tags', [])):
            raise ValueError('Opening equity/correction classification requires a baseline date.')
        return None
    if len(markers) != 1 or date.fromisoformat(markers[0]).isoformat() != markers[0]:
        raise ValueError('Opening classification must contain one real baseline date.')
    tags = entry.get('tags', [])
    equity = [tag[len(EQUITY_TAG):] for tag in tags if tag.startswith(EQUITY_TAG)]
    corrections = [tag[len(CORRECTION_TAG):] for tag in tags if tag.startswith(CORRECTION_TAG)]
    if len(equity) != 1 or not equity[0] or len(corrections) > 1 or (corrections and not corrections[0]):
        raise ValueError('Opening requires one equity counterpart and at most one correction reference.')
    if any(tag.startswith('fc:opening-') and not tag.startswith((OPENING_TAG, EQUITY_TAG, CORRECTION_TAG)) for tag in tags):
        raise ValueError('Unknown reserved opening classification.')
    return markers[0]


def opening_scope(draft: JournalEntryDraft, accounts: dict, commodities: dict) -> set[tuple[str, str]]:
    """Same stock/lot shape for dedicated intake, ordinary Journal and restored facts."""
    currency = commodities.get(draft.balancing_commodity_code)
    equity_id = next(tag[len(EQUITY_TAG):] for tag in draft.tags if tag.startswith(EQUITY_TAG))
    equity = accounts.get(equity_id)
    if not currency or currency.kind != 'currency' or not equity or equity.type != 'equity' or currency.code not in equity.allowed_commodity_codes:
        raise ValueError('Opening requires a currency and an explicit matching equity counterpart.')
    if not draft.source.strip() or any(tag.startswith('personal-transfer:') for tag in draft.tags):
        raise ValueError('Opening stock requires its source and cannot be a cross-segment transfer.')
    pairs = set()
    for posting in draft.postings:
        account, commodity = accounts.get(posting.account_id), commodities.get(posting.commodity_code)
        pair = (posting.account_id, posting.commodity_code)
        if pair in pairs or not account or account.type not in {'asset', 'liability', 'equity'} or posting.cash_flow_category != 'other':
            raise ValueError('Opening lines must be distinct stock accounts, never period income/expense.')
        if not commodity or commodity.code not in account.allowed_commodity_codes:
            raise ValueError('Opening commodity is missing or not allowed by its account.')
        if commodity.kind == 'currency':
            if commodity.code != currency.code or posting.lot_action or posting.lot_id or posting.lot_allocations or posting.valuation_rate not in {None, '1'}:
                raise ValueError('Currency openings use their own currency and never inferred FX or lots.')
        elif commodity.kind == 'security':
            if account.type != 'asset' or posting.side != 'debit' or posting.lot_action != 'acquire' or posting.rate_type != 'cost' or not posting.valuation_rate:
                raise ValueError('Opening securities require acquired lots with positive units and explicit book cost.')
        else:
            raise ValueError('Opening supports currencies and securities, not unspecified units.')
        pairs.add(pair)
    scope = {pair for pair in pairs if pair[0] != equity_id}
    if not scope:
        raise ValueError('Opening requires stock lines apart from its equity counterpart.')
    return scope


def build_opening_draft(item: OpeningBalanceRequest, accounts: dict, commodities: dict) -> JournalEntryDraft:
    currency = commodities.get(item.balancing_commodity_code)
    equity = accounts.get(item.equity_account_id)
    if not currency or currency.kind != 'currency' or currency.status != 'active':
        raise ValueError('Choose an active balancing currency; currencies are initialized separately.')
    if not equity or equity.type != 'equity' or equity.status != 'active' or currency.code not in equity.allowed_commodity_codes:
        raise ValueError('Choose an explicit active equity counterpart in the balancing currency.')
    postings, difference, pairs = [], Decimal(0), set()
    for index, value in enumerate(item.balances):
        account, commodity = accounts.get(value.account_id), commodities.get(value.commodity_code)
        pair = (value.account_id, value.commodity_code)
        if pair in pairs or value.account_id == item.equity_account_id:
            raise ValueError('Opening lines must be distinct and separate from the equity counterpart.')
        pairs.add(pair)
        if not account or account.type not in {'asset', 'liability', 'equity'}:
            raise ValueError('Opening balances use asset, liability or equity accounts, never income/expense.')
        if not commodity or commodity.status != 'active' or commodity.code not in account.allowed_commodity_codes:
            raise ValueError('Opening commodity must be active and allowed by its account.')
        amount = Decimal(value.amount)
        if not amount:
            raise ValueError('Journal opening lines must be nonzero; do not invent a transaction for a zero stock.')
        side = 'debit' if account.type == 'asset' else 'credit'
        if amount < 0:
            side = 'credit' if side == 'debit' else 'debit'
        rate, lot = '1', {}
        if commodity.kind == 'security':
            if account.type != 'asset' or amount < 0 or not value.unit_cost or Decimal(value.unit_cost) <= 0 or not value.lot_id:
                raise ValueError('Security opening requires positive units, explicit positive unit cost and a lot ID. Market price is not cost.')
            rate = value.unit_cost
            lot = {'lotAction': 'acquire', 'lotId': value.lot_id}
        elif commodity.code != currency.code or value.unit_cost is not None or value.lot_id:
            raise ValueError('Currency openings do not infer FX or lots. Record each currency separately.')
        valuation = quantize(decimal_mul(amount.copy_abs(), Decimal(rate)), currency.scale)
        difference = decimal_add(difference, valuation if side == 'debit' else valuation.copy_negate())
        postings.append({'id': f'{item.id}-p{index+1}', 'accountId': account.id, 'side': side,
                         'units': canonical_decimal(amount.copy_abs()), 'commodityCode': commodity.code,
                         'valuationRate': rate, 'rateType': 'cost' if lot else 'exchange',
                         'cashFlowCategory': 'other', 'memo': value.note, **lot})
    if difference:
        postings.append({'id': f'{item.id}-equity', 'accountId': equity.id,
                         'side': 'credit' if difference > 0 else 'debit',
                         'units': canonical_decimal(difference.copy_abs()), 'commodityCode': currency.code,
                         'cashFlowCategory': 'other', 'memo': 'Explicit opening equity counterpart'})
    tags = [OPENING_TAG + item.date, EQUITY_TAG + equity.id]
    if item.supersedes:
        tags.append(CORRECTION_TAG + item.supersedes)
    return JournalEntryDraft.model_validate({'id': item.id, 'date': item.date, 'description': 'Opening balances',
        'source': item.source, 'tags': tags, 'balancingCommodityCode': currency.code, 'postings': postings})


def validate_opening(draft: JournalEntryDraft, accounts: dict, commodities: dict, entries: list[dict]) -> None:
    payload = draft.model_dump(by_alias=True)
    baseline = opening_date(payload)
    if baseline is None:
        pairs = {(p.account_id, p.commodity_code) for p in draft.postings}
        for entry in entries:
            original_baseline = opening_date(entry)
            if original_baseline and not entry.get('reversalOf'):
                scope = {(p['accountId'], p['commodityCode']) for p in entry['postings']
                         if EQUITY_TAG + p['accountId'] not in entry['tags']}
                if pairs & scope:
                    parsed = date.fromisoformat(draft.date).isoformat()
                    if parsed != draft.date or parsed < original_baseline:
                        raise ValueError('Journal date must be a real date on or after its account/commodity opening baseline.')
        return
    if draft.date != baseline or baseline > datetime.now(timezone(timedelta(hours=8))).date().isoformat():
        raise ValueError('Opening uses its real baseline date, not a future or shifted Journal date.')
    equity_ids = [tag[len(EQUITY_TAG):] for tag in draft.tags if tag.startswith(EQUITY_TAG)]
    pairs = opening_scope(draft, accounts, commodities)
    if accounts[equity_ids[0]].status != 'active':
        raise ValueError('Opening equity counterpart must be active when posted.')
    corrections = [tag[len(CORRECTION_TAG):] for tag in draft.tags if tag.startswith(CORRECTION_TAG)]
    reversals = {entry['reversalOf']: entry for entry in entries if entry.get('reversalOf')}
    if corrections:
        original = next((entry for entry in entries if entry['id'] == corrections[0]), None)
        if len(corrections) != 1 or not original or original.get('reversalOf') or opening_date(original) != baseline or original['id'] not in reversals:
            raise ValueError('Opening correction requires one fully linked-reversed baseline at the same date.')
        if reversals[original['id']]['date'] != baseline:
            raise ValueError('A later-date reversal cannot replace an earlier opening. Use an actual-date adjustment to preserve historical balances.')
        original_pairs = {(p['accountId'], p['commodityCode']) for p in original['postings'] if p['accountId'] != equity_ids[0]}
        if original_pairs != pairs or EQUITY_TAG + equity_ids[0] not in original['tags']:
            raise ValueError('Opening correction must retain the original account/currency and equity scope.')
        if any(CORRECTION_TAG + original['id'] in entry.get('tags', []) and not entry.get('reversalOf') for entry in entries):
            raise ValueError('Opening correction lineage cannot branch; correct the latest retained opening instead.')
    for entry in entries:
        overlap = pairs & {(p['accountId'], p['commodityCode']) for p in entry['postings']}
        if not overlap:
            continue
        entry_date = date.fromisoformat(entry['date']).isoformat()
        original_baseline = opening_date(entry)
        if original_baseline and not entry.get('reversalOf'):
            if entry['id'] not in reversals or not corrections:
                raise ValueError('An opening already exists; replacement requires an explicit same-date correction lineage.')
        if entry_date < baseline:
            raise ValueError('Opening date must not follow existing facts for the selected account/commodity.')


def validate_opening_history(entries: list[dict], drafts: list[dict], accounts: dict, commodities: dict) -> None:
    """Restore checks historical classification without treating inactive facts as new drafts."""
    roots, scopes, parents, reversals = {}, {}, {}, {}
    for entry in entries:
        baseline = opening_date(entry)
        if entry.get('reversalOf'):
            if entry['reversalOf'] in reversals:
                raise ValueError('Restored entries cannot reverse the same original twice.')
            reversals[entry['reversalOf']] = entry
        elif baseline:
            payload = {key: value for key, value in entry.items() if key in JournalEntryDraft.model_fields or key == 'balancingCommodityCode'}
            payload['postings'] = [{key: value for key, value in p.items() if key != 'valuationAmount'} for p in entry['postings']]
            draft = JournalEntryDraft.model_validate(payload)
            if entry['date'] != baseline:
                raise ValueError('Restored opening date disagrees with its baseline classification.')
            roots[entry['id']], scopes[entry['id']] = entry, opening_scope(draft, accounts, commodities)
            totals = {'debit': Decimal(0), 'credit': Decimal(0)}
            scale = commodities[draft.balancing_commodity_code].scale
            for posting in entry['postings']:
                try:
                    units, value = Decimal(posting['units']), Decimal(posting['valuationAmount'])
                except (InvalidOperation, TypeError) as error:
                    raise ValueError('Restored opening values must be finite exact decimals.') from error
                expected = quantize(decimal_mul(units, Decimal(posting.get('valuationRate') or '1')), scale)
                if not value.is_finite() or value != expected or quantize(units, commodities[posting['commodityCode']].scale) != units:
                    raise ValueError('Restored opening valuation must equal its explicit units and cost at the balancing scale.')
                totals[posting['side']] = decimal_add(totals[posting['side']], value)
            if totals['debit'] != totals['credit']:
                raise ValueError('Restored opening stock is not balanced.')
            parents[entry['id']] = next((tag[len(CORRECTION_TAG):] for tag in entry['tags'] if tag.startswith(CORRECTION_TAG)), None)
    for record in drafts:
        payload = record['draft']
        if opening_date(payload):
            opening_scope(JournalEntryDraft.model_validate(payload), accounts, commodities)
            if payload['date'] != opening_date(payload):
                raise ValueError('Restored opening draft date disagrees with its classification.')
    for original_id, reversal in reversals.items():
        original = next((e for e in entries if e['id'] == original_id), None)
        if not original or original.get('reversalOf') or opening_date(reversal) != opening_date(original):
            raise ValueError('Restored reversal classification disagrees with its original.')
        if original_id in roots:
            if reversal['tags'] != original['tags'] or reversal['date'] < original['date']:
                raise ValueError('Restored opening reversal must retain its classification and effective chronology.')
            fields = ('accountId', 'units', 'commodityCode', 'valuationRate', 'valuationAmount', 'rateType', 'cashFlowCategory')
            if len(original['postings']) != len(reversal['postings']) or any(
                    a['side'] == b['side'] or any(a.get(key) != b.get(key) for key in fields)
                    for a, b in zip(original['postings'], reversal['postings'])):
                raise ValueError('Restored opening reversal must exactly reverse its stock postings.')
    for identity, entry in roots.items():
        chain, current = set(), identity
        while current:
            if current in chain or current not in roots:
                raise ValueError('Restored opening correction lineage is missing or cyclic.')
            chain.add(current)
            parent = parents[current]
            if parent:
                old = roots.get(parent)
                equity_tag = next(tag for tag in entry['tags'] if tag.startswith(EQUITY_TAG))
                if (not old or parent not in reversals or reversals[parent]['date'] != entry['date']
                        or old['date'] != entry['date'] or scopes[parent] != scopes[identity]
                        or equity_tag not in old['tags']):
                    raise ValueError('Restored opening correction must retain scope with a same-date linked reversal.')
                if sum(value == parent for value in parents.values()) != 1:
                    raise ValueError('Restored opening correction lineage cannot branch.')
            current = parent
        for other_id, other in roots.items():
            if other_id not in chain and identity not in _ancestors(other_id, parents) and scopes[identity] & scopes[other_id]:
                raise ValueError('Restored independent openings overlap the same account/commodity.')
        for other in entries:
            if scopes[identity] & {(p['accountId'], p['commodityCode']) for p in other['postings']}:
                if date.fromisoformat(other['date']).isoformat() < entry['date']:
                    raise ValueError('Restored facts precede their account/commodity opening baseline.')


def _ancestors(identity: str, parents: dict) -> set[str]:
    seen = set()
    while identity and identity not in seen:
        seen.add(identity)
        identity = parents.get(identity)
    return seen
