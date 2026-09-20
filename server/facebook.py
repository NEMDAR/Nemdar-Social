"""Opt-in Facebook Page publishing. No credentials or responses are logged."""
import json,os,re,time,secrets
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlencode
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from server.core import Problem,uid,timestamp
from server.dispatch import NotSent,Uncertain

class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def graph(method,path,token,version,params):
 if not re.fullmatch(r'v[0-9]{1,2}\.0',version):raise Problem('إصدار Graph API غير صالح')
 url='https://graph.facebook.com/'+version+'/'+path
 data=urlencode(params).encode() if method=='POST' else None
 if method=='GET':url+='?'+urlencode(params)
 request=Request(url,data=data,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':'application/x-www-form-urlencoded'})
 try:
  with build_opener(NoRedirect()).open(request,timeout=20) as response:
   result=json.loads(response.read(1024*1024))
 except HTTPError as error:
  # Only explicit provider validation/auth refusals are safe to retry.
  try:code=json.loads(error.read(65536)).get('error',{}).get('code')
  except Exception:code=None
  if error.code in (400,401,403) and code in (10,100,190,200):raise NotSent() from None
  raise Uncertain() from None
 except Exception:raise Uncertain() from None
 if not isinstance(result,dict) or 'error' in result:raise Uncertain()
 return result

def graph_photo(path,token,version,fields,filename,mime,data):
 if not re.fullmatch(r'v[0-9]{1,2}\.0',version):raise Problem('إصدار Graph API غير صالح')
 if mime not in ('image/jpeg','image/png') or not data:raise NotSent()
 boundary='----nemdar-'+secrets.token_hex(16)
 parts=[]
 for name,value in fields.items():
  parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode())
 safe_name=re.sub(r'[^A-Za-z0-9._-]','_',filename)[:120] or 'image'
 parts.extend([(f'--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="{safe_name}"\r\nContent-Type: {mime}\r\n\r\n').encode(),data,f'\r\n--{boundary}--\r\n'.encode()])
 request=Request('https://graph.facebook.com/'+version+'/'+path,data=b''.join(parts),method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'multipart/form-data; boundary='+boundary})
 try:
  with build_opener(NoRedirect()).open(request,timeout=30) as response:result=json.loads(response.read(1024*1024))
 except HTTPError as error:
  try:code=json.loads(error.read(65536)).get('error',{}).get('code')
  except Exception:code=None
  if error.code in (400,401,403) and code in (10,100,190,200):raise NotSent() from None
  raise Uncertain() from None
 except Exception:raise Uncertain() from None
 if not isinstance(result,dict) or 'error' in result:raise Uncertain()
 return result

def key():
 try:value=bytes.fromhex(os.environ.get('VAULT_KEY',''))
 except ValueError:raise Problem('إعداد مفتاح الخزنة غير صحيح',503)
 if len(value)!=32:raise Problem('الخزنة غير مهيأة على الخادم',503)
 return value

def schema(db):
 db.execute('''CREATE TABLE IF NOT EXISTS page_connections(account_id TEXT PRIMARY KEY,client_id TEXT NOT NULL,page_id TEXT NOT NULL,page_name TEXT NOT NULL,version TEXT NOT NULL,cipher BLOB NOT NULL,expires REAL NOT NULL,verified_at TEXT NOT NULL)''')

def metadata(store,user):
 with store.db() as db:
  rows=db.execute('SELECT account_id,client_id,page_id,page_name,version,expires,verified_at FROM page_connections').fetchall()
 return [{**dict(r),'status':'identity_verified' if r['expires']>time.time() else 'expired'} for r in rows if store.allowed(user,r['client_id'])]

def connect(store,user,p,transport=graph):
 if user['role']!='admin':raise Problem('الإجراء يحتاج صلاحية مدير',403)
 account_id=p.get('accountId');token=p.get('token');page=p.get('pageId');version=p.get('version')
 if not isinstance(account_id,str) or not isinstance(page,str) or not re.fullmatch(r'[0-9]{1,40}',page):raise Problem('أدخل معرّف صفحة رقمي صحيح')
 if not isinstance(token,str) or not 10<=len(token)<=16000 or any(c.isspace() for c in token):raise Problem('توكن الصفحة غير صالح')
 if not isinstance(version,str) or not re.fullmatch(r'v[0-9]{1,2}\.0',version):raise Problem('أدخل إصدار Graph API من تطبيق Meta مثل vXX.0')
 try:expires=float(p.get('expires'))
 except (ValueError,TypeError):raise Problem('حدد تاريخ انتهاء التفويض')
 if not time.time()<expires<time.time()+366*86400:raise Problem('حدد انتهاء صلاحية مستقبلي خلال سنة، لا يتجاوز صلاحية التوكن')
 encryption_key=key()
 with store.db() as db:
  account=store.entity(db,account_id,'accounts');store.require(user,account['clientId'])
  if account['platform']!='Facebook':raise Problem('هذا الموصل لصفحات فيسبوك فقط')
 try:identity=transport('GET','me',token,version,{'fields':'id,name,category'})
 except Exception:raise Problem('تعذر التحقق من توكن الصفحة. راجع الصلاحية وإصدار API ثم حاول مجدداً',400) from None
 if identity.get('id')!=page or not identity.get('category'):raise Problem('التوكن لا يخص الصفحة المحددة؛ استخدم Page Access Token')
 name=identity.get('name','')
 if not isinstance(name,str):raise Problem('استجابة الصفحة غير صحيحة')
 cid=account['clientId'];nonce=os.urandom(12);cipher=nonce+AESGCM(encryption_key).encrypt(nonce,token.encode(),('facebook:'+cid+':'+account_id).encode())
 with store.db() as db:
  db.execute('BEGIN IMMEDIATE')
  if db.execute("SELECT 1 FROM dispatch_jobs WHERE account_id=? AND state='sending'",(account_id,)).fetchone():raise Problem('انتظر انتهاء الإرسال قبل تغيير التفويض',409)
  db.execute('INSERT OR REPLACE INTO page_connections VALUES(?,?,?,?,?,?,?,?)',(account_id,cid,page,name[:200],version,cipher,expires,timestamp()))
  store.put(db,'audit',{'id':uid(),'clientId':cid,'action':'facebook-connect','entityId':account_id,'actor':user['name'],'at':timestamp()})
  db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
 return store.state(user)

