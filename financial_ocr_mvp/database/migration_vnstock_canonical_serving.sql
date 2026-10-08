-- Additive canonical mapping and serving layer for the reviewed VCI pilot.
-- Legacy/OCR tables and vnstock_financial_evidence are not altered.
CREATE TABLE financial.vnstock_metric_catalog (
    canonical_metric_code TEXT PRIMARY KEY,
    metric_name_vi TEXT NOT NULL,
    metric_name_en TEXT,
    statement_type VARCHAR(32),
    unit_type TEXT,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE financial.vnstock_metric_mapping (
    mapping_id TEXT PRIMARY KEY,
    source VARCHAR(32) NOT NULL CHECK (source = 'vnstock_vci'),
    ticker_scope VARCHAR(16),
    statement_type VARCHAR(32) NOT NULL CHECK (statement_type IN ('balance_sheet', 'income_statement', 'cash_flow')),
    source_item_id TEXT,
    source_item_name TEXT,
    source_item_name_en TEXT,
    source_row_index INTEGER,
    canonical_metric_code TEXT NOT NULL REFERENCES financial.vnstock_metric_catalog(canonical_metric_code),
    mapping_version INTEGER NOT NULL DEFAULT 1,
    mapping_status VARCHAR(16) NOT NULL CHECK (mapping_status IN ('APPROVED', 'AMBIGUOUS', 'MISSING')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vnstock_metric_mapping_source_lookup
    ON financial.vnstock_metric_mapping (source, ticker_scope, statement_type, source_item_id, source_row_index);

CREATE TABLE financial.vnstock_serving_facts (
    ticker VARCHAR(16) NOT NULL,
    year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 2100),
    canonical_metric_code TEXT NOT NULL REFERENCES financial.vnstock_metric_catalog(canonical_metric_code),
    value NUMERIC NULL,
    source_evidence_id TEXT NOT NULL REFERENCES financial.vnstock_financial_evidence(evidence_id),
    mapping_id TEXT NOT NULL REFERENCES financial.vnstock_metric_mapping(mapping_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, year, canonical_metric_code)
);

CREATE INDEX idx_vnstock_serving_ticker_metric_year
    ON financial.vnstock_serving_facts (ticker, canonical_metric_code, year);

CREATE INDEX idx_vnstock_serving_year_metric_value
    ON financial.vnstock_serving_facts (year, canonical_metric_code, value);
