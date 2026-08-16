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
