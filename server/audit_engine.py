"""Evidence-driven Audit Intelligence Engine. Frontend must not decide business truth."""
import json,re,time
from datetime import datetime,timezone
from urllib.parse import parse_qs
from server.core import ASSESSMENT_SOURCES,Problem,timestamp,uid
from server.audit_policy import (
 ADDITIVE_INSIGHT_METRICS,NON_ADDITIVE_INSIGHT_METRICS,PERIOD_COMPAT_SECONDS,POLICIES
)

SOURCE_LABELS={
 'website':'الموقع الإلكتروني','instagram':'Instagram','facebook':'Facebook','tiktok':'TikTok',
 'linkedin':'LinkedIn','youtube':'YouTube','googleBusiness':'Google Business'
}
SECRET_KEYS={'token','access_token','accesstoken','page_token','pageaccesstoken','cipher','password',
             'csrf','authorization','cookie','secret','vault_key','vaultkey','session','private_key'}
SECRET_TOKEN_RE=re.compile(r'(private-[a-z0-9-]*token|bearer\s+[a-z0-9._\-]+)',re.I)
STATUSES=('unknown','unavailable','stale','inferred','observed')
LEVELS=('surface','verified','insights','attributed')
SCHEMA_VERSION=1

def ensure_schema(db):
 db.executescript('''CREATE TABLE IF NOT EXISTS audit_runs(
  id TEXT PRIMARY KEY,client_id TEXT NOT NULL,created_at TEXT NOT NULL,generated_by TEXT NOT NULL,report TEXT NOT NULL);
  CREATE INDEX IF NOT EXISTS audit_runs_client_created ON audit_runs(client_id, created_at);''')

def _number(value):
 return isinstance(value,(int,float)) and not isinstance(value,bool)

def _list(value):
 return value if isinstance(value,list) else []

def _parse_time(value):
 if value is None: return None
 if _number(value): return float(value)
 if not isinstance(value,str) or not value.strip(): return None
 try: return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
 except ValueError: return None

def _iso(ts):
 return datetime.fromtimestamp(ts,timezone.utc).isoformat()

def freshness(policy_id, observed_at, now, expires_at=None):
 policy=POLICIES[policy_id]
 observed=_parse_time(observed_at)
 age=None if observed is None else max(0, now-observed)
 info={'policy':policy_id,'mode':policy['mode'],'label':policy['label'],
       'maxAgeSeconds':policy['maxAgeSeconds'],'observedAt':observed_at,'ageSeconds':age,'fresh':True}
 if policy['mode']=='generation_time':
  info.update(observedAt=_iso(now),ageSeconds=0,fresh=True)
 elif policy['mode']=='until_disconnect':
  exp=_parse_time(expires_at)
  info.update(expiresAt=expires_at,fresh=exp is not None and exp>now)
 elif policy['mode']=='max_age':
  max_age=policy['maxAgeSeconds']
  info['fresh']=age is not None and age<=max_age
 else:
  info['fresh']=False
 return info

def _provenance(source,layer,**extra):
 payload={'source':source,'layer':layer}
 payload.update({k:v for k,v in extra.items() if v is not None})
 return payload

def _evidence(eid,kind,status,value=None,unit=None,explanation='',rule=None,freshness_info=None,provenance=None,
              account_id=None,metric_name=None,period=None,observed_at=None):
 if status not in STATUSES: raise ValueError('invalid evidence status')
 item={'id':eid,'kind':kind,'status':status,'value':value,'unit':unit,'explanation':explanation,
       'rule':rule,'freshness':freshness_info,'provenance':provenance or {},
       'accountId':account_id,'metricName':metric_name,'period':period,'observedAt':observed_at}
 if status=='observed' and _number(value) and value==0: item['zero']=True
 if status in ('unknown','unavailable') and item['value']==0: item['value']=None
 return item

