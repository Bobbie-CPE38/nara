# AU0 — Contract ส่งต่อสำหรับ AU1–AU5

AU0 เป็นเอกสารเท่านั้น: ย้ายร่าง #120 เข้า workflow 6.33 / API 9.9 และ planned schema ไม่ deploy ไม่เพิ่ม dependency/constant/runtime และไม่สร้าง migration ล่วงหน้า ผู้ใช้ให้คน 3 รับหน้าที่คน 1 และยืนยัน self-leave ทันทีเมื่อ 2026-10-22; ข้ออื่นยึดร่างที่รีวิวแล้วพร้อมข้อยุติใน workflow

## ข้อเปลี่ยนที่ทีมต้องรีวิว

- AUTH-Q3 เดิมถูกแก้เฉพาะ self-leave: POST `/me/unavailability` ใช้ staff/actor จาก session เริ่ม flow STAFF_UNAVAILABLE เดิม ไม่รออนุมัติการลา แต่การอนุมัติคนแทน/merge/Safety ไม่เปลี่ยน
- POST `/events` ทั่วไปยัง 403 ใน session ปุ่ม Demo จึงต้องเปลี่ยนไป trusted adapter POST `/demo/events` (SYSTEM actor) ไม่เปิดตัวตนผู้ใช้ปลอมเพื่อให้ Demo ใช้ได้
- Backend มี `STAFF.password_hash` เดิมจริง แต่ seed เป็น `!` ไม่ใช่บัญชีใช้งาน เลือก AUTH_ACCOUNT เป็นแหล่งรหัสใหม่และไม่เปิดบัญชีโดยคัดลอก legacy hash
- Permanent identity คือ STAFF.auth_subject UUID ไม่ใช้ staff_id ที่ reset สร้างซ้ำเป็นหลักฐานตัวคน; reset เก็บ Staff/actor identity/account, ล้าง session/auth-register code, ขัดกัน rollback
- REGISTER เป็นคำสั่งใหม่ผ่าน LINE binding เดิมเพื่อสมัครบัญชีเว็บ ไม่ใช้ token LINK แทน และไม่ใช่ LINE Login; expiry ของ auth code เป็น real UTC ต่างจาก LINK เดิม
- cookie/Origin/rate limit เป็นกติกา API ขั้นต่ำของระบบทดสอบ ไม่ประกาศพร้อมใช้ข้อมูลจริง ไม่มี account lockout หรือระบบกู้รหัสอัตโนมัติ

## Inventory ของ Route ปัจจุบัน (ตรวจจาก source ก่อน Implement AU)

Path เป็นของ Backend ก่อน Caddy เติม `/api` คอลัมน์สิทธิ์เป็น **ข้อกำหนดหลัง AU** ไม่ใช่สิ่งที่โค้ดวันนี้ทำแล้ว AU2 ต้องเติม integration test ต่อ method/path รวม list/count ไม่ใช่เปลี่ยนแค่ DemoUser dependency แล้วถือว่าครบ

