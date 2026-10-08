BEGIN;

CREATE TABLE IF NOT EXISTS financial_documents (
    id BIGSERIAL PRIMARY KEY,
    document_hash TEXT NOT NULL UNIQUE,
    ticker TEXT,
    company_name TEXT,
    reporting_period TEXT,
    source_pdf TEXT,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL,
    quality_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    canonical_document JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_facts (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES financial_documents(id) ON DELETE CASCADE,
    fact_id TEXT NOT NULL,
    concept TEXT NOT NULL,
    metric TEXT NOT NULL,
    statement_type TEXT NOT NULL,
    financial_category TEXT NOT NULL,
    code TEXT,
    period TEXT,
    value TEXT,
    final_value TEXT,
    raw_value TEXT,
    candidate_value TEXT,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    source JSONB NOT NULL DEFAULT '{}'::jsonb,
    column_info JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, fact_id)
);

CREATE TABLE IF NOT EXISTS financial_validation (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES financial_documents(id) ON DELETE CASCADE,
    rule_name TEXT NOT NULL,
    formula TEXT,
    status TEXT NOT NULL,
    expected_value TEXT,
    actual_value TEXT,
    table_id TEXT,
    column_index INTEGER,
    facts_used JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_financial_facts_document
    ON financial_facts(document_id);
CREATE INDEX IF NOT EXISTS idx_financial_facts_concept_period
    ON financial_facts(concept, period);
CREATE INDEX IF NOT EXISTS idx_financial_facts_statement
    ON financial_facts(statement_type);
CREATE INDEX IF NOT EXISTS idx_financial_facts_category
    ON financial_facts(financial_category);
CREATE INDEX IF NOT EXISTS idx_financial_facts_status_confidence
    ON financial_facts(status, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_financial_facts_source
    ON financial_facts USING GIN(source);
CREATE INDEX IF NOT EXISTS idx_financial_validation_document
    ON financial_validation(document_id, status);

COMMIT;
