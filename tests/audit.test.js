import test from 'node:test';
import assert from 'node:assert/strict';
import {displayMetricValue,presentAuditReport,presentDeltaItem,presentMaturity,presentPerformanceCard,presentRecommendation,presentScore,validateAuditUrls} from '../src/audit.js';

test('audit links require valid http URLs',()=>{
 assert.deepEqual(validateAuditUrls({website:'https://example.com'}),{website:'https://example.com/'});
 assert.throws(()=>validateAuditUrls({instagram:'not-a-url'}),/غير صحيح/);
 assert.throws(()=>validateAuditUrls({}),/رابطاً واحداً/);
});

test('presentation never converts unknown unavailable or stale into zero',()=>{
 assert.equal(displayMetricValue({status:'unknown',value:0,explanation:'لا توجد قيمة Reach'}),'لا توجد قيمة Reach');
 assert.equal(displayMetricValue({status:'unavailable',value:0,explanation:'Meta رفضت Reach'}),'Meta رفضت Reach');
 assert.equal(displayMetricValue({status:'stale',value:120,displayValue:'Reach 120 · بيانات قديمة'}),'Reach 120 · بيانات قديمة');
 assert.equal(displayMetricValue({status:'observed',value:0,displayValue:'0'}),'0');
 assert.equal(displayMetricValue({status:'observed',value:0}),'0');
});

test('presentAuditReport is display-only and keeps server scores',()=>{
 const view=presentAuditReport({
  level:'verified',
  scores:{coverageScore:40,confidenceScore:70,performanceScore:null,performanceExplanation:'لا توجد مقاييس أداء'},
  metrics:[{id:'reach',title:'Reach',status:'unknown',value:null,explanation:'غير متاح من الروابط العامة',sectionTitle:'الأداء'}],
  recommendations:[{title:'اربط حسابًا واحدًا للتحقق',route:'connectors',evidenceIds:['ev:identity']}]
 });
 assert.equal(view.level,'verified');
 assert.equal(view.coverageDisplay,'40%');
 assert.equal(view.performanceDisplay,'—');
 assert.equal(view.metrics[0].value,'غير متاح من الروابط العامة');
 assert.equal(view.metrics[0].numericValue,null);
 assert.equal(view.metrics[0].statusLabel,'غير معروف');
});

test('status labels cover observed inferred unknown unavailable and stale',()=>{
 const view=presentAuditReport({scores:{},metrics:[
  {id:'a',title:'A',status:'observed',value:0,displayValue:'0'},
  {id:'b',title:'B',status:'inferred',displayValue:'مستنتج'},
  {id:'c',title:'C',status:'unknown',explanation:'غير معروف'},
  {id:'d',title:'D',status:'unavailable',explanation:'غير متاح'},
  {id:'e',title:'E',status:'stale',value:9,displayValue:'9'}
 ]});
 assert.deepEqual(view.metrics.map(metric=>metric.statusLabel),['مرصود','مستنتج','غير معروف','غير متاح','قديم']);
 assert.equal(view.metrics[0].value,'0');
 assert.equal(view.metrics[2].numericValue,null);
});

test('null performance score is rendered as an explanation not a zero',()=>{
 assert.equal(presentScore(null),'—');
 assert.equal(presentScore(undefined),'—');
 assert.equal(presentScore(67),'67%');
});

test('maturity journey locks attributed unless the report level is attributed',()=>{
 const insights=presentMaturity('insights');
 assert.deepEqual(insights.map(stage=>[stage.id,stage.state]),[
  ['surface','completed'],['verified','completed'],['insights','current'],['attributed','locked']
 ]);
 const attributed=presentMaturity('attributed');
 assert.equal(attributed.at(-1).state,'current');
 assert.ok(attributed.slice(0,3).every(stage=>stage.state==='completed'));
});

test('performance KPI card uses unavailable copy instead of zero or red score',()=>{
 const missing=presentPerformanceCard(null,'لا توجد مقاييس أداء');
 assert.equal(missing.available,false);
 assert.equal(missing.display,'غير متاح حالياً');
 assert.match(missing.explanation,/لا توجد مقاييس أداء/);
 const ready=presentPerformanceCard(81);
 assert.equal(ready.available,true);
 assert.equal(ready.display,'81%');
});

test('delta presentation never invents growth from unknown or lost measurement',()=>{
 assert.equal(presentDeltaItem({kind:'newly_measured'}).changeLabel,'تم قياسه لأول مرة');
 assert.equal(presentDeltaItem({kind:'measurement_lost'}).changeLabel,'القياس غير متاح حالياً');
 assert.equal(presentDeltaItem({kind:'numeric',absolute:12,percent:10}).changeLabel,'+12 (+10%)');
});

test('recommendation CTA is mapped from engine ids and not generated',()=>{
 const rec=presentRecommendation({id:'rec_sync_insights',priority:2,title:'زامن Insights للمنصة',detail:'شغّل المزامنة',route:'connectors',evidenceIds:['ev:1']});
 assert.equal(rec.ctaLabel,'مزامنة Insights');
 assert.equal(rec.route,'connectors');
 assert.equal(rec.priorityLabel,'أولوية متوسطة');
});

test('presentAuditReport exposes performance card and grouped sections without changing scores',()=>{
 const view=presentAuditReport({
  level:'insights',
  scores:{coverageScore:55,confidenceScore:60,performanceScore:null,performanceExplanation:'لا توجد مقاييس أداء'},
  metrics:[{id:'reach',title:'Reach',status:'observed',value:100,displayValue:'100',section:'performance',sectionTitle:'الأداء'}],
  layers:[{id:'platform_insights',name:'Platform Insights',status:'ready'}],
  recommendations:[{id:'rec_connect',title:'اربط',route:'connectors',priority:1}]
 });
 assert.equal(view.performanceDisplay,'—');
 assert.equal(view.performanceCard.display,'غير متاح حالياً');
 assert.equal(view.metricSections[0].title,'الأداء');
 assert.equal(view.maturity.find(stage=>stage.state==='current').id,'insights');
 assert.equal(view.layers[0].statusLabel,'جاهز');
 assert.equal(view.recommendations[0].ctaLabel,'ربط حساب');
});
