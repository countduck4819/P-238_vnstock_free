import argparse, json, re, unicodedata
from difflib import SequenceMatcher
from decimal import Decimal
from pathlib import Path

NUMBER=re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")

def candidate_for_validation(value):
    """Remove OCR whitespace only; never invent digits or separators."""
    if value is None:
        return ""
    text = str(value).strip()
    if re.fullmatch(r"[0-9.()\s]+", text):
        return re.sub(r"\s+", "", text)
    return text


def parse(value):
    if value is None or not NUMBER.fullmatch(str(value).strip()): return None
    text=str(value).strip(); neg=text.startswith("("); text=text.strip("()")
    try:
        number=Decimal(text.replace(".","")); return -number if neg else number
    except Exception: return None

def rows_from_table(table):
    source=table.get("source_grid",{}); headers=source.get("headers",[]); rows=source.get("rows",[])
    return headers,rows

def normalize_label(value):
    """Normalize labels only for matching; the source label is never changed."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("đ", "d")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def row_index(rows, terms):
    normalized_terms = [normalize_label(term) for term in terms]
    best = (0.0, None)
    for i, row in enumerate(rows):
        name = normalize_label(row[1] if len(row) > 1 else "")
        if not name:
            continue
        if any(term in name for term in normalized_terms):
            return i
        # OCR can corrupt a few characters (for example "lqi nhuan gp").
        # Fuzzy matching is used only to locate an equation row.
        score = max(SequenceMatcher(None, term, name).ratio() for term in normalized_terms)
        if score > best[0]:
            best = (score, i)
    return best[1] if best[0] >= 0.62 else None

def finance_check(table, item, candidate):
    headers,rows=rows_from_table(table); r=item.get("row"); c=item.get("column")
    if r is None or r>=len(rows): return "not_applicable", "row_not_available"
    revenue=row_index(rows,("doanh thu về bán hàng", "doanh thu thuần", "tong doanh thu ve ban hang")); cogs=row_index(rows,("giá vốn hàng bán",)); gross=row_index(rows,("lợi nhuận gộp", "loi nhuan gop", "loi nhuan gp", "lqi nhuzn gp"))
    if None in (revenue,cogs,gross): return "not_applicable", "equation_rows_not_available"
    if c>=len(rows[revenue]) or c>=len(rows[cogs]) or c>=len(rows[gross]): return "not_applicable", "equation_column_not_available"
    values={revenue:rows[revenue][c],cogs:rows[cogs][c],gross:rows[gross][c]}
    if r not in values: return "not_applicable", "candidate_not_in_supported_equation"
    values[r]=candidate
    parsed=[parse(values[i]) for i in (revenue,cogs,gross)]
    if any(v is None for v in parsed): return "not_applicable", "equation_has_other_unverified_value"
    passed=parsed[0]-parsed[1]==parsed[2]
    return ("pass" if passed else "fail", "revenue_minus_cogs_equals_gross_profit")

def table_key(table):
    source = table.get("source_grid", {})
    return table.get("table_id", source.get("table_id"))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("mapping",type=Path); ap.add_argument("ocr_review",type=Path); ap.add_argument("output",type=Path); args=ap.parse_args()
    data=json.loads(args.mapping.read_text(encoding="utf-8")); review=json.loads(args.ocr_review.read_text(encoding="utf-8")); mapping=data.get("mapping",data); tables={table_key(t):t for t in mapping.get("tables",[])}
    promoted=0; pending=0; results=[]
    for item in review.get("items",[]):
        candidate=item.get("ocr_value")
        validation_candidate=candidate_for_validation(candidate)
        table=tables.get(item.get("table"))
        fmt=bool(NUMBER.fullmatch(validation_candidate))
        finance_status,formula=finance_check(table,item,validation_candidate) if table else ("not_applicable","table_not_available")
        # ``not_applicable`` is not proof that the candidate is financially correct.
        # Keep it pending until an applicable equation actually passes.
        eligible=item.get("decision")=="candidate" and str(item.get("confidence","")).lower()=="high" and fmt and finance_status=="pass"
        decision="verified_value" if eligible else "pending_review"; promoted+=eligible; pending+=not eligible
        results.append({"page":item.get("page"),"table":item.get("table"),"row":item.get("row"),"column":item.get("column"),"raw_value":item.get("old_value"),"candidate":candidate,"validation_candidate":validation_candidate,"decision":decision,"finance_check":finance_status,"formula":formula,"confidence":item.get("confidence"),"method":"RapidOCR"})
    output={"schema":"financial_verified_mapping_v1","summary":{"total_candidates":len(results),"verified_values":promoted,"pending_review":pending,"raw_values_overwritten":0},"candidate_reviews":results,"mapping":mapping,"policy":{"raw_value_overwrite":False,"canonical_output":False}}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8"); print("Saved:",args.output); print(output["summary"])
if __name__=="__main__": main()
