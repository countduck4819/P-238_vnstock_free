from __future__ import annotations
from dataclasses import dataclass,asdict
import re,unicodedata
FACTS=["net_revenue","profit_after_tax","total_assets","total_liabilities","total_equity","operating_cash_flow","investing_cash_flow","financing_cash_flow"]
ALIASES={"net_revenue":["doanh thu thuan"],"profit_after_tax":["loi nhuan sau thue"],"total_assets":["tong cong tai san","tong tai san"],"total_liabilities":["no phai tra","tong cong no phai tra","tong no phai tra"],"total_equity":["von chu so huu","tong cong von chu so huu","tong von chu so huu"],"operating_cash_flow":["luu chuyen tien thuan tu hoat dong kinh doanh"],"investing_cash_flow":["luu chuyen tien thuan tu hoat dong dau tu"],"financing_cash_flow":["luu chuyen tien thuan tu hoat dong tai chinh"]}
def norm(s):
 s=unicodedata.normalize('NFKC',s.replace('\xa0',' ')).lower(); s=''.join(c for c in unicodedata.normalize('NFD',s) if unicodedata.category(c)!='Mn'); return re.sub(r'[^a-z0-9]+',' ',s).strip()
def nums(s):
 out=[]
 for x in re.findall(r'\(?[-−]?\s*\d[\d.,\s]*\)?',s):
  raw=x.strip(); neg=raw.startswith('(') or raw.startswith('-') or raw.endswith('-'); digits=re.sub(r'\D','',raw)
  if 2 <= len(digits) <= 100: out.append(-int(digits) if neg else int(digits))
 return out
@dataclass
class Cell: cell_index:int; raw_text:str; normalized_text:str
@dataclass
class Row: page:int|None; table_index:int; row_index:int; cells:list[Cell]; normalized_label:str; numeric_cells:list[int]; section_context:str; statement_code:str|None
@dataclass
class DocumentContext: document_id:str; ticker:str; fiscal_year:int; normalized_path:str; raw_text:str; rows:list[Row]; tables_count:int; html_parse_count:int=1
def build_document_context(path,document_id,ticker,fiscal_year):
 text=path.read_text(encoding='utf8',errors='replace'); markers=list(re.finditer(r'=+\s*PAGE\s+(\d+)\s*=+',text,re.I)); tables=[]
 for ti,m in enumerate(re.finditer(r'<table\b[^>]*>(.*?)</table\s*>',text,re.I|re.S)):
  page=None
  for pm in markers:
   if pm.start()<m.start(): page=int(pm.group(1))
   else: break
  body=m.group(1); rawrows=[]
  for ri,tr in enumerate(re.findall(r'<tr\b[^>]*>(.*?)</tr\s*>',body,re.I|re.S)):
   raws=[' '.join(re.sub(r'<[^>]+>',' ',c).replace('&nbsp;',' ').split()) for c in re.findall(r'<(?:td|th)\b[^>]*>(.*?)</(?:td|th)\s*>',tr,re.I|re.S)]
   if raws: rawrows.append(raws)
  alltext=norm(' '.join(' '.join(x) for x in rawrows));
  if any(x in alltext for x in ('tong cong tai san','tong tai san','no phai tra','von chu so huu')): section='balance_sheet'
  elif 'doanh thu thuan' in alltext or 'loi nhuan sau thue' in alltext: section='income_statement'
  elif ('luu chuyen tien' in alltext and ('kinh doanh' in alltext or 'dau tu' in alltext or 'tai chinh' in alltext)) or ('luu chuyen' in alltext and 'hoat' in alltext): section='cash_flow'
  else: section='unknown'
  for ri,raws in enumerate(rawrows):
   cells=[Cell(i,x,norm(x)) for i,x in enumerate(raws)]; label=norm(' '.join(raws[:2])); code=None
   for c in cells[:3]:
    if re.fullmatch(r'(10|20|30|40|60|270|300|400)',c.normalized_text): code=c.raw_text
   value_cells=[]
   for c in cells[1:]:
    value_cells += nums(c.raw_text)
   # exclude leading statement code/note-like tiny tokens when later financial cells exist
   if code and value_cells and value_cells[0]==int(re.sub(r'\D','',code)): value_cells=value_cells[1:]
   # Codes can be emitted in the last cell by OCR/table exporters.
   code_numbers={10,20,30,40,60,270,300,400}
   value_cells=[v for v in value_cells if v not in code_numbers or len(value_cells)==1]
   tables.append(Row(page,ti,ri,cells,label,value_cells,section,code))
 return DocumentContext(document_id,ticker,fiscal_year,str(path),text,tables,tables and max(x.table_index for x in tables)+1 or 0), {'read_ms':0.0,'parse_ms':0.0,'index_ms':0.0}
def extract_all_facts(ctx):
 sections={'net_revenue':'income_statement','profit_after_tax':'income_statement','total_assets':'balance_sheet','total_liabilities':'balance_sheet','total_equity':'balance_sheet','operating_cash_flow':'cash_flow','investing_cash_flow':'cash_flow','financing_cash_flow':'cash_flow'}; out={}
 for fact in FACTS:
  found=None
  for row in ctx.rows:
   if row.section_context!=sections[fact] or not row.numeric_cells: continue
   
   label=row.normalized_label
   token_ok=any(a in label for a in ALIASES[fact])
   if fact=='net_revenue': token_ok=token_ok or ('doanh thu' in label and 'thuan' in label)
   if fact=='profit_after_tax': token_ok=token_ok or ('loi nhuan' in label and 'sau thue' in label)
   if fact.startswith('operating'): token_ok=token_ok or ('luu chuyen tien' in label and ('kinh doanh' in label or 'kinh ong' in label))
   if fact.startswith('investing'): token_ok=token_ok or ('luu chuyen tien' in label and ('dau tu' in label or 'dau' in label))
   if fact.startswith('financing'): token_ok=token_ok or ('luu chuyen tien' in label and ('tai chinh' in label or 'tai' in label))
   if fact=='net_revenue' and any(q in label for q in ('bao hiem','moi gioi chung khoan','thu nhap lai thuan','total operating income')): token_ok=False
   if token_ok: found={'value':row.numeric_cells[0],'page':row.page,'raw_label':' '.join(c.raw_text for c in row.cells[:2]),'statement_code':row.statement_code,'table_index':row.table_index,'row_index':row.row_index}; break
  out[fact]=found
 return out
def validate(facts):
 if any(facts[x] is None for x in FACTS): return False
 a=facts['total_assets']['value']; b=facts['total_liabilities']['value']+facts['total_equity']['value']; return abs(a-b)<=max(1000,abs(a)*.03)
