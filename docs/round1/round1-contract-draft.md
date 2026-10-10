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
| 3 | ส่ง Offer เป็น Wave, Reject แล้วไปต่อ, Head Nurse ไม่อนุมัติ | ส่ง Offer ให้อันดับ 1 คนเดียว, `REJECT` ตอบ `422`, ไม่อนุมัติตอบ `422` ไม่เขียนอะไร |

ของกลางที่ต้องตกลงก่อนเริ่ม มี 8 หมวด

1. Transition ใหม่ (ข้อ 2)
2. กติกาเลือกผู้สมัครของ Wave (ข้อ 3)
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

* ส่ง Offer เป็น Wave: หลายคนพร้อมกันตาม `rank` (Q11)
* ผู้สมัครตอบ `REJECT` → รอคนที่เหลือใน Wave ถ้าไม่เหลือใครให้รอ ส่ง Wave ถัดไป
* Safety ไม่ผ่าน → บันทึกผล แล้วส่ง Wave ถัดไป (ตอนนี้เป็น `FAILED`)
* ผู้อนุมัติไม่อนุมัติ → บันทึกผล แล้วไปต่อตามที่ตกลงในข้อ 2
* ไม่เหลือผู้สมัคร → เคสหยุดที่ `MANUAL_HANDOFF` (ตอนนี้เป็น `FAILED`)
* Merge Gap: Event ใหม่ของเวรที่มีเคสเปิดอยู่ใช้เคสเดิม มี Window รอรวม Event ก่อนหาคน (ข้อ 2.5)
* Hard Rules ชุดแรก ใช้ทั้งตอน Solver คัดคน และตอน Safety ตรวจซ้ำ
* Solver เลือกคนที่มี Role / Skill ตรงกับที่ Gap บอกว่าขาด

### 1.2 ไม่อยู่ในรอบ 1 (เขียนไว้กันหลุดขอบเขต)

| เรื่อง | อยู่รอบไหน | ผลต่อรอบ 1 |
|---|---|---|
| Timeout ของผู้สมัครและผู้อนุมัติ | 2, 4 | เคสยังรอได้ไม่จำกัดเวลา |
| OR-Tools, Soft Constraint, คะแนน | 2, 3 | อันดับยังมาจากกติกาตายตัวของ Solver |
| การจัดการเคสหลัง `MANUAL_HANDOFF`, Escalation | 3 | รอบ 1 แค่หยุดที่สถานะนี้พร้อมเหตุผล |
| เคสเดียวรับคนมาแทนมากกว่า 1 คน, `PENDING_APPROVAL` ใน Roster | ขึ้นกับ Q21 | Wave ใช้ในรอบ 1 แล้ว (Q11) แต่ทางเดินของเคสเมื่อต้องรับมากกว่า 1 คนยังไม่ได้ตกลง |
| Lock ต่อ Shift ข้ามเคส | 4 | Merge Gap ย้ายมาทำในรอบ 1 แล้ว รายละเอียดยังไม่ได้เขียนลงร่างนี้ (รอคำตอบเรื่องเคสรับหลายคนและ Offer ตอนดึงเคสกลับ) |
| Cross-Ward (ยืมคนข้ามหอ) | 4 | ผู้สมัครยังมาจากหอเดียวกัน กฎ `SOURCE_WARD_MINIMUM_VIOLATION` เขียนในรอบ 1 แต่ยังไม่มีกรณีใช้จริง (ข้อ 7.2) |
| LINE จริง | 3 | ยังใช้ LINE Simulator |

---

## 2. Transition ใหม่

### 2.1 ตารางที่เสนอ

ของเดิมใน `domain/workflow/transitions.py` คงไว้ทั้งหมด เพิ่ม 5 เส้น

| # | จาก | ไป | ใครสั่ง | เกิดเมื่อ |z
|---|---|---|---|---|
| T1 | `WAITING_RESPONSE` | `OUTREACH` | `outreach_service.record_response()` เรียก `resume(db, case_id, OUTREACH)` | ผู้สมัครตอบ `REJECT` ทุกครั้ง แม้ Wave ยังมี Offer `SENT` เหลือ `contact_candidate` เป็นคนตัดสินว่ารอต่อหรือส่ง Wave ใหม่ (ข้อ 3.2) |
| T2 | `SAFETY_VALIDATION` | `OUTREACH` | handler `validate_safety` คืน `next_status = OUTREACH` | Hard Rule ไม่ผ่านอย่างน้อยหนึ่งข้อ |
| T3 | `WAITING_APPROVAL` | `OUTREACH` | `approval_service.decide()` เรียก `resume(db, case_id, OUTREACH)` | ผู้อนุมัติส่ง `approved = false` |
| T4 | `OUTREACH` | `MANUAL_HANDOFF` | handler `contact_candidate` คืน `next_status = MANUAL_HANDOFF` | ไม่เหลือผู้สมัครที่ติดต่อได้ใน Plan และเคสไม่มี Offer `SENT` ค้าง (ข้อ 3) |
| T5 | `OPTIMIZING` | `MANUAL_HANDOFF` | handler `optimize` คืน `next_status = MANUAL_HANDOFF` | Solver ไม่ได้ผู้สมัครเลย (ตอนนี้โยน `NoCandidatesError`) |

ทุกเส้นกลับมาที่ `OUTREACH` จุดเดียว เหตุผล: `contact_candidate` เป็นที่เดียวที่เลือกคนของ Wave และส่ง Offer กติกาเลือกคนจึงอยู่ที่เดียว (ข้อ 3)

### 2.2 สิ่งที่ไม่เปลี่ยน

* `FAILED` ยังตั้งได้จากเส้นทาง D11 เท่านั้น (Exception) Handler ห้ามคืน `FAILED`
* `MANUAL_HANDOFF` → `FAILED` มีอยู่แล้ว ยังไม่เพิ่มเส้นออกจาก `MANUAL_HANDOFF` เส้นอื่น (เป็นงานรอบ 3)
* จุดรอเดิมสองจุดไม่เปลี่ยน: `WAITING_RESPONSE`, `WAITING_APPROVAL` Merge Gap เพิ่มจุดรอที่สาม `WAITING_MERGE_WINDOW` (ข้อ 2.5)

### 2.3 ผลต่อ Orchestrator (ไฟล์ของคน 1)

* `resume()` ตอนนี้รับ `next_status` อะไรก็ได้ที่ผ่าน `assert_transition()` และไม่ใช่ `FAILED` T1 กับ T3 จึงใช้ได้โดยไม่ต้องแก้โค้ด ต้องเพิ่ม Test
* T4 กับ T5: Handler คืน `MANUAL_HANDOFF` พร้อม `wait = False` (ตามกติกา `wait` เป็น True เฉพาะเมื่อไปจุดรอ) รอบถัดไปของลูป Orchestrator เห็นว่าอยู่ใน `AUTOMATION_STOPPED_STATUSES` แล้วหยุดเอง ต้องเพิ่ม Test ยืนยัน
* `_MAX_STEPS`: เส้น T2 ทำให้รอบเดียววนได้ (Safety ไม่ผ่าน → `OUTREACH` → `WAITING_RESPONSE` หยุด) ไม่วนไม่จบ เพราะ `OUTREACH` จบที่จุดรอหรือ `MANUAL_HANDOFF` เสมอ T1 ตอน Wave ยังเหลือคนที่ยังไม่ตอบก็เหมือนกัน (`WAITING_RESPONSE` → `OUTREACH` → `WAITING_RESPONSE` โดยไม่ส่ง Offer เพิ่ม) ต้องเพิ่ม Test ทั้งสองแบบ

### 2.4 คำถามที่ต้องตัดสิน

* **Q1** ผู้อนุมัติไม่อนุมัติ (T3) แปลว่าอะไร
  * ก. ไม่เอาผู้สมัครคนนี้ → ไปคนถัดไป (`OUTREACH`) ← ข้อเสนอ
  * เหตุผลของข้อ ก: ง่ายสุด และ `reason` ที่ผู้อนุมัติพิมพ์ยังอยู่ใน Audit ให้คนตามดูได้ ถ้าคนถัดไปหมดก็ไป `MANUAL_HANDOFF` เองตาม T4
* **Q2** ไม่เหลือผู้สมัคร (T4, T5) ไป `MANUAL_HANDOFF` หรือคง `FAILED`
  * `MANUAL_HANDOFF` เพราะไม่ใช่ระบบขัดข้อง หน้า `cases/[id]` มีคำอธิบายสถานะนี้อยู่แล้ว และ `FAILED` ควรเหลือไว้ให้ Exception จริง
* **Q3** ส่ง Wave ถัดไปด้วย Plan เดิม หรือรัน Solver ใหม่ (`→ OPTIMIZING`)
  * ใช้ Plan เดิม แต่ตรวจความพร้อมของคนใน Wave ซ้ำตอนจะส่ง (ข้อ 3) เหตุผล: Plan ใหม่ทุกครั้งทำให้อันดับเปลี่ยนกลางเคสและ Timeline อ่านยาก รันใหม่เมื่อไหร่ค่อยตัดสินตอนมี OR-Tools

---

### 2.5 Merge Gap (ทำในรอบ 1)

Event ใหม่ของเวรที่มีเคสเปิดอยู่ ไม่เปิดเคสใหม่ ใช้เคสเดิมและเพิ่ม `STAFFING_GAP` แถวใหม่ เวรหนึ่งจึงมีเคสที่ยังเดินอยู่ได้เคสเดียว

```text
PART A: Source (หนึ่ง Transaction)
Change detected → Update/Create source data → Create event (RECEIVED)

PART B: Gap flow (หนึ่ง Transaction ต่อ Event)
Event → Lock shift → Read current data → Update requirement (เฉพาะ Event ที่เกิน Threshold) → Calculate gap
      → มีเคสเปิดของเวรนี้ไหม
           ├─ มี  → ใช้เคสเดิม → Event = PROCESSED → เพิ่ม Gap แถวใหม่บนเคสนั้น  ← MERGE
           └─ ไม่มี → เวรขาดคนไหม
                    ├─ ไม่ขาด → Event = IGNORED จบ
                    └─ ขาด   → เปิดเคส + เริ่ม Window → Event = PROCESSED → เพิ่ม Gap

Window ปิด → Gap แถวล่าสุด (รวมแล้ว) เข้า Optimization
```

Gap รวมกันยังไง: ไม่มีการบวกแถว ทุกครั้งคิดใหม่จากข้อมูลปัจจุบันของเวร แถวล่าสุดจึงรวมทุกการลาที่ผ่านมาแล้ว

| ส่วน | รวมยังไง |
|---|---|
| ความต้องการ (`required_staff`) | UPDATE ในแถว Requirement เดิม เฉพาะ Event ที่เกิน Threshold |
| จำนวนคนในเวร | นับใหม่จาก Roster ที่ `ASSIGNED` การลาทุกครั้งที่ผ่านมาถูกหักแล้ว |
| `headcount_gap` | `effective_minimum - current_valid_staff` คิดครั้งเดียวจากสองบรรทัดบน (ข้อ 8.2) |
| Gap ของ Role / Skill | คิดใหม่ทุกตัว: จำนวนที่ต้องการ ลบ คนในเวรที่มี Role / Skill นั้น |

