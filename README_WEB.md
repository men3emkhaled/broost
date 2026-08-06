# الموقع ولوحة الإدارة

## التشغيل المحلي

- من النسخة المثبتة: شغّل `Broost Web Server` من قائمة Start.
- من السورس: شغّل `run_web.bat`.
- موقع العميل: `http://127.0.0.1:8765`
- لوحة الإدارة: `http://127.0.0.1:8765/admin`

التشغيل المحلي يستخدم SQLite تلقائيًا داخل `webapp/data`، ولا يحتاج Neon أو ImgBB.

## النشر

الإنتاج مقسّم إلى:

- Vercel للفرونت ولوحة الإدارة.
- Railway للـFastAPI API باستخدام `Dockerfile`.
- Neon PostgreSQL للداتا.
- ImgBB لصور إثباتات التحويل.

Railway يحتاج `DATABASE_URL` و`IMGBB_API_KEY` و`BROOST_ADMIN_PASSWORD` و`BROOST_SYNC_KEY`. Vercel يحتاج `API_BASE_URL` فقط. راجع [DEPLOYMENT.md](DEPLOYMENT.md) للترتيب الكامل ونقل الداتا الحالية بأمان.

## تشغيل Docker يدويًا

الحاوية مخصصة للإنتاج ولذلك ترفض العمل إذا كانت القيم السرية ناقصة:

```powershell
docker build -t cashier-web .
docker run --rm -p 8080:8080 `
  -e DATABASE_URL="postgresql://..." `
  -e IMGBB_API_KEY="..." `
  -e BROOST_ADMIN_PASSWORD="..." `
  -e BROOST_SYNC_KEY="..." `
  cashier-web
```

لا يحتاج Railway إلى Volume؛ الداتا في Neon والصور في ImgBB.
