"""Apply Qwen review metadata without overwriting financial raw values."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DIGIT=re.compile(r"[0-9]")

def digits(value: Any) -> str:
    return "".join(DIGIT.findall("" if value is None else str(value)))

def evaluate(item: dict[str,Any]) -> dict[str,Any]:
    old=item.get("old_value"); qwen=item.get("qwen_value"); same=bool(digits(old)) and digits(old)==digits(qwen)
    high=str(item.get("confidence","")).lower()=="high"
    if same and high: decision="approved"; reason="same_digit_sequence_format_only"
    else: decision="pending_review"; reason="different_digit_sequence" if not same else "confidence_not_high"
    return {"page":item.get("page"),"table":item.get("table"),"row":item.get("row"),"column":item.get("column"),"old_value":old,"review_candidate":qwen,"decision":decision,"reason":reason,"confidence":item.get("confidence"),"source":"Qwen2.5-VL-3B-Instruct"}

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("mapping",type=Path); ap.add_argument("qwen_review",type=Path); ap.add_argument("validation_report",type=Path); ap.add_argument("output",type=Path); args=ap.parse_args()
    mapping=json.loads(args.mapping.read_text(encoding="utf-8")); qwen=json.loads(args.qwen_review.read_text(encoding="utf-8")); report=json.loads(args.validation_report.read_text(encoding="utf-8"))
    corrections=[evaluate(item) for item in qwen.get("items",[])]
    structural_blocked=any(t.get("structural_status")=="BLOCKED" for t in report.get("tables",[]))
    status="blocked" if structural_blocked else ("partial" if corrections or report.get("summary",{}).get("partial",0) else "ok")
    result={"status":status,"corrections":corrections,"mapping":mapping,"policy":{"raw_value_overwrite":False,"financial_normalization":False}}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print("Saved:",args.output); print("approved:",sum(x["decision"]=="approved" for x in corrections),"pending_review:",sum(x["decision"]=="pending_review" for x in corrections))

if __name__=="__main__": main()