def collect_evidence(workspace, now):
 items=[];assessment=workspace.get('assessment') or {};urls=assessment.get('urls') or {}
 snapshots=assessment.get('snapshots') or {};surface_at=snapshots.get('observedAt')
 surface_fresh=freshness('public_surface',surface_at,now)
 first_party=freshness('first_party',None,now)
 generated_at=_iso(now)
 if not isinstance(urls,dict): urls={}
 if not isinstance(snapshots,dict): snapshots={}
 for key in ASSESSMENT_SOURCES:
  label=SOURCE_LABELS.get(key,key);url=urls.get(key) if isinstance(urls.get(key),str) else ''
  if url.strip():
   items.append(_evidence(f'ev:source:{key}','source_url','observed',url.strip(),'url',
    f'تمت إضافة رابط {label}',freshness_info=first_party,
    provenance=_provenance('assessment.urls','public_surface',sourceKey=key,collectedAt=generated_at)))
  else:
   items.append(_evidence(f'ev:source:{key}','source_url','unknown',None,'url',
    f'لم يُضف رابط {label}',freshness_info=first_party,
    provenance=_provenance('assessment.urls','public_surface',sourceKey=key,collectedAt=generated_at)))
  snap=snapshots.get(key)
  if not url.strip(): continue
  if not isinstance(snap,dict):
   items.append(_evidence(f'ev:snapshot:{key}','surface_snapshot','unknown',None,None,
    'لا توجد نتيجة فحص عام لهذا المصدر',freshness_info=surface_fresh,
    provenance=_provenance('surface_collector','public_surface',sourceKey=key,collectedAt=surface_at)))
   continue
  snap_status=snap.get('status')
  signals=snap.get('signals') if isinstance(snap.get('signals'),dict) else {}
  payload={'title':snap.get('title') or '','httpStatus':snap.get('httpStatus'),'reason':snap.get('reason'),
           'signals':{k:signals[k] for k in signals if k in ('mobileViewport','forms','whatsApp','socialLinks','analytics','structuredData')}}
  if snap_status=='available':
   status='observed' if surface_fresh['fresh'] else 'stale'
   items.append(_evidence(f'ev:snapshot:{key}','surface_snapshot',status,payload,None,
    'قراءة عامة مكتملة' if status=='observed' else 'الفحص العام أقدم من سياسة الحداثة',
    freshness_info=surface_fresh,observed_at=surface_at,
    provenance=_provenance('surface_collector','public_surface',sourceKey=key,collectedAt=surface_at)))
  elif snap_status=='blocked':
   items.append(_evidence(f'ev:snapshot:{key}','surface_snapshot','unavailable',None,None,
    'رُفض الرابط من جامع الفحص العام',freshness_info=surface_fresh,observed_at=surface_at,
    provenance=_provenance('surface_collector','public_surface',sourceKey=key,reason=snap.get('reason'),collectedAt=surface_at)))
  else:
   items.append(_evidence(f'ev:snapshot:{key}','surface_snapshot','unavailable',payload,None,
    'تعذرت القراءة العامة للمصدر',freshness_info=surface_fresh,observed_at=surface_at,
    provenance=_provenance('surface_collector','public_surface',sourceKey=key,reason=snap.get('reason'),collectedAt=surface_at)))
 accounts=_list(workspace.get('accounts'));connections=_list(workspace.get('connections'))
 by_account={c.get('account_id'):c for c in connections if isinstance(c,dict)}
 verified=[]
 for account in accounts:
  if not isinstance(account,dict) or not account.get('id'): continue
  aid=account['id'];conn=by_account.get(aid)
  if not conn:
   items.append(_evidence(f'ev:connection:{aid}','connection','unknown',None,None,
    'لا يوجد تفويض محفوظ لهذا الحساب',account_id=aid,freshness_info=freshness('verified_identity',None,now),
    provenance=_provenance('connections','verified_identity',accountId=aid,platform=account.get('platform'),collectedAt=generated_at)))
   continue
  expires=conn.get('expires');ident_fresh=freshness('verified_identity',conn.get('verified_at'),now,expires)
  platform=conn.get('platform') or account.get('platform')
  if conn.get('status')=='identity_verified' and ident_fresh['fresh']:
   verified.append(aid)
   items.append(_evidence(f'ev:connection:{aid}','connection','observed','identity_verified',None,
    'تم التحقق من هوية الحساب عبر المنصة',account_id=aid,freshness_info=ident_fresh,observed_at=conn.get('verified_at'),
    provenance=_provenance('page_connections' if platform=='Facebook' else 'instagram_connections','verified_identity',
     accountId=aid,platform=platform,pageId=conn.get('page_id'),igUserId=conn.get('ig_user_id'),collectedAt=conn.get('verified_at'))))
  else:
   items.append(_evidence(f'ev:connection:{aid}','connection','unavailable','expired',None,
    'التفويض منتهٍ أو غير صالح',account_id=aid,freshness_info=ident_fresh,observed_at=conn.get('verified_at'),
    provenance=_provenance('connections','verified_identity',accountId=aid,platform=platform,collectedAt=conn.get('verified_at'))))
 if verified:
  items.append(_evidence('ev:identity','identity','observed',len(verified),'count',
   f'{len(verified)} اتصال صالح',freshness_info=freshness('verified_identity',generated_at,now,now+1),
   provenance=_provenance('connections','verified_identity',accountIds=verified,collectedAt=generated_at)))
 else:
  items.append(_evidence('ev:identity','identity','unknown',None,'count','لم تُتحقق أي هوية حساب',
   freshness_info=freshness('verified_identity',None,now),
   provenance=_provenance('connections','verified_identity',collectedAt=generated_at)))
 identity_ok=bool(verified)
 for snap in _list(workspace.get('insights')):
  if not isinstance(snap,dict): continue
  aid=snap.get('accountId');synced=snap.get('syncedAt');fresh=freshness('meta_insights',synced,now)
  period=snap.get('range') if isinstance(snap.get('range'),dict) else None
  metrics=snap.get('metrics') if isinstance(snap.get('metrics'),dict) else {}
  if not identity_ok:
   items.append(_evidence(f'ev:insight-locked:{aid or "unknown"}','insight_metric','unknown',None,None,
    'Insights تُستخدم بعد التحقق من الهوية',account_id=aid,freshness_info=fresh,
    provenance=_provenance('meta_graph_api','platform_insights',snapshotId=snap.get('id'),collectedAt=synced)))
   continue
  for name,payload in metrics.items():
   raw=payload.get('value') if isinstance(payload,dict) else None
   unit='count'
   if not _number(raw):
    status,value='unknown',None
   elif not fresh['fresh']:
    status,value='stale',raw
   else:
    status,value='observed',raw
   items.append(_evidence(f'ev:insight:{aid}:{name}','insight_metric',status,value,unit,
    'قيمة مرصودة من Snapshot المنصة' if status=='observed' else 'Snapshot أقدم من 48 ساعة' if status=='stale' else 'لا توجد قيمة رقمية صالحة',
    account_id=aid,metric_name=name,period=period,observed_at=synced,freshness_info=fresh,
    provenance=_provenance(snap.get('source') or 'Meta Graph API','platform_insights',
     accountId=aid,snapshotId=snap.get('id'),platform=snap.get('platform'),aggregation=(payload or {}).get('aggregation') if isinstance(payload,dict) else None,
     collectedAt=synced)))
  for name in _list(snap.get('unavailable')):
   if not isinstance(name,str): continue
   items.append(_evidence(f'ev:insight:{aid}:{name}','insight_metric','unavailable',None,'count',
    'Meta رفضت أو لم تُرجع هذا المقياس',account_id=aid,metric_name=name,period=period,observed_at=synced,freshness_info=fresh,
    provenance=_provenance(snap.get('source') or 'Meta Graph API','platform_insights',
     accountId=aid,snapshotId=snap.get('id'),platform=snap.get('platform'),collectedAt=synced)))
  if snap.get('status')=='unavailable' and not metrics and not _list(snap.get('unavailable')):
   items.append(_evidence(f'ev:insight:{aid}:snapshot','insight_metric','unavailable',None,None,
    'تعذرت مزامنة Insights لهذا الحساب',account_id=aid,observed_at=synced,freshness_info=fresh,
    provenance=_provenance(snap.get('source') or 'Meta Graph API','platform_insights',snapshotId=snap.get('id'),collectedAt=synced)))
 posts=_list(workspace.get('posts'));jobs=_list(workspace.get('jobs'))
 leads=_list(workspace.get('leads'));campaigns=_list(workspace.get('campaigns'));media=_list(workspace.get('media'))
 def ops(eid,kind,payload,explanation):
  if not identity_ok:
   return _evidence(eid,kind,'unknown',None,None,'بيانات التشغيل تُفتح بعد التحقق من الهوية',rule='ops_locked_until_verified',
    freshness_info=first_party,provenance=_provenance('nemdar_store','nemdar_operations',collectedAt=generated_at))
  return _evidence(eid,kind,'observed',payload,None,explanation,freshness_info=first_party,
   provenance=_provenance('nemdar_store','nemdar_operations',collectedAt=generated_at))
 published=[p for p in posts if isinstance(p,dict) and p.get('status') in ('published','partial')]
 scheduled=[p for p in posts if isinstance(p,dict) and p.get('status')=='scheduled']
 terminal=[j for j in jobs if isinstance(j,dict) and j.get('state') in ('published','failed','unknown')]
 successful=[j for j in terminal if j.get('state')=='published']
 failed=[j for j in jobs if isinstance(j,dict) and j.get('state')=='failed']
 items.append(ops('ev:ops:posts','operation_posts',
  {'total':len(posts),'published':len(published),'scheduled':len(scheduled)} if identity_ok else None,
  f'{len(posts)} عنصر محتوى مسجّل'))
 items.append(ops('ev:ops:jobs','operation_jobs',
  {'total':len(jobs),'terminal':len(terminal),'successful':len(successful),'failed':len(failed),
   'deliveryRate':round(len(successful)/len(terminal)*100) if terminal else None} if identity_ok else None,
  'نتائج إرسال موثّقة' if terminal else 'لا توجد نتائج نهائية'))
 qualified=[l for l in leads if isinstance(l,dict) and l.get('status')=='qualified']
 complete=[l for l in leads if isinstance(l,dict) and l.get('status')!='incomplete']
 items.append(ops('ev:ops:leads','operation_leads',
  {'total':len(leads),'qualified':len(qualified),'complete':len(complete)} if identity_ok else None,
  f'{len(leads)} ليد مسجّل'))
 approved=[c for c in campaigns if isinstance(c,dict) and c.get('status')=='approved']
 items.append(ops('ev:ops:campaigns','operation_campaigns',
  {'total':len(campaigns),'approved':len(approved)} if identity_ok else None,
  f'{len(campaigns)} خطة حملة'))
 documented=[m for m in media if isinstance(m,dict) and str(m.get('alt') or '').strip() and str(m.get('rights') or '').strip()]
 items.append(ops('ev:ops:media','operation_media',
  {'total':len(media),'documented':len(documented)} if identity_ok else None,
  f'{len(media)} أصل وسائط'))
 analytics=any(isinstance(e.get('value'),dict) and (e['value'].get('signals') or {}).get('analytics')
               for e in items if e['kind']=='surface_snapshot' and e['status'] in ('observed','stale'))
 crm_attribution=bool(workspace.get('attributionEvidence'))
 items.append(_evidence('ev:attribution','attribution','observed' if (analytics and crm_attribution) else 'unknown',
  None,None,
  'يتوفر Analytics وربط CRM' if analytics and crm_attribution else 'لا يمكن إثبات التحويل دون Analytics وربط CRM',
  freshness_info=first_party,provenance=_provenance('analytics_crm','revenue_attribution',collectedAt=generated_at)))
 return items

