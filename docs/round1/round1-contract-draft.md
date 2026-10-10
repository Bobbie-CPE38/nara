# ร่าง Contract รอบ 1 หลัง Skeleton

> ร่างไว้คุยกับทีม ยังไม่ใช่ข้อตกลง ทุกจุดที่เขียนว่า "ข้อเสนอ" คือของฉัน ทีมแก้ได้
> ตกลงเสร็จแล้วย้ายเนื้อหาเข้า `docs/workflow.md` ใน PR เดียว ให้ทุกคนรีวิวก่อนแตก branch งาน

---

## 0. สรุปสั้น

รอบ 1 คือการเปิดเส้นทางที่ Skeleton ปิดไว้ สามเรื่องพร้อมกัน

| คน | งาน | ตอนนี้ Skeleton ทำอะไร |
|---|---|---|
| 1 | Coverage ครบ: Role + Skill + Minimum | คำนวณ Headcount จาก Ratio และ Role / Skill แล้ว แต่ Solver ยังไม่ได้ใช้ผล Role / Skill เลือกคน และ `minimum_staff` ยังไม่ถูกใช้ |
| 2 | Hard Rules ของจริง ใช้ร่วมทั้ง Solver และ Safety | มีแค่ 3 ข้อใน `availability_service` Safety ผ่านเสมอถ้า 3 ข้อนี้ผ่าน ไม่ผ่านคือ `FAILED` |
| 3 | Reject แล้วไปคนถัดไป, Head Nurse ไม่อนุมัติ | `REJECT` ตอบ `422`, ไม่อนุมัติตอบ `422` ไม่เขียนอะไร |

ของกลางที่ต้องตกลงก่อนเริ่ม มี 8 หมวด

1. Transition ใหม่ (ข้อ 2)
2. กติกา "ผู้สมัครคนถัดไป" (ข้อ 3)
3. แถวที่แต่ละเส้นทางเขียน และสถานะของ Offer เก่า (ข้อ 4)
4. Audit ของเส้นทางใหม่ (ข้อ 5)
5. คำตอบของ API ที่เปลี่ยน และหน้าเว็บที่ต้องแก้ตาม (ข้อ 6)
6. Hard Rules: รหัส, ที่ใช้, รูปแบบผล (ข้อ 7)
7. Coverage: ความหมายของ Minimum และ Seam จาก Gap ไป Solver (ข้อ 8)
8. Seed Scenario, Test และลำดับ PR (ข้อ 9, 10)

รายการคำถามที่ต้องได้คำตอบในที่ประชุมอยู่ข้อ 12

---

## 1. ขอบเขต

### 1.1 อยู่ในรอบ 1

* ผู้สมัครตอบ `REJECT` → ระบบส่ง Offer ให้คนถัดไป
* Safety ไม่ผ่าน → บันทึกผล แล้วไปคนถัดไป (ตอนนี้เป็น `FAILED`)
* ผู้อนุมัติไม่อนุมัติ → บันทึกผล แล้วไปต่อตามที่ตกลงในข้อ 2
* ไม่เหลือผู้สมัคร → เคสหยุดที่ `MANUAL_HANDOFF` (ตอนนี้เป็น `FAILED`)
* Hard Rules ชุดแรก ใช้ทั้งตอน Solver คัดคน และตอน Safety ตรวจซ้ำ
* Solver เลือกคนที่มี Role / Skill ตรงกับที่ Gap บอกว่าขาด

### 1.2 ไม่อยู่ในรอบ 1 (เขียนไว้กันหลุดขอบเขต)

| เรื่อง | อยู่รอบไหน | ผลต่อรอบ 1 |
|---|---|---|
| Timeout ของผู้สมัครและผู้อนุมัติ | 2, 4 | เคสยังรอได้ไม่จำกัดเวลา |
| OR-Tools, Soft Constraint, คะแนน | 2, 3 | อันดับยังมาจากกติกาตายตัวของ Solver |
| การจัดการเคสหลัง `MANUAL_HANDOFF`, Escalation | 3 | รอบ 1 แค่หยุดที่สถานะนี้พร้อมเหตุผล |
| Gap มากกว่า 1 คนต่อเคส, ส่ง Offer เป็น Wave, `PENDING_APPROVAL` ใน Roster | ยังไม่มีรอบ | หนึ่งเคสยังหาคนแทนได้หนึ่งคน (ดูคำถาม Q11) |
| รวม Event, Lock ต่อ Shift | 4 | สองเคสในเวรเดียวกันยังแยกกันทำ |
| Cross-Ward, `preserve_source_ward_minimum` | 4 | ผู้สมัครยังมาจากหอเดียวกัน |
| LINE จริง | 3 | ยังใช้ LINE Simulator |

---

## 2. Transition ใหม่

### 2.1 ตารางที่เสนอ

ของเดิมใน `domain/workflow/transitions.py` คงไว้ทั้งหมด เพิ่ม 5 เส้น

| # | จาก | ไป | ใครสั่ง | เกิดเมื่อ |z
|---|---|---|---|---|
| T1 | `WAITING_RESPONSE` | `OUTREACH` | `outreach_service.record_response()` เรียก `resume(db, case_id, OUTREACH)` | ผู้สมัครตอบ `REJECT` |
| T2 | `SAFETY_VALIDATION` | `OUTREACH` | handler `validate_safety` คืน `next_status = OUTREACH` | Hard Rule ไม่ผ่านอย่างน้อยหนึ่งข้อ |
| T3 | `WAITING_APPROVAL` | `OUTREACH` | `approval_service.decide()` เรียก `resume(db, case_id, OUTREACH)` | ผู้อนุมัติส่ง `approved = false` |
| T4 | `OUTREACH` | `MANUAL_HANDOFF` | handler `contact_candidate` คืน `next_status = MANUAL_HANDOFF` | ไม่เหลือผู้สมัครที่ติดต่อได้ใน Plan (ข้อ 3) |
| T5 | `OPTIMIZING` | `MANUAL_HANDOFF` | handler `optimize` คืน `next_status = MANUAL_HANDOFF` | Solver ไม่ได้ผู้สมัครเลย (ตอนนี้โยน `NoCandidatesError`) |

