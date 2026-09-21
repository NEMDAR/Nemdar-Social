"""Audit Intelligence Engine: evidence, scoring, recommendations, history, isolation."""
import json,os,tempfile,time,unittest
from datetime import datetime,timezone
from unittest.mock import patch
from server.app import App
from server.audit_engine import (
 aggregate_insight,compute_delta,generate_report,get_current,get_history,run_audit,sanitize
)
from server.audit_policy import META_INSIGHTS_MAX_AGE_SECONDS,POLICIES,PUBLIC_SURFACE_MAX_AGE_SECONDS
from server.core import Problem,Store

NOW=datetime(2026,9,21,12,tzinfo=timezone.utc).timestamp()

def iso(ts=NOW):
 return datetime.fromtimestamp(ts,timezone.utc).isoformat()

def workspace(**kwargs):
 base={'client':{'id':'c','name':'Client'},'assessment':None,'accounts':[],'connections':[],
       'posts':[],'jobs':[],'leads':[],'campaigns':[],'media':[],'insights':[],'attributionEvidence':None}
 base.update(kwargs);return base

def metric(report,mid):
 return next(item for item in report['metrics'] if item['id']==mid)

def evidence(report,eid):
 return next(item for item in report['evidence'] if item['id']==eid)

class EngineTests(unittest.TestCase):
 def test_missing_reach_is_unknown_not_zero(self):
  report=generate_report(workspace(assessment={'urls':{'instagram':'https://instagram.com/example','website':'https://example.com'}}),NOW)
  reach=metric(report,'reach')
  self.assertEqual(report['level'],'surface')
  self.assertEqual(reach['status'],'unknown')
  self.assertIsNone(reach['value'])
  self.assertNotEqual(reach['value'],0)
  self.assertTrue(report['unknown']>0)

 def test_rejected_reach_is_unavailable_not_zero(self):
  ws=workspace(
   accounts=[{'id':'ig-1','platform':'Instagram','externalId':'brand'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}],
   insights=[{'id':'insights-ig-1','accountId':'ig-1','status':'partial','syncedAt':iso(),'range':{'since':NOW-28*86400,'until':NOW,'days':28},
              'metrics':{},'unavailable':['reach'],'source':'Meta Graph API'}]
  )
  report=generate_report(ws,NOW);reach=metric(report,'reach')
  self.assertEqual(reach['status'],'unavailable');self.assertIsNone(reach['value'])

 def test_stale_insights_keep_value_and_are_not_zero(self):
  synced=iso(NOW-META_INSIGHTS_MAX_AGE_SECONDS-60)
  ws=workspace(
   accounts=[{'id':'ig-1','platform':'Instagram','externalId':'brand'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}],
   insights=[{'id':'insights-ig-1','accountId':'ig-1','status':'available','syncedAt':synced,'range':{'since':NOW-28*86400,'until':NOW,'days':28},
              'metrics':{'reach':{'value':120}},'unavailable':[],'source':'Meta Graph API'}]
  )
  report=generate_report(ws,NOW);reach=metric(report,'reach')
  self.assertEqual(reach['status'],'stale');self.assertEqual(reach['value'],120)

 def test_observed_zero_is_observed_zero(self):
  ws=workspace(
   accounts=[{'id':'ig-1','platform':'Instagram','externalId':'brand'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}],
   insights=[{'id':'insights-ig-1','accountId':'ig-1','status':'available','syncedAt':iso(),'range':{'since':NOW-28*86400,'until':NOW,'days':28},
              'metrics':{'reach':{'value':0}},'unavailable':[],'source':'Meta Graph API'}]
  )
  report=generate_report(ws,NOW);reach=metric(report,'reach');ev=evidence(report,'ev:insight:ig-1:reach')
  self.assertEqual(reach['status'],'observed');self.assertEqual(reach['value'],0);self.assertTrue(ev.get('zero'))

 def test_verified_does_not_invent_insights(self):
  ws=workspace(
   assessment={'urls':{'instagram':'https://instagram.com/example'}},
   accounts=[{'id':'ig-1','platform':'Instagram'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}]
  )
  report=generate_report(ws,NOW)
  self.assertEqual(report['level'],'verified')
  self.assertEqual(metric(report,'identity_discoverability')['status'],'observed')
  self.assertEqual(metric(report,'reach')['status'],'unknown')
  self.assertIsNone(metric(report,'reach')['value'])

 def test_surface_locks_internal_operations(self):
  ws=workspace(assessment={'urls':{'website':'https://example.com'}},
               posts=[{'status':'published'}],jobs=[{'state':'published'}],
               leads=[{'status':'qualified'}],campaigns=[{'status':'approved'}])
  report=generate_report(ws,NOW)
  self.assertEqual(report['level'],'surface')
  self.assertEqual(metric(report,'content_cycle')['status'],'unknown')
  self.assertEqual(next(l for l in report['layers'] if l['name']=='NEMDAR Operations')['status'],'locked')
  self.assertEqual(report['recommendations'][0]['route'],'connectors')
  self.assertIsNone(metric(report,'content_cycle')['value'])

 def test_verified_uses_first_party_ops_without_relabelling_analytics(self):
  ws=workspace(
   assessment={'urls':{'instagram':'https://instagram.com/example'}},
   accounts=[{'id':'ig-1','platform':'Instagram'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}],
   posts=[{'id':'p1','status':'published'},{'id':'p2','status':'scheduled'}],
   jobs=[{'state':'published'},{'state':'failed'},{'state':'published'}],
   leads=[{'status':'qualified'},{'status':'incomplete'}],
   campaigns=[{'status':'approved'},{'status':'draft'}],
   insights=[{'status':'partial','accountId':'ig-1','syncedAt':iso(),'range':{'since':NOW-28*86400,'until':NOW,'days':28},
              'metrics':{'reach':{'value':120},'engagements':{'value':15}},'unavailable':[]}]
  )
  report=generate_report(ws,NOW)
  self.assertEqual(report['level'],'insights')
  self.assertIn('2 محتوى',metric(report,'content_cycle')['displayValue'])
  self.assertIn('67%',metric(report,'publishing_reliability')['displayValue'])
  self.assertIn('1 مؤهل من 2',metric(report,'lead_quality')['displayValue'])
  self.assertEqual(metric(report,'reach')['status'],'observed')
  self.assertEqual(metric(report,'reach')['value'],120)
  self.assertEqual(next(l for l in report['layers'] if l['name']=='NEMDAR Operations')['status'],'ready')
  self.assertEqual(next(l for l in report['layers'] if l['name']=='Platform Insights')['status'],'ready')
  self.assertNotEqual(metric(report,'content_cycle')['provenance']['layer'],'platform_insights')

 def test_scores_are_separated_and_performance_is_nullable(self):
  surface=generate_report(workspace(assessment={'urls':{'website':'https://example.com'}}),NOW)
  self.assertIsInstance(surface['scores']['coverageScore'],int)
  self.assertIsNotNone(surface['scores']['coverageScore'])
  self.assertIsNone(surface['scores']['performanceScore'])
  self.assertIn('لا توجد مقاييس أداء',surface['scores']['performanceExplanation'])
  ws=workspace(
   accounts=[{'id':'ig-1','platform':'Instagram'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}],
   insights=[{'accountId':'ig-1','status':'available','syncedAt':iso(),'range':{'since':NOW-28*86400,'until':NOW,'days':28},
              'metrics':{'reach':{'value':500}},'unavailable':[]}]
  )
  only_reach=generate_report(ws,NOW)
  self.assertEqual(metric(only_reach,'reach')['status'],'observed')
  self.assertIsNone(only_reach['scores']['performanceScore'])
  self.assertGreater(only_reach['scores']['coverageScore'],surface['scores']['coverageScore'])

 def test_missing_metrics_do_not_reduce_performance_score(self):
  base=workspace(
   accounts=[{'id':'ig-1','platform':'Instagram'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}],
   jobs=[{'state':'published'},{'state':'published'},{'state':'failed'}]
  )
  with_ops=generate_report(base,NOW)
  with_unknown_reach=generate_report({**base,'insights':[]},NOW)
  self.assertEqual(with_ops['scores']['performanceScore'],67)
  self.assertEqual(with_unknown_reach['scores']['performanceScore'],67)
  self.assertEqual(metric(with_unknown_reach,'reach')['status'],'unknown')

 def test_section_scores_are_independently_nullable(self):
  report=generate_report(workspace(assessment={'urls':{'website':'https://example.com'}}),NOW)
  ads=next(s for s in report['scores']['sectionScores'] if s['id']=='ads')
  ops=next(s for s in report['scores']['sectionScores'] if s['id']=='operations')
  self.assertIsNone(ads['performanceScore']);self.assertIsNone(ops['performanceScore'])

 def test_attributed_requires_real_analytics_and_crm_and_is_not_faked(self):
  ws=workspace(
   accounts=[{'id':'ig-1','platform':'Instagram'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}],
   leads=[{'status':'qualified'}],
   insights=[{'accountId':'ig-1','status':'available','syncedAt':iso(),'metrics':{'reach':{'value':10}},'unavailable':[]}]
  )
  report=generate_report(ws,NOW)
  self.assertEqual(report['level'],'insights')
  self.assertNotEqual(report['level'],'attributed')
  self.assertEqual(metric(report,'conversion_revenue')['status'],'unknown')
  supported=generate_report({**ws,'attributionEvidence':{'crm':'linked','analytics':'ga4'},
    'assessment':{'urls':{'website':'https://example.com'},'snapshots':{'website':{'status':'available','signals':{'analytics':True}},'observedAt':iso()}}},NOW)
  self.assertEqual(supported['level'],'attributed')

 def test_recommend_connect_only_when_unverified(self):
  bare=generate_report(workspace(assessment={'urls':{'website':'https://example.com'}}),NOW)
  self.assertEqual(bare['recommendations'][0]['id'],'rec_connect')
  verified=generate_report(workspace(
   accounts=[{'id':'ig-1','platform':'Instagram'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}]
  ),NOW)
  self.assertFalse(any(item['id']=='rec_connect' for item in verified['recommendations']))
  self.assertTrue(any(item['id']=='rec_sync_insights' for item in verified['recommendations']))

 def test_recommend_publishing_failure_and_conversion_unverified(self):
  report=generate_report(workspace(
   accounts=[{'id':'ig-1','platform':'Instagram'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}],
   posts=[{'status':'published'}],jobs=[{'state':'failed'}]
  ),NOW)
  ids=[item['id'] for item in report['recommendations']]
  self.assertIn('rec_publish_fail',ids)
  self.assertIn('rec_conversion',ids)
  conversion=next(item for item in report['recommendations'] if item['id']=='rec_conversion')
  self.assertIn('لا يعني أن أداء التحويل سيئ',conversion['detail'])
  self.assertTrue(all(item.get('evidenceIds') for item in report['recommendations']))

 def test_recommendations_max_five_and_deduped(self):
  report=generate_report(workspace(
   assessment={'urls':{'website':'https://example.com','instagram':'https://instagram.com/x'},
               'snapshots':{'website':{'status':'available','signals':{'analytics':False}},'observedAt':iso()}},
   accounts=[{'id':'ig-1','platform':'Instagram'}],
   connections=[{'account_id':'ig-1','status':'identity_verified','platform':'Instagram','expires':NOW+3600,'verified_at':iso()}],
   posts=[],jobs=[{'state':'failed'}],leads=[],campaigns=[{'status':'draft'}]
  ),NOW)
  self.assertLessEqual(len(report['recommendations']),5)
  families=[item['id'] for item in report['recommendations']]
  self.assertEqual(len(families),len(set(families)))
  self.assertFalse(any(item['id']=='rec_connect' for item in report['recommendations']))

 def test_delta_rules(self):
  previous={'id':'old','metrics':[
   {'id':'reach','title':'Reach','status':'unknown','value':None,'unit':'count','period':{'days':28,'since':NOW-28*86400,'until':NOW}},
   {'id':'impressions','title':'Impressions','status':'observed','value':100,'unit':'count','period':{'days':28,'since':NOW-28*86400,'until':NOW}},
   {'id':'engagements','title':'Engagements','status':'observed','value':10,'unit':'count','period':{'days':28,'since':NOW-28*86400,'until':NOW}},
   {'id':'followers','title':'Followers','status':'observed','value':20,'unit':'count','period':{'days':7}}
  ]}
  current=[
   {'id':'reach','title':'Reach','status':'observed','value':50,'unit':'count','period':{'days':28,'since':NOW-28*86400,'until':NOW}},
   {'id':'impressions','title':'Impressions','status':'unknown','value':None,'unit':'count','period':{'days':28,'since':NOW-28*86400,'until':NOW}},
   {'id':'engagements','title':'Engagements','status':'observed','value':12,'unit':'count','period':{'days':28,'since':NOW-28*86400,'until':NOW}},
   {'id':'followers','title':'Followers','status':'observed','value':25,'unit':'count','period':{'days':28}}
  ]
  delta={item['metricId']:item for item in compute_delta(current,previous)}
  self.assertEqual(delta['reach']['kind'],'newly_measured');self.assertIsNone(delta['reach']['percent'])
  self.assertEqual(delta['impressions']['kind'],'measurement_lost');self.assertIsNone(delta['impressions']['percent'])
  self.assertEqual(delta['engagements']['kind'],'numeric');self.assertEqual(delta['engagements']['absolute'],2)
  self.assertEqual(delta['followers']['kind'],'incompatible')

 def test_followers_are_not_summed_as_a_trend(self):
  items=[
   {'id':'a','kind':'insight_metric','metricName':'followers','status':'observed','value':10,'unit':'count','accountId':'a','period':{'days':28,'since':1,'until':2}},
   {'id':'b','kind':'insight_metric','metricName':'followers','status':'observed','value':15,'unit':'count','accountId':'b','period':{'days':28,'since':1,'until':2}}
  ]
  result=aggregate_insight(items,'followers')
  self.assertEqual(result['aggregation'],'per_account');self.assertIsNone(result['value'])

 def test_additive_metrics_sum_only_when_compatible_and_complete(self):
  compatible=[
   {'id':'a','kind':'insight_metric','metricName':'reach','status':'observed','value':10,'unit':'count','accountId':'a','period':{'days':28,'since':NOW-28*86400,'until':NOW}},
   {'id':'b','kind':'insight_metric','metricName':'reach','status':'observed','value':5,'unit':'count','accountId':'b','period':{'days':28,'since':NOW-28*86400,'until':NOW}}
  ]
  summed=aggregate_insight(compatible,'reach')
  self.assertEqual(summed['aggregation'],'sum');self.assertEqual(summed['value'],15)
  incomplete=compatible+[{'id':'c','kind':'insight_metric','metricName':'reach','status':'unknown','value':None,'unit':'count','accountId':'c','period':{'days':28,'since':NOW-28*86400,'until':NOW}}]
  partial=aggregate_insight(incomplete,'reach')
  self.assertEqual(partial['aggregation'],'per_account');self.assertIsNone(partial['value'])
  mismatched=[compatible[0],{**compatible[1],'period':{'days':7,'since':NOW-7*86400,'until':NOW}}]
  self.assertEqual(aggregate_insight(mismatched,'reach')['aggregation'],'per_account')

 def test_expired_connection_is_not_verified(self):
  report=generate_report(workspace(
   accounts=[{'id':'ig-1','platform':'Instagram'}],
   connections=[{'account_id':'ig-1','status':'expired','platform':'Instagram','expires':NOW-10,'verified_at':iso(NOW-86400)}]
  ),NOW)
  self.assertEqual(report['level'],'surface')
  self.assertEqual(metric(report,'connection_security')['status'],'unavailable')
  self.assertTrue(any(item['id']=='rec_connect' or item['id']=='rec_renew' for item in report['recommendations']))

 def test_surface_snapshot_older_than_seven_days_is_stale(self):
  report=generate_report(workspace(assessment={'urls':{'website':'https://example.com','instagram':'https://instagram.com/x'},
   'snapshots':{'website':{'status':'available','title':'Example','signals':{'analytics':True,'forms':1}},'observedAt':iso(NOW-PUBLIC_SURFACE_MAX_AGE_SECONDS-10)}}),NOW)
  website=metric(report,'website_conversion_readiness')
  self.assertEqual(website['status'],'stale')

 def test_unknown_metrics_are_never_serialized_as_zero(self):
  report=generate_report(workspace(assessment={'urls':{'website':'https://example.com'}}),NOW)
  for item in report['metrics']:
   if item['status'] in ('unknown','unavailable'):
    self.assertIsNot(item['value'],0)
    self.assertNotEqual(item['value'],0)
  for item in report['evidence']:
   if item['status'] in ('unknown','unavailable'):
    self.assertNotEqual(item.get('value'),0)

 def test_freshness_policies_are_centralized(self):
  self.assertEqual(POLICIES['public_surface']['maxAgeSeconds'],7*86400)
  self.assertEqual(POLICIES['meta_insights']['maxAgeSeconds'],48*3600)
  self.assertEqual(POLICIES['verified_identity']['mode'],'until_disconnect')
  self.assertEqual(POLICIES['first_party']['mode'],'generation_time')
  self.assertEqual(PUBLIC_SURFACE_MAX_AGE_SECONDS,7*86400)

 def test_sanitize_strips_secrets_and_token_strings(self):
  cleaned=sanitize({'token':'private-facebook-token','metrics':{'reach':1},'note':'Authorization: Bearer abc.def','nested':{'cipher':'abc'}})
  self.assertNotIn('token',cleaned);self.assertNotIn('cipher',cleaned['nested'])
  self.assertNotIn('private-facebook-token',json.dumps(cleaned))
  report=generate_report(workspace(),NOW)
  blob=json.dumps(report)
  for word in ('token','cipher','password','csrf'):
   self.assertNotIn('"'+word+'"',blob)

 def test_every_inferred_result_has_a_named_rule(self):
  report=generate_report(workspace(assessment={'urls':{'website':'https://example.com','instagram':'https://instagram.com/x'}}),NOW)
  inferred=[m for m in report['metrics'] if m['status']=='inferred']
  self.assertTrue(inferred)
  self.assertTrue(all(m.get('rule') for m in inferred))
  self.assertTrue(all(e.get('provenance') for e in report['evidence']))

