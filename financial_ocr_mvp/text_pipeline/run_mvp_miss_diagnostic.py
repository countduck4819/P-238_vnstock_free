from __future__ import annotations
import json,re,time
from pathlib import Path
from collections import Counter
from .mvp_extractor_context import build_document_context,extract_all_facts,FACTS,ALIASES,norm
from .registry_models import document_id
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'financial_ocr_mvp/output'; NORM=OUT/'phase3_normalized'
def docs(n):
 inv=json.loads((OUT/'dataset_inventory.json').read_text())['reports']; out=[]
 for r in inv:
  if r['year'] in (2021,2022,2023,2024,2025) and r['has_table']:
   p=NORM/r['ticker']/str(r['year'])/(document_id(r['path'])+'.txt')
   if p.exists(): out.append((r,p))
  if len(out)>=n: break
 return out
def candidates(ctx,fact):
 aliases=ALIASES[fact]; out=[]
 for row in ctx.rows:
  label=row.normalized_label
  if any(a.split()[0] in label or a in label for a in aliases):
   out.append({'page':row.page,'table_index':row.table_index,'row_index':row.row_index,'cells_raw':[c.raw_text for c in row.cells],'normalized_label':label,'statement_code_candidates':[row.statement_code] if row.statement_code else [],'numeric_tokens':row.numeric_cells,'section_table_context':row.section_context})
 return out
def main():
 t=time.perf_counter(); ds=docs(20); matrix=[]; coverage=[]; reasons=Counter(); stage1_dump=[]
 for r,p in ds:
  ctx,_=build_document_context(p,document_id(r['path']),r['ticker'],r['year']); facts=extract_all_facts(ctx)
  coverage.append({'ticker':r['ticker'],'year':r['year'],'document_id':document_id(r['path']),'html_table_count':len(set(x.table_index for x in ctx.rows)),'html_row_count':len(ctx.rows),'rows_with_numeric_tokens':sum(bool(x.numeric_cells) for x in ctx.rows),'rows_with_statement_code':0,'rows_with_page':sum(x.page is not None for x in ctx.rows),'rows_without_page':sum(x.page is None for x in ctx.rows)})
  for f in FACTS:
   cs=candidates(ctx,f); found=facts[f] is not None
   reason='' if found else ('J_ACTUAL_SOURCE_NOT_FOUND' if not cs else ('F_NUMERIC_CELLS_NOT_RECOGNIZED' if not any(x['numeric_tokens'] for x in cs) else 'D_ALIAS_OR_CONTEXT_MATCH'))
   if reason: reasons[reason]+=1
   matrix.append({'ticker':r['ticker'],'year':r['year'],'document_id':document_id(r['path']),'metric_code':f,'found':found,'candidate_rows_count':len(cs),'best_candidate_label':cs[0]['normalized_label'] if cs else None,'best_candidate_statement_code':None,'page':facts[f]['page'] if found else (cs[0]['page'] if cs else None),'reason_not_selected':reason})
   if len(stage1_dump)<5 and not found: stage1_dump.append({'ticker':r['ticker'],'year':r['year'],'metric_code':f,'candidates':cs[:10]})
 result={'documents_processed':len(ds),'matrix':matrix,'row_coverage':coverage,'candidate_rows_for_missing_stage1':stage1_dump,'miss_reason_distribution':dict(reasons),'html_parse_count':len(ds),'runtime_seconds':round(time.perf_counter()-t,3),'policy':'diagnostic only; no alias/selection changes'}
 (OUT/'mvp_extraction_miss_diagnostic.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 (OUT/'mvp_extraction_miss_diagnostic.md').write_text('# MVP extraction miss diagnostic\n\n'+json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'documents':len(ds),'facts_found':sum(x['found'] for x in matrix),'facts_total':len(matrix),'miss_reasons':dict(reasons),'rows':sum(x['html_row_count'] for x in coverage)},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
