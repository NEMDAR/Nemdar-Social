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

test('audit links require valid http URLs',()=>{
 assert.deepEqual(validateAuditUrls({website:'https://example.com'}),{website:'https://example.com/'});
 assert.throws(()=>validateAuditUrls({instagram:'not-a-url'}),/غير صحيح/);
 assert.throws(()=>validateAuditUrls({}),/رابطاً واحداً/);
});
