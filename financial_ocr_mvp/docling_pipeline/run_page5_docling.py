"""Run Docling on the isolated high-resolution page-5 table."""
from pathlib import Path
import json
from docling.document_converter import DocumentConverter

BASE = Path(__file__).resolve().parents[1]
INPUT = BASE / "output" / "docling" / "page_005_table_400dpi.png"
OUTPUT = BASE / "output" / "docling" / "page_005_table_400dpi.json"

if not INPUT.exists():
    raise SystemExit(f"Missing crop: {INPUT}. Run prepare_page5.py first.")

result = DocumentConverter().convert(str(INPUT))
with OUTPUT.open("w", encoding="utf-8") as file:
    json.dump(result.document.export_to_dict(), file, ensure_ascii=False, indent=2)

print("Saved:", OUTPUT)
print("Tables:", len(result.document.tables))
for index, table in enumerate(result.document.tables):
    cells = table.data.table_cells
    print(index, "cells:", len(cells), "page:", table.prov[0].page_no if table.prov else None)
