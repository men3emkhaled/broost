# نشر الموقع بأقل إعدادات

التقسيم النهائي:

- Vercel: ملفات الموقع ولوحة الإدارة فقط.
- Railway: FastAPI داخل Docker.
- Neon: PostgreSQL للداتا الأونلاين.
- ImgBB: صور إثباتات تحويل المحافظ.
- برنامج الكاشير: يظل بقاعدة SQLite المحلية ويتصل بـRailway API.

## القيم المطلوبة

على Railway أضف أربع قيم فقط من شاشة Variables:

1. `DATABASE_URL`: انسخ **Pooled connection string** من Neon.
2. `IMGBB_API_KEY`: مفتاح API من ImgBB.
3. `BROOST_ADMIN_PASSWORD`: كلمة مرور لوحة الإدارة.
4. `BROOST_SYNC_KEY`: مفتاح طويل وعشوائي، ويجب وضع نفس القيمة داخل إعدادات مزامنة برنامج الكاشير.

لا تضف `PORT`؛ Railway يضبطه تلقائيًا. ملف `railway.toml` يحدد Docker والـhealth check وإعادة التشغيل.

على Vercel أضف قيمة واحدة:

- `API_BASE_URL`: رابط Railway العام مثل `https://example.up.railway.app` بدون `/` في النهاية.

بعد تغيير `API_BASE_URL` أعد نشر Vercel كي يولّد `config.js` الجديد.

## أول نقل للداتا إلى Neon

شغّل هذا مرة واحدة فقط من مجلد المشروع بعد ضبط `DATABASE_URL` و`IMGBB_API_KEY` محليًا:

```powershell
python scripts/migrate_sqlite_to_neon.py
```

السكريبت لا يعدّل ملف SQLite، ويرفض الكتابة إذا وجد داتا فعلية في Neon. كما يرفع صور التحويل القديمة إلى ImgBB ويضبط أرقام sequences بعد النقل.

## فحص قبل الربط

- افتح `https://RAILWAY-DOMAIN/health` وتأكد أن `database` تساوي `postgresql` و`proof_storage` تساوي `imgbb`.
- افتح رابط Vercel وتأكد أن المنيو تظهر.
- من إعدادات المزامنة في برنامج الكاشير ضع رابط Railway ونفس `BROOST_SYNC_KEY`.
- نفّذ طلبًا تجريبيًا نقدي، ثم طلب محفظة بصورة تحويل، ثم إلغاء طلب للتأكد من رجوع النقاط.

لا ترفع `.env` أو مفاتيح Neon وImgBB إلى GitHub؛ الملفات مهيأة لتجاهلها.
