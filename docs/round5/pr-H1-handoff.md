# PR H1 — Handover และตัวกลางสร้างเวร

H1 สร้างข้อมูลส่งมอบเวรจาก DB ล้วน ไม่เรียก LLM และไม่ส่ง LINE การแสดงในหน้าเว็บเป็น U5 การส่ง LINE เป็น H2

## Migration

`e8c4b2a6f0d9` ต่อจาก N1 `a4d8e1b7c3f5` เพิ่ม FK `STRUCTURED_HANDOVER.roster_assignment_id` แบบ NOT NULL และ Unique หนึ่ง Handover ต่อหนึ่งแถว Roster ไม่ Backfill และไม่เดาความสัมพันธ์ ถ้ามี Handover เก่าที่ไม่คาดไว้ Migration จะล้มและต้องตรวจข้อมูลก่อน

ก่อนลองกับฐานข้อมูลพัฒนาให้รัน `alembic upgrade head` หลัง Backup ตามขั้นตอนของทีม H1 ทดสอบ Migration กับฐาน `_test` ไม่ได้อัปเกรดหรือ Reset ฐาน Demo ของผู้พัฒนา

## จุดที่คน 2 ใช้ใน N2

`roster_service.restore_late_arrival(db, original=..., check_in_at=..., actor_id=...)` เป็นตัวสร้างแถวใหม่ตอนมาสาย:

- N2 ล็อกตาม workflow 6.11 ตรวจซ้ำเรื่อง check-in/การทำซ้ำ และยกเลิกแถวเดิมก่อนเรียก
- ตัวนี้ต้องได้แถวเดิมที่ `CANCELLED` และเวลา check-in อยู่ก่อนเวลาจบที่มีผล
- สร้างแถวใหม่จากเวลา check-in ถึงเวลาจบเดิม รักษา `assignment_type` และ `candidate_source`
- ถ้าแถวเก่ามี Handover ใช้เคสเดิมสร้าง Handover ของแถวใหม่ด้วยช่วงเวลาที่มาจริง ถ้าไม่มี ไม่สร้าง Handover
- แถวเก่าและ Handover เก่าเก็บเป็นประวัติ ไม่เอา `transferred_from_assignment_id` มาใช้ซ้ำ เพราะลิงก์นั้นมี Unique และเป็นของแถวประวัติเดิม
- ไม่มี Commit, ไม่มี Row Lock เพิ่ม, ไม่อ่าน `ATTENDANCE` N2 รับผิดชอบ Attendance, การย่อ Unavailability, การประเมิน Gap และการยกเลิก Offer/คำขอที่เกิน ใน Transaction เดียวกัน

ทางอื่นใช้ `roster_service.create_assignment()` ผ่าน `create_replacement()`, `create_transfer()` หรือ `handoff_service.assign()` ตามเดิม การอนุมัติเองเรียกทางตัดสินเดียวกับคนกดอยู่แล้ว

## จุดที่ H2 และ U5 ใช้

`handover_service.ensure()` สร้าง Snapshot และ Audit ใน Transaction ที่สร้างเวร ไม่มี Commit การเรียกซ้ำคืนแถวเดิมโดยไม่เขียน Audit ซ้ำ Unique Constraint เป็นด่านสุดท้ายเมื่อสอง Connection แข่งกัน H2 เพิ่ม delivery intent ใน Transaction นี้ได้ และต้องตรวจว่ายังใช้งานอยู่ก่อนส่งและทุกครั้งที่ลองใหม่ตาม Contract

`GET /me/handovers` ใช้ตัวตนจาก `X-Demo-User` เท่านั้น ส่วน `GET /cases/{id}` เพิ่ม `handovers` รูปข้อมูลเดียวกัน ทั้งสองคืนปัจจุบันก่อน ตามด้วยประวัติ แต่ละกลุ่มเรียงเวลาใหม่ก่อน แล้วใช้ ID ตัดสินเมื่อ Demo Clock ทำให้เวลาเท่ากัน

แต่ละรายการมี `handover_id`, `roster_assignment_id`, `active`, `generated_at`, `content` ตัวอ่านต้องดู `active` เพื่อแยกข้อมูลเตรียมขึ้นเวรกับประวัติ Handover ใช้งานเมื่อแถว Roster เป็น `ASSIGNED` และ Clock ยังไม่ถึงเวลาจบที่มีผล เวรที่ยังไม่เริ่มก็แสดงได้ แถวต้นทางที่ยัง `ASSIGNED` หลังย้ายกลางเวรจะหยุดใช้งานตรง `actual_end_at`

`content.version = 1` ตาม workflow 6.25 Snapshot ไม่เปลี่ยนเมื่อ DB เปลี่ยนภายหลัง เหตุของเคสมาจาก `CASE_OPENED.payload.event_id` ไม่ใช่ Event ที่มี ID น้อยสุด ถ้าไม่มีต้นทางที่ถูกต้องถือเป็นข้อผิดพลาด ไม่เดาค่า การอนุมัติผ่าน D11 จึงคงผลอนุมัติ แต่ Rollback เวรและ Handover พร้อมให้เคสเป็น `FAILED`

## การตรวจ

- `test_handover.py`: Snapshot/ต้นทางทั้งห้าเหตุ, การสร้างซ้ำ, Rollback, อนุมัติปกติ/อัตโนมัติ/จัดเอง/ย้าย, seam ตอนมาสาย, API/ประวัติ และสอง Connection
- `test_handover_migration.py`: เส้น Migration เดียว, Downgrade/Upgrade, NOT NULL/FK/Unique, SQL แบบ Offline และการปฏิเสธข้อมูลเก่าที่ระบุ Roster ไม่ได้
- Test เดิมเพิ่ม CASE_OPENED ให้ fixture ของเคสตรงกับข้อมูลจริง แล้วแยก Audit ตั้งต้นออกจากการตรวจงานแต่ละขั้น Assertions ของลำดับ Audit ยังคงเทียบรายการตรงตัว และ Golden Path เพิ่ม `HANDOVER_GENERATED` ก่อน `ASSIGNMENT_CREATED`
