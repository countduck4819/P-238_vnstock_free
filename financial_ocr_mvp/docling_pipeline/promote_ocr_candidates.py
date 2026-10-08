import argparse, json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("validated",type=Path); ap.add_argument("ocr_review",type=Path); ap.add_argument("output",type=Path); args=ap.parse_args()
    data=json.loads(args.validated.read_text(encoding="utf-8")); review=json.loads(args.ocr_review.read_text(encoding="utf-8"))
    approved=[]
    for item in review.get("items",[]):
        if item.get("decision")!="candidate" or str(item.get("confidence","")).lower()!="high": continue
        approved.append({"page":item.get("page"),"table":item.get("table"),"row":item.get("row"),"column":item.get("column"),"value":item.get("ocr_value"),"confidence":item.get("confidence"),"method":"RapidOCR","status":"verified_candidate","bbox":item.get("bbox")})
    result={"schema":"verified_semantic_mapping_v1","status":"partial" if approved else data.get("status","partial"),"summary":{"verified_candidates":len(approved),"raw_values_overwritten":0},"verified_candidates":approved,"mapping":data.get("mapping",data)}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print("Saved:",args.output); print(result["summary"])
if __name__=="__main__": main()
