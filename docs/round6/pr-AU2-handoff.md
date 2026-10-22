# AU2 — สิทธิ์ทุก Route และแจ้งลาตัวเอง

AU2 ทำกติกาข้อ 6.33.4 ของ `docs/workflow.md` ให้เป็นโค้ดใน `AUTH_MODE=session` โหมด demo ทำงานเหมือนก่อน AU2 กติกามีแหล่งเดียวที่ workflow ข้อ 6.33.4 และหัวข้อ "AU2 Implement แล้ว" ไฟล์นี้เก็บ inventory ของ route ที่ใช้ตรวจ และผลทดสอบ ไม่มี Migration ไม่เปลี่ยนเครื่อง AWS (ยังเป็นงาน AU4)

## Inventory ของ Route (42 method/path)

Path เป็นของ Backend ก่อน Caddy เติม `/api` ชนิดของแต่ละ route ตรงกับตาราง `INVENTORY` ใน `backend/tests/integration/test_route_permissions.py` ซึ่งเทียบกับ route จริงของแอป route ใหม่ที่ไม่อยู่ในตารางทำให้เทสต์ล้มจนกว่าจะเพิ่มเจ้าของและเทสต์

| ชนิด | ความหมายใน session | Route |
|---|---|---|
| public | ไม่ต้องมี session | GET `/health`, GET `/clock` |
| auth | API ล็อกอินของ AU1 (ไม่ต้องมี session ที่ยัง valid) | GET `/auth/config`, POST `/auth/login`, POST `/auth/logout` |
| internal | ต้องมี `X-Internal-Secret` ไม่ใช่ session (Job และ CLI) | POST `/internal/merge-windows/close-due`, POST `/internal/line-accounts/{staff_id}/issue-code`, POST `/internal/line-accounts/{staff_id}/unlink` |
| webhook | ลายเซ็น LINE | POST `/line/webhook` |
| demo | ไม่ต้องมี session; บน AWS อยู่หลัง Basic Auth ของ Demo (AU4) และใน session ต้องมี Origin | POST `/demo/reset`, `/demo/clock/advance`, `/demo/clock/freeze`, `/demo/clock/unfreeze`, `/demo/attendance/check-in`, **`/demo/events` (ใหม่)** |
| session | ต้องมี session: ไม่มี cookie หรือมีแค่ X-Demo-User ได้ 401 `AUTH_REQUIRED` ไม่มี `WWW-Authenticate` | ที่เหลือทั้งหมด 27 route (ด้านล่าง) |

| Route ที่ต้องมี session | staff | head_nurse | supervisor |
|---|---|---|---|
| GET `/auth/me`, POST `/auth/change-password` | ตัวเอง (AU1) | ตัวเอง | ตัวเอง |
| GET `/cases/{id}`, GET `/cases/{id}/audit`, POST `/cases/{id}/explanation`, POST `/cases/{id}/summary` | เคสที่เกี่ยวข้อง | หอตัวเอง และเคสที่ฝั่ง SOURCE ของคำขอสองหออยู่หอตัวเอง | ทุกเคส |
| GET `/cases?status=` | เฉพาะเคสที่เกี่ยวข้อง (กรองใน query) | หอตัวเอง | ทุกหอ |
| GET `/cases/{id}/handoff/candidates`, POST `.../handoff/assignments`, POST `.../handoff/close` | 403 (กติกาเดิมของ service) | หอตัวเอง | ทุกหอ |
| GET `/dashboard` | เคส/Offer/NO_SHOW ของตัวเอง ไม่มีจำนวน Approval; shortage ตามหอ | หอตัวเอง | ทุกหอ |
| GET `/approvals` | 403 | คำขอที่มีฝั่งในหอตัวเอง | ทั้งหมด |
| GET `/approvals/auto`, POST `/approvals/{id}/decision` | 403 (กติกาเดิม) | ตามกติกาเดิม | ตามกติกาเดิม |
| POST `/events` | 403 `AUTH_FORBIDDEN` ก่อนอ่าน body | 403 | 403 |
| GET `/events/{id}` | Event ของตัวเอง หรือของเคสที่อ่านได้ | + Event ของเวรในหอตัวเอง | ทั้งหมด |
| GET `/gap/shifts`, GET `/gap/shifts/{id}` | หอตัวเอง (กติกาเดิมของ F1) | หอตัวเอง | ทุกหอ |
| GET `/roster?shift_id=` | หอของเวรต้องเป็นหอตัวเอง | หอตัวเอง | ทุกหอ |
| GET `/roster?staff_id=` | ตัวเองทุกหอ; คนอื่นต้องอยู่หอตัวเองและเห็นเฉพาะแถวของเวรในหอตัวเอง | เช่นเดียวกัน | ทุกคน |
| GET `/me/offers`, `/me/handovers`, POST `/me/offers/{id}/response`, POST `/me/attendance/check-in` | ตัวเอง (กติกาเดิม) | ตัวเอง | ตัวเอง |
| **POST `/me/unavailability` (ใหม่)** | ตัวเองที่มีแถว Roster ในเวร | เช่นเดียวกัน | เช่นเดียวกัน |
| GET `/demo/line-sim/offers`, POST `/demo/line-sim/respond` | `staff_id` ต้องเป็นตัวเอง; respond ตรวจเจ้าของ Offer ใน DB (เดิม) | เช่นเดียวกัน | เช่นเดียวกัน |
| PATCH `/unavailability/{id}` | 403 | หอของคนลา | ทุกหอ (ขยายใน AU2 ทั้งสองโหมด) |

