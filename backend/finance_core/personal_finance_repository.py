"""FC-owned application operations backed by one workspace-scoped connection."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from finance_core.database import transaction
from finance_core.ledger_repository import LedgerRepository, now_iso
from finance_core.models_v2 import Account, JournalEntryDraft, canonical_decimal
from finance_core.models_personal import (
    ArrangementDraftRequest, CloseRequest, FinancialAccount, FinanceSettings,
    InvestmentArrangement, MonthlyObservation, NonFinancialAsset, Party, LegacyMappingRequest,
    BalanceRecordRequest,
)
from finance_core.personal_finance import (
    allocate_distribution, arrangement_for, effective_date,
    ledger_at, month_end, previous_month,
)
from finance_core.schema_migration import (
    archive_living, canonical, fingerprint, rows, schema_version,
)

from finance_core.personal_finance_snapshot import PersonalFinanceSnapshot, RevisionConflict, dump
from finance_core.recorded_balances import calculate_recorded_balances


class PersonalFinanceRepository:
    def __init__(self, ledger: LedgerRepository):
        self.ledger = ledger
        self.connection = ledger.connection
        self.snapshot = PersonalFinanceSnapshot(self.connection)
        if schema_version(self.connection) != 3:
            raise RevisionConflict('Schema 3 requires an explicit stopped-writer migration into a new Vault copy.')

    def accounts(self) -> list[dict]:
        return self.snapshot.accounts()

    def delete_account(self, account_id: str) -> dict:
        return self.ledger.delete_account(account_id)

    def parties(self) -> list[dict]:
        return self.snapshot.parties()

    def assets(self) -> list[dict]:
        return self.snapshot.assets()

    def arrangements(self) -> list[dict]:
        return self.snapshot.arrangements()

    def observations(self) -> list[dict]:
        return [value for value in self.snapshot.observations() if not value.get('observedDate')]

    def balance_records(self) -> list[dict]:
        return [value for value in self.snapshot.observations() if value.get('observedDate')]

    def record_balance(self, item: BalanceRecordRequest, *, opening: bool = False) -> dict:
        observation = MonthlyObservation.model_validate({**dump(item), 'kind': 'balance',
                                                       'month': item.observed_date[:7]})
        with transaction(self.connection):
            if opening:
                existing = [record for record in self.balance_records() if record['subjectId'] == item.subject_id]
                if item.supersedes or (existing and item.observed_date >= min(record['observedDate'] for record in existing)):
                    raise ValueError('Living opening must precede existing actual-date records. Use ordinary balances or their explicit correction instead.')
            self._record_observation(observation)
        return next(value for value in self.balance_records() if value['id'] == item.id)

    def recorded_balance_report(self, month: str) -> dict:
        month_end(month)
        return calculate_recorded_balances(month, self.accounts(), self.balance_records())

    def settings(self) -> dict | None:
        return self.snapshot.settings()

    def legacy_living(self) -> dict:
        return self.snapshot.legacy_living()


    def map_legacy(self, legacy_id: str, item: LegacyMappingRequest) -> dict:
        legacy = next((value for value in self.ledger.list_living_accounts() if value.id == legacy_id), None)
        account = next((value for value in self.accounts() if value['id'] == item.target_account_id), None)
        if not legacy or not account or legacy.commodity_code not in account['allowedCommodityCodes']:
            raise ValueError('Select explicit existing identities with a matching currency.')
        if account.get('legacyLivingId') or any(value.get('legacyLivingId') == legacy_id for value in self.accounts()):
            raise ValueError('Legacy identity is already mapped.')
        with transaction(self.connection):
            archive_living(self.connection)
            account['legacyLivingId'] = legacy_id
            self.connection.execute('UPDATE financial_accounts_v3 SET legacy_living_id=?,payload_json=? WHERE id=?', (legacy_id, canonical(account), account['id']))
            self.connection.execute('INSERT INTO finance_migration_receipts_v3 VALUES(?,?)', ('mapping-' + str(uuid4()), canonical({'legacyLivingId': legacy_id, 'targetAccountId': account['id'], 'reason': item.reason, 'sameEconomicAccountConfirmed': True})))
            self._invalidate()
        return account


    def _invalidate(self) -> None:
        self.ledger._invalidate_undo()

    def save_party(self, item: Party) -> dict:
        with transaction(self.connection):
            self.connection.execute('INSERT INTO finance_parties_v3 VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json', (item.id, canonical(dump(item))))
            self._invalidate()
        return dump(item)

    def save_settings(self, item: FinanceSettings) -> dict:
        self.snapshot.require_party(item.reporting_party_id)
        month_end(item.cutover_month)
        current = self.settings()
        if current and self.connection.execute('SELECT 1 FROM monthly_closes_v3 LIMIT 1').fetchone() and current != dump(item):
            raise ValueError('Confirmed month closes lock the reporting party and baseline. Use a new Vault for a different boundary.')
        with transaction(self.connection):
            self.connection.execute("INSERT INTO finance_settings_v3 VALUES('personal',?) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json", (canonical(dump(item)),))
            self._invalidate()
        return dump(item)

    def save_account(self, item: FinancialAccount, *, create: bool) -> dict:
        with transaction(self.connection):
            existing = next((value for value in self.accounts() if value['id'] == item.id), None)
            if create == (existing is not None):
                raise ValueError('Account already exists or was not found.')
            if item.segment == 'living':
                self.snapshot.require_party(item.owner_party_id)
                if len(item.allowed_commodity_codes) != 1:
                    raise ValueError('A monthly snapshot account has exactly one currency.')
                self.snapshot.require_currency(item.allowed_commodity_codes[0])
            for code in item.allowed_commodity_codes:
                if self.ledger.get_commodity(code) is None:
                    raise ValueError('Account references an unknown commodity.')
            used = bool(existing and self.snapshot.account_is_referenced(item.id))
            if existing:
                locked = ('segment', 'balanceSource', 'ownerPartyId', 'allowedCommodityCodes', 'startMonth', 'legacyLivingId', 'successorOf')
                if used and any(existing.get(key) != dump(item).get(key) for key in locked):
                    raise ValueError('Used accounts lock segment, measurement and ownership. Register an explicit successor.')
                if used and existing['type'] != item.type:
                    raise ValueError('A used unified account cannot silently change accounting type.')
                if item.end_month:
                    if self.connection.execute('SELECT 1 FROM monthly_observations_v3 WHERE subject_id=? AND month>? LIMIT 1', (item.id, item.end_month)).fetchone():
                        raise ValueError('End month cannot precede an existing observation. History must remain in its recorded period.')
                    dates = self.connection.execute('SELECT e.date FROM postings_v2 p JOIN journal_entries_v2 e ON e.id=p.entry_id WHERE p.account_id=?', (item.id,))
                    if any(effective_date(row['date']) > month_end(item.end_month) for row in dates):
                        raise ValueError('End month cannot precede a posted Journal entry.')
            if item.successor_of:
                predecessor = next((value for value in self.accounts() if value['id'] == item.successor_of), None)
                if not predecessor or not predecessor.get('endMonth') or not item.start_month or predecessor['endMonth'] != previous_month(item.start_month) or predecessor['allowedCommodityCodes'] != item.allowed_commodity_codes:
                    raise ValueError('Successors require an explicit predecessor endMonth before startMonth.')
                if any(value.get('successorOf') == item.successor_of and value['id'] != item.id for value in self.accounts()):
                    raise ValueError('A real account may have only one successor.')
                if predecessor['balanceSource'] == 'ledger':
                    state = self.snapshot.state(previous_month(item.start_month))
                    ledger, issues = ledger_at(state, month_end(previous_month(item.start_month)))
                    if issues or any(balance for (account_id, _), balance in ledger['balances'].items() if account_id == predecessor['id']):
                        raise ValueError('Close a predecessor ledger balance explicitly before changing its measurement source.')
            if item.legacy_living_id:
                legacy = next((value for value in self.ledger.list_living_accounts() if value.id == item.legacy_living_id), None)
                if not legacy or item.segment != 'living' or item.allowed_commodity_codes != [legacy.commodity_code]:
                    raise ValueError('Legacy mapping must explicitly match a Living identity and currency; never match by name.')
            if item.balance_source == 'ledger':
                self.ledger._save_account_row(Account.model_validate({key: value for key, value in dump(item).items() if key in {'id','code','name','type','subtype','allowedCommodityCodes','status'}}), create=create)
            elif existing and existing['balanceSource'] == 'ledger':
                self.connection.execute('DELETE FROM financial_accounts_v3 WHERE id=?', (item.id,))
                self.connection.execute('DELETE FROM accounts_v2 WHERE id=?', (item.id,))
            self.connection.execute('INSERT INTO financial_accounts_v3 VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET ledger_account_id=excluded.ledger_account_id,legacy_living_id=excluded.legacy_living_id,payload_json=excluded.payload_json',
                                    (item.id, item.id if item.balance_source == 'ledger' else None, item.legacy_living_id, canonical(dump(item))))
            archive_living(self.connection)
            self._invalidate()
            return dump(item)

    def save_asset(self, item: NonFinancialAsset, *, create: bool) -> dict:
        self.snapshot.require_party(item.owner_party_id)
        self.snapshot.require_currency(item.currency, item.purchase_cost)
        existing = next((value for value in self.assets() if value['id'] == item.id), None)
        if create == (existing is not None):
            raise ValueError('Asset already exists or was not found.')
        if existing and self.connection.execute('SELECT 1 FROM monthly_observations_v3 WHERE subject_id=?', (item.id,)).fetchone():
            if any(existing.get(key) != dump(item).get(key) for key in ('currency', 'purchasedDate', 'purchaseCost', 'ownerPartyId', 'ownershipShare', 'linkedAccountId', 'valuationMethod')):
                raise ValueError('Valued asset identity/ownership/cost is locked; append a valuation correction instead.')
        if item.linked_account_id:
            account = next((value for value in self.accounts() if value['id'] == item.linked_account_id), None)
            if not account or account['segment'] != 'living' or account['type'] != 'asset' or account['allowedCommodityCodes'] != [item.currency] or account['ownerPartyId'] != item.owner_party_id:
                raise ValueError('Linked assets require a same-currency Living asset account with matching ownership.')
            if any(value.get('linkedAccountId') == item.linked_account_id and value['id'] != item.id for value in self.assets()):
                raise ValueError('One economic asset can have only one valuation authority.')
        with transaction(self.connection):
            self.connection.execute('INSERT INTO non_financial_assets_v3 VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json', (item.id, canonical(dump(item))))
            self._invalidate()
        return dump(item)


    def save_arrangement(self, item: InvestmentArrangement) -> dict:
        self.snapshot.validate_arrangement(item)
        previous = [value for value in self.arrangements() if value['id'] == item.id]
        if item.version != max((value['version'] for value in previous), default=0) + 1:
            raise ValueError('Agreement versions are consecutive and append-only.')
        if previous and (item.currency != previous[-1]['currency'] or item.from_month <= previous[-1]['fromMonth']):
            raise ValueError('A new version starts a later month and cannot rewrite historical ownership.')
        if any(value['currency'] == item.currency and value['id'] != item.id for value in self.arrangements()):
            raise ValueError('This Vault has one Investment pool per currency; append a version to its existing agreement.')
        if self.connection.execute('SELECT 1 FROM monthly_closes_v3 WHERE month>=? LIMIT 1', (item.from_month,)).fetchone():
            raise ValueError('A new ownership version cannot rewrite a confirmed month.')
        with transaction(self.connection):
            self.connection.execute('INSERT INTO investment_arrangements_v3 VALUES(?,?,?)', (item.id, item.version, canonical(dump(item))))
            self._invalidate()
        return dump(item)

    def record_observations(self, items: list[MonthlyObservation]) -> list[dict]:
        with transaction(self.connection):
            return [self._record_observation(item) for item in items]

    def record_observation(self, item: MonthlyObservation) -> dict:
        return self.record_observations([item])[0]

    def _record_observation(self, item: MonthlyObservation) -> dict:
        month_end(item.month)
        if item.observed_date and item.observed_date > datetime.now(timezone(timedelta(hours=8))).date().isoformat():
            raise ValueError('A balance date cannot be in the future (Asia/Shanghai).')
        for amount in (item.amount, item.incoming, item.outgoing, item.fees, item.in_transit):
            self.snapshot.require_currency(item.currency, amount)
        subjects = self.assets() if item.kind == 'valuation' else self.accounts()
        if item.kind != 'transfer':
            subject = next((value for value in subjects if value['id'] == item.subject_id), None)
            if not subject or (item.kind == 'balance' and (subject['balanceSource'] != 'monthly_snapshot' or subject['allowedCommodityCodes'] != [item.currency])) or (item.kind == 'valuation' and subject['currency'] != item.currency):
                raise ValueError('Observation subject, measurement source and currency must match.')
            if item.kind == 'balance' and subject.get('endMonth') and item.month > subject['endMonth']:
                raise ValueError('Account purpose has ended. Only observations within its recorded period are allowed.')
            if item.observed_date and subject.get('startMonth') and item.month < subject['startMonth']:
                raise ValueError('Balance date precedes the account purpose period.')
            if item.observed_date and subject['status'] == 'inactive' and not subject.get('endMonth'):
                raise ValueError('An inactive account requires an explicit purpose end month before recording historical balances.')
        observations = self.snapshot.observations()
        replaced = {value.get('supersedes') for value in observations}
        if item.observed_date:
            if item.supersedes:
                previous = next((value for value in observations if value['id'] == item.supersedes), None)
                if not previous or previous['id'] in replaced or any(previous.get(key) != dump(item).get(key) for key in ('subjectId', 'kind', 'currency', 'observedDate')):
                    raise RevisionConflict('A dated correction must name an unreplaced balance with the same account, currency and actual date.')
        else:
            current = next((value for value in observations if not value.get('observedDate') and value['subjectId'] == item.subject_id and value['month'] == item.month and value['kind'] == item.kind and value['id'] not in replaced), None)
            if (current['id'] if current else None) != item.supersedes:
                raise RevisionConflict('Observation changed; corrections must name the current observation id.')
        if item.confirmed and item.kind == 'balance' and not item.observed_date:
            subject = next(value for value in subjects if value['id'] == item.subject_id)
            if subject.get('successorOf') and item.month == previous_month(subject['startMonth']):
                predecessor = next(value for value in self.accounts() if value['id'] == subject['successorOf'])
                if predecessor['balanceSource']=='ledger':
                    ledger, issues = ledger_at(self.snapshot.state(item.month),month_end(item.month))
                    if issues:
                        raise ValueError('Predecessor ledger has unresolved historical inputs.')
                    expected = ledger['balances'].get((predecessor['id'],item.currency),Decimal(0))
                else:
                    row = self.connection.execute('SELECT payload_json FROM monthly_observations_v3 o WHERE subject_id=? AND month=? AND kind=\'balance\' AND NOT EXISTS(SELECT 1 FROM monthly_observations_v3 n WHERE n.supersedes=o.id)',(predecessor['id'],item.month)).fetchone()
                    previous = json.loads(row['payload_json']) if row else None
                    if not previous or not previous['confirmed']:
                        raise ValueError('Confirm the predecessor closing observation before carrying the successor opening.')
                    expected = Decimal(previous['amount'])
                if expected != Decimal(item.amount):
                    raise ValueError('Successor opening must equal the explicit predecessor closing carry in the same currency.')
            if subject.get('successorOf') and subject.get('startMonth') == item.month:
                # The prior month is independently confirmed as the new opening observation.
                opening = self.connection.execute('SELECT 1 FROM monthly_observations_v3 WHERE subject_id=? AND month=?', (item.subject_id, previous_month(item.month))).fetchone()
                if not opening:
                    raise ValueError('A successor requires an explicit opening observation and documented carry source.')
        self.connection.execute('INSERT INTO monthly_observations_v3 VALUES(?,?,?,?,?,?,?)',
                                (item.id, item.subject_id, item.month, item.kind, canonical(dump(item)), now_iso(), item.supersedes))
        self._invalidate()
        return dump(item)

    def report(self, month: str) -> dict:
        result = self.snapshot.report(month, self.snapshot.state(month))
        latest = self.connection.execute('SELECT id,input_revision FROM monthly_closes_v3 WHERE month=? ORDER BY revision DESC LIMIT 1', (month,)).fetchone()
        result['coverage']['confirmedCloseId'] = latest['id'] if latest else ''
        result['coverage']['needsReview'] = bool(latest and latest['input_revision'] != result['revision'])
        # A preceding changed close also invalidates the continuity of later closes.
        for close in self.connection.execute('SELECT month,input_revision FROM monthly_closes_v3 c WHERE month<? AND NOT EXISTS(SELECT 1 FROM monthly_closes_v3 n WHERE n.supersedes=c.id)', (month,)):
            if fingerprint(self.snapshot.state(close['month'])) != close['input_revision']:
                result['coverage']['needsReview'] = True
        return result

    def closes(self) -> list[dict]:
        return [{'id': row['id'], 'month': row['month'], 'revision': row['revision'], 'inputRevision': row['input_revision'],
                 'reason': row['reason'], 'confirmedAt': row['confirmed_at'], 'supersedes': row['supersedes'],
                 'report': json.loads(row['result_json'])} for row in rows(self.connection, 'monthly_closes_v3')]

    def close_month(self, item: CloseRequest) -> dict:
        if item.month >= datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m'):
            raise ValueError('Only completed calendar months can be confirmed (Asia/Shanghai).')
        # SQLite writer reservation covers read, hash check, computation and insert.
        with transaction(self.connection):
            state = self.snapshot.state(item.month)
            result = self.snapshot.report(item.month, state)
            if item.expected_revision != result['revision']:
                raise RevisionConflict('Inputs changed since preview. Refresh and review before confirming.')
            if not result['coverage']['complete']:
                raise ValueError('Month close is incomplete. Resolve its reconciliation issues first.')
            if item.month > (self.settings() or {})['cutoverMonth']:
                prior = previous_month(item.month)
                previous = self.connection.execute('SELECT input_revision FROM monthly_closes_v3 WHERE month=? ORDER BY revision DESC LIMIT 1', (prior,)).fetchone()
                if not previous or previous['input_revision'] != fingerprint(self.snapshot.state(prior)):
                    raise ValueError('Confirm or correct the previous month close first; continuity cannot skip unknown months.')
            current = self.connection.execute('SELECT id,revision FROM monthly_closes_v3 WHERE month=? ORDER BY revision DESC LIMIT 1', (item.month,)).fetchone()
            if (current['id'] if current else None) != item.supersedes:
                raise RevisionConflict('A correction must supersede the current month close.')
            close_id = str(uuid4())
            self.connection.execute('INSERT INTO monthly_closes_v3 VALUES(?,?,?,?,?,?,?,?,?)',
                                    (close_id, item.month, current['revision'] + 1 if current else 1,
                                     result['revision'], canonical(state), canonical(result), item.reason, now_iso(), item.supersedes))
            self._invalidate()
        return next(value for value in self.closes() if value['id'] == close_id)

    def generate_draft(self, arrangement_id: str, request: ArrangementDraftRequest) -> dict:
        month = request.date.strftime('%Y-%m')
        report = self.report(month)
        stored = self.connection.execute('SELECT * FROM arrangement_drafts_v3 WHERE id=?', (request.id,)).fetchone()
        if stored:
            if stored['request_json'] != canonical(dump(request)) or stored['arrangement_id'] != arrangement_id:
                raise RevisionConflict('Operation id already belongs to a different request.')
            draft = self.ledger.get_draft(request.id)
            if not draft:
                raise RevisionConflict('Generated draft was deleted. Use a new operation id after review.')
            return draft
        if report['revision'] != request.expected_revision:
            raise RevisionConflict('Inputs changed before draft generation.')
        arrangement = next((value for value in self.arrangements() if value['id'] == arrangement_id and value == arrangement_for(self.arrangements(), value['currency'], month)), None)
        if not arrangement:
            raise ValueError('No agreement is effective on this draft date.')
        currency = arrangement['currency']
        self.snapshot.require_currency(currency, request.amount)
        claims = {value['accountId']: value for value in arrangement['claims']}
        accounts = {value['id']: value for value in self.accounts()}
        ledger, issues = ledger_at(self.snapshot.state(month), request.date)
        if issues:
            raise ValueError('Historical ledger reconciliation must pass before an entitlement draft.')
        postings = []
        tags = [f'arrangement:{arrangement_id}:{arrangement["version"]}', f'operation:{request.operation}']

        def posting(account_id, side, amount):
            if amount <= 0:
                return
            postings.append({'id': f'{request.id}-{len(postings)+1}', 'accountId': account_id, 'side': side,
                             'units': canonical_decimal(amount), 'commodityCode': currency, 'cashFlowCategory': 'financing'})

        amount = Decimal(request.amount)
        if request.operation in {'funding','repayment','interest_payment','distribution_payment'}:
            cash = accounts.get(request.cash_account_id)
            claim = claims.get(request.claim_account_id)
            allowed = {'distribution'} if request.operation == 'distribution_payment' else {'interest'} if request.operation == 'interest_payment' else {'member','loan'}
            if not cash or cash['balanceSource'] != 'ledger' or cash['type'] != 'asset' or cash['subtype'] != 'cash' or currency not in cash['allowedCommodityCodes'] or not claim or claim['partyId'] != request.party_id or claim['kind'] not in allowed:
                raise ValueError('Select a matching party claim and Investment cash account.')
            if request.operation != 'funding' and amount > ledger['balances'].get((request.claim_account_id, currency), Decimal(0)):
                raise ValueError('Payment exceeds the accrued party claim; classify any excess separately.')
            funding = request.operation == 'funding'
            posting(request.cash_account_id, 'debit' if funding else 'credit', amount)
            posting(request.claim_account_id, 'credit' if funding else 'debit', amount)
            if request.from_living:
                if request.party_id != (self.settings() or {}).get('reportingPartyId'):
                    raise ValueError('Living transfers must identify the configured reporting party.')
                tags.append(f'personal-transfer:{"out" if funding else "in"}:{currency}')
        elif request.operation == 'interest':
            agreement = next((value for value in arrangement['interestAgreements'] if value['id'] == request.interest_agreement_id), None)
            if not agreement or month < agreement['fromMonth'] or (agreement.get('toMonth') and month > agreement['toMonth']):
                raise ValueError('No interest schedule is effective for this month.')
            principal_changes = any(value['account_id'] == agreement['principalAccountId'] and ledger['dates'].get(value['entry_id'], date.min).strftime('%Y-%m') == month for value in self.snapshot.state(month)['postings'])
            special = month in {agreement['fromMonth'], agreement.get('toMonth')} or principal_changes
            if special and not request.special_period_confirmed:
                raise ValueError('First/last/principal-change periods require explicit agreed interest confirmation; no proration is inferred.')
            if not special and request.amount != agreement['monthlyAmount']:
                raise ValueError('Ordinary months use the agreed fixed monthly amount.')
            tag = f'interest:{arrangement_id}:{agreement["id"]}:{month}'
            if any(tag in json.loads(entry['tags_json']) for entry in ledger['entries'].values()):
                raise ValueError('Interest for this agreement/month is already accrued.')
            tags.append(tag)
            posting(agreement['expenseAccountId'], 'debit', amount)
            posting(agreement['payableAccountId'], 'credit', amount)
        else:
            equity = arrangement.get('distributionEquityAccountId')
            if not equity:
                raise ValueError('Map a distribution equity account first.')
            posting(equity, 'debit', amount)
            scale = self.ledger.get_commodity(currency).scale
            for party_id, allocated in allocate_distribution(amount, arrangement['residualShares'], scale):
                if not allocated:
                    continue
                matches = [value for value in arrangement['claims'] if value['partyId'] == party_id and value['kind'] == 'distribution']
                if len(matches) != 1:
                    raise ValueError('Each residual beneficiary requires one distribution payable before accrual.')
                posting(matches[0]['accountId'], 'credit', allocated)
        draft = JournalEntryDraft.model_validate({'id': request.id, 'date': request.date.isoformat(), 'description': request.reason,
                                                  'source': 'arrangement-draft', 'reference': arrangement_id, 'tags': tags,
                                                  'balancingCommodityCode': currency, 'postings': postings})
        completed, _ = self.ledger.validate_draft(draft)
        if completed is None:
            raise ValueError('Generated draft failed normal Journal validation.')
        # No nested repository transaction; this is the same writer used by Journal.
        with transaction(self.connection):
            if fingerprint(self.snapshot.state(month)) != request.expected_revision:
                raise RevisionConflict('Inputs changed during draft generation.')
            stamp = now_iso()
            self.connection.execute('INSERT INTO journal_drafts_v2(id,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?)', (draft.id, canonical(dump(draft)), 'draft', stamp, stamp))
            self.connection.execute('INSERT INTO arrangement_drafts_v3 VALUES(?,?,?,?,?,?)', (request.id, arrangement_id, arrangement['version'], canonical(dump(request)), canonical(dump(draft)), request.expected_revision))
            self._invalidate()
        return self.ledger.get_draft(draft.id)


    def export_segment(self, segment: str) -> dict:
        accounts = [value for value in self.accounts() if value['segment'] == segment]
        ids = {value['id'] for value in accounts}
        if segment == 'investment':
            # Export complete aggregates even if a future bridge entry spans segments.
            entries = [entry for entry in self.ledger.list_entries() if any(value['accountId'] in ids for value in entry['postings'])]
            return {'formatVersion': 1, 'segment': segment, 'restoreCapable': False, 'accounts': accounts, 'entries': entries,
                    'arrangements': self.arrangements()}
        return {'formatVersion': 1, 'segment': segment, 'restoreCapable': False, 'accounts': accounts, 'assets': self.assets(),
                'observations': self.observations(), 'balanceRecords': self.balance_records(),
                'monthlyPlans': [dump(value) for value in self.ledger.list_monthly_plans()]}

    def export_segment_csv(self, segment: str) -> str:
        output = io.StringIO(newline='')
        if segment == 'living':
            fields = ['id','subjectId','month','kind','currency','amount','incoming','outgoing','fees','inTransit','confirmed','source','supersedes','reason','recordedAt','observedDate','note']
            values = self.snapshot.observations()
        else:
            fields = ['entryId','date','description','balancingCommodityCode','postingId','accountId','side','units','commodityCode','valuationRate','rateType','memo','tags','lotAction','lotId','lotAllocationsJson']
            values = []
            for entry in self.export_segment('investment')['entries']:
                for posting in entry['postings']:
                    values.append({'entryId':entry['id'],'date':entry['date'],'description':entry['description'],'balancingCommodityCode':entry['balancingCommodityCode'],
                                   **{key:posting.get(key,'') for key in ['accountId','side','units','commodityCode','valuationRate','rateType','memo','lotAction','lotId']},
                                   'postingId':posting['id'],'tags':'|'.join(entry['tags']),'lotAllocationsJson':canonical(posting.get('lotAllocations',[]))})
        writer = csv.DictWriter(output,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(values)
        return '\ufeff' + output.getvalue()

    def preview_living_csv(self, text: str) -> list[dict]:
        reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')),strict=True)
        required = {'subjectId','month','kind','currency','amount','incoming','outgoing','source'}
        if set(reader.fieldnames or []) != required or len(reader.fieldnames or []) != len(required):
            raise ValueError('CSV columns must be subjectId,month,kind,currency,amount,incoming,outgoing,source.')
        values = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('CSV row shape does not match its header.')
            payload = {key: value for key, value in row.items() if value != ''}
            payload.update(id=f'csv-{uuid4()}', confirmed=False)
            observation = MonthlyObservation.model_validate(payload)
            for amount in (observation.amount, observation.incoming, observation.outgoing):
                self.snapshot.require_currency(observation.currency, amount)
            month_end(observation.month)
            values.append(dump(observation))
            if len(values) > 1000:
                raise ValueError('CSV preview supports at most 1000 monthly observations.')
        if not values:
            raise ValueError('CSV contains no monthly observations.')
        return values


