import test from 'node:test';
import assert from 'node:assert/strict';
import {displayMetricValue,presentAuditReport,presentScore,validateAuditUrls} from '../src/audit.js';

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
