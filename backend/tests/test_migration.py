import sqlite3

from finance_core.database import FinanceRepository, connect
from finance_core.migration import audit_legacy_transactions, extract_legacy_bundle


def test_legacy_extract_excludes_context_and_reports(tmp_path):
    source = sqlite3.connect(tmp_path / "legacy.sqlite3")
    source.row_factory = sqlite3.Row
    source.executescript("""
      CREATE TABLE transactions (id TEXT, date TEXT, account TEXT, source TEXT, type TEXT, category TEXT, asset_symbol TEXT, amount REAL, currency TEXT, note TEXT, ref TEXT, raw_data TEXT, account_code TEXT, account_name TEXT, responsibility_center TEXT, debit REAL, credit REAL);
      CREATE TABLE holdings (id TEXT, symbol TEXT, name TEXT, asset_type TEXT, quantity REAL, average_cost REAL, current_price REAL, currency TEXT, sector TEXT, thesis_note TEXT);
      CREATE TABLE account_options (account TEXT, sort_order INTEGER);
      CREATE TABLE recurring_transactions (id TEXT, name TEXT, account TEXT, debit REAL, credit REAL, currency TEXT, description TEXT, frequency TEXT, day_of_month INTEGER, start_date TEXT, enabled INTEGER, generated_periods_json TEXT);
      CREATE TABLE living_accounts (id TEXT, name TEXT, currency TEXT, balance REAL, note TEXT, updated_at TEXT);
      CREATE TABLE living_account_snapshots (id TEXT, account_id TEXT, balance REAL, currency TEXT, recorded_at TEXT);
      CREATE TABLE monthly_plans (id TEXT, kind TEXT, name TEXT, amount REAL, currency TEXT, category TEXT, recurring_monthly INTEGER, day_of_month INTEGER, start_date TEXT, note TEXT);
      CREATE TABLE analysis_reports (id TEXT, snapshot_json TEXT);
      CREATE TABLE validation_reports (id TEXT, snapshot_json TEXT);
      CREATE TABLE knowledge_notes (id TEXT, content TEXT);
      INSERT INTO holdings VALUES ('h1','DEMO','Synthetic','ETF',1,100,110,'CNY','Demo','Synthetic');
      INSERT INTO transactions VALUES ('t1','2026-08-17','1001 Cash','Manual','Deposit','Synthetic','',100,'CNY','Synthetic','',NULL,NULL,NULL,NULL,100,0);
      INSERT INTO analysis_reports VALUES ('private-report','{}');
      INSERT INTO validation_reports VALUES ('private-validation','{}');
      INSERT INTO knowledge_notes VALUES ('private-context','excluded');
    """)
    bundle = extract_legacy_bundle(source)
    assert [item.id for item in bundle.holdings] == ["h1"]
    assert not hasattr(bundle, "analysis_reports")
    audit = audit_legacy_transactions(source)
    assert audit["legacyRows"] == 1
    assert audit["automaticallyWrittenToV2"] == 0
    assert audit["requiresHumanCompletion"] == 1
    target = connect(tmp_path / "core.sqlite3")
    assert [row[0] for row in target.execute("SELECT version FROM schema_migrations ORDER BY version")] == [1, 2]
    FinanceRepository(target).replace_bundle(bundle.model_dump(by_alias=True))
    assert FinanceRepository(target).export_bundle()["holdings"][0]["id"] == "h1"