def _insight_items(evidence, name):
 return [e for e in evidence if e.get('kind')=='insight_metric' and e.get('metricName')==name]

def _compatible_periods(items):
 periods=[e.get('period') for e in items if isinstance(e.get('period'),dict)]
 if not periods: return True
 days={p.get('days') for p in periods}
 if len(days)>1: return False
 sinces=[_parse_time(p.get('since')) for p in periods]
 untils=[_parse_time(p.get('until')) for p in periods]
 if any(v is None for v in sinces+untils):
  # unix ints are numbers already parsed as time? since/until in insights are unix ints
  sinces=[float(p['since']) if _number(p.get('since')) else _parse_time(p.get('since')) for p in periods]
  untils=[float(p['until']) if _number(p.get('until')) else _parse_time(p.get('until')) for p in periods]
 if any(v is None for v in sinces+untils): return False
 return (max(sinces)-min(sinces)<=PERIOD_COMPAT_SECONDS) and (max(untils)-min(untils)<=PERIOD_COMPAT_SECONDS)

def aggregate_insight(evidence, name):
 items=_insight_items(evidence,name)
 if not items:
  return {'status':'unknown','value':None,'aggregation':'none','accounts':[],'evidenceIds':[],
          'explanation':'لا توجد أدلة Insights لهذا المقياس'}
 observed=[e for e in items if e['status']=='observed' and _number(e.get('value'))]
 stale=[e for e in items if e['status']=='stale' and _number(e.get('value'))]
 unavailable=[e for e in items if e['status']=='unavailable']
 ids=[e['id'] for e in items]
 accounts=[{'accountId':e.get('accountId'),'status':e['status'],'value':e.get('value'),'period':e.get('period'),
            'unit':e.get('unit'),'evidenceId':e['id']} for e in items]
 if name in NON_ADDITIVE_INSIGHT_METRICS:
  if len(observed)==1 and not stale:
   return {'status':'observed','value':observed[0]['value'],'aggregation':'per_account','accounts':accounts,
           'evidenceIds':ids,'explanation':'قيمة لكل حساب؛ لا تُجمع المتابعات كاتجاه زمني'}
  if observed or stale:
   return {'status':'observed' if observed and not stale else 'stale','value':None,'aggregation':'per_account',
           'accounts':accounts,'evidenceIds':ids,
           'explanation':'قيم المتابعين لكل حساب. لا يُجمع المجموع كاتجاه نمو ما لم يُصرَّح أنه إجمالي الجمهور'}
  if unavailable and not observed:
   return {'status':'unavailable','value':None,'aggregation':'none','accounts':accounts,'evidenceIds':ids,
           'explanation':'المقياس غير متاح من المنصة'}
  return {'status':'unknown','value':None,'aggregation':'none','accounts':accounts,'evidenceIds':ids,
          'explanation':'لا توجد قيمة مرصودة'}
 usable=observed
 if not usable and stale:
  status='stale';usable=stale
 elif not usable and unavailable:
  return {'status':'unavailable','value':None,'aggregation':'none','accounts':accounts,'evidenceIds':ids,
          'explanation':'Meta رفضت هذا المقياس'}
 elif not usable:
  return {'status':'unknown','value':None,'aggregation':'none','accounts':accounts,'evidenceIds':ids,
          'explanation':'لا توجد قيمة مرصودة'}
 else:
  status='observed'
 incomplete=len(usable)<len([e for e in items if e['status'] in ('observed','stale','unavailable','unknown')]) and any(e['status'] in ('unknown','unavailable') for e in items)
 if len(usable)==1 and not incomplete:
  return {'status':status,'value':usable[0]['value'],'aggregation':'single','accounts':accounts,'evidenceIds':ids,
          'explanation':'قيمة مرصودة لحساب واحد'}
 if name in ADDITIVE_INSIGHT_METRICS and _compatible_periods(usable) and all(e.get('unit')==usable[0].get('unit') for e in usable) and not incomplete:
  total=sum(e['value'] for e in usable)
  return {'status':status,'value':total,'aggregation':'sum','accounts':accounts,'evidenceIds':ids,
          'explanation':f'مجموع {name} عبر {len(usable)} حسابات بنطاق زمني متوافق'}
 return {'status':status,'value':None,'aggregation':'per_account','accounts':accounts,'evidenceIds':ids,
         'explanation':'القيم غير قابلة للجمع بسبب اختلاف النطاق أو نقص القياس في بعض الحسابات'}

def _conf_label(status, fresh=True):
 if status=='observed' and fresh: return 'عالٍ'
 if status=='observed': return 'متوسط'
 if status=='inferred': return 'متوسط'
 if status=='stale': return 'منخفض'
 return 'غير متاح'

def _metric(mid,section,section_title,title,status,value,display,unit,confidence,explanation,evidence_ids,provenance,
            scoring,freshness_info=None,rule=None,accounts=None,period=None,aggregation='none',improvement=None):
 return {
  'id':mid,'section':section,'sectionTitle':section_title,'title':title,'name':title,'group':section_title,
  'status':status,'value':value,'displayValue':display,'unit':unit,'confidence':confidence,
  'explanation':explanation,'evidenceIds':evidence_ids or [],'provenance':provenance or {},
  'scoring':scoring,'freshness':freshness_info,'rule':rule,'accounts':accounts or [],
  'period':period,'aggregation':aggregation,'improvementAction':improvement,'source':(provenance or {}).get('source') or ''
 }

COV={'coverage':True,'confidence':True,'performance':False}
PERF={'coverage':True,'confidence':True,'performance':True}

