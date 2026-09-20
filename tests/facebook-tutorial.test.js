import test from 'node:test';
import assert from 'node:assert/strict';
import {facebookTutorial} from '../src/facebook-tutorial.js';

test('Facebook tutorial includes the complete safe manual flow',()=>{
 const html=facebookTutorial();
 for(const value of ['developers.facebook.com/apps/','developers.facebook.com/tools/explorer/','developers.facebook.com/tools/debug/accesstoken/','pages_show_list','pages_read_engagement','pages_manage_posts','/me/accounts?fields=id,name,access_token','لا ترسل كلمة مرور'])assert.ok(html.includes(value),value);
 assert.equal((html.match(/<li>/g)||[]).length>=7,true);
});

test('external tutorial links prevent opener access',()=>{
 const html=facebookTutorial();
 assert.equal((html.match(/target="_blank"/g)||[]).length,(html.match(/rel="noopener noreferrer"/g)||[]).length);
});
