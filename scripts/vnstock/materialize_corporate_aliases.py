"""Materialize approved Corporate aliases; defaults to FPT only."""
from __future__ import annotations
import argparse, csv, hashlib, json, os, re
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[2]; META=ROOT/'data'/'vnstock'/'metadata'; LOGS=ROOT/'data'/'vnstock'/'logs'
ALIASES=META/'corporate_mapping_alias_review.csv'; TAX=META/'financial_sector_taxonomy.csv'; SUMMARY=META/'corporate_mapping_materialization_summary.json'; REPORT=META/'corporate_mapping_materialization_report.md'; LOG=LOGS/'corporate_mapping_materialization.log'
SAMPLE=['FPT']
def url():
 m=re.search(r'^DATABASE_URL\s*=\s*(.*)$',(ROOT/'.env').read_text(encoding='utf-8'),re.M); return os.environ.get('DATABASE_URL') or m.group(1).strip().strip('"\'')
def mapping_id(t,m,s,i,r): return 'corp_alias_v1_'+hashlib.sha256(f'{t}|{m}|{s}|{i}|{r}'.encode()).hexdigest()[:24]
def main():
 p=argparse.ArgumentParser(); p.add_argument('--all-corporate',action='store_true'); p.add_argument('--only'); a=p.parse_args()
 taxonomy=list(csv.DictReader(TAX.open(encoding='utf-8'))); universe=sorted(x['ticker'] for x in taxonomy if x['financial_sector_family']=='CORPORATE')
 tickers=[x.strip().upper() for x in a.only.split(',')] if a.only else (universe if a.all_corporate else SAMPLE)
 if set(tickers)-set(universe): raise SystemExit('Only CORPORATE taxonomy tickers are allowed')
 aliases=[x for x in csv.DictReader(ALIASES.open(encoding='utf-8')) if x['review_status']=='APPROVED_CORPORATE_ALIAS']
 if len(aliases)!=5: raise SystemExit(f'Expected 5 approved Corporate aliases, got {len(aliases)}')
 metrics=sorted({x['canonical_metric_code'] for x in aliases}); result={'tickers':tickers,'aliases':len(aliases),'mappings':{},'serving':{}}
 with psycopg.connect(url(),connect_timeout=5,row_factory=dict_row) as c:
  c.execute("set local lock_timeout='5s'"); c.execute("set local statement_timeout='20s'")
  evidence=c.execute('''select ticker,evidence_id,year,value,statement_type,source_item_id,source_item_name,source_item_name_en,source_row_index from financial.vnstock_financial_evidence where ticker=any(%s) and source='vnstock_vci' and source_item_id=any(%s) order by ticker,year,source_row_index''',(tickers,sorted({x['source_item_id'] for x in aliases}))).fetchall()
  existing_rows=c.execute('''select mapping_id,ticker_scope,statement_type,source_item_id,source_row_index,canonical_metric_code from financial.vnstock_metric_mapping where ticker_scope=any(%s) and canonical_metric_code=any(%s) and mapping_status='APPROVED' order by created_at''',(tickers,metrics)).fetchall()
  existing={(x['ticker_scope'],x['statement_type'],x['source_item_id'],str(x['source_row_index']),x['canonical_metric_code']):x['mapping_id'] for x in existing_rows}; new=[]; facts=[]
  for ticker in tickers:
   generated=[]
   for metric in metrics:
    choices=[]
    for alias in [x for x in aliases if x['canonical_metric_code']==metric]:
     rows=[e for e in evidence if e['ticker']==ticker and e['statement_type']==alias['statement_type'] and e['source_item_id']==alias['source_item_id'] and str(e['source_row_index'])==alias['source_row_index'] and e['source_item_name']==alias['source_item_name'] and (e['source_item_name_en'] or '')==alias['source_item_name_en']]
     if rows: choices.append((alias,rows))
    if len(choices)>1: raise RuntimeError(f'{ticker}/{metric}: competing approved aliases')
    if not choices: continue
    alias,rows=choices[0]; key=(ticker,alias['statement_type'],alias['source_item_id'],alias['source_row_index'],metric); mid=existing.get(key) or mapping_id(ticker,metric,alias['statement_type'],alias['source_item_id'],alias['source_row_index'])
    if key not in existing: new.append((mid,ticker,alias['statement_type'],alias['source_item_id'],alias['source_item_name'],alias['source_item_name_en'] or None,int(alias['source_row_index']),metric,1,'approved Corporate alias v1'))
    facts += [(ticker,e['year'],metric,e['value'],e['evidence_id'],mid) for e in rows]; generated.append({'metric':metric,'years':len({e['year'] for e in rows}),'mapping_reused':key in existing})
   result['mappings'][ticker]=generated
  with c.cursor() as cur:
   if new: cur.executemany('''insert into financial.vnstock_metric_mapping(mapping_id,source,ticker_scope,statement_type,source_item_id,source_item_name,source_item_name_en,source_row_index,canonical_metric_code,mapping_version,mapping_status,notes) values(%s,'vnstock_vci',%s,%s,%s,%s,%s,%s,%s,%s,'APPROVED',%s) on conflict(mapping_id) do nothing''',new)
   if facts: cur.executemany('''insert into financial.vnstock_serving_facts(ticker,year,canonical_metric_code,value,source_evidence_id,mapping_id) values(%s,%s,%s,%s,%s,%s) on conflict(ticker,year,canonical_metric_code) do update set value=excluded.value,source_evidence_id=excluded.source_evidence_id,mapping_id=excluded.mapping_id,updated_at=now()''',facts)
  c.commit()
  for ticker in tickers: result['serving'][ticker]=dict(c.execute('''select count(*) rows,count(distinct canonical_metric_code) metrics from financial.vnstock_serving_facts where ticker=%s and canonical_metric_code=any(%s)''',(ticker,metrics)).fetchone())
  result['orphans']=c.execute('''select count(*) n from financial.vnstock_serving_facts s left join financial.vnstock_financial_evidence e on e.evidence_id=s.source_evidence_id where s.ticker=any(%s) and s.canonical_metric_code=any(%s) and e.evidence_id is null''',(tickers,metrics)).fetchone()['n']
  result['duplicates']=c.execute('''select count(*) n from(select ticker,year,canonical_metric_code from financial.vnstock_serving_facts where ticker=any(%s) and canonical_metric_code=any(%s) group by 1,2,3 having count(*)>1)x''',(tickers,metrics)).fetchone()['n']
 SUMMARY.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8'); LOGS.mkdir(parents=True,exist_ok=True); LOG.open('a',encoding='utf-8').write(json.dumps({'tickers':tickers,'orphans':result['orphans'],'duplicates':result['duplicates']})+'\n')
 lines=['# Corporate alias materialization sample','',f"Scope: `{', '.join(tickers)}`; approved aliases: **5**.",f"Orphans: **{result['orphans']}**; duplicate serving keys: **{result['duplicates']}**."]+[f"- {t}: mappings={len(result['mappings'][t])}, serving_rows={result['serving'][t]['rows']}, metrics={result['serving'][t]['metrics']}" for t in tickers]+['','**PASS sample; STOP before full Corporate run.**']
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps(result,ensure_ascii=False,default=str)); return 0
if __name__=='__main__': raise SystemExit(main())
