"""Durable per-target dispatch. No live adapter is registered in this release."""
import json,time
from datetime import datetime,timezone
from server.core import Problem,timestamp,uid

class NotSent(Exception):
 """Adapter guarantees the provider did not accept this request."""
class Uncertain(Exception):
 """Provider may have accepted the request: never retry automatically."""

def ensure_schema(db):
 db.executescript('''CREATE TABLE IF NOT EXISTS dispatch_jobs(
 id TEXT PRIMARY KEY,post_id TEXT NOT NULL,account_id TEXT NOT NULL,client_id TEXT NOT NULL,
 state TEXT NOT NULL,due REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
 claimed REAL,receipt TEXT,error TEXT,UNIQUE(post_id,account_id));
 CREATE INDEX IF NOT EXISTS dispatch_due ON dispatch_jobs(state,due);
 ''')

def enqueue(db,post):
 due=datetime.fromisoformat(post['scheduledAt']).timestamp()
 old=db.execute('SELECT state FROM dispatch_jobs WHERE post_id=?',(post['id'],)).fetchall()
 if any(r['state'] in ['sending','published','unknown'] for r in old):raise Problem('لا يمكن إعادة جدولة مهمة بدأت الإرسال')
 for aid in post['accountIds']:
  db.execute('''INSERT INTO dispatch_jobs(id,post_id,account_id,client_id,state,due) VALUES(?,?,?,?,?,?)
  ON CONFLICT(post_id,account_id) DO UPDATE SET state='blocked',due=excluded.due,error=NULL,receipt=NULL''',(uid(),post['id'],aid,post['clientId'],'blocked',due))

def cancel(db,post_id):
 if db.execute("SELECT 1 FROM dispatch_jobs WHERE post_id=? AND state IN ('sending','published','unknown')",(post_id,)).fetchone():raise Problem('الإرسال بدأ بالفعل؛ راجع حالة كل حساب قبل أي تغيير')
 db.execute("UPDATE dispatch_jobs SET state='cancelled' WHERE post_id=? AND state IN ('queued','blocked','failed')",(post_id,))

def jobs_for(db,store,user):
 return [{**dict(row),'postId':row['post_id'],'accountId':row['account_id'],'clientId':row['client_id']} for row in db.execute('SELECT * FROM dispatch_jobs ORDER BY due DESC') if store.allowed(user,row['client_id'])]

def retry(db,job_id,client_id):
 job=db.execute('SELECT * FROM dispatch_jobs WHERE id=? AND client_id=?',(job_id,client_id)).fetchone()
 if not job:raise Problem('المهمة غير موجودة',404)
 if job['state'] not in ['failed','blocked']:raise Problem('لا تُعاد المهام الناجحة أو ذات النتيجة غير المؤكدة')
 db.execute("UPDATE dispatch_jobs SET state='queued',error=NULL WHERE id=?",(job_id,))

def aggregate(db,store,post_id):
 post=store.entity(db,post_id,'posts');states=[r[0] for r in db.execute('SELECT state FROM dispatch_jobs WHERE post_id=?',(post_id,))]
 if states and all(s=='published' for s in states):post.update(status='published',dispatchStatus='published')
 elif 'published' in states:post.update(status='partial',dispatchStatus='partial')
 elif 'unknown' in states:post['dispatchStatus']='unknown'
 elif 'failed' in states:post['dispatchStatus']='failed'
 elif 'sending' in states:post['dispatchStatus']='sending'
 elif states and all(s=='cancelled' for s in states):post['dispatchStatus']='cancelled'
 else:post['dispatchStatus']='blocked_no_connector'
 store.put(db,'posts',post)

class Dispatcher:
 """An adapter must expose ready(account) and publish(post, account, idempotency_key).
 publish returns a nonempty provider receipt ID. ready must be local and read-only.
 Unknown exceptions and crash recovery require manual reconciliation.
 """
 def __init__(self,store,adapters=None):self.store=store;self.adapters=adapters or {}
 def recover(self,now=None):
  now=time.time() if now is None else now
  with self.store.db() as db:
   db.execute('BEGIN IMMEDIATE')
   rows=db.execute("SELECT * FROM dispatch_jobs WHERE state='sending' AND claimed<?",(now-300,)).fetchall()
   for job in rows:
    db.execute("UPDATE dispatch_jobs SET state='unknown',error='تعطل عامل النشر؛ تحقّق من المنصة قبل أي إعادة إرسال' WHERE id=?",(job['id'],));aggregate(db,self.store,job['post_id'])
   if rows:db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
  return len(rows)
 def run_one(self,now=None):
  now=time.time() if now is None else now;selected=None
  with self.store.db() as db:
   db.execute('BEGIN IMMEDIATE')
   for job in db.execute("SELECT * FROM dispatch_jobs WHERE state IN ('queued','blocked') AND due<=? ORDER BY due",(now,)).fetchall():
    post=self.store.entity(db,job['post_id'],'posts');account=self.store.entity(db,job['account_id'],'accounts');adapter=self.adapters.get(account['platform'])
    if not adapter or not adapter.ready(account):
     db.execute("UPDATE dispatch_jobs SET state='blocked' WHERE id=? AND state!='blocked'",(job['id'],));continue
    db.execute("UPDATE dispatch_jobs SET state='sending',claimed=?,attempts=attempts+1,error=NULL WHERE id=?",(now,job['id']));selected=(dict(job),post,account,adapter);aggregate(db,self.store,job['post_id']);db.execute("UPDATE meta SET value=value+1 WHERE key='revision'");break
  if not selected:return False
  job,post,account,adapter=selected;state='unknown';receipt=None;error=None
  try:
   receipt=adapter.publish(post,account,job['id'])
   if not isinstance(receipt,str) or not receipt.strip():raise Uncertain()
   state='published'
  except NotSent:state='failed';error='أكد الموصل عدم قبول الطلب؛ يمكن إعادة محاولة هذا الهدف'
  except Exception:state='unknown';error='نتيجة الإرسال غير مؤكدة؛ راجع المنصة ولا تُعد الإرسال تلقائياً'
  with self.store.db() as db:
   db.execute('BEGIN IMMEDIATE')
   # Compare-and-set: do not overwrite a task already reconciled elsewhere.
   changed=db.execute("UPDATE dispatch_jobs SET state=?,receipt=?,error=? WHERE id=? AND state='sending'",(state,receipt,error,job['id'])).rowcount
   if changed:
    aggregate(db,self.store,job['post_id']);self.store.put(db,'audit',{'id':uid(),'clientId':job['client_id'],'action':'dispatch-'+state,'entityId':job['id'],'actor':'عامل النشر','at':timestamp()});db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
  return True
