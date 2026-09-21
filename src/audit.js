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
const list=value=>Array.isArray(value)?value:[];
const metric=(group,name,status,value,confidence,source)=>({group,name,status,value,confidence,source});

function operationalEvidence(workspace,verified){
 const posts=list(workspace.posts),jobs=list(workspace.jobs),leads=list(workspace.leads),campaigns=list(workspace.campaigns),media=list(workspace.media),insights=list(workspace.insights);
 const publishedPosts=posts.filter(post=>['published','partial'].includes(post.status));
 const scheduledPosts=posts.filter(post=>post.status==='scheduled');
 const terminalJobs=jobs.filter(job=>['published','failed','unknown'].includes(job.state));
 const successfulJobs=terminalJobs.filter(job=>job.state==='published');
 const qualifiedLeads=leads.filter(lead=>lead.status==='qualified');
 const completeLeads=leads.filter(lead=>lead.status!=='incomplete');
 const approvedCampaigns=campaigns.filter(campaign=>campaign.status==='approved');
 const documentedMedia=media.filter(item=>String(item.alt||'').trim()&&String(item.rights||'').trim());
 const deliveryRate=terminalJobs.length?Math.round(successfulJobs.length/terminalJobs.length*100):null;
 const insightSnapshots=insights.filter(snapshot=>['available','partial'].includes(snapshot.status)&&snapshot.metrics&&Object.keys(snapshot.metrics).length);
 const insightTotal=name=>insightSnapshots.reduce((sum,snapshot)=>sum+(Number(snapshot.metrics?.[name]?.value)||0),0);
 const insightAvailable=name=>insightSnapshots.some(snapshot=>Number.isFinite(Number(snapshot.metrics?.[name]?.value)));
 const insightValues=Object.fromEntries(['reach','impressions','engagements','followers','profileViews','websiteClicks','videoViews'].map(name=>[name,insightAvailable(name)?insightTotal(name):null]));
 return {verified,posts,jobs,leads,campaigns,media,insights,insightSnapshots,insightValues,publishedPosts,scheduledPosts,terminalJobs,successfulJobs,qualifiedLeads,completeLeads,approvedCampaigns,documentedMedia,deliveryRate};
}

function recommendations({connected,website,evidence}){
 const items=[];
 if(!connected.length)items.push({priority:1,title:'اربط حسابًا واحدًا للتحقق',detail:'الربط الحالي يؤكد هوية الحساب ويفتح طبقة بيانات التشغيل داخل NEMDAR؛ لا ينشر أو يحذف تلقائيًا.',route:'connectors'});
 if(connected.length&&!evidence.posts.length)items.push({priority:1,title:'أنشئ أول دورة محتوى موثّقة',detail:'أضف مسودة، راجعها، اعتمدها ثم جدولها حتى يبدأ التقرير المتقدم بقياس انتظام التشغيل.',route:'content'});
 if(connected.length&&evidence.posts.length&&!evidence.publishedPosts.length)items.push({priority:1,title:'أكمل أول نشر موثّق',detail:`يوجد ${evidence.posts.length} عنصر محتوى لكن لا توجد نتيجة نشر ناجحة أو جزئية مسجلة حتى الآن.`,route:'queue'});
 if(website?.status==='available'&&!website.signals?.analytics)items.push({priority:2,title:'فعّل قياس الموقع',detail:'لم يكتشف الفحص العام Analytics؛ أضف أداة قياس ثم أعد التقييم لإثبات مسار التحويل.',route:'audit'});
 if(connected.length&&!evidence.leads.length)items.push({priority:2,title:'اربط مرحلة الليدز بالتشغيل',detail:'لا توجد ليدز داخل مساحة العميل؛ سجّل المصدر وأدلة BANT قبل حساب جودة التحويل.',route:'leads'});
 if(connected.length&&evidence.campaigns.length&&!evidence.approvedCampaigns.length)items.push({priority:3,title:'راجع خطط الحملات',detail:`هناك ${evidence.campaigns.length} خطة بدون اعتماد ميزانية مسجل. الاعتماد لا يشغّل إعلانًا ولا يخصم مبلغًا.`,route:'campaigns'});
 if(connected.length&&!evidence.insightSnapshots.length)items.push({priority:3,title:'زامن Insights للمنصة',detail:'التحقق من الهوية وحده لا يوفر Reach أو Impressions. شغّل مزامنة القراءة من شاشة ربط المنصات.',route:'connectors'});
 return items.sort((a,b)=>a.priority-b.priority).slice(0,4);
}

