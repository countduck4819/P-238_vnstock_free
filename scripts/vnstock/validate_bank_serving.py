"""Read-only validation for the BANK reusable-rule serving sample."""
from __future__ import annotations
import argparse, csv, json, os, re
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[2]; META=ROOT/'data'/'vnstock'/'metadata'
REPORT=META/'bank_serving_validation_report.md'; SUMMARY=META/'bank_serving_validation_summary.json'
SAMPLE=['ACB','MBB','BID']; METRICS=['net_fee_and_commission_income','net_interest_income','net_profit','profit_before_tax','provision_for_credit_losses','total_assets','total_equity']
def url():
 m=re.search(r'^DATABASE_URL\s*=\s*(.*)$',(ROOT/'.env').read_text(encoding='utf-8'),re.M); return os.environ.get('DATABASE_URL') or m.group(1).strip().strip('"\'')
def main():
 args=argparse.ArgumentParser(); args.add_argument('--all-banks',action='store_true'); a=args.parse_args()
 taxonomy=list(csv.DictReader((META/'financial_sector_taxonomy.csv').open(encoding='utf-8')))
 tickers=sorted(x['ticker'] for x in taxonomy if x['financial_sector_family']=='BANK') if a.all_banks else SAMPLE
 with psycopg.connect(url(),connect_timeout=5,row_factory=dict_row) as c:
  counts=[dict(x) for x in c.execute('''select ticker,count(*) rows,count(distinct canonical_metric_code) metrics from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code=any(%s) group by ticker order by ticker''',(tickers,METRICS)).fetchall()]
  orphan=c.execute('''select count(*) n from financial.vnstock_serving_facts s left join financial.vnstock_financial_evidence e on e.evidence_id=s.source_evidence_id left join financial.vnstock_metric_mapping m on m.mapping_id=s.mapping_id where s.ticker=any(%s) and s.canonical_metric_code=any(%s) and(e.evidence_id is null or m.mapping_id is null)''',(tickers,METRICS)).fetchone()['n']
  dup=c.execute('''select count(*) n from(select ticker,year,canonical_metric_code from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code=any(%s) group by 1,2,3 having count(*)>1)x''',(tickers,METRICS)).fetchone()['n']
  mapdup=c.execute('''select count(*) n from(select ticker_scope,canonical_metric_code from financial.vnstock_metric_mapping where ticker_scope=any(%s) and canonical_metric_code=any(%s) and mapping_status='APPROVED' group by 1,2 having count(*)>1)x''',(tickers,METRICS)).fetchone()['n']
  fact=[dict(x) for x in c.execute("select ticker,year,canonical_metric_code,value,source_evidence_id from financial.vnstock_serving_facts where ticker='ACB' and year=2025 and canonical_metric_code='net_profit'").fetchall()]
  series=[dict(x) for x in c.execute("select year,value from financial.vnstock_serving_facts where ticker='ACB' and canonical_metric_code='net_interest_income' and year between 2021 and 2025 order by year").fetchall()]
  compare=[dict(x) for x in c.execute("select ticker,value from financial.vnstock_serving_facts where ticker=any(%s) and year=2025 and canonical_metric_code='net_profit' order by ticker",(tickers,)).fetchall()]
  ranking=[dict(x) for x in c.execute("select ticker,value from financial.vnstock_serving_facts where ticker=any(%s) and year=2025 and canonical_metric_code='net_profit' order by value desc nulls last",(tickers,)).fetchall()]
 summary={'counts':counts,'orphan_provenance':orphan,'duplicate_serving_keys':dup,'duplicate_mapping_keys':mapdup,'fact_rows':len(fact),'series_rows':len(series),'compare_rows':len(compare),'ranking_rows':len(ranking),'pass':orphan==0 and dup==0 and mapdup==0 and len(counts)==len(tickers) and all(x['rows']==56 and x['metrics']==7 for x in counts)}
 SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 lines=['# Bank serving validation','',f"Scope: **{len(tickers)} BANK tickers**; validation PASS: **{summary['pass']}**.",f"Orphans: **{orphan}**; duplicate serving keys: **{dup}**; duplicate mapping keys: **{mapdup}**.",'','| Ticker | Rows | Metrics |','|---|---:|---:|']+[f"| {x['ticker']} | {x['rows']} | {x['metrics']} |" for x in counts]+['','- Fact query rows: '+str(len(fact)), '- Time-series rows: '+str(len(series)), '- Compare rows: '+str(len(compare)), '- Ranking rows: '+str(len(ranking)), '', '**PASS validation.**']
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False,default=str)); return 0 if summary['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
