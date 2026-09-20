import tempfile,time,unittest,json
from concurrent.futures import ThreadPoolExecutor
from server.core import Store,Problem
from server.dispatch import Dispatcher,NotSent

class FakeAdapter:
 def __init__(self,outcome='success'):self.calls=[];self.outcome=outcome
 def ready(self,account):return True
 def publish(self,post,account,idempotency_key):
  self.calls.append(account['id'])
  if self.outcome=='failed':raise NotSent()
  if self.outcome=='unknown':raise TimeoutError()
  return 'receipt-'+idempotency_key

class DispatchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name+'/db');self.user={'id':'owner','role':'admin','name':'Owner','email':'owner@example.com','clients':'[]'}
  s=self.act('client',{'name':'Client','brand':'Brand'});self.cid=s['clients'][0]['id'];bid=s['brands'][0]['id'];ids=[]
  for n in ['first','second']:
   s=self.act('account',{'clientId':self.cid,'brandId':bid,'platform':'Instagram','externalId':n});ids.append(s['accounts'][-1]['id'])
  s=self.act('post',{'clientId':self.cid,'title':'Post','body':'Body','accountIds':ids});self.pid=s['posts'][0]['id'];self.ref={'clientId':self.cid,'id':self.pid}
  self.act('review',self.ref);self.act('approve',self.ref);self.act('schedule',{**self.ref,'when':'2099-01-01T12:00:00+04:00'});self.now=4102444800
 def tearDown(self):self.tmp.cleanup()
 def act(self,a,p):return self.store.mutate(self.user,a,p,self.store.state(self.user)['revision'])
 def jobs(self):return self.store.state(self.user)['jobs']
 def test_missing_adapter_never_claims_or_sends(self):
  self.assertFalse(Dispatcher(self.store).run_one(self.now));self.assertTrue(all(j['state']=='blocked' and j['attempts']==0 for j in self.jobs()))
 def test_due_date_respected(self):
  adapter=FakeAdapter();self.assertFalse(Dispatcher(self.store,{'Instagram':adapter}).run_one(time.time()));self.assertEqual(adapter.calls,[])
 def test_one_job_per_target_success_never_repeated(self):
  adapter=FakeAdapter();worker=Dispatcher(self.store,{'Instagram':adapter});worker.run_one(self.now);worker.run_one(self.now);self.assertFalse(worker.run_one(self.now));self.assertEqual(len(adapter.calls),2);self.assertEqual(len(set(adapter.calls)),2);self.assertEqual(self.store.state(self.user)['posts'][0]['status'],'published')
  with self.assertRaises(Problem):self.act('retry-target',{'id':self.jobs()[0]['id'],'clientId':self.cid})
 def test_partial_failure_retry_only_failed(self):
  adapter=FakeAdapter();worker=Dispatcher(self.store,{'Instagram':adapter});worker.run_one(self.now);adapter.outcome='failed';worker.run_one(self.now);self.assertEqual(self.store.state(self.user)['posts'][0]['status'],'partial')
  failed=next(j for j in self.jobs() if j['state']=='failed');self.act('retry-target',{'clientId':self.cid,'id':failed['id']});adapter.outcome='success';worker.run_one(self.now);self.assertEqual(len(adapter.calls),3);self.assertEqual(adapter.calls[1],adapter.calls[2]);self.assertNotEqual(adapter.calls[0],adapter.calls[2])
 def test_uncertain_result_never_retried(self):
  adapter=FakeAdapter('unknown');worker=Dispatcher(self.store,{'Instagram':adapter});worker.run_one(self.now);job=next(j for j in self.jobs() if j['state']=='unknown')
  with self.assertRaises(Problem):self.act('retry-target',{'clientId':self.cid,'id':job['id']})
  with self.assertRaises(Problem):self.act('cancel',self.ref)
 def test_crash_recovery_preserves_uncertainty(self):
  job=self.jobs()[0]
  with self.store.db() as db:db.execute("UPDATE dispatch_jobs SET state='sending',claimed=? WHERE id=?",(self.now-400,job['id']))
  self.assertEqual(Dispatcher(self.store).recover(self.now),1);self.assertEqual(next(j for j in self.jobs() if j['id']==job['id'])['state'],'unknown')
 def test_cancel_reschedule_does_not_duplicate_targets(self):
  self.act('cancel',self.ref);self.assertTrue(all(j['state']=='cancelled' for j in self.jobs()));self.act('schedule',{**self.ref,'when':'2099-01-01T12:00:00+04:00'});self.assertEqual(len(self.jobs()),2)
 def test_concurrent_workers_claim_different_targets(self):
  adapter=FakeAdapter();worker=Dispatcher(self.store,{'Instagram':adapter})
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:worker.run_one(self.now),range(2)))
  self.assertEqual(len(set(adapter.calls)),2);self.assertTrue(all(j['state']=='published' for j in self.jobs()))
 def test_retry_cannot_cross_client(self):
  cid=self.act('client',{'name':'Other','brand':'Other'})['clients'][-1]['id']
  with self.assertRaises(Problem):self.act('retry-target',{'clientId':cid,'id':self.jobs()[0]['id']})
 def test_old_schedules_migrate_on_reopen(self):
  with self.store.db() as db:db.execute('DELETE FROM dispatch_jobs')
  self.store=Store(self.store.path);self.assertEqual(len(self.jobs()),2)
