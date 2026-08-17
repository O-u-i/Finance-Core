CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS app_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS transactions (
  id TEXT PRIMARY KEY, date TEXT NOT NULL, account TEXT NOT NULL, source TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('Deposit','Withdrawal','Buy','Sell','Dividend','Transfer','Fee')),
  category TEXT NOT NULL, asset_symbol TEXT NOT NULL, amount REAL NOT NULL,
  currency TEXT NOT NULL, note TEXT NOT NULL, ref TEXT NOT NULL, raw_data TEXT,
  account_code TEXT, account_name TEXT, responsibility_center TEXT, debit REAL, credit REAL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date DESC, id);

CREATE TABLE IF NOT EXISTS holdings (
  id TEXT PRIMARY KEY, symbol TEXT NOT NULL, name TEXT NOT NULL,
  asset_type TEXT NOT NULL CHECK (asset_type IN ('Stock','ETF','Bond','Cash Equivalent','Fund','Other')),
  quantity REAL NOT NULL, average_cost REAL NOT NULL, current_price REAL NOT NULL,
  currency TEXT NOT NULL, sector TEXT NOT NULL, thesis_note TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS account_options (
  account TEXT PRIMARY KEY, sort_order INTEGER NOT NULL CHECK (sort_order >= 0)
) STRICT;

CREATE TABLE IF NOT EXISTS recurring_transactions (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, account TEXT NOT NULL, debit REAL NOT NULL,
  credit REAL NOT NULL, currency TEXT NOT NULL, description TEXT NOT NULL,
  frequency TEXT NOT NULL CHECK (frequency = 'monthly'),
  day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
  start_date TEXT NOT NULL, enabled INTEGER NOT NULL CHECK (enabled IN (0,1)),
  generated_periods_json TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS living_accounts (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, currency TEXT NOT NULL, balance REAL NOT NULL,
  note TEXT NOT NULL, updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS living_account_snapshots (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL, balance REAL NOT NULL,
  currency TEXT NOT NULL, recorded_at TEXT NOT NULL,
  FOREIGN KEY (account_id) REFERENCES living_accounts(id) ON DELETE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS monthly_plans (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('income','expense')),
  name TEXT NOT NULL, amount REAL NOT NULL, currency TEXT NOT NULL, category TEXT NOT NULL,
  recurring_monthly INTEGER NOT NULL CHECK (recurring_monthly IN (0,1)),
  day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
  start_date TEXT NOT NULL, note TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS undo_operations (
  token TEXT PRIMARY KEY, action TEXT NOT NULL, resource TEXT NOT NULL,
  resource_id TEXT, inverse_json TEXT NOT NULL, created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL, consumed_at TEXT
) STRICT;

INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
VALUES (1, 'finance-core-v1', '1970-01-01T00:00:00.000Z');

CREATE TABLE IF NOT EXISTS commodities_v2 (
  code TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('currency','security','other')),
  scale INTEGER NOT NULL CHECK (scale BETWEEN 0 AND 18),
  name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','inactive'))
) STRICT;

CREATE TABLE IF NOT EXISTS accounts_v2 (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('asset','liability','equity','income','expense')),
  subtype TEXT NOT NULL,
  allowed_commodities_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','inactive'))
) STRICT;

CREATE TABLE IF NOT EXISTS price_quotes_v2 (
  id TEXT PRIMARY KEY,
  commodity_code TEXT NOT NULL,
  quote_commodity_code TEXT NOT NULL,
  price TEXT NOT NULL,
  as_of TEXT NOT NULL,
  source TEXT NOT NULL,
  FOREIGN KEY (commodity_code) REFERENCES commodities_v2(code),
  FOREIGN KEY (quote_commodity_code) REFERENCES commodities_v2(code)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_price_quotes_v2_latest
  ON price_quotes_v2(commodity_code, quote_commodity_code, as_of DESC, id DESC);

CREATE TABLE IF NOT EXISTS journal_drafts_v2 (
  id TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft','posted')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  posted_entry_id TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS journal_entries_v2 (
  id TEXT PRIMARY KEY,
  date TEXT NOT NULL,
  description TEXT NOT NULL,
  payee TEXT NOT NULL,
  source TEXT NOT NULL,
  reference TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  balancing_commodity_code TEXT NOT NULL,
  posted_at TEXT NOT NULL,
  reversal_of TEXT,
  FOREIGN KEY (balancing_commodity_code) REFERENCES commodities_v2(code),
  FOREIGN KEY (reversal_of) REFERENCES journal_entries_v2(id)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_journal_entries_v2_date ON journal_entries_v2(date DESC, id);

CREATE TABLE IF NOT EXISTS postings_v2 (
  id TEXT PRIMARY KEY,
  entry_id TEXT NOT NULL,
  sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
  account_id TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('debit','credit')),
  units TEXT NOT NULL,
  commodity_code TEXT NOT NULL,
  valuation_rate TEXT NOT NULL,
  valuation_amount TEXT NOT NULL,
  rate_type TEXT NOT NULL CHECK (rate_type IN ('exchange','price','cost')),
  memo TEXT NOT NULL,
  cash_flow_category TEXT NOT NULL CHECK (cash_flow_category IN ('income','expense','investment','financing','transfer','other')),
  lot_json TEXT,
  UNIQUE (entry_id, sort_order),
  FOREIGN KEY (entry_id) REFERENCES journal_entries_v2(id) ON DELETE RESTRICT,
  FOREIGN KEY (account_id) REFERENCES accounts_v2(id),
  FOREIGN KEY (commodity_code) REFERENCES commodities_v2(code)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_postings_v2_entry ON postings_v2(entry_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_postings_v2_account ON postings_v2(account_id, commodity_code);

CREATE TABLE IF NOT EXISTS lots_v2 (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  commodity_code TEXT NOT NULL,
  acquired_date TEXT NOT NULL,
  original_units TEXT NOT NULL,
  remaining_units TEXT NOT NULL,
  original_cost TEXT NOT NULL,
  remaining_cost TEXT NOT NULL,
  cost_commodity_code TEXT NOT NULL,
  source_entry_id TEXT NOT NULL,
  FOREIGN KEY (account_id) REFERENCES accounts_v2(id),
  FOREIGN KEY (commodity_code) REFERENCES commodities_v2(code),
  FOREIGN KEY (cost_commodity_code) REFERENCES commodities_v2(code),
  FOREIGN KEY (source_entry_id) REFERENCES journal_entries_v2(id)
) STRICT;

CREATE TABLE IF NOT EXISTS lot_movements_v2 (
  id TEXT PRIMARY KEY,
  lot_id TEXT NOT NULL,
  entry_id TEXT NOT NULL,
  posting_id TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('acquire','dispose','restore','reverse-acquire')),
  units TEXT NOT NULL,
  cost TEXT NOT NULL,
  FOREIGN KEY (lot_id) REFERENCES lots_v2(id),
  FOREIGN KEY (entry_id) REFERENCES journal_entries_v2(id),
  FOREIGN KEY (posting_id) REFERENCES postings_v2(id)
) STRICT;

CREATE TABLE IF NOT EXISTS recurring_entry_rules_v2 (
  id TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  enabled INTEGER NOT NULL CHECK (enabled IN (0,1)),
  day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
  start_date TEXT NOT NULL,
  generated_periods_json TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS living_accounts_v2 (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  commodity_code TEXT NOT NULL,
  balance TEXT NOT NULL,
  note TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (commodity_code) REFERENCES commodities_v2(code)
) STRICT;

CREATE TABLE IF NOT EXISTS living_snapshots_v2 (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  balance TEXT NOT NULL,
  commodity_code TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  FOREIGN KEY (account_id) REFERENCES living_accounts_v2(id) ON DELETE RESTRICT,
  FOREIGN KEY (commodity_code) REFERENCES commodities_v2(code)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_living_snapshots_v2_time ON living_snapshots_v2(recorded_at,id);

CREATE TABLE IF NOT EXISTS monthly_plans_v2 (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('income','expense')),
  name TEXT NOT NULL,
  amount TEXT NOT NULL,
  commodity_code TEXT NOT NULL,
  category TEXT NOT NULL,
  recurring_monthly INTEGER NOT NULL CHECK (recurring_monthly IN (0,1)),
  day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
  start_date TEXT NOT NULL,
  note TEXT NOT NULL,
  FOREIGN KEY (commodity_code) REFERENCES commodities_v2(code)
) STRICT;

CREATE TABLE IF NOT EXISTS undo_operations_v2 (
  token TEXT PRIMARY KEY,
  snapshot_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  consumed_at TEXT
) STRICT;

INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
VALUES (2, 'finance-core-v2-ledger', '1970-01-01T00:00:00.000Z');
