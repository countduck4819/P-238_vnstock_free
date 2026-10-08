"""Validation utilities for Docling raw grids. No OCR repair or value normalization."""

from __future__ import annotations

import re
from typing import Any

NUMBER_PATTERN = re.compile(r"^[+-]?[0-9][0-9.,() ]*$|^$|^null$", re.IGNORECASE)

def validate_table(table: dict[str, Any]) -> list[str]:
    errors=[]
    headers=table.get("headers",[])
    rows=table.get("rows",[])
    if not headers: errors.append("missing header rows")
    if not rows: errors.append("missing data rows")
    width=max((len(row) for row in headers), default=0)
    if width == 0: errors.append("empty header")
    for i,row in enumerate(headers+rows):
        if len(row)!=width: errors.append(f"row {i} has {len(row)} columns; expected {width}")
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            if j>=4 and value not in (None,"") and not NUMBER_PATTERN.match(str(value).strip()):
                errors.append(f"row {i}, column {j}: suspicious raw value {value!r}")
    return errors
