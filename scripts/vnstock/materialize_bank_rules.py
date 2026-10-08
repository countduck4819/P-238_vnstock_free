"""Materialize reviewed BANK reusable rules; defaults to a three-bank sample."""
from __future__ import annotations
import argparse, csv, hashlib, json, os, re
from datetime import datetime, timezone
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[2]; META=ROOT/'data'/'vnstock'/'metadata'; LOGS=ROOT/'data'/'vnstock'/'logs'
RULES=META/'canonical_mapping_rule_review.csv'; TAX=META/'financial_sector_taxonomy.csv'; CATALOG=META/'canonical_metric_catalog.csv'
SUMMARY=META/'bank_mapping_materialization_summary.json'; REPORT=META/'bank_mapping_materialization_report.md'; VALIDATION=META/'bank_serving_validation_report.md'; LOG=LOGS/'bank_mapping_materialization.log'
SAMPLE=('ACB','MBB','BID'); VERSION=1
EXTRA_CATALOG={
 'net_fee_and_commission_income':('Thu nhập phí và hoa hồng thuần','Net fee and commission income','income_statement','Bank net fee and commission income from VCI evidence.'),
 'provision_for_credit_losses':('Dự phòng rủi ro tín dụng','Provision for credit losses','income_statement','Bank provision for credit losses from VCI evidence.'),
}

def db_url():
 t=(ROOT/'.env').read_text(encoding='utf-8'); m=re.search(r'^DATABASE_URL\s*=\s*(.*)$',t,re.M)
 if not m: raise SystemExit('DATABASE_URL missing')
 return os.environ.get('DATABASE_URL') or m.group(1).strip().strip('"\'')
def mid(ticker,metric,statement,item,row): return 'bank_rule_v1_'+hashlib.sha256(f'{ticker}|{metric}|{statement}|{item}|{row}'.encode()).hexdigest()[:24]

