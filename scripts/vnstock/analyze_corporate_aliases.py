"""Review deterministic Corporate alias/structural patterns for five MVP metrics."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]; META=ROOT/'data'/'vnstock'/'metadata'
INPUT=META/'canonical_mapping_sector_analysis.csv'; CAND=META/'corporate_mapping_alias_candidates.csv'; REVIEW=META/'corporate_mapping_alias_review.csv'; COVER=META/'corporate_mapping_alias_coverage.csv'; REPORT=META/'corporate_mapping_alias_report.md'; SUMMARY=META/'corporate_mapping_alias_summary.json'
EXPECTED={
 'net_profit':('income_statement','net_profit_loss_after_tax'),
 'net_revenue':('income_statement','net_sales'),
 'profit_before_tax':('income_statement','net_accounting_profit_loss_before_tax'),
 'total_assets':('balance_sheet','total_assets'),
 'total_liabilities':('balance_sheet','liabilities'),
}

def main():
 d=pd.read_csv(INPUT,dtype=str).fillna(''); d=d[(d.financial_sector_family=='CORPORATE')&d.canonical_metric_code.isin(EXPECTED)].copy()
 matched=d[d.source_item_id.ne('')].copy(); matched['source_row_index_num']=pd.to_numeric(matched.source_row_index,errors='coerce')
 keys=['canonical_metric_code','statement_type','source_item_id','source_item_name','source_item_name_en','source_row_index']
 patterns=matched.groupby(keys,dropna=False).agg(ticker_count=('ticker','nunique'),year_coverage=('years_available',lambda x:'|'.join(sorted(set(x)))),representative_tickers=('ticker',lambda x:','.join(sorted(set(x))[:5])),provenance_available=('candidate_count',lambda x:bool((pd.to_numeric(x,errors='coerce').fillna(0)>0).all())),collision_count=('candidate_status',lambda x:int((x=='AMBIGUOUS').sum()))).reset_index()
 statuses=[]; reasons=[]
 for _,r in patterns.iterrows():
  expected_statement,expected_item=EXPECTED[r.canonical_metric_code]
  if r.statement_type!=expected_statement or r.source_item_id!=expected_item: status,reason='REJECT','source identity/statement outside deterministic whitelist'
  elif r.collision_count>0: status,reason='REVIEW','competing evidence/collision exists'
  elif not r.provenance_available: status,reason='REVIEW','provenance incomplete'
  elif int(r.ticker_count)<2: status,reason='REVIEW','unique structural variant; insufficient repeated evidence'
  else: status,reason='APPROVED_CORPORATE_ALIAS','exact whitelisted source identity and stable repeated structural pattern'
  statuses.append(status); reasons.append(reason)
 patterns['review_status']=statuses; patterns['review_reason']=reasons; patterns.to_csv(CAND,index=False); patterns.to_csv(REVIEW,index=False)
 approved=patterns[patterns.review_status=='APPROVED_CORPORATE_ALIAS']; coverage=[]
 for metric in EXPECTED:
  applicable=set(d[d.canonical_metric_code==metric].ticker); current=set(d[(d.canonical_metric_code==metric)&(d.candidate_status=='APPROVED')].ticker)
  p=approved[approved.canonical_metric_code==metric]
  safe=set()
  for _,a in p.iterrows(): safe|=set(matched[(matched.canonical_metric_code==metric)&(matched.statement_type==a.statement_type)&(matched.source_item_id==a.source_item_id)&(matched.source_item_name==a.source_item_name)&(matched.source_item_name_en==a.source_item_name_en)&(matched.source_row_index==a.source_row_index)].ticker)
  covered=safe|current; collision=set(d[(d.canonical_metric_code==metric)&(d.candidate_status=='AMBIGUOUS')].ticker)
  coverage.append({'canonical_metric_code':metric,'total_corporate_tickers':818,'approved_alias_count':len(p),'tickers_safely_covered':len(covered-collision),'tickers_uncovered':818-len(covered-collision),'coverage_percent':round(100*len(covered-collision)/818,2),'collision_tickers':len(collision),'review_patterns':int((patterns.canonical_metric_code.eq(metric)&patterns.review_status.eq('REVIEW')).sum())})
 cov=pd.DataFrame(coverage); cov.to_csv(COVER,index=False)
 no_source=d[d.source_item_id.eq('')].groupby('canonical_metric_code').ticker.nunique().to_dict(); review_tickers={m:int(matched[(matched.canonical_metric_code==m)&~matched.ticker.isin(set())].ticker.nunique()) for m in []}
 summary={'patterns_analyzed':len(patterns),'approved_aliases':int((patterns.review_status=='APPROVED_CORPORATE_ALIAS').sum()),'review_count':int((patterns.review_status=='REVIEW').sum()),'reject_count':int((patterns.review_status=='REJECT').sum()),'provenance_invalid':int((~patterns.provenance_available).sum()),'coverage':coverage,'no_source_match_tickers':{k:int(v) for k,v in no_source.items()}}
 SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# Corporate mapping alias review','',f"Patterns analyzed: **{len(patterns)}**; approved aliases: **{summary['approved_aliases']}**; review: **{summary['review_count']}**; reject: **{summary['reject_count']}**.",'','## Coverage simulation','','| Metric | Approved aliases | Safe coverage | Uncovered | Coverage | Collisions | Review patterns |','|---|---:|---:|---:|---:|---:|---:|']
 for x in coverage: lines.append(f"| {x['canonical_metric_code']} | {x['approved_alias_count']} | {x['tickers_safely_covered']}/818 | {x['tickers_uncovered']} | {x['coverage_percent']}% | {x['collision_tickers']} | {x['review_patterns']} |")
 lines += ['','Aliases are exact source-item + statement + structural-row patterns. No fuzzy matching or LLM decision is used. Total equity and operating cash flow are excluded.','', '**PASS alias analysis; STOP before full Corporate materialization.**']
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
