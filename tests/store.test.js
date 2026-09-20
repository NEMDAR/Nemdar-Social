import {test} from 'node:test';
import assert from 'node:assert/strict';
import {initialState,update,readState,persist} from '../src/store.js';
const now=new Date('2026-09-20T10:00:00Z');
const draft=s=>update(s,'post',{id:'p',clientId:'demo',title:'تشكيلة الخريف',body:'أهلاً بالخريف',accountIds:['ig1','ig2']},now);
test('complete draft → review → approval → schedule → cancel lifecycle',()=>{
 let s=draft(initialState());s=update(s,'review',{id:'p',clientId:'demo'},now);s=update(s,'approve',{id:'p',clientId:'demo'},now);
 s=update(s,'schedule',{id:'p',clientId:'demo',when:'2026-09-21T12:00:00+04:00'},now);
 assert.equal(s.posts[0].scheduledAt,'2026-09-21T08:00:00.000Z');assert.equal(s.posts[0].status,'scheduled');
 s=update(s,'cancel',{id:'p',clientId:'demo'},now);assert.equal(s.posts[0].status,'approved');assert.equal(s.posts[0].scheduledAt,undefined);assert.equal(s.audit.length,5);
});
test('cannot cross client boundaries or select another client account',()=>{
 let s=update(initialState(),'client',{id:'c2',name:'شركة أخرى',brand:'علامة أخرى'});
 assert.throws(()=>update(s,'post',{clientId:'c2',title:'t',body:'b',accountIds:['ig1']}));
 s=draft(s);assert.throws(()=>update(s,'review',{id:'p',clientId:'c2'}));
});
test('cannot skip review, schedule without approval, or schedule in the past',()=>{
 const s=draft(initialState());assert.throws(()=>update(s,'approve',{id:'p',clientId:'demo'}));assert.throws(()=>update(s,'schedule',{id:'p',clientId:'demo',when:'2030-01-01'}));
 const approved=update(update(s,'review',{id:'p',clientId:'demo'}),'approve',{id:'p',clientId:'demo'});
 assert.throws(()=>update(approved,'schedule',{id:'p',clientId:'demo',when:'2020-01-01'},now));
});
test('duplicate account is rejected while second account on same platform is accepted',()=>{
 const p={clientId:'demo',platform:'Instagram',externalId:'@UrbanLife.DXB'};
 assert.throws(()=>update(initialState(),'account',p));const s=update(initialState(),'account',{...p,externalId:'New.Account'});assert.equal(s.accounts.length,3);assert.equal(s.accounts[2].connectionStatus,'not_connected');
});
test('lead criteria can be completed later without creating duplicate lead',()=>{
 let s=update(initialState(),'lead',{id:'l',clientId:'demo',name:'عميل محتمل',budget:'yes',need:'yes'});assert.equal(s.leads[0].status,'incomplete');
 s=update(s,'lead',{id:'l',clientId:'demo',name:'عميل محتمل',budget:'yes',need:'yes',authority:'yes',timeline:'yes'});assert.equal(s.leads.length,1);assert.equal(s.leads[0].status,'qualified');
});
test('failed validation leaves original data intact',()=>{const s=initialState(),before=JSON.stringify(s);assert.throws(()=>update(s,'post',{clientId:'demo',title:' ',body:'x',accountIds:['ig1']}));assert.equal(JSON.stringify(s),before);});
test('state survives persistence; corrupted data is not silently overwritten',()=>{let value=null;const storage={getItem:()=>value,setItem:(_,v)=>value=v};const s=draft(initialState());persist(storage,s);assert.deepEqual(readState(storage),s);value='corrupt';assert.throws(()=>readState(storage));assert.equal(value,'corrupt');});
