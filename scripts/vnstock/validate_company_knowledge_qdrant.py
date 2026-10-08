"""Validate pilot collection contract, idempotency, payload and filtered retrieval."""
from __future__ import annotations
import argparse, json, os, re
from pathlib import Path
from qdrant_client import QdrantClient, models
import sentence_transformers, torch
from sentence_transformers import SentenceTransformer

ROOT=Path(__file__).resolve().parents[2]; META=ROOT/'data'/'vnstock'/'metadata'; CONFIG=META/'company_knowledge_embedding_config.json'; REPORT=META/'company_knowledge_qdrant_pilot_report.md'; SUMMARY=META/'company_knowledge_qdrant_pilot_summary.json'
def configured_value(name):
 value=os.environ.get(name)
 if value: return value.strip().strip("\"'")
 env_file=ROOT/'.env'
 if not env_file.exists(): return None
 match=re.search(rf'^\s*{re.escape(name)}\s*=\s*(.*)$',env_file.read_text(encoding='utf-8'),re.MULTILINE)
 return match.group(1).strip().strip("\"'") if match else None
TESTS=[('FPT','mô hình kinh doanh','company_profile'),('FPT','lịch sử công ty','company_history'),('ACB','ban lãnh đạo quản lý','management'),('ACB','thông tin công ty','company_profile'),('SSI','ban lãnh đạo','management'),('SSI','thông tin niêm yết','listing_info'),('BVH','lịch sử hình thành','company_history'),('BVH','mô hình kinh doanh địa chỉ và loại hình công ty','company_profile')]
def main():
 p=argparse.ArgumentParser(); p.add_argument('--full',action='store_true'); a=p.parse_args(); cfg=json.loads(CONFIG.read_text(encoding='utf-8')); client=QdrantClient(url=configured_value('QDRANT_URL') or cfg['qdrant_url'],api_key=configured_value('QDRANT_API_KEY') or None,timeout=60); info=client.get_collection(cfg['collection_name']); params=info.config.params.vectors; count=client.count(cfg['collection_name'],exact=True).count
 embedder=SentenceTransformer(cfg['embedding_model'],revision=cfg.get('embedding_revision'),local_files_only=True); query_vectors=embedder.encode([x[1] for x in TESTS],show_progress_bar=False,normalize_embeddings=True); results=[]
 for (ticker,query,expected),vector in zip(TESTS,query_vectors):
  response=client.query_points(collection_name=cfg['collection_name'],query=vector.tolist(),query_filter=models.Filter(must=[models.FieldCondition(key='ticker',match=models.MatchValue(value=ticker))]),limit=1,with_payload=True).points; top=response[0] if response else None; payload=top.payload if top else {}; text=str(payload.get('text','')).replace('\n',' '); results.append({'ticker_filter':ticker,'query':query,'expected_document_type':expected,'top_document_type':payload.get('document_type'),'returned_ticker':payload.get('ticker'),'score':round(float(top.score),6) if top else None,'snippet':text[:180],'pass':bool(top and payload.get('ticker')==ticker and payload.get('document_type')==expected)})
 payload_points=[]; offset=None
 while True:
  page,offset=client.scroll(cfg['collection_name'],limit=100,offset=offset,with_payload=True,with_vectors=False); payload_points.extend(page)
  if offset is None: break
 required=['document_id','ticker','document_type','source_provider','source_files','content_hash','embedding_model','embedding_revision','embedding_mode']; missing_payload=sum(any(x.payload.get(k) in (None,'') for k in required) for x in payload_points); expected=count
 duplicate_point_ids=len(payload_points)-len({str(x.id) for x in payload_points}); expected_document_ids=0
 if a.full:
  docs_path=META/'company_knowledge_documents.jsonl'; docs=[json.loads(x) for x in docs_path.read_text(encoding='utf-8').splitlines() if x.strip()]; expected=len(docs); expected_document_ids=len(docs)-len({x['document_id'] for x in docs})
 passed=params.size==1024 and params.distance==models.Distance.COSINE and count==expected and (count>=16 if a.full else count==16) and missing_payload==0 and duplicate_point_ids==0 and expected_document_ids==0 and all(x['pass'] for x in results)
 summary={'embedding_runtime':'sentence-transformers','embedding_runtime_version':sentence_transformers.__version__,'torch_version':torch.__version__,'embedding_model':cfg['embedding_model'],'embedding_revision':cfg.get('embedding_revision'),'vector_dimension':params.size,'distance':str(params.distance),'collection':cfg['collection_name'],'pilot_point_count':count,'expected_document_count':expected,'idempotency_check':'PASS' if count==expected and duplicate_point_ids==0 else 'FAIL','duplicate_point_ids':duplicate_point_ids,'duplicate_document_ids':expected_document_ids,'ticker_coverage':len({x.payload.get('ticker') for x in payload_points}),'document_type_counts':{k:sum(x.payload.get('document_type')==k for x in payload_points) for k in sorted({x.payload.get('document_type') for x in payload_points})},'payload_missing_count':missing_payload,'retrieval_results':results,'ticker_filter_pass':all(x['returned_ticker']==x['ticker_filter'] for x in results),'numerical_query_route':'POSTGRESQL','qdrant_pilot':'PASS' if passed else 'FAIL'}; SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# Company Knowledge Qdrant Pilot','',f"Pilot: **{summary['qdrant_pilot']}**; collection `{cfg['collection_name']}`, points **{count}**, dense dimension **{params.size}**, distance **{params.distance}**.",f"Embedding: `{cfg['embedding_model']}` revision `{cfg.get('embedding_revision')}`, normalized dense vectors. Runtime: sentence-transformers {sentence_transformers.__version__}, torch {torch.__version__}. Payload missing: **{missing_payload}**; idempotency: **{summary['idempotency_check']}**.",'','## Retrieval','','| Ticker filter | Query | Top type | Score | PASS |','|---|---|---|---:|---|']+[f"| {x['ticker_filter']} | {x['query']} | {x['top_document_type']} | {x['score']} | {x['pass']} |" for x in results]+['','Ticker filter guard: **PASS**.' if summary['ticker_filter_pass'] else 'Ticker filter guard: **FAIL**.','Numerical query route: **POSTGRESQL**. No financial statement facts are stored in this collection.','',f"**QDRANT_PILOT = {summary['qdrant_pilot']}**"]
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps({'point_count':count,'payload_missing':missing_payload,'retrieval_pass':sum(x['pass'] for x in results),'ticker_filter_pass':summary['ticker_filter_pass'],'qdrant_pilot':summary['qdrant_pilot']},ensure_ascii=False)); return 0 if passed else 1
if __name__=='__main__': raise SystemExit(main())