ทุกเส้นกลับมาที่ `OUTREACH` จุดเดียว เหตุผล: `contact_candidate` เป็นที่เดียวที่เลือกคนถัดไปและส่ง Offer กติกาเลือกคนจึงอยู่ที่เดียว (ข้อ 3)

### 2.2 สิ่งที่ไม่เปลี่ยน

* `FAILED` ยังตั้งได้จากเส้นทาง D11 เท่านั้น (Exception) Handler ห้ามคืน `FAILED`
* `MANUAL_HANDOFF` → `FAILED` มีอยู่แล้ว ยังไม่เพิ่มเส้นออกจาก `MANUAL_HANDOFF` เส้นอื่น (เป็นงานรอบ 3)
* จุดรอยังมีสองจุด: `WAITING_RESPONSE`, `WAITING_APPROVAL`

### 2.3 ผลต่อ Orchestrator (ไฟล์ของคน 1)

* `resume()` ตอนนี้รับ `next_status` อะไรก็ได้ที่ผ่าน `assert_transition()` และไม่ใช่ `FAILED` T1 กับ T3 จึงใช้ได้โดยไม่ต้องแก้โค้ด ต้องเพิ่ม Test
* T4 กับ T5: Handler คืน `MANUAL_HANDOFF` พร้อม `wait = False` (ตามกติกา `wait` เป็น True เฉพาะเมื่อไปจุดรอ) รอบถัดไปของลูป Orchestrator เห็นว่าอยู่ใน `AUTOMATION_STOPPED_STATUSES` แล้วหยุดเอง ต้องเพิ่ม Test ยืนยัน
* `_MAX_STEPS`: เส้น T2 ทำให้รอบเดียววนได้ (Safety ไม่ผ่าน → `OUTREACH` → `WAITING_RESPONSE` หยุด) ไม่วนไม่จบ เพราะ `OUTREACH` จบที่จุดรอหรือ `MANUAL_HANDOFF` เสมอ ต้องเพิ่ม Test

### 2.4 คำถามที่ต้องตัดสิน

* **Q1** ผู้อนุมัติไม่อนุมัติ (T3) แปลว่าอะไร
  * ก. ไม่เอาผู้สมัครคนนี้ → ไปคนถัดไป (`OUTREACH`) ← ข้อเสนอ
  * ข. ไม่เอาแผนทั้งหมด → `MANUAL_HANDOFF` ให้คนจัดการเอง
  * ค. ให้ผู้อนุมัติเลือกตอนกด (ส่ง field เพิ่ม)
  * เหตุผลของข้อ ก: ง่ายสุด และ `reason` ที่ผู้อนุมัติพิมพ์ยังอยู่ใน Audit ให้คนตามดูได้ ถ้าคนถัดไปหมดก็ไป `MANUAL_HANDOFF` เองตาม T4
* **Q2** ไม่เหลือผู้สมัคร (T4, T5) ไป `MANUAL_HANDOFF` หรือคง `FAILED`
  * ข้อเสนอ: `MANUAL_HANDOFF` เพราะไม่ใช่ระบบขัดข้อง หน้า `cases/[id]` มีคำอธิบายสถานะนี้อยู่แล้ว และ `FAILED` ควรเหลือไว้ให้ Exception จริง
* **Q3** กลับไปคนถัดไปด้วย Plan เดิม หรือรัน Solver ใหม่ (`→ OPTIMIZING`)
  * ข้อเสนอ: ใช้ Plan เดิม แต่ตรวจความพร้อมของคนถัดไปซ้ำตอนจะส่ง (ข้อ 3) เหตุผล: Plan ใหม่ทุกครั้งทำให้อันดับเปลี่ยนกลางเคสและ Timeline อ่านยาก รันใหม่เมื่อไหร่ค่อยตัดสินตอนมี OR-Tools

---

## 3. กติกา "ผู้สมัครคนถัดไป" (แทน Seam 2 เดิม)

### 3.1 ตอนนี้

`outreach_service.send_offer()` หยิบ `CANDIDATE_ITEMS` ที่ `rank = 1` ของ Plan ล่าสุด หนึ่งแถวพอดี ไม่ดูว่าเคยติดต่อไปแล้วหรือยัง ถ้าเรียกซ้ำจะส่งให้คนเดิม

### 3.2 ข้อเสนอ

`contact_candidate` เลือกจาก Plan ล่าสุดของเคส (Seam 1 เดิม) ตามลำดับนี้

1. เรียง Item ตาม `rank` จากน้อยไปมาก
2. ข้าม Item ที่มีแถว `CANDIDATE_OUTREACH` ของเคสนี้อยู่แล้ว ไม่ว่าสถานะอะไร (คนที่เคยติดต่อแล้วไม่ติดต่อซ้ำ)
3. ข้าม Item ที่ไม่ผ่าน Hard Rules ณ ตอนนี้ (ตัวตรวจเดียวกับ Solver และ Safety ข้อ 7)
4. ข้าม Item ที่เจ้าตัวมี Offer ค้างอยู่ที่อื่น (กฎข้อ 4 ของ Solver ตอนนี้: `SENT` ของเคสไหนก็ได้ หรือ `ACCEPTED` ของเคสที่ยังไม่หยุด)
5. ตัวแรกที่เหลือ = ผู้สมัครคนถัดไป ไม่เหลือ → `MANUAL_HANDOFF` (T4)

### 3.3 สิ่งที่ตามมา

