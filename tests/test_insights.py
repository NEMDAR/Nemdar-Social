import os,tempfile,time,unittest
from unittest.mock import patch
from server.core import Store,Problem
from server.facebook import connect as facebook_connect
from server.instagram import connect as instagram_connect
from server.insights import normalize,sync_account

class InsightsTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name+'/db');self.env=patch.dict(os.environ,{'VAULT_KEY':'ef'*32});self.env.start()
  self.admin={'id':'u','name':'Owner','email':'owner@example.com','role':'admin','clients':'[]'}
  with self.store.db() as db:
   self.store.put(db,'clients',{'id':'c'})
   self.store.put(db,'accounts',{'id':'fb','clientId':'c','platform':'Facebook','externalId':'page'})
   self.store.put(db,'accounts',{'id':'ig','clientId':'c','platform':'Instagram','externalId':'brand'})
  self.now=time.time();expires=self.now+3600
  facebook_connect(self.store,self.admin,{'accountId':'fb','pageId':'123','token':'private-facebook-token','version':'v25.0','expires':expires},lambda *_:{'id':'123','name':'Page','category':'Business'})
  instagram_connect(self.store,self.admin,{'accountId':'ig','pageId':'456','token':'private-instagram-token','version':'v25.0','expires':expires},lambda *_:{'id':'456','instagram_business_account':{'id':'789','username':'brand'}})
 def tearDown(self):self.env.stop();self.temp.cleanup()
 def test_normalize_supports_series_latest_and_provider_total(self):
  result={'data':[{'values':[{'value':2,'end_time':'a'},{'value':3,'end_time':'b'}]}]}
  self.assertEqual(normalize(result)['value'],5);self.assertEqual(normalize(result,'latest')['value'],3)
  self.assertEqual(normalize({'data':[{'total_value':{'value':9}}]})['value'],9)
 def test_facebook_snapshot_is_scoped_and_never_returns_token(self):
  seen=[]
  def transport(method,path,token,version,params):
   seen.append((path,token,params));values={'page_impressions':10,'page_post_engagements':4,'page_fans':30,'page_video_views':2}
   return {'data':[{'values':[{'value':values[params['metric']],'end_time':'2026-09-21T00:00:00+0000'}]}]}
  state=sync_account(self.store,self.admin,{'accountId':'fb'},transport,now=self.now)
  snapshot=state['insights'][0];self.assertEqual(snapshot['status'],'available');self.assertEqual(snapshot['metrics']['impressions']['value'],10)
  self.assertEqual(snapshot['metrics']['followers']['aggregation'],'latest');self.assertTrue(all(call[0]=='123/insights' for call in seen))
  self.assertNotIn('private-facebook-token',str(state))
  other={**self.admin,'role':'viewer','clients':'["other"]'};self.assertEqual(self.store.state(other)['insights'],[])
 def test_instagram_partial_snapshot_preserves_available_metrics(self):
  def transport(method,path,token,version,params):
   self.assertEqual(path,'789/insights');self.assertEqual(params['metric_type'],'total_value')
   if params['metric']=='website_clicks':raise RuntimeError('unsupported')
   return {'data':[{'total_value':{'value':7}}]}
  state=sync_account(self.store,self.admin,{'accountId':'ig'},transport,now=self.now);snapshot=state['insights'][0]
  self.assertEqual(snapshot['status'],'partial');self.assertIn('websiteClicks',snapshot['unavailable']);self.assertEqual(snapshot['metrics']['reach']['value'],7)
 def test_sync_requires_admin_and_active_connection(self):
  with self.assertRaises(Problem):sync_account(self.store,{**self.admin,'role':'editor'},{'accountId':'fb'},lambda *_:{})
  with self.assertRaises(Problem):sync_account(self.store,self.admin,{'accountId':'missing'},lambda *_:{})

if __name__=='__main__':unittest.main()
