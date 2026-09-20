export const auditSources=[
 {key:'website',label:'الموقع الإلكتروني',hint:'https://example.com'},
 {key:'instagram',label:'Instagram',hint:'https://instagram.com/brand'},
 {key:'facebook',label:'Facebook',hint:'https://facebook.com/brand'},
 {key:'tiktok',label:'TikTok',hint:'https://tiktok.com/@brand'},
 {key:'linkedin',label:'LinkedIn',hint:'https://linkedin.com/company/brand'},
 {key:'youtube',label:'YouTube',hint:'https://youtube.com/@brand'},
 {key:'googleBusiness',label:'Google Business',hint:'https://maps.google.com/...'}
];

const connectionActive=c=>c.status==='identity_verified';

export function buildAuditReport(assessment,accounts=[],connections=[]){
 const urls=assessment?.urls||{};
 const sources=auditSources.map(source=>({...source,url:urls[source.key]||'',present:Boolean(urls[source.key])}));
 const present=sources.filter(source=>source.present);
 const connected=connections.filter(connection=>connectionActive(connection)&&accounts.some(account=>account.id===connection.account_id));
 const expired=connections.filter(connection=>connection.status==='expired'&&accounts.some(account=>account.id===connection.account_id));
 const level=connected.length?'verified':'surface';
 const metrics=[
  {group:'الحضور الرقمي',name:'القنوات الموجودة',status:'available',value:`${present.length} من ${auditSources.length} مصادر أُضيفت للتقييم`,confidence:'عالٍ',source:'الروابط التي أدخلها العميل'},
  {group:'الهوية',name:'تطابق هوية الحساب',status:connected.length?'available':present.length>1?'inferred':'unknown',value:connected.length?`${connected.length} حساب تم التحقق من هويته عبر المنصة`:present.length>1?'يمكن مقارنة أسماء الحسابات والروابط العامة بعد تشغيل جامع البيانات':'أضف أكثر من قناة أو وصّل الحسابات',confidence:connected.length?'عالٍ':present.length>1?'متوسط':'غير متاح',source:connected.length?'اتصال موثّق':'إشارات عامة'},
  {group:'رحلة العميل',name:'ترابط القنوات والـCTA',status:urls.website&&present.length>1?'inferred':'unknown',value:urls.website&&present.length>1?'يمكن فحص انتقال العميل بين السوشيال والموقع':'أضف الموقع وقناة سوشيال واحدة على الأقل',confidence:urls.website&&present.length>1?'متوسط':'غير متاح',source:'الروابط العامة'},
  {group:'المحتوى',name:'تكرار النشر وأنواع المحتوى',status:'inferred',value:'يتطلب جمع عينة المحتوى العام من كل منصة قبل احتساب النتيجة',confidence:'متوسط بعد الجمع',source:'المحتوى العام'},
  {group:'الأداء',name:'التفاعل الظاهر وأفضل المحتوى',status:'inferred',value:'يمكن قياس الإشارات العامة فقط؛ لا تساوي Reach أو Engagement الداخلي',confidence:'متوسط بعد الجمع',source:'Likes / Comments / Views العامة'},
  {group:'الأداء',name:'Reach · Impressions · Saves',status:'unknown',value:'غير متاح من الروابط العامة',confidence:'غير متاح',source:'يتطلب Basic Connect بصلاحيات Insights'},
  {group:'الجمهور',name:'العمر والموقع وأوقات النشاط',status:'unknown',value:'لن نخمن بيانات الجمهور من المتابعين أو التعليقات',confidence:'غير متاح',source:'يتطلب Basic Connect بصلاحيات Insights'},
  {group:'الإعلانات',name:'Spend · CTR · CPL · ROAS',status:'unknown',value:'حسابات الإعلانات غير موصّلة',confidence:'غير متاح',source:'يتطلب ربط Ad Account للقراءة'},
  {group:'التحويل',name:'Leads · Conversion Rate · Revenue',status:'unknown',value:'لا يمكن إثبات التحويل من بيانات السوشيال العامة',confidence:'غير متاح',source:'يتطلب Analytics + CRM'},
  {group:'الأمان',name:'حالة الاتصال',status:connected.length?'available':expired.length?'unknown':'unknown',value:connected.length?`${connected.length} اتصال صالح · قراءة الهوية مؤكدة${expired.length?` · ${expired.length} منتهي`:''}`:expired.length?`${expired.length} اتصال منتهي ويحتاج تجديد`:'لم تمنح NEMDAR أي صلاحية للحسابات حتى الآن',confidence:connected.length?'عالٍ':'غير متاح',source:'سجل الاتصالات'}
 ];
 const known=metrics.filter(metric=>metric.status==='available').length;
 const inferred=metrics.filter(metric=>metric.status==='inferred').length;
 const unknown=metrics.filter(metric=>metric.status==='unknown').length;
 return {level,sources,present,connected,expired,metrics,known,inferred,unknown,coverage:Math.round((known+inferred*.45)/metrics.length*100)};
}

export function validateAuditUrls(urls){
 const cleaned={};
 for(const source of auditSources){
  const raw=String(urls?.[source.key]||'').trim();
  if(!raw)continue;
  let parsed;
  try{parsed=new URL(raw);}catch{throw new Error(`رابط ${source.label} غير صحيح`);}
  if(!['http:','https:'].includes(parsed.protocol)||!parsed.hostname)throw new Error(`رابط ${source.label} غير صحيح`);
  cleaned[source.key]=parsed.toString();
 }
 if(!Object.keys(cleaned).length)throw new Error('أضف رابطاً واحداً على الأقل لبدء التقييم');
 return cleaned;
}