export function buildAuditReport(assessment,accounts=[],connections=[],workspace={}){
 const urls=assessment?.urls||{};
 const snapshots=assessment?.snapshots||{};
 const sources=auditSources.map(source=>({...source,url:urls[source.key]||'',present:Boolean(urls[source.key]),snapshot:snapshots[source.key]||null}));
 const present=sources.filter(source=>source.present);
 const inspected=sources.filter(source=>source.snapshot?.status==='available');
 const website=sources.find(source=>source.key==='website')?.snapshot;
 const connected=connections.filter(connection=>connectionActive(connection)&&accounts.some(account=>account.id===connection.account_id));
 const expired=connections.filter(connection=>connection.status==='expired'&&accounts.some(account=>account.id===connection.account_id));
 const level=connected.length?'verified':'surface';
 const evidence=operationalEvidence(workspace,level==='verified');
 const contentStatus=level==='verified'&&evidence.posts.length?'available':'unknown';
 const deliveryStatus=level==='verified'&&evidence.terminalJobs.length?'available':level==='verified'&&evidence.jobs.length?'inferred':'unknown';
 const leadStatus=level==='verified'&&evidence.leads.length?'available':'unknown';
 const campaignStatus=level==='verified'&&evidence.campaigns.length?'available':'unknown';
 const platformInsightStatus=level==='verified'&&evidence.insightSnapshots.length?'available':'unknown';
 const insight=evidence.insightValues;
 const metrics=[
  metric('الحضور الرقمي','القنوات الموجودة','available',`${present.length} من ${auditSources.length} مصادر أُضيفت للتقييم`,'عالٍ','الروابط التي أدخلها العميل'),
  metric('الهوية','قابلية اكتشاف الهوية العامة',connected.length||inspected.length?'available':present.length?'inferred':'unknown',connected.length?`${connected.length} حساب تم التحقق من هويته عبر المنصة`:inspected.length?`تمت قراءة العنوان والوصف العام من ${inspected.length} مصدر`:'الروابط محفوظة لكن المصادر لم تسمح بالقراءة العامة',connected.length?'عالٍ':inspected.length?'عالٍ':'منخفض',connected.length?'اتصال موثّق':'Public Collector'),
  metric('رحلة العميل','ترابط القنوات والـCTA',website?.status==='available'&&present.length>1?'available':urls.website&&present.length>1?'inferred':'unknown',website?.status==='available'?`الموقع: ${website.signals?.whatsApp?'WhatsApp ظاهر':'WhatsApp غير مكتشف'} · ${website.signals?.forms||0} نموذج · ${website.signals?.socialLinks||0} رابط سوشيال`:urls.website&&present.length>1?'الموقع موجود لكن القراءة العامة لم تكتمل':'أضف الموقع وقناة سوشيال واحدة على الأقل',website?.status==='available'?'عالٍ':urls.website?'متوسط':'غير متاح','Public website scan'),
  metric('الموقع','جاهزية التحويل والقياس',website?.status==='available'?'available':'unknown',website?.status==='available'?`${website.signals?.mobileViewport?'Mobile ✓':'Mobile غير مكتشف'} · ${website.signals?.analytics?'Tracking ✓':'Tracking غير مكتشف'} · ${website.signals?.structuredData?'Structured Data ✓':'Structured Data غير مكتشف'}`:urls.website?'تعذرت قراءة الموقع من الخادم':'لم يُضف موقع',website?.status==='available'?'عالٍ':'غير متاح','HTML public signals'),
  metric('التشغيل','دورة المحتوى داخل NEMDAR',contentStatus,contentStatus==='available'?`${evidence.posts.length} محتوى · ${evidence.publishedPosts.length} منشور/نجاح جزئي · ${evidence.scheduledPosts.length} مجدول`:'لا توجد دورة محتوى موثّقة متاحة في وضع التقرير الحالي',contentStatus==='available'?'عالٍ':'غير متاح','First-party workflow data'),
  metric('التشغيل','موثوقية تسليم النشر',deliveryStatus,deliveryStatus==='available'?`${evidence.successfulJobs.length} نجاح من ${evidence.terminalJobs.length} نتيجة نهائية · ${evidence.deliveryRate}%`:deliveryStatus==='inferred'?`${evidence.jobs.length} مهمة موجودة لكن لا توجد نتائج نهائية كافية`:'لا توجد نتائج إرسال موثقة يمكن قياسها',deliveryStatus==='available'?'عالٍ':deliveryStatus==='inferred'?'متوسط':'غير متاح','Dispatch receipts'),
  metric('الأداء','Reach · Impressions · Saves',platformInsightStatus,platformInsightStatus==='available'?`${insight.reach===null?'Reach غير متاح':'Reach '+insight.reach.toLocaleString('ar-AE')} · ${insight.impressions===null?'Impressions غير متاح':'Impressions '+insight.impressions.toLocaleString('ar-AE')} · Saves غير متاح في ملخص الحساب`:connected.length?'تم التحقق من الهوية، لكن Insights لم تُزامن أو لم تسمح بها Meta':'غير متاح من الروابط العامة',platformInsightStatus==='available'?'عالٍ':'غير متاح',platformInsightStatus==='available'?'Meta Graph API snapshot':'يتطلب مزامنة Insights للقراءة'),
  metric('الأداء','التفاعل الموثّق',platformInsightStatus,platformInsightStatus==='available'?(insight.engagements===null?'Snapshot متاح لكن Metric التفاعل غير متاحة لهذا الحساب':`${insight.engagements.toLocaleString('ar-AE')} تفاعل خلال نطاق الـSnapshot`):'لا نستخدم أرقامًا مستخرجة بشكل غير موثوق من صفحة الملف الشخصي',platformInsightStatus==='available'?'عالٍ':'غير متاح',platformInsightStatus==='available'?'Meta Graph API snapshot':'يتطلب بيانات منصة موثوقة'),
  metric('الجمهور','العمر والموقع وأوقات النشاط','unknown','لن نخمن بيانات الجمهور من المتابعين أو التعليقات','غير متاح','يتطلب موصل Insights للقراءة'),
  metric('الحملات','جاهزية خطط الحملات',campaignStatus,campaignStatus==='available'?`${evidence.campaigns.length} خطة · ${evidence.approvedCampaigns.length} ميزانية معتمدة · إنفاق فعلي غير متاح`:'لا توجد خطط حملات موثقة في التقرير المتقدم',campaignStatus==='available'?'عالٍ':'غير متاح','First-party campaign plans'),
  metric('الإعلانات','Spend · CTR · CPL · ROAS','unknown','لا يُعرض الإنفاق المخطط كأنه إنفاق فعلي','غير متاح','يتطلب ربط Ad Account للقراءة'),
  metric('الليدز','جودة وتأهيل الليدز',leadStatus,leadStatus==='available'?`${evidence.qualifiedLeads.length} مؤهل من ${evidence.leads.length} · ${evidence.completeLeads.length} مكتمل القرار`:'لا توجد بيانات ليدز موثقة في التقرير المتقدم',leadStatus==='available'?'عالٍ':'غير متاح','NEMDAR CRM · BANT evidence'),
  metric('التحويل','Conversion Rate · Revenue','unknown',evidence.leads.length?'الليدز موجودة لكن لا يوجد ربط إيراد أو مصدر تحويل مثبت':'لا يمكن إثبات التحويل من بيانات السوشيال العامة','غير متاح','يتطلب Analytics + CRM attribution'),
  metric('الأمان','حالة الاتصال',connected.length?'available':'unknown',connected.length?`${connected.length} اتصال صالح · قراءة الهوية مؤكدة${expired.length?` · ${expired.length} منتهي`:''}`:expired.length?`${expired.length} اتصال منتهي ويحتاج تجديد`:'لم تمنح NEMDAR أي صلاحية للحسابات حتى الآن',connected.length?'عالٍ':'غير متاح','سجل الاتصالات')
 ];
 const known=metrics.filter(metric=>metric.status==='available').length;
 const inferred=metrics.filter(metric=>metric.status==='inferred').length;
 const unknown=metrics.filter(metric=>metric.status==='unknown').length;
 const layers=[
  {name:'Public Surface',status:inspected.length?'ready':'limited',detail:`${inspected.length} من ${present.length} مصدر تمت قراءته`},
  {name:'Verified Identity',status:connected.length?'ready':'locked',detail:connected.length?`${connected.length} اتصال موثّق`:'يحتاج ربط حساب'},
  {name:'NEMDAR Operations',status:connected.length&&(evidence.posts.length||evidence.leads.length||evidence.campaigns.length)?'ready':connected.length?'empty':'locked',detail:connected.length?`${evidence.posts.length} محتوى · ${evidence.leads.length} ليد · ${evidence.campaigns.length} حملة`:'تُفتح بعد التحقق'},
  {name:'Platform Insights',status:evidence.insightSnapshots.length?'ready':'locked',detail:evidence.insightSnapshots.length?`${evidence.insightSnapshots.length} Snapshot موثّق · آخر مزامنة ${evidence.insightSnapshots.map(item=>item.syncedAt).sort().at(-1)||''}`:'Reach والجمهور تحتاج صلاحيات قراءة منفصلة'},
  {name:'Revenue Attribution',status:'locked',detail:'يحتاج Analytics + CRM attribution'}
 ];
 return {level,sources,present,inspected,connected,expired,metrics,known,inferred,unknown,evidence,layers,recommendations:recommendations({connected,website,evidence}),observedAt:snapshots.observedAt||'',coverage:Math.round((known+inferred*.45)/metrics.length*100)};
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
