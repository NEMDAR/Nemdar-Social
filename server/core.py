"""Transactional single-agency workspace. Authorization is enforced server-side."""
import base64, hashlib, hmac, json, os, secrets, sqlite3, time, uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

PLATFORMS=['Facebook','Instagram','WhatsApp Business','Threads','YouTube','LinkedIn','Pinterest','TikTok','X','Google Business Profile']
COLLECTIONS=['clients','brands','accounts','posts','leads','campaigns','media','audit','secrets']
ROLES=['admin','editor','reviewer','viewer']
class Problem(Exception):
 def __init__(self,message,status=400): self.message,self.status=message,status

def text(p,k,limit=200,optional=False):
 v=p.get(k,'')
 if not isinstance(v,str) or len(v)>limit or (not optional and not v.strip()): raise Problem('بيانات غير صالحة: '+k)
 return v.strip()
def timestamp(): return datetime.now(timezone.utc).isoformat()
def uid(): return uuid.uuid4().hex
def password_hash(password,salt=None):
 if not isinstance(password,str) or not 12<=len(password)<=256: raise Problem('كلمة المرور يجب أن تكون من 12 إلى 256 حرفاً')
 salt=salt or secrets.token_hex(16)
 digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=2**17,r=8,p=1,maxmem=256*1024*1024).hex()
 return salt+':'+digest
def password_valid(password,stored):
 try: return hmac.compare_digest(password_hash(password,stored.split(':')[0]),stored)
 except (Problem,ValueError): return False

