"""Qwen cell retry v2: expanded context crop and upscaling."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

MODEL_NAME="Qwen/Qwen2.5-VL-3B-Instruct"
PROMPT="""Bạn là Financial OCR Verification Engine.
Đọc duy nhất ô số tài chính trong ảnh, có thể có các ô lân cận để xác định ngữ cảnh.
Chỉ chép đúng ký tự nhìn thấy. Không suy luận, tính toán, sửa theo logic kế toán,
thêm/bớt chữ số, thêm/bớt dấu chấm hoặc bỏ dấu ngoặc. Nếu không chắc chắn trả value null.
Trả duy nhất JSON: {"value": null, "confidence": "high|medium|low"}."""


def parse_json(text: str):
    decoder=json.JSONDecoder()
    for i,char in enumerate(text):
        if char!="{": continue
        try: value,_=decoder.raw_decode(text[i:])
        except json.JSONDecodeError: continue
        if isinstance(value,dict): return value.get("value"),str(value.get("confidence","low")).lower()
    return None,"low"

def expanded_crop(image: Image.Image,bbox: dict[str,Any],padding: int,scale: int):
    original=tuple(float(bbox[k]) for k in ("l","t","r","b"))
    left=max(0,round(original[0]-padding)); top=max(0,round(original[1]-padding))
    right=min(image.width,round(original[2]+padding)); bottom=min(image.height,round(original[3]+padding))
    crop=image.crop((left,top,right,bottom))
    resized=crop.resize((crop.width*scale,crop.height*scale),Image.Resampling.LANCZOS)
    return resized,{"l":left,"t":top,"r":right,"b":bottom}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("queue",type=Path); ap.add_argument("image",type=Path); ap.add_argument("output",type=Path); ap.add_argument("--padding",type=int,default=30); ap.add_argument("--scale",type=int,choices=(2,3),default=2); args=ap.parse_args()
    queue=json.loads(args.queue.read_text(encoding="utf-8")); image=Image.open(args.image).convert("RGB")
    processor=AutoProcessor.from_pretrained(MODEL_NAME); model=Qwen2_5_VLForConditionalGeneration.from_pretrained(MODEL_NAME,torch_dtype=torch.float16,device_map="auto"); model.eval()
    items=queue.get("items",[]); results=[]
    for index,item in enumerate(items,1):
        bbox=item.get("bbox"); value=None; confidence="low"; expanded=None
        if bbox:
            crop,expanded=expanded_crop(image,bbox,args.padding,args.scale)
            messages=[{"role":"user","content":[{"type":"image","image":crop},{"type":"text","text":PROMPT}]}]
            text=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            inputs=processor(text=[text],images=[crop],return_tensors="pt").to(model.device)
            with torch.no_grad(): output=model.generate(**inputs,max_new_tokens=100,do_sample=False)
            generated=output[:,inputs.input_ids.shape[1]:]
            value,confidence=parse_json(processor.batch_decode(generated,skip_special_tokens=True)[0])
        results.append({"page":item.get("page"),"table":item.get("table"),"row":item.get("row"),"column":item.get("column"),"old_value":item.get("old_value"),"qwen_value":value,"confidence":confidence,"decision":"needs_review","original_bbox":bbox,"expanded_bbox":expanded,"resize_scale":args.scale})
        print(f"[{index}/{len(items)}] {item.get('old_value')!r} -> {value!r} ({confidence})")
    output={"schema":"qwen_cell_review_v1","items":results}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8"); print("Saved:",args.output)

if __name__=="__main__": main()