* **กฎข้อ 4 ต้องย้ายออกจาก `optimization_service`** ไปอยู่ที่ที่ทั้ง Solver (คน 2) และ Outreach (คน 3) เรียกได้ ไม่งั้นมีกติกาเดียวกันสองที่ ต้องตกลงว่าไฟล์ไหน ใครย้าย (Q4)
* **Lock:** ตอนเลือกคนถัดไปต้องล็อกแถว `STAFF` ของผู้สมัครแบบเดียวกับ Solver (`FOR NO KEY UPDATE` เรียงตาม `id`) ไม่งั้นสองเคสที่ถูก Reject พร้อมกันจะส่ง Offer ให้คนเดียวกัน แล้ว Seam 3 จะเจอ Offer `SENT` สองแถว ลำดับ Lock เดิมยังใช้ได้: Outreach → เคส → `STAFF`
* **คนที่ถูกข้ามต้องไม่หายเงียบ** (กติกาข้อ 6.4: ห้ามหยิบแถวแรกเงียบ ๆ) ข้อเสนอ: ใส่ `skipped` ใน payload ของ `OFFER_SENT` หรือ `MANUAL_HANDOFF` เป็น List ของ `{staff_id, reason}` โดย `reason` เป็นรหัส ไม่ใช่ข้อความอิสระ (Q5)
* **`GET /cases/{id}`:** `candidates[].outreach_status` ยังเป็น `null` สำหรับคนที่ถูกข้าม หน้าเว็บจะแสดง "Not contacted" ซึ่งยังถูก แต่ไม่บอกว่าข้ามเพราะอะไร ถ้าอยากให้เห็นต้องเพิ่ม field (Q6)

---

## 4. แถวที่แต่ละเส้นทางเขียน

### 4.1 ปัญหาที่ต้องแก้ก่อน: Offer เก่าที่ `ACCEPTED`

Seam 4 (`get_accepted_outreach`) ต้องการ `CANDIDATE_OUTREACH` ที่ `ACCEPTED` ของเคส **หนึ่งแถวพอดี** ถ้า Safety ไม่ผ่านหรือผู้อนุมัติไม่อนุมัติ แล้วคนถัดไปตอบรับ เคสจะมี `ACCEPTED` สองแถว Safety รอบสองจะ Error ทันที

กฎข้อ 4 ของ Solver ก็กันคนที่มี `ACCEPTED` บนเคสที่ยังไม่หยุด คนที่ถูกปัดตกจะถูกกันไว้จนเคสจบ ทั้งที่ว่างแล้ว

**ข้อเสนอ:** เมื่อผู้สมัครที่ตอบรับแล้วถูกปัดตก (T2 หรือ T3) ตั้ง Offer ของเขาเป็น `CANCELLED` (ค่ามีใน `OutreachStatus` แล้ว) Seam 4 ยังเป็น "หนึ่งแถวพอดี" ได้ และคนนั้นกลับไปเป็นผู้สมัครของเคสอื่นได้ (Q7)

### 4.2 ตารางการเขียน

| เส้นทาง | ตาราง | ค่าที่เขียน | ใครเขียน |
|---|---|---|---|
| T1 Reject | `CANDIDATE_OUTREACH` | `status = REJECTED`, `response_at = clock.now()` | `outreach_service.record_response()` |
| T2 Safety ไม่ผ่าน | `SAFETY_VALIDATION` | `is_passed = false`, `failure_reason` = รหัส Rule (ข้อ 7.4), `validation_snapshot`, `validated_at = clock.now()` | `safety_service` |
| | `CANDIDATE_OUTREACH` (ของคนที่ไม่ผ่าน) | `status = CANCELLED` | `safety_service` หรือ `outreach_service` (Q8) |
| | `APPROVAL_REQUEST` | **ไม่สร้าง** | |
| T3 ไม่อนุมัติ | `APPROVAL_REQUEST` | `approver_id`, `is_approved = false`, `is_pending = false`, `reason`, `decided_at = clock.now()` | `approval_service.decide()` |
| | `CANDIDATE_OUTREACH` (ของคนที่ไม่ได้รับอนุมัติ) | `status = CANCELLED` | `approval_service` หรือ `outreach_service` (Q8) |
| T4, T5 ไม่เหลือผู้สมัคร | ไม่มีแถวใหม่นอกจาก Audit | | Handler |
| คนถัดไปได้ Offer | `CANDIDATE_OUTREACH` (แถวใหม่) | `status = SENT`, `sent_at = clock.now()` | `outreach_service.send_offer()` |

### 4.3 ลำดับ Lock ของเส้นทางใหม่

ลำดับเดิมทั้งระบบ: `SHIFT` / `ROSTER_ASSIGNMENT` → `CANDIDATE_OUTREACH` หรือ `APPROVAL_REQUEST` → เคส → `STAFF`

* T1: ล็อก Offer ที่ `SENT` (เดิม) → `resume()` ล็อกเคส → `contact_candidate` ล็อก `STAFF` ตรงลำดับเดิม
* T3: ล็อก `APPROVAL_REQUEST` (เดิม) → **ต้องแก้ Offer เป็น `CANCELLED` ก่อนเรียก `resume()`** เพื่อให้ Outreach มาก่อนเคส
* T2: Handler ทำงานตอน Orchestrator ถือ Lock ของเคสอยู่แล้ว การแก้ Offer `ACCEPTED` เป็น `CANCELLED` ตรงนี้คือแตะ Outreach **หลัง** เคส ผิดลำดับถ้ามองตามตัวอักษร
  * ที่ผ่านได้: โค้ดอื่นล็อกเฉพาะ Offer ที่ `SENT` (respond และงาน Timeout ในรอบ 2) ไม่มีใครล็อกแถว `ACCEPTED`
  * ต้องเขียนเป็นกติกาไว้: "การล็อก Outreach ก่อนเคส หมายถึงแถวที่ `SENT` เท่านั้น แถว `ACCEPTED` แก้ได้ภายใต้ Lock ของเคส" (Q9)

---

## 5. Audit

### 5.1 Action ที่ใช้

ทั้งสี่ตัวมีใน `AuditAction` แล้ว ไม่ต้องเพิ่ม Enum

