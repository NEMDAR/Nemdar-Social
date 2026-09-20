import base64,io,json,os,tempfile,unittest
from unittest.mock import patch
from server.app import App
from server.core import Problem

class WorkspaceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.path=cls.temp.name+'/db.sqlite';cls.app=App(cls.path,'http://localhost:8080');cls.store=cls.app.store
  cls.store.setup('owner@example.com','A-strong-test-password')
  cls.token,cls.csrf=cls.store.login('owner@example.com','A-strong-test-password','test')
  cls.admin=cls.store.session(cls.token)
 def action(self,action,p,user=None):
  user=user or self.admin;return self.store.mutate(user,action,p,self.store.state(user)['revision'])
 def client(self,name='Client'):
  state=self.action('client',{'name':name,'brand':'Brand'});cid=state['clients'][-1]['id'];bid=next(b['id'] for b in state['brands'] if b['clientId']==cid);return cid,bid
 def account(self,cid,bid):return self.action('account',{'clientId':cid,'brandId':bid,'platform':'Instagram','externalId':'account'})['accounts'][-1]['id']
 def user(self,role,cids):
  import uuid
  email=uuid.uuid4().hex+'@example.com';self.action('user',{'email':email,'password':'Another-good-password','name':role,'role':role,'clients':cids});token,_=self.store.login(email,'Another-good-password','test');return self.store.session(token),token
 def request(self,path,method='GET',body=None,token=None,csrf=None,origin='http://localhost:8080'):
  raw=json.dumps(body or {}).encode();env={'PATH_INFO':path,'REQUEST_METHOD':method,'HTTP_ORIGIN':origin,'HTTP_COOKIE':'session='+(token or ''),'HTTP_X_CSRF_TOKEN':csrf or '', 'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),'REMOTE_ADDR':'test'};result={}
  def start(status,headers):result.update(status=int(status.split()[0]),headers=dict(headers))
  result['body']=b''.join(self.app(env,start));return result
 def test_01_auth_required(self):self.assertEqual(self.request('/api/state')['status'],401)
 def test_02_cookie_attributes(self):
  r=self.request('/api/login','POST',{'email':'owner@example.com','password':'A-strong-test-password'});self.assertEqual(r['status'],200);self.assertIn('HttpOnly',r['headers']['Set-Cookie']);self.assertIn('SameSite=Strict',r['headers']['Set-Cookie'])
 def test_03_origin_and_csrf_enforced(self):
  self.assertEqual(self.request('/api/logout','POST',token=self.token,origin='https://evil.example')['status'],403)
  self.assertEqual(self.request('/api/logout','POST',token=self.token)['status'],403)
 def test_04_private_files_not_served(self):
  for path in ['/data/workspace.db','/server/core.py','/.env','/src/../../server/core.py']:
   self.assertEqual(self.request(path)['status'],404)
 def test_05_scope_and_role(self):
  cid,bid=self.client();other,_=self.client('Other');editor,_=self.user('editor',[cid]);viewer,_=self.user('viewer',[cid])
  self.assertEqual([x['id'] for x in self.store.state(editor)['clients']],[cid])
  with self.assertRaises(Problem):self.action('brand',{'clientId':other,'name':'No'},editor)
  with self.assertRaises(Problem):self.action('brand',{'clientId':cid,'name':'No'},viewer)
  with self.assertRaises(Problem):self.action('user',{},editor)
 def test_06_full_content_workflow(self):
  cid,bid=self.client();aid=self.account(cid,bid);editor,_=self.user('editor',[cid]);reviewer,_=self.user('reviewer',[cid]);p={'clientId':cid,'accountIds':[aid],'title':'Test','body':'Body','mediaIds':[]}
  post=self.action('post',p,editor)['posts'][-1];ref={'clientId':cid,'id':post['id']}
  with self.assertRaises(Problem):self.action('approve',ref,reviewer)
  self.action('review',ref,editor)
  with self.assertRaises(Problem):self.action('approve',ref,editor)
  self.action('approve',ref,reviewer)
  with self.assertRaises(Problem):self.action('schedule',{**ref,'when':'2020-01-01T00:00:00+04:00'},editor)
  s=self.action('schedule',{**ref,'when':'2099-01-01T12:00:00+04:00'},editor);scheduled=next(p for p in s['posts'] if p['id']==post['id']);self.assertEqual(scheduled['dispatchStatus'],'blocked_no_connector');self.assertIn('08:00:00',scheduled['scheduledAt']);self.action('cancel',ref,editor)
 def test_07_duplicate_accounts(self):
  cid,bid=self.client();self.account(cid,bid)
  with self.assertRaises(Problem):self.action('account',{'clientId':cid,'brandId':bid,'platform':'Instagram','externalId':'@ACCOUNT'})
 def test_08_stale_write_rejected(self):
  rev=self.store.state(self.admin)['revision'];self.client()
  with self.assertRaises(Problem) as err:self.store.mutate(self.admin,'client',{'name':'Stale','brand':'X'},rev)
  self.assertEqual(err.exception.status,409)
 def test_09_media_scope(self):
  cid,_=self.client();other,_=self.client();user,_=self.user('editor',[other]);raw=b'\x89PNG\r\n\x1a\n'+b'demo'
  s=self.action('media',{'clientId':cid,'name':'demo.png','data':base64.b64encode(raw).decode()});m=s['media'][-1];self.assertEqual(self.store.file(self.admin,m['id'])[0],raw)
  with self.assertRaises(Problem):self.store.file(user,m['id'])
  with self.assertRaises(Problem):self.action('media',{'clientId':cid,'name':'script.svg','data':base64.b64encode(b'<svg/>').decode()})
 def test_10_vault_ciphertext_no_read_api(self):
  cid,_=self.client();os.environ['VAULT_KEY']='ab'*32
  s=self.action('secret',{'clientId':cid,'name':'Provider','value':'private-token-123'});secret=s['secrets'][-1]
  self.assertNotIn('private-token',json.dumps(s))
  with self.store.db() as db:
   cipher=db.execute('SELECT cipher FROM vault WHERE id=?',(secret['id'],)).fetchone()[0];self.assertNotIn(b'private-token',cipher)
  self.assertEqual(self.request('/api/secrets/'+secret['id'],token=self.token)['status'],404)
  self.action('delete-secret',{'id':secret['id']});self.assertFalse(any(x['id']==secret['id'] for x in self.store.state(self.admin)['secrets']))
 def test_11_campaign_budget_approval(self):
  cid,bid=self.client();aid=self.account(cid,bid)
  p={'clientId':cid,'accountId':aid,'name':'Campaign','objective':'Leads','budget':100,'start':'2026-10-01','end':'2026-10-10'}
  s=self.action('campaign',p);campaign=s['campaigns'][-1];s=self.action('campaign-approve',{'clientId':cid,'id':campaign['id']});self.assertEqual(s['campaigns'][-1]['status'],'approved');self.assertNotIn('spent',s['campaigns'][-1])
  with self.assertRaises(Problem):self.action('campaign',{**p,'budget':float('nan')})
 def test_12_lead_unknown_not_qualified(self):
  cid,_=self.client();s=self.action('lead',{'clientId':cid,'name':'Lead','budget':'yes','need':'yes'});self.assertEqual(s['leads'][-1]['status'],'incomplete')
 def test_13_disabled_user_session_revoked(self):
  user,token=self.user('viewer',[]);self.action('disable-user',{'id':user['id']})
  with self.assertRaises(Problem):self.store.session(token)
 def test_14_password_change_revokes_sessions(self):
  user,token=self.user('viewer',[]);self.store.change_password(user,'Another-good-password','New-safe-password-123')
  with self.assertRaises(Problem):self.store.session(token)
 def test_15_password_not_in_state(self):self.assertNotIn('password',self.store.state(self.admin)['user']);self.assertTrue(all('password' not in u for u in self.store.state(self.admin)['users']))
 def test_16_database_reopen(self):
  from server.core import Store
  self.assertEqual(Store(self.path).state(self.admin)['revision'],self.store.state(self.admin)['revision'])
 def test_17_setup_is_one_time(self):
  with self.assertRaises(Problem):self.store.setup('attacker@example.com','Attacker-password-123')
 def test_18_login_throttling(self):
  for _ in range(8):
   with self.assertRaises(Problem):self.store.login('unknown@example.com','Wrong-password-123','rate-test')
  with self.assertRaises(Problem) as err:self.store.login('unknown@example.com','Wrong-password-123','rate-test')
  self.assertEqual(err.exception.status,429)
 def test_19_unknown_action_rolls_back(self):
  cid,_=self.client();rev=self.store.state(self.admin)['revision']
  with self.assertRaises(Problem):self.action('bogus',{'clientId':cid})
  self.assertEqual(self.store.state(self.admin)['revision'],rev)
 def test_20_state_endpoint(self):
  r=self.request('/api/state',token=self.token);self.assertEqual(r['status'],200);self.assertIn('Content-Security-Policy',r['headers']);self.assertEqual(json.loads(r['body'])['user']['role'],'admin')
 def test_21_surface_assessment_is_scoped_and_validated(self):
  cid,_=self.client();other,_=self.client('Other assessment client');editor,_=self.user('editor',[cid])
  snapshots={'website':{'status':'available','title':'Example'},'instagram':{'status':'unavailable'},'observedAt':'2026-09-20T00:00:00+00:00'}
  with patch('server.surface_audit.collect',return_value=snapshots):state=self.action('assessment',{'clientId':cid,'urls':{'website':'https://example.com','instagram':'https://instagram.com/example'}},editor)
  assessment=state['assessments'][-1]
  self.assertEqual(assessment['mode'],'surface');self.assertEqual(set(assessment['urls']),{'website','instagram'})
  self.assertEqual(assessment['snapshots']['website']['title'],'Example')
  self.assertFalse(any(item['clientId']==other for item in state['assessments']))
  with patch('server.surface_audit.collect',return_value={}):
   with self.assertRaises(Problem):self.action('assessment',{'clientId':cid,'urls':{'website':'javascript:alert(1)'}},editor)
   with self.assertRaises(Problem):self.action('assessment',{'clientId':cid,'urls':{}},editor)
if __name__=='__main__':unittest.main()
