-- Additive VCI evidence layer.  No legacy table is altered.
CREATE TABLE financial.vnstock_financial_evidence (
    evidence_id TEXT PRIMARY KEY,
    ticker VARCHAR(16) NOT NULL,
    year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 2100),
    statement_type VARCHAR(32) NOT NULL CHECK (statement_type IN ('balance_sheet', 'income_statement', 'cash_flow')),
    source VARCHAR(32) NOT NULL CHECK (source = 'vnstock_vci'),
    source_item_id TEXT,
    source_item_name TEXT,
    source_item_name_en TEXT,
    source_row_index INTEGER NOT NULL,
    value NUMERIC NULL,
    raw_snapshot_id TEXT NOT NULL,
    source_file TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vnstock_evidence_ticker_year_statement
    ON financial.vnstock_financial_evidence (ticker, year, statement_type);

CREATE INDEX idx_vnstock_evidence_ticker_item_year
    ON financial.vnstock_financial_evidence (ticker, source_item_id, year);

CREATE INDEX idx_vnstock_evidence_item_year
    ON financial.vnstock_financial_evidence (source_item_id, year);
