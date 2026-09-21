import test from 'node:test';
import assert from 'node:assert/strict';
import {instagramTutorial} from '../src/instagram-tutorial.js';

test('Instagram tutorial includes professional-account publishing and insights flow',()=>{const html=instagramTutorial();for(const value of ['Instagram Professional','instagram_basic','instagram_content_publish','instagram_manage_insights','pages_show_list','pages_read_engagement','instagram_business_account{id,username}','مزامنة Insights','صورة JPEG/PNG واحدة'])assert.ok(html.includes(value),value);});
test('Instagram external links prevent opener access',()=>{const html=instagramTutorial();assert.equal((html.match(/target="_blank"/g)||[]).length,(html.match(/rel="noopener noreferrer"/g)||[]).length);});