def evaluate_metrics(workspace, evidence, now):
 by_id={e['id']:e for e in evidence}
 def ev(*ids): return [by_id[i] for i in ids if i in by_id]
 identity=by_id.get('ev:identity') or {}
 verified=identity.get('status')=='observed'
 source_obs=[e for e in evidence if e['kind']=='source_url' and e['status']=='observed']
 snaps_ok=[e for e in evidence if e['kind']=='surface_snapshot' and e['status'] in ('observed','stale')]
 website_snap=next((e for e in evidence if e['id']=='ev:snapshot:website'),None)
 website_src=by_id.get('ev:source:website')
 posts=by_id.get('ev:ops:posts') or {}
 jobs=by_id.get('ev:ops:jobs') or {}
 leads=by_id.get('ev:ops:leads') or {}
 campaigns=by_id.get('ev:ops:campaigns') or {}
 attr=by_id.get('ev:attribution') or {}
 first_party=freshness('first_party',None,now)
 metrics=[]
 metrics.append(_metric('channels_present','presence','الحضور الرقمي','القنوات الموجودة','observed',len(source_obs),
  f'{len(source_obs)} من {len(ASSESSMENT_SOURCES)} مصادر أُضيفت للتقييم','count',_conf_label('observed'),
  'عدد الروابط التي أدخلها العميل. القيمة صفر هنا مرصودة وليست مقياساً للأداء.',
  [e['id'] for e in source_obs] or ['ev:source:website'],_provenance('assessment.urls','public_surface'),COV,
  first_party,improvement='add_source_url'))
 if verified:
  n=identity.get('value') or 0
  metrics.append(_metric('identity_discoverability','identity','الهوية','قابلية اكتشاف الهوية العامة','observed',n,
   f'{n} حساب تم التحقق من هويته عبر المنصة','count',_conf_label('observed'),
   'التحقق من الهوية لا يساوي صلاحية Insights.',identity.get('id') and [identity['id']] or [],
   identity.get('provenance'),COV,identity.get('freshness')))
 elif snaps_ok:
  metrics.append(_metric('identity_discoverability','identity','الهوية','قابلية اكتشاف الهوية العامة','inferred',len(snaps_ok),
   f'تمت قراءة العنوان والوصف العام من {len(snaps_ok)} مصدر','count',_conf_label('inferred'),
   'هوية مستنتجة من البيانات العامة فقط.',[e['id'] for e in snaps_ok],
   _provenance('surface_collector','public_surface'),COV,snaps_ok[0].get('freshness'),rule='infer_identity_from_public_title'))
 elif source_obs:
  metrics.append(_metric('identity_discoverability','identity','الهوية','قابلية اكتشاف الهوية العامة','inferred',len(source_obs),
   'الروابط محفوظة لكن المصادر لم تسمح بالقراءة العامة','count',_conf_label('inferred'),
   'لا توجد قراءة عامة ناجحة بعد.',[e['id'] for e in source_obs],
   _provenance('assessment.urls','public_surface'),COV,first_party,rule='infer_identity_from_saved_urls'))
 else:
  metrics.append(_metric('identity_discoverability','identity','الهوية','قابلية اكتشاف الهوية العامة','unknown',None,
   'لم تُضف مصادر كافية لاكتشاف الهوية','count','غير متاح','لا توجد أدلة هوية.',
   ['ev:identity'],_provenance('connections','verified_identity'),COV,first_party,improvement='connect_account'))
 site_ok=website_snap and website_snap.get('status') in ('observed','stale')
 present=len(source_obs)
 if site_ok and present>1:
  signals=(website_snap.get('value') or {}).get('signals') or {}
  metrics.append(_metric('journey_cta','journey','رحلة العميل','ترابط القنوات والـCTA',website_snap['status'],
   {'whatsApp':bool(signals.get('whatsApp')),'forms':signals.get('forms') or 0,'socialLinks':signals.get('socialLinks') or 0},
   f"الموقع: {'WhatsApp ظاهر' if signals.get('whatsApp') else 'WhatsApp غير مكتشف'} · {signals.get('forms') or 0} نموذج · {signals.get('socialLinks') or 0} رابط سوشيال",
   None,_conf_label(website_snap['status'],(website_snap.get('freshness') or {}).get('fresh',True)),
   'إشارات CTA من الفحص العام للموقع.',[website_snap['id']]+[e['id'] for e in source_obs],
   website_snap.get('provenance'),COV,website_snap.get('freshness')))
 elif website_src and website_src.get('status')=='observed' and present>1:
  metrics.append(_metric('journey_cta','journey','رحلة العميل','ترابط القنوات والـCTA','inferred',None,
   'الموقع موجود لكن القراءة العامة لم تكتمل',None,_conf_label('inferred'),
   'الاستنتاج من وجود روابط فقط.',[website_src['id']],website_src.get('provenance'),COV,first_party,rule='infer_journey_from_urls'))
 else:
  metrics.append(_metric('journey_cta','journey','رحلة العميل','ترابط القنوات والـCTA','unknown',None,
   'أضف الموقع وقناة سوشيال واحدة على الأقل',None,'غير متاح','لا يكفي دليل لرحلة العميل.',
   [website_src['id']] if website_src else [],_provenance('surface_collector','public_surface'),COV,first_party,improvement='add_website_and_social'))
 if site_ok:
  signals=(website_snap.get('value') or {}).get('signals') or {}
  metrics.append(_metric('website_conversion_readiness','website','الموقع','جاهزية التحويل والقياس',website_snap['status'],
   signals,f"{'Mobile ✓' if signals.get('mobileViewport') else 'Mobile غير مكتشف'} · {'Tracking ✓' if signals.get('analytics') else 'Tracking غير مكتشف'} · {'Structured Data ✓' if signals.get('structuredData') else 'Structured Data غير مكتشف'}",
   None,_conf_label(website_snap['status'],(website_snap.get('freshness') or {}).get('fresh',True)),
   'إشارات HTML عامة. غياب Analytics ليس أداء تحويل سيئاً.',[website_snap['id']],website_snap.get('provenance'),COV,website_snap.get('freshness'),
   improvement='enable_website_analytics'))
 elif website_src and website_src.get('status')=='observed':
  metrics.append(_metric('website_conversion_readiness','website','الموقع','جاهزية التحويل والقياس','unknown',None,
   'تعذرت قراءة الموقع من الخادم',None,'غير متاح','تعذر القياس لا يُحوَّل إلى صفر.',
   [website_src['id']],website_src.get('provenance'),COV,first_party))
 else:
  metrics.append(_metric('website_conversion_readiness','website','الموقع','جاهزية التحويل والقياس','unknown',None,
   'لم يُضف موقع',None,'غير متاح','لا يوجد موقع لفحصه.',[],_provenance('assessment.urls','public_surface'),COV,first_party,improvement='add_website'))
 if verified and posts.get('status')=='observed':
  payload=posts.get('value') or {}
  metrics.append(_metric('content_cycle','operations','التشغيل','دورة المحتوى داخل NEMDAR','observed',payload.get('total'),
   f"{payload.get('total') or 0} محتوى · {payload.get('published') or 0} منشور/نجاح جزئي · {payload.get('scheduled') or 0} مجدول",
   'count',_conf_label('observed'),'تشغيل داخلي، ليس Analytics منصة.',[posts['id']],posts.get('provenance'),COV,first_party))
 else:
  metrics.append(_metric('content_cycle','operations','التشغيل','دورة المحتوى داخل NEMDAR','unknown',None,
   'لا توجد دورة محتوى موثّقة متاحة في وضع التقرير الحالي',None,'غير متاح','تُفتح بعد التحقق من الهوية.',
   [posts.get('id')] if posts.get('id') else [],_provenance('nemdar_store','nemdar_operations'),COV,first_party,improvement='create_content_cycle',
   rule=posts.get('rule')))
 job_payload=jobs.get('value') if isinstance(jobs.get('value'),dict) else {}
 if verified and jobs.get('status')=='observed' and job_payload.get('terminal'):
  rate=job_payload.get('deliveryRate')
  metrics.append(_metric('publishing_reliability','operations','التشغيل','موثوقية تسليم النشر','observed',rate,
   f"{job_payload.get('successful') or 0} نجاح من {job_payload.get('terminal') or 0} نتيجة نهائية · {rate}%",
   'percent',_conf_label('observed'),'نسبة نتائج الإرسال النهائية المرصودة داخل NEMDAR، وليست معيار صناعة.',
   [jobs['id']],jobs.get('provenance'),PERF,first_party))
 elif verified and jobs.get('status')=='observed' and job_payload.get('total'):
  metrics.append(_metric('publishing_reliability','operations','التشغيل','موثوقية تسليم النشر','inferred',None,
   f"{job_payload.get('total')} مهمة موجودة لكن لا توجد نتائج نهائية كافية",None,_conf_label('inferred'),
   'المهام موجودة دون نتائج نهائية كافية للقياس.',[jobs['id']],jobs.get('provenance'),COV,first_party,rule='infer_jobs_pending_terminal'))
 else:
  metrics.append(_metric('publishing_reliability','operations','التشغيل','موثوقية تسليم النشر','unknown',None,
   'لا توجد نتائج إرسال موثقة يمكن قياسها',None,'غير متاح','لا تُحتسب النسبة صفراً عند غياب النتائج.',
   [jobs.get('id')] if jobs.get('id') else [],_provenance('dispatch_jobs','nemdar_operations'),COV,first_party,improvement='investigate_publishing'))
 insight_titles={
  'reach':('الأداء','Reach','count'),
  'impressions':('الأداء','Impressions','count'),
  'saves':('الأداء','Saves','count'),
  'engagements':('الأداء','التفاعل الموثّق','count'),
  'followers':('الجمهور','المتابعون','count'),
  'audience_demographics':('الجمهور','العمر والموقع وأوقات النشاط',None)
 }
 for iid,(section_title,title,unit) in insight_titles.items():
  if iid=='saves':
   metrics.append(_metric('saves','performance',section_title,title,'unknown',None,'Saves غير متاح في ملخص الحساب',unit,'غير متاح',
    'لا يوجد مصدر Saves في Snapshot الحالي. الغياب ليس صفراً.',[],_provenance('meta_graph_api','platform_insights'),COV,
    freshness('meta_insights',None,now),improvement='sync_insights'))
   continue
  if iid=='audience_demographics':
   metrics.append(_metric('audience_demographics','audience',section_title,title,'unknown',None,
    'لن نخمن بيانات الجمهور من المتابعين أو التعليقات',None,'غير متاح','يتطلب موصل Insights ديموغرافي.',
    [],_provenance('meta_graph_api','platform_insights'),COV,freshness('meta_insights',None,now)))
   continue
  agg=aggregate_insight(evidence,iid)
  status=agg['status'];value=agg['value']
  if status=='observed' and agg['aggregation']=='per_account':
   parts=[]
   for row in agg['accounts']:
    if row['status']=='observed' and _number(row['value']): parts.append(f"{row['accountId']}: {int(row['value'])}")
    elif row['status']=='unknown': parts.append(f"{row['accountId']}: غير معروف")
    elif row['status']=='unavailable': parts.append(f"{row['accountId']}: غير متاح")
    elif row['status']=='stale' and _number(row['value']): parts.append(f"{row['accountId']}: {int(row['value'])} (قديم)")
   display=' · '.join(parts) or agg['explanation']
  elif status in ('observed','stale') and _number(value):
   display=f"{title} {int(value)}" if iid!='engagements' else f"{int(value)} تفاعل خلال نطاق الـSnapshot"
   if status=='stale': display+=' · بيانات قديمة'
  elif status=='unavailable':
   display='المقياس غير متاح من المنصة'
  elif verified:
   display='تم التحقق من الهوية، لكن Insights لم تُزامن أو لم تسمح بها Meta'
  else:
   display='غير متاح من الروابط العامة'
  mid={'engagements':'engagements','followers':'followers'}.get(iid,iid)
  item_fresh=None
  related=_insight_items(evidence,iid)
  if related: item_fresh=related[0].get('freshness')
  metrics.append(_metric(mid,'performance' if iid!='followers' else 'audience',section_title,title,status,value,display,unit,
   _conf_label(status,(item_fresh or {}).get('fresh',status=='observed')),agg['explanation'],agg['evidenceIds'],
   related[0].get('provenance') if related else _provenance('meta_graph_api','platform_insights'),COV,item_fresh,
   accounts=agg['accounts'],period=(related[0].get('period') if related else None),aggregation=agg['aggregation'],
   improvement='sync_insights'))
 if verified and campaigns.get('status')=='observed':
  payload=campaigns.get('value') or {}
  metrics.append(_metric('campaign_readiness','campaigns','الحملات','جاهزية خطط الحملات','observed',payload.get('total'),
   f"{payload.get('total') or 0} خطة · {payload.get('approved') or 0} ميزانية معتمدة · إنفاق فعلي غير متاح",'count',
   _conf_label('observed'),'خطط داخلية. الاعتماد ليس إنفاقاً.',[campaigns['id']],campaigns.get('provenance'),COV,first_party))
 else:
  metrics.append(_metric('campaign_readiness','campaigns','الحملات','جاهزية خطط الحملات','unknown',None,
   'لا توجد خطط حملات موثقة في التقرير المتقدم',None,'غير متاح','تُفتح بعد التحقق.',
   [campaigns.get('id')] if campaigns.get('id') else [],_provenance('nemdar_store','nemdar_operations'),COV,first_party,improvement='review_campaigns'))
 metrics.append(_metric('ad_performance','ads','الإعلانات','Spend · CTR · CPL · ROAS','unknown',None,
  'لا يُعرض الإنفاق المخطط كأنه إنفاق فعلي',None,'غير متاح','يتطلب ربط Ad Account للقراءة.',
  [],_provenance('ad_account','revenue_attribution'),COV,first_party))
 if verified and leads.get('status')=='observed':
  payload=leads.get('value') or {}
  total=payload.get('total') or 0
  rate=round((payload.get('qualified') or 0)/total*100) if total else None
  metrics.append(_metric('lead_quality','leads','الليدز','جودة وتأهيل الليدز','observed',rate,
   f"{payload.get('qualified') or 0} مؤهل من {total} · {payload.get('complete') or 0} مكتمل القرار",'percent',
   _conf_label('observed'),'نسبة التأهيل من أدلة BANT الداخلية.',[leads['id']],leads.get('provenance'),PERF if rate is not None else COV,first_party))
 else:
  metrics.append(_metric('lead_quality','leads','الليدز','جودة وتأهيل الليدز','unknown',None,
   'لا توجد بيانات ليدز موثقة في التقرير المتقدم',None,'غير متاح','تُفتح بعد التحقق.',
   [leads.get('id')] if leads.get('id') else [],_provenance('nemdar_store','nemdar_operations'),COV,first_party,improvement='record_leads'))
 conv_status=attr.get('status') or 'unknown'
 metrics.append(_metric('conversion_revenue','conversion','التحويل','Conversion Rate · Revenue',conv_status,None,
  'الليدز موجودة لكن لا يوجد ربط إيراد أو مصدر تحويل مثبت' if (leads.get('value') or {}).get('total') else 'لا يمكن إثبات التحويل من بيانات السوشيال العامة',
  None,'غير متاح' if conv_status!='observed' else _conf_label('observed'),
  'غياب قياس التحويل يعني أن التحويل غير قابل للتحقق، وليس أداءً سيئاً.',
  [attr.get('id')] if attr.get('id') else [],attr.get('provenance') or _provenance('analytics_crm','revenue_attribution'),COV,
  first_party,improvement='verify_conversion_measurement'))
 expired=[e for e in evidence if e['kind']=='connection' and e.get('value')=='expired']
 if verified:
  metrics.append(_metric('connection_security','security','الأمان','حالة الاتصال','observed',len([e for e in evidence if e['kind']=='connection' and e['status']=='observed']),
   f"{len([e for e in evidence if e['kind']=='connection' and e['status']=='observed'])} اتصال صالح · قراءة الهوية مؤكدة"+(f" · {len(expired)} منتهي" if expired else ''),
   'count',_conf_label('observed'),'حالة التفويض الحالية.',[e['id'] for e in evidence if e['kind']=='connection'],
   _provenance('connections','verified_identity'),COV,first_party))
 elif expired:
  metrics.append(_metric('connection_security','security','الأمان','حالة الاتصال','unavailable',len(expired),
   f'{len(expired)} اتصال منتهي ويحتاج تجديد',None,_conf_label('unavailable'),
   'التفويض منتهٍ.',[e['id'] for e in expired],_provenance('connections','verified_identity'),COV,first_party,improvement='renew_connection'))
 else:
  metrics.append(_metric('connection_security','security','الأمان','حالة الاتصال','unknown',None,
   'لم تمنح NEMDAR أي صلاحية للحسابات حتى الآن',None,'غير متاح','لا يوجد تفويض.',
   ['ev:identity'],_provenance('connections','verified_identity'),COV,first_party,improvement='connect_account'))
 return metrics

