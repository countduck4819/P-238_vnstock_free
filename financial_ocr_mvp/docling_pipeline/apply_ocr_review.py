import argparse, json, re
from pathlib import Path
from typing import Any

NUMBER=re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")
def valid(value: Any)->bool: return bool(NUMBER.fullmatch(str(value or "").strip()))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("mapping",type=Path); ap.add_argument("ocr_review",type=Path); ap.add_argument("validation_report",type=Path); ap.add_argument("output",type=Path); args=ap.parse_args()
    mapping=json.loads(args.mapping.read_text(encoding="utf-8")); review=json.loads(args.ocr_review.read_text(encoding="utf-8")); validation=json.loads(args.validation_report.read_text(encoding="utf-8"))
    entries=[]; approved=0; pending=0; lookup={t.get("table_id"):t for t in mapping.get("tables",[])}
    for item in review.get("items",[]):
        ok=str(item.get("confidence","")).lower()=="high" and valid(item.get("ocr_value")) and item.get("decision")=="candidate"; decision="candidate" if ok else "pending_review"; approved+=ok; pending+=not ok
        entry={"page":item.get("page"),"table":item.get("table"),"row":item.get("row"),"column":item.get("column"),"old_value":item.get("old_value"),"review_candidate":{"value":item.get("ocr_value"),"confidence":item.get("confidence"),"method":"RapidOCR","status":decision},"bbox":item.get("bbox"),"source_method":"RapidOCR","decision":decision}
        entries.append(entry)
        if item.get("table") in lookup: lookup[item.get("table")].setdefault("review_candidates",[]).append(entry)
    blocked=any(t.get("structural_status")=="BLOCKED" for t in validation.get("tables",[]))
    result={"status":"blocked" if blocked else "partial","summary":{"total_cells":len(entries),"approved_candidates":approved,"pending_review":pending},"review_candidates":entries,"mapping":mapping,"policy":{"raw_value_overwrite":False,"canonical_output":False}}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print("Saved:",args.output); print(result["summary"])
if __name__=="__main__": main()