def disconnect(store,user,account_id):
 if user['role']!='admin':raise Problem('الإجراء يحتاج صلاحية مدير',403)
 if not isinstance(account_id,str):raise Problem('معرف غير صالح')
 with store.db() as db:
  db.execute('BEGIN IMMEDIATE');account=store.entity(db,account_id,'accounts');store.require(user,account['clientId'])
  if db.execute("SELECT 1 FROM dispatch_jobs WHERE account_id=? AND state='sending'",(account_id,)).fetchone():raise Problem('انتظر انتهاء الإرسال قبل فصل الحساب',409)
  db.execute('DELETE FROM page_connections WHERE account_id=?',(account_id,))
  store.put(db,'audit',{'id':uid(),'clientId':account['clientId'],'action':'facebook-disconnect','entityId':account_id,'actor':user['name'],'at':timestamp()});db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
 return store.state(user)

class FacebookPages:
 def __init__(self,store,transport=graph,photo_transport=graph_photo):self.store,self.transport,self.photo_transport=store,transport,photo_transport
 def connection(self,account):
  with self.store.db() as db:row=db.execute('SELECT * FROM page_connections WHERE account_id=? AND client_id=?',(account['id'],account['clientId'])).fetchone()
  return dict(row) if row else None
 def ready(self,account):
  c=self.connection(account)
  try:key()
  except Problem:return False
  return bool(c and c['expires']>time.time())
 def publish(self,post,account,idempotency_key):
  # Graph publishing has no assumed idempotency support. Ambiguous outcomes never retry.
  media_ids=post.get('mediaIds') or []
  if len(media_ids)>1 or not post.get('body','').strip():raise NotSent()
  c=self.connection(account)
  if not c or c['expires']<=time.time():raise NotSent()
  try:token=AESGCM(key()).decrypt(c['cipher'][:12],c['cipher'][12:],('facebook:'+account['clientId']+':'+account['id']).encode()).decode()
  except Exception:raise NotSent() from None
  if media_ids:
   with self.store.db() as db:
    media=self.store.entity(db,media_ids[0],'media')
    if media['clientId']!=account['clientId'] or media['mime'] not in ('image/jpeg','image/png'):raise NotSent()
    row=db.execute('SELECT data,mime FROM blobs WHERE id=?',(media['id'],)).fetchone()
    if not row:raise NotSent()
    data,mime=row['data'],row['mime']
   result=self.photo_transport(c['page_id']+'/photos',token,c['version'],{'message':post['body']},media['name'],mime,data)
   receipt=result.get('post_id') or result.get('id')
  else:
   result=self.transport('POST',c['page_id']+'/feed',token,c['version'],{'message':post['body']})
   receipt=result.get('id')
  if not isinstance(receipt,str) or not re.fullmatch(r'[0-9]+(?:_[0-9]+)?',receipt):raise Uncertain()
  return receipt

def send_target(store,user,p):
 if user['role']!='admin':raise Problem('الإرسال الفعلي يحتاج مديراً',403)
 job_id=p.get('jobId')
 if not isinstance(job_id,str) or p.get('confirm') is not True:raise Problem('أكد إرسال هذا الهدف')
 with store.db() as db:
  job=db.execute('SELECT * FROM dispatch_jobs WHERE id=?',(job_id,)).fetchone()
  if not job:raise Problem('المهمة غير موجودة',404)
  store.require(user,job['client_id']);account=store.entity(db,job['account_id'],'accounts');post=store.entity(db,job['post_id'],'posts')
  if account['platform']!='Facebook':raise Problem('الإرسال متاح لصفحات فيسبوك فقط')
  media_ids=post.get('mediaIds') or []
  if len(media_ids)>1:raise Problem('نشر Facebook الحالي يدعم صورة واحدة فقط لكل منشور')
  if media_ids:
   media=store.entity(db,media_ids[0],'media')
   if media['clientId']!=job['client_id']:raise Problem('الملف يتبع عميلاً آخر',403)
   if media['mime'] not in ('image/jpeg','image/png'):raise Problem('نشر Facebook الحالي يدعم صورة JPEG أو PNG واحدة؛ الفيديو وWebP غير مفعّلين')
  if job['due']>time.time():raise Problem('موعد النشر لم يحن بعد')
  if job['state'] not in ('queued','blocked'):raise Problem('المهمة ليست جاهزة؛ لا يُعاد إرسال الناجح أو غير المؤكد')
 adapter=FacebookPages(store)
 if not adapter.ready(account):raise Problem('اربط الصفحة بتفويض صالح أولاً')
 from server.dispatch import Dispatcher
 if not Dispatcher(store,{'Facebook':adapter},actor=user['name']).run_one(job_id=job_id):raise Problem('تغيرت حالة المهمة؛ حدّث الصفحة',409)
 return store.state(user)
