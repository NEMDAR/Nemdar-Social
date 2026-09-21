export const auditSources=[
 {key:'website',label:'الموقع الإلكتروني',hint:'https://example.com'},
 {key:'instagram',label:'Instagram',hint:'https://instagram.com/brand'},
 {key:'facebook',label:'Facebook',hint:'https://facebook.com/brand'},
 {key:'tiktok',label:'TikTok',hint:'https://tiktok.com/@brand'},
 {key:'linkedin',label:'LinkedIn',hint:'https://linkedin.com/company/brand'},
 {key:'youtube',label:'YouTube',hint:'https://youtube.com/@brand'},
 {key:'googleBusiness',label:'Google Business',hint:'https://maps.google.com/...'}
];

export const evidenceStatusLabel={
 observed:'مرصود',
 inferred:'مستنتج',
 unknown:'غير معروف',
 unavailable:'غير متاح',
 stale:'قديم',
 zero:'صفر مرصود'
};

export const auditLevelLabel={
 surface:'SURFACE AUDIT · READ ONLY',
 verified:'VERIFIED AUDIT',
 insights:'INSIGHTS AUDIT',
 attributed:'ATTRIBUTED AUDIT'
};

export const auditLevelTitle={
 surface:'تحليل سطحي من الروابط العامة فقط — بدون أي وصول للحسابات.',
 verified:'تم تأكيد هوية حساب واحد على الأقل؛ التقرير يوضح بدقة ما أصبح موثّقًا وما زال يحتاج Insights.',
 insights:'توفرت أدلة Insights حديثة. الأرقام المعروضة مرصودة من المنصة وليست تقديرات.',
 attributed:'قياس التحويل والإيراد موثّق من Analytics وCRM.'
};

export const MATURITY_STAGES=[
 {id:'surface',label:'Surface',title:'الروابط العامة'},
 {id:'verified',label:'Verified',title:'هوية موثّقة'},
 {id:'insights',label:'Insights',title:'قياس المنصة'},
 {id:'attributed',label:'Attributed',title:'إسناد التحويل'}
];

export const layerStatusLabel={
 ready:'جاهز',
 limited:'محدود',
 empty:'فارغ',
 locked:'مقفل',
 stale:'قديم'
};

export const layerTitle={
 public_surface:'السطح العام',
 verified_identity:'الهوية الموثّقة',
 nemdar_operations:'تشغيل NEMDAR',
 platform_insights:'قياس المنصات',
 revenue_attribution:'إسناد الإيراد'
};

export const provenanceSourceLabel={
 'assessment.urls':'روابط التقييم',
 'surface_collector':'فحص الموقع العام',
 'connections':'اتصال موثّق',
 'page_connections':'Facebook Connection',
 'instagram_connections':'Instagram Connection',
 'meta_graph_api':'Meta Graph API',
 'nemdar_store':'تشغيل NEMDAR',
 'dispatch_jobs':'إيصال النشر',
 'analytics_crm':'Analytics + CRM',
 'ad_account':'حساب إعلاني'
};

export const deltaKindLabel={
 numeric:'مقارنة رقمية',
 newly_measured:'تم قياسه لأول مرة',
 measurement_lost:'القياس غير متاح حالياً',
 became_stale:'أصبح قديماً',
 incompatible:'غير قابل للمقارنة',
 unchanged:'بدون تغيير'
};

export const recommendationCta={
 rec_connect:{label:'ربط حساب',icon:'link'},
 rec_renew:{label:'تجديد التفويض',icon:'autorenew'},
 rec_content:{label:'إنشاء محتوى',icon:'edit_note'},
 rec_first_publish:{label:'متابعة النشر',icon:'send'},
 rec_publish_fail:{label:'مراجعة فشل النشر',icon:'error'},
 rec_site_analytics:{label:'إعداد Analytics',icon:'analytics'},
 rec_leads:{label:'فتح الليدز',icon:'contacts'},
 rec_campaigns:{label:'مراجعة الحملات',icon:'campaign'},
 rec_sync_insights:{label:'مزامنة Insights',icon:'sync'},
 rec_refresh_insights:{label:'تحديث Insights',icon:'refresh'},
 rec_insights_denied:{label:'فتح ربط المنصات',icon:'link_off'},
 rec_conversion:{label:'مراجعة التقييم',icon:'monitoring'}
};

export const improvementLabel={
 add_source_url:'أضف مصدرًا',
 connect_account:'ربط حساب',
 add_website_and_social:'أضف الموقع والقنوات',
 add_website:'أضف الموقع',
 create_content_cycle:'إنشاء محتوى',
 investigate_publishing:'مراجعة النشر',
 review_campaigns:'مراجعة الحملات',
 record_leads:'تسجيل ليدز',
 renew_connection:'تجديد التفويض'
};

const MEASURED=new Set(['observed','inferred']);
const LEVEL_ORDER=['surface','verified','insights','attributed'];