สิ่งที่ตกลงแล้ว

| หัวข้อ | กติกา |
|---|---|
| จุดรอใหม่ | เพิ่มสถานะ `WAITING_MERGE_WINDOW` ก่อน `ASSESSING` เป็นจุดรอที่สาม (T6, T7) |
| ความยาว Window | ค่าตั้งได้ เริ่มที่ 10 นาที แล้วปรับ |
| Window = 0 | Demo ปกติและ Test เดิมตั้งเป็น 0: เคสเข้าจุดรอแล้วออกทันทีใน Request เดียวกัน `POST /events` ยังเดินรวดเดียวถึง `WAITING_RESPONSE` เหมือนเดิม ตั้งเป็น 10 เฉพาะ Test และ Demo ของการ Merge |
| เก็บเวลาปิด | คอลัมน์ใหม่ `merge_window_closes_at` ใน `STAFFING_CASES` ตั้งตอนเปิดเคส = `clock.now()` + ความยาว Window (Migration ใหม่) |
| ปิด Window ใน Demo | เลื่อน Clock ต้องมี Route เลื่อนนาฬิกาและปุ่มในหน้า `demo/control` Route นี้เรียกฟังก์ชันปิด Window ตัวเดียวกับ Job เพราะเลื่อนนาฬิกาอย่างเดียว Job ไม่รันเอง |
| Gap = 0 ตอน Window ปิด | รอบ 1 ไม่เกิด Event มีแต่การลา Gap ระหว่าง Window จึงมีแต่เพิ่ม ไม่ต้องมีกิ่งปิดเคส ต้องกลับมาคิดเมื่อมี Event ที่ทำให้ Gap ลดได้ |
| Event ใหม่หลัง Window ปิดแล้ว | ใช้เคสเดิม คิด Gap ใหม่ เก็บของที่ทำไปแล้วทั้งหมด (Offer ที่ส่ง, คนที่ตอบรับ, คำขออนุมัติ) หาคนเพิ่มเฉพาะส่วนที่ขาดเพิ่ม วิธีที่เคสรับ Gap ใหม่ดู Q26 |
| ส่งทีละคนหรือเป็น Batch | ผู้ใช้เลือกจำนวนได้ รายละเอียดดู Q25 |

Transition ที่เพิ่มจาก 2.1

| # | จาก | ไป | ใครสั่ง | เกิดเมื่อ |
|---|---|---|---|---|
| T6 | `OPEN` | `WAITING_MERGE_WINDOW` | การรับ Event ตอนเปิดเคส | ทุกเคสใหม่ แทนเส้น `OPEN → ASSESSING` |
| T7 | `WAITING_MERGE_WINDOW` | `ASSESSING` | ฟังก์ชันปิด Window เรียก `resume()` | `clock.now() >= merge_window_closes_at` (Window = 0 เกิดทันที) |
| T8 | (ไม่ใช้) | | | เส้น `EXECUTING → OUTREACH` เป็นของแบบทีละคน Q24 เลือกแบบขนานแล้ว เส้นที่ต้องเพิ่มจริงขึ้นกับคำตอบย่อยของ Q24 |

ยังต้องตัดสิน

* **Q24** เคสที่ขาดมากกว่า 1 คน เดินยังไงหลังมีคนตอบรับ คำถามนี้คนละเรื่องกับจำนวน Offer ที่ส่ง (Q25) Q25 คือส่งหากี่คน Q24 คือคนที่ตอบรับแล้วเดินผ่าน Safety, Approval, Execute ยังไง
  * ก. ทีละคน วนจนครบ: ไม่เลือก
  * ข. ขนานหลายคน ← **ตอบแล้ว เลือกแบบนี้** คนที่ตอบรับหลายคนเข้า Safety และรออนุมัติพร้อมกัน ต้องรื้อ Seam 3, 4, 7 คำถามย่อยที่ต้องตอบต่อ
    * อนุมัติยังไง: กดต่อคน (หนึ่ง `APPROVAL_REQUEST` ต่อผู้สมัคร ตารางเดิมใช้ได้ ปฏิเสธรายคนได้) หรือกดครั้งเดียวทั้งชุด (ต้องแก้ตาราง, API, หน้า `approvals`) ข้อเสนอ: กดต่อคน
    * สถานะของเคสตอนแต่ละคนอยู่คนละขั้น: เคสมีสถานะเดียว แต่คนหนึ่งอาจรออนุมัติ อีกคนยังไม่ตอบ ต้องตกลงว่าเคสอยู่สถานะไหน และสถานะรายคนเก็บที่ไหน
    * Seam 3 รับคำตอบเฉพาะเคสที่อยู่ `WAITING_RESPONSE` ถ้าเคสไปต่อแล้ว คนที่ตอบช้าจะได้ `409` ต้องแก้กติกานี้
    * Seam 4 ต้องรับ `ACCEPTED` หลายแถว Safety ตรวจทีละคนและบันทึกหนึ่ง `SAFETY_VALIDATION` ต่อคน
    * จัดเวร (Execute) ทีละคนเมื่ออนุมัติ หรือรอครบทุกคนก่อน
    * เคสเป็น `RESOLVED` เมื่อไหร่: ครบจำนวนที่ขาด ถ้าได้ไม่ครบและไม่เหลือผู้สมัคร คนที่จัดเวรไปแล้วอยู่ต่อ เคสไป `MANUAL_HANDOFF`
    * ข้อเสนอของ Q26 ก ใช้คู่กับแบบทีละคน ต้องคิดใหม่สำหรับแบบขนาน
* **Q25** "ผู้ใช้เลือกจำนวนที่ส่ง" ต้องรู้ 4 อย่าง
  * ใครเลือก (Head Nurse หรือคนตั้งค่าระบบ)
  * เลือกที่ไหน (ค่าใน Policy, ค่าตั้งของระบบ หรือหน้าเว็บตอนเคสเปิด ถ้าเป็นหน้าเว็บ เคสต้องมีจุดรอให้คนเลือก)
  * ค่าเริ่มต้นเมื่อไม่มีใครเลือก
  * แทนสูตรขนาด Wave ใน Q11 (`headcount_gap` + สำรอง) หรือสูตรนั้นเป็นค่าเริ่มต้น
* **Q26** Event ใหม่หลัง Window ปิด เคสรับ Gap ใหม่ยังไง
  * ก. ไม่เปลี่ยนสถานะของเคส แค่เพิ่ม Gap แถวใหม่ เคสอ่านแถวล่าสุดเองเมื่อผ่าน `OUTREACH` หรือ `EXECUTING` รอบถัดไป ← ข้อเสนอ ใช้ได้ถ้า Q24 = ก ไม่ต้องมี Transition ถอยหลัง และของที่ทำไปแล้วไม่ถูกแตะ
  * ข. ดึงเคสกลับไป `ASSESSING` แล้วเดินกลับมาสถานะเดิม ต้องเพิ่ม Transition ถอยหลังจากทุกสถานะ และจำสถานะเดิมไว้
  * เคสที่จบแล้ว (`RESOLVED`, `UNRESOLVED`, `FAILED`) หรือ `MANUAL_HANDOFF` ไม่นับเป็นเคสเปิด Event ใหม่เปิดเคสใหม่
* **Audit ของ Event ที่ Merge** ข้อเสนอ: `EVENT_RECEIVED`, `UNAVAILABILITY_CREATED`, `GAP_ASSESSED` เขียนบน `case_id` ของเคสเดิม ไม่มี `CASE_OPENED` ไม่เพิ่ม Action ใหม่
* **Job ปิด Window ตัวจริง** รอบ 1 มีแค่ฟังก์ชันกับ Route ของ Demo หรือมี Scheduler ด้วย ข้อเสนอ: แค่ฟังก์ชันกับ Route

ผลต่อข้ออื่นของร่างนี้ที่**ยังไม่ได้แก้** รอคำตอบ Q24 ถึง Q26

* ข้อ 3 และ Q11: ขนาด Wave และบรรทัดสุดท้ายของ Q11 ที่ว่าการรวมเคสเป็นงานรอบ 4
* ข้อ 3.4 Q21: ข้อเสนอ "เคสหนึ่งรับหนึ่งคน" ใช้ไม่ได้แล้ว เพราะเคสที่ Merge ขาดได้มากกว่า 1 คน Q24 มาแทน
* ข้อ 5.3: ลำดับ Audit ทุกกรณีสมมติเคสรับหนึ่งคน และยังไม่มีขั้น Window
* ข้อ 8.3: กติกา "ผู้สมัครต้องมี Skill ครบทุกตัว" ต้องเขียนใหม่สำหรับเคสที่รับหลายคน

---

## 3. กติกาเลือกผู้สมัครของ Wave (แทน Seam 2 เดิม)

### 3.2 ตอนนี้

`contact_candidate` เลือกจาก Plan ล่าสุดของเคส (Seam 1 เดิม) ตามลำดับนี้

1. ถ้าเคสยังมี Offer `SENT` อยู่ = Wave เดิมยังไม่จบ ไม่ส่งเพิ่ม กลับไปรอที่ `WAITING_RESPONSE`
2. เรียง Item ตาม `rank` จากน้อยไปมาก
3. ข้าม Item ที่เคสนี้ติดต่อไปแล้วและใช้ไม่ได้อีก (สถานะไหนนับ ดู Q22)
4. ข้าม Item ที่ไม่ผ่าน Hard Rules ณ ตอนนี้ (ตัวตรวจเดียวกับ Solver และ Safety ข้อ 7)
5. ข้าม Item ที่เจ้าตัวมี Offer ค้างอยู่ที่อื่น (กฎข้อ 4 ของ Solver ตอนนี้: `SENT` ของเคสไหนก็ได้ หรือ `ACCEPTED` ของเคสที่ยังไม่หยุด)
6. หยิบตามลำดับจนครบขนาด Wave (Q11) เหลือน้อยกว่าขนาด Wave ก็ส่งเท่าที่มี ไม่เหลือเลย → `MANUAL_HANDOFF` (T4)

### 3.3 สิ่งที่ตามมา

