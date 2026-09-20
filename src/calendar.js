// Calendar date keys are always Dubai dates, independent of the browser timezone.
export function dayKey(value=new Date()) {
 const d=new Date(new Date(value).getTime()+4*60*60*1000);
 return Number.isNaN(d.getTime())?'':d.toISOString().slice(0,10);
}
export function moveMonth(month,offset) {
 const [y,m]=month.split('-').map(Number);
 return new Date(Date.UTC(y,m-1+offset,1)).toISOString().slice(0,7);
}
export function monthDays(month) {
 const [y,m]=month.split('-').map(Number), first=new Date(Date.UTC(y,m-1,1));
 const start=1-first.getUTCDay();
 return Array.from({length:42},(_,i)=>new Date(Date.UTC(y,m-1,start+i)).toISOString().slice(0,10));
}
export function datedPosts(posts,month) {
 return posts.filter(p=>['scheduled','published','partial'].includes(p.status)&&dayKey(p.scheduledAt).startsWith(month)).sort((a,b)=>new Date(a.scheduledAt)-new Date(b.scheduledAt));
}