| Method | Path | สิทธิ์หลัง AU | ผู้รับผิดชอบ |
|---|---|---|---|
| POST | `/approvals/{approval_id}/decision` | session + head own-side / supervisor ตามเวลา/side; filter list | AU2 |
| GET | `/approvals` | session + head own-side / supervisor ตามเวลา/side; filter list | AU2 |
| GET | `/approvals/auto` | session + head own-side / supervisor ตามเวลา/side; filter list | AU2 |
| GET | `/cases` | session + related case / head ward / supervisor | AU2 |
| GET | `/cases/{case_id}` | session + related case / head ward / supervisor | AU2 |
| POST | `/cases/{case_id}/explanation` | session + related case / head ward / supervisor | AU2 |
| POST | `/cases/{case_id}/summary` | session + related case / head ward / supervisor | AU2 |
| GET | `/cases/{case_id}/audit` | session + related case / head ward / supervisor | AU2 |
| GET | `/cases/{case_id}/handoff/candidates` | session + head own ward / supervisor; Hard Rules เดิม | AU2 |
| POST | `/cases/{case_id}/handoff/assignments` | session + head own ward / supervisor; Hard Rules เดิม | AU2 |
| POST | `/cases/{case_id}/handoff/close` | session + head own ward / supervisor; Hard Rules เดิม | AU2 |
| GET | `/clock` | public; ไม่มีข้อมูลบุคคล | AU2/AU4 |
| GET | `/dashboard` | session + ward scope + related-case scope ของ staff | AU2 |
| POST | `/demo/reset` | Basic + Origin สำหรับ mutation; SYSTEM/Demo actor | AU1 reset, AU3 adapter, AU4 gate |
| POST | `/demo/clock/advance` | Basic + Origin สำหรับ mutation; SYSTEM/Demo actor | AU1 reset, AU3 adapter, AU4 gate |
| POST | `/demo/clock/freeze` | Basic + Origin สำหรับ mutation; SYSTEM/Demo actor | AU1 reset, AU3 adapter, AU4 gate |
| POST | `/demo/clock/unfreeze` | Basic + Origin สำหรับ mutation; SYSTEM/Demo actor | AU1 reset, AU3 adapter, AU4 gate |
| POST | `/demo/attendance/check-in` | Basic + Origin สำหรับ mutation; SYSTEM/Demo actor | AU1 reset, AU3 adapter, AU4 gate |
| POST | `/events` | session ทุก role 403; self-leave แยก route | AU2 |
| GET | `/events/{event_id}` | session + Event owner/case relation หรือ ward/supervisor | AU2 |
| GET | `/gap/shifts` | session + ward scope; staff_id=self อ่านเวรของตนทุกหอได้ | AU2 |
| GET | `/gap/shifts/{shift_id}` | session + ward scope; staff_id=self อ่านเวรของตนทุกหอได้ | AU2 |
| POST | `/internal/merge-windows/close-due` | internal secret; public 404 | เดิม; AU2 regression |
| POST | `/internal/line-accounts/{staff_id}/issue-code` | internal secret; public 404 | เดิม; AU2 regression |
| POST | `/internal/line-accounts/{staff_id}/unlink` | internal secret; public 404 | เดิม; AU2 regression |
| GET | `/demo/line-sim/offers` | Basic + session + own staff/outreach | AU2/AU4 |
| POST | `/demo/line-sim/respond` | Basic + session + own staff/outreach | AU2/AU4 |
| POST | `/line/webhook` | exact signed LINE webhook; ไม่ใช้ session | AU4/AU5 regression |
| GET | `/me/handovers` | session + self only | AU2 |
| GET | `/me/offers` | session + self only | AU2 |
| POST | `/me/offers/{outreach_id}/response` | session + self only | AU2 |
| POST | `/me/attendance/check-in` | session + self only | AU2 |
| GET | `/roster` | session + ward scope; staff_id=self อ่านเวรของตนทุกหอได้ | AU2 |
| PATCH | `/unavailability/{unavailability_id}` | session + head ของคนลา / supervisor ทุกหอ | AU2 |
| GET | `/health` | public; ไม่มีข้อมูลบุคคล | AU2/AU4 |

รวม 35 method/path จากโค้ดที่ AU0 ตรวจ ไม่รวม routes ของ framework (docs/redoc/openapi ต้องปิดหรือ session ตาม workflow 6.33.5) และ route ใหม่ที่ยังไม่ Implement: GET auth/config, POST auth/login, POST auth/logout, GET auth/me, POST auth/change-password (AU1); POST me/unavailability, POST demo/events (AU2); POST auth/register (AU5) ถ้ามี PR อื่นเพิ่ม route ต้องเพิ่ม inventory และเทสต์ด้วย

## ลำดับ rollout / เกณฑ์ส่งต่อ

1. AU0 merge ก่อน AU1 โดยทีมรีวิวขอบเขต/รูป API/schema ไม่มีคำสั่งให้เปลี่ยนเครื่อง AWS จากเอกสารนี้
2. AU1 สร้าง migration ต่อ head ล่าสุด, บัญชี/session/CLI/auth APIs และ reset compatibility; defaults dev/demo ยังใช้เทสต์เดิมได้ Seed credentials สำหรับ demo เท่านั้น
3. AU2/AU3/AU5 ทำหลัง AU1 โดยยึด API 9.9 และ error/permission matrix เดียวกัน การเปลี่ยนร่าง API ต้องแก้ Contract ก่อนให้ frontend/backend แยกทาง
4. AU4 หลัง AU2+AU3 ตรวจ production ก่อนตัด Basic Auth กว้างออก ตรวจว่า X-Demo-User ปลอมตัวไม่ได้ เก็บผล gate/browser และ LINE smoke ใหม่ ไม่เอาหลักฐาน W ก่อน AU4 มาอ้างแทน; ส่วนสมัครจริง AU5 ต้องผ่านก่อนปิดรอบ
5. ต้อง AU0–AU5 ครบและ session บน production ก่อนปิดรอบ ไม่เปลี่ยนโหมด AWS ตาม AU1 ที่ merge เพียงตัวเดียว B2 รอ IAM ของเครื่องแยกต่างหาก ไม่มี AWS key หรือเปิด LLM ใน AU0

AU0 ตรวจ inventory, reference/หัวข้อและความสอดคล้องของเอกสารกับ source เท่านั้น ไม่รัน app test แล้วอ้างว่าระบบ auth ใช้ได้: runtime ยังไม่มี AU1–AU5 และไม่มีการทดสอบ login/สิทธิ์บน AWS ใน PR นี้
