# نشر نسخة UAT مستقلة

المستودع: NEMDAR/Nemdar-Social. لا تستخدم تطبيق Factory أو OrgOS القائم ولا قاعدة بياناتهما.

## محلياً

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m server.manage init --email YOUR_EMAIL
npm start
```

افتح http://localhost:8080 بنفس اسم المضيف، وليس 127.0.0.1، لأن APP_ORIGIN يجب أن يطابق Origin تماماً. كلمة المرور تدخل تفاعلياً ولا تظهر في السجل. لا توجد بيانات دخول افتراضية أو تسجيل عام.

## Docker / Coolify

1. تطبيق Dockerfile مستقل من الفرع main، منفذ داخلي 8080.
2. قرص دائم عند `/app/data`، بملكية uid 10001.
3. اضبط `APP_ORIGIN` على أصل HTTPS النهائي بدون شرطة أخيرة.
4. اضبط `DATABASE_PATH=/app/data/workspace.db`.
5. خزنة الأسرار اختيارية: اضبط `VAULT_KEY` إلى مفتاح عشوائي 32 بايت ممثّل في 64 حرف hex. أدخله في إعدادات الأسرار في Coolify. لا تحفظه في الريبو أو سجل محادثة. لا تغيّره بعد حفظ الأسرار دون ترحيل التشفير؛ تدوير المفتاح غير منفذ بعد.
6. بعد تشغيل الحاوية، من Terminal التفاعلي: `python -m server.manage init --email YOUR_EMAIL` لإنشاء المدير مرة واحدة.
7. مرر الزيارات عبر HTTPS reverse proxy. لا تعرّض منفذ Waitress مباشرة للإنترنت.
8. فحص الحياة: `/api/health`. باقي بيانات API تحتاج جلسة دخول.

باستخدام Compose محلياً:

```sh
docker compose up -d --build
docker compose exec social python -m server.manage init --email YOUR_EMAIL
```

خادم التطوير WSGI في `npm start` للاستخدام المحلي فقط. صورة Docker تستخدم Waitress. SQLite مخصص لنسخة وكالة واحدة وحاوية كاتبة واحدة؛ لا تستخدم عدة replicas على نفس الملف.

## النسخ الاحتياطي والاستعادة

```sh
python -m server.manage backup --output /secure-backups/social-2026-09-20.db
```

يتضمن النسخ ملفات الوسائط والأسرار المشفرة والجلسات. احفظ النسخ خارج مسار الويب، واحتفظ بمفتاح الخزنة منفصلاً. للاستعادة: أوقف الحاوية، استبدل قاعدة البيانات من النسخة المتسقة مع حذف ملفات WAL/SHM القديمة بعد الإيقاف، أعد الملكية uid 10001، ثم شغّل واختبر. ألغِ الجلسات المستعادة قبل فتح الخدمة للمستخدمين. تم اختبار إعادة فتح قاعدة البيانات؛ سيناريو الاستعادة على VPS لم يُنفذ.

## موارد UAT

- مشروع مستقل: NEMDAR Social UAT (`vk3kucladekr17jlorlpygjs`).
- التطبيق: `zupnhqfv7edn1mbhc1mdv2fo`.
- الرابط: https://social-uat.nemdar.tech
- التخزين الدائم: `/app/data`.
- النشر التلقائي من GitHub معطل؛ النشر مربوط بنسخة محددة.
- مسار التشغيل: Workflow يدوي خاص بـSocial يستدعي Coolify Canonical Control Plane كـsub-workflow. مشكلة الاستدعاء المباشر عولجت بدون تعديل المسار الأصلي أو نسخ بيانات الدخول.
- الصورة تتضمن curl حتى يعمل فحص الصحة الذي يضيفه Coolify.

### إعداد المدير من المتصفح

يدعم الخادم `BOOTSTRAP_TOKEN_HASH` (بصمة SHA-256 لمفتاح عشوائي) وإعداد المدير مرة واحدة عبر رابط خاص على `/login.html#setup=...`. المفتاح الخام لا يُحفظ في GitHub أو إعدادات البناء. لا يعمل بعد وجود أول مستخدم. المستخدم يختار البريد وكلمة المرور بنفسه. بعد الإعداد يمكن حذف المتغير من Coolify؛ الحسابات تبقى داخل قاعدة البيانات.

لا تضع رابط التفعيل الخاص في التوثيق العام. لا توجد بيانات دخول افتراضية.

## تحقق النشر

التطبيق منشور على نسخة الكود `ecf6ac618a76ad4bf38916f8925867eefaeb950b`. نشر Coolify `f7ppayv8dmtlnkxokjjg2yxc` انتهى بنجاح، والتطبيق running:healthy. فحص HTTPS بتاريخ 2026-09-20 أعاد 200 مع `{"ok":true,"version":"0.4.0"}`.

تحديث التقويم: نُشر commit `764341e6484d14492c175dcf4e8a426f4b614e19` بنجاح عبر deployment `utuyv7ra1aqbpponcvtlbcga`، بحالة finished / running:healthy. أعاد ملف التقويم الجديد 200، وحافظ /api/state على 401 بدون جلسة. أكد المالك إكمال إعداد المدير.

## مفتاح الخزنة في v0.5

يفضل VAULT_KEY خارجي محفوظ بأمان (64 حرف hex). عند غيابه تنشئ خدمة production مفتاحًا عشوائيًا مرة واحدة في `data/vault.key` بصلاحية 0600 على القرص الدائم، للخزنة الفارغة فقط. احفظ نسخة آمنة منفصلة منه؛ نسخة SQLite وحدها لا تكفي لاستعادة الأسرار. المفتاح والبيانات على نفس القرص في هذا النمط، وليس مدير مفاتيح خارجيًا. لا تفقد الملف أو تغيره عند إعادة النشر. إذا كانت البيانات مشفرة والمفتاح مفقود يتوقف التشغيل بدل إنشاء مفتاح بديل.

موصل Facebook يعمل حاليًا بإجراء يدوي من المدير. لا تسجّله في worker التلقائي قبل سياسة إطلاق واضحة واختبار حي. التوكن يدخل فقط في نموذج الربط داخل التطبيق، لا في المحادثة أو GitHub.

## نشر v0.5 على UAT

نُشر commit `040c13d8b7c32bc91e4877aee7822e5bd1724870` أولياً عبر deployment `tqtykekdtwvgdbe3xd7ykqze`. انتهى النشر بحالة `finished` والتطبيق `running:healthy`، وأعاد `/api/health` النسخة `0.5.0`. بقي `/api/state` محمياً وأعاد 401 بدون جلسة. لم يُدخل أي Page Access Token ولم يُجر نشر حي على Facebook أثناء التحقق.

التصحيح النهائي لعلامة Schema نُشر من commit `64d3f0d9da94a67870d3adb856dccf896e1a2de1` عبر deployment `tdczgi1myhmhd4hu9hn0dzth`، وانتهى كذلك بحالة `finished` والتطبيق `running:healthy`. تحقق HTTP من ظهور واجهة ربط Facebook، وبقاء صفحة الدخول متاحة، وبقاء بيانات الحالة محمية بدون جلسة.

نُشر Tutorial الربط من commit `409813aac1d406847c0c6f19ce052ac46f7d6ba1` عبر deployment `tqqbunedmujm1jksoe4fbtua`. انتهى النشر بحالة `finished` واستقرت الخدمة على `running:healthy`. أعاد ملف Tutorial العام 200 واحتوى العنوان والصلاحيات المتوقعة، وظل `/api/state` يعيد 401 بدون جلسة.
