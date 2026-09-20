export function readiness(state,clientId){
 const own=key=>(state[key]||[]).filter(x=>x.clientId===clientId);
 const posts=own('posts'),accounts=own('accounts');
 return [
 {title:'إضافة العميل',done:state.clients.some(c=>c.id===clientId),route:'accounts',detail:'ملف مستقل للعميل وعلاماته وحساباته.'},
 {title:'تسجيل الحسابات',done:accounts.length>0,route:'accounts',detail:`${accounts.length} حساب مسجل. تسجيل الحساب لا يمنح صلاحية النشر.`},
 {title:'تجهيز المحتوى',done:posts.length>0,route:'content',detail:`${posts.length} منشور في مساحة العميل.`},
 {title:'اعتماد أول محتوى',done:posts.some(p=>['approved','scheduled','published','partial'].includes(p.status)),route:'content',detail:'راجع المحتوى واعتمده قبل تحديد موعده.'},
 {title:'تحديد موعد النشر',done:posts.some(p=>p.scheduledAt&&['scheduled','published','partial'].includes(p.status)),route:'calendar',detail:'المواعيد بتوقيت دبي؛ حالة الإرسال مستقلة عن الجدولة.'},
 {title:'تفعيل الربط الخارجي',done:false,route:'connectors',detail:'موصل نصوص صفحات فيسبوك متاح للإعداد والإرسال اليدوي. نجاح الربط وحده لا يثبت صلاحية النشر.'}
 ];
}
