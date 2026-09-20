export function facebookTutorial(){
 return `<section class="panel connector-tutorial">
  <div class="panel-head"><div><span class="eyebrow">Tutorial</span><h2>ربط صفحة Facebook خطوة بخطوة</h2></div><span class="badge warn">حوالي 10 دقائق</span></div>
  <div class="notice"><strong>قبل ما تبدأ</strong><p>لا ترسل كلمة مرور Facebook أو الـAccess Token لأي شخص ولا تضعه في الشات. أدخله فقط في نموذج الربط داخل NEMDAR Social.</p></div>
  <ol class="tutorial-steps">
   <li><div><h3>أضف الحساب داخل NEMDAR Social</h3><p>من «العملاء والحسابات» اختر العميل والعلامة، وأضف حسابًا بمنصة Facebook واكتب اسم الصفحة أو معرّفها الواضح.</p><a href="#accounts">افتح العملاء والحسابات ←</a></div></li>
   <li><div><h3>جهّز تطبيق Meta Developer</h3><p>افتح لوحة تطبيقات Meta وأنشئ تطبيقًا أو اختر تطبيقك الحالي. فعّل حالة الاستخدام التي تسمح بإدارة صفحات Facebook. لو الصفحة لعميل خارج أدوار التطبيق، راجع متطلبات Live Mode وApp Review وBusiness Verification في لوحة Meta.</p><a href="https://developers.facebook.com/apps/" target="_blank" rel="noopener noreferrer">فتح Meta Apps ↗</a></div></li>
   <li><div><h3>أنشئ User Access Token بالصلاحيات المطلوبة</h3><p>من Graph API Explorer اختر نفس التطبيق وإصدار Graph API، ثم اطلب الصلاحيات التالية ووافق بالحساب الذي يدير الصفحة:</p><code dir="ltr">pages_show_list · pages_read_engagement · pages_manage_posts</code><a href="https://developers.facebook.com/tools/explorer/" target="_blank" rel="noopener noreferrer">فتح Graph API Explorer ↗</a></div></li>
   <li><div><h3>استخرج Page ID وPage Access Token</h3><p>داخل Graph API Explorer نفّذ الطلب التالي. من الصفحة المطلوبة انسخ <b>id</b> و<b>access_token</b>. لا تستخدم User Token في NEMDAR Social.</p><code dir="ltr">GET /me/accounts?fields=id,name,access_token</code></div></li>
   <li><div><h3>راجع صلاحية التوكن</h3><p>افتح Access Token Debugger وتأكد من التطبيق، الصلاحيات، وتاريخ الانتهاء. سجّل في NEMDAR تاريخًا لا يتجاوز التاريخ الظاهر هناك.</p><a href="https://developers.facebook.com/tools/debug/accesstoken/" target="_blank" rel="noopener noreferrer">فتح Access Token Debugger ↗</a></div></li>
   <li><div><h3>أكمل الربط هنا</h3><p>في بطاقة Facebook اضغط «ربط الصفحة»، ثم أدخل Page ID، وإصدار API كما يظهر في Explorer بصيغة <b dir="ltr">vXX.0</b>، وPage Access Token، وتاريخ الانتهاء. زر الحفظ يتحقق من هوية الصفحة فقط ولا ينشر شيئًا.</p></div></li>
   <li><div><h3>اختبر النشر بشكل آمن</h3><p>أنشئ منشورًا نصيًا فقط، أو أرفق صورة JPEG/PNG واحدة من مكتبة الوسائط، ثم أرسله للمراجعة واعتمده وحدد موعدًا. بعد حلول الموعد افتح «متابعة النشر» واضغط «إرسال فعلي الآن». ستظهر شاشة تأكيد نهائية قبل الإرسال.</p><a href="#content">ابدأ بمسودة ←</a></div></li>
  </ol>
  <details class="troubleshooting"><summary>لو الربط أو النشر رفض — افتح الحلول</summary><ul><li><b>Error 190:</b> التوكن منتهي أو غير صالح؛ أنشئ Page Access Token جديدًا.</li><li><b>Error 200 أو رفض صلاحية:</b> راجع <span dir="ltr">pages_manage_posts</span> ودور المستخدم على الصفحة وحالة التطبيق.</li><li><b>التوكن لا يخص الصفحة:</b> اختر السجل الصحيح من <span dir="ltr">/me/accounts</span> وتأكد أن Page ID مطابق.</li><li><b>الصفحة لا تظهر:</b> الحساب الذي أنشأ التوكن لا يملك وصولًا كافيًا للصفحة، أو الصلاحيات لم تُقبل.</li></ul></details>
  <p class="muted tutorial-limit">الإصدار الحالي ينشر نصًا أو صورة JPEG/PNG واحدة على صفحة Facebook وبإرسال يدوي. تعدد الصور والفيديو وWebP وInstagram والإعلانات غير مفعّلة بعد.</p>
 </section>`;
}