## ผลทดสอบ (รันจริงในเครื่องผู้พัฒนา กับ PostgreSQL จริง ไม่เรียก LINE หรือ Bedrock)

- `tests/integration/test_route_permissions.py` 127 เทสต์: inventory ตรงกับ route ของแอป, ทุก route ชนิด session ได้ 401 ทั้งไม่มี cookie และมีแค่ X-Demo-User, matrix ข้างบนต่อคน (101, 105, 201, 202, 301, 900, 902, 950), list/count ที่กรองใน query, คำขอที่ถูกปฏิเสธไม่เขียนข้อมูล, `must_change_password` ได้ 403
- `tests/integration/test_self_leave.py` 22 เทสต์: แจ้งลาตัวเองใช้ actor ของผู้ใช้, คำขอที่ถูกปฏิเสธไม่เขียน Event/Unavailability/Case/Audit/Offer, แจ้งซ้ำต่อเนื่องได้ 409 และไม่เปิดเคสที่สอง, **แจ้งซ้ำพร้อมกันสองการเชื่อมต่อจริง** ได้ 201 กับ 409 มี Event, Unavailability, Case และ Audit EVENT_RECEIVED อย่างละหนึ่ง, `/demo/events` ใช้ SYSTEM actor และ source SIMULATED, ต้องมี Origin ใน session, Job ภายในยังทำงานใน session
- ชุดเทสต์ Backend เดิมผ่านในโหมด demo (ดูผลใน Description ของ PR) แก้เทสต์เดิมหนึ่งตัวที่ตรวจว่า Supervisor แก้วันลาไม่ได้ เพราะข้อ 6.33.4 ขยายสิทธิ์นี้

## ส่งต่อ

- **AU3:** ปุ่มของหน้า Demo control ต้องเปลี่ยนจาก POST `/events` พร้อม X-Demo-User เป็น POST `/demo/events` พร้อม `reporter_staff_id` (ใน session หน้าเดิมจะได้ 403); หน้าพยาบาลแจ้งลาเรียก POST `/me/unavailability` และอ่านเวรจาก GET `/roster?staff_id=<ตัวเอง>`; หน้าเว็บต้องแสดง 403 ทั้งแบบ code (`AUTH_FORBIDDEN`, `AUTH_PASSWORD_CHANGE_REQUIRED`) และข้อความเดิมของ service
- **AU4:** ปิดหรือบังคับ session ของ `/docs`, `/redoc`, `/openapi.json` บน AWS; Basic Auth ของ Demo ครอบ `/api/demo/events` ด้วย
- **AU5:** route `/auth/register` ที่จะเพิ่มต้องเพิ่มใน `INVENTORY` ของเทสต์ (ชนิด auth)