def main():
 p=argparse.ArgumentParser(); p.add_argument('--all-banks',action='store_true'); p.add_argument('--only'); p.add_argument('--preflight',action='store_true'); a=p.parse_args()
 tax=list(csv.DictReader(TAX.open(encoding='utf-8'))); banks=sorted(r['ticker'] for r in tax if r['financial_sector_family']=='BANK')
 tickers=[x.strip().upper() for x in a.only.split(',')] if a.only else (banks if a.all_banks else list(SAMPLE))
 if set(tickers)-set(banks): raise SystemExit('Only BANK taxonomy tickers are allowed')
 rules=[r for r in csv.DictReader(RULES.open(encoding='utf-8')) if r['financial_sector_family']=='BANK' and r['review_status']=='APPROVED_REUSABLE_RULE']
 if len(rules)!=7: raise SystemExit(f'Expected exactly 7 approved BANK rules, got {len(rules)}')
 catalog={r['canonical_metric_code']:r for r in csv.DictReader(CATALOG.open(encoding='utf-8'))}
 started=datetime.now(timezone.utc); result={'started_at':started.isoformat(),'tickers':tickers,'rule_count':len(rules),'mappings':{},'serving':{}}
 print(f'preflight: tickers={tickers} rules={len(rules)}',flush=True)
 with psycopg.connect(db_url(),connect_timeout=5,row_factory=dict_row) as c:
  if c.execute('select current_database() database').fetchone()['database']!='fireant_stock_dev': raise SystemExit('Unexpected database')
  if a.preflight:
   print(dict(c.execute("select count(*) catalog_count,(select count(*) from financial.vnstock_metric_mapping) mapping_count,(select count(*) from financial.vnstock_serving_facts) serving_count from financial.vnstock_metric_catalog").fetchone()),flush=True)
   activity=c.execute("select pid,state,wait_event_type,wait_event,left(query,80) query from pg_stat_activity where datname=current_database() and pid<>pg_backend_pid() order by pid").fetchall()
   print({'other_sessions':[dict(x) for x in activity]},flush=True)
   return 0
  c.execute("set local lock_timeout='5s'")
  c.execute("set local statement_timeout='20s'")
  catalog_values=[]
  for rule in rules:
   code=rule['canonical_metric_code']
   if code in catalog:
    x=catalog[code]; values=(code,x['metric_name_vi'],x['metric_name_en'],x['statement_type'],x['unit_type'],x['description'])
   else:
    vi,en,statement,description=EXTRA_CATALOG[code]; values=(code,vi,en,statement,'source_native_numeric',description)
   catalog_values.append(values)
  with c.cursor() as cur: cur.executemany('''insert into financial.vnstock_metric_catalog(canonical_metric_code,metric_name_vi,metric_name_en,statement_type,unit_type,description) values(%s,%s,%s,%s,%s,%s) on conflict(canonical_metric_code) do nothing''',catalog_values)
  item_ids=[r['source_item_id'] for r in rules]; metric_codes=[r['canonical_metric_code'] for r in rules]
  evidence=c.execute('''select ticker,evidence_id,year,value,statement_type,source_item_id,source_row_index,source_item_name,source_item_name_en from financial.vnstock_financial_evidence where ticker=any(%s) and source='vnstock_vci' and source_item_id=any(%s) order by ticker,year,source_row_index''',(tickers,item_ids)).fetchall()
  existing_rows=c.execute('''select mapping_id,ticker_scope,statement_type,source_item_id,source_row_index,canonical_metric_code from financial.vnstock_metric_mapping where source='vnstock_vci' and ticker_scope=any(%s) and canonical_metric_code=any(%s) and mapping_status='APPROVED' order by created_at''',(tickers,metric_codes)).fetchall()
  existing={(x['ticker_scope'],x['statement_type'],x['source_item_id'],x['source_row_index'],x['canonical_metric_code']):x['mapping_id'] for x in existing_rows}
  new_mappings=[]; serving_rows=[]
  for ticker in tickers:
   generated=[]
   for rule in rules:
    ev=[x for x in evidence if x['ticker']==ticker and x['statement_type']==rule['statement_type'] and x['source_item_id']==rule['source_item_id']]
    row_ids={x['source_row_index'] for x in ev}
    if not ev: continue
    if len(row_ids)!=1: raise RuntimeError(f'{ticker}/{rule["canonical_metric_code"]}: competing row identities {sorted(row_ids)}')
    row=next(iter(row_ids)); key=(ticker,rule['statement_type'],rule['source_item_id'],row,rule['canonical_metric_code']); mapping_id=existing.get(key) or mid(ticker,rule['canonical_metric_code'],rule['statement_type'],rule['source_item_id'],row)
    if key not in existing: new_mappings.append((mapping_id,ticker,rule['statement_type'],rule['source_item_id'],ev[0]['source_item_name'],ev[0]['source_item_name_en'],row,rule['canonical_metric_code'],VERSION,'approved reusable BANK rule v1'))
    for x in ev:
     serving_rows.append((ticker,x['year'],rule['canonical_metric_code'],x['value'],x['evidence_id'],mapping_id))
    generated.append({'metric':rule['canonical_metric_code'],'mapping_id':mapping_id,'years':len({x['year'] for x in ev}),'reused':key in existing})
   result['mappings'][ticker]=generated
  with c.cursor() as cur:
   if new_mappings: cur.executemany('''insert into financial.vnstock_metric_mapping(mapping_id,source,ticker_scope,statement_type,source_item_id,source_item_name,source_item_name_en,source_row_index,canonical_metric_code,mapping_version,mapping_status,notes) values(%s,'vnstock_vci',%s,%s,%s,%s,%s,%s,%s,%s,'APPROVED',%s) on conflict(mapping_id) do nothing''',new_mappings)
   if serving_rows: cur.executemany('''insert into financial.vnstock_serving_facts(ticker,year,canonical_metric_code,value,source_evidence_id,mapping_id) values(%s,%s,%s,%s,%s,%s) on conflict(ticker,year,canonical_metric_code) do update set value=excluded.value,source_evidence_id=excluded.source_evidence_id,mapping_id=excluded.mapping_id,updated_at=now()''',serving_rows)
  c.commit()
  for ticker in tickers: result['serving'][ticker]=dict(c.execute('''select count(*) rows,count(distinct canonical_metric_code) metrics,count(*) filter(where value is null) null_rows from financial.vnstock_serving_facts where ticker=%s and canonical_metric_code=any(%s)''',(ticker,metric_codes)).fetchone())
  result['orphan_count']=c.execute('''select count(*) n from financial.vnstock_serving_facts s left join financial.vnstock_financial_evidence e on e.evidence_id=s.source_evidence_id left join financial.vnstock_metric_mapping m on m.mapping_id=s.mapping_id where s.ticker=any(%s) and (e.evidence_id is null or m.mapping_id is null)''',(tickers,)).fetchone()['n']
  result['duplicate_keys']=c.execute('''select count(*) n from(select ticker,year,canonical_metric_code from financial.vnstock_serving_facts where ticker=any(%s) group by 1,2,3 having count(*)>1)x''',(tickers,)).fetchone()['n']
 result['finished_at']=datetime.now(timezone.utc).isoformat(); SUMMARY.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8'); LOGS.mkdir(parents=True,exist_ok=True)
 with LOG.open('a',encoding='utf-8') as f: f.write(json.dumps({'at':result['finished_at'],'tickers':tickers,'orphan':result['orphan_count'],'duplicates':result['duplicate_keys']})+'\n')
 lines=['# Bank mapping materialization','',f"Tickers: `{', '.join(tickers)}`; approved rules: **7**.",f"Orphan provenance: **{result['orphan_count']}**; duplicate serving keys: **{result['duplicate_keys']}**.",'','| Ticker | Mappings | Serving rows | Metrics | Null rows |','|---|---:|---:|---:|---:|']
 for t in tickers: lines.append(f"| {t} | {len(result['mappings'][t])} | {result['serving'][t]['rows']} | {result['serving'][t]['metrics']} | {result['serving'][t]['null_rows']} |")
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8'); VALIDATION.write_text('\n'.join(lines+['','Rerun is idempotent through existing mapping reuse, deterministic new mapping IDs and serving-key UPSERT.'])+'\n',encoding='utf-8')
 print(json.dumps({'tickers':tickers,'mapping_counts':{t:len(v) for t,v in result['mappings'].items()},'serving':result['serving'],'orphan':result['orphan_count'],'duplicates':result['duplicate_keys']},ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
