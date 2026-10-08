from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]; META=ROOT/'data'/'vnstock'/'metadata'
IN=META/'canonical_mapping_sector_analysis.csv'; RULES=META/'canonical_mapping_rule_candidates.csv'; IMPACT=META/'canonical_mapping_rule_coverage_impact.csv'; REPORT=META/'canonical_mapping_rule_discovery_report.md'
CORP={'net_revenue','profit_before_tax','net_profit','total_assets','total_liabilities','total_equity','operating_cash_flow'}
BANK={'net_interest_income','net_fee_and_commission_income','operating_expenses','provision_for_credit_losses','profit_before_tax','net_profit','total_assets','total_equity'}

def main():
 d=pd.read_csv(IN,dtype=str).fillna(''); d['candidate_count_num']=pd.to_numeric(d.candidate_count,errors='coerce').fillna(0); d['row_num']=pd.to_numeric(d.source_row_index,errors='coerce')
 u=d[(d.analysis_status=='UNSAFE_TO_MAP') & d.financial_sector_family.isin(['CORPORATE','BANK'])].copy(); u=u[u.canonical_metric_code.isin(CORP|BANK)]
 keys=['financial_sector_family','canonical_metric_code','statement_type','source_item_id','source_item_name','source_item_name_en','source_row_index']
 g=u.groupby(keys,dropna=False).agg(ticker_coverage=('ticker','nunique'),year_coverage=('years_available',lambda s: '|'.join(sorted(set(s)))),collision_count=('distinct_source_rows',lambda s:int((pd.to_numeric(s,errors='coerce').fillna(0)>1).sum())),candidate_rows=('ticker','size')).reset_index()
 # Any ticker-level ambiguity for a metric contaminates every competing source
 # pattern for that sector/metric until a hierarchy policy is approved.
 collision_map = d[d.candidate_status.eq('AMBIGUOUS')].groupby(['financial_sector_family','canonical_metric_code']).ticker.nunique().to_dict()
 g['collision_count'] = [max(int(v), int(collision_map.get((s,m), 0))) for v,s,m in zip(g.collision_count,g.financial_sector_family,g.canonical_metric_code)]
 # An exact source identity is a reusable candidate only when it recurs across >=2 tickers and has no collision evidence.
 g['proposed_status']='REVIEW'; g.loc[(g.ticker_coverage>=2)&(g.collision_count==0)&g.source_item_id.ne(''),'proposed_status']='SAFE_RULE_CANDIDATE'; g.loc[g.source_item_id.eq(''),'proposed_status']='REJECT'
 g['notes']='Exact source identity; human review still required before approval.'
 g.sort_values(['proposed_status','ticker_coverage'],ascending=[True,False]).to_csv(RULES,index=False)
 impacts=[]
 for sec, metrics in [('CORPORATE',CORP),('BANK',BANK)]:
  total=int(d[d.financial_sector_family.eq(sec)].ticker.nunique())
  for m in sorted(metrics):
   applicable=set(d[(d.financial_sector_family==sec)&(d.canonical_metric_code==m)].ticker)
   current=set(d[(d.financial_sector_family==sec)&(d.canonical_metric_code==m)&(d.candidate_status=='APPROVED')].ticker)
   safe=g[(g.financial_sector_family==sec)&(g.canonical_metric_code==m)&(g.proposed_status=='SAFE_RULE_CANDIDATE')]
   potential=set(u[(u.financial_sector_family==sec)&(u.canonical_metric_code==m)&u.source_item_id.isin(safe.source_item_id)].ticker)|current
   impacts.append({'financial_sector_family':sec,'canonical_metric_code':m,'current_approved_tickers':len(current),'potential_approved_tickers':len(potential),'total_applicable_tickers':len(applicable),'potential_coverage_percent':round(100*len(potential)/len(applicable),2) if applicable else 0,'safe_rule_count':len(safe)})
 pd.DataFrame(impacts).to_csv(IMPACT,index=False)
 safe=g[g.proposed_status=='SAFE_RULE_CANDIDATE']; rej=g[g.proposed_status=='REJECT']; rev=g[g.proposed_status=='REVIEW']
 summary={'unsafe_corporate_bank_rows':len(u),'pattern_count':len(g),'safe_rule_candidates':len(safe),'review_patterns':len(rev),'rejected_patterns':len(rej),'impact':impacts}
 (META/'canonical_mapping_rule_discovery_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# Reusable canonical mapping rule discovery','',f"UNSAFE_TO_MAP analyzed (Corporate + Bank): **{len(u)} rows**",f"Grouped patterns: **{len(g)}**; SAFE_RULE_CANDIDATE: **{len(safe)}**; REVIEW: **{len(rev)}**; REJECT: **{len(rej)}**",'', '## Coverage impact simulation','', '| Sector | Metric | Current approved | Potential approved | Applicable | Potential coverage | Safe rules |','|---|---|---:|---:|---:|---:|---:|']
 for x in impacts: lines.append(f"| {x['financial_sector_family']} | {x['canonical_metric_code']} | {x['current_approved_tickers']} | {x['potential_approved_tickers']} | {x['total_applicable_tickers']} | {x['potential_coverage_percent']}% | {x['safe_rule_count']} |")
 lines += ['', 'Rules are proposals only. Exact source identity, sector, statement type, provenance and collision evidence must be reviewed before any mapping materialization. `total_equity` competing identities remain excluded from SAFE_RULE_CANDIDATE.', '', '**PASS pattern discovery; STOP before mapping/Serving Facts materialization.**']
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