| Action | ใครเขียน | Actor | entity_type | payload ขั้นต่ำ |
|---|---|---|---|---|
| `OFFER_REJECTED` | `outreach_service` | user (ผู้สมัคร) | CANDIDATE_OUTREACH | `outreach_id`, `staff_id` |
| `SAFETY_FAILED` | `validate_safety` | `safety_rule_engine` | SAFETY_VALIDATION | `validation_id`, `staff_id`, `outreach_id`, `failed_rules` (List ของรหัส) |
| `APPROVAL_REJECTED` | `approval_service` | user (ผู้อนุมัติ) | APPROVAL_REQUEST | `approval_id`, `staff_id` (ผู้สมัคร), `outreach_id`, `reason` |
| `MANUAL_HANDOFF` | Handler ที่หยุดเคส (`contact_candidate` หรือ `optimize`) | Actor ของ Handler นั้น | STAFFING_CASES | `reason` (รหัส), `stopped_at` (State ที่หยุด) |

รหัส `reason` ของ `MANUAL_HANDOFF` ที่เสนอ: `NO_CANDIDATE_LEFT` (T4), `NO_FEASIBLE_PLAN` (T5)

### 5.2 กติกา

* `CASE_STATUS_CHANGED` ยังเขียนโดย Orchestrator เท่านั้น ทุกเส้นใหม่จะมีแถวนี้เอง
* ไม่เพิ่ม Action สำหรับการตั้ง Offer เป็น `CANCELLED` ให้ `outreach_id` ใน payload ของ `SAFETY_FAILED` / `APPROVAL_REJECTED` บอกแทน (Q10)
* `payload` ยังห้ามมีข้อมูลผู้ป่วยรายบุคคลและ `password_hash` `reason` ของการไม่อนุมัติเป็นข้อความที่ผู้อนุมัติพิมพ์ ตอนนี้ `APPROVAL_APPROVED` ก็เก็บ `reason` อยู่แล้ว คงแบบเดียวกัน
* `GOLDEN_PATH_AUDIT_ACTIONS` ไม่เปลี่ยน E2E เดิมต้องเขียวเหมือนเดิม

### 5.3 ลำดับ Audit ที่คาดหวังของแต่ละกรณี (ไม่นับ `CASE_STATUS_CHANGED`)

ใช้เป็นเกณฑ์ของ Integration Test แต่ละกรณี

**ก. 201 ปฏิเสธ, 202 รับ, อนุมัติ**
`EVENT_RECEIVED`, `UNAVAILABILITY_CREATED`, `CASE_OPENED`, `GAP_ASSESSED`, `SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_REJECTED` (201), `OFFER_SENT` (202), `OFFER_ACCEPTED` (202), `SAFETY_PASSED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `ASSIGNMENT_CREATED`, `CASE_RESOLVED`

**ข. 201 รับ, Safety ไม่ผ่าน, 202 รับ, อนุมัติ**
... `OFFER_SENT` (201), `OFFER_ACCEPTED` (201), `SAFETY_FAILED` (201), `OFFER_SENT` (202), `OFFER_ACCEPTED` (202), `SAFETY_PASSED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `ASSIGNMENT_CREATED`, `CASE_RESOLVED`

