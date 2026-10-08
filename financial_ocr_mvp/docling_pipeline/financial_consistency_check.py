"""Two-layer financial validation: structure can pass while values need review."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

NUMBER=re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")

def structural_issues(table: dict[str,Any]) -> list[dict[str,Any]]:
    issues=[]; source=table.get("source_grid",table); headers=source.get("headers",[]); rows=source.get("rows",[])
    if not headers: issues.append({"type":"missing_header"})
    width=max((len(row) for row in headers),default=0)
    for i,row in enumerate(headers+rows):
        if len(row)!=width: issues.append({"type":"column_count_mismatch","row":i,"expected":width,"actual":len(row)})
    if not source.get("cell_sources"): issues.append({"type":"missing_bbox_trace"})
    if width<3: issues.append({"type":"insufficient_columns"})
    return issues

def value_issues(table: dict[str,Any], qwen_items: list[dict[str,Any]]) -> list[dict[str,Any]]:
    issues=[]; source=table.get("source_grid",table); headers=source.get("headers",[]); rows=source.get("rows",[])
    width=max((len(row) for row in headers),default=0)
    for r,row in enumerate(rows):
        for c,value in enumerate(row):
            if c>=4 and value not in (None,"") and not NUMBER.fullmatch(str(value).strip()):
                issues.append({"type":"ocr_error","row":r,"column":c,"value":value})
    for item in qwen_items:
        if item.get("decision") in {"needs_review", "candidate"}:
            issues.append({"type": "cell_review", "method": item.get("method", "OCR"), "row": item.get("row"), "column": item.get("column"), "value": item.get("old_value"), "candidate": item.get("ocr_value", item.get("qwen_value")), "decision": item.get("decision")})
    return issues

def table_report(table: dict[str,Any], qwen_items: list[dict[str,Any]]) -> dict[str,Any]:
    structural=structural_issues(table); values=value_issues(table,qwen_items)
    if structural: status="BLOCKED"
    elif values: status="PARTIAL"
    else: status="OK"
    return {"table_id":table.get("table_id",table.get("source_grid",{}).get("table_id")),"table_status":status,"structural_status":"BLOCKED" if structural else "OK","value_status":"PARTIAL" if values else "OK","issues":structural+values}

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("semantic_mapping",type=Path); ap.add_argument("qwen_review",type=Path); ap.add_argument("output",type=Path); args=ap.parse_args()
    mapping=json.loads(args.semantic_mapping.read_text(encoding="utf-8"))
    qwen=json.loads(args.qwen_review.read_text(encoding="utf-8"))
    tables_source=mapping.get("mapping", mapping)
    qwen_items=qwen.get("items",[])
    reports=[table_report(table,qwen_items) for table in tables_source.get("tables",[])]
    result={"schema":"semantic_validation_report_v1","tables":reports,"summary":{"total":len(reports),"ok":sum(x["table_status"]=="OK" for x in reports),"partial":sum(x["table_status"]=="PARTIAL" for x in reports),"blocked":sum(x["table_status"]=="BLOCKED" for x in reports)}}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print("Saved:",args.output); print(result["summary"])

if __name__=="__main__": main()
