"""Read-only combined BANK + CORPORATE numerical-serving MVP gate."""
from __future__ import annotations
import csv, json, os, re
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[2]; META=ROOT/'data'/'vnstock'/'metadata'
REPORT=META/'numerical_serving_mvp_validation_report.md'; SUMMARY=META/'numerical_serving_mvp_validation_summary.json'
BANK_METRICS=['net_fee_and_commission_income','net_interest_income','net_profit','profit_before_tax','provision_for_credit_losses','total_assets','total_equity']
CORP_METRICS=['net_profit','net_revenue','profit_before_tax','total_assets','total_liabilities']
def url():
 m=re.search(r'^DATABASE_URL\s*=\s*(.*)$',(ROOT/'.env').read_text(encoding='utf-8'),re.M); return os.environ.get('DATABASE_URL') or m.group(1).strip().strip('"\'')
def main():
 tax=list(csv.DictReader((META/'financial_sector_taxonomy.csv').open(encoding='utf-8'))); banks=sorted(x['ticker'] for x in tax if x['financial_sector_family']=='BANK'); corps=sorted(x['ticker'] for x in tax if x['financial_sector_family']=='CORPORATE'); scope=banks+corps
 with psycopg.connect(url(),connect_timeout=5,row_factory=dict_row) as c:
  bank=dict(c.execute('''select count(*) rows,count(distinct ticker) tickers,count(distinct canonical_metric_code) metrics,min(year) year_min,max(year) year_max from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code=any(%s)''',(banks,BANK_METRICS)).fetchone())
  corp=dict(c.execute('''select count(*) rows,count(distinct ticker) tickers,count(distinct canonical_metric_code) metrics,min(year) year_min,max(year) year_max from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code=any(%s)''',(corps,CORP_METRICS)).fetchone())
  combined=dict(c.execute('''select count(*) rows,count(distinct ticker) tickers,count(distinct canonical_metric_code) metrics,min(year) year_min,max(year) year_max from financial.vnstock_serving_facts where(ticker=any(%s) and canonical_metric_code=any(%s))or(ticker=any(%s) and canonical_metric_code=any(%s))''',(banks,BANK_METRICS,corps,CORP_METRICS)).fetchone())
  metric_rows=[dict(x) for x in c.execute('''select canonical_metric_code,count(*) rows,count(distinct ticker) tickers,min(year) year_min,max(year) year_max from financial.vnstock_serving_facts where(ticker=any(%s) and canonical_metric_code=any(%s))or(ticker=any(%s) and canonical_metric_code=any(%s)) group by 1 order by 1''',(banks,BANK_METRICS,corps,CORP_METRICS)).fetchall()]
  integrity=dict(c.execute('''select count(*) filter(where e.evidence_id is null) orphan_evidence,count(*) filter(where m.mapping_id is null) orphan_mapping,count(*) filter(where not(s.value is not distinct from e.value)) value_mismatch,count(*) filter(where s.ticker<>e.ticker or s.year<>e.year) provenance_key_mismatch from financial.vnstock_serving_facts s left join financial.vnstock_financial_evidence e on e.evidence_id=s.source_evidence_id left join financial.vnstock_metric_mapping m on m.mapping_id=s.mapping_id where s.ticker=any(%s)''',(scope,)).fetchone())
  dup_serving=c.execute('''select count(*) n from(select ticker,year,canonical_metric_code from financial.vnstock_serving_facts where ticker=any(%s) group by 1,2,3 having count(*)>1)x''',(scope,)).fetchone()['n']
  dup_mapping=c.execute('''select count(*) n from(select m.ticker_scope,m.canonical_metric_code from financial.vnstock_metric_mapping m where m.mapping_id in(select distinct mapping_id from financial.vnstock_serving_facts where ticker=any(%s)) group by 1,2 having count(*)>1)x''',(scope,)).fetchone()['n']
  invalid_mapping=c.execute('''select count(*) n from financial.vnstock_serving_facts s join financial.vnstock_metric_mapping m on m.mapping_id=s.mapping_id where s.ticker=any(%s) and m.mapping_status<>'APPROVED' ''',(scope,)).fetchone()['n']
  corp_forbidden=c.execute('''select count(*) n from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code in('total_equity','operating_cash_flow')''',(corps,)).fetchone()['n']
  zero_without_zero_evidence=c.execute('''select count(*) n from financial.vnstock_serving_facts s join financial.vnstock_financial_evidence e on e.evidence_id=s.source_evidence_id where s.ticker=any(%s) and s.value=0 and(e.value is null or e.value<>0)''',(scope,)).fetchone()['n']
  queries={
   'fact_fpt':len(c.execute("select 1 from financial.vnstock_serving_facts where ticker='FPT' and canonical_metric_code='net_profit' order by year desc limit 1").fetchall()),
   'fact_acb':len(c.execute("select 1 from financial.vnstock_serving_facts where ticker='ACB' and canonical_metric_code='net_profit' order by year desc limit 1").fetchall()),
   'series_fpt':len(c.execute("select 1 from financial.vnstock_serving_facts where ticker='FPT' and canonical_metric_code='net_revenue' order by year").fetchall()),
   'series_mbb_2021_2025':len(c.execute("select 1 from financial.vnstock_serving_facts where ticker='MBB' and canonical_metric_code='net_interest_income' and year between 2021 and 2025").fetchall()),
   'compare_corporate':len(c.execute("select 1 from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code='net_profit' and year=2025",(['FPT','HPG','MWG'],)).fetchall()),
   'compare_bank':len(c.execute("select 1 from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code='net_profit' and year=2025",(['ACB','MBB','VCB'],)).fetchall()),
   'rank_corporate':len(c.execute("select 1 from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code='net_profit' and year=2025 and value is not null order by value desc limit 10",(corps,)).fetchall()),
   'rank_bank':len(c.execute("select 1 from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code='net_profit' and year=2025 and value is not null order by value desc limit 10",(banks,)).fetchall()),
  }
  missing=sorted(set(corps)-set(x['ticker'] for x in c.execute('select distinct ticker from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code=any(%s)',(corps,CORP_METRICS)).fetchall()))
 passed=bank['tickers']==25 and bank['rows']==1400 and corp['tickers']==809 and corp['rows']==30545 and combined['rows']==31945 and all(v==0 for v in integrity.values()) and dup_serving==0 and dup_mapping==0 and invalid_mapping==0 and zero_without_zero_evidence==0 and all(v>0 for v in queries.values())
 summary={'bank':bank,'corporate':corp,'combined':combined,'metric_breakdown':metric_rows,'unsupported_corporate':missing,'integrity':integrity,'duplicate_mapping_keys':dup_mapping,'duplicate_serving_keys':dup_serving,'invalid_mapping_status_rows':invalid_mapping,'out_of_scope_corporate_pilot_rows':corp_forbidden,'zero_without_zero_evidence':zero_without_zero_evidence,'query_checks':queries,'vnstock_called_in_serving_path':False,'numerical_serving_mvp':'PASS' if passed else 'FAIL'}
 SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 lines=['# Numerical Serving MVP Validation','',f"Gate: **{summary['numerical_serving_mvp']}**",'',f"- BANK: {bank['tickers']}/25 tickers, {bank['rows']} rows, {bank['metrics']} metrics.",f"- CORPORATE: {corp['tickers']}/818 tickers, {corp['rows']} rows, {corp['metrics']} metrics.",f"- Combined MVP scope: {combined['tickers']} tickers, {combined['rows']} rows, years {combined['year_min']}–{combined['year_max']}.",f"- Unsupported Corporate: {len(missing)} (`{', '.join(missing)}`).",f"- Evidence orphans: {integrity['orphan_evidence']}; mapping orphans: {integrity['orphan_mapping']}; value/provenance mismatches: {integrity['value_mismatch']+integrity['provenance_key_mismatch']}.",f"- Duplicate mapping keys: {dup_mapping}; duplicate serving keys: {dup_serving}; non-approved mapping rows: {invalid_mapping}.",f"- Missing-to-zero violations: {zero_without_zero_evidence}; out-of-scope Corporate pilot rows retained: {corp_forbidden}.",'','## Query checks','']+[f"- {k}: {v} row(s)" for k,v in queries.items()]+['','All queries read PostgreSQL serving facts only; no VNStock or LLM call is present.','', '**PASS; STOP before the next roadmap phase.**' if passed else '**FAIL; STOP.**']
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps({k:summary[k] for k in ['bank','corporate','combined','integrity','duplicate_mapping_keys','duplicate_serving_keys','query_checks','numerical_serving_mvp']},ensure_ascii=False,default=str)); return 0 if passed else 1
if __name__=='__main__': raise SystemExit(main())