export function displayMetricValue(metric={}){
 const status=metric.status;
 if(status==='observed'||status==='inferred'||status==='stale'){
  if(metric.displayValue!=null&&metric.displayValue!=='')return String(metric.displayValue);
  if(metric.value===0||metric.value==='0')return '0';
  if(metric.value==null||metric.value==='')return metric.explanation||'—';
  return String(metric.value);
 }
 return metric.explanation||metric.displayValue||'غير متاح للقياس';
}

export function presentScore(value){
 return value==null||Number.isNaN(Number(value))?'—':`${Math.round(Number(value))}%`;
}

export function presentPerformanceCard(score,explanation=''){
 if(score==null||Number.isNaN(Number(score))){
  return {available:false,display:'غير متاح حالياً',explanation:explanation||'لا توجد مقاييس أداء مرصودة وقابلة للمقارنة. المقاييس الناقصة لا تخفّض درجة الأداء.'};
 }
 return {available:true,display:`${Math.round(Number(score))}%`,explanation:explanation||'أداء مرصود من الأدلة المتاحة.'};
}

export function presentMaturity(level){
 const current=LEVEL_ORDER.includes(level)?level:'surface';
 const idx=LEVEL_ORDER.indexOf(current);
 return MATURITY_STAGES.map((stage,i)=>({
  ...stage,
  state:i<idx?'completed':i===idx?'current':'locked'
 }));
}

export function groupMetricsBySection(metrics=[]){
 const groups=[];
 const index=new Map();
 for(const metric of metrics){
  const key=metric.section||metric.group||'other';
  if(!index.has(key)){
   const group={id:key,title:metric.sectionTitle||metric.group||'مقاييس',metrics:[]};
   index.set(key,group);
   groups.push(group);
  }
  index.get(key).metrics.push(metric);
 }
 return groups;
}

export function presentSourceLabel(source=''){
 return provenanceSourceLabel[source]||source||'';
}

export function presentDeltaItem(item={}){
 const kind=item.kind||'unchanged';
 let change=deltaKindLabel[kind]||kind;
 if(kind==='numeric'){
  const abs=item.absolute;
  const pct=item.percent;
  const absText=abs==null?'':`${abs>0?'+':''}${abs}`;
  const pctText=pct==null?'':` (${pct>0?'+':''}${pct}%)`;
  change=absText+pctText||'مقارنة رقمية';
 }else if(kind==='newly_measured'){
  change='تم قياسه لأول مرة';
 }else if(kind==='measurement_lost'){
  change='القياس غير متاح حالياً';
 }
 return {...item,kindLabel:deltaKindLabel[kind]||kind,changeLabel:change};
}

export function presentRecommendation(item={}){
 const cta=recommendationCta[item.id]||{label:'فتح',icon:'arrow_back'};
 const priority=Number(item.priority)||3;
 return {
  ...item,
  priorityLabel:priority===1?'أولوية عالية':priority===2?'أولوية متوسطة':'متابعة',
  priorityClass:priority===1?'high':priority===2?'medium':'low',
  ctaLabel:cta.label,
  ctaIcon:cta.icon,
  route:item.route||'audit',
  why:item.detail||'',
  evidenceLabel:(item.evidenceIds||[]).length?`أدلة: ${item.evidenceIds.length}`:''
 };
}

export function presentAuditReport(report){
 if(!report||typeof report!=='object')return null;
 const scores=report.scores||{};
 const metrics=(report.metrics||[]).map(metric=>{
  const status=metric.status||'unknown';
  const value=displayMetricValue(metric);
  const source=metric.provenance?.source||metric.source||'';
  return {
   ...metric,
   status,
   name:metric.title||metric.name,
   group:metric.sectionTitle||metric.group,
   value,
   numericValue:MEASURED.has(status)||status==='stale'?metric.value:null,
   statusLabel:evidenceStatusLabel[status]||evidenceStatusLabel.unknown,
   provenanceLabel:presentSourceLabel(source),
   freshnessLabel:metric.freshness?.label||'',
   explanation:metric.explanation||'',
   actionLabel:improvementLabel[metric.improvementAction]||''
  };
 });
 const coverageScore=scores.coverageScore??report.coverage??null;
 const confidenceScore=scores.confidenceScore??null;
 const performanceScore=scores.performanceScore??null;
 const performanceExplanation=scores.performanceExplanation||'';
 return {
  ...report,
  level:report.level||'surface',
  levelLabel:auditLevelLabel[report.level]||auditLevelLabel.surface,
  metrics,
  metricSections:groupMetricsBySection(metrics),
  maturity:presentMaturity(report.level||'surface'),
  scores:{
   coverageScore,
   confidenceScore,
   performanceScore,
   performanceExplanation
  },
  coverageDisplay:presentScore(coverageScore),
  confidenceDisplay:presentScore(confidenceScore),
  performanceDisplay:presentScore(performanceScore),
  performanceCard:presentPerformanceCard(performanceScore,performanceExplanation),
  recommendations:(report.recommendations||[]).map(presentRecommendation),
  layers:(report.layers||[]).map(layer=>({
   ...layer,
   title:layerTitle[layer.id]||layer.name,
   statusLabel:layerStatusLabel[layer.status]||layer.status
  })),
  delta:(report.delta||[]).map(presentDeltaItem),
  sources:report.sources||[]
 };
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
