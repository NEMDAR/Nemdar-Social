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

const MEASURED=new Set(['observed','inferred']);

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

export function presentAuditReport(report){
 if(!report||typeof report!=='object')return null;
 const scores=report.scores||{};
 const metrics=(report.metrics||[]).map(metric=>{
  const status=metric.status||'unknown';
  const value=displayMetricValue(metric);
  return {
   ...metric,
   status,
   name:metric.title||metric.name,
   group:metric.sectionTitle||metric.group,
   value,
   numericValue:MEASURED.has(status)||status==='stale'?metric.value:null,
   statusLabel:evidenceStatusLabel[status]||evidenceStatusLabel.unknown,
   provenanceLabel:metric.provenance?.source||metric.source||'',
   freshnessLabel:metric.freshness?.label||'',
   explanation:metric.explanation||''
  };
 });
 return {
  ...report,
  level:report.level||'surface',
  levelLabel:auditLevelLabel[report.level]||auditLevelLabel.surface,
  metrics,
  scores:{
   coverageScore:scores.coverageScore??report.coverage??null,
   confidenceScore:scores.confidenceScore??null,
   performanceScore:scores.performanceScore??null,
   performanceExplanation:scores.performanceExplanation||''
  },
  coverageDisplay:presentScore(scores.coverageScore??report.coverage),
  confidenceDisplay:presentScore(scores.confidenceScore),
  performanceDisplay:presentScore(scores.performanceScore),
  recommendations:report.recommendations||[],
  layers:report.layers||[],
  delta:report.delta||[],
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