class Store:
 def __init__(self,path):
  self.path=str(path);Path(path).parent.mkdir(parents=True,exist_ok=True)
  with self.db() as db:
   db.executescript('''PRAGMA journal_mode=WAL;
   CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,clients TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
   CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
   CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY,kind TEXT NOT NULL,client_id TEXT NOT NULL,data TEXT NOT NULL);
   CREATE INDEX IF NOT EXISTS scope_idx ON entities(kind,client_id);
   CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value INTEGER NOT NULL);
   INSERT OR IGNORE INTO meta VALUES('revision',0);
   CREATE TABLE IF NOT EXISTS blobs(id TEXT PRIMARY KEY,data BLOB NOT NULL,mime TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS vault(id TEXT PRIMARY KEY,cipher BLOB NOT NULL);
   CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,until REAL NOT NULL);
   ''')
   from server.facebook import schema
   schema(db)
   from server.dispatch import ensure_schema
   ensure_schema(db)
   from server.dispatch import enqueue
   for row in db.execute("SELECT data FROM entities WHERE kind='posts' AND id NOT IN (SELECT post_id FROM dispatch_jobs)").fetchall():
    post=json.loads(row[0])
    if post.get('status')=='scheduled':enqueue(db,post)
 @contextmanager
 def db(self):
  db=sqlite3.connect(self.path,timeout=20);db.row_factory=sqlite3.Row
  try:
   yield db
   db.commit()
  except Exception:
   db.rollback();raise
  finally:db.close()
 def setup(self,email,password,name='Administrator'):
  hashed=password_hash(password)
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT 1 FROM users').fetchone(): raise Problem('الحساب الإداري موجود بالفعل')
   db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',(uid(),email.strip().lower(),name,hashed,'admin','[]'))
 def login(self,email,password,ip):
  key=hashlib.sha256((ip+'|'+email.lower()).encode()).hexdigest();now=time.time()
  with self.db() as db:
   attempt=db.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
   if attempt and attempt['until']>now and attempt['count']>=8: raise Problem('محاولات كثيرة؛ حاول بعد 15 دقيقة',429)
   user=db.execute('SELECT * FROM users WHERE email=? AND active=1',(email.strip().lower(),)).fetchone()
   # Use a real KDF even for an unknown account to reduce enumeration by timing.
   stored=user['password'] if user else '00'*16+':'+'00'*64
   if not password_valid(password,stored):
    count=attempt['count']+1 if attempt and attempt['until']>now else 1
    db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(key,count,now+900));db.commit()
    raise Problem('البريد أو كلمة المرور غير صحيحة',401)
   db.execute('DELETE FROM attempts WHERE key=?',(key,));db.execute('DELETE FROM sessions WHERE expires<?',(now,))
   token=secrets.token_urlsafe(40);csrf=secrets.token_urlsafe(32)
   db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],csrf,now+28800))
   return token,csrf
 def session(self,token):
  with self.db() as db:
   row=db.execute('SELECT users.*,sessions.csrf FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>? AND active=1',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
   if not row: raise Problem('سجّل الدخول للمتابعة',401)
   return dict(row)
 def logout(self,token):
  with self.db() as db: db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
 def allowed(self,user,client_id): return user['role']=='admin' or client_id in json.loads(user['clients'])
 def require(self,user,client_id):
  if not self.allowed(user,client_id): raise Problem('غير مصرح بالوصول لهذا العميل',403)
 def entity(self,db,id,kind=None):
  row=db.execute('SELECT * FROM entities WHERE id=?',(id,)).fetchone()
  if not row or (kind and row['kind']!=kind): raise Problem('العنصر غير موجود',404)
  return json.loads(row['data'])
 def put(self,db,kind,obj): db.execute('INSERT OR REPLACE INTO entities VALUES(?,?,?,?)',(obj['id'],kind,obj.get('clientId',obj['id']),json.dumps(obj,ensure_ascii=False)))
 def state(self,user):
  result={k:[] for k in COLLECTIONS}
  with self.db() as db:
   result['revision']=db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
   for row in db.execute('SELECT * FROM entities ORDER BY rowid'):
    if self.allowed(user,row['client_id']):
     if row['kind']=='secrets' and user['role']!='admin': continue
     result[row['kind']].append(json.loads(row['data']))
   from server.dispatch import jobs_for
   result['jobs']=jobs_for(db,self,user)
   result['audit'].reverse()
   result['users']=[{k:r[k] for k in ['id','email','name','role','clients','active']} for r in db.execute('SELECT * FROM users')] if user['role']=='admin' else []
  result['user']={k:user[k] for k in ['id','email','name','role']}
  from server.facebook import metadata
  result['connections']=metadata(self,user)
  result['csrf']=user.get('csrf','');result['version']=5
  return result
 def mutate(self,user,action,p,revision):
  if not isinstance(action,str) or any(not isinstance(p.get(k,''),str) for k in ['id','clientId']):raise Problem('معرف غير صالح')
  if user['role']=='viewer': raise Problem('الحساب للقراءة فقط',403)
  admin_actions=['client','user','disable-user','secret','delete-secret']
  if action in admin_actions and user['role']!='admin': raise Problem('الإجراء يحتاج صلاحية مدير',403)
  if action in ['approve','campaign-approve'] and user['role'] not in ['admin','reviewer']: raise Problem('الإجراء يحتاج صلاحية اعتماد',403)
  if user['role']=='reviewer' and action not in ['approve','reject','campaign-approve']: raise Problem('الحساب مخصص للمراجعة والاعتماد',403)
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   current=db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
   if revision!=current: raise Problem('البيانات اتغيّرت من مستخدم آخر؛ حدّث الصفحة ثم حاول مجدداً',409)
   cid=p.get('clientId','');id=p.get('id') or uid();kind='';obj=None
   if action not in admin_actions:
    self.require(user,cid);self.entity(db,cid,'clients')
   if action=='client':
    id=uid();cid=id;kind='clients';obj={'id':id,'name':text(p,'name'),'brand':text(p,'brand'),'contact':text(p,'contact',optional=True),'brief':text(p,'brief',2000,True)}
    brand={'id':uid(),'clientId':cid,'name':obj['brand'],'voice':'','audience':''};self.put(db,'brands',brand)
   elif action=='brand':
    kind='brands';obj={'id':uid(),'clientId':cid,'name':text(p,'name'),'voice':text(p,'voice',2000,True),'audience':text(p,'audience',2000,True)}
   elif action=='account':
    platform=text(p,'platform');external=text(p,'externalId').lstrip('@');brand=self.entity(db,p.get('brandId'),'brands')
    if platform not in PLATFORMS or brand['clientId']!=cid: raise Problem('المنصة أو العلامة غير صحيحة')
    for row in db.execute("SELECT data FROM entities WHERE kind='accounts' AND client_id=?",(cid,)):
     a=json.loads(row[0])
     if a['platform']==platform and a['externalId'].casefold()==external.casefold(): raise Problem('الحساب مسجّل بالفعل')
    kind='accounts';obj={'id':uid(),'clientId':cid,'brandId':brand['id'],'platform':platform,'externalId':external,'connectionStatus':'not_connected'}
   elif action in ['post','edit-post']:
    accounts=p.get('accountIds',[])
    if not isinstance(accounts,list) or not accounts or len(accounts)>30 or any(not isinstance(a,str) for a in accounts): raise Problem('اختر حساباً واحداً على الأقل')
    for a in accounts:
     if self.entity(db,a,'accounts')['clientId']!=cid: raise Problem('الحساب يتبع عميلاً آخر',403)
    media=p.get('mediaIds',[])
    if not isinstance(media,list) or len(media)>10 or any(not isinstance(m,str) for m in media): raise Problem('اختر حتى 10 ملفات')
    for m in media:
     if self.entity(db,m,'media')['clientId']!=cid: raise Problem('الملف يتبع عميلاً آخر',403)
    kind='posts';obj={'id':uid(),'clientId':cid,'title':text(p,'title'),'body':text(p,'body',10000),'accountIds':list(dict.fromkeys(accounts)),'mediaIds':media,'status':'draft','createdAt':timestamp(),'createdBy':user['id']}
    if action=='edit-post':
     old=self.entity(db,id,'posts')
     if old['clientId']!=cid or old['status']!='draft': raise Problem('يمكن تعديل المسودات فقط')
     obj.update(id=id,createdAt=old['createdAt'],createdBy=old['createdBy'])
   elif action in ['review','approve','reject','schedule','cancel']:
    kind='posts';obj=self.entity(db,id,kind)
    if obj['clientId']!=cid: raise Problem('غير مصرح',403)
    expected={'review':'draft','approve':'review','reject':'review','schedule':'approved','cancel':'scheduled'}[action]
    if obj['status']!=expected: raise Problem('الإجراء لا يناسب الحالة الحالية')
    if action=='review':obj['status']='review'
    if action=='approve':obj.update(status='approved',approvedBy=user['id'],approvedAt=timestamp())
    if action=='reject':obj['status']='draft'
    if action=='schedule':
     try: when=datetime.fromisoformat(text(p,'when'))
     except ValueError: raise Problem('الموعد غير صحيح')
     if not when.tzinfo or when<=datetime.now(timezone.utc): raise Problem('اختر موعداً مستقبلياً مع منطقة زمنية')
     obj.update(status='scheduled',scheduledAt=when.astimezone(timezone.utc).isoformat(),dispatchStatus='blocked_no_connector')
     from server.dispatch import enqueue
     enqueue(db,obj)
    if action=='cancel':
     from server.dispatch import cancel
     cancel(db,id)
     obj['status']='approved';obj.pop('scheduledAt',None);obj.pop('dispatchStatus',None)
   elif action=='retry-target':
    from server.dispatch import retry
    retry(db,id,cid)
   elif action=='lead':
    criteria={k:True if p.get(k)=='yes' else False if p.get(k)=='no' else None for k in ['budget','authority','need','timeline']}
    status='unqualified' if False in criteria.values() else 'qualified' if all(v is True for v in criteria.values()) else 'incomplete'
    if p.get('id'):
     old=self.entity(db,id,'leads')
     if old['clientId']!=cid: raise Problem('غير مصرح',403)
    kind='leads';obj={'id':id,'clientId':cid,'name':text(p,'name'),'notes':text(p,'notes',5000,True),'criteria':criteria,'status':status}
   elif action=='campaign':
    try: budget=float(p.get('budget',0))
    except (TypeError,ValueError): raise Problem('الميزانية غير صحيحة')
    if not 0<budget<=100000000: raise Problem('الميزانية يجب أن تكون أكبر من صفر')
    account=self.entity(db,p.get('accountId'),'accounts')
    if account['clientId']!=cid: raise Problem('الحساب يتبع عميلاً آخر',403)
    start=text(p,'start');end=text(p,'end')
    try:
     if datetime.fromisoformat(start)>datetime.fromisoformat(end): raise ValueError()
    except ValueError: raise Problem('نطاق التاريخ غير صحيح')
    kind='campaigns';obj={'id':uid(),'clientId':cid,'name':text(p,'name'),'objective':text(p,'objective'),'accountId':account['id'],'budget':budget,'currency':'AED','start':start,'end':end,'status':'draft','createdBy':user['id']}
   elif action=='campaign-approve':
    kind='campaigns';obj=self.entity(db,id,kind)
    if obj['clientId']!=cid or obj['status']!='draft': raise Problem('الحملة غير متاحة للاعتماد')
    obj.update(status='approved',approvedBy=user['id'],approvedAt=timestamp())
   elif action=='media':
    try: data=base64.b64decode(p.get('data',''),validate=True)
    except (ValueError,TypeError): raise Problem('ملف غير صالح')
    if not 0<len(data)<=10*1024*1024: raise Problem('حجم الملف الأقصى 10 ميجابايت')
    mime='image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if data.startswith(b'\xff\xd8\xff') else 'image/webp' if data[:4]==b'RIFF' and data[8:12]==b'WEBP' else 'video/mp4' if data[4:8]==b'ftyp' else ''
    if not mime: raise Problem('الصيغ المتاحة PNG / JPEG / WebP / MP4 فقط')
    kind='media';id=uid();obj={'id':id,'clientId':cid,'name':text(p,'name'),'alt':text(p,'alt',2000,True),'rights':text(p,'rights',2000,True),'mime':mime,'size':len(data),'createdAt':timestamp()}
    db.execute('INSERT INTO blobs VALUES(?,?,?)',(id,data,mime))
   elif action=='user':
    role=text(p,'role')
    if role not in ROLES: raise Problem('الدور غير صحيح')
    clients=p.get('clients',[])
    if not isinstance(clients,list) or any(not isinstance(c,str) for c in clients): raise Problem('قائمة العملاء غير صحيحة')
    for c in clients:self.entity(db,c,'clients')
    email=text(p,'email').lower()
    if '@' not in email: raise Problem('البريد غير صحيح')
    try:db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',(uid(),email,text(p,'name'),password_hash(p.get('password','')),role,json.dumps(clients)))
    except sqlite3.IntegrityError:raise Problem('البريد مسجل بالفعل')
   elif action=='disable-user':
    if id==user['id']:raise Problem('لا يمكنك تعطيل حسابك الحالي')
    db.execute('UPDATE users SET active=0 WHERE id=?',(id,));db.execute('DELETE FROM sessions WHERE user_id=?',(id,))
   elif action=='secret':
    self.require(user,cid);self.entity(db,cid,'clients')
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key=os.environ.get('VAULT_KEY','')
    try: key=bytes.fromhex(key)
    except ValueError: raise Problem('إعداد مفتاح الخزنة غير صحيح',503)
    if len(key)!=32: raise Problem('الخزنة غير مهيأة على الخادم',503)
    value=text(p,'value',16000);id=uid();nonce=os.urandom(12)
    encrypted=nonce+AESGCM(key).encrypt(nonce,value.encode(),(cid+':'+id).encode())
    db.execute('INSERT INTO vault VALUES(?,?)',(id,encrypted))
    kind='secrets';obj={'id':id,'clientId':cid,'name':text(p,'name'),'createdAt':timestamp(),'status':'stored','lastFour':'••••'}
   elif action=='delete-secret':
    obj=self.entity(db,id,'secrets');self.require(user,obj['clientId']);cid=obj['clientId']
    db.execute('DELETE FROM vault WHERE id=?',(id,));db.execute('DELETE FROM entities WHERE id=?',(id,));obj=None
   else:raise Problem('إجراء غير معروف')
   if obj is not None: self.put(db,kind,obj);id=obj['id']
   self.put(db,'audit',{'id':uid(),'clientId':cid,'action':action,'entityId':id,'actor':user['name'],'at':timestamp()})
   db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
  return self.state(user)
 def file(self,user,id):
  with self.db() as db:
   obj=self.entity(db,id,'media');self.require(user,obj['clientId'])
   row=db.execute('SELECT * FROM blobs WHERE id=?',(id,)).fetchone()
   if not row:raise Problem('الملف غير موجود',404)
   return row['data'],row['mime']
 def change_password(self,user,current,new):
  if not password_valid(current,user['password']):raise Problem('كلمة المرور الحالية غير صحيحة',403)
  hashed=password_hash(new)
  with self.db() as db:
   db.execute('UPDATE users SET password=? WHERE id=?',(hashed,user['id']));db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