class AuditApiTests(unittest.TestCase):
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
 def user(self,role,cids):
  import uuid
  email=uuid.uuid4().hex+'@example.com';self.action('user',{'email':email,'password':'Another-good-password','name':role,'role':role,'clients':cids});token,_=self.store.login(email,'Another-good-password','test');return self.store.session(token),token
 def request(self,path,method='GET',body=None,token=None,csrf=None,origin='http://localhost:8080'):
  import io
  raw=json.dumps(body or {}).encode();env={'PATH_INFO':path.split('?')[0],'REQUEST_METHOD':method,'HTTP_ORIGIN':origin,'HTTP_COOKIE':'session='+(token or ''),'HTTP_X_CSRF_TOKEN':csrf or self.csrf,'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),'REMOTE_ADDR':'test','QUERY_STRING':path.split('?')[1] if '?' in path else ''}
  result={}
  def start(status,headers):result.update(status=int(status.split()[0]),headers=dict(headers))
  result['body']=b''.join(self.app(env,start));return result
 def test_schema_preserves_existing_rows(self):
  cid,_=self.client('Keep me')
  reopened=Store(self.path)
  names=[c['name'] for c in reopened.state(self.admin)['clients']]
  self.assertIn('Keep me',names)
  with reopened.db() as db:
   db.execute('SELECT id FROM audit_runs LIMIT 1')
 def test_assessment_persists_immutable_audit_run(self):
  cid,_=self.client()
  snapshots={'website':{'status':'available','title':'Example','signals':{'analytics':True}},'observedAt':iso()}
  with patch('server.surface_audit.collect',return_value=snapshots):
   self.action('assessment',{'clientId':cid,'urls':{'website':'https://example.com'}})
  current=get_current(self.store,self.admin,cid)
  self.assertEqual(current['current']['level'],'surface')
  first_id=current['current']['id']
  run_audit(self.store,self.admin,cid,now=NOW)
  pair=get_current(self.store,self.admin,cid)
  self.assertNotEqual(pair['current']['id'],first_id)
  self.assertEqual(pair['previous']['id'],first_id)
  history=get_history(self.store,self.admin,cid)
  self.assertGreaterEqual(len(history['items']),2)
  with self.store.db() as db:
   rows=db.execute('SELECT report FROM audit_runs WHERE id=?',(first_id,)).fetchone()
   stored=json.loads(rows['report'])
  self.assertEqual(stored['id'],first_id)
 def test_tenant_isolation_on_audit_endpoints(self):
  cid,_=self.client('A');other,_=self.client('B');editor,token=self.user('editor',[cid])
  run_audit(self.store,self.admin,other,now=NOW)
  with self.assertRaises(Problem) as err:get_current(self.store,editor,other)
  self.assertEqual(err.exception.status,403)
  r=self.request('/api/audit?clientId='+other,token=token,csrf=editor['csrf'])
  self.assertEqual(r['status'],403)
  r=self.request('/api/audit/history?clientId='+other,token=token,csrf=editor['csrf'])
  self.assertEqual(r['status'],403)
  r=self.request('/api/audit/run','POST',{'clientId':other},token=token,csrf=editor['csrf'])
  self.assertEqual(r['status'],403)
  allowed=self.request('/api/audit?clientId='+cid,token=token,csrf=editor['csrf'])
  self.assertEqual(allowed['status'],200)
 def test_viewer_can_read_but_not_run(self):
  cid,_=self.client();viewer,token=self.user('viewer',[cid])
  run_audit(self.store,self.admin,cid,now=NOW)
  r=self.request('/api/audit?clientId='+cid,token=token,csrf=viewer['csrf'])
  self.assertEqual(r['status'],200)
  denied=self.request('/api/audit/run','POST',{'clientId':cid},token=token,csrf=viewer['csrf'])
  self.assertEqual(denied['status'],403)
 def test_csrf_and_origin_on_run(self):
  cid,_=self.client()
  self.assertEqual(self.request('/api/audit/run','POST',{'clientId':cid},token=self.token,csrf='bad')['status'],403)
  self.assertEqual(self.request('/api/audit/run','POST',{'clientId':cid},token=self.token,origin='https://evil.example')['status'],403)
 def test_audit_json_never_contains_connection_tokens(self):
  cid,bid=self.client()
  state=self.action('account',{'clientId':cid,'brandId':bid,'platform':'Facebook','externalId':'page'})
  os.environ['VAULT_KEY']='ab'*32
  from server.facebook import connect
  account=state['accounts'][-1]
  connect(self.store,self.admin,{'accountId':account['id'],'pageId':'123','token':'private-facebook-token','version':'v25.0','expires':time.time()+3600},lambda *_:{'id':'123','name':'Page','category':'Business'})
  payload=run_audit(self.store,self.admin,cid,now=NOW)
  blob=json.dumps(payload)
  self.assertNotIn('private-facebook-token',blob)
  self.assertNotIn('cipher',blob)
  r=self.request('/api/audit?clientId='+cid,token=self.token)
  self.assertNotIn(b'private-facebook-token',r['body'])
  self.assertEqual(self.request('/api/health')['status'],200)
  self.assertEqual(json.loads(self.request('/api/health')['body'])['version'],'0.9.0')
 def test_reviewer_cannot_run_audit(self):
  cid,_=self.client();reviewer,_=self.user('reviewer',[cid])
  with self.assertRaises(Problem) as err:run_audit(self.store,reviewer,cid)
  self.assertEqual(err.exception.status,403)
 def test_unauthenticated_audit_is_rejected(self):
  self.assertEqual(self.request('/api/audit?clientId=x')['status'],401)

if __name__=='__main__':unittest.main()
