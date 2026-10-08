from __future__ import annotations
import json,time,statistics
from pathlib import Path
from .mvp_extractor_context import build_document_context,extract_all_facts,validate,FACTS
from .registry_models import document_id
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"financial_ocr_mvp/output"; NORM=OUT/"phase3_normalized"
def run(n):
 inv=json.loads((OUT/"dataset_inventory.json").read_text())["reports"]; docs=[]
 for r in inv:
  if r["year"] in (2021,2022,2023,2024,2025) and r["has_table"]:
   p=NORM/r["ticker"]/str(r["year"])/(document_id(r["path"])+".txt")
   if p.exists(): docs.append((r,p))
  if len(docs)>=n: break
 rows=[]; found=0; t0=time.perf_counter()
 for r,p in docs:
  s=time.perf_counter(); ctx,t=build_document_context(p,document_id(r["path"]),r["ticker"],r["year"]); a=time.perf_counter(); facts=extract_all_facts(ctx); b=time.perf_counter(); ok=validate(facts); e=time.perf_counter()
  found+=sum(v is not None for v in facts.values()); rows.append({"ticker":r["ticker"],"year":r["year"],"html_parse_count":ctx.html_parse_count,"facts_found":sum(v is not None for v in facts.values()),"valid":ok,"total_document_ms":round((e-s)*1000,3),"read_ms":t["read_ms"],"index_extract_ms":round((b-a)*1000,3),"validation_ms":round((e-b)*1000,3),"evidence_complete":all(v is not None and "page" in v for v in facts.values())})
 durations=[x["total_document_ms"] for x in rows]; result={"documents_processed":len(rows),"html_parse_count":sum(x["html_parse_count"] for x in rows),"facts_found":found,"runtime_seconds":round(time.perf_counter()-t0,3),"docs_per_second":round(len(rows)/(time.perf_counter()-t0),3) if rows else 0,"p50_total_document_ms":round(statistics.median(durations),3) if durations else None,"p95_total_document_ms":round(sorted(durations)[max(0,int(len(durations)*.95)-1)],3) if durations else None,"documents":rows,"pass":len(rows)==n and all(x["html_parse_count"]==1 and x["evidence_complete"] for x in rows)}
 return result
if __name__=="__main__":
 result={"stage_1_5":run(5),"stage_2_20":run(20)}; (OUT/"mvp_extractor_performance_fix.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8"); (OUT/"mvp_extractor_performance_fix.md").write_text("# MVP extractor performance fix\n\n"+json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8"); print(json.dumps(result,ensure_ascii=False,indent=2))
