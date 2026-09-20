import test from 'node:test';
import assert from 'node:assert/strict';
import {dayKey,moveMonth,monthDays,datedPosts} from '../src/calendar.js';
test('Dubai midnight groups UTC evening into next day',()=>{assert.equal(dayKey('2026-09-30T20:30:00Z'),'2026-10-01');assert.equal(dayKey('invalid'),'');});
test('month navigation crosses years and includes leap day',()=>{assert.equal(moveMonth('2026-12',1),'2027-01');assert.equal(moveMonth('2026-01',-1),'2025-12');const days=monthDays('2024-02');assert.equal(days.length,42);assert.ok(days.includes('2024-02-29'));assert.equal(new Date(days[0]).getUTCDay(),0);});
test('calendar excludes cancelled drafts and includes published history in Dubai month',()=>{const posts=[{id:1,status:'scheduled',scheduledAt:'2026-09-30T20:30:00Z'},{id:2,status:'draft',scheduledAt:'2026-10-02T00:00:00Z'},{id:3,status:'published',scheduledAt:'2026-10-03T00:00:00Z'}];assert.deepEqual(datedPosts(posts,'2026-10').map(p=>p.id),[1,3]);assert.deepEqual(datedPosts(posts,'2026-09'),[]);});
