"""Read-only Meta Insights snapshots. Tokens never leave the server."""
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from server.core import Problem,timestamp,uid
from server.facebook import graph,key

METRICS={
 'Facebook':[
  ('page_impressions','impressions','sum'),
  ('page_post_engagements','engagements','sum'),
  ('page_fans','followers','latest'),
  ('page_video_views','videoViews','sum')
 ],
 'Instagram':[
  ('reach','reach','sum'),
  ('profile_views','profileViews','sum'),
  ('website_clicks','websiteClicks','sum'),
  ('total_interactions','engagements','sum')
 ]
}

def _number(value):
 return isinstance(value,(int,float)) and not isinstance(value,bool)

def normalize(result,aggregation='sum'):
 data=result.get('data') if isinstance(result,dict) else None
 if not isinstance(data,list) or not data or not isinstance(data[0],dict):return None
 item=data[0]
 total=item.get('total_value',{}).get('value') if isinstance(item.get('total_value'),dict) else None
 if _number(total):return {'value':total,'points':1,'aggregation':'provider_total'}
 values=item.get('values')
 if not isinstance(values,list):return None
 points=[]
 for point in values:
  if isinstance(point,dict) and _number(point.get('value')):points.append({'value':point['value'],'at':point.get('end_time','')})
 if not points:return None
 value=points[-1]['value'] if aggregation=='latest' else sum(point['value'] for point in points)
 return {'value':value,'points':len(points),'aggregation':aggregation,'from':points[0]['at'],'to':points[-1]['at']}

def _connection(store,account):
 table='page_connections' if account['platform']=='Facebook' else 'instagram_connections'
 with store.db() as db:row=db.execute(f'SELECT * FROM {table} WHERE account_id=? AND client_id=?',(account['id'],account['clientId'])).fetchone()
 return dict(row) if row else None

def _token(account,connection):
 label=account['platform'].lower()
 try:return AESGCM(key()).decrypt(connection['cipher'][:12],connection['cipher'][12:],(label+':'+account['clientId']+':'+account['id']).encode()).decode()
 except Exception:raise Problem('تعذر فتح تفويض الحساب؛ أعد ربطه',400) from None

def sync_account(store,user,p,transport=graph,now=None):
 if user['role']!='admin':raise Problem('مزامنة Insights تحتاج صلاحية مدير',403)
 account_id=p.get('accountId') if isinstance(p,dict) else None
 if not isinstance(account_id,str):raise Problem('معرف الحساب غير صالح')
 now=time.time() if now is None else now
 with store.db() as db:
  account=store.entity(db,account_id,'accounts');store.require(user,account['clientId'])
 if account['platform'] not in METRICS:raise Problem('Insights متاحة حاليًا لحسابات Facebook وInstagram فقط')
 connection=_connection(store,account)
 if not connection or connection['expires']<=now:raise Problem('اربط الحساب بتفويض صالح قبل مزامنة Insights')
 token=_token(account,connection);until=int(now);since=until-28*86400
 target=connection['page_id'] if account['platform']=='Facebook' else connection['ig_user_id']
 metric_results={};unavailable=[]
 def fetch(definition):
  provider,name,aggregation=definition
  params={'metric':provider,'period':'day','since':since,'until':until}
  if account['platform']=='Instagram':params['metric_type']='total_value'
  try:return name,normalize(transport('GET',target+'/insights',token,connection['version'],params),aggregation)
  except Exception:return name,None
 with ThreadPoolExecutor(max_workers=min(4,len(METRICS[account['platform']])),thread_name_prefix='meta-insights') as pool:
  futures={pool.submit(fetch,item):item for item in METRICS[account['platform']]}
  for future in as_completed(futures):
   name,value=future.result()
   if value is None:unavailable.append(name)
   else:metric_results[name]=value
 snapshot={
  'id':'insights-'+account_id,'clientId':account['clientId'],'accountId':account_id,
  'platform':account['platform'],'status':'available' if metric_results and not unavailable else 'partial' if metric_results else 'unavailable',
  'range':{'since':since,'until':until,'days':28},'metrics':metric_results,'unavailable':sorted(unavailable),
  'syncedAt':timestamp(),'source':'Meta Graph API'
 }
 with store.db() as db:
  db.execute('BEGIN IMMEDIATE');store.put(db,'insights',snapshot)
  store.put(db,'audit',{'id':uid(),'clientId':account['clientId'],'action':'insights-sync','entityId':account_id,'actor':user['name'],'at':timestamp()})
  db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
 return store.state(user)
