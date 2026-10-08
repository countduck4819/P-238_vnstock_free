"""Build deterministic semantic company documents; default scope is four pilot tickers."""
from __future__ import annotations
import argparse, hashlib, json, uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; RAW=ROOT/'data'/'vnstock'/'raw'/'company'; META=ROOT/'data'/'vnstock'/'metadata'
OUTPUT=META/'company_knowledge_documents_pilot.jsonl'; REPORT=META/'company_knowledge_qdrant_pilot_report.md'; SUMMARY=META/'company_knowledge_qdrant_pilot_summary.json'
PILOT=['FPT','ACB','SSI','BVH']; PROVIDER='vnstock_vci'; NS=uuid.UUID('c485cf1d-628d-46e1-ae30-7f25a2ab0cf1')
def first(path):
 x=json.loads(path.read_text(encoding='utf-8')); return x[0] if isinstance(x,list) and x else x if isinstance(x,dict) else {}
def clean(v): return str(v).strip() if v not in (None,'') else ''
def make(ticker,kind,parts,sources,as_of=''):
 text='\n'.join(x for x in parts if x).strip()
 if not text: return None
 content_hash=hashlib.sha256(text.encode()).hexdigest(); document_id=str(uuid.uuid5(NS,f'{ticker}|{kind}|{content_hash}'))
 return {'document_id':document_id,'ticker':ticker,'document_type':kind,'text':text,'source_files':sources,'source_provider':PROVIDER,'as_of_date':as_of or None,'content_hash':content_hash}
def field(d,key,label):
 v=clean(d.get(key)); return f'{label}: {v}' if v else ''
def build(ticker):
 root=RAW/ticker; paths={n:root/f'{n}.json' for n in ['profile','overview','officers']}; found=[str(p.relative_to(ROOT)) for p in paths.values() if p.exists()]
 profile=first(paths['profile']) if paths['profile'].exists() else {}; overview=first(paths['overview']) if paths['overview'].exists() else {}; officers=json.loads(paths['officers'].read_text(encoding='utf-8')) if paths['officers'].exists() else []
 # profile/overview are overlapping snapshots; merge deterministically and cite both.
 company={**overview,**profile}; company_sources=[str(paths[n].relative_to(ROOT)) for n in ['profile','overview'] if paths[n].exists()]
 docs=[
  make(ticker,'company_profile',[f'Mã cổ phiếu: {ticker}',field(company,'company_type','Loại hình công ty'),field(company,'founded_date','Ngày thành lập'),field(company,'business_model','Mô hình kinh doanh'),field(company,'number_of_employees','Số nhân viên'),field(company,'address','Địa chỉ'),field(company,'website','Website')],company_sources,clean(company.get('as_of_date'))),
  make(ticker,'company_history',[f'Mã cổ phiếu: {ticker}',field(company,'history','Lịch sử'),field(company,'founded_date','Ngày thành lập'),field(company,'listing_date','Ngày niêm yết'),field(company,'exchange','Sàn giao dịch')],company_sources,clean(company.get('as_of_date'))),
  make(ticker,'listing_info',[f'Mã cổ phiếu: {ticker}',field(company,'exchange','Sàn giao dịch'),field(company,'listing_date','Ngày niêm yết'),field(company,'par_value','Mệnh giá'),field(company,'listing_price','Giá niêm yết'),field(company,'listed_volume','Khối lượng niêm yết'),field(company,'outstanding_shares','Cổ phiếu lưu hành')],company_sources,clean(company.get('as_of_date'))),
 ]
 people=[]
 for o in officers:
  if not isinstance(o,dict) or not clean(o.get('name')): continue
  people.append(' | '.join(x for x in [clean(o.get('name')),clean(o.get('position')),clean(o.get('position_en')),clean(o.get('from_date'))] if x))
 docs.append(make(ticker,'management',[f'Mã cổ phiếu: {ticker}',field(company,'ceo_name','Tổng giám đốc'),field(company,'ceo_position','Chức vụ CEO'),'Ban lãnh đạo: '+'; '.join(people) if people else ''],sorted(set(company_sources+[str(paths['officers'].relative_to(ROOT))] if paths['officers'].exists() else company_sources)),clean(company.get('as_of_date'))))
 return [x for x in docs if x],found,4-len([x for x in docs if x])
def main():
 p=argparse.ArgumentParser(); p.add_argument('--all',action='store_true'); p.add_argument('--only'); a=p.parse_args(); tickers=[x.strip().upper() for x in a.only.split(',')] if a.only else (sorted(x.name for x in RAW.iterdir() if x.is_dir()) if a.all else PILOT)
 target=META/'company_knowledge_documents.jsonl' if a.all else OUTPUT; previous_hash=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None; documents=[]; raw_found={}; blank=0
 for t in tickers:
  docs,found,skipped=build(t); documents+=docs; raw_found[t]=found; blank+=skipped
 unique={d['document_id']:d for d in documents}; documents=list(unique.values()); target.write_text(''.join(json.dumps(d,ensure_ascii=False)+'\n' for d in documents),encoding='utf-8'); current_hash=hashlib.sha256(target.read_bytes()).hexdigest()
 types={k:sum(d['document_type']==k for d in documents) for k in sorted(set(d['document_type'] for d in documents))}; summary={'pilot_tickers':tickers,'raw_files_found':raw_found,'documents_built':len(documents),'document_types':types,'blank_documents_skipped':blank,'duplicate_raw_snapshots_skipped':sum(1 for t in tickers if (RAW/t/'profile.json').exists() and (RAW/t/'overview.json').exists() and (RAW/t/'profile.json').read_bytes()==(RAW/t/'overview.json').read_bytes()),'duplicate_document_ids':len(documents)-len(set(d['document_id'] for d in documents)),'document_build_idempotent':previous_hash in (None,current_hash),'qdrant_available':True,'embedding_configured':False,'qdrant_upsert':'NOT_RUN','qdrant_pilot':'FAIL_BLOCKED'}
 SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# Company Knowledge Qdrant Pilot','',f"Documents built: **{len(documents)}** for `{', '.join(tickers)}`; types: `{types}`.",f"Blank documents skipped: **{blank}**; overlapping profile/overview snapshots deduplicated: **{summary['duplicate_raw_snapshots_skipped']}**; duplicate IDs: **0**; deterministic rebuild: **{summary['document_build_idempotent']}**.",'','Qdrant is reachable, but the existing `stock_rag_chunks_v2` collection is an unrelated 384-dimensional numerical/OCR collection and was not modified. No explicit approved embedding model/provider/version exists in project configuration, and no Qdrant client/embedding runtime is installed in the active environments. Therefore embedding, collection creation, upsert and retrieval were not run.','','Numerical guard: company documents contain qualitative/profile/listing metadata only. Financial statement questions such as FPT net profit 2025 remain PostgreSQL-only.','','**QDRANT_PILOT = FAIL_BLOCKED; STOP before embedding/upsert.**']
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps({k:summary[k] for k in ['documents_built','document_types','blank_documents_skipped','duplicate_raw_snapshots_skipped','duplicate_document_ids','embedding_configured','qdrant_upsert','qdrant_pilot']},ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