* **กฎข้อ 4 ต้องย้ายออกจาก `optimization_service`** ไปอยู่ที่ที่ Solver (คน 2) 
**ย้ายไปไหน**: availability_service เป็นฟังก์ชัน Public ชื่อ staff_with_open_offers(db, staff_ids) คืน Set ของ staff_id ที่มี Offer ค้าง
**ใครย้าย**: คน 2 ใน PR 1c เป็น Refactor ไม่เปลี่ยนพฤติกรรม Solver เปลี่ยนไปเรียกตัวใหม่ และลบ _staff_with_open_offers() ออกจาก optimization_service
**ทำไมไม่อยู่ใน domain/constraints/**: กฎนี้ต้อง Query CANDIDATE_OUTREACH แต่ตัวตรวจในข้อ 7.3 เป็น Pure Function ที่ไม่อ่าน DB จึงต้องอยู่ชั้น Service
**ทำไมเป็น availability_service**: เป็นของกลางเรื่อง "คนนี้ใช้ได้ไหม" อยู่แล้ว Outreach เรียกได้โดยไม่ต้อง Import Solver
**ใครเรียก**: Solver (คัดคนออกจาก Plan) และ contact_candidate (ข้ามคน ข้อ 3.2 ขั้นที่ 5)
**Safety ห้ามเรียก**: ผู้สมัครที่กำลังถูกตรวจมี Offer ACCEPTED ของเคสตัวเองอยู่ ถ้าเรียกจะไม่ผ่านทุกครั้ง กฎนี้จึงไม่อยู่ในรายการรหัสของข้อ 7.2
**รหัสเหตุผลตอนข้ามคน (ใช้กับ Q5)**: HAS_OPEN_OFFER (Q4)
* **Lock:** ตอนเลือกคนของ Wave ต้องล็อกแถว `STAFF` ของผู้สมัครทั้ง Plan แบบเดียวกับ Solver (`FOR NO KEY UPDATE` เรียงตาม `id`) ไม่งั้นสองเคสที่ถูก Reject พร้อมกันจะส่ง Offer ให้คนเดียวกัน แล้ว Seam 3 จะเจอ Offer `SENT` สองแถว ลำดับ Lock เดิมยังใช้ได้: Outreach → เคส → `STAFF`
* **คนที่ถูกข้ามต้องไม่หายเงียบ** (กติกาข้อ 6.4: ห้ามหยิบแถวแรกเงียบ ๆ) ใส่ `skipped` ใน payload ของ `OFFER_SENT` แถวแรกของ Wave (หนึ่ง Wave มี `OFFER_SENT` หลายแถว ข้อ 5.1) หรือของ `MANUAL_HANDOFF` เมื่อไม่เหลือใคร เป็น List ของ `{staff_id, reason}` โดย `reason` เป็นรหัส ไม่ใช่ข้อความอิสระ (Q5)
* **`GET /cases/{id}`:** `candidates[].outreach_status` ยังเป็น `null` สำหรับคนที่ถูกข้าม หน้าเว็บจะแสดง "Not contacted" ซึ่งยังถูก ไม่บอกว่าข้ามเพราะอะไร (Q6)
* **เมื่อมีคนตอบ `ACCEPT` จนครบจำนวนที่เคสต้องหา:** Offer ที่ยัง `SENT` ของเคสเป็น `CANCELLED` ใน Transaction เดียวกับคำตอบ ก่อนเรียก `resume()` (Q11, ข้อ 4.2) คนที่ถูกยกเลิกกดตอบทีหลังได้ `409` ตามการตรวจเดิมของ Seam 3 (ไม่เจอ Offer `SENT`)
* **กฎ Offer ค้างกันคนมากขึ้น:** ทุกคนใน Wave ถูกกันจากเคสอื่นจนกว่าจะตอบหรือถูกยกเลิก Wave ยิ่งใหญ่ เคสอื่นของช่วงเวลาเดียวกันยิ่งเหลือผู้สมัครน้อย

### 3.4 คำถามที่ Wave เปิดเพิ่ม

* **Q21** เคสหนึ่งรับคนมาแทนกี่คน และ "จำนวนที่ขาด" ใน Q11 อ่านจากไหน
  * ปัญหา: `headcount_gap` คิดจากทั้งเวร ไม่ใช่ต่อเคส 104 กับ 105 ลาเวรเดียวกันได้สองเคส เคสที่สองเห็น Gap = 2 ถ้าทั้งสองเคสหาคนตาม `headcount_gap` ของตัวเอง เวรจะได้คนเกิน
  * ทางเดินตอนนี้รองรับทีละคน: Seam 4 ต้องเจอ `ACCEPTED` หนึ่งแถวพอดี, หนึ่งเคสมี `APPROVAL_REQUEST` ที่ Pending หนึ่งแถว, Seam 3 รับคำตอบเฉพาะเคสที่อยู่ `WAITING_RESPONSE`
  * ก. รอบ 1 เคสหนึ่งรับหนึ่งคน (หนึ่ง Event = คนลาหนึ่งคน) Wave ของ Golden Case = 1 + สำรอง 1 = 2 คน คนแรกที่ `ACCEPT` ได้ไป ที่เหลือ `CANCELLED` ← ข้อเสนอ
  * ข. เคสรับได้หลายคน ต้องเพิ่ม Transition ให้เคสกลับมารอคำตอบหลังจัดคนแรก, แก้ Seam 4 กับ Approval ให้ทำงานต่อคน และกันสองเคสของเวรเดียวกันหาคนซ้ำ งานของทั้งสามคนใหญ่ขึ้น
* **Q22** คนที่ Offer ถูก `CANCELLED` ตอนยังไม่ได้ตอบ ติดต่อซ้ำใน Wave ถัดไปได้ไหม
  * ได้ ← ข้อเสนอ ไม่งั้น Plan 3 คนหมดเร็ว: Wave แรก 201 + 202, 201 รับ (202 ถูกยกเลิก), Safety ไม่ผ่าน เหลือแค่ 203
  * ขั้นที่ 3 ของข้อ 3.2 จึงข้ามเฉพาะคนที่ `REJECTED` และคนที่ถูกปัดตกหลังตอบรับ (`CANCELLED` ที่ `response_at` ไม่ว่าง) คนที่ `CANCELLED` โดย `response_at` ว่างได้ Offer แถวใหม่

---

## 4. แถวที่แต่ละเส้นทางเขียน

### 4.1 ปัญหาที่ต้องแก้ก่อน: Offer เก่าที่ `ACCEPTED`

Seam 4 (`get_accepted_outreach`) ต้องการ `CANDIDATE_OUTREACH` ที่ `ACCEPTED` ของเคส **หนึ่งแถวพอดี** ถ้า Safety ไม่ผ่านหรือผู้อนุมัติไม่อนุมัติ แล้วคนถัดไปตอบรับ เคสจะมี `ACCEPTED` สองแถว Safety รอบสองจะ Error ทันที Wave ไม่ทำให้ข้อนี้แย่ลงถ้าเคสรับทีละคน (Q21 = ก) เพราะ `ACCEPT` แรกยกเลิก Offer `SENT` ที่เหลือทันที

กฎข้อ 4 ของ Solver ก็กันคนที่มี `ACCEPTED` บนเคสที่ยังไม่หยุด คนที่ถูกปัดตกจะถูกกันไว้จนเคสจบ ทั้งที่ว่างแล้ว

 เมื่อผู้สมัครที่ตอบรับแล้วถูกปัดตก (T2 หรือ T3) ตั้ง Offer ของเขาเป็น `CANCELLED` (ค่ามีใน `OutreachStatus` แล้ว) Seam 4 ยังเป็น "หนึ่งแถวพอดี" ได้ และคนนั้นกลับไปเป็นผู้สมัครของเคสอื่นได้ (Q7)

### 4.2 ตารางการเขียน

| เส้นทาง | ตาราง | ค่าที่เขียน | ใครเขียน |
|---|---|---|---|
| T1 Reject | `CANDIDATE_OUTREACH` | `status = REJECTED`, `response_at = clock.now()` | `outreach_service.record_response()` |
| T2 Safety ไม่ผ่าน | `SAFETY_VALIDATION` | `is_passed = false`, `failure_reason` = รหัส Rule (ข้อ 7.4), `validation_snapshot`, `validated_at = clock.now()` | `safety_service` |
| | `CANDIDATE_OUTREACH` (ของคนที่ไม่ผ่าน) | `status = CANCELLED` | `outreach_service` (Q8) |
| | `APPROVAL_REQUEST` | **ไม่สร้าง** | |
| T3 ไม่อนุมัติ | `APPROVAL_REQUEST` | `approver_id`, `is_approved = false`, `is_pending = false`, `reason`, `decided_at = clock.now()` | `approval_service.decide()` |
| | `CANDIDATE_OUTREACH` (ของคนที่ไม่ได้รับอนุมัติ) | `status = CANCELLED` | `outreach_service` (Q8) |
| T4, T5 ไม่เหลือผู้สมัคร | ไม่มีแถวใหม่นอกจาก Audit | | Handler |
| ส่ง Wave | `CANDIDATE_OUTREACH` (แถวใหม่ หนึ่งแถวต่อคน) | `status = SENT`, `sent_at = clock.now()` ค่าเดียวกันทั้ง Wave | `outreach_service.send_offer()` (ตอนนี้รับอันดับ 1 คนเดียว ต้องแก้ให้รับหลาย Item) |
| `ACCEPT` ครบจำนวนที่ต้องหา | `CANDIDATE_OUTREACH` ที่ยัง `SENT` ของเคส | `status = CANCELLED`, `response_at` คงเป็น NULL | `outreach_service.record_response()` |

### 4.3 ลำดับ Lock ของเส้นทางใหม่

ลำดับเดิมทั้งระบบ: `SHIFT` / `ROSTER_ASSIGNMENT` → `CANDIDATE_OUTREACH` หรือ `APPROVAL_REQUEST` → เคส → `STAFF`

* T1: ล็อก Offer ที่ `SENT` (เดิม) → `resume()` ล็อกเคส → `contact_candidate` ล็อก `STAFF` ตรงลำดับเดิม
* คำตอบใน Wave: `record_response()` ต้องล็อก Offer `SENT` **ทุกแถวของเคส** เรียงตาม `id` ก่อนตรวจและเขียน ไม่ใช่ล็อกแถวของผู้ตอบแล้วค่อยล็อกแถวอื่นตอนยกเลิก ไม่งั้นสองคนที่ `ACCEPT` พร้อมกันถือแถวของตัวเองแล้วรอแถวของอีกฝ่ายเป็นวง ตอนนี้ Seam 3 ล็อกแถวของผู้ตอบแถวเดียว ต้องแก้ และต้องมี Test สอง Connection
* T3: ล็อก `APPROVAL_REQUEST` (เดิม) → **ต้องแก้ Offer เป็น `CANCELLED` ก่อนเรียก `resume()`** เพื่อให้ Outreach มาก่อนเคส
* T2: Handler ทำงานตอน Orchestrator ถือ Lock ของเคสอยู่แล้ว การแก้ Offer `ACCEPTED` เป็น `CANCELLED` ตรงนี้คือแตะ Outreach **หลัง** เคส ผิดลำดับถ้ามองตามตัวอักษร
  * ที่ผ่านได้: โค้ดอื่นล็อกเฉพาะ Offer ที่ `SENT` (respond และงาน Timeout ในรอบ 2) ไม่มีใครล็อกแถว `ACCEPTED`
  * "การล็อก Outreach ก่อนเคส หมายถึงแถวที่ `SENT` เท่านั้น แถว `ACCEPTED` แก้ได้ภายใต้ Lock ของเคส" (Q9)

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

Action เดิมที่ payload เปลี่ยนเพราะ Wave

* `OFFER_SENT`: ยังเป็นหนึ่งแถวต่อคน เรียงตาม `rank` payload เดิม (`outreach_id`, `staff_id`, `channel`) เพิ่ม `wave` (เลข Wave ของเคส เริ่มที่ 1) แถวแรกของ Wave มี `skipped` (Q5)
* `OFFER_ACCEPTED`: เพิ่ม `cancelled_outreach_ids` (List ของ Offer ที่ถูกยกเลิกเพราะครบแล้ว ว่างได้) (Q10)

### 5.2 กติกา

* `CASE_STATUS_CHANGED` ยังเขียนโดย Orchestrator เท่านั้น ทุกเส้นใหม่จะมีแถวนี้เอง
* ไม่เพิ่ม Action สำหรับการตั้ง Offer เป็น `CANCELLED` ให้ `outreach_id` ใน payload ของ `SAFETY_FAILED` / `APPROVAL_REJECTED` บอกแทน ส่วน Offer ที่ถูกยกเลิกเพราะ Wave ครบแล้ว ให้ `cancelled_outreach_ids` ของ `OFFER_ACCEPTED` บอก (Q10)
* `payload` ยังห้ามมีข้อมูลผู้ป่วยรายบุคคลและ `password_hash` `reason` ของการไม่อนุมัติเป็นข้อความที่ผู้อนุมัติพิมพ์ ตอนนี้ `APPROVAL_APPROVED` ก็เก็บ `reason` อยู่แล้ว คงแบบเดียวกัน
* `GOLDEN_PATH_AUDIT_ACTIONS` **เปลี่ยน**: Golden Case ขาด 1 คน ขนาด Wave ตาม Q11 = 1 + 1 = 2 จึงมี `OFFER_SENT` สองแถว (201, 202) แล้ว 201 ตอบรับ ต้องแก้ค่าคงที่และ E2E ใน PR เดียวกับที่เปิด Wave (PR 2b)

### 5.3 ลำดับ Audit ที่คาดหวังของแต่ละกรณี (ไม่นับ `CASE_STATUS_CHANGED`)

ใช้เป็นเกณฑ์ของ Integration Test แต่ละกรณี ทุกกรณีสมมติว่า Wave = 2 คน (หา 1 + สำรอง 1 ตาม Q11 กับ Q21 = ก) และคนที่ถูกยกเลิกตอนยังไม่ตอบติดต่อซ้ำได้ (Q22) ถ้าคำตอบเป็นอย่างอื่นต้องเขียนลำดับใหม่

**Golden Path (เปลี่ยน). 201 รับ, อนุมัติ**
`EVENT_RECEIVED`, `UNAVAILABILITY_CREATED`, `CASE_OPENED`, `GAP_ASSESSED`, `SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_ACCEPTED` (201, ยกเลิกของ 202), `SAFETY_PASSED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `ASSIGNMENT_CREATED`, `CASE_RESOLVED`

**ก. 201 ปฏิเสธ, 202 รับ, อนุมัติ**
... `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_REJECTED` (201), `OFFER_ACCEPTED` (202), `SAFETY_PASSED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `ASSIGNMENT_CREATED`, `CASE_RESOLVED` ไม่มี `OFFER_SENT` เพิ่มหลัง 201 ปฏิเสธ เพราะ 202 ยังไม่ตอบ

**ข. 201 รับ, Safety ไม่ผ่าน, 202 รับ, อนุมัติ**
... `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_ACCEPTED` (201, ยกเลิกของ 202), `SAFETY_FAILED` (201), `OFFER_SENT` (202, Wave 2), `OFFER_SENT` (203, Wave 2), `OFFER_ACCEPTED` (202, ยกเลิกของ 203), `SAFETY_PASSED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `ASSIGNMENT_CREATED`, `CASE_RESOLVED`

**ค. 201 รับ, ผู้อนุมัติไม่อนุมัติ, 202 รับ, อนุมัติ** (ถ้า Q1 = ก)
... `OFFER_ACCEPTED` (201, ยกเลิกของ 202), `SAFETY_PASSED`, `APPROVAL_REQUESTED`, `APPROVAL_REJECTED`, `OFFER_SENT` (202, Wave 2), `OFFER_SENT` (203, Wave 2), `OFFER_ACCEPTED` (202, ยกเลิกของ 203), `SAFETY_PASSED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `ASSIGNMENT_CREATED`, `CASE_RESOLVED`

**ง. ทุกคนปฏิเสธ**
... `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_REJECTED` (201), `OFFER_REJECTED` (202), `OFFER_SENT` (203, Wave 2), `OFFER_REJECTED` (203), `MANUAL_HANDOFF` (`NO_CANDIDATE_LEFT`) เคสจบที่ `MANUAL_HANDOFF`

**จ. Solver ไม่ได้ใครเลย**
`EVENT_RECEIVED`, `UNAVAILABILITY_CREATED`, `CASE_OPENED`, `GAP_ASSESSED`, `MANUAL_HANDOFF` (`NO_FEASIBLE_PLAN`) ต้องตกลงว่ามี `SOLVER_EXECUTED` ก่อน (Q12)

---

## 6. API และหน้าเว็บ

### 6.1 คำตอบที่เปลี่ยน

| Route | ตอนนี้ | รอบ 1 |
|---|---|---|
| `POST /demo/line-sim/respond` กับ `REJECT` | `422` ไม่เขียน DB | `200` `{outreach_id, outreach_status: "REJECTED", case_id, case_status}` |
| `POST /approvals/{id}/decision` กับ `approved = false` | `422` ไม่เขียน DB | `200` `{approval_id, is_approved: false, case_id, case_status}` |

* รูปแบบ Body ของคำตอบไม่เปลี่ยน มีแค่ค่าใหม่ จึงไม่ต้องแก้ Type ฝั่ง Frontend
* `case_status` ในคำตอบเป็นได้หลายค่า: `WAITING_RESPONSE` (ยังรอคนอื่นใน Wave หรือส่ง Wave ถัดไปแล้ว), `MANUAL_HANDOFF` (ไม่เหลือใคร), `FAILED` (D11)
* ผู้สมัครที่ Offer ถูก `CANCELLED` เพราะมีคนรับครบแล้ว กดตอบทีหลังได้ `409` ตามการตรวจเดิม ไม่เพิ่ม Status Code ใหม่
* การตรวจที่มาก่อนยังเหมือนเดิมทั้งหมด: respond ตรวจ `outreach_id` (PR #30) และ `409`, decision ตรวจ `404 → 403 → 409`
* ลบข้อ 9.2 ของ `workflow.md` ("ขอบเขตของ Skeleton") ส่วนที่บอกว่า `REJECT` และไม่อนุมัติตอบ `422`
* `reason` ตอนไม่อนุมัติ: บังคับและไม่ว่าง ไม่ส่งเหตุผลให้ตอบ `422` (Q13)

### 6.2 หน้าเว็บที่ต้องแก้ตาม

| หน้า | เจ้าของ | ต้องแก้ |
|---|---|---|
| `demo/line-sim` | คน 3 | เอาข้อความ "Rejection is not supported" ออก ปุ่ม Reject ใช้งานจริง แสดงผลตาม `case_status` หลายคนเห็น Offer ของเคสเดียวกันพร้อมกัน และ Offer ที่ถูกยกเลิกต้องหายจากรายการ หรือขึ้นข้อความว่าปิดแล้วเมื่อได้ `409` |
| `approvals` | คน 1 | ปุ่ม Reject ตอนนี้แสดง `422` เป็น Error ต้องแสดงผลสำเร็จ และมีช่องกรอก `reason` ถ้า Q13 บังคับ กรณี `case_status = MANUAL_HANDOFF` ต้องมีข้อความของมัน |
| `cases/[id]` | คน 2 | ตารางผู้สมัครจะมี Offer หลายสถานะ (`REJECTED`, `CANCELLED`, `SENT`) มี `SENT` หลายแถวพร้อมกัน และคนเดียวมี Offer ได้มากกว่าหนึ่งแถวถ้าติดต่อซ้ำ (Q22) Timeline ยาวขึ้น ต้องเช็กว่า `MANUAL_HANDOFF` ยัง Poll ต่อตามที่ออกแบบไว้ |
| `roster` | คน 3 | ไม่เปลี่ยน |
| `demo/control` | คน 1 | ไม่เปลี่ยน รอบ 1 ไม่เพิ่มปุ่มโหลด Scenario (Q16) |

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
| `DAILY_HOURS_EXCEEDED` | `maximum_daily_hours` | ทำ | นิยามอยู่ใต้ตาราง (Q14) |
| `WEEKLY_HOURS_EXCEEDED` | `maximum_weekly_hours` | ทำ | นิยามอยู่ใต้ตาราง (Q14) |
| `SOURCE_WARD_MINIMUM_VIOLATION` | `preserve_source_ward_minimum` | ทำ (Unit Test เท่านั้น) | นิยามอยู่ใต้ตาราง (Q15) |
| (ไม่มีรหัส) | `preserve_minimum_staffing` | ไม่เป็น Hard Rule | เป็นธงของการคิด Gap ของเวรที่ขาดคน คน 1 ทำ (ข้อ 8.2 Q18) |

**Q15 ธงสองตัวเรื่องจำนวนคนขั้นต่ำ:** ต่างกันที่ปกป้องจำนวนคนของหอไหน

| ธง | ความหมาย | ใครทำ |
|---|---|---|
| `preserve_minimum_staffing` | ใช้ขั้นต่ำคงที่ `minimum_staff` ร่วมกับขั้นต่ำจากจำนวนผู้ป่วย (`required_staff`) เพื่อกำหนดเป้าหมายของ**เวรที่กำลังขาดคน** ปิดธง = ใช้เฉพาะ `required_staff` | คน 1 ในการคิด Gap (ข้อ 8.2) |
| `preserve_source_ward_minimum` | ห้ามย้ายผู้สมัครมาช่วย ถ้าการย้ายทำให้**หอต้นทาง**เหลือคนต่ำกว่าขั้นต่ำ | คน 2 เป็น Hard Rule `SOURCE_WARD_MINIMUM_VIOLATION` |

ตัวอย่าง: หอ A ขาดคน และต้องการดึงพยาบาลจากหอ B

* `preserve_minimum_staffing` กำหนดว่าหอ A ต้องมีอย่างน้อยกี่คน: `effective_minimum = max(minimum_staff, required_staff)`
* `preserve_source_ward_minimum` ตรวจว่าหอ B ส่งคนออกมาได้ไหม เช่น หอ B มี 5 คน ขั้นต่ำ 5 คน ส่งออกหนึ่งคนเหลือ 4 จึงห้ามเมื่อเปิดธง
* สองธงทำงานแยกกัน: ธงแรกกำหนดเป้าหมายของเวรที่รับคน ธงที่สองกันไม่ให้การแก้ปัญหาสร้างการขาดคนที่ต้นทาง

กติกาของ `SOURCE_WARD_MINIMUM_VIOLATION`

| หัวข้อ | กติกา |
|---|---|
| เวรที่ดู | เวรต้นทางของผู้สมัคร คือเวรที่เขาอยู่และจะถูกย้ายออก (Requirement ผูกกับเวร จึงตรวจที่ระดับเวรของหอต้นทาง) |
| สูตร | `staff_left = จำนวนคนในเวรต้นทาง - 1` ผ่านเมื่อ `staff_left >= เป้าหมายของเวรต้นทาง` |
| เป้าหมายของเวรต้นทาง | `preserve_minimum_staffing` เปิด: `max(minimum_staff, required_staff)` ปิด: `required_staff` อย่างเดียว สูตรเดียวกับการคิด Gap (ข้อ 8.2) |
| เหตุผล | ใช้เป้าหมายตัวเดียวกับการคิด Gap ไม่ใช่ `minimum_staff` อย่างเดียว ไม่งั้นย้ายคนออกแล้วเวรต้นทางกลายเป็นขาดคนตามการคิด Gap "คนพอ" จึงมีความหมายเดียวทั้งระบบ |
| ชื่อรหัส | `SOURCE_WARD_MINIMUM_VIOLATION` บอกชัดว่าเป็นกฎของ `preserve_source_ward_minimum` ไม่สับสนกับ `preserve_minimum_staffing` ที่กำหนดเป้าหมายของเวรที่รับคน |
| ผู้สมัครไม่มีเวรต้นทาง | ผ่าน |
| รอบ 1 | เขียนกฎและ Unit Test ยังไม่มีกรณีไม่ผ่านใน Workflow เพราะรอบ 1 เพิ่มเวรให้คนที่ว่างอยู่เท่านั้น คนที่มีเวรชนเวลาไม่ผ่าน `SHIFT_CONFLICT` ไปก่อน กฎจะมีผลจริงเมื่อมี Swap หรือ Cross-Ward (รอบ 4) ตกลงแล้วว่ารับได้ที่รอบ 1 มีแค่ Unit Test |

**Q14 ชั่วโมงรายวันและรายสัปดาห์:** รอบ 1 ทำทั้งสองข้อ `DAILY_HOURS_EXCEEDED` และ `WEEKLY_HOURS_EXCEEDED`

| หัวข้อ | กติกา |
|---|---|
| ชั่วโมงของเวร | `end_at - start_at` นับทั้งเวร ไม่แบ่งข้ามวัน |
| วัน | วันที่ของ `start_at` ตามเวลา Asia/Bangkok เวรดึก 23:00 ถึง 07:00 นับเป็นของวันที่เริ่ม |
| สัปดาห์ | จันทร์ 00:00 ถึงจันทร์ถัดไป 00:00 ตามเวลา Asia/Bangkok นับตาม `start_at` |
| เวรที่นับ | Roster ของผู้สมัครที่สถานะอยู่ใน `COMMITTED_ROSTER_STATUSES` รวมกับเวรของเคส |
| ไม่ผ่านเมื่อ | ผลรวมมากกว่าค่าใน Policy (เท่ากันถือว่าผ่าน) |
| แหล่งข้อมูล | ชั่วโมงตามตารางเวรจาก Roster ไม่นับ OT และเวลาทำงานจริง (รอ Working Time Snapshot รอบ 3) |
| `validation_snapshot` | เก็บผลรวมที่คำนวณได้และค่าเพดาน เช่น `{"weekly_hours": 56, "weekly_limit": 52}` |

ข้อจำกัดที่รู้

* สัปดาห์ตามปฏิทินไม่กันการขึ้นเวรติดกันข้ามสัปดาห์
* ข้อรายวันยังไม่มีกรณีที่ไม่ผ่านโดยลำพังกับเวร 8 ชั่วโมงในตอนนี้ จึงมีแค่ Unit Test

### 7.3 ต้องตกลง: Interface

* ตัวตรวจเป็น Pure Function ใน `domain/constraints/` (ไฟล์มีชื่อใน `repo-structure.md` แล้ว: `codes.py`, `context.py`, `hard_rules.py`, `evaluator.py`) ไม่อ่าน DB เอง ผู้เรียกโหลดข้อมูลแล้วส่งเข้าไป แบบเดียวกับ `gap_calculator`
* ผลที่คืน: List ของรหัสที่ไม่ผ่าน (ว่าง = ผ่าน) ไม่ใช่ Exception เพราะ Safety ต้องบันทึกครบทุกข้อที่ไม่ผ่าน
* ผู้เรียกสามที่ต้องได้ผลเดียวกันจากข้อมูลเดียวกัน: Solver (คัดคนออก), `contact_candidate` (ข้ามคน ข้อ 3), Safety (บันทึกผล)
* **Q17** `availability_service.assert_available()` คำตอบ: คงไว้เป็นเปลือกห่อตัวตรวจใหม่
  * ชื่อฟังก์ชัน, Argument (`db`, `shift`, `staff_id`) และ Exception เดิม (`StaffNotActiveError`, `StaffAlreadyOnShiftError`, `StaffUnavailableError`) ไม่เปลี่ยน Execute ของคน 3 (`roster_service`) ไม่ต้องแก้โค้ด
  * ข้างใน: โหลดข้อมูล เรียกตัวตรวจใหม่ใน `domain/constraints/` แล้วแปลงรหัสแรกที่ไม่ผ่านเป็น Exception กติกาจึงมีที่เดียว
  * รหัสใหม่ที่ไม่มี Exception เดิม (เช่น `SHIFT_CONFLICT`, `INSUFFICIENT_REST`): โยน `CandidateNotAvailableError` ตัวแม่ คน 3 ตรวจโค้ดแล้วยืนยันว่า Execute รับได้ เพราะไม่ได้จับเฉพาะ Exception สามชนิดเดิม เส้นทางคือ `assert_available()` โยน → `create_replacement()` ปล่อยต่อ → Handler `execute_assignment` ปล่อยต่อ → Orchestrator จับด้วย `except Exception` → Rollback รอบนั้น เคสเป็น `FAILED` ตาม D11
  * Exception เก็บรหัสกฎที่ไม่ผ่านเป็น Attribute (ไม่ใช่แค่ในข้อความ) เพื่อให้ `WORKFLOW_FAILED` ระบุสาเหตุได้ ใช้รหัสชุดเดียวกับตารางข้อ 7.2
  * **Q23** ไม่ผ่านตอน Execute แล้วเคสไปไหน ตอนนี้เป็น `FAILED` การเปลี่ยนชนิด Exception ไม่เปลี่ยนข้อนี้ ถ้าต้องการให้กลับไปหาผู้สมัครใหม่ ต้องเพิ่ม Transition `EXECUTING → OUTREACH` (เส้นที่ 6) และกติกาของ Offer กับ Approval ที่ผ่านไปแล้ว ข้อเสนอ: รอบ 1 คง `FAILED` เพราะ Safety ตรวจกฎชุดเดียวกันไปก่อนหน้าแล้ว กรณีนี้เกิดได้เฉพาะเมื่อสถานการณ์เปลี่ยนระหว่างรออนุมัติ
  * Safety (`safety_service`) เลิกเรียกเปลือกนี้ เปลี่ยนไปเรียกตัวตรวจใหม่ตรง ๆ เพราะต้องได้ List ของรหัสทุกข้อไปบันทึก (ข้อ 7.4) ไม่ใช่ Exception ข้อแรก
  * คน 2 เป็นคนแก้ข้างในเปลือก ใน PR 1a หรือ PR 3 Test เดิมของ `availability_service` ต้องเขียวโดยไม่แก้
* Policy ที่ใช้: `policy_service.get_hard_constraint_policy(db)` ตัวเดิม (ตรึง `id = 1`) ธง Boolean ใน Policy ที่เป็น `false` = ข้ามข้อนั้น

### 7.4 ต้องตกลง: สิ่งที่ Safety บันทึก

| คอลัมน์ | ค่าที่เสนอ |
|---|---|
| `SAFETY_VALIDATION.is_passed` | `false` เมื่อมีรหัสไม่ผ่านอย่างน้อยหนึ่งข้อ |
| `failure_reason` | รหัสที่ไม่ผ่าน คั่นด้วย `,` เรียงตามลำดับในตาราง 7.2 ไม่ใช่ข้อความอิสระ |
| `validation_snapshot` | ข้อมูลที่ใช้ตัดสิน เช่น `{"checked_rules": [...], "failed_rules": [...], "policy_id": 1, "shift_id": 1, "staff_id": 201}` รายละเอียดให้คน 2 เสนอ ข้อชั่วโมงเก็บผลรวมกับเพดานด้วย (ข้อ 7.2 Q14) |
| `hard_constraint_policy_id` | Policy ที่ใช้ตรวจจริง |

กรณีที่ยังเป็น `FAILED` (D11) ไม่ใช่ Safety ไม่ผ่าน: ข้อมูลผิดรูป เช่น `ProposedShiftMismatchError`, Item ไม่ได้อยู่ในเคสนี้, ไม่เจอ Offer `ACCEPTED` หนึ่งแถวพอดี พวกนี้คือระบบผิด ไม่ใช่ผู้สมัครไม่เหมาะ

---

## 8. Coverage (งานของคน 1 ที่ Solver ต้องใช้)

### 8.1 ตอนนี้

* `gap_calculator` คิด `minimum_required_staff = ceil(patient_count / patients_per_nurse)` และ Gap ของ Role / Skill ตาม Requirement
* `STAFFING_GAP` + แถว Role / Skill ถูกบันทึกแล้ว พร้อม Snapshot
* `STAFFING_REQUIREMENTS.required_staff` และ `minimum_staff` **ไม่ถูกใช้** (เอกสารเขียนไว้ชัดว่าไม่ใช้เป็นเป้าหมาย) รอบ 1 เปลี่ยนเป็นใช้ทั้งสองค่าตาม Q18
* Solver ยังไม่อ่าน Gap เลย ผู้สมัครตายตัว 201, 202, 203

### 8.2 ต้องตกลง: "Minimum" คืออะไร

ชื่องานคือ "Role + Skill + Minimum" แต่ตอนนี้มีตัวเลขจำนวนคนสองแหล่ง

**Q18** `required_staff` และ `minimum_staff` ใน Requirement ใช้ทำอะไร คำตอบ

| หัวข้อ | กติกา |
|---|---|
| `required_staff` | จำนวนคนที่ต้องการตามภาระงาน = `ceil(patient_count / patients_per_nurse)` เก็บไว้ใน Requirement และคำนวณใหม่เฉพาะเมื่อ Event ของ Patient Surge เกิน Threshold โดย **UPDATE ในแถว Requirement เดิม** ไม่สร้างแถวใหม่ |
| `minimum_staff` | ค่าคงที่ของแต่ละเวร คือจำนวนคนขั้นต่ำที่เวรต้องมีเสมอ |
| เป้าหมายจำนวนคน | `max(required_staff, minimum_staff)` |
| `headcount_gap` | `max(เป้าหมาย - จำนวนคนในเวร, 0)` |
| `calculate_gap()` | รับ `required_staff` และ `minimum_staff` แทน `patient_count` และ `patients_per_nurse` (แก้ Signature ต้องแจ้งทีมก่อน) |
| สูตร `ceil` | แยกเป็นฟังก์ชันของตัวเอง ใช้ตอนเขียน `required_staff` (ตอนนี้คือ Seed ภายหลังคืองาน Patient Surge) |
| Snapshot ใน `STAFFING_GAP` | เก็บ `effective_minimum` (เป้าหมายที่ใช้คิด) คอลัมน์เดียว `required_staff` และ `minimum_staff` อ่านผ่าน `staffing_requirement_id` ไม่เก็บซ้ำ รายละเอียดอยู่ใต้ Pseudo Code |
| Test | `required_staff` ใน Seed ต้องตรงกับสูตร และเพิ่มกรณีที่ `minimum_staff` มากกว่า `required_staff` |
| แก้เอกสาร | `workflow.md` ข้อ 3 และ Docstring ของ `gap_calculator` ที่บอกว่าไม่ใช้ `required_staff` |
| ยังไม่ตัดสินในรอบ 1 | ค่า Threshold และใครเป็นคนเขียน `required_staff` ตอน Patient Surge |

เขียนเป็น Pseudo Code

```text
if preserve_minimum_staffing:
    effective_minimum = max(minimum_staff, required_staff)
else:
    effective_minimum = required_staff

headcount_gap = max(effective_minimum - current_valid_staff, 0)
```

* `preserve_minimum_staffing` คือธงใน `HARD_CONSTRAINT_POLICY` (Seed ตอนนี้เป็น `true`) ธงนี้เป็น `false` = ไม่ใช้ `minimum_staff` เป็นพื้น
* ธงนี้ใช้ที่การคิด Gap ที่เดียว การกันไม่ให้ต้นทางขาดคนเป็นของอีกธงคือ `preserve_source_ward_minimum` (ข้อ 7.2 Q15) ทั้งสองอย่างทำในรอบ 1
* `current_valid_staff` = จำนวนคนในเวรที่นับตอนนี้ (Roster ที่ `ASSIGNED`) ไม่เปลี่ยนวิธีนับ
* Golden Case ไม่เปลี่ยนผล: เวร 1 มี `required_staff = 5`, `minimum_staff = 4` เป้าหมายยังเป็น 5 และค่า Seed ตรงกับสูตรอยู่แล้ว (ผู้ป่วย 10 คน หาร 2 = 5, เวร 2 ผู้ป่วย 2 คน หาร 2 = 1)

สิ่งที่ตามมาและยังต้องตกลง

* **ข้อมูลไม่ตรงกันได้:** `patient_count` ของเวรเปลี่ยนแต่ยังไม่มีใครเขียน `required_staff` ใหม่ Gap จะคิดจากค่าเก่า รอบ 1 ยอมรับ เพราะงาน Patient Surge ยังไม่มี Test ของ Seed เป็นตัวกันเดียว
* **คอลัมน์ของ `STAFFING_GAP`** ตอบแล้ว

  | คอลัมน์ | เปลี่ยน |
  |---|---|
  | `id` | คงไว้ |
  | `case_id` | คงไว้ |
  | `staffing_requirement_id` | คงไว้ |
  | `headcount_gap` | คงไว้ |
  | `effective_minimum` | เพิ่ม |
  | `computed_at` | คงไว้ |
  | `patient_count` | ลบ |
  | `patients_per_nurse` | ลบ |

  * `effective_minimum` คือค่าที่ส่งเข้าสูตร `headcount_gap` จริง (หลังดูธง `preserve_minimum_staffing` แล้ว) `record_gap()` เขียนค่าที่ใช้คิด ไม่คิดใหม่ตอนบันทึก
  * `patient_count` กับ `patients_per_nurse` ลบ เพราะไม่ใช่ Input ของ Gap แล้ว เป็นข้อมูลของขั้นที่เขียน `required_staff` ลบ CHECK `ck_staffing_gap_patients_per_nurse_valid` ไปด้วย
  * **ผลที่ตามมา:** `required_staff` ถูก UPDATE ในแถวเดิม ค่าที่อ่านผ่าน `staffing_requirement_id` จึงเป็นค่าปัจจุบัน ไม่ใช่ค่าตอนคิด Gap ค่าเดียวในแถว Gap ที่บอกเป้าหมายตอนคิดคือ `effective_minimum` ห้ามเอา `required_staff` / `minimum_staff` ของ Requirement มาแสดงคู่กับ Gap เก่าว่าเป็นค่าที่ใช้คิด (Q20)
  * ต้องตกลง: แถว `STAFFING_GAP` เก่าตอน Migration ข้อเสนอ: ทำแบบ Migration `c4d7e19a52f3` คือปฏิเสธถ้าตารางมีแถว ให้ `make reset` ไม่เติมค่าย้อนหลัง ต้องแจ้งทีมว่าหลัง merge ทุกคนต้อง Reset
  * ไฟล์ที่แก้: Migration ใหม่, Model `StaffingGap`, `gap_service` (`assess_shift()`, `record_gap()`), `docs/database-schema.md`, Test ที่ตรวจสองคอลัมน์เดิม
* `gap_service.assess_shift()` ต้องโหลด Requirement มาใช้กับ Headcount ด้วย (ตอนนี้ใช้แค่ Role / Skill) และต้องอ่านธง `preserve_minimum_staffing` จาก Policy

### 8.3 ต้องตกลง: Seam ใหม่ "Gap → Solver"

Solver ต้องรู้ว่าต้องหาคนแบบไหน ข้อเสนอ

| หัวข้อ | กติกา |
|---|---|
| แถวที่อ่าน | `STAFFING_GAP` ของเคส ที่ `id` มากสุด ไม่เจอ → Error (เคสผ่าน `ASSESSING` มาแล้วต้องมี) |
| Role ที่ต้องการ | แถว `STAFFING_GAP_ROLE` ที่ `gap_count > 0` |
| Skill ที่ต้องการ | แถว `STAFFING_GAP_SKILL` ที่ `gap_count > 0` |
| ผู้สมัครที่ผ่าน | มี Role ที่ต้องการ และมี Skill ที่ต้องการ**ครบทุกตัว** (ถ้าเคสรับคนเดียวตาม Q21 = ก คนนั้นต้องปิดได้ทุก Gap ถ้าเคสรับหลายคน ต้องเขียนกติกานี้ใหม่) |
| ไม่มี Role / Skill Gap เลย (ขาดแค่จำนวนคน) | ผู้สมัคร Role ไหนก็ได้ที่ Requirement ของเวรมี |
| ใครโหลด | ฟังก์ชันเดียวใน `gap_service` ให้ Solver และ Safety เรียก ไม่เขียน Query เอง |

ตัวอย่างที่ใช้ทดสอบได้กับ Seed ปัจจุบัน: 101 (มี Skill ICU) ลาเวร 1 → ICU เหลือ 1 จากที่ต้องการ 2 → ผู้สมัครต้องมี ICU → 201 และ 203 ผ่าน, 202 ไม่ผ่าน (`SKILL_MISMATCH`)

### 8.4 คำถามอื่นของ Coverage

* **Q11** Gap มากกว่า 1 (เช่น 104 กับ 105 ลาเวรเดียวกัน ตอนนี้ได้สองเคสแยกกัน) และการส่ง Offer รอบ 1 จะส่งทีละคนหรือส่งเป็น Wave
  * หนึ่ง Wave = ส่ง Offer ให้ผู้สมัครหลายคนพร้อมกันตามลำดับ `rank` ทุกแถวเป็น `SENT`
  * ขนาด Wave: เสนอ `headcount_gap` + สำรอง n คน (โดย n = ceil(0.1 * headcount_gap) )
  * รับคนตามลำดับที่ตอบ `ACCEPT` จนครบจำนวนที่ขาด Offer ที่ยัง `SENT` อยู่ตอนครบแล้วเป็น `CANCELLED`
  * ทั้ง Wave Reject หรือไม่ผ่าน Safety จนไม่ครบ → ส่ง Wave ถัดไปจากคนที่เหลือใน Plan ไม่เหลือใคร → `MANUAL_HANDOFF` (T4)
  * การรวมสองเคสของเวรเดียวกันเป็นเคสเดียวยังเป็นงาน Aggregation รอบ 4 รอบ 1 แต่ละเคสส่ง Wave ของตัวเอง
* **Q19** ตรวจ Coverage ซ้ำก่อน `RESOLVED` ไหม คำตอบ: ไม่ตรวจ หลังสร้าง Roster ของคนมาแทน ถ้าเวรยังขาด (เพราะมีคนลาเพิ่มระหว่างทาง) เคสนี้ยัง `RESOLVED` ได้ เพราะเคสนี้ปิดการขาดของ Event ตัวเองแล้ว การขาดใหม่มีเคสของมันเอง
* **Q20** `GET /cases/{id}` คืนค่าที่ใช้คำนวณ Gap ด้วยไหม คำตอบ: เพิ่ม ตอนนี้หน้าเว็บแสดงแค่ "Short by 1" โดยไม่บอกว่าจากกี่คน
  * ค่าที่คืน: `effective_minimum` และ `headcount_gap` จากแถว Gap เท่านั้น สองค่านี้จดไว้ตอนคิด จึงถูกเสมอ ชื่อ Field ตกลงตอนทำ PR
  * ไม่คืน `required_staff` กับ `minimum_staff` เพราะ Requirement ถูก UPDATE ในแถวเดิม ค่าที่อ่านได้อาจไม่ใช่ค่าตอนคิด (ข้อ 8.2)
  * `patient_count` กับ `patients_per_nurse` ไม่คืน เพราะคอลัมน์ถูกลบจาก `STAFFING_GAP` แล้ว (ข้อ 8.2)
  * จำนวนคนในเวรตอนคิดไม่มีคอลัมน์เก็บ (ไม่อยู่ในรายการคอลัมน์ที่ตกลง) ถ้าหน้าเว็บจะแสดง ให้คิดจาก `effective_minimum - headcount_gap` ซึ่งถูกเฉพาะเมื่อเวรขาดคน เคสเปิดเฉพาะเมื่อมี Gap จึงใช้ได้กับทุกเคส
  * เพิ่ม Field ใน Response = แก้ Type ฝั่ง Frontend และหน้า `cases/[id]` ของคน 2

---

## 9. Seed Scenario และ Test

### 9.1 Scenario ที่ต้องมี

ตอนนี้มีแค่ `seed/scenarios/golden_case.py` ชื่อไฟล์อื่นอยู่ใน `repo-structure.md` แล้ว

| ไฟล์ | เจ้าของ | สถานการณ์ | ข้อมูลที่ต้องเพิ่มจาก Golden Case |
|---|---|---|---|
| `candidate_reject.py` | คน 3 | 201 ปฏิเสธ, 202 รับใน Wave เดียวกัน (กรณี ก) และทุกคนปฏิเสธจนต้องส่ง Wave 2 (กรณี ง) | ไม่ต้องเพิ่ม ใช้ Golden Case ได้ |
| `head_nurse_reject.py` | คน 3 | 900 ไม่อนุมัติ 201 (กรณี ค) | ไม่ต้องเพิ่ม |
| `safety_failure.py` | คน 2 | 201 รับแล้ว Safety ไม่ผ่าน (กรณี ข) | ต้องทำให้ 201 ผิด Rule **หลัง** ได้ Offer เช่น เพิ่ม Roster เวรอื่นที่ชนเวลา ระหว่างรอคำตอบ |
| `no_feasible_solution.py` | คน 2 | ไม่มีผู้สมัครผ่าน Hard Rules เลย (กรณี จ) | ทำให้ 201, 202, 203 ไม่ผ่านทั้งหมด |
| (ใหม่) Skill Gap | คน 1 + คน 2 | 101 ลา ต้องได้คนที่มี ICU (ข้อ 8.3) | ไม่ต้องเพิ่ม |

**Q16** Scenario โหลดยังไง คำตอบ: รอบ 1 ใช้ใน Test เท่านั้น แต่ทุกไฟล์เขียน Interface เดียวกัน เพื่อให้เพิ่มปุ่มโหลดทีหลังได้โดยไม่ต้องรื้อ

| หัวข้อ | กติกา |
|---|---|
| `POST /demo/reset` | ไม่เปลี่ยน ไม่รับ Parameter โหลด Golden Case อย่างเดียว |
| หน้า `demo/control` | ไม่เปลี่ยน ไม่มีปุ่มเลือก Scenario ในรอบ 1 |
| Interface ของไฟล์ Scenario | ทุกไฟล์ใน `seed/scenarios/` มี `seed(db: Session) -> None` แบบเดียวกับ `golden_case.seed()` ที่มีอยู่ ไม่ Commit ผู้เรียกเป็นเจ้าของ Transaction |
| ข้อมูลตั้งต้น | Scenario เรียกต่อจาก `base_data.seed(db)` และ `golden_case.seed(db)` เพิ่มเฉพาะแถวที่ต่างจาก Golden Case ไม่ก๊อปข้อมูล Golden Case ไปเขียนซ้ำ |
| ID ที่ใส่เอง | ถ้าไฟล์ไหนใส่ `id` เอง ต้องเลื่อน Sequence ของตารางนั้นตาม แบบที่ Seed เดิมทำ |
| เหตุการณ์กลางทาง | สิ่งที่ต้องเกิดหลังเคสเริ่มเดิน (เช่น 201 ได้เวรชนเวลาหลังได้ Offer ใน `safety_failure`) ไม่อยู่ใน `seed()` ให้แยกเป็นฟังก์ชันของตัวเองในไฟล์เดียวกัน Test เรียกตอนที่ต้องการ |
| ใครเรียก | Fixture ของ Test เท่านั้น |

* เหตุผล: กรณี Reject กับไม่อนุมัติกด Demo ได้จาก Golden Case อยู่แล้วโดยไม่ต้องโหลด Scenario ส่วนกรณี Safety ไม่ผ่านต้องมี Route เพิ่มสำหรับเหตุการณ์กลางทาง ซึ่งไม่อยู่ในขอบเขตรอบ 1
* ไม่ทำในรอบ 1: `POST /demo/reset?scenario=`, ทะเบียนชื่อ Scenario, ปุ่มเลือกในหน้า `demo/control`, ปุ่มรายงานลาที่เปลี่ยนตาม Scenario

### 9.2 กติกาของ Test

* ทุกกรณีใน 5.3 มี Integration Test ที่ตรวจลำดับ Audit ตรงตามนั้น และตรวจสถานะสุดท้ายของเคส
* กรณีที่จบ `RESOLVED` ตรวจ Roster ด้วย: คนที่ได้ `REPLACEMENT` ต้องเป็นคนที่ได้รับอนุมัติ ไม่ใช่คนที่ถูกปัดตก
* `test_transitions.py`: ตาราง Transition ที่ยอมรับต้องเพิ่ม 5 เส้นใหม่ (ไฟล์ของคน 1) ตอนนี้ Test ยอมรับเฉพาะเส้น Golden Path กับ `→ FAILED` เส้นใหม่จะแดงจนกว่าจะแก้ Test พร้อมกัน
* `tests/e2e/test_workforce_recovery.py` ต้องเขียวตลอด แต่ลำดับ Golden Path เปลี่ยนเพราะ Wave (ข้อ 5.3) แก้ E2E พร้อม `GOLDEN_PATH_AUDIT_ACTIONS` ใน PR 2b ไม่แยก PR
* Test ที่สมมติว่ามี Offer `SENT` แถวเดียว หรือว่า 202 ไม่มี Offer ตอน 201 ยังไม่ตอบ ต้องแก้ใน PR 2b
* Wave ต้องมี Test สอง Connection: สองคนใน Wave เดียวกัน `ACCEPT` พร้อมกัน ต้องได้ `ACCEPTED` หนึ่งแถวกับ `409` หนึ่งครั้ง ไม่ค้าง
* Fixture `stub_handlers` ใน `tests/integration/conftest.py`: ถ้า Handler ตัวไหนมีทางออกเพิ่ม (เช่น `OUTREACH → MANUAL_HANDOFF`) Stub ยังคืนเส้น Golden Path เหมือนเดิม ไม่ต้องแก้
* Test ที่ตอนนี้คาดหวัง `422` ของ `REJECT` และไม่อนุมัติ และ Test ที่คาด `FAILED` จาก `NoCandidatesError` / Safety ไม่ผ่าน ต้องเปลี่ยนใน PR ของเจ้าของเส้นทางนั้น

---

## 10. ลำดับ PR

Branch Protection เปิดแล้ว ทุก PR ต้องมี `staging` ล่าสุดและ CI เขียว

| ลำดับ | PR | ใครทำ | มีอะไร | ต้องเข้าก่อน |
|---|---|---|---|---|
| 0 | Contract | คน 1 | `workflow.md` (ข้อ 5, 6.4, 7, 8, 9), `transitions.py` + `test_transitions.py` 5 เส้นใหม่, Test ของ Orchestrator สำหรับ `MANUAL_HANDOFF` ที่มาจาก Handler **ไม่มีการเปลี่ยนพฤติกรรม** เพราะยังไม่มี Handler ตัวไหนคืนเส้นใหม่ | ทุกตัวข้างล่าง |
| 1a | Hard Rules: ตัวตรวจ + รหัส | คน 2 | `domain/constraints/` + Unit Test ยังไม่ต่อกับ Workflow | 2a, 2b, 3 |
| 1b | Seam Gap → Solver + เป้าหมายจำนวนคนตาม Q18 | คน 1 | ฟังก์ชันใน `gap_service` + Test, `calculate_gap()` Signature ใหม่, ฟังก์ชันสูตร `ceil`, Migration ของ `STAFFING_GAP` (เพิ่ม `effective_minimum`, ลบ `patient_count` กับ `patients_per_nurse`), Test ของ Seed | 2a |
| 1c | ย้ายกฎข้อ 4 (Offer ค้าง) เป็นของกลาง | ตาม Q4 | Refactor ไม่เปลี่ยนพฤติกรรม | 2b |
| M | Merge Gap (`T6`, `T7`) | คน 1 | สถานะ `WAITING_MERGE_WINDOW`, คอลัมน์ `merge_window_closes_at` + Migration, การรับ Event ใช้เคสเดิม, ฟังก์ชันปิด Window, Route เลื่อน Clock + ปุ่มใน `demo/control`, ค่าตั้งความยาว Window (Test เดิมใช้ 0) | หลัง PR 0 ลำดับเทียบกับ 2b ต้องตกลง เพราะทั้งคู่เปลี่ยนเส้นทางของเคส |
| 2a | Solver ใช้ Hard Rules + Gap, `T5` | คน 2 | `optimize`, `optimization_service`, Scenario `no_feasible_solution` | |
| 2b | Wave + Reject (`T1`, `T4`) | คน 3 | `contact_candidate`, `outreach_service` (ส่งหลายคน, ยกเลิก Offer ที่เหลือ, ล็อกทุกแถวของเคส), หน้า `line-sim`, Scenario `candidate_reject`, `GOLDEN_PATH_AUDIT_ACTIONS` + E2E | |
| 3 | Safety บันทึกผลไม่ผ่าน (`T2`) | คน 2 | `validate_safety`, `safety_service`, Scenario `safety_failure` | หลัง 2b (ต้องมีกติกา Wave ถัดไป) |
| 4 | ไม่อนุมัติ (`T3`) | คน 3 | `approval_service`, Scenario `head_nurse_reject` | หลัง 2b |
| 5 | หน้า `approvals` | คน 1 | Reject ใช้งานจริง + `reason` | หลัง 4 |
| 6 | หน้า `cases/[id]` | คน 2 | เช็กการแสดงผลของสถานะและ Offer ใหม่ | หลัง 2b, 3, 4 |

ข้อที่เสี่ยงพังเงียบ (เคยเจอในขั้นที่ 4)

* PR 3 กับ PR 4 แก้เส้นทางที่มาบรรจบกันที่ `OUTREACH` ทั้งคู่ต้องมี Test ที่รันกับ `contact_candidate` ตัวจริงของ 2b ไม่ใช่ Stub
* PR 2a เปลี่ยนว่าใครอยู่ใน Plan Test ของคน 3 ที่สมมติว่ามี 201, 202, 203 ครบอาจแดงหลังรวม ให้ Test อ่านจำนวนผู้สมัครจาก Plan จริง
* PR 2b เปลี่ยน Golden Path (มี `OFFER_SENT` สองแถว และ 202 มี Offer) Test ของคนอื่นที่ตรวจลำดับ Audit ทั้งเส้นหรือสมมติว่า 202 ว่าง จะแดงหลังรวม PR 2b ใหญ่กว่าเดิมมาก ควรเข้าเร็วและแจ้งทีมก่อน merge
* ทุก PR จะชนกันที่ `workflow.md` ข้อ 13 เหมือนเดิม เก็บทุกแถว

---

## 11. ผลต่อเอกสารและไฟล์กลาง

| ไฟล์ | ต้องแก้ | ใคร |
|---|---|---|
| `docs/workflow.md` ข้อ 4 | `MANUAL_HANDOFF` เปลี่ยนจาก "ภายหลัง" เป็นใช้แล้ว (เฉพาะการหยุด) | PR 0 |
| ข้อ 5 | เพิ่มหัวข้อย่อยของ 5 เส้นใหม่ | PR 0 |
| ข้อ 6.4 | Seam 2 ใหม่เป็นการส่ง Wave (ข้อ 3), Seam 3 ล็อก Offer `SENT` ทุกแถวของเคสและยกเลิกแถวที่เหลือ (ข้อ 4.3), Seam 4 เพิ่มกติกา `CANCELLED` (ข้อ 4.1), Seam ใหม่ Gap → Solver (ข้อ 8.3), กติกา Lock (ข้อ 4.3) | PR 0 |
| ข้อ 7 | เพิ่มตาราง Audit ของเส้นใหม่ และลำดับของแต่ละกรณี (ข้อ 5) | PR 0 |
| ข้อ 8 | เปลี่ยนชื่อจาก "Stub ของแต่ละขั้น" และอัปเดตแถว Solver, Outreach, Response, Safety, Approval | เจ้าของแต่ละแถว ใน PR ของตัวเอง |
| ข้อ 9.2, 9.3 | ลบส่วน `422`, เพิ่มค่าใหม่ของคำตอบ (ข้อ 6.1) | PR 0 |
| ข้อ 12 | ย้ายเรื่องที่ทำแล้วออก | PR สุดท้ายของรอบ |
| `domain/workflow/transitions.py` | 5 เส้นใหม่ | PR 0 |
| `docs/workflow.md` ข้อ 3 และข้อ 8 แถว Gap | เป้าหมายจำนวนคน = `max(required_staff, minimum_staff)` แทนสูตรจาก `patient_count` (ข้อ 8.2) | PR 0 |
| `gap_calculator` (Signature + Docstring), Migration ของ `STAFFING_GAP`, `docs/database-schema.md` | รับ `required_staff` / `minimum_staff`, เพิ่ม `effective_minimum`, ลบ `patient_count` และ `patients_per_nurse` | PR 1b แจ้งทีมก่อน และแจ้งให้ Reset หลัง merge |
| `domain/enums.py` | ไม่ต้องเพิ่มค่า ถ้าตอบ Q10 ว่าไม่เพิ่ม Action แต่ `GOLDEN_PATH_AUDIT_ACTIONS` ต้องเพิ่ม `OFFER_SENT` อีกหนึ่งแถว | PR 2b |
| `domain/enums.py`, `transitions.py`, Migration ของ `STAFFING_CASES` | `CaseStatus.WAITING_MERGE_WINDOW` (เพิ่มใน `WAITING_CASE_STATUSES`), เส้น T6 ถึง T8, คอลัมน์ `merge_window_closes_at` | PR 0 สำหรับ Enum กับ Transition, PR M สำหรับ Migration |
| `docs/workflow.md` ข้อ 12 แถว "การใช้ `PENDING_APPROVAL` ใน Roster" | เอาคำว่า Wave ออกจากเงื่อนไข เพราะ Wave ใช้แล้ว | PR 0 |
| `docs/walking-skeleton.md` | ตาราง "หลัง Skeleton" ใส่สถานะของรอบ 1 | PR สุดท้ายของรอบ |

---

## 12. รายการคำถามสำหรับที่ประชุม

เรียงตามที่ขวางงานมากสุด คำตอบของ Q1 ถึง Q11 และ Q21, Q22 ต้องได้ก่อนเปิด PR 0

| # | คำถาม | ข้อเสนอ | ขวางใคร |
|---|---|---|---|
| Q1 | ไม่อนุมัติแล้วไปไหน | ไปคนถัดไป (`OUTREACH`) | 3, 1 |
| Q2 | ไม่เหลือผู้สมัครเป็นสถานะอะไร | `MANUAL_HANDOFF` | 2, 3 |
| Q3 | ส่ง Wave ถัดไปด้วย Plan เดิมหรือรัน Solver ใหม่ | Plan เดิม + ตรวจความพร้อมซ้ำ | 2, 3 |
| Q4 | กฎ "มี Offer ค้าง" ย้ายไปอยู่ไฟล์ไหน ใครย้าย | อยู่กับตัวตรวจกลางของคน 2 คน 2 ย้าย | 2, 3 |
| Q5 | คนที่ถูกข้ามตอนเลือกคนของ Wave บันทึกยังไง | `skipped` ใน `OFFER_SENT` แถวแรกของ Wave เมื่อส่งได้ หรือใน `MANUAL_HANDOFF` เมื่อไม่เหลือใคร | 3 |
| Q6 | `GET /cases/{id}` ต้องบอกเหตุผลที่ผู้สมัครถูกข้ามไหม | ยังไม่ต้อง ดูจาก Timeline | 1, 2 |
| Q7 | Offer ของคนที่ถูกปัดตกหลังตอบรับ ตั้งเป็น `CANCELLED` ใช่ไหม | ใช่ | 2, 3 |
| Q8 | ใครเป็นคนตั้ง `CANCELLED` | ฟังก์ชันเดียวใน `outreach_service` ให้ Safety และ Approval เรียก | 2, 3 |
| Q9 | ยอมรับกติกา "แถว `ACCEPTED` แก้ได้ภายใต้ Lock ของเคส" ไหม | ยอมรับ และเขียนลงข้อ 6.2 | ทุกคน |
| Q10 | เพิ่ม Audit Action สำหรับ `CANCELLED` ไหม | ไม่เพิ่ม ใช้ `cancelled_outreach_ids` ใน `OFFER_ACCEPTED` สำหรับ Offer ที่ยกเลิกเพราะ Wave ครบ | 3 |
| Q11 | ส่ง Offer ทีละคนหรือเป็น Wave ขนาดเท่าไหร่ | Wave ขนาด `headcount_gap` + `ceil(0.1 * headcount_gap)` (ข้อ 8.4) | ทุกคน |
| Q12 | Solver ไม่ได้ใครเลย เขียน `SOLVER_EXECUTED` และแถว Plan (`INFEASIBLE`) ก่อน `MANUAL_HANDOFF` ไหม | เขียน เพื่อให้ Timeline บอกว่า Solver รันแล้ว | 2 |
| Q13 | `reason` ตอนไม่อนุมัติบังคับไหม | บังคับ ไม่ว่าง | 3, 1 |
| Q14 | รอบ 1 ทำ Rule ชั่วโมงรายวันและรายสัปดาห์ไหม นิยามวันกับสัปดาห์ยังไง | ทำทั้งสองข้อ วัน = วันที่ของ `start_at`, สัปดาห์ = จันทร์ถึงจันทร์ ตามเวลา Asia/Bangkok (ข้อ 7.2) | 2 |
| Q15 | `preserve_minimum_staffing` กับ `preserve_source_ward_minimum` ต่างกันยังไง ใครตรวจ | ตอบแล้ว: ธงแรกกำหนดเป้าหมายของเวรที่ขาดคน (คน 1) ธงที่สองเป็น Hard Rule `SOURCE_WARD_MINIMUM_VIOLATION` ของเวรต้นทาง เทียบกับเป้าหมายสูตรเดียวกับการคิด Gap (คน 2, ข้อ 7.2) | 1, 2 |
| Q16 | Scenario โหลดผ่าน Test อย่างเดียว หรือมีปุ่มในหน้า Demo | Test อย่างเดียว แต่ทุกไฟล์มี `seed(db)` แบบเดียวกัน เผื่อเพิ่มปุ่มทีหลัง (ข้อ 9.1) | ทุกคน |
| Q17 | `assert_available()` คงไว้เป็นเปลือก หรือให้ Execute เปลี่ยนไปเรียกตัวใหม่ | คงไว้เป็นเปลือก ชื่อและ Exception เดิม Execute ไม่ต้องแก้ (คน 3 ยืนยันแล้ว) Exception เก็บรหัสกฎ Safety เปลี่ยนไปเรียกตัวตรวจใหม่ (ข้อ 7.3) | 2, 3 |
| Q18 | `required_staff` และ `minimum_staff` ใช้ทำอะไร | เป้าหมาย = `max(required_staff, minimum_staff)` โดย `required_staff` เก็บใน Requirement ตามสูตร `ceil` (ข้อ 8.2) | 1, 2 |
| Q19 | ตรวจ Coverage ซ้ำก่อน `RESOLVED` ไหม | ตอบแล้ว: ไม่ตรวจ (ข้อ 8.4) | 1 |
| Q20 | `GET /cases/{id}` คืนค่าที่ใช้คำนวณ Gap เพิ่มไหม | ตอบแล้ว: เพิ่ม `effective_minimum` คู่กับ `headcount_gap` ไม่คืน `required_staff` / `minimum_staff` (ข้อ 8.4) | 1, 2 |
| Q21 | เคสหนึ่งรับคนมาแทนกี่คน | แทนด้วย Q24 เพราะ Merge Gap ทำให้เคสขาดได้มากกว่า 1 คน | ทุกคน |
| Q22 | คนที่ Offer ถูกยกเลิกตอนยังไม่ตอบ ติดต่อซ้ำใน Wave ถัดไปได้ไหม | ได้ แยกด้วย `response_at` (ข้อ 3.4) | 3, 2 |
| Q23 | ไม่ผ่าน Hard Rules ตอน Execute แล้วเคสไปไหน | คง `FAILED` ในรอบ 1 ไม่เพิ่ม Transition (ข้อ 7.3) | 2, 3 |
| Q24 | เคสที่ขาดมากกว่า 1 คน เดินทีละคนหรือขนาน | ตอบแล้ว: ขนาน มีคำถามย่อย 6 ข้อ (ข้อ 2.5) | ทุกคน |
| Q25 | ผู้ใช้เลือกจำนวน Offer ที่ส่ง: ใครเลือก ที่ไหน ค่าเริ่มต้น และแทนสูตรของ Q11 ไหม | ยังไม่มีข้อเสนอ ต้องได้คำตอบ 4 ข้อ (ข้อ 2.5) | 3, 1 |
| Q26 | Event ใหม่หลัง Window ปิด เคสรับ Gap ใหม่ยังไง | เพิ่ม Gap แถวใหม่ ไม่เปลี่ยนสถานะ เคสอ่านแถวล่าสุดเอง (ข้อ 2.5) | 1, 3 |

---

## 13. สิ่งที่ฉันยังไม่ได้ตรวจ

* ยังไม่ได้ไล่ Test ทั้งหมดว่าตัวไหนจะแดงเมื่อเปลี่ยนคำตอบ `422` และ `FAILED` รายการในข้อ 9.2 มาจากการอ่านโค้ดของ Service ไม่ได้รัน
* ข้อ 4.3 เรื่อง Lock เป็นการวิเคราะห์จากโค้ดปัจจุบัน ยังไม่มี Test พิสูจน์ ต้องมี Test สอง Connection แบบที่ทำกับ Orchestrator และ Solver
* ส่วนของ Wave แก้ตามหลัง Q11 ยังไม่ได้ไล่โค้ดของ Seam 3 (`record_response`) และ `send_offer` ว่าต้องแก้กี่จุด และยังไม่ได้นับ Test ที่จะแดงเมื่อ Golden Path มี `OFFER_SENT` สองแถว
* ข้อ 2.5 Merge Gap เขียนจากแผนภาพและคำตอบในแชท ยังไม่ได้ไล่โค้ดการรับ Event ว่าการหา "เคสเปิดของเวรนี้" ต้องล็อกอะไรเพิ่ม และยังไม่ได้นับ Test ที่ผ่านเส้น `OPEN → ASSESSING` ซึ่งจะเปลี่ยนเป็นผ่านจุดรอใหม่
* ข้อความใน Q21 ว่า `headcount_gap` คิดจากทั้งเวร มาจากการอ่าน `workflow.md` ข้อ 8 แถว Gap ยังไม่ได้รันสองเคสในเวรเดียวกันเพื่อดูค่าจริง
* ตาราง Hard Rules ข้อ 7.2 เดาจากชื่อคอลัมน์ของ `HARD_CONSTRAINT_POLICY` ความหมายจริงของแต่ละคอลัมน์ต้องให้คน 2 ยืนยัน
