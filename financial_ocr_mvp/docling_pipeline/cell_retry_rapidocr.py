import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

NUMBER_PATTERN = re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")

def crop_cell(image: Image.Image, bbox: dict[str, Any], padding: int, scale: int):
    left=max(0, round(float(bbox["l"])-padding)); top=max(0, round(float(bbox["t"])-padding))
    right=min(image.width, round(float(bbox["r"])+padding)); bottom=min(image.height, round(float(bbox["b"])+padding))
    crop=image.crop((left,top,right,bottom))
    return crop.resize((crop.width*scale,crop.height*scale),Image.Resampling.LANCZOS)

def label(score: float) -> str:
    return "high" if score >= 0.90 else "medium" if score >= 0.70 else "low"

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("queue",type=Path); ap.add_argument("image",type=Path); ap.add_argument("output",type=Path); ap.add_argument("--padding",type=int,default=30); ap.add_argument("--scale",type=int,default=3); args=ap.parse_args()
    queue=json.loads(args.queue.read_text(encoding="utf-8")); image=Image.open(args.image).convert("RGB"); ocr=RapidOCR(); results=[]
    for item in queue.get("items",[]):
        text=None; score=0.0; bbox=item.get("bbox")
        if bbox:
            detected,_=ocr(crop_cell(image,bbox,args.padding,args.scale))
            if detected:
                best=max(detected,key=lambda entry: float(entry[2])); text=str(best[1]).strip(); score=float(best[2])
        confidence=label(score); valid=bool(NUMBER_PATTERN.fullmatch(text or ""))
        results.append({"page":item.get("page"),"table":item.get("table"),"row":item.get("row"),"column":item.get("column"),"old_value":item.get("old_value"),"ocr_value":text,"confidence":confidence,"decision":"candidate" if valid and confidence=="high" else "needs_review","method":"RapidOCR","bbox":bbox,"ocr_score":score})
    output={"schema":"rapidocr_cell_review_v1","policy":"candidate_only_no_source_overwrite","items":results}; args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8"); print("Saved:",args.output); print("candidates:",sum(x["decision"]=="candidate" for x in results),"needs_review:",sum(x["decision"]=="needs_review" for x in results))

if __name__=="__main__": main()
