-- Financial schema smoke tests.

-- Count documents and facts.
SELECT COUNT(*) AS documents FROM financial.financial_documents;
SELECT COUNT(*) AS facts FROM financial.financial_facts;

-- Revenue for FPT/Q1 2015. Until ticker metadata is populated, filter by concept/period.
SELECT d.ticker, d.company_name, f.metric, f.concept, f.value,
       f.confidence, f.status, f.source
FROM financial.financial_facts f
JOIN financial.financial_documents d ON d.id = f.document_id
WHERE f.concept = 'revenue'
  AND f.period ILIKE '%2015%'
ORDER BY (f.source->>'page')::int, (f.source->>'column')::int;

-- All expenses.
SELECT f.metric, f.concept, f.value, f.period,
       f.confidence, f.status, f.raw_value, f.candidate_value
FROM financial.financial_facts f
WHERE f.financial_category = 'expense'
ORDER BY f.period, f.concept, (f.source->>'row')::int;

-- Facts from page 5/source trace.
SELECT f.fact_id, f.metric, f.concept, f.value,
       f.raw_value, f.candidate_value, f.confidence, f.status, f.source
FROM financial.financial_facts f
WHERE (f.source->>'page')::int = 5
ORDER BY (f.source->>'table'), (f.source->>'row')::int,
         (f.source->>'column')::int;

-- Candidate facts needing review.
SELECT f.fact_id, f.metric, f.value, f.raw_value,
       f.candidate_value, f.confidence, f.status, f.source
FROM financial.financial_facts f
WHERE f.status IN ('candidate', 'needs_review')
ORDER BY f.confidence DESC, f.fact_id;

-- Validation pass/fail/not_applicable.
SELECT rule_name, status, expected_value, actual_value, details
FROM financial.financial_validation
ORDER BY status, rule_name;
