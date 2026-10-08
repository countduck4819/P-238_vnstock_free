"""Retry suspicious financial cells with Qwen vision without overwriting source data."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

MODEL_NAME = "Qwen/Qwen2.5-VL-3B-Instruct"
NUMBER_PATTERN = re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")

PROMPT = """Bạn là Financial OCR Verification Engine.

Đọc duy nhất một ô số tài chính trong ảnh.
Chỉ đọc đúng ký tự nhìn thấy; không suy luận, tính toán, sửa theo logic kế toán,
thêm dấu chấm, bỏ dấu ngoặc hoặc đổi format.
Nếu nhìn thấy (5.126.536.321) phải trả đúng (5.126.536.321).
Nếu không chắc chắn, value phải là null và confidence là low.

Chỉ trả JSON object đúng dạng:
{"value": null, "confidence": "high|medium|low"}
Không markdown. Không giải thích."""


def valid_numeric(value: Any) -> bool:
    if value is None:
        return False
    return bool(NUMBER_PATTERN.fullmatch(str(value).strip()))


def parse_response(text: str) -> tuple[str | None, str]:
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            confidence = str(value.get("confidence", "low")).lower()
            candidate = value.get("value")
            return (None if candidate is None else str(candidate), confidence)
    return None, "low"


def crop(image: Image.Image, bbox: dict[str, Any]) -> Image.Image:
    left, top, right, bottom = (bbox[key] for key in ("l", "t", "r", "b"))
    # Add a small margin so Qwen can see punctuation without including neighboring cells.
    margin = 8
    return image.crop((round(left) - margin, round(top) - margin, round(right) + margin, round(bottom) + margin))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("queue", type=Path)
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    image = Image.open(args.image).convert("RGB")

    print("Loading Qwen...")
    processor = AutoProcessor.from_pretrained(MODEL_NAME)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_NAME, torch_dtype=torch.float16, device_map="auto"
    )
    model.eval()

    results = []
    for index, item in enumerate(queue.get("items", []), start=1):
        old_value = item.get("old_value")
        bbox = item.get("bbox")
        qwen_value = None
        confidence = "low"
        reason = "missing_bbox"

        if bbox:
            cell_image = crop(image, bbox)
            messages = [{"role": "user", "content": [
                {"type": "image", "image": cell_image},
                {"type": "text", "text": PROMPT},
            ]}]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[text], images=[cell_image], return_tensors="pt").to(model.device)
            with torch.no_grad():
                output = model.generate(**inputs, max_new_tokens=100, do_sample=False)
            generated = output[:, inputs.input_ids.shape[1]:]
            response = processor.batch_decode(generated, skip_special_tokens=True)[0]
            qwen_value, confidence = parse_response(response)
            reason = "high_confidence_valid_numeric" if confidence == "high" and valid_numeric(qwen_value) else "low_confidence_or_invalid_numeric"

        decision = "approved" if confidence == "high" and valid_numeric(qwen_value) else "needs_review"
        results.append({
            "page": item.get("page"),
            "table": item.get("table"),
            "row": item.get("row"),
            "column": item.get("column"),
            "old_value": old_value,
            "qwen_value": qwen_value,
            "confidence": confidence,
            "decision": decision,
            "reason": reason,
            "bbox": bbox,
        })
        print(f"[{index}/{len(queue.get('items', []))}] {decision}: {old_value!r} -> {qwen_value!r}")

    output = {
        "schema": "qwen_cell_review_v1",
        "policy": "candidate_only_no_source_overwrite",
        "items": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", args.output)


if __name__ == "__main__":
    main()
