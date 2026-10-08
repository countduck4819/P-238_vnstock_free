-- Replace :document_id with the imported financial_documents.id when needed.

-- 1. Revenue for FPT Q1 2015.
-- Current canonical output has no ticker field yet, so period/concept are used.
SELECT d.ticker, d.company_name, f.metric, f.concept, f.value,
       f.confidence, f.status, f.source
FROM financial_facts f
JOIN financial_documents d ON d.id = f.document_id
WHERE f.concept = 'revenue'
  AND f.period ILIKE '%2015%'
  AND (d.ticker = 'FPT' OR d.ticker IS NULL)
ORDER BY f.source->>'page', (f.source->>'column')::int;

-- 2. All expense facts.
SELECT f.metric, f.concept, f.value, f.period,
       f.confidence, f.status, f.source
FROM financial_facts f
WHERE f.financial_category = 'expense'
ORDER BY f.period, f.concept, f.source->>'page';

-- 3. Facts extracted from page 5.
SELECT f.fact_id, f.metric, f.concept, f.value,
       f.raw_value, f.candidate_value, f.confidence, f.status, f.source
FROM financial_facts f
WHERE (f.source->>'page')::int = 5
ORDER BY (f.source->>'table'), (f.source->>'row')::int,
         (f.source->>'column')::int;

-- 4. High-confidence facts.
SELECT f.metric, f.concept, f.value, f.period,
       f.confidence, f.status, f.source
FROM financial_facts f
WHERE f.confidence >= 0.90
ORDER BY f.confidence DESC, f.period, f.concept;

-- 5. Validation results.
SELECT rule_name, formula, status, expected_value,
       actual_value, table_id, column_index, facts_used
FROM financial_validation
WHERE document_id = :document_id
ORDER BY status, rule_name, column_index;
