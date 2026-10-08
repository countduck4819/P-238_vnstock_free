"""Map a validated Docling raw grid to canonical financial rows.

This mapper is deterministic: it preserves source text and numeric strings exactly.
Semantic LLM mapping can be added later without changing the raw-grid contract.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from validate_raw_grid import validate_table

DOCUMENT={"ticker":"FPT","document_id":"FPT_Q1_2015","source_pdf":"FPT_Q1_2015.pdf","report_period":"Q1_2015","company_name":"Công ty Cổ phần FPT","exchange":"HOSE"}

def _cell_text(value: Any) -> str:
    return "" if value is None else str(value).strip()

def build_columns(headers: list[list[Any]]) -> list[str]:
    width=max((len(row) for row in headers),default=0); parent=[""]*width
    for row in headers:
        for i,value in enumerate(row):
            text=_cell_text(value)
            if text: parent[i]=text
    leaf=headers[-1] if headers else []
    result=[]
    for i in range(width):
        child=_cell_text(leaf[i] if i<len(leaf) else None)
        result.append(" / ".join(x for x in (parent[i],child) if x and x!=parent[i]) or parent[i] or f"column_{i}")
    return result

def map_table(table: dict[str,Any]) -> dict[str,Any]:
    errors=validate_table(table)
    if errors: return {"status":"needs_review","errors":errors,"source_grid":table}
    headers=table["headers"]; rows=table["rows"]; width=len(headers[0])
    columns=build_columns(headers)
    name_index=1; code_index=2; data_indices=list(range(4,width))
    mapped=[]
    for r,row in enumerate(rows):
        cells=[]
        for i in data_indices:
            raw=row[i]
            cells.append({"column":columns[i],"raw_value":raw,"source":{"pdf":DOCUMENT["source_pdf"],"page":table.get("source",{}).get("page"),"table":table.get("table_id"),"row":r,"column":i,"value":raw}})
        mapped.append({"row_name":row[name_index],"row_code":row[code_index],"cells":cells})
    return {"status":"ok","document":DOCUMENT,"statement":{"statement_type":"financial_statement","table_id":table.get("table_id"),"headers":columns},"rows":mapped,"raw_value_validation":{"policy":"exact_match","normalized":False}}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("input",type=Path); ap.add_argument("output",type=Path); args=ap.parse_args()
    data=json.loads(args.input.read_text(encoding="utf-8")); tables=data.get("tables",[])
    results=[]
    for table in tables:
        results.append(map_table(table))
    result={"schema":"financial_canonical_mapping_v1","tables":results}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print("Saved:",args.output)

if __name__=="__main__": main()
