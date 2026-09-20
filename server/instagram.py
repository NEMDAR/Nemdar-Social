"""Opt-in Instagram Professional single-image publishing through Meta Graph API."""
import hashlib,hmac,os,re,time
from urllib.parse import parse_qs
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from server.core import Problem,uid,timestamp
from server.dispatch import NotSent,Uncertain
from server.facebook import graph,key

def schema(db):
 db.execute('''CREATE TABLE IF NOT EXISTS instagram_connections(account_id TEXT PRIMARY KEY,client_id TEXT NOT NULL,page_id TEXT NOT NULL,ig_user_id TEXT NOT NULL,username TEXT NOT NULL,version TEXT NOT NULL,cipher BLOB NOT NULL,expires REAL NOT NULL,verified_at TEXT NOT NULL)''')

def metadata(store,user):
 with store.db() as db:rows=db.execute('SELECT account_id,client_id,page_id,ig_user_id,username,version,expires,verified_at FROM instagram_connections').fetchall()
 return [{**dict(r),'platform':'Instagram','status':'identity_verified' if r['expires']>time.time() else 'expired'} for r in rows if store.allowed(user,r['client_id'])]

def connect(store,user,p,transport=graph):
 if user['role']!='admin':raise Problem('الإجراء يحتاج صلاحية مدير',403)
 account_id=p.get('accountId');token=p.get('token');page=p.get('pageId');version=p.get('version')
 if not isinstance(account_id,str) or not isinstance(page,str) or not re.fullmatch(r'[0-9]{1,40}',page):raise Problem('أدخل معرّف صفحة Facebook المرتبطة بالحساب')
 if not isinstance(token,str) or not 10<=len(token)<=16000 or any(c.isspace() for c in token):raise Problem('Page Access Token غير صالح')
 if not isinstance(version,str) or not re.fullmatch(r'v[0-9]{1,2}\.0',version):raise Problem('أدخل إصدار Graph API من تطبيق Meta مثل vXX.0')
 try:expires=float(p.get('expires'))
 except (ValueError,TypeError):raise Problem('حدد تاريخ انتهاء التفويض')
 if not time.time()<expires<time.time()+366*86400:raise Problem('حدد انتهاء صلاحية مستقبلي خلال سنة، لا يتجاوز صلاحية التوكن')
 encryption_key=key()
 with store.db() as db:
  account=store.entity(db,account_id,'accounts');store.require(user,account['clientId'])
  if account['platform']!='Instagram':raise Problem('هذا الموصل لحسابات Instagram فقط')
 try:identity=transport('GET',page,token,version,{'fields':'id,name,instagram_business_account{id,username}'})
 except Exception:raise Problem('تعذر التحقق من صفحة Facebook وحساب Instagram المرتبط بها',400) from None
 ig=identity.get('instagram_business_account')
 if identity.get('id')!=page or not isinstance(ig,dict) or not re.fullmatch(r'[0-9]{1,40}',str(ig.get('id',''))):raise Problem('لم نجد حساب Instagram Professional مرتبطاً بهذه الصفحة')
 username=ig.get('username') or account['externalId'];cid=account['clientId'];nonce=os.urandom(12)
 cipher=nonce+AESGCM(encryption_key).encrypt(nonce,token.encode(),('instagram:'+cid+':'+account_id).encode())
 with store.db() as db:
  db.execute('BEGIN IMMEDIATE')
  if db.execute("SELECT 1 FROM dispatch_jobs WHERE account_id=? AND state='sending'",(account_id,)).fetchone():raise Problem('انتظر انتهاء الإرسال قبل تغيير التفويض',409)
  db.execute('INSERT OR REPLACE INTO instagram_connections VALUES(?,?,?,?,?,?,?,?,?)',(account_id,cid,page,str(ig['id']),str(username)[:200],version,cipher,expires,timestamp()))
  store.put(db,'audit',{'id':uid(),'clientId':cid,'action':'instagram-connect','entityId':account_id,'actor':user['name'],'at':timestamp()});db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
 return store.state(user)

def disconnect(store,user,account_id):
 if user['role']!='admin':raise Problem('الإجراء يحتاج صلاحية مدير',403)
 with store.db() as db:
  db.execute('BEGIN IMMEDIATE');account=store.entity(db,account_id,'accounts');store.require(user,account['clientId'])
  if db.execute("SELECT 1 FROM dispatch_jobs WHERE account_id=? AND state='sending'",(account_id,)).fetchone():raise Problem('انتظر انتهاء الإرسال قبل فصل الحساب',409)
  db.execute('DELETE FROM instagram_connections WHERE account_id=?',(account_id,))
  store.put(db,'audit',{'id':uid(),'clientId':account['clientId'],'action':'instagram-disconnect','entityId':account_id,'actor':user['name'],'at':timestamp()});db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
 return store.state(user)

