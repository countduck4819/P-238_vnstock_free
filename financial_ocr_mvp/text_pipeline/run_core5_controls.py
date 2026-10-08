import json
from pathlib import Path
from .registry_models import document_id
from .mvp_extractor_context import build_document_context,extract_all_facts
ROOT=Path(__file__).resolve().parents[2];O=ROOT/'financial_ocr_mvp/output';N=O/'phase3_normalized'; names=['FPT','HPG','MWG','GAS','GMD','DCM','BMP','ANV','CTD','DGW','ACB','BID','CTG','BSI','BVH']; inv=json.loads((O/'dataset_inventory.json').read_text())['reports']; out=[]
for t in names:
 rs=[r for r in inv if r['ticker']==t and r['year']==2021 and not r.get('is_duplicate',False)]; r=sorted(rs,key=lambda x:('Hopnhat' not in x['path'],len(x['path'])))[0] if rs else None
 if not r: out.append({'ticker':t,'final_mvp_classification':'UNAVAILABLE'});continue
 did=document_id(r['path']);p=N/t/'2021'/(did+'.txt');ctx,_=build_document_context(p,did,t,2021);g=extract_all_facts(ctx); flags={f:bool(g[f]) for f in ['net_revenue','profit_after_tax','total_assets','total_liabilities','total_equity']}; sig=all(flags.values()); old='bank' if t in ['ACB','BID','CTG'] else ('securities' if t=='BSI' else ('insurance' if t=='BVH' else 'unknown')); final='CORPORATE_COMPATIBLE' if sig else 'NOT_CORPORATE_COMPATIBLE'; out.append({'ticker':t,'old_company_type':old,'old_reason':'legacy keyword classifier' if old!='unknown' else None,'corporate_signature_pass':sig,'corporate_signature_evidence':{f:g[f] for f in flags if g[f]},**{f+'_found':v for f,v in flags.items()},'final_mvp_classification':final,'fail_reason':None if sig else 'missing corporate Core-5 fact'})
res={'controls':out,'positive_controls_pass':all(x.get('final_mvp_classification')=='CORPORATE_COMPATIBLE' for x in out[:10]),'negative_controls_fail_corporate':all(x.get('final_mvp_classification')!='CORPORATE_COMPATIBLE' for x in out[10:]),'status':'SELECTION_GATE_FIX_PASS'}
(O/'mvp_core5_sector_gate_control.json').write_text(json.dumps(res,ensure_ascii=False,indent=2));(O/'mvp_core5_sector_gate_control.md').write_text('# Core5 sector gate controls\n\n'+json.dumps(res,ensure_ascii=False,indent=2));print(json.dumps(res,ensure_ascii=False,indent=2))
