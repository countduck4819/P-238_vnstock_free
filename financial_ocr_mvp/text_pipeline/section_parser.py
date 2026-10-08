from __future__ import annotations

import re
import unicodedata

from .section_taxonomy import CORE, SECTION_ALIASES


def normalize(value: str) -> str:
    value=unicodedata.normalize("NFKD",value.casefold())
    value="".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",value)).strip()


def classify_page(text: str) -> tuple[str, float, str] | None:
    value=normalize(text[:3000])
    if any(x in value for x in SECTION_ALIASES["table_of_contents"]): return "table_of_contents",0.99,"toc_marker"
    candidates=[]
    for section,aliases in SECTION_ALIASES.items():
        score=max((1.0 if normalize(a) in value else 0.0 for a in aliases),default=0.0)
        if score: candidates.append((section,score))
    if not candidates:return None
    section,score=max(candidates,key=lambda x:x[1])
    return section,score,"alias_match"


def parse_sections(pages: list[dict[str,object]]) -> list[dict[str,object]]:
    anchors=[]
    for page in pages:
        match=classify_page(str(page["text"]))
        if match and match[0] != "table_of_contents": anchors.append((match[0],int(page["page"]),match[1],str(page["text"])[:240]))
    sections=[]
    for i,(kind,start,confidence,heading) in enumerate(anchors):
        end=anchors[i+1][1]-1 if i+1<len(anchors) else int(pages[-1]["page"])
        selected=[p for p in pages if start<=int(p["page"])<=end]
        sections.append({"section_id":f"{kind}:{start}","type":kind,"start_page":start,"end_page":end,"pages":[int(p["page"]) for p in selected],"heading":heading,"confidence":confidence,"table_count":sum(int(p["table_count"]) for p in selected)})
    return sections
