from __future__ import annotations
import csv,json,logging,os,time
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from vnstock import Fundamental, Company
ROOT=Path(__file__).resolve().parents[2]; RAW=ROOT/'data/vnstock/raw'; META=ROOT/'data/vnstock/metadata'; LOGS=ROOT/'data/vnstock/logs'; TICKERS=['FPT','HPG','MWG','GAS','ACB','MBB','SSI','BVH']; RES=['balance_sheet','income_statement','cash_flow','profile','overview','officers']
LOGS.mkdir(parents=True,exist_ok=True);META.mkdir(parents=True,exist_ok=True);logging.basicConfig(filename=LOGS/'downloader.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
def save_json(path,obj):
 path.write_text(json.dumps(obj.to_dict(orient='records') if hasattr(obj,'to_dict') else obj,ensure_ascii=False,indent=2,default=str),encoding='utf8')
def fetch(t,r):
 fdir=RAW/'financial'/t; cdir=RAW/'company'/t; fdir.mkdir(parents=True,exist_ok=True);cdir.mkdir(parents=True,exist_ok=True)
 ext='parquet' if r in ('balance_sheet','income_statement','cash_flow') else 'json'; path=(fdir if ext=='parquet' else cdir)/(r+'.'+ext)
 if path.exists() and path.stat().st_size>0:return 'exists',None
 try:
  if r in ('balance_sheet','income_statement','cash_flow'):
   obj=getattr(Fundamental().equity(t),r)(period='year')
   if obj is None or len(obj)==0:return 'empty',None
   obj.to_parquet(path,index=False)
  else:
   c=Company(source='KBS',symbol=t,show_log=False); obj=c.info() if r=='profile' else getattr(c,r)()
   if obj is None or (hasattr(obj,'empty') and obj.empty):return 'empty',None
   save_json(path,obj)
  logging.info('%s %s success',t,r);return 'success',None
 except Exception as e:
  logging.exception('%s %s error',t,r);return 'error',str(e)
def main():
 started=time.perf_counter(); counts={k:0 for k in ['financial_requests_attempted','financial_success','financial_exists','financial_empty','financial_error','company_requests_attempted','company_success','company_exists','company_empty','company_error']}; rows=[]
 for t in TICKERS:
  row={'ticker':t}; errors=[]
  for r in RES:
   group='financial' if r in ('balance_sheet','income_statement','cash_flow') else 'company';counts[group+'_requests_attempted']+=1;st,err=fetch(t,r);row[r+'_status']=st;counts[group+'_'+st]+=1
   if err: row[r+'_error_message']=err;errors.append(r+': '+err)
   time.sleep(0.5)
  row['updated_at']=datetime.now(timezone.utc).isoformat();rows.append(row)
 with (META/'download_manifest.csv').open('w',newline='',encoding='utf8') as f:
  fields=sorted(set().union(*(x.keys() for x in rows)));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 success=sum(all(x.get(r+'_status') in ('success','exists') for r in RES) for x in rows);partial=sum(any(x.get(r+'_status') in ('success','exists') for r in RES) and not all(x.get(r+'_status') in ('success','exists') for r in RES) for x in rows)
 summary={**counts,'pilot_tickers':8,'ticker_success_count':success,'ticker_partial_count':partial,'ticker_failed_count':8-success-partial,'runtime_seconds':round(time.perf_counter()-started,3),'errors':[{'ticker':x['ticker'],**{k:v for k,v in x.items() if k.endswith('error_message')}} for x in rows if any(k.endswith('error_message') for k in x)]}
 (META/'pilot_download_summary.md').write_text('# VNStock pilot download summary\n\n'+json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