def derive_level(evidence, workspace):
 identity=next((e for e in evidence if e['id']=='ev:identity'),None)
 verified=identity and identity.get('status')=='observed'
 attr=next((e for e in evidence if e['id']=='ev:attribution'),None)
 insights=[e for e in evidence if e['kind']=='insight_metric' and e['status']=='observed']
 if attr and attr.get('status')=='observed' and workspace.get('attributionEvidence') and insights:
  return 'attributed'
 if verified and insights:
  return 'insights'
 if verified:
  return 'verified'
 return 'surface'

def _coverage_weight(status):
 return {'observed':1.0,'inferred':0.5,'stale':0.75,'unavailable':0.0,'unknown':0.0}.get(status,0.0)

def _confidence_weight(metric):
 status=metric['status']
 fresh=(metric.get('freshness') or {}).get('fresh',True)
 if status=='unknown': return None
 if status=='observed': return 1.0 if fresh else 0.55
 if status=='inferred': return 0.45
 if status=='stale': return 0.35
 if status=='unavailable': return 0.8
 return None

def score_metrics(metrics):
 coverable=[m for m in metrics if (m.get('scoring') or {}).get('coverage')]
 coverage=round(sum(_coverage_weight(m['status']) for m in coverable)/len(coverable)*100) if coverable else 0
 conf_vals=[w for w in (_confidence_weight(m) for m in coverable) if w is not None]
 confidence=round(sum(conf_vals)/len(conf_vals)*100) if conf_vals else None
 perf_vals=[]
 for m in metrics:
  if not (m.get('scoring') or {}).get('performance'): continue
  if m['status']!='observed': continue
  if not _number(m.get('value')): continue
  perf_vals.append(float(m['value']))
 performance=round(sum(perf_vals)/len(perf_vals)) if perf_vals else None
 sections={}
 for m in metrics:
  bucket=sections.setdefault(m['section'],{'id':m['section'],'title':m['sectionTitle'],'metrics':[]})
  bucket['metrics'].append(m)
 section_scores=[]
 for bucket in sections.values():
  rows=bucket['metrics']
  cov=round(sum(_coverage_weight(m['status']) for m in rows)/len(rows)*100) if rows else 0
  cvals=[w for w in (_confidence_weight(m) for m in rows) if w is not None]
  conf=round(sum(cvals)/len(cvals)*100) if cvals else None
  pvals=[float(m['value']) for m in rows if (m.get('scoring') or {}).get('performance') and m['status']=='observed' and _number(m.get('value'))]
  section_scores.append({'id':bucket['id'],'title':bucket['title'],'coverageScore':cov,'confidenceScore':conf,
                         'performanceScore':round(sum(pvals)/len(pvals)) if pvals else None})
 observed=sum(1 for m in metrics if m['status']=='observed')
 inferred=sum(1 for m in metrics if m['status']=='inferred')
 unknown=sum(1 for m in metrics if m['status']=='unknown')
 unavailable=sum(1 for m in metrics if m['status']=='unavailable')
 stale=sum(1 for m in metrics if m['status']=='stale')
 return {
  'coverage':coverage,'confidence':confidence,'performance':performance,
  'performanceExplanation':None if performance is not None else 'لا توجد مقاييس أداء مرصودة وقابلة للمقارنة. المقاييس الناقصة لا تخفّض درجة الأداء.',
  'sectionScores':section_scores,
  'counts':{'observed':observed,'inferred':inferred,'unknown':unknown,'unavailable':unavailable,'stale':stale,'total':len(metrics)}
 }

