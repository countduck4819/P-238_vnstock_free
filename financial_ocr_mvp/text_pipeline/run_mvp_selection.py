import csv,json,time
from collections import defaultdict,Counter
from pathlib import Path
from .registry_models import document_id
from .mvp_extractor_context import build_document_context,extract_all_facts,validate,FACTS
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'financial_ocr_mvp/output'; NORM=OUT/'phase3_normalized'; YEARS=[2021,2022,2023,2024,2025]
def scope(path): return 'consolidated' if 'Hopnhat' in path or 'hopnhat' in path.lower() else 'separate'
def rejected_type(text):
 u=text.upper()
 if 'NGÂN HÀNG' in u or 'NGAN HANG' in u: return 'bank'
 if 'CHỨNG KHOÁN' in u or 'CHUNG KHOAN' in u: return 'securities'
 if 'BẢO HIỂM' in u or 'BAO HIEM' in u: return 'insurance'
 return None
def main():
 t=time.perf_counter(); inv=json.loads((OUT/'dataset_inventory.json').read_text())['reports']; groups=defaultdict(lambda:defaultdict(list))
 for r in inv:
  if r['year'] in YEARS and not r.get('is_duplicate',False): groups[r['ticker']][r['year']].append(r)
 candidates={k:v for k,v in groups.items() if all(y in v for y in YEARS)}; kept=[]; rejects=[]; facts=[]; cy_pass=cy_fail=0; opened=parsed=0; parse_count=0; used=[]
 for ticker,years in sorted(candidates.items()):
  chosen={}
  for y in YEARS:
   rs=sorted(years[y],key=lambda r:(scope(r['path'])!='consolidated', 'Hopnhat' not in r['path'],len(r['path'])))
   chosen[y]=rs[0]
  scopes={scope(r['path']) for r in chosen.values()}
  if len(scopes)!=1: rejects.append({'ticker':ticker,'reason':'mixed_report_scope','scopes':sorted(scopes)}); continue
  ticker_facts=[]; ok=True; reasons=[]; source=[]; typ=None
  for y in YEARS:
   r=chosen[y]; did=document_id(r['path']); p=NORM/ticker/str(y)/(did+'.txt')
   if not p.exists(): ok=False; reasons.append(f'{y}:missing_normalized_output'); continue
   opened+=1; ctx,_=build_document_context(p,did,ticker,y); parsed+=1; parse_count+=ctx.html_parse_count
   typ=typ or rejected_type(ctx.raw_text)
   got=extract_all_facts(ctx); year_ok=True
   for f in FACTS:
    x=got[f]
    if not x: year_ok=False; reasons.append(f'{y}:missing_{f}'); continue
    rec={'ticker':ticker,'year':y,'metric_code':f,'value':x['value'],'report_scope':next(iter(scopes)),'audit_status':'audited','document_id':did,'source_report_year':y,'value_origin':'current','page':x['page'],'table_index':x['table_index'],'row_index':x['row_index'],'raw_label':x['raw_label'],'statement_code':x['statement_code'],'validation_status':'candidate'}; ticker_facts.append(rec)
   if not year_ok: ok=False
   elif not validate(got): ok=False; reasons.append(f'{y}:balance_equation_or_validation_failed')
   cy_pass+=int(year_ok and validate(got)); cy_fail+=int(not(year_ok and validate(got))); source.append({'year':y,'document_id':did,'path':r['path']})
  if typ: ok=False; reasons.append(f'company_type_excluded:{typ}')
  if ok: kept.append(ticker); facts.extend(ticker_facts); used.extend(source)
  else: rejects.append({'ticker':ticker,'reason':'; '.join(sorted(set(reasons)))})
 # tickers lacking coverage are rejected without opening files
 for ticker in sorted(set(groups)-set(candidates)): rejects.append({'ticker':ticker,'reason':'missing_target_year_coverage','available_years':sorted(groups[ticker])})
 facts=[x for x in facts if x['ticker'] in set(kept)]
 summary={'schema':'p238_mvp_5y_selection_v1','target_years':YEARS,'candidate_tickers_with_full_coverage':len(candidates),'candidate_tickers':len(groups),'kept_tickers':len(kept),'rejected_tickers':len(rejects),'kept_ticker_list':kept,'rejected_ticker_list':rejects,'company_years_pass':len(kept)*5,'company_years_fail':len(rejects)*5,'facts_extracted':len(facts),'facts_validated':len(facts),'coverage_per_fact':{f:sum(x['metric_code']==f for x in facts) for f in FACTS},'report_scope_distribution':dict(Counter(x['report_scope'] for x in facts[::8])),'source_documents_used':len(used),'documents_opened':opened,'documents_parsed':parsed,'html_parse_count':parse_count,'runtime_seconds':round(time.perf_counter()-t,3),'policy':'strict; direct annual current values; no OCR/LLM/Docling/PostgreSQL'}
 (OUT/'mvp_5y_eligible_tickers.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
 with (OUT/'mvp_5y_financial_facts.jsonl').open('w',encoding='utf8') as f:
  for x in facts:f.write(json.dumps(x,ensure_ascii=False)+'\n')
 with (OUT/'mvp_5y_financial_facts.csv').open('w',newline='',encoding='utf8') as f:
  fields=list(facts[0]) if facts else ['ticker']; w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(facts)
 (OUT/'mvp_5y_rejected_tickers.json').write_text(json.dumps(rejects,ensure_ascii=False,indent=2),encoding='utf8')
 (OUT/'mvp_5y_selection_summary.md').write_text('# Strict MVP 5-year selection\n\n'+json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8'); print(json.dumps({k:summary[k] for k in ('candidate_tickers_with_full_coverage','kept_tickers','rejected_tickers','company_years_pass','facts_extracted','documents_opened','documents_parsed','html_parse_count','runtime_seconds')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
