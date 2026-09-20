import json,os,tempfile,time,unittest
from urllib.parse import urlsplit
from unittest.mock import patch
from server.core import Store,Problem
from server.dispatch import Dispatcher,NotSent
from server.instagram import connect,disconnect,metadata,InstagramProfessional,signed_media_url,public_media

class InstagramTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name+'/db');self.env=patch.dict(os.environ,{'VAULT_KEY':'cd'*32,'APP_ORIGIN':'https://social.example'});self.env.start()
  self.admin={'id':'u','name':'Owner','email':'owner@example.com','role':'admin','clients':'[]'}
  self.account={'id':'ig-a','clientId':'c','platform':'Instagram','externalId':'brand'}
  self.post={'id':'p','clientId':'c','status':'scheduled','body':'Caption','mediaIds':['image']}
  with self.store.db() as db:
   self.store.put(db,'clients',{'id':'c'});self.store.put(db,'accounts',self.account);self.store.put(db,'posts',self.post)
   self.store.put(db,'media',{'id':'image','clientId':'c','name':'post.png','mime':'image/png'});db.execute('INSERT INTO blobs VALUES(?,?,?)',('image',b'\x89PNG\r\n\x1a\nimage','image/png'))
  self.payload={'accountId':'ig-a','pageId':'123','token':'private-instagram-page-token','version':'v25.0','expires':time.time()+3600}
 def tearDown(self):self.env.stop();self.temp.cleanup()
 def identity(self,*_):return {'id':'123','name':'Page','instagram_business_account':{'id':'987','username':'brand'}}
 def link(self):return connect(self.store,self.admin,self.payload,self.identity)
 def job(self):
  with self.store.db() as db:db.execute('INSERT INTO dispatch_jobs(id,post_id,account_id,client_id,state,due) VALUES(?,?,?,?,?,?)',('j','p','ig-a','c','blocked',time.time()-5))
 def test_connection_is_encrypted_scoped_and_deletable(self):
  state=self.link();self.assertNotIn(self.payload['token'],json.dumps(state));self.assertEqual(metadata(self.store,self.admin)[0]['username'],'brand')
  with self.store.db() as db:self.assertNotIn(self.payload['token'].encode(),db.execute('SELECT cipher FROM instagram_connections').fetchone()[0])
  other={**self.admin,'role':'viewer','clients':'["other"]'};self.assertEqual(metadata(self.store,other),[])
  disconnect(self.store,self.admin,'ig-a');self.assertFalse(InstagramProfessional(self.store).ready(self.account))
 def test_connection_requires_professional_account_on_matching_page(self):
  with self.assertRaises(Problem):connect(self.store,self.admin,self.payload,lambda *_:{'id':'123','name':'No Instagram'})
  with self.assertRaises(Problem):connect(self.store,self.admin,self.payload,lambda *_:{'id':'999','instagram_business_account':{'id':'987'}})
 def test_signed_public_image_url_expires_and_rejects_tampering(self):
  url=signed_media_url('image',60);parts=urlsplit(url);data,mime=public_media(self.store,'image',parts.query);self.assertEqual(mime,'image/png');self.assertTrue(data.startswith(b'\x89PNG'))
  with self.assertRaises(Problem):public_media(self.store,'image',parts.query.replace('sig=','sig=bad'))
  with self.assertRaises(Problem):public_media(self.store,'image','exp=1&sig=bad')
 def test_two_step_image_publish_uses_signed_url_and_creation_id(self):
  self.link();calls=[]
  def transport(method,path,token,version,params):
   calls.append((method,path,token,version,params));return {'id':'555'} if path.endswith('/media') else {'id':'777'}
  adapter=InstagramProfessional(self.store,transport,lambda media_id:'https://social.example/signed/'+media_id)
  self.assertEqual(adapter.publish(self.post,self.account,'j'),'777');self.assertEqual(calls[0][1],'987/media');self.assertEqual(calls[0][-1]['image_url'],'https://social.example/signed/image');self.assertEqual(calls[1][1],'987/media_publish');self.assertEqual(calls[1][-1],{'creation_id':'555'})
 def test_instagram_requires_exactly_one_supported_image(self):
  self.link();adapter=InstagramProfessional(self.store,lambda *_:self.fail('Graph must not be called'))
  with self.assertRaises(NotSent):adapter.publish({**self.post,'mediaIds':[]},self.account,'j')
  with self.assertRaises(NotSent):adapter.publish({**self.post,'mediaIds':['one','two']},self.account,'j')
 def test_successful_job_is_not_published_twice(self):
  self.link();self.job();calls=[]
  def transport(method,path,token,version,params):calls.append(path);return {'id':'555'} if path.endswith('/media') else {'id':'777'}
  worker=Dispatcher(self.store,{'Instagram':InstagramProfessional(self.store,transport,lambda _:'https://social.example/image')})
  self.assertTrue(worker.run_one(job_id='j'));self.assertFalse(worker.run_one(job_id='j'));self.assertEqual(calls,['987/media','987/media_publish'])
