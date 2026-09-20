import test from 'node:test';
import assert from 'node:assert/strict';
import {readiness} from '../src/readiness.js';
test('readiness isolates client data and never equates registration with live connection',()=>{
 const state={clients:[{id:'a'},{id:'b'}],accounts:[{clientId:'b',connectionStatus:'connected'}],posts:[{clientId:'b',status:'published',scheduledAt:'2026-01-01'}]};
 assert.deepEqual(readiness(state,'a').map(x=>x.done),[true,false,false,false,false,false]);
 assert.deepEqual(readiness(state,'b').map(x=>x.done),[true,true,true,true,true,false]);
});
test('cancelled draft with stale date does not count as scheduled or approved',()=>{
 const state={clients:[{id:'a'}],accounts:[],posts:[{clientId:'a',status:'draft',scheduledAt:'2026-01-01'}]};
 assert.deepEqual(readiness(state,'a').map(x=>x.done),[true,false,true,false,false,false]);
});
