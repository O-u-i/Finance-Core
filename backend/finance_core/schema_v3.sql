-- Additive ledger migration; existing journal/account columns remain unchanged.
CREATE TABLE financial_accounts_v3 (
  id TEXT PRIMARY KEY,
  ledger_account_id TEXT UNIQUE REFERENCES accounts_v2(id),
  legacy_living_id TEXT UNIQUE REFERENCES living_accounts_v2(id),
  payload_json TEXT NOT NULL
) STRICT;
CREATE UNIQUE INDEX financial_account_code_v3 ON financial_accounts_v3(json_extract(payload_json,'$.code'));
CREATE TABLE finance_parties_v3 (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL) STRICT;
CREATE TABLE finance_settings_v3 (id TEXT PRIMARY KEY CHECK(id='personal'), payload_json TEXT NOT NULL) STRICT;
CREATE TABLE non_financial_assets_v3 (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL) STRICT;
CREATE TABLE investment_arrangements_v3 (
  id TEXT NOT NULL, version INTEGER NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(id,version)
) STRICT;
-- Balance payloads may include observedDate (actual YYYY-MM-DD); month is its
-- query bucket, not a month-end claim. Older payloads retain an unknown actual
-- date. Multiple dated roots are allowed; explicit corrections stay immutable.
CREATE TABLE monthly_observations_v3 (
  id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, month TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('balance','valuation','transfer')),
  payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL,
  supersedes TEXT UNIQUE REFERENCES monthly_observations_v3(id)
) STRICT;
CREATE INDEX monthly_observations_v3_subject ON monthly_observations_v3(subject_id,month,kind);
CREATE TABLE monthly_closes_v3 (
  id TEXT PRIMARY KEY, month TEXT NOT NULL, revision INTEGER NOT NULL,
  input_revision TEXT NOT NULL, input_json TEXT NOT NULL, result_json TEXT NOT NULL,
  reason TEXT NOT NULL, confirmed_at TEXT NOT NULL,
  supersedes TEXT UNIQUE REFERENCES monthly_closes_v3(id),
  UNIQUE(month,revision)
) STRICT;
CREATE TABLE legacy_living_archive_v3 (
  source_table TEXT NOT NULL, source_id TEXT NOT NULL, payload_json TEXT NOT NULL,
  sha256 TEXT NOT NULL, archived_at TEXT NOT NULL,
  PRIMARY KEY(source_table,source_id)
) STRICT;
CREATE TABLE finance_migration_receipts_v3 (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL) STRICT;
CREATE TABLE arrangement_drafts_v3 (
  id TEXT PRIMARY KEY, arrangement_id TEXT NOT NULL, arrangement_version INTEGER NOT NULL,
  request_json TEXT NOT NULL, draft_json TEXT NOT NULL, input_revision TEXT NOT NULL,
  UNIQUE(arrangement_id,arrangement_version,id),
  FOREIGN KEY(arrangement_id,arrangement_version) REFERENCES investment_arrangements_v3(id,version)
) STRICT;
-- Closed facts/provenance are append-only. Restore inserts into an empty target.
CREATE TRIGGER monthly_close_no_update BEFORE UPDATE ON monthly_closes_v3 BEGIN SELECT RAISE(ABORT,'Month closes are immutable'); END;
CREATE TRIGGER monthly_close_no_delete BEFORE DELETE ON monthly_closes_v3 BEGIN SELECT RAISE(ABORT,'Month closes are immutable'); END;
CREATE TRIGGER observation_no_update BEFORE UPDATE ON monthly_observations_v3 BEGIN SELECT RAISE(ABORT,'Observations are immutable'); END;
CREATE TRIGGER observation_no_delete BEFORE DELETE ON monthly_observations_v3 BEGIN SELECT RAISE(ABORT,'Observations are immutable'); END;
CREATE TRIGGER arrangement_no_update BEFORE UPDATE ON investment_arrangements_v3 BEGIN SELECT RAISE(ABORT,'Agreement versions are immutable'); END;
CREATE TRIGGER arrangement_no_delete BEFORE DELETE ON investment_arrangements_v3 BEGIN SELECT RAISE(ABORT,'Agreement versions are immutable'); END;
CREATE TRIGGER archive_no_update BEFORE UPDATE ON legacy_living_archive_v3 BEGIN SELECT RAISE(ABORT,'Legacy archive is immutable'); END;
CREATE TRIGGER archive_no_delete BEFORE DELETE ON legacy_living_archive_v3 BEGIN SELECT RAISE(ABORT,'Legacy archive is immutable'); END;
