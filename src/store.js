import {addAccount,qualify,schedule} from './workflow.js';
export const platforms=['Facebook','Instagram','WhatsApp Business','Threads','YouTube','LinkedIn','Pinterest','TikTok','X','Google Business Profile'];
export const initialState=()=>({version:1,clients:[{id:'demo',name:'مجموعة المدار التجارية',brand:'أوربان لايف للأزياء',contact:'',brief:'أزياء وتجزئة في الإمارات'}],accounts:[{id:'ig1',clientId:'demo',platform:'Instagram',externalId:'UrbanLife.DXB',connectionStatus:'not_connected'},{id:'ig2',clientId:'demo',platform:'Instagram',externalId:'UrbanLife.AJM',connectionStatus:'not_connected'}],posts:[],leads:[],audit:[]});
const required=(v,label)=>{if(typeof v!=='string'||!v.trim())throw new Error(`أدخل ${label}`);return v.trim();};
export function update(state,action,payload,now=new Date()){
 const s=structuredClone(state), id=payload.id||crypto.randomUUID();
 const client=()=>{if(!s.clients.some(c=>c.id===payload.clientId))throw new Error('العميل غير موجود');};
 if(action==='client')s.clients.push({id,name:required(payload.name,'اسم العميل'),brand:required(payload.brand,'العلامة التجارية'),contact:payload.contact||'',brief:payload.brief||''});
 else if(action==='account'){client();if(!platforms.includes(payload.platform))throw new Error('المنصة غير مدعومة');s.accounts=addAccount(s.accounts,{id,clientId:payload.clientId,platform:payload.platform,externalId:required(payload.externalId,'معرّف الحساب').replace(/^@/,'')});}
 else if(action==='post'){
  client();const accountIds=[...new Set(payload.accountIds||[])];
  if(!accountIds.length||accountIds.some(a=>!s.accounts.some(x=>x.id===a&&x.clientId===payload.clientId)))throw new Error('اختر حساباً تابعاً للعميل');
  s.posts.push({id,clientId:payload.clientId,title:required(payload.title,'عنوان المحتوى'),body:required(payload.body,'نص المحتوى'),accountIds,status:'draft',createdAt:now.toISOString()});
 }else if(['review','approve','schedule','cancel'].includes(action)){
  const p=s.posts.find(p=>p.id===id&&p.clientId===payload.clientId);if(!p)throw new Error('المحتوى غير موجود');
  if(action==='review'){if(p.status!=='draft')throw new Error('المسودة فقط يمكن إرسالها للمراجعة');p.status='review';}
  if(action==='approve'){if(p.status!=='review')throw new Error('أرسل المحتوى للمراجعة أولاً');p.status='approved';}
  if(action==='schedule')Object.assign(p,schedule(p,payload.when,now));
  if(action==='cancel'){if(p.status!=='scheduled')throw new Error('المحتوى غير مجدول');p.status='approved';delete p.scheduledAt;}
 }else if(action==='lead'){
  client();const criteria={};for(const k of ['budget','authority','need','timeline'])criteria[k]=payload[k]==='yes'?true:payload[k]==='no'?false:null;
  const existing=s.leads.find(l=>l.id===id&&l.clientId===payload.clientId);
  const lead={id,clientId:payload.clientId,name:required(payload.name,'اسم الليد'),notes:payload.notes||'',criteria,status:qualify(criteria)};
  if(existing)Object.assign(existing,lead);else s.leads.push(lead);
 }else throw new Error('إجراء غير معروف');
 s.audit.unshift({id:crypto.randomUUID(),action,entityId:id,clientId:payload.clientId||id,at:now.toISOString()});
 return s;
}
export function readState(storage){const raw=storage.getItem('nemdar-social-v1');if(!raw)return initialState();const s=JSON.parse(raw);if(s.version!==1||!['clients','accounts','posts','leads','audit'].every(k=>Array.isArray(s[k])))throw new Error('تعذر قراءة البيانات المحفوظة؛ لم يتم استبدالها.');return s;}
export function persist(storage,state){storage.setItem('nemdar-social-v1',JSON.stringify(state));}
