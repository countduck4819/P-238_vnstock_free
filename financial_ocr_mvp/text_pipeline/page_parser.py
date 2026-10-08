from __future__ import annotations

import re

from .normalizer import tag_counts

MARKER = re.compile(r"^\s*=+\s*PAGE\s+(\d+)\s*=+\s*$", re.I | re.M)


def split_pages(text: str) -> list[dict[str, object]]:
    matches=list(MARKER.finditer(text))
    pages=[]
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        body=text[m.end():end].lstrip("\n")
        pages.append({"page":int(m.group(1)),"text":body,"html_tables":[],"table_count":tag_counts(body)["table"]})
    return pages