def build_layers(evidence, workspace, level):
 inspected=[e for e in evidence if e['kind']=='surface_snapshot' and e['status'] in ('observed','stale')]
 present=[e for e in evidence if e['kind']=='source_url' and e['status']=='observed']
 verified=[e for e in evidence if e['kind']=='connection' and e['status']=='observed']
 posts=next((e for e in evidence if e['id']=='ev:ops:posts'),None)
 leads=next((e for e in evidence if e['id']=='ev:ops:leads'),None)
 campaigns=next((e for e in evidence if e['id']=='ev:ops:campaigns'),None)
 insights_obs=[e for e in evidence if e['kind']=='insight_metric' and e['status']=='observed']
 insights_stale=[e for e in evidence if e['kind']=='insight_metric' and e['status']=='stale']
 ops_ready=bool(verified) and any((e.get('value') or {}).get('total') for e in (posts,leads,campaigns) if e and e.get('status')=='observed')
 attr=next((e for e in evidence if e['id']=='ev:attribution'),None)
 layers=[
  {'id':'public_surface','name':'Public Surface','status':'ready' if inspected else 'limited' if present else 'empty',
   'detail':f'{len(inspected)} من {len(present)} مصدر تمت قراءته'},
  {'id':'verified_identity','name':'Verified Identity','status':'ready' if verified else 'locked',
   'detail':f'{len(verified)} اتصال موثّق' if verified else 'يحتاج ربط حساب'},
  {'id':'nemdar_operations','name':'NEMDAR Operations',
   'status':'ready' if ops_ready else 'empty' if verified else 'locked',
   'detail':(f"{(posts.get('value') or {}).get('total',0)} محتوى · {(leads.get('value') or {}).get('total',0)} ليد · {(campaigns.get('value') or {}).get('total',0)} حملة") if verified else 'تُفتح بعد التحقق'},
  {'id':'platform_insights','name':'Platform Insights',
   'status':'ready' if insights_obs else 'stale' if insights_stale else 'locked',
   'detail':(f'{len(insights_obs)+len(insights_stale)} دليل Insights') if insights_obs or insights_stale else 'Reach والجمهور تحتاج صلاحيات قراءة منفصلة'},
  {'id':'revenue_attribution','name':'Revenue Attribution',
   'status':'ready' if attr and attr.get('status')=='observed' else 'locked',
   'detail':'Analytics + CRM attribution متوفران' if attr and attr.get('status')=='observed' else 'يحتاج Analytics + CRM attribution'}
 ]
 return layers

