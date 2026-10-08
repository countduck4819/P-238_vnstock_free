"""Retry pending numeric cells with a larger crop and RapidOCR."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

NUMBER_PATTERN = re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")


def expand_bbox(image: Image.Image, bbox: dict[str, Any], padding: int) -> tuple[dict[str, int], tuple[int, int, int, int]]:
    left = max(0, round(float(bbox["l"]) - padding))
    top = max(0, round(float(bbox["t"]) - padding))
    right = min(image.width, round(float(bbox["r"]) + padding))
    bottom = min(image.height, round(float(bbox["b"]) + padding))
    expanded = {"l": left, "t": top, "r": right, "b": bottom}
    return expanded, (left, top, right, bottom)


def prepare_crop(image: Image.Image, bbox: dict[str, Any], padding: int, scale: int) -> tuple[Image.Image, dict[str, int]]:
    expanded, box = expand_bbox(image, bbox, padding)
    crop = image.crop(box)
    resized = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
    return resized, expanded


def confidence_label(score: float) -> str:
    if score >= 0.90:
        return "high"
    if score >= 0.70:
        return "medium"
    return "low"


def validation_text(text: str | None) -> str:
    # Whitespace is removed only for validation; the OCR text is preserved in output.
    return re.sub(r"\s+", "", str(text or "").strip())


def is_valid_number(text: str | None) -> bool:
    return bool(NUMBER_PATTERN.fullmatch(validation_text(text)))


def run_retry(ocr: RapidOCR, image: Image.Image, bbox: dict[str, Any], padding: int, scale: int) -> tuple[str, float, dict[str, int]]:
    crop, expanded_bbox = prepare_crop(image, bbox, padding, scale)
    detected, _ = ocr(crop)
    if not detected:
        return "", 0.0, expanded_bbox

    # RapidOCR boxes are relative to the resized crop. Prefer detections whose
    # center is inside the original cell bbox. This prevents a high-confidence
    # value from a neighboring cell becoming the retry result merely because
    # the expanded crop contains more context.
    origin_left = (float(bbox["l"]) - expanded_bbox["l"]) * scale
    origin_top = (float(bbox["t"]) - expanded_bbox["t"]) * scale
    origin_right = (float(bbox["r"]) - expanded_bbox["l"]) * scale
    origin_bottom = (float(bbox["b"]) - expanded_bbox["t"]) * scale

    def center(entry: Any) -> tuple[float, float]:
        points = entry[0]
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    inside = []
    for entry in detected:
        cx, cy = center(entry)
        if origin_left <= cx <= origin_right and origin_top <= cy <= origin_bottom:
            inside.append(entry)
    pool = inside or detected
    best = max(pool, key=lambda entry: float(entry[2]))
    return str(best[1]).strip(), float(best[2]), expanded_bbox


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry pending RapidOCR cell candidates")
    parser.add_argument("review", type=Path, help="rapidocr_cell_review.json")
    parser.add_argument("image", type=Path, help="page table image")
    parser.add_argument("output", type=Path, help="rapidocr_retry_v2_review.json")
    parser.add_argument("--padding", type=int, default=60)
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()

    review = json.loads(args.review.read_text(encoding="utf-8"))
    image = Image.open(args.image).convert("RGB")
    ocr = RapidOCR()
    results: list[dict[str, Any]] = []

    items = review.get("items", review if isinstance(review, list) else [])
    for item in items:
        if item.get("decision") != "needs_review":
            continue

        bbox = item.get("bbox")
        first = item.get("ocr_value")
        second = ""
        score = 0.0
        expanded_bbox: dict[str, int] | None = None
        if bbox:
            second, score, expanded_bbox = run_retry(ocr, image, bbox, args.padding, args.scale)

        # The retry is the preferred candidate only when it is valid and high
        # confidence. Otherwise retain the first candidate for manual review.
        if is_valid_number(second) and score >= 0.90:
            best = second
            decision = "candidate"
        elif is_valid_number(first):
            best = first
            decision = "pending_review"
        else:
            best = second or first or ""
            decision = "pending_review"

        results.append({
            "page": item.get("page"),
            "table": item.get("table"),
            "row": item.get("row"),
            "column": item.get("column"),
            "old_value": item.get("old_value"),
            "first_candidate": first or "",
            "second_candidate": second,
            "best_candidate": best,
            "confidence": confidence_label(score),
            "ocr_score": score,
            "method": "RapidOCR_v2",
            "decision": decision,
            "bbox": bbox,
            "expanded_bbox": expanded_bbox,
        })

    output = {
        "schema": "rapidocr_retry_v2_review_v1",
        "policy": "pending_only_no_source_overwrite",
        "settings": {"padding": args.padding, "resize_scale": args.scale},
        "summary": {
            "retried": len(results),
            "candidates": sum(x["decision"] == "candidate" for x in results),
            "needs_review": sum(x["decision"] == "pending_review" for x in results),
        },
        "items": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", args.output)
    print(output["summary"])


if __name__ == "__main__":
    main()
