"""Evaluate Qwen OCR candidates without changing source values."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DIGITS = re.compile(r"[0-9]")

def digits_only(value: Any) -> str:
    return "".join(DIGITS.findall("" if value is None else str(value)))

def format_candidate(qwen_value: Any) -> str | None:
    digits = digits_only(qwen_value)
    if not digits:
        return None
    groups=[]
    while digits:
        groups.append(digits[-3:]); digits=digits[:-3]
    return ".".join(reversed(groups))

def evaluate(item: dict[str,Any]) -> dict[str,Any]:
    old=item.get("old_value"); qwen=item.get("qwen_value")
    old_digits=digits_only(old); qwen_digits=digits_only(qwen)
    same=bool(old_digits) and old_digits==qwen_digits
    high=str(item.get("confidence","")).lower()=="high"
    candidate=format_candidate(qwen) if same else None
    if same and high:
        decision="candidate"; reason="same_digits_format_difference"
    else:
        decision="needs_review"; reason="different_numeric_value" if old_digits!=qwen_digits else "confidence_not_high"
    result={"page":item.get("page"),"table":item.get("table"),"row":item.get("row"),"column":item.get("column"),"old_value":old,"qwen_value":qwen,"candidate_value":candidate,"confidence":item.get("confidence"),"decision":decision,"reason":reason}
    return result

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("input",type=Path); ap.add_argument("output",type=Path); args=ap.parse_args()
    data=json.loads(args.input.read_text(encoding="utf-8"))
    result={"schema":"qwen_cell_candidates_v1","items":[evaluate(item) for item in data.get("items",[])]}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Saved:",args.output)
    print("candidates:",sum(x["decision"]=="candidate" for x in result["items"]))
    print("needs_review:",sum(x["decision"]=="needs_review" for x in result["items"]))

if __name__=="__main__": main()