**ค. 201 รับ, ผู้อนุมัติไม่อนุมัติ, 202 รับ, อนุมัติ** (ถ้า Q1 = ก)
... `OFFER_ACCEPTED` (201), `SAFETY_PASSED`, `APPROVAL_REQUESTED`, `APPROVAL_REJECTED`, `OFFER_SENT` (202), `OFFER_ACCEPTED` (202), `SAFETY_PASSED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `ASSIGNMENT_CREATED`, `CASE_RESOLVED`

**ง. ทุกคนปฏิเสธ**
... `OFFER_SENT` (201), `OFFER_REJECTED`, `OFFER_SENT` (202), `OFFER_REJECTED`, `OFFER_SENT` (203), `OFFER_REJECTED`, `MANUAL_HANDOFF` (`NO_CANDIDATE_LEFT`) เคสจบที่ `MANUAL_HANDOFF`

**จ. Solver ไม่ได้ใครเลย**
`EVENT_RECEIVED`, `UNAVAILABILITY_CREATED`, `CASE_OPENED`, `GAP_ASSESSED`, `MANUAL_HANDOFF` (`NO_FEASIBLE_PLAN`) ต้องตกลงว่ามี `SOLVER_EXECUTED` ก่อนหรือไม่ (Q12)

---

## 6. API และหน้าเว็บ

### 6.1 คำตอบที่เปลี่ยน

| Route | ตอนนี้ | รอบ 1 |
|---|---|---|
| `POST /demo/line-sim/respond` กับ `REJECT` | `422` ไม่เขียน DB | `200` `{outreach_id, outreach_status: "REJECTED", case_id, case_status}` |
| `POST /approvals/{id}/decision` กับ `approved = false` | `422` ไม่เขียน DB | `200` `{approval_id, is_approved: false, case_id, case_status}` |

* รูปแบบ Body ของคำตอบไม่เปลี่ยน มีแค่ค่าใหม่ จึงไม่ต้องแก้ Type ฝั่ง Frontend
* `case_status` ในคำตอบเป็นได้หลายค่า: `WAITING_RESPONSE` (ส่งให้คนถัดไปแล้ว), `MANUAL_HANDOFF` (ไม่เหลือใคร), `FAILED` (D11)
* การตรวจที่มาก่อนยังเหมือนเดิมทั้งหมด: respond ตรวจ `outreach_id` (PR #30) และ `409`, decision ตรวจ `404 → 403 → 409`
* ลบข้อ 9.2 ของ `workflow.md` ("ขอบเขตของ Skeleton") ส่วนที่บอกว่า `REJECT` และไม่อนุมัติตอบ `422`
* `reason` ตอนไม่อนุมัติ: บังคับส่งหรือไม่ (Q13) ข้อเสนอ: บังคับ และไม่ว่าง ไม่ส่งตอบ `422`

### 6.2 หน้าเว็บที่ต้องแก้ตาม

| หน้า | เจ้าของ | ต้องแก้ |
|---|---|---|
| `demo/line-sim` | คน 3 | เอาข้อความ "Rejection is not supported" ออก ปุ่ม Reject ใช้งานจริง แสดงผลตาม `case_status` |
| `approvals` | คน 1 | ปุ่ม Reject ตอนนี้แสดง `422` เป็น Error ต้องแสดงผลสำเร็จ และมีช่องกรอก `reason` ถ้า Q13 บังคับ กรณี `case_status = MANUAL_HANDOFF` ต้องมีข้อความของมัน |
| `cases/[id]` | คน 2 | ตารางผู้สมัครจะมี Offer หลายสถานะ (`REJECTED`, `CANCELLED`, `SENT`) Timeline ยาวขึ้น ต้องเช็กว่า `MANUAL_HANDOFF` ยัง Poll ต่อตามที่ออกแบบไว้ |
| `roster` | คน 3 | ไม่เปลี่ยน |
| `demo/control` | คน 1 | ไม่เปลี่ยน ถ้าไม่เพิ่มปุ่มโหลด Scenario (Q16) |

---

## 7. Hard Rules (งานของคน 2 ที่ทุกคนเรียกใช้)

### 7.1 ตอนนี้

`availability_service` มี 3 ข้อ ใช้โดย Solver, Safety และ Execute

| ข้อ | Exception ตอนนี้ |
|---|---|
| `STAFF.status = ACTIVE` | `StaffNotActiveError` |
| ไม่มี Roster ในเวรของเคสที่สถานะอยู่ใน `COMMITTED_ROSTER_STATUSES` | `StaffAlreadyOnShiftError` |
| ไม่มี `STAFF_UNAVAILABILITY` ชนช่วงเวลาของเวร | `StaffUnavailableError` |

`HARD_CONSTRAINT_POLICY` มีคอลัมน์รออยู่: `minimum_rest_hours`, `maximum_daily_hours`, `maximum_weekly_hours`, `prevent_shift_conflict`, `require_matching_role`, `require_matching_skill`, `require_active_staff`, `preserve_minimum_staffing`, `preserve_source_ward_minimum`

### 7.2 ต้องตกลง: รอบ 1 ทำข้อไหน

ข้อเสนอให้คน 2 ยืนยัน

| รหัสที่เสนอ | มาจาก | รอบ 1 | หมายเหตุ |
|---|---|---|---|
| `STAFF_NOT_ACTIVE` | `require_active_staff` + ข้อ 1 เดิม | ทำ | |
| `ALREADY_ON_SHIFT` | ข้อ 2 เดิม | ทำ | |
| `UNAVAILABLE` | ข้อ 3 เดิม | ทำ | |
| `SHIFT_CONFLICT` | `prevent_shift_conflict` | ทำ | มี Roster ในเวรอื่นที่เวลาชนกัน ตอนนี้ยังไม่เช็ก |
| `ROLE_MISMATCH` | `require_matching_role` | ทำ | ต้องรู้ว่าเคสขาด Role อะไร (ข้อ 8.3) |
| `SKILL_MISMATCH` | `require_matching_skill` | ทำ | ต้องรู้ว่าเคสขาด Skill อะไร (ข้อ 8.3) |
| `INSUFFICIENT_REST` | `minimum_rest_hours` | ทำ | คิดจาก Roster ก่อนและหลังเวรของเคส |
| `DAILY_HOURS_EXCEEDED` | `maximum_daily_hours` | Q14 | ต้องนิยาม "วัน" ของเวรข้ามคืน |
| `WEEKLY_HOURS_EXCEEDED` | `maximum_weekly_hours` | Q14 | ต้องนิยาม "สัปดาห์" และคิดจาก Roster ตรง ๆ ไปก่อน (Working Time Snapshot เป็นรอบ 3) |
| `SOURCE_WARD_MINIMUM` | `preserve_source_ward_minimum` | ไม่ทำ | รอ Cross-Ward รอบ 4 |
| (เรื่อง Coverage ของเวรเป้าหมาย) | `preserve_minimum_staffing` | Q15 | ความหมายต้องตกลงกับ Coverage ของคน 1 |

### 7.3 ต้องตกลง: Interface

* ตัวตรวจเป็น Pure Function ใน `domain/constraints/` (ไฟล์มีชื่อใน `repo-structure.md` แล้ว: `codes.py`, `context.py`, `hard_rules.py`, `evaluator.py`) ไม่อ่าน DB เอง ผู้เรียกโหลดข้อมูลแล้วส่งเข้าไป แบบเดียวกับ `gap_calculator`
* ผลที่คืน: List ของรหัสที่ไม่ผ่าน (ว่าง = ผ่าน) ไม่ใช่ Exception เพราะ Safety ต้องบันทึกครบทุกข้อที่ไม่ผ่าน
* ผู้เรียกสามที่ต้องได้ผลเดียวกันจากข้อมูลเดียวกัน: Solver (คัดคนออก), `contact_candidate` (ข้ามคน ข้อ 3), Safety (บันทึกผล)
* `availability_service.assert_available()` ที่ Execute (คน 3) เรียกอยู่: คงชื่อและ Exception เดิมไว้เป็นเปลือกห่อตัวตรวจใหม่ หรือให้ Execute เปลี่ยนไปเรียกตัวใหม่ (Q17)
* Policy ที่ใช้: `policy_service.get_hard_constraint_policy(db)` ตัวเดิม (ตรึง `id = 1`) ธง Boolean ใน Policy ที่เป็น `false` = ข้ามข้อนั้น

### 7.4 ต้องตกลง: สิ่งที่ Safety บันทึก

| คอลัมน์ | ค่าที่เสนอ |
|---|---|
| `SAFETY_VALIDATION.is_passed` | `false` เมื่อมีรหัสไม่ผ่านอย่างน้อยหนึ่งข้อ |
| `failure_reason` | รหัสที่ไม่ผ่าน คั่นด้วย `,` เรียงตามลำดับในตาราง 7.2 ไม่ใช่ข้อความอิสระ |
| `validation_snapshot` | ข้อมูลที่ใช้ตัดสิน เช่น `{"checked_rules": [...], "failed_rules": [...], "policy_id": 1, "shift_id": 1, "staff_id": 201}` รายละเอียดให้คน 2 เสนอ |
| `hard_constraint_policy_id` | Policy ที่ใช้ตรวจจริง |

กรณีที่ยังเป็น `FAILED` (D11) ไม่ใช่ Safety ไม่ผ่าน: ข้อมูลผิดรูป เช่น `ProposedShiftMismatchError`, Item ไม่ได้อยู่ในเคสนี้, ไม่เจอ Offer `ACCEPTED` หนึ่งแถวพอดี พวกนี้คือระบบผิด ไม่ใช่ผู้สมัครไม่เหมาะ

---

## 8. Coverage (งานของคน 1 ที่ Solver ต้องใช้)

### 8.1 ตอนนี้

* `gap_calculator` คิด `minimum_required_staff = ceil(patient_count / patients_per_nurse)` และ Gap ของ Role / Skill ตาม Requirement
* `STAFFING_GAP` + แถว Role / Skill ถูกบันทึกแล้ว พร้อม Snapshot
* `STAFFING_REQUIREMENTS.required_staff` และ `minimum_staff` **ไม่ถูกใช้** (เอกสารเขียนไว้ชัดว่าไม่ใช้เป็นเป้าหมาย)
* Solver ยังไม่อ่าน Gap เลย ผู้สมัครตายตัว 201, 202, 203

### 8.2 ต้องตกลง: "Minimum" คืออะไร

ชื่องานคือ "Role + Skill + Minimum" แต่ตอนนี้มีตัวเลขจำนวนคนสองแหล่ง

* **Q18** `minimum_staff` ใน Requirement ใช้ทำอะไร
  * ก. เป็นพื้นขั้นต่ำ: เป้าหมาย = `max(ceil(patient_count / ratio), minimum_staff)` ← ข้อเสนอ
  * ข. ไม่ใช้ต่อ ลบออกจากความหมายของ Coverage คงไว้แค่ในตาราง
  * ค. ใช้แยกสองระดับ: ต่ำกว่า `required_staff` = ควรหาคน, ต่ำกว่า `minimum_staff` = วิกฤต (กระทบ Escalation รอบ 3)
* ถ้าเลือก ก หรือ ค `calculate_gap()` ต้องรับ Input เพิ่ม และ Snapshot ใน `STAFFING_GAP` ต้องเก็บค่านั้นด้วย (Migration ใหม่) ต้องแจ้งทีมก่อนตามกติกาแก้ Signature

### 8.3 ต้องตกลง: Seam ใหม่ "Gap → Solver"

Solver ต้องรู้ว่าต้องหาคนแบบไหน ข้อเสนอ

| หัวข้อ | กติกา |
|---|---|
| แถวที่อ่าน | `STAFFING_GAP` ของเคส ที่ `id` มากสุด ไม่เจอ → Error (เคสผ่าน `ASSESSING` มาแล้วต้องมี) |
| Role ที่ต้องการ | แถว `STAFFING_GAP_ROLE` ที่ `gap_count > 0` |
| Skill ที่ต้องการ | แถว `STAFFING_GAP_SKILL` ที่ `gap_count > 0` |
| ผู้สมัครที่ผ่าน | มี Role ที่ต้องการ และมี Skill ที่ต้องการ**ครบทุกตัว** (เคสหนึ่งหาคนเดียว คนนั้นต้องปิดได้ทุก Gap) |
| ไม่มี Role / Skill Gap เลย (ขาดแค่จำนวนคน) | ผู้สมัคร Role ไหนก็ได้ที่ Requirement ของเวรมี |
| ใครโหลด | ฟังก์ชันเดียวใน `gap_service` ให้ Solver และ Safety เรียก ไม่เขียน Query เอง |

ตัวอย่างที่ใช้ทดสอบได้กับ Seed ปัจจุบัน: 101 (มี Skill ICU) ลาเวร 1 → ICU เหลือ 1 จากที่ต้องการ 2 → ผู้สมัครต้องมี ICU → 201 และ 203 ผ่าน, 202 ไม่ผ่าน (`SKILL_MISMATCH`)

### 8.4 คำถามอื่นของ Coverage

* **Q11** Gap มากกว่า 1 (เช่น 104 กับ 105 ลาเวรเดียวกัน ตอนนี้ได้สองเคสแยกกัน) รอบ 1 คงแบบ "หนึ่งเคสหนึ่งคน" ใช่ไหม ข้อเสนอ: ใช่ เพราะการรวมเคสคืองาน Aggregation รอบ 4
* **Q19** ตรวจ Coverage ซ้ำก่อน `RESOLVED` ไหม: หลังสร้าง Roster ของคนมาแทน ถ้าเวรยังขาด (เพราะมีคนลาเพิ่มระหว่างทาง) เคสนี้ยัง `RESOLVED` ได้ ข้อเสนอ: `RESOLVED` ได้ เพราะเคสนี้ปิดการขาดของ Event ตัวเองแล้ว การขาดใหม่มีเคสของมันเอง
* **Q20** `GET /cases/{id}` ควรคืนค่าที่ใช้คำนวณด้วยไหม (`patient_count`, `patients_per_nurse`, จำนวนที่ต้องการ, จำนวนที่มี) ตอนนี้หน้าเว็บแสดงแค่ "Short by 1" โดยไม่บอกว่าจากกี่คน

---

## 9. Seed Scenario และ Test

### 9.1 Scenario ที่ต้องมี

ตอนนี้มีแค่ `seed/scenarios/golden_case.py` ชื่อไฟล์อื่นอยู่ใน `repo-structure.md` แล้ว

| ไฟล์ | เจ้าของ | สถานการณ์ | ข้อมูลที่ต้องเพิ่มจาก Golden Case |
|---|---|---|---|
| `candidate_reject.py` | คน 3 | 201 ปฏิเสธ, 202 รับ (กรณี ก) และทุกคนปฏิเสธ (กรณี ง) | ไม่ต้องเพิ่ม ใช้ Golden Case ได้ |
| `head_nurse_reject.py` | คน 3 | 900 ไม่อนุมัติ 201 (กรณี ค) | ไม่ต้องเพิ่ม |
| `safety_failure.py` | คน 2 | 201 รับแล้ว Safety ไม่ผ่าน (กรณี ข) | ต้องทำให้ 201 ผิด Rule **หลัง** ได้ Offer เช่น เพิ่ม Roster เวรอื่นที่ชนเวลา ระหว่างรอคำตอบ |
| `no_feasible_solution.py` | คน 2 | ไม่มีผู้สมัครผ่าน Hard Rules เลย (กรณี จ) | ทำให้ 201, 202, 203 ไม่ผ่านทั้งหมด |
| (ใหม่) Skill Gap | คน 1 + คน 2 | 101 ลา ต้องได้คนที่มี ICU (ข้อ 8.3) | ไม่ต้องเพิ่ม |

* **Q16** Scenario โหลดยังไง
  * ก. ใช้ใน Test เท่านั้น ผ่าน Fixture `POST /demo/reset` โหลด Golden Case อย่างเดียวเหมือนเดิม ← ข้อเสนอ
  * ข. `POST /demo/reset?scenario=` และปุ่มในหน้า `demo/control` (เพิ่มงาน Frontend ของคน 1)

### 9.2 กติกาของ Test

* ทุกกรณีใน 5.3 มี Integration Test ที่ตรวจลำดับ Audit ตรงตามนั้น และตรวจสถานะสุดท้ายของเคส
* กรณีที่จบ `RESOLVED` ตรวจ Roster ด้วย: คนที่ได้ `REPLACEMENT` ต้องเป็นคนที่ได้รับอนุมัติ ไม่ใช่คนที่ถูกปัดตก
* `test_transitions.py`: ตาราง Transition ที่ยอมรับต้องเพิ่ม 5 เส้นใหม่ (ไฟล์ของคน 1) ตอนนี้ Test ยอมรับเฉพาะเส้น Golden Path กับ `→ FAILED` เส้นใหม่จะแดงจนกว่าจะแก้ Test พร้อมกัน
* `tests/e2e/test_workforce_recovery.py` ต้องเขียวตลอด ไม่แก้ลำดับ Golden Path
* Fixture `stub_handlers` ใน `tests/integration/conftest.py`: ถ้า Handler ตัวไหนมีทางออกเพิ่ม (เช่น `OUTREACH → MANUAL_HANDOFF`) Stub ยังคืนเส้น Golden Path เหมือนเดิม ไม่ต้องแก้
* Test ที่ตอนนี้คาดหวัง `422` ของ `REJECT` และไม่อนุมัติ และ Test ที่คาด `FAILED` จาก `NoCandidatesError` / Safety ไม่ผ่าน ต้องเปลี่ยนใน PR ของเจ้าของเส้นทางนั้น

---

## 10. ลำดับ PR

Branch Protection เปิดแล้ว ทุก PR ต้องมี `staging` ล่าสุดและ CI เขียว

| ลำดับ | PR | ใครทำ | มีอะไร | ต้องเข้าก่อน |
|---|---|---|---|---|
| 0 | Contract | คน 1 | `workflow.md` (ข้อ 5, 6.4, 7, 8, 9), `transitions.py` + `test_transitions.py` 5 เส้นใหม่, Test ของ Orchestrator สำหรับ `MANUAL_HANDOFF` ที่มาจาก Handler **ไม่มีการเปลี่ยนพฤติกรรม** เพราะยังไม่มี Handler ตัวไหนคืนเส้นใหม่ | ทุกตัวข้างล่าง |
| 1a | Hard Rules: ตัวตรวจ + รหัส | คน 2 | `domain/constraints/` + Unit Test ยังไม่ต่อกับ Workflow | 2a, 2b, 3 |
| 1b | Seam Gap → Solver | คน 1 | ฟังก์ชันใน `gap_service` + Test และคำตอบของ Q18 ถ้ามี | 2a |
| 1c | ย้ายกฎข้อ 4 (Offer ค้าง) เป็นของกลาง | ตาม Q4 | Refactor ไม่เปลี่ยนพฤติกรรม | 2b |
| 2a | Solver ใช้ Hard Rules + Gap, `T5` | คน 2 | `optimize`, `optimization_service`, Scenario `no_feasible_solution` | |
| 2b | คนถัดไป + Reject (`T1`, `T4`) | คน 3 | `contact_candidate`, `outreach_service`, หน้า `line-sim`, Scenario `candidate_reject` | |
| 3 | Safety บันทึกผลไม่ผ่าน (`T2`) | คน 2 | `validate_safety`, `safety_service`, Scenario `safety_failure` | หลัง 2b (ต้องมีกติกาคนถัดไป) |
| 4 | ไม่อนุมัติ (`T3`) | คน 3 | `approval_service`, Scenario `head_nurse_reject` | หลัง 2b |
| 5 | หน้า `approvals` | คน 1 | Reject ใช้งานจริง + `reason` | หลัง 4 |
| 6 | หน้า `cases/[id]` | คน 2 | เช็กการแสดงผลของสถานะและ Offer ใหม่ | หลัง 2b, 3, 4 |

ข้อที่เสี่ยงพังเงียบ (เคยเจอในขั้นที่ 4)

* PR 3 กับ PR 4 แก้เส้นทางที่มาบรรจบกันที่ `OUTREACH` ทั้งคู่ต้องมี Test ที่รันกับ `contact_candidate` ตัวจริงของ 2b ไม่ใช่ Stub
* PR 2a เปลี่ยนว่าใครอยู่ใน Plan Test ของคน 3 ที่สมมติว่ามี 201, 202, 203 ครบอาจแดงหลังรวม ให้ Test อ่านจำนวนผู้สมัครจาก Plan จริง
* ทุก PR จะชนกันที่ `workflow.md` ข้อ 13 เหมือนเดิม เก็บทุกแถว

---

## 11. ผลต่อเอกสารและไฟล์กลาง

| ไฟล์ | ต้องแก้ | ใคร |
|---|---|---|
| `docs/workflow.md` ข้อ 4 | `MANUAL_HANDOFF` เปลี่ยนจาก "ภายหลัง" เป็นใช้แล้ว (เฉพาะการหยุด) | PR 0 |
| ข้อ 5 | เพิ่มหัวข้อย่อยของ 5 เส้นใหม่ | PR 0 |
| ข้อ 6.4 | Seam 2 ใหม่ (ข้อ 3), Seam 4 เพิ่มกติกา `CANCELLED` (ข้อ 4.1), Seam ใหม่ Gap → Solver (ข้อ 8.3), กติกา Lock (ข้อ 4.3) | PR 0 |
| ข้อ 7 | เพิ่มตาราง Audit ของเส้นใหม่ และลำดับของแต่ละกรณี (ข้อ 5) | PR 0 |
| ข้อ 8 | เปลี่ยนชื่อจาก "Stub ของแต่ละขั้น" และอัปเดตแถว Solver, Outreach, Response, Safety, Approval | เจ้าของแต่ละแถว ใน PR ของตัวเอง |
| ข้อ 9.2, 9.3 | ลบส่วน `422`, เพิ่มค่าใหม่ของคำตอบ (ข้อ 6.1) | PR 0 |
| ข้อ 12 | ย้ายเรื่องที่ทำแล้วออก | PR สุดท้ายของรอบ |
| `domain/workflow/transitions.py` | 5 เส้นใหม่ | PR 0 |
| `domain/enums.py` | ไม่ต้องเพิ่มค่า ถ้าตอบ Q10 ว่าไม่เพิ่ม Action | |
| `docs/walking-skeleton.md` | ตาราง "หลัง Skeleton" ใส่สถานะของรอบ 1 | PR สุดท้ายของรอบ |

---

## 12. รายการคำถามสำหรับที่ประชุม

เรียงตามที่ขวางงานมากสุด คำตอบของ Q1 ถึง Q10 ต้องได้ก่อนเปิด PR 0

| # | คำถาม | ข้อเสนอ | ขวางใคร |
|---|---|---|---|
| Q1 | ไม่อนุมัติแล้วไปไหน | ไปคนถัดไป (`OUTREACH`) | 3, 1 |
| Q2 | ไม่เหลือผู้สมัครเป็นสถานะอะไร | `MANUAL_HANDOFF` | 2, 3 |
| Q3 | ไปคนถัดไปด้วย Plan เดิมหรือรัน Solver ใหม่ | Plan เดิม + ตรวจความพร้อมซ้ำ | 2, 3 |
| Q4 | กฎ "มี Offer ค้าง" ย้ายไปอยู่ไฟล์ไหน ใครย้าย | อยู่กับตัวตรวจกลางของคน 2 คน 2 ย้าย | 2, 3 |
| Q5 | คนที่ถูกข้ามตอนเลือกคนถัดไป บันทึกยังไง | `skipped` ใน payload ของ `OFFER_SENT` / `MANUAL_HANDOFF` | 3 |
| Q6 | `GET /cases/{id}` ต้องบอกเหตุผลที่ผู้สมัครถูกข้ามไหม | ยังไม่ต้อง ดูจาก Timeline | 1, 2 |
| Q7 | Offer ของคนที่ถูกปัดตกหลังตอบรับ ตั้งเป็น `CANCELLED` ใช่ไหม | ใช่ | 2, 3 |
| Q8 | ใครเป็นคนตั้ง `CANCELLED` | ฟังก์ชันเดียวใน `outreach_service` ให้ Safety และ Approval เรียก | 2, 3 |
| Q9 | ยอมรับกติกา "แถว `ACCEPTED` แก้ได้ภายใต้ Lock ของเคส" ไหม | ยอมรับ และเขียนลงข้อ 6.2 | ทุกคน |
| Q10 | เพิ่ม Audit Action สำหรับ `CANCELLED` ไหม | ไม่เพิ่ม | 3 |
| Q11 | รอบ 1 คง "หนึ่งเคสหนึ่งคน" ใช่ไหม | ใช่ | ทุกคน |
| Q12 | Solver ไม่ได้ใครเลย เขียน `SOLVER_EXECUTED` และแถว Plan (`INFEASIBLE`) ก่อน `MANUAL_HANDOFF` ไหม | เขียน เพื่อให้ Timeline บอกว่า Solver รันแล้ว | 2 |
| Q13 | `reason` ตอนไม่อนุมัติบังคับไหม | บังคับ ไม่ว่าง | 3, 1 |
| Q14 | รอบ 1 ทำ Rule ชั่วโมงรายวันและรายสัปดาห์ไหม นิยามวันกับสัปดาห์ยังไง | ให้คน 2 เสนอ | 2 |
| Q15 | `preserve_minimum_staffing` หมายถึงอะไร ใครตรวจ | คุยคู่กับ Q18 | 1, 2 |
| Q16 | Scenario โหลดผ่าน Test อย่างเดียว หรือมีปุ่มในหน้า Demo | Test อย่างเดียว | 1 |
| Q17 | `assert_available()` คงไว้เป็นเปลือก หรือให้ Execute เปลี่ยนไปเรียกตัวใหม่ | คงไว้เป็นเปลือก | 2, 3 |
| Q18 | `minimum_staff` ใช้ทำอะไร | เป็นพื้นขั้นต่ำของเป้าหมายจำนวนคน | 1, 2 |
| Q19 | ตรวจ Coverage ซ้ำก่อน `RESOLVED` ไหม | ไม่ตรวจ | 1 |
| Q20 | `GET /cases/{id}` คืนค่าที่ใช้คำนวณ Gap เพิ่มไหม | เพิ่ม | 1, 2 |

---

## 13. สิ่งที่ฉันยังไม่ได้ตรวจ

* ยังไม่ได้ไล่ Test ทั้งหมดว่าตัวไหนจะแดงเมื่อเปลี่ยนคำตอบ `422` และ `FAILED` รายการในข้อ 9.2 มาจากการอ่านโค้ดของ Service ไม่ได้รัน
* ข้อ 4.3 เรื่อง Lock เป็นการวิเคราะห์จากโค้ดปัจจุบัน ยังไม่มี Test พิสูจน์ ต้องมี Test สอง Connection แบบที่ทำกับ Orchestrator และ Solver
* ตาราง Hard Rules ข้อ 7.2 เดาจากชื่อคอลัมน์ของ `HARD_CONSTRAINT_POLICY` ความหมายจริงของแต่ละคอลัมน์ต้องให้คน 2 ยืนยัน
