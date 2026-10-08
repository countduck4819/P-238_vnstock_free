"""Create and optionally retry OCR for suspicious Docling cells.

This module never overwrites raw_value. It emits review_queue.json and keeps the
original value when OCR retry is unavailable or not high-confidence.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError:
    Image = None

NUMERIC = re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")

def suspicious(value: Any) -> bool:
    if value in (None, ""): return False
    text=str(value).strip()
    return not bool(NUMERIC.fullmatch(text))

def cell_sources(table: dict[str,Any]) -> dict[tuple[int,int],dict[str,Any]]:
    matrix=table.get("cell_sources",[])
    return {(r,c): source for r,row in enumerate(matrix) for c,source in enumerate(row) if source}

def retry_ocr(image_path: Path, bbox: dict[str,Any]) -> tuple[str|None,float,str]:
    if Image is None: return None,0.0,"Pillow unavailable"
    try:
        image=Image.open(image_path).convert("RGB")
        left,top,right,bottom=(bbox.get(k) for k in ("l","t","r","b"))
        crop=image.crop((round(left),round(top),round(right),round(bottom)))
        # Optional dependency; no OCR result is accepted without explicit confidence.
        from rapidocr_onnxruntime import RapidOCR
        engine=RapidOCR()
        result,_=engine(crop)
        text="".join(item[1] for item in (result or [])).strip()
        return (text or None, 0.0, "RapidOCR confidence unavailable; not auto-approved")
    except Exception as exc:
        return None,0.0,f"retry unavailable: {exc}"

def build_queue(mapping: dict[str,Any], image_path: Path|None, retry: bool, source_page: str|None = None) -> dict[str,Any]:
    queue=[]
    for table in mapping.get("tables",[]):
        if table.get("status")!="needs_review": continue
        source_grid=table.get("source_grid",{})
        lookup=cell_sources(source_grid)
        rows=source_grid.get("rows",[])
        headers=source_grid.get("headers",[])
        width=max((len(row) for row in headers+rows),default=0)
        for row_index,row in enumerate(rows):
            for col_index,value in enumerate(row):
                if col_index < 4 or not suspicious(value): continue
                trace=lookup.get((row_index+len(headers),col_index),{})
                item={"page":source_page or source_grid.get("source",{}).get("page"),"table":source_grid.get("table_id"),"row":row_index,"column":col_index,"old_value":value,"new_value":None,"status":"needs_review","reason":"ocr_numeric_error","bbox":trace.get("bbox"),"trace":trace}
                if retry and image_path and trace.get("bbox"):
                    new,confidence,note=retry_ocr(image_path,trace["bbox"]); item["ocr_retry_value"]=new; item["ocr_retry_confidence"]=confidence; item["ocr_retry_note"]=note
                    if new and confidence>=0.99 and NUMERIC.fullmatch(new): item["new_value"]=new; item["status"]="candidate"
                queue.append(item)
    return {"schema":"financial_review_queue_v1","policy":"never_overwrite_raw_value","items":queue}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("input",type=Path); ap.add_argument("output",type=Path); ap.add_argument("--image",type=Path); ap.add_argument("--retry",action="store_true"); ap.add_argument("--source-page"); args=ap.parse_args()
    mapping=json.loads(args.input.read_text(encoding="utf-8")); result=build_queue(mapping,args.image,args.retry,args.source_page)
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print("Saved:",args.output,"items:",len(result["items"]))

if __name__=="__main__": main()
