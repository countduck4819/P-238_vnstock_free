"""Validate the derived metric MVP on FPT and ACB without materialization."""
from __future__ import annotations
import json, os, re, sys
from decimal import Decimal
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[2]; META=ROOT/'data'/'vnstock'/'metadata'; sys.path.insert(0,str(ROOT))
from src.services.derived_metrics import calculate
REPORT=META/'derived_metric_mvp_report.md'; SUMMARY=META/'derived_metric_mvp_summary.json'
def url():
 m=re.search(r'^DATABASE_URL\s*=\s*(.*)$',(ROOT/'.env').read_text(encoding='utf-8'),re.M); return os.environ.get('DATABASE_URL') or m.group(1).strip().strip('"\'')
def main():
 with psycopg.connect(url(),connect_timeout=5,row_factory=dict_row) as c:
  columns=[dict(x) for x in c.execute("select column_name,data_type,is_nullable from information_schema.columns where table_schema='financial' and table_name='vnstock_metric_catalog' order by ordinal_position").fetchall()]
  base_count=c.execute('select count(*) n from financial.vnstock_metric_catalog').fetchone()['n']
  rows=c.execute("select ticker,year,canonical_metric_code,value from financial.vnstock_serving_facts where ticker=any(%s) and year between 2023 and 2025 and canonical_metric_code=any(%s)",(['FPT','ACB'],['net_revenue','net_profit','total_assets','total_equity'])).fetchall()
 facts={t:{} for t in ['FPT','ACB']}
 for x in rows: facts[x['ticker']][(x['canonical_metric_code'],x['year'])]=x['value']
 tests=[]
 for ticker,sector,codes in [('FPT','CORPORATE',['net_revenue_yoy_growth','net_profit_yoy_growth','net_profit_margin','roa']),('ACB','BANK',['net_profit_yoy_growth','roa','roe'])]:
  for year in [2024,2025]: tests.append(calculate(ticker,year,codes[0],sector,facts[ticker]))
  for code in codes[1:]: tests.append(calculate(ticker,2025,code,sector,facts[ticker]))
 synthetic_missing=calculate('TEST',2025,'net_profit_yoy_growth','CORPORATE',{('net_profit',2025):Decimal(1)})
 synthetic_zero=calculate('TEST',2025,'net_profit_margin','CORPORATE',{('net_profit',2025):Decimal(1),('net_revenue',2025):Decimal(0)})
 unsupported=calculate('FPT',2025,'roe','CORPORATE',facts['FPT'])
 ok=all(x['calculation_status']=='OK' for x in tests) and synthetic_missing['calculation_status']=='MISSING_INPUT' and synthetic_zero['calculation_status']=='ZERO_DENOMINATOR' and unsupported['calculation_status']=='UNSUPPORTED'
 summary={'current_catalog_fields':columns,'current_base_metric_count':base_count,'catalog_supports_derived_metadata':False,'calculation_location':'on_demand_backend','sample_results':tests,'policy_tests':{'missing':synthetic_missing,'zero_denominator':synthetic_zero,'unsupported':unsupported},'vnstock_called':False,'base_facts_modified':False,'pass':ok}
 SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 lines=['# Derived Metric MVP','',f"Validation: **{'PASS' if ok else 'FAIL'}**",f"Current PostgreSQL catalog has **{base_count} base metrics** and does not yet contain metric_type/formula/required_metrics/policy columns. Derived definitions remain in a separate additive catalog.",'','## Approved MVP','','- `net_revenue_yoy_growth` — CORPORATE','- `net_profit_yoy_growth` — CORPORATE/BANK','- `net_profit_margin` — CORPORATE','- `roa` — CORPORATE/BANK, average current/prior assets','- `roe` — BANK only, average current/prior equity','','`credit_cost_proxy` is UNSUPPORTED because an appropriate denominator is absent. Missing inputs return MISSING_INPUT; zero denominators return ZERO_DENOMINATOR. No nearest-year substitution is used.','','## Samples','']
 for x in tests: lines.append(f"- {x['ticker']} {x['year']} `{x['canonical_metric_code']}`: {x['calculation_status']}, value={x['value']}")
 lines += ['','Calculation location: deterministic backend on demand. Base serving facts, raw and evidence were not modified; no VNStock or LLM call occurred.','', '**PASS; STOP before Query Harness.**' if ok else '**FAIL; STOP.**']
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps({'base_catalog_count':base_count,'sample_count':len(tests),'statuses':[x['calculation_status'] for x in tests],'missing_test':synthetic_missing['calculation_status'],'zero_test':synthetic_zero['calculation_status'],'unsupported_test':unsupported['calculation_status'],'pass':ok},ensure_ascii=False)); return 0 if ok else 1
if __name__=='__main__': raise SystemExit(main())
