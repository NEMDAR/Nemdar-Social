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
 const snapshots=assessment?.snapshots||{};
 const sources=auditSources.map(source=>({...source,url:urls[source.key]||'',present:Boolean(urls[source.key]),snapshot:snapshots[source.key]||null}));
 const present=sources.filter(source=>source.present);
 const inspected=sources.filter(source=>source.snapshot?.status==='available');
 const website=sources.find(source=>source.key==='website')?.snapshot;
 const connected=connections.filter(connection=>connectionActive(connection)&&accounts.some(account=>account.id===connection.account_id));
 const expired=connections.filter(connection=>connection.status==='expired'&&accounts.some(account=>account.id===connection.account_id));
 const level=connected.length?'verified':'surface';
 const metrics=[
  {group:'الحضور الرقمي',name:'القنوات الموجودة',status:'available',value:`${present.length} من ${auditSources.length} مصادر أُضيفت للتقييم`,confidence:'عالٍ',source:'الروابط التي أدخلها العميل'},
  {group:'الهوية',name:'قابلية اكتشاف الهوية العامة',status:connected.length||inspected.length?'available':present.length?'inferred':'unknown',value:connected.length?`${connected.length} حساب تم التحقق من هويته عبر المنصة`:inspected.length?`تمت قراءة العنوان والوصف العام من ${inspected.length} مصدر`:'الروابط محفوظة لكن المصادر لم تسمح بالقراءة العامة',confidence:connected.length?'عالٍ':inspected.length?'عالٍ':'منخفض',source:connected.length?'اتصال موثّق':'Public Collector'},
  {group:'رحلة العميل',name:'ترابط القنوات والـCTA',status:website?.status==='available'&&present.length>1?'available':urls.website&&present.length>1?'inferred':'unknown',value:website?.status==='available'?`الموقع: ${website.signals?.whatsApp?'WhatsApp ظاهر':'WhatsApp غير مكتشف'} · ${website.signals?.forms||0} نموذج · ${website.signals?.socialLinks||0} رابط سوشيال`:urls.website&&present.length>1?'الموقع موجود لكن القراءة العامة لم تكتمل':'أضف الموقع وقناة سوشيال واحدة على الأقل',confidence:website?.status==='available'?'عالٍ':urls.website?'متوسط':'غير متاح',source:'Public website scan'},
  {group:'الموقع',name:'جاهزية التحويل والقياس',status:website?.status==='available'?'available':'unknown',value:website?.status==='available'?`${website.signals?.mobileViewport?'Mobile ✓':'Mobile غير مكتشف'} · ${website.signals?.analytics?'Tracking ✓':'Tracking غير مكتشف'} · ${website.signals?.structuredData?'Structured Data ✓':'Structured Data غير مكتشف'}`:urls.website?'تعذرت قراءة الموقع من الخادم':'لم يُضف موقع',confidence:website?.status==='available'?'عالٍ':'غير متاح',source:'HTML public signals'},
  {group:'المحتوى',name:'تكرار النشر وأنواع المحتوى',status:'unknown',value:'جامع الملف العام لا يدّعي معرفة سجل المنشورات؛ يحتاج موصل منصة أو جامع محتوى معتمد',confidence:'غير متاح',source:'يتطلب بيانات المنشورات'},
  {group:'الأداء',name:'التفاعل الظاهر وأفضل المحتوى',status:'unknown',value:'لا نستخدم أرقامًا مستخرجة بشكل غير موثوق من صفحة الملف الشخصي',confidence:'غير متاح',source:'يتطلب بيانات محتوى موثوقة'},
  {group:'الأداء',name:'Reach · Impressions · Saves',status:'unknown',value:'غير متاح من الروابط العامة',confidence:'غير متاح',source:'يتطلب Basic Connect بصلاحيات Insights'},
  {group:'الجمهور',name:'العمر والموقع وأوقات النشاط',status:'unknown',value:'لن نخمن بيانات الجمهور من المتابعين أو التعليقات',confidence:'غير متاح',source:'يتطلب Basic Connect بصلاحيات Insights'},
  {group:'الإعلانات',name:'Spend · CTR · CPL · ROAS',status:'unknown',value:'حسابات الإعلانات غير موصّلة',confidence:'غير متاح',source:'يتطلب ربط Ad Account للقراءة'},
  {group:'التحويل',name:'Leads · Conversion Rate · Revenue',status:'unknown',value:'لا يمكن إثبات التحويل من بيانات السوشيال العامة',confidence:'غير متاح',source:'يتطلب Analytics + CRM'},
  {group:'الأمان',name:'حالة الاتصال',status:connected.length?'available':expired.length?'unknown':'unknown',value:connected.length?`${connected.length} اتصال صالح · قراءة الهوية مؤكدة${expired.length?` · ${expired.length} منتهي`:''}`:expired.length?`${expired.length} اتصال منتهي ويحتاج تجديد`:'لم تمنح NEMDAR أي صلاحية للحسابات حتى الآن',confidence:connected.length?'عالٍ':'غير متاح',source:'سجل الاتصالات'}
 ];
 const known=metrics.filter(metric=>metric.status==='available').length;
 const inferred=metrics.filter(metric=>metric.status==='inferred').length;
 const unknown=metrics.filter(metric=>metric.status==='unknown').length;
 return {level,sources,present,inspected,connected,expired,metrics,known,inferred,unknown,observedAt:snapshots.observedAt||'',coverage:Math.round((known+inferred*.45)/metrics.length*100)};
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
