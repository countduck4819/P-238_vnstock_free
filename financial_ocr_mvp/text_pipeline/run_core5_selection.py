import csv,json,time
from collections import defaultdict,Counter
from pathlib import Path
from .registry_models import document_id
from .mvp_extractor_context import build_document_context,extract_all_facts,FACTS
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'financial_ocr_mvp/output'; NORM=OUT/'phase3_normalized'; YEARS=[2021,2022,2023,2024,2025]; CORE=['net_revenue','profit_after_tax','total_assets','total_liabilities','total_equity']; CF=['operating_cash_flow','investing_cash_flow','financing_cash_flow']
def scope(p): return 'consolidated' if 'Hopnhat' in p or 'hopnhat' in p.lower() else 'separate'
def noncorp(text):
 u=text.upper()
 for k,v in [('NGÂN HÀNG','bank'),('NGAN HANG','bank'),('CHỨNG KHOÁN','securities'),('CHUNG KHOAN','securities'),('BẢO HIỂM','insurance'),('BAO HIEM','insurance')]:
  if k in u:return v
 return None
def main():
 t=time.perf_counter(); inv=json.loads((OUT/'dataset_inventory.json').read_text())['reports']; g=defaultdict(lambda:defaultdict(list))
 for r in inv:
  if r['year'] in YEARS and not r.get('is_duplicate',False):g[r['ticker']][r['year']].append(r)
 full={k:v for k,v in g.items() if all(y in v for y in YEARS)}; kept=[]; rej=[]; facts=[]; cy=[]; opened=parsed=pc=0; reason=Counter(); scope_stats=Counter(); ticker_cf=Counter()
 for ticker,ys in sorted(full.items()):
  selections=None; selected_scope=None
  for sc in ('consolidated','separate'):
   if all(any(scope(r['path'])==sc for r in ys[y]) for y in YEARS): selections={y:sorted([r for r in ys[y] if scope(r['path'])==sc],key=lambda r:len(r['path']))[0] for y in YEARS}; selected_scope=sc; break
  if not selections: rej.append({'ticker':ticker,'reason':'REJECT_MIXED_SCOPE'}); reason['REJECT_MIXED_SCOPE']+=1; continue
  candidate_facts=[]; ok=True; reasons=[]; cfs=Counter(); typ=None
  for y in YEARS:
   r=selections[y]; did=document_id(r['path']); path=NORM/ticker/str(y)/(did+'.txt')
   if not path.exists(): ok=False; reasons.append(f'{y}:missing_normalized'); continue
   opened+=1; ctx,_=build_document_context(path,did,ticker,y); parsed+=1; pc+=ctx.html_parse_count; typ=typ or noncorp(ctx.raw_text); got=extract_all_facts(ctx)
   missing=[f for f in CORE if not got[f]]
   if missing: ok=False; reasons.extend(f'{y}:missing_{f}' for f in missing)
   # Equation only when all three BS facts exist; no repair.
   if not missing:
    a=got['total_assets']['value']; b=got['total_liabilities']['value']+got['total_equity']['value']
    if abs(a-b)>max(1000,abs(a)*.03):ok=False; reasons.append(f'{y}:balance_equation_failed')
   for f in CF:
    if got[f]:cfs[f]+=1
   for f in FACTS:
    x=got[f]
    candidate_facts.append({'ticker':ticker,'year':y,'metric_code':f,'value':x['value'] if x else None,'report_scope':selected_scope,'audit_status':'audited','document_id':did,'source_report_year':y,'value_origin':'current','page':x['page'] if x else None,'table_index':x['table_index'] if x else None,'row_index':x['row_index'] if x else None,'raw_label':x['raw_label'] if x else None,'statement_code':x['statement_code'] if x else None,'validation_status':'VALIDATED_MVP' if f in CORE and x else ('candidate' if x else 'missing_optional')})
  if typ:ok=False; reasons.append(f'company_type_excluded:{typ}')
  if ok:
   kept.append(ticker); facts.extend(candidate_facts); scope_stats[selected_scope]+=1; ticker_cf.update({f:1 for f in CF if cfs[f]==5}); cy.extend([{'ticker':ticker,'year':y,'report_scope':selected_scope,'core':{f:next(z['value'] for z in candidate_facts if z['year']==y and z['metric_code']==f) for f in CORE},'cash_flow':{f:next(z['value'] for z in candidate_facts if z['year']==y and z['metric_code']==f) for f in CF},'core_validation_status':'VALIDATED_MVP'} for y in YEARS])
  else:rej.append({'ticker':ticker,'reason':'; '.join(sorted(set(reasons)))}); reason.update(set(reasons))
 for ticker in sorted(set(g)-set(full)):rej.append({'ticker':ticker,'reason':'missing_target_year_coverage','available_years':sorted(g[ticker])});reason['missing_target_year_coverage']+=1
 summary={'schema':'p238_mvp_core5_5y_v1','target_years':YEARS,'candidate_tickers':len(g),'corporate_candidates':len(full),'eligible_core5_tickers':len(kept),'rejected_tickers':len(rej),'eligible_ticker_list':kept,'company_years_validated':len(cy),'mandatory_facts_expected':len(kept)*25,'mandatory_facts_validated':len(kept)*25,'cashflow_facts_found':sum(x['value'] is not None for x in facts if x['metric_code'] in CF),'coverage_per_core_metric':{f:sum(x['metric_code']==f and x['value'] is not None for x in facts) for f in CORE},'coverage_cashflow':{f:sum(x['metric_code']==f and x['value'] is not None for x in facts) for f in CF},'tickers_with_5y_operating_cash_flow':sum(1 for t in kept if sum(x['ticker']==t and x['metric_code']=='operating_cash_flow' and x['value'] is not None for x in facts)==5),'tickers_with_5y_all_cashflows':sum(1 for t in kept if all(sum(x['ticker']==t and x['metric_code']==f and x['value'] is not None for x in facts)==5 for f in CF)),'rejection_reason_distribution':dict(reason),'report_scope_distribution':dict(scope_stats),'documents_opened':opened,'documents_parsed':parsed,'html_parse_count':pc,'runtime_seconds':round(time.perf_counter()-t,3),'raw_unchanged':True,'normalized_unchanged':True,'postgres_unchanged':True,'status':'MVP_CORE5_5Y_DATASET_READY' if kept else 'MVP_CORE5_5Y_DATASET_EMPTY'}
 (OUT/'mvp_core5_5y_eligible_tickers.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8'); (OUT/'mvp_core5_5y_rejected_tickers.json').write_text(json.dumps(rej,ensure_ascii=False,indent=2),encoding='utf8'); (OUT/'mvp_core5_5y_company_years.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in cy),encoding='utf8'); (OUT/'mvp_core5_5y_financial_facts.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in facts),encoding='utf8')
 with (OUT/'mvp_core5_5y_financial_facts.csv').open('w',newline='',encoding='utf8') as f:
  fields=list(facts[0]) if facts else ['ticker'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(facts)
 (OUT/'mvp_core5_5y_selection_summary.md').write_text('# Core5 5-year MVP selection\n\n'+json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:summary[k] for k in ('corporate_candidates','eligible_core5_tickers','rejected_tickers','mandatory_facts_validated','cashflow_facts_found','documents_parsed','html_parse_count','runtime_seconds','status')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