def recommend(evidence, metrics, workspace):
 by_id={e['id']:e for e in evidence}
 identity=by_id.get('ev:identity') or {}
 verified=identity.get('status')=='observed'
 website=next((e for e in evidence if e['id']=='ev:snapshot:website'),None)
 jobs=by_id.get('ev:ops:jobs') or {}
 posts=by_id.get('ev:ops:posts') or {}
 leads=by_id.get('ev:ops:leads') or {}
 campaigns=by_id.get('ev:ops:campaigns') or {}
 expired=[e for e in evidence if e['kind']=='connection' and e.get('value')=='expired']
 insight_obs=[e for e in evidence if e['kind']=='insight_metric' and e['status']=='observed']
 insight_stale=[e for e in evidence if e['kind']=='insight_metric' and e['status']=='stale']
 insight_unavail=[e for e in evidence if e['kind']=='insight_metric' and e['status']=='unavailable']
 candidates=[]
 def add(priority,family,rid,title,detail,route,evidence_ids,rule):
  candidates.append({'priority':priority,'family':family,'id':rid,'title':title,'detail':detail,'route':route,
                     'evidenceIds':[eid for eid in evidence_ids if eid],'rule':rule})
 if not verified:
  add(1,'connect','rec_connect','اربط حسابًا واحدًا للتحقق',
      'الربط الحالي يؤكد هوية الحساب ويفتح طبقة بيانات التشغيل داخل NEMDAR؛ لا ينشر أو يحذف تلقائيًا.','connectors',
      ['ev:identity'],'recommend_connect_unverified')
 if expired:
  add(1,'expired','rec_renew','جدّد التفويض المنتهي','يوجد اتصال منتهٍ ولا يمكن اعتماد هويته حتى يُجدَّد.','connectors',
      [e['id'] for e in expired],'recommend_renew_expired')
 if verified and posts.get('status')=='observed' and not (posts.get('value') or {}).get('total'):
  add(1,'content','rec_content','أنشئ أول دورة محتوى موثّقة',
      'أضف مسودة، راجعها، اعتمدها ثم جدولها حتى يبدأ التقرير بقياس انتظام التشغيل.','content',
      [posts.get('id')],'recommend_create_content')
 if verified and (posts.get('value') or {}).get('total') and not (posts.get('value') or {}).get('published'):
  add(1,'publish','rec_first_publish','أكمل أول نشر موثّق',
      f"يوجد {(posts.get('value') or {}).get('total')} عنصر محتوى لكن لا توجد نتيجة نشر ناجحة أو جزئية مسجلة حتى الآن.",'queue',
      [posts.get('id')],'recommend_complete_first_publish')
 failed=(jobs.get('value') or {}).get('failed') or 0
 if verified and failed:
  add(1,'publish','rec_publish_fail','راجع موثوقية النشر',
      f'يوجد {failed} فشل إرسال مرصود. هذا دليل تشغيلي وليس تخمين أداء منصة.','queue',
      [jobs.get('id')],'recommend_investigate_publishing_failure')
 if website and website.get('status') in ('observed','stale') and not ((website.get('value') or {}).get('signals') or {}).get('analytics'):
  add(2,'analytics','rec_site_analytics','فعّل قياس الموقع',
      'لم يكتشف الفحص العام Analytics؛ أضف أداة قياس ثم أعد التقييم لإثبات مسار التحويل. غياب الأداة لا يعني أداء تحويل سيئاً.','audit',
      [website['id']],'recommend_enable_website_analytics')
 if verified and not (leads.get('value') or {}).get('total'):
  add(2,'leads','rec_leads','اربط مرحلة الليدز بالتشغيل',
      'لا توجد ليدز داخل مساحة العميل؛ سجّل المصدر وأدلة BANT قبل حساب جودة التحويل.','leads',
      [leads.get('id')],'recommend_record_leads')
 if verified and (campaigns.get('value') or {}).get('total') and not (campaigns.get('value') or {}).get('approved'):
  add(3,'campaigns','rec_campaigns','راجع خطط الحملات',
      f"هناك {(campaigns.get('value') or {}).get('total')} خطة بدون اعتماد ميزانية مسجل. الاعتماد لا يشغّل إعلانًا ولا يخصم مبلغًا.",'campaigns',
      [campaigns.get('id')],'recommend_review_campaigns')
 if verified and not insight_obs and not insight_stale:
  add(2,'insights','rec_sync_insights','زامن Insights للمنصة',
      'التحقق من الهوية وحده لا يوفر Reach أو Impressions. شغّل مزامنة القراءة من شاشة ربط المنصات.','connectors',
      [e['id'] for e in evidence if e['kind']=='connection' and e['status']=='observed'] or ['ev:identity'],
      'recommend_sync_insights')
 elif verified and insight_stale and not insight_obs:
  add(2,'insights','rec_refresh_insights','حدّث Insights القديمة',
      'توجد قيم Insights لكنّها أقدم من سياسة الـ48 ساعة. أعد المزامنة قبل استخدام الأرقام.','connectors',
      [e['id'] for e in insight_stale],'recommend_refresh_stale_insights')
 elif verified and insight_unavail and not insight_obs:
  add(3,'insights','rec_insights_denied','Insights مرفوضة من المنصة',
      'Meta لم تُرجع المقاييس المطلوبة. هذا غير متاح وليس صفراً.','connectors',
      [e['id'] for e in insight_unavail],'recommend_insights_unavailable')
 conv=next((m for m in metrics if m['id']=='conversion_revenue'),None)
 if conv and conv['status']!='observed':
  add(3,'conversion','rec_conversion','قياس التحويل غير قابل للتحقق بعد',
      'لا يمكن بعد التحقق من قياس التحويل أو الإيراد. هذا لا يعني أن أداء التحويل سيئ.','audit',
      [conv['evidenceIds'][0]] if conv.get('evidenceIds') else ['ev:attribution'],
      'recommend_conversion_unverified')
 candidates.sort(key=lambda item:(item['priority'],item['id']))
 seen=set();out=[]
 for item in candidates:
  if item['family'] in seen: continue
  if verified and item['family']=='connect': continue
  seen.add(item['family']);out.append(item)
  if len(out)==5: break
 for item in out:
  item.pop('family',None)
 return out

def compute_delta(current_metrics, previous_report):
 if not previous_report or not isinstance(previous_report.get('metrics'),list): return None
 prev={m['id']:m for m in previous_report['metrics'] if isinstance(m,dict) and m.get('id')}
 items=[]
 for metric in current_metrics:
  old=prev.get(metric['id'])
  if not old: continue
  cur_status,old_status=metric['status'],old.get('status')
  entry={'metricId':metric['id'],'title':metric['title'],'previous':{'status':old_status,'value':old.get('value'),'unit':old.get('unit'),'period':old.get('period')},
         'current':{'status':cur_status,'value':metric.get('value'),'unit':metric.get('unit'),'period':metric.get('period')},
         'absolute':None,'percent':None,'kind':'unchanged','explanation':''}
  if old_status in ('unknown','unavailable') and cur_status=='observed':
   entry.update(kind='newly_measured',explanation='المقياس أصبح مرصوداً. ليست نسبة نمو.')
  elif old_status=='observed' and cur_status in ('unknown','unavailable'):
   entry.update(kind='measurement_lost',explanation='فُقد القياس أو أصبح غير متاح. ليست تراجعاً في الأداء.')
  elif old_status=='observed' and cur_status=='stale':
   entry.update(kind='became_stale',explanation='القيمة لم تعد ضمن سياسة الحداثة. ليست تراجع أداء.')
  elif old_status=='stale' and cur_status=='observed':
   entry.update(kind='newly_measured',explanation='توفرت قيمة حديثة بعد بيانات قديمة.')
  elif old_status=='observed' and cur_status=='observed':
   if old.get('unit')!=metric.get('unit'):
    entry.update(kind='incompatible',explanation='لا تجوز المقارنة لاختلاف الوحدة.')
   elif not _periods_compatible(old.get('period'),metric.get('period')):
    entry.update(kind='incompatible',explanation='لا تجوز المقارنة لاختلاف النطاق الزمني.')
   elif _number(old.get('value')) and _number(metric.get('value')):
    abs_d=metric['value']-old['value']
    percent=None if old['value']==0 else round(abs_d/old['value']*100,1)
    entry.update(kind='numeric',absolute=abs_d,percent=percent,
                 explanation='مقارنة رقمية بين قيمتين مرصودتين متوافقتين.')
   else:
    entry.update(kind='unchanged' if old.get('value')==metric.get('value') else 'incompatible',
                 explanation='لا توجد قيم رقمية قابلة للمقارنة.' if old.get('value')!=metric.get('value') else 'لا تغيير مرصود.')
  elif old_status==cur_status:
   entry.update(kind='unchanged',explanation='الحالة لم تتغير بشكل قابل للمقارنة.')
  else:
   entry.update(kind='incompatible',explanation='الحالتان غير متوافقتين للمقارنة.')
  items.append(entry)
 return items

def _periods_compatible(a,b):
 if not a and not b: return True
 if not a or not b: return False
 if not isinstance(a,dict) or not isinstance(b,dict): return False
 if a.get('days')!=b.get('days'): return False
 def ts(period,key):
  value=period.get(key)
  return float(value) if _number(value) else _parse_time(value)
 sa,sb,ua,ub=ts(a,'since'),ts(b,'since'),ts(a,'until'),ts(b,'until')
 if None in (sa,sb,ua,ub): return False
 return abs(sa-sb)<=PERIOD_COMPAT_SECONDS and abs(ua-ub)<=PERIOD_COMPAT_SECONDS

def build_sources(workspace):
 assessment=workspace.get('assessment') or {};urls=assessment.get('urls') or {};snapshots=assessment.get('snapshots') or {}
 sources=[]
 for key in ASSESSMENT_SOURCES:
  url=urls.get(key) if isinstance(urls,dict) else ''
  snap=snapshots.get(key) if isinstance(snapshots,dict) else None
  sources.append({'key':key,'label':SOURCE_LABELS.get(key,key),'url':url or '','present':bool(url),
                  'snapshot':snap if isinstance(snap,dict) else None})
 return sources

def sanitize(value):
 if isinstance(value,dict):
  cleaned={}
  for key,item in value.items():
   compact=re.sub(r'[^a-z0-9]','',str(key).lower())
   if compact in SECRET_KEYS or str(key).lower() in SECRET_KEYS: continue
   cleaned[key]=sanitize(item)
  return cleaned
 if isinstance(value,list): return [sanitize(item) for item in value]
 if isinstance(value,str) and SECRET_TOKEN_RE.search(value): return SECRET_TOKEN_RE.sub('[redacted]',value)
 return value