def signed_media_url(media_id,ttl=600):
 exp=int(time.time()+ttl);message=f'{media_id}:{exp}'.encode();signature=hmac.new(key(),b'instagram-media:'+message,hashlib.sha256).hexdigest()
 origin=os.environ.get('APP_ORIGIN','').rstrip('/')
 if not origin.startswith('https://'):raise Problem('رابط التطبيق العام HTTPS مطلوب لنشر Instagram',503)
 return f'{origin}/api/public-media/{media_id}?exp={exp}&sig={signature}'

def public_media(store,media_id,query):
 values=parse_qs(query,keep_blank_values=True)
 try:exp=int(values.get('exp',[''])[0]);supplied=values.get('sig',[''])[0]
 except (ValueError,TypeError):raise Problem('رابط الوسائط غير صالح',403)
 if exp<time.time() or exp>time.time()+900:raise Problem('رابط الوسائط منتهي أو غير صالح',403)
 expected=hmac.new(key(),b'instagram-media:'+f'{media_id}:{exp}'.encode(),hashlib.sha256).hexdigest()
 if not isinstance(supplied,str) or not hmac.compare_digest(supplied,expected):raise Problem('رابط الوسائط غير صالح',403)
 with store.db() as db:
  media=store.entity(db,media_id,'media')
  if media['mime'] not in ('image/jpeg','image/png'):raise Problem('صيغة الوسائط غير مدعومة',404)
  row=db.execute('SELECT data,mime FROM blobs WHERE id=?',(media_id,)).fetchone()
  if not row:raise Problem('الملف غير موجود',404)
 return row['data'],row['mime']

class InstagramProfessional:
 def __init__(self,store,transport=graph,url_factory=signed_media_url):self.store,self.transport,self.url_factory=store,transport,url_factory
 def connection(self,account):
  with self.store.db() as db:row=db.execute('SELECT * FROM instagram_connections WHERE account_id=? AND client_id=?',(account['id'],account['clientId'])).fetchone()
  return dict(row) if row else None
 def ready(self,account):
  c=self.connection(account)
  try:key()
  except Problem:return False
  return bool(c and c['expires']>time.time())
 def publish(self,post,account,idempotency_key):
  media_ids=post.get('mediaIds') or []
  if len(media_ids)!=1:raise NotSent()
  c=self.connection(account)
  if not c or c['expires']<=time.time():raise NotSent()
  with self.store.db() as db:
   media=self.store.entity(db,media_ids[0],'media')
   if media['clientId']!=account['clientId'] or media['mime'] not in ('image/jpeg','image/png'):raise NotSent()
  try:token=AESGCM(key()).decrypt(c['cipher'][:12],c['cipher'][12:],('instagram:'+account['clientId']+':'+account['id']).encode()).decode()
  except Exception:raise NotSent() from None
  container=self.transport('POST',c['ig_user_id']+'/media',token,c['version'],{'image_url':self.url_factory(media['id']),'caption':post.get('body','')})
  creation_id=container.get('id')
  if not isinstance(creation_id,str) or not re.fullmatch(r'[0-9]+',creation_id):raise Uncertain()
  result=self.transport('POST',c['ig_user_id']+'/media_publish',token,c['version'],{'creation_id':creation_id})
  receipt=result.get('id')
  if not isinstance(receipt,str) or not re.fullmatch(r'[0-9]+',receipt):raise Uncertain()
  return receipt

def send_target(store,user,p):
 if user['role']!='admin':raise Problem('الإرسال الفعلي يحتاج مديراً',403)
 job_id=p.get('jobId')
 if not isinstance(job_id,str) or p.get('confirm') is not True:raise Problem('أكد إرسال هذا الهدف')
 with store.db() as db:
  job=db.execute('SELECT * FROM dispatch_jobs WHERE id=?',(job_id,)).fetchone()
  if not job:raise Problem('المهمة غير موجودة',404)
  store.require(user,job['client_id']);account=store.entity(db,job['account_id'],'accounts');post=store.entity(db,job['post_id'],'posts')
  if account['platform']!='Instagram':raise Problem('الإرسال متاح لحساب Instagram المرتبط فقط')
  media_ids=post.get('mediaIds') or []
  if len(media_ids)!=1:raise Problem('نشر Instagram الحالي يحتاج صورة JPEG أو PNG واحدة بالضبط')
  media=store.entity(db,media_ids[0],'media')
  if media['clientId']!=job['client_id']:raise Problem('الملف يتبع عميلاً آخر',403)
  if media['mime'] not in ('image/jpeg','image/png'):raise Problem('نشر Instagram الحالي يدعم صورة JPEG أو PNG واحدة؛ الفيديو وWebP غير مفعّلين')
  if job['due']>time.time():raise Problem('موعد النشر لم يحن بعد')
  if job['state'] not in ('queued','blocked'):raise Problem('المهمة ليست جاهزة؛ لا يُعاد إرسال الناجح أو غير المؤكد')
 adapter=InstagramProfessional(store)
 if not adapter.ready(account):raise Problem('اربط حساب Instagram Professional بتفويض صالح أولاً')
 from server.dispatch import Dispatcher
 if not Dispatcher(store,{'Instagram':adapter},actor=user['name']).run_one(job_id=job_id):raise Problem('تغيرت حالة المهمة؛ حدّث الصفحة',409)
 return store.state(user)
