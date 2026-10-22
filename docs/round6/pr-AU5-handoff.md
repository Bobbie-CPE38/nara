# AU5 — สมัครบัญชีเว็บผ่าน LINE REGISTER

เพิ่มหลัง AU1 (#124) ตาม workflow 6.33.6 และ API 9.9; โค้ด Backend เท่านั้น หน้าเว็บ `/register` เป็น AU3 และการเปลี่ยนด่าน/โหมด AWS เป็น AU4 ไม่ deploy หรือแก้ env ของเครื่องใน PR นี้ ไม่เปลี่ยน LINE Login เป็น OAuth และไม่เปลี่ยนกติกา LINK เดิม

## วิธีใช้หลังหน้าเว็บและด่านพร้อม

1. พนักงาน ACTIVE ที่ยังไม่มีบัญชีเว็บต้องผูก LINE ส่วนตัวด้วย LINK ตามคู่มือเดิมก่อน
2. ส่ง `REGISTER` ในแชตส่วนตัวกับ Nara ระบบตอบรหัสสมัครอายุ 10 นาทีตามเวลาจริง แสดงครั้งเดียวต่อคำสั่ง ไม่ส่งรหัสลงแชตทีม/หลักฐานรีวิว
3. เปิดหน้า `/register` ของเว็บ กรอกรหัสและตั้ง password 12–128 ตัว ไม่กรอก staff_id/role/ward; AU3 เรียก POST `/api/auth/register` ด้วย JSON `{code,password}`, Origin ของเว็บ และ credentials ตาม flow ของ AU1
4. สำเร็จได้ 201 `{staff_id}` แล้วไปล็อกอินเอง ไม่มี session จากการสมัคร หากได้ 400 `AUTH_INVALID_REGISTRATION` ให้ขอรหัสใหม่ หากมีบัญชีอยู่แล้วให้ login หรือติดต่อผู้ดูแล ไม่ใช้ REGISTER reset รหัส
5. ขอ REGISTER ใหม่ทำให้รหัสก่อนหน้าใช้ไม่ได้; unlink/rebind แม้ UID เดิมทำให้รหัสเก่าใช้ไม่ได้ บัญชีเว็บที่สมัครแล้วและ session ไม่ถูกยกเลิกเพราะ unlink เพียงอย่างเดียว

สิทธิ์/รูป error ให้อ้าง workflow เป็นแหล่งเดียว: `/auth/*` no-store, Origin guard และ error validation ที่ไม่คืนรหัส/password ของ AU1; register จำกัด 5 ครั้ง/60 วินาทีต่อ IP และ subject ที่ระบุได้ก่อน hash password; คำสั่งออกโค้ดจำกัด 5 ครั้ง/60 วินาทีต่อ subject ไม่มี account lockout

## Migration และการส่งต่อ

- Head ใหม่ `b8f3d5a0c2e4` ต่อ `a7e2c4f9b1d3` เพิ่มตาราง `auth_registration_code` ว่าง (รวม 48 application tables) ใช้ migration ปกติ ไม่ reset เพื่อ upgrade
- เก็บเฉพาะ domain-separated SHA-256 ของ code และ UID พร้อม subject/contact_id อายุ 600 วินาที real UTC ไม่มี raw code/UID เพิ่มใน DB, Audit หรือ log
- สมัครใช้ preflight แบบอ่านอย่างเดียวภายใต้ shared reset gate แล้ว rollback transaction ก่อน hash; route ใช้ preflight เดียวเพื่อนับ subject/rate limit แล้ว hash โดยไม่มี transaction หรือ lock จากนั้น shared Auth reset gate → Staff → registration code → Contacts → account ตรวจสถานะ/expiry/used/revoked/actor/binding/account ซ้ำทั้งหมด สร้าง account/consume code ใน transaction เดียว ไม่สร้างหรือเลือกตัวตนจาก body; preflight เป็นเพียงการคัดกรองเบื้องต้น ไม่ให้สิทธิ์สมัคร
- LINK issue/link/unlink เพิ่ม shared reset gate ก่อนทำงาน; unlink revoke registration codes ก่อน Contacts โดย LINK token/expiry/audit เดิมคงเดิม
- Reset สำเร็จล้าง session และ registration codes; account/identity คงอยู่ตาม AU1 Reset ที่ rollback ต้องคงหลักฐานเก่าให้ใช้ได้ ไม่มีการเรียก LINE ใน transaction: ออก code กับ webhook dedup commit ก่อน reply; reply ล้มเหลวให้ขอ REGISTER ใหม่
- ถ้า AU2 เพิ่ม Migration ระหว่างงาน ต้อง rebase down_revision/test head ก่อน merge ไม่สร้างสอง head
- Downgrade ลบเฉพาะ registration codes; บัญชี/session ยังคงตาม AU1 กลับไปก่อน AU1 จะลบบัญชีตามคำเตือนของ AU1

## หลักฐานทดสอบ / สิ่งที่ยังต้องทำจริง

ทดสอบกับ PostgreSQL แยกและ LINE transport จำลอง ไม่มีการส่ง LINE/Bedrock จริง: signed webhook, personal binding, dedup/reply failure, code expiry/reset, unlink/relink, account provisioning, สอง connection แข่งสร้างบัญชี, rate limit และ Origin/error redaction พร้อม regression เดิม ผลคำสั่งสุดท้ายบันทึกใน PR description

Live **ยังไม่ทำ**: หลัง AU3/AU4 deploy ให้ใช้บัญชีทดสอบที่ยังไม่มี web account ส่ง REGISTER → สมัครหน้าเว็บ → login → me ตรวจ staff/role/ward ถูกต้อง → ใช้ code เดิมซ้ำถูกปฏิเสธ → ขอใหม่/ปลด LINE แล้วรหัสก่อนปลดใช้ไม่ได้ ตรวจ LINE LINK/Offer/button/Handover/check-in และ reset/session ใหม่ตามขอบเขตเดิม เก็บ revision/image และผลที่ไม่ใส่ code/password/UID ก่อนปิดรอบ ผล fake ไม่ใช้แทน production acceptance

## หมายเหตุ rate limit และการตรวจเครื่องตอน AU4

- ย้าย limiter/ค่าคงที่ไป `app/core/rate_limit.py` ให้ทั้ง API และ service ใช้แหล่งเดียว `app/api/rate_limit.py` เป็น compatibility exports เท่านั้น ไม่มี counter ชุดที่สอง
- โค้ดอ่าน `request.client.host` จาก ASGI scope ไม่อ่าน X-Forwarded-For เอง Uvicorn อาจแปลง scope ได้เฉพาะเมื่อ peer อยู่ใน trusted proxy config จึงต้องตรวจทั้งฝั่ง server และ Caddy รุ่นปัจจุบัน Compose ไม่ตั้ง `FORWARDED_ALLOW_IPS`; ค่า default ของ Uvicorn รุ่นที่ใช้ทดสอบเชื่อ loopback (`127.0.0.1,::1`) ไม่ได้เชื่อ Caddy ที่อยู่คนละ container โดยอัตโนมัติ จึงคาดว่าจะเห็น IP ของ Caddy จน AU4 ตั้ง trust ให้ถูกต้อง ห้ามตั้ง trust ทุก peer โดยไม่จำกัดทางเข้าถึง Backend
- เพดาน register ยังคง 5 ครั้ง/60 วินาทีต่อ IP **รวมทุกคนหลัง NAT เดียวกัน** แม้แก้ trusted proxy แล้ว และต่อ subject ที่หาได้จาก code ตาม AU0 ข้อนี้ยังไม่ได้ปรับนโยบายให้ใช้ลงทะเบียนพนักงานทั้งหอพร้อมกัน ให้เว้นช่วง rollout และรอ Retry-After เมื่อ 429; ถ้าต้องเพิ่มเพดานต้องตกลง/แก้ contract และ tests ก่อน deploy ไม่อ้างว่าเป็น 5 ครั้งต่อพนักงานอย่างเดียว
- จาก repository: Compose กำหนด Backend หนึ่ง service และคำสั่ง Uvicorn `--reload` ไม่มี `--workers`/`WEB_CONCURRENCY`; systemd ไม่ใช้ `--scale` ค่าเริ่มต้นที่ตรวจจาก Uvicorn ในสภาพแวดล้อมทดสอบเป็นหนึ่ง serving worker (reload supervisor ไม่ใช่ worker ที่รับคำขออีกตัว) จึงสอดคล้องกับ process-local limiter **ยังไม่ได้ยืนยัน process/env บน AWS จริง**
- AU4 ต้องตรวจ command/process จริง เช่น `sudo docker top nara-staffing-backend -eo pid,ppid,args` และตรวจเฉพาะ `WEB_CONCURRENCY`/`FORWARDED_ALLOW_IPS` โดยไม่ dump env ทั้งหมด ต้องมีหนึ่ง serving worker และหนึ่ง Backend replica ก่อนอ้างเพดานรวม หากเพิ่ม workers/replicas ต้องย้าย counter ไปที่ shared store ก่อน
- หลังตั้ง proxy ต้องทดสอบการนับต่อ client IP ที่ทราบจริง และตรวจ X-Forwarded-For ปลอมไม่เปลี่ยน bucket จากภายนอก พร้อมทดสอบคนหลายคนหลัง NAT เดียวกัน รัน/เก็บหลักฐานบนรุ่น AU4 ก่อนเปิดใช้งาน ไม่ถือผล local นี้เป็นผล production