def generate_report(workspace, now=None, previous=None, generated_by=None, run_id=None, created_at=None):
 now=time.time() if now is None else now
 evidence=collect_evidence(workspace, now)
 metrics=evaluate_metrics(workspace, evidence, now)
 level=derive_level(evidence, workspace)
 scores=score_metrics(metrics)
 layers=build_layers(evidence, workspace, level)
 recs=recommend(evidence, metrics, workspace)
 sources=build_sources(workspace)
 client=workspace.get('client') or {}
 connections=_list(workspace.get('connections'))
 accounts=_list(workspace.get('accounts'))
 connected=[c for c in connections if c.get('status')=='identity_verified' and any(a.get('id')==c.get('account_id') for a in accounts)]
 expired=[c for c in connections if c.get('status')=='expired' and any(a.get('id')==c.get('account_id') for a in accounts)]
 present=[s for s in sources if s['present']]
 inspected=[s for s in sources if isinstance(s.get('snapshot'),dict) and s['snapshot'].get('status')=='available']
 created=created_at or timestamp()
 report={
  'id':run_id or uid(),'clientId':client.get('id'),'schemaVersion':SCHEMA_VERSION,'level':level,
  'createdAt':created,'generatedBy':generated_by or {},'generatedAt':_iso(now),
  'scores':{'coverageScore':scores['coverage'],'confidenceScore':scores['confidence'],
            'performanceScore':scores['performance'],'performanceExplanation':scores['performanceExplanation'],
            'sectionScores':scores['sectionScores']},
  'coverage':scores['coverage'],'known':scores['counts']['observed'],'inferred':scores['counts']['inferred'],
  'unknown':scores['counts']['unknown'],'unavailable':scores['counts']['unavailable'],'stale':scores['counts']['stale'],
  'evidence':evidence,'metrics':metrics,'layers':layers,'recommendations':recs,'sources':sources,
  'present':present,'inspected':inspected,'connected':[{k:c.get(k) for k in ('account_id','client_id','platform','status','page_id','page_name','ig_user_id','username','expires','verified_at') if k in c or c.get(k) is not None} for c in connected],
  'expired':[{k:c.get(k) for k in ('account_id','client_id','platform','status','expires') if k in c or c.get(k) is not None} for c in expired],
  'delta':compute_delta(metrics, previous),'previousAuditId':(previous or {}).get('id'),
  'observedAt':((workspace.get('assessment') or {}).get('snapshots') or {}).get('observedAt') or '',
  'accounts':[{'id':a.get('id'),'platform':a.get('platform'),'externalId':a.get('externalId')} for a in accounts if isinstance(a,dict)]
 }
 return sanitize(report)

def _row_connections(db, client_id, now):
 rows=[]
 for table,platform,extra in (('page_connections','Facebook',()),('instagram_connections','Instagram',('ig_user_id','username'))):
  cols='account_id,client_id,page_id,'+('ig_user_id,username,' if extra else 'page_name,')+'version,expires,verified_at'
  for row in db.execute(f'SELECT {cols} FROM {table} WHERE client_id=?',(client_id,)):
   item=dict(row);item['platform']=platform
   item['status']='identity_verified' if item['expires']>now else 'expired'
   rows.append(item)
 return rows

def load_workspace(store, db, user, client_id, now=None):
 now=time.time() if now is None else now
 store.require(user, client_id)
 client=store.entity(db, client_id, 'clients')
 groups={k:[] for k in ('accounts','posts','leads','campaigns','media','insights','assessments')}
 for row in db.execute('SELECT kind,data FROM entities WHERE client_id=?',(client_id,)):
  if row['kind'] in groups: groups[row['kind']].append(json.loads(row['data']))
 jobs=[]
 for row in db.execute('SELECT * FROM dispatch_jobs WHERE client_id=?',(client_id,)):
  item=dict(row);item.update(postId=row['post_id'],accountId=row['account_id'],clientId=row['client_id']);jobs.append(item)
 assessment=sorted(groups['assessments'], key=lambda item: item.get('updatedAt') or '')[-1] if groups['assessments'] else None
 return {'client':client,'assessment':assessment,'accounts':groups['accounts'],'posts':groups['posts'],
         'leads':groups['leads'],'campaigns':groups['campaigns'],'media':groups['media'],'insights':groups['insights'],
         'jobs':jobs,'connections':_row_connections(db, client_id, now),'attributionEvidence':None}

def _latest_runs(db, client_id, limit=50):
 rows=db.execute('SELECT id,created_at,generated_by,report FROM audit_runs WHERE client_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?',(client_id,limit)).fetchall()
 out=[]
 for row in rows:
  try: report=json.loads(row['report'])
  except (TypeError,ValueError): report={}
  out.append({'id':row['id'],'createdAt':row['created_at'],'generatedBy':row['generated_by'],'report':report})
 return out

def persist_from_db(store, db, user, client_id, now=None):
 now=time.time() if now is None else now
 ensure_schema(db)
 workspace=load_workspace(store, db, user, client_id, now)
 previous=(_latest_runs(db, client_id, 1) or [{}])[0].get('report')
 run_id=uid();created=timestamp()
 report=generate_report(workspace, now, previous, {'id':user.get('id'),'name':user.get('name')}, run_id, created)
 db.execute('INSERT INTO audit_runs VALUES(?,?,?,?,?)',(run_id,client_id,created,user.get('id') or '',json.dumps(report,ensure_ascii=False)))
 return report

def _require_client(store, user, client_id):
 if not isinstance(client_id,str) or not client_id: raise Problem('معرف العميل غير صالح')
 store.require(user, client_id)
 with store.db() as db: store.entity(db, client_id, 'clients')
 return client_id

def _serialize_pair(store, user, client_id):
 with store.db() as db:
  ensure_schema(db)
  runs=_latest_runs(db, client_id, 2)
 current=runs[0]['report'] if runs else None
 previous=runs[1]['report'] if len(runs)>1 else None
 return sanitize({'current':current,'previous':previous})

def get_current(store, user, client_id):
 client_id=_require_client(store, user, client_id)
 return _serialize_pair(store, user, client_id)

def get_history(store, user, client_id):
 client_id=_require_client(store, user, client_id)
 with store.db() as db:
  ensure_schema(db)
  runs=_latest_runs(db, client_id, 100)
 items=[]
 for run in runs:
  report=run['report'] or {}
  scores=report.get('scores') or {}
  items.append({'id':run['id'],'createdAt':run['createdAt'],'level':report.get('level'),
                'coverageScore':scores.get('coverageScore'),'confidenceScore':scores.get('confidenceScore'),
                'performanceScore':scores.get('performanceScore'),'generatedBy':report.get('generatedBy')})
 return sanitize({'items':items})

def run_audit(store, user, client_id, now=None):
 if user.get('role')=='viewer': raise Problem('الحساب للقراءة فقط',403)
 if user.get('role')=='reviewer': raise Problem('الحساب مخصص للمراجعة والاعتماد',403)
 client_id=_require_client(store, user, client_id)
 now=time.time() if now is None else now
 with store.db() as db:
  db.execute('BEGIN IMMEDIATE');ensure_schema(db)
  report=persist_from_db(store, db, user, client_id, now)
  store.put(db,'audit',{'id':uid(),'clientId':client_id,'action':'audit-run','entityId':report['id'],'actor':user.get('name'),'at':timestamp()})
  db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
 return _serialize_pair(store, user, client_id)

def client_id_from_query(env):
 raw=(parse_qs(env.get('QUERY_STRING',''), keep_blank_values=True).get('clientId') or [None])[0]
 return raw
