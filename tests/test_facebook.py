import json,os,tempfile,time,unittest
from unittest.mock import patch
from pathlib import Path
from server.core import Store,Problem
from server.facebook import connect,disconnect,metadata,FacebookPages,send_target,graph_photo
from server.dispatch import Dispatcher,NotSent,Uncertain
from server.vault_key import initialize

class FacebookTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name+'/db');self.env=patch.dict(os.environ,{'VAULT_KEY':'ab'*32});self.env.start()
  self.admin={'id':'u','name':'Owner','email':'owner@example.com','role':'admin','clients':'[]'}
  self.account={'id':'a','clientId':'c','platform':'Facebook','externalId':'my-page'}
  self.post={'id':'p','clientId':'c','status':'scheduled','body':'Hello','mediaIds':[]}
  with self.store.db() as db:
   self.store.put(db,'clients',{'id':'c'});self.store.put(db,'accounts',self.account);self.store.put(db,'posts',self.post)
  self.payload={'accountId':'a','pageId':'123','token':'private-token-do-not-return','version':'v25.0','expires':time.time()+3600}
 def tearDown(self):self.env.stop();self.temp.cleanup()
 def identity(self,*args):return {'id':'123','name':'Page','category':'Business'}
 def link(self):return connect(self.store,self.admin,self.payload,self.identity)
 def job(self,id='j',post='p'):
  with self.store.db() as db:db.execute('INSERT INTO dispatch_jobs(id,post_id,account_id,client_id,state,due) VALUES(?,?,?,?,?,?)',(id,post,'a','c','blocked',time.time()-10))
 def test_encrypted_scoped_metadata_and_disconnect(self):
  result=self.link();self.assertNotIn(self.payload['token'],json.dumps(result))
  with self.store.db() as db:self.assertNotIn(self.payload['token'].encode(),db.execute('SELECT cipher FROM page_connections').fetchone()[0])
  other={**self.admin,'role':'viewer','clients':'["other"]'};self.assertEqual(metadata(self.store,other),[])
  disconnect(self.store,self.admin,'a');self.assertFalse(FacebookPages(self.store).ready(self.account))
 def test_nonadmin_and_wrong_page_cannot_connect(self):
  with self.assertRaises(Problem):connect(self.store,{**self.admin,'role':'editor'},self.payload,self.identity)
  with self.assertRaises(Problem):connect(self.store,self.admin,self.payload,lambda *args:{'id':'456','category':'Business'})
  with self.assertRaises(Problem):connect(self.store,self.admin,self.payload,lambda *args:{'id':'123','name':'User'})
 def test_expired_and_invalid_versions_rejected(self):
  for extra in [{'expires':0},{'expires':float('nan')},{'version':'../../evil'}]:
   with self.assertRaises(Problem):connect(self.store,self.admin,{**self.payload,**extra},self.identity)
 def test_success_is_not_sent_twice(self):
  self.link();self.job();calls=[]
  def transport(*args):calls.append(args);return {'id':'123_456'}
  dispatcher=Dispatcher(self.store,{'Facebook':FacebookPages(self.store,transport)})
  self.assertTrue(dispatcher.run_one(job_id='j'));self.assertFalse(dispatcher.run_one(job_id='j'));self.assertEqual(len(calls),1)
  self.assertEqual(calls[0][1],'123/feed');self.assertEqual(calls[0][-1],{'message':'Hello'})
 def test_ambiguous_response_is_never_retried(self):
  self.link();self.job();adapter=FacebookPages(self.store,lambda *args:{})
  worker=Dispatcher(self.store,{'Facebook':adapter});worker.run_one(job_id='j');self.assertFalse(worker.run_one(job_id='j'))
  with self.store.db() as db:self.assertEqual(db.execute('SELECT state FROM dispatch_jobs').fetchone()[0],'unknown')
 def test_single_image_is_uploaded_as_photo(self):
  self.link();image_id='image'
  with self.store.db() as db:
   self.store.put(db,'media',{'id':image_id,'clientId':'c','name':'cover.jpg','mime':'image/jpeg'})
   db.execute('INSERT INTO blobs VALUES(?,?,?)',(image_id,b'\xff\xd8\xffdata','image/jpeg'))
  calls=[]
  adapter=FacebookPages(self.store,lambda *args:self.fail('Feed transport must not be called'),lambda *args:(calls.append(args) or {'post_id':'123_789'}))
  self.assertEqual(adapter.publish({**self.post,'mediaIds':[image_id]},self.account,'j'),'123_789')
  self.assertEqual(calls[0][0],'123/photos');self.assertEqual(calls[0][3],{'message':'Hello'});self.assertEqual(calls[0][-2],'image/jpeg')
 def test_unsupported_or_multiple_attachments_never_silently_drop(self):
  self.link();adapter=FacebookPages(self.store,lambda *args:self.fail('Network must not be called'),lambda *args:self.fail('Upload must not be called'))
  with self.assertRaises(NotSent):adapter.publish({**self.post,'mediaIds':['one','two']},self.account,'j')
  with self.store.db() as db:
   self.store.put(db,'media',{'id':'video','clientId':'c','name':'clip.mp4','mime':'video/mp4'});db.execute('INSERT INTO blobs VALUES(?,?,?)',('video',b'data','video/mp4'))
  with self.assertRaises(NotSent):adapter.publish({**self.post,'mediaIds':['video']},self.account,'j')
 def test_photo_transport_uses_multipart_and_bearer_header(self):
  captured={}
  class Response:
   def __enter__(self):return self
   def __exit__(self,*_):pass
   def read(self,_):return b'{"post_id":"123_456"}'
  class Opener:
   def open(self,request,timeout):captured.update(request=request,timeout=timeout);return Response()
  with patch('server.facebook.build_opener',return_value=Opener()):
   result=graph_photo('123/photos','private-token','v25.0',{'message':'Caption'},'photo.jpg','image/jpeg',b'\xff\xd8\xffdata')
  request=captured['request'];self.assertEqual(result['post_id'],'123_456');self.assertEqual(captured['timeout'],30)
  self.assertEqual(request.get_header('Authorization'),'Bearer private-token');self.assertIn('multipart/form-data',request.get_header('Content-type'))
  self.assertIn(b'Caption',request.data);self.assertIn(b'photo.jpg',request.data);self.assertNotIn(b'private-token',request.data)
 def test_exact_target_and_send_permissions(self):
  self.link();self.job();worker=Dispatcher(self.store,{'Facebook':FacebookPages(self.store,lambda *args:{'id':'123_456'})})
  self.assertFalse(worker.run_one(job_id='unrelated'))
  with self.assertRaises(Problem):send_target(self.store,{**self.admin,'role':'editor'},{'jobId':'j','confirm':True})
  with self.assertRaises(Problem):send_target(self.store,self.admin,{'jobId':'j','confirm':False})
 def test_key_provisioning_persists_and_refuses_missing_existing_key(self):
  with patch.dict(os.environ,{},clear=True):
   initialize(self.store);first=os.environ.pop('VAULT_KEY');initialize(self.store);self.assertEqual(first,os.environ['VAULT_KEY']);self.assertEqual((Path(self.temp.name)/'vault.key').stat().st_mode&0o777,0o600)
  self.link();(Path(self.temp.name)/'vault.key').unlink()
  with patch.dict(os.environ,{},clear=True):
   with self.assertRaises(RuntimeError):initialize(self.store)
