import test from 'node:test';
import assert from 'node:assert/strict';
import {buildAuditReport,validateAuditUrls} from '../src/audit.js';

test('surface audit exposes unknown internal metrics',()=>{
 const report=buildAuditReport({urls:{instagram:'https://instagram.com/example',website:'https://example.com'}},[],[]);
 assert.equal(report.level,'surface');
 assert.equal(report.present.length,2);
 assert.ok(report.metrics.some(metric=>metric.name.includes('Reach')&&metric.status==='unknown'));
 assert.ok(report.unknown>0);
});

test('verified connection upgrades the report without inventing insights',()=>{
 const accounts=[{id:'ig-1',platform:'Instagram'}];
 const connections=[{account_id:'ig-1',status:'identity_verified',platform:'Instagram'}];
 const report=buildAuditReport({urls:{instagram:'https://instagram.com/example'}},accounts,connections);
 assert.equal(report.level,'verified');
 assert.equal(report.connected.length,1);
 assert.equal(report.metrics.find(metric=>metric.name==='قابلية اكتشاف الهوية العامة').status,'available');
 assert.equal(report.metrics.find(metric=>metric.name.includes('Reach')).status,'unknown');
});

test('verified audit uses first-party operations without relabelling them as platform analytics',()=>{
 const accounts=[{id:'ig-1',platform:'Instagram'}];
 const connections=[{account_id:'ig-1',status:'identity_verified',platform:'Instagram'}];
 const workspace={
  posts:[{id:'p1',status:'published'},{id:'p2',status:'scheduled'}],
  jobs:[{state:'published'},{state:'failed'},{state:'published'}],
  leads:[{status:'qualified'},{status:'incomplete'}],
  campaigns:[{status:'approved'},{status:'draft'}],
  media:[]
 };
 const report=buildAuditReport({urls:{instagram:'https://instagram.com/example'}},accounts,connections,workspace);
 assert.equal(report.evidence.deliveryRate,67);
 assert.match(report.metrics.find(metric=>metric.name==='دورة المحتوى داخل NEMDAR').value,/2 محتوى/);
 assert.match(report.metrics.find(metric=>metric.name==='موثوقية تسليم النشر').value,/67%/);
 assert.match(report.metrics.find(metric=>metric.name==='جودة وتأهيل الليدز').value,/1 مؤهل من 2/);
 assert.equal(report.metrics.find(metric=>metric.name.includes('Reach')).status,'unknown');
 assert.equal(report.layers.find(layer=>layer.name==='NEMDAR Operations').status,'ready');
});

test('surface audit keeps internal operations locked until identity is verified',()=>{
 const workspace={posts:[{status:'published'}],jobs:[{state:'published'}],leads:[{status:'qualified'}],campaigns:[{status:'approved'}]};
 const report=buildAuditReport({urls:{website:'https://example.com'}},[],[],workspace);
 assert.equal(report.level,'surface');
 assert.equal(report.metrics.find(metric=>metric.name==='دورة المحتوى داخل NEMDAR').status,'unknown');
 assert.equal(report.layers.find(layer=>layer.name==='NEMDAR Operations').status,'locked');
 assert.equal(report.recommendations[0].route,'connectors');
});

test('audit links require valid http URLs',()=>{
 assert.deepEqual(validateAuditUrls({website:'https://example.com'}),{website:'https://example.com/'});
 assert.throws(()=>validateAuditUrls({instagram:'not-a-url'}),/غير صحيح/);
 assert.throws(()=>validateAuditUrls({}),/رابطاً واحداً/);
});
