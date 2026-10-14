"""Read-only workspace snapshots and reference/provenance checks.

No dependency on the Journal writer or personal application operations.
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from finance_core.ledger import quantize
from finance_core.models_v2 import Account, Commodity, JournalEntryDraft, LivingAccountV2
from finance_core.models_personal import (
    ArrangementDraftRequest, FinancialAccount, FinanceSettings, InvestmentArrangement,
    MonthlyObservation, NonFinancialAsset, Party, PersonalReport,
)
from finance_core.personal_finance import calculate_report, effective_date, month_end
from finance_core.schema_migration import canonical, fingerprint, rows
from finance_core.opening_balances import EQUITY_TAG


class RevisionConflict(ValueError):
    pass


def dump(model) -> dict:
    return model.model_dump(mode='json', by_alias=True, exclude_none=True)


class PersonalFinanceSnapshot:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def _json_rows(self, table: str) -> list[dict]:
        return [json.loads(row['payload_json']) for row in rows(self.connection, table)]


    def accounts(self) -> list[dict]:
        current = {item.id: dump(item) for item in self.ledger_accounts()}
        return [{**item, **current.get(item['id'], {})} if item['balanceSource'] == 'ledger' else item
                for item in self._json_rows('financial_accounts_v3')]

    def referenced_commodity_codes(self) -> set[str]:
        """Current configuration and retained facts both prevent commodity deletion."""
        tables = {row['name'] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        codes: set[str] = set()
        columns = [
            ('price_quotes_v2', ('commodity_code', 'quote_commodity_code')),
            ('journal_entries_v2', ('balancing_commodity_code',)),
            ('postings_v2', ('commodity_code',)),
            ('lots_v2', ('commodity_code', 'cost_commodity_code')),
            ('living_accounts_v2', ('commodity_code',)), ('living_snapshots_v2', ('commodity_code',)),
            ('monthly_plans_v2', ('commodity_code',)),
            *[(table, ('currency',)) for table in ('transactions', 'holdings', 'recurring_transactions',
                                                 'living_accounts', 'living_account_snapshots', 'monthly_plans')],
        ]
        for table, names in columns:
            if table in tables:
                for name in names:
                    codes.update(row[0].strip().upper() for row in self.connection.execute(f'SELECT DISTINCT {name} FROM {table}'))
        for row in self.connection.execute('SELECT allowed_commodities_json FROM accounts_v2'):
            codes.update(code.strip().upper() for code in json.loads(row[0]))

        # Match typed reference fields, never free text such as names or memos.
        keys = {'commodityCode', 'quoteCommodityCode', 'balancingCommodityCode', 'costCommodityCode',
                'currency', 'commodity_code', 'quote_commodity_code', 'balancing_commodity_code', 'cost_commodity_code'}

        def collect(value):
            if isinstance(value, list):
                for item in value:
                    collect(item)
            elif isinstance(value, dict):
                for key, item in value.items():
                    if key in keys and isinstance(item, str):
                        codes.add(item.strip().upper())
                    elif key == 'allowedCommodityCodes':
                        codes.update(code.strip().upper() for code in item)
                    else:
                        collect(item)

        for table, names in [
            ('journal_drafts_v2', ('payload_json',)), ('recurring_entry_rules_v2', ('payload_json',)),
            ('financial_accounts_v3', ('payload_json',)), ('non_financial_assets_v3', ('payload_json',)),
            ('investment_arrangements_v3', ('payload_json',)), ('monthly_observations_v3', ('payload_json',)),
            ('legacy_living_archive_v3', ('payload_json',)), ('finance_migration_receipts_v3', ('payload_json',)),
            ('arrangement_drafts_v3', ('request_json', 'draft_json')),
        ]:
            if table in tables:
                for row in rows(self.connection, table):
                    for name in names:
                        collect(json.loads(row[name]))
        if 'monthly_closes_v3' in tables:
            for row in rows(self.connection, 'monthly_closes_v3'):
                state = json.loads(row['input_json'])
                # Even a zero/unused registry entry is part of a confirmed close's provenance.
                codes.update(item['code'].strip().upper() for item in state['commodities'])
                collect(state)
        return codes

    def account_is_referenced(self, account_id: str) -> bool:
        """Include JSON references, not just posted balances; never erase provenance."""
        tables = {row['name'] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, column in [('postings_v2', 'account_id'), ('lots_v2', 'account_id'),
                              ('monthly_observations_v3', 'subject_id')]:
            if table in tables and self.connection.execute(f'SELECT 1 FROM {table} WHERE {column}=? LIMIT 1', (account_id,)).fetchone():
                return True
        if 'financial_accounts_v3' in tables:
            account = next((item for item in self.accounts() if item['id'] == account_id), None)
            if account and account.get('legacyLivingId'):
                return True

        keys = {'accountId', 'linkedAccountId', 'successorOf', 'targetAccountId',
                'distributionEquityAccountId', 'principalAccountId', 'payableAccountId',
                'expenseAccountId', 'cashAccountId', 'claimAccountId'}

        def references(value):
            if isinstance(value, list):
                return EQUITY_TAG + account_id in value or any(references(item) for item in value)
            if isinstance(value, dict):
                return any((key in keys and item == account_id) or references(item) for key, item in value.items())
            return False

        if any(references(json.loads(row['tags_json'])) for row in rows(self.connection, 'journal_entries_v2')):
            return True

        for table, columns in [('journal_drafts_v2', ('payload_json',)), ('recurring_entry_rules_v2', ('payload_json',)),
                               ('financial_accounts_v3', ('payload_json',)), ('non_financial_assets_v3', ('payload_json',)),
                               ('investment_arrangements_v3', ('payload_json',)), ('finance_migration_receipts_v3', ('payload_json',)),
                               ('arrangement_drafts_v3', ('request_json', 'draft_json'))]:
            if table in tables and any(references(json.loads(row[column])) for row in rows(self.connection, table) for column in columns):
                return True
        if 'monthly_closes_v3' in tables:
            return any(any(item['id'] == account_id for item in json.loads(row['input_json'])['accounts'])
                       for row in rows(self.connection, 'monthly_closes_v3'))
        return False


    def parties(self) -> list[dict]:
        return self._json_rows('finance_parties_v3')


    def assets(self) -> list[dict]:
        return self._json_rows('non_financial_assets_v3')


    def arrangements(self) -> list[dict]:
        return self._json_rows('investment_arrangements_v3')


    def observations(self) -> list[dict]:
        return [{**json.loads(row['payload_json']), 'recordedAt': row['recorded_at']}
                for row in rows(self.connection, 'monthly_observations_v3')]


    def settings(self) -> dict | None:
        values = self._json_rows('finance_settings_v3')
        return values[0] if values else None


    def legacy_living(self) -> dict:
        mapped = {item.get('legacyLivingId') for item in self.accounts()}
        legacy = self.legacy_accounts()
        return {'accounts': [dump(item) for item in legacy],
                'unmappedIds': [item.id for item in legacy if item.id not in mapped],
                'archivedSources': [{'sourceTable': row['source_table'], 'sourceId': row['source_id'], 'sha256': row['sha256']}
                                    for row in rows(self.connection, 'legacy_living_archive_v3')],
                'datesInferred': False}


    @staticmethod
    def ledger_account(row: sqlite3.Row) -> Account:
        return Account.model_validate({
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "type": row["type"],
            "subtype": row["subtype"],
            "allowedCommodityCodes": json.loads(row["allowed_commodities_json"]),
            "status": row["status"],
        })


    def ledger_accounts(self) -> list[Account]:
        return [self.ledger_account(row) for row in self.connection.execute('SELECT * FROM accounts_v2 ORDER BY code,id')]

    def legacy_accounts(self) -> list[LivingAccountV2]:
        rows = self.connection.execute("SELECT * FROM living_accounts_v2 ORDER BY name,id").fetchall()
        return [LivingAccountV2.model_validate({
            "id": row["id"], "name": row["name"], "commodityCode": row["commodity_code"],
            "balance": row["balance"], "note": row["note"], "updatedAt": row["updated_at"],
        }) for row in rows]


    def commodity(self, code: str) -> Commodity | None:
        row = self.connection.execute('SELECT * FROM commodities_v2 WHERE code=?', (code.upper(),)).fetchone()
        return Commodity.model_validate(dict(row)) if row else None

    def require_party(self, party_id: str | None) -> None:
        if not party_id or party_id not in {item['id'] for item in self.parties()}:
            raise ValueError('Register the beneficiary party first.')


    def require_currency(self, code: str, amount: str | None = None) -> None:
        commodity = self.commodity(code)
        if commodity is None or commodity.kind != 'currency':
            raise ValueError('A registered currency is required.')
        if amount is not None:
            if commodity.status != 'active':
                raise ValueError('amount commodity must exist and be active.')
            if quantize(Decimal(amount), commodity.scale) != Decimal(amount):
                raise ValueError('amount contains more fractional digits than the commodity scale allows.')


    def validate_arrangement(self, item: InvestmentArrangement) -> None:
        self.require_currency(item.currency)
        for share in item.residual_shares:
            self.require_party(share.party_id)
        accounts = {value['id']: value for value in self.accounts()}
        for claim in item.claims:
            self.require_party(claim.party_id)
            account = accounts.get(claim.account_id)
            if not account or account['balanceSource'] != 'ledger' or account['type'] != 'liability' or item.currency not in account['allowedCommodityCodes']:
                raise ValueError('Claims map registered Investment liabilities in the agreement currency.')
        claim_map = {claim.account_id: claim for claim in item.claims}
        for agreement in item.interest_agreements:
            self.require_currency(item.currency, agreement.monthly_amount)
            principal, payable = claim_map.get(agreement.principal_account_id), claim_map.get(agreement.payable_account_id)
            expense = accounts.get(agreement.expense_account_id)
            if not principal or not payable or principal.party_id != agreement.party_id or payable.party_id != agreement.party_id or principal.kind not in {'loan', 'member'} or payable.kind != 'interest' or not expense or expense['type'] != 'expense' or expense['balanceSource'] != 'ledger' or item.currency not in expense['allowedCommodityCodes']:
                raise ValueError('Interest requires explicit same-party principal, interest payable and Investment expense mappings.')
        if item.distribution_equity_account_id:
            account = accounts.get(item.distribution_equity_account_id)
            if not account or account['type'] != 'equity' or item.currency not in account['allowedCommodityCodes']:
                raise ValueError('Distribution requires a registered equity account.')


    def state(self, month: str) -> dict:
        end = month_end(month)
        state = {'settings': self.settings(), 'parties': self.parties(), 'accounts': self.accounts(),
                 'assets': self.assets(), 'arrangements': self.arrangements(), 'observations': self.observations(),
                 'commodities': rows(self.connection, 'commodities_v2'), 'entries': rows(self.connection, 'journal_entries_v2'),
                 'postings': rows(self.connection, 'postings_v2'), 'lots': rows(self.connection, 'lots_v2'),
                 'movements': rows(self.connection, 'lot_movements_v2'), 'quotes': rows(self.connection, 'price_quotes_v2')}
        def within(value):
            try:
                return effective_date(value) <= end
            except (ValueError, TypeError):
                return True  # Unclassifiable data remains an explicit failure, not silent omission.
        state['entries'] = [value for value in state['entries'] if within(value['date'])]
        ids = {value['id'] for value in state['entries']}
        state['postings'] = [value for value in state['postings'] if value['entry_id'] in ids]
        state['movements'] = [value for value in state['movements'] if value['entry_id'] in ids]
        lot_ids = {value['lot_id'] for value in state['movements']}
        state['lots'] = [{key: value for key, value in lot.items() if key not in {'remaining_units','remaining_cost'}} for lot in state['lots'] if lot['id'] in lot_ids]
        state['quotes'] = [value for value in state['quotes'] if within(value['as_of'])]
        # v1 close/reconciliation inputs remain month-end facts, never dated readouts.
        state['observations'] = [value for value in state['observations'] if value['month'] <= month and not value.get('observedDate')]
        state['arrangements'] = [value for value in state['arrangements'] if value['fromMonth'] <= month]
        state['interestConfirmations'] = [json.loads(row['request_json']) for row in rows(self.connection,'arrangement_drafts_v3') if row['id'] in ids and json.loads(row['request_json'])['operation'] == 'interest']
        state['unmappedLegacyLiving'] = self.legacy_living()['unmappedIds']
        return state


    def report(self, month: str, state: dict) -> dict:
        revision = fingerprint(state)
        result = calculate_report(month, state, revision)
        if state['unmappedLegacyLiving']:
            result['issues'].append({'code': 'LEGACY_LIVING_MAPPING_REQUIRED', 'subjectId': 'legacy', 'message': 'Resolve legacy Living ids explicitly; names and timestamps are not migration evidence.'})
            result['coverage']['complete'] = False
            for currency in result['currencies']:
                currency['totals']['personalNetWorth'] = None
        return result


    def validate_generated_draft(self, draft: JournalEntryDraft) -> None:
        row = self.connection.execute('SELECT * FROM arrangement_drafts_v3 WHERE id=?', (draft.id,)).fetchone()
        if row is None:
            return
        if row['draft_json'] != canonical(dump(draft)) or row['input_revision'] != fingerprint(self.state(effective_date(draft.date).strftime('%Y-%m'))):
            raise RevisionConflict('Generated entitlement draft is changed or stale; regenerate after reviewing current inputs.')


    def validate_restored_state(self) -> None:
        """Hash integrity is not semantic validation; enforce the current finance shapes too."""
        for table, model in [('finance_parties_v3',Party),('financial_accounts_v3',FinancialAccount),
                             ('non_financial_assets_v3',NonFinancialAsset),('finance_settings_v3',FinanceSettings),
                             ('investment_arrangements_v3',InvestmentArrangement),('monthly_observations_v3',MonthlyObservation)]:
            for row in rows(self.connection,table):
                value=json.loads(row['payload_json'])
                model.model_validate(value)
                if table != 'finance_settings_v3' and row['id'] != value['id']:
                    raise ValueError('Restored finance identity disagrees with its payload.')
                if table == 'investment_arrangements_v3' and row['version'] != value['version']:
                    raise ValueError('Restored agreement version disagrees with its payload.')
                if table == 'monthly_observations_v3' and (row['month']!=value['month'] or row['kind']!=value['kind'] or row['subject_id']!=value['subjectId'] or row['supersedes']!=value.get('supersedes')):
                    raise ValueError('Restored observation identity disagrees with its payload.')
        parties = {item['id'] for item in self.parties()}
        accounts = {item['id']:item for item in self.accounts()}
        assets = {item['id']:item for item in self.assets()}
        if {item.id for item in self.ledger_accounts()} != {item['id'] for item in self.accounts() if item['balanceSource']=='ledger'}:
            raise ValueError('Restored ledger/registry identities do not agree.')
        for item in self.accounts():
            registry = self.connection.execute('SELECT * FROM financial_accounts_v3 WHERE id=?',(item['id'],)).fetchone()
            if registry['ledger_account_id'] != (item['id'] if item['balanceSource']=='ledger' else None) or registry['legacy_living_id'] != item.get('legacyLivingId'):
                raise ValueError('Restored account measurement identity is inconsistent.')
            if item.get('ownerPartyId') and item['ownerPartyId'] not in parties:
                raise ValueError('Restored account beneficiary is missing.')
            if item['segment']=='living':
                self.require_party(item.get('ownerPartyId'))
                if len(item['allowedCommodityCodes'])!=1:
                    raise ValueError('Restored monthly snapshot account must have one currency.')
                self.require_currency(item['allowedCommodityCodes'][0])
            for code in item['allowedCommodityCodes']:
                if self.commodity(code) is None:
                    raise ValueError('Restored account commodity is missing.')
        if self.settings():
            self.require_party(self.settings()['reportingPartyId'])
        linked = set()
        for asset in assets.values():
            self.require_party(asset['ownerPartyId'])
            self.require_currency(asset['currency'],asset['purchaseCost'])
            account = accounts.get(asset.get('linkedAccountId'))
            if asset.get('linkedAccountId'):
                if not account or account['segment']!='living' or account['type']!='asset' or account['allowedCommodityCodes']!=[asset['currency']] or account['ownerPartyId']!=asset['ownerPartyId'] or account['id'] in linked:
                    raise ValueError('Restored linked asset measurement authority is inconsistent.')
                linked.add(account['id'])
        agreements = self.arrangements()
        for value in agreements:
            self.validate_arrangement(InvestmentArrangement.model_validate(value))
        currencies = {}
        for value in sorted(agreements,key=lambda item:item['version']):
            previous = currencies.get(value['currency'])
            if value['version'] != (previous['version']+1 if previous else 1) or (previous and (value['id']!=previous['id'] or value['fromMonth']<=previous['fromMonth'])):
                raise ValueError('Restored agreement versions must form one dated pool per currency.')
            currencies[value['currency']]=value
        observations = {item['id']:item for item in self._json_rows('monthly_observations_v3')}
        observation_groups = {}
        for value in observations.values():
            previous = observations.get(value.get('supersedes'))
            if value.get('supersedes') and not previous:
                raise ValueError('Restored observation correction source is missing.')
            if previous and any(previous.get(key) != value.get(key) for key in ('subjectId','kind','month','currency','observedDate')):
                raise ValueError('Restored observation correction changed its identity.')
            subject = assets.get(value['subjectId']) if value['kind']=='valuation' else accounts.get(value['subjectId'])
            if value['kind']!='transfer' and subject is None:
                raise ValueError('Restored observation subject is missing.')
            if value['kind']=='balance' and (subject['balanceSource']!='monthly_snapshot' or subject['allowedCommodityCodes']!=[value['currency']]):
                raise ValueError('Restored balance conflicts with its measurement authority.')
            if value['kind']=='valuation' and subject['currency']!=value['currency']:
                raise ValueError('Restored valuation currency conflicts with its asset.')
            for field in ('amount','incoming','outgoing','fees','inTransit'):
                self.require_currency(value['currency'],value.get(field))
            observation_groups.setdefault((value['subjectId'],value['month'],value['kind'],value.get('observedDate')),[]).append(value)
        for group in observation_groups.values():
            replaced={value['supersedes'] for value in group if value.get('supersedes')}
            heads=[value for value in group if value['id'] not in replaced]
            if not heads or (not group[0].get('observedDate') and len(heads)!=1):
                raise ValueError('Restored monthly observations require one correction chain per identity.')
            seen=set()
            for current in heads:
                while current:
                    if current['id'] in seen:
                        raise ValueError('Restored observation correction chain is cyclic or merged.')
                    seen.add(current['id'])
                    current=observations.get(current.get('supersedes'))
            if len(seen)!=len(group):
                raise ValueError('Restored observation correction chain is disconnected.')
        for row in rows(self.connection,'arrangement_drafts_v3'):
            request=ArrangementDraftRequest.model_validate(json.loads(row['request_json']))
            draft=JournalEntryDraft.model_validate(json.loads(row['draft_json']))
            if request.id!=row['id'] or draft.id!=row['id'] or draft.reference!=row['arrangement_id']:
                raise ValueError('Restored generated draft provenance is inconsistent.')
        for row in rows(self.connection,'legacy_living_archive_v3'):
            if fingerprint(json.loads(row['payload_json'])) != row['sha256']:
                raise ValueError('Restored legacy archive provenance hash is invalid.')
        closes={row['id']:row for row in rows(self.connection,'monthly_closes_v3')}
        for row in closes.values():
            state, result = json.loads(row['input_json']),json.loads(row['result_json'])
            PersonalReport.model_validate(result)
            previous=closes.get(row['supersedes'])
            if row['revision']!=(previous['revision']+1 if previous else 1) or (previous and previous['month']!=row['month']) or result['month']!=row['month'] or not result['coverage']['complete']:
                raise ValueError('Restored month close correction identity is inconsistent.')
            try:
                recomputed=self.report(row['month'],state)
            except (KeyError,TypeError,ValueError) as error:
                raise ValueError('Restored close inputs are not reproducible.') from error
            if fingerprint(state)!=row['input_revision'] or canonical(recomputed) != canonical(result):
                raise ValueError('Restored close inputs and deterministic result do not agree.')

