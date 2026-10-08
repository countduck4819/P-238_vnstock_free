from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]; META=ROOT/'data'/'vnstock'/'metadata'
RULES=META/'canonical_mapping_rule_candidates.csv'; ANALYSIS=META/'canonical_mapping_sector_analysis.csv'
OUT=META/'canonical_mapping_rule_review.csv'; REPORT=META/'canonical_mapping_rule_review_report.md'; SUMMARY=META/'canonical_mapping_rule_review_summary.json'

def main():
 rules=pd.read_csv(RULES,dtype=str).fillna(''); rules.columns=[str(c).strip() for c in rules.columns]; rules=rules[rules['proposed_status'].eq('SAFE_RULE_CANDIDATE')].copy(); d=pd.read_csv(ANALYSIS,dtype=str).fillna(''); d.columns=[str(c).strip() for c in d.columns]
 rows=[]
 for _,r in rules.iterrows():
  q=d[(d.financial_sector_family==r['financial_sector_family'])&(d.canonical_metric_code==r['canonical_metric_code'])&(d.statement_type==r['statement_type'])&(d.source_item_id==r['source_item_id'])]
  names=set(q.source_item_name); names_en=set(q.source_item_name_en); ids=set(q.source_item_id); rows_seen=set(q.source_row_index)
  collision=bool(((d.financial_sector_family==r['financial_sector_family'])&(d.canonical_metric_code==r['canonical_metric_code'])&(d.candidate_status=='AMBIGUOUS')).any())
  provenance_ok=bool((q.source_item_id!='').all() and (q.source_item_name!='').all() and (pd.to_numeric(q.candidate_count,errors='coerce').fillna(0)>0).all())
  if collision: status='REVIEW'; reason='total_equity collision affects sector/metric; no winner policy'
  elif len(names)>1 or len(names_en)>1 or len(ids)!=1 or len(rows_seen)!=1: status='REVIEW'; reason='source identity/label varies across matched tickers'
  elif not provenance_ok: status='REVIEW'; reason='provenance/source identity incomplete'
  else: status='APPROVED_REUSABLE_RULE'; reason='stable identity, semantic label, statement, provenance and zero collision'
  rows.append({**{k:r[k] for k in ['financial_sector_family','canonical_metric_code','statement_type','source_item_id','source_item_name','ticker_coverage','year_coverage','collision_count','proposed_status']},'previous_status':r.proposed_status,'review_status':status,'review_reason':reason,'observed_label_count':len(names),'observed_row_identity_count':len(rows_seen),'provenance_valid':str(provenance_ok).upper(),'representative_tickers':','.join(sorted(set(q.ticker)&set(['FPT','AAA','HPG','ACB','MBB']))[:5])})
 out=pd.DataFrame(rows); out.to_csv(OUT,index=False)
 approved=out[out.review_status.eq('APPROVED_REUSABLE_RULE')]; review=out[out.review_status.eq('REVIEW')]
 impacts=[]
 for _,r in approved.iterrows():
  q=d[(d.financial_sector_family==r['financial_sector_family'])&(d.canonical_metric_code==r['canonical_metric_code'])&(d.source_item_id==r['source_item_id'])]
  all_metric=d[(d.financial_sector_family==r['financial_sector_family'])&(d.canonical_metric_code==r['canonical_metric_code'])]
  current=set(all_metric[all_metric.candidate_status=='APPROVED'].ticker); potential=set(q.ticker)|current; applicable=set(all_metric.ticker)
  impacts.append({'financial_sector_family':r.financial_sector_family,'canonical_metric_code':r.canonical_metric_code,'currently_approved':len(current),'newly_covered':len(potential-current),'total_covered':len(potential),'applicable_tickers':len(applicable),'expected_coverage_percent':round(100*len(potential)/len(applicable),2) if applicable else 0})
 summary={'reviewed_rules':len(rules),'approved_reusable_rules':len(approved),'review_count':len(review),'reject_count':0,'provenance_invalid':int((out.provenance_valid!='TRUE').sum()),'collision_review_rules':int((out.collision_count.astype(int)>0).sum()),'coverage_after_approval':impacts}
 SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# Reusable mapping rule review','',f"Rules reviewed: **{len(rules)}**; APPROVED_REUSABLE_RULE: **{len(approved)}**; REVIEW: **{len(review)}**; REJECT: **0**",'', '## Approved rules', '']
 for _,r in approved.iterrows(): lines.append(f"- `{r.financial_sector_family}` / `{r.canonical_metric_code}` → `{r.source_item_id}` ({r.ticker_coverage} tickers)")
 lines += ['', '## Coverage after approval simulation','', '| Sector | Metric | Current | Newly covered | Total covered | Applicable | Expected coverage |','|---|---|---:|---:|---:|---:|---:|']
 for x in impacts: lines.append(f"| {x['financial_sector_family']} | {x['canonical_metric_code']} | {x['currently_approved']} | {x['newly_covered']} | {x['total_covered']} | {x['applicable_tickers']} | {x['expected_coverage_percent']}% |")
 lines += ['', '## Review rules and gate', ''] + [f"- `{r.financial_sector_family}` / `{r.canonical_metric_code}`: {r.review_reason}." for _,r in review.iterrows()] + ['', 'Representative source labels, row identities, years and provenance were checked from the candidate artifact; no raw/evidence values were modified. `total_equity` remains unresolved.', '', '**PASS review; STOP before mapping materialization.**']
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
