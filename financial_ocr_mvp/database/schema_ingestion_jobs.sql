-- Additive migration for batch ingestion. It does not alter existing tables.
CREATE SCHEMA IF NOT EXISTS financial;

CREATE TABLE IF NOT EXISTS financial.financial_ingestion_jobs (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 2100),
    quarter INTEGER CHECK (quarter IS NULL OR quarter BETWEEN 1 AND 4),
    report_type TEXT NOT NULL,
    source_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'retry')),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_financial_ingestion_jobs_status
    ON financial.financial_ingestion_jobs (status);
CREATE INDEX IF NOT EXISTS idx_financial_ingestion_jobs_ticker_period
    ON financial.financial_ingestion_jobs (ticker, year, quarter);
