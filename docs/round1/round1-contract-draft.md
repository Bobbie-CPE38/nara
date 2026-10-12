# ร่าง Contract รอบ 1 หลัง Skeleton

> Contract รอบ 1 คำถาม Q1 ถึง Q56 ตอบครบแล้ว ทีมรีวิวผ่านแล้ว (PR #32)
> PR 0 ย้ายกติกาของข้อ 2, 3, 4, 5, 6.1 และ 8.2 เข้า `docs/workflow.md` แล้ว (ข้อ 3, 4, 5, 6, 7 และ 9 ของไฟล์นั้น โดยข้อ 8.2 อยู่ที่ข้อ 3.6) ถ้าสองไฟล์ไม่ตรงกันในเรื่องพวกนั้น ให้ยึด `docs/workflow.md`
> เรื่องที่ยังอยู่ที่ไฟล์นี้ที่เดียว: หน้าเว็บที่ต้องแก้ตาม (ข้อ 6.2), Hard Rules (ข้อ 7), Seam จาก Gap ไป Solver กับสูตรจัดอันดับและ Target ของ Wave (ข้อ 8.3, 8.4), Scenario และ Test (ข้อ 9), ลำดับ PR (ข้อ 10), ไฟล์กลาง (ข้อ 11), คำถามและคำตอบ (ข้อ 12)
> เลขข้อในไฟล์นี้ไม่ถูกเปลี่ยน ข้อความที่อ้าง "ข้อ 2.5" หรือ "ข้อ 4.3" จึงยังชี้ที่เดิม

---

## 0. สรุปสั้น

รอบ 1 เปลี่ยนจาก "เคสหนึ่งรับคนมาแทนหนึ่งคน" เป็น "เคสหนึ่งทำให้ Gap ของเวรหมด" และเปิดเส้นทางที่ Skeleton ปิดไว้

| คน | งานหลัก | ตอนนี้ Skeleton ทำอะไร |
|---|---|---|
| 1 | Merge Gap (Window, Threshold, Event สี่ชนิด, Job), Coverage (`effective_minimum`), สถานะเคสคำนวณจาก Gap ที่เหลือ | หนึ่ง Event เปิดหนึ่งเคสทันที รับแค่ `STAFF_UNAVAILABLE` สถานะเคสเดินตามผู้สมัครคนเดียว |
| 2 | Hard Rules ของจริง, Solver อ่าน Gap เลือกกลุ่มด้วยน้ำหนัก และเรียง `rank` ด้วย `ranking_key`, กติกาเติม Target ของ Wave, Safety ตรวจรายคน | มีแค่ 3 ข้อใน `availability_service` Solver คืนผู้สมัครตายตัว Safety ไม่ผ่านคือ `FAILED` |
| 3 | ส่ง Offer เป็น Wave, Reject, ผู้สมัครถือหลาย Offer, อนุมัติและจัดเวรรายคน | ส่ง Offer ให้อันดับ 1 คนเดียว `REJECT` และไม่อนุมัติตอบ `422` |

การแบ่งงานในตารางนี้และเจ้าของ PR ในข้อ 10 กำหนดแล้ว

ของกลางที่ตกลงในร่างนี้

1. Transition (ข้อ 2.1) และ Merge Gap (ข้อ 2.5)
2. สถานะสองระดับและผู้สมัครถือหลาย Offer (ข้อ 2.6)
3. กติกาเลือกผู้สมัครของ Wave (ข้อ 3)
4. แถวที่แต่ละเส้นทางเขียน และลำดับ Lock (ข้อ 4)
5. Audit (ข้อ 5) และ API กับหน้าเว็บ (ข้อ 6)
6. Hard Rules (ข้อ 7) และ Coverage, Solver, Target ของ Wave (ข้อ 8)
7. Scenario, Test และลำดับ PR (ข้อ 9, 10)

สถานะของคำถามทุกข้ออยู่ข้อ 12

---

## 1. ขอบเขต

### 1.1 อยู่ในรอบ 1

* Merge Gap: Event ของเวรเดียวกันรอรวมใน Window หนึ่ง Window เปิดได้หนึ่งเคส Window ถัดไปของเวรรอจนเคสก่อนหน้าจบ (ข้อ 2.5)
* รับ Event ครบสี่ชนิด: `STAFF_UNAVAILABLE`, `ASSIGNMENT_CANCELLED`, `PATIENT_SURGE`, `REQUIREMENT_CHANGED` ทุกชนิดผ่านการตรวจ Threshold (ข้อ 2.5)
* Job ที่ปิด Window เองตามเวลา เป็น Service แยก (ข้อ 2.5)
* เป้าหมายของเคสคือทำให้ Gap หมด ทั้งจำนวนคน, Role และ Skill ปิดด้วยหลายคนได้ (ข้อ 2.6, 8.3)
* ส่ง Offer เป็น Wave ขนาดตาม Target ของ Gap แต่ละแบบ (ข้อ 3, 8.3)
* ผู้สมัครตอบ `REJECT` ได้ และผู้สมัครคนเดียวถือ Offer จากหลายเคสพร้อมกันได้ จำกัดด้วย `OUTREACH_POLICY` (ข้อ 2.6 ค)
* Safety ตรวจรายคนทันทีที่ตอบรับ ไม่ผ่าน = คนนั้นหลุด เคสเดินต่อ
* อนุมัติรายคน ไม่อนุมัติ = คนนั้นหลุด อนุมัติแล้วจัดเวรทันที ไม่ตรวจซ้ำ
* ไม่เหลือผู้สมัคร → เคสหยุดที่ `MANUAL_HANDOFF`
* Hard Rules ชุดแรก ใช้ทั้งตอน Solver คัดคน ตอนเลือกคนของ Wave และตอน Safety
* Solver อ่าน Gap เลือกกลุ่มด้วยน้ำหนักจาก `SOFT_CONSTRAINT_POLICY` และเรียง `rank` ด้วย `ranking_key` (ข้อ 8.3)
* ใช้ `STAFF_WORKING_TIME_SNAPSHOT` ในรอบ 1 (Q54)
* Timeout ของ Offer ดึงมาจากรอบ 2 (ข้อ 2.7, Q56) การอนุมัติไม่มี Timeout

### 1.2 ไม่อยู่ในรอบ 1 (เขียนไว้กันหลุดขอบเขต)

| เรื่อง | อยู่รอบไหน | ผลต่อรอบ 1 |
|---|---|---|
| Timeout ของผู้อนุมัติ | 4 | การอนุมัติไม่มี Timeout หรือ Deadline เคสที่รออนุมัติรอได้ไม่จำกัดเวลา ส่วน Timeout ของ Offer ดึงมารอบ 1 แล้ว (ข้อ 2.7) |
| OR-Tools | 2, 3 | รอบ 1 เลือกกลุ่มด้วยน้ำหนักจาก `SOFT_CONSTRAINT_POLICY` และเรียง `rank` ด้วย `ranking_key` แล้ว (Q47) แต่ยังไม่ใช้ OR-Tools |
| การจัดการเคสหลัง `MANUAL_HANDOFF`, Escalation | 3 | รอบ 1 แค่หยุดที่สถานะนี้พร้อมเหตุผล |
| `NO_SHOW` (อนุมัติและจัดเวรแล้วแต่ไม่มา) | 5 | รอบ 1 ไม่ตรวจซ้ำตอนจัดเวร (Q38) |
| Re-optimize กลางเคส | ยังไม่กำหนด | Solver รันครั้งเดียวตอนเคสเกิด (Q37) |
| Cross-Ward (ยืมคนข้ามหอ) | 4 | ผู้สมัครยังมาจากหอเดียวกัน กฎ `SOURCE_WARD_MINIMUM_VIOLATION` เขียนในรอบ 1 แต่ยังไม่มีกรณีใช้จริง (ข้อ 7.2) |
| ปุ่มโหลด Scenario ในหน้า Demo | ยังไม่กำหนด | Scenario ใช้ใน Test เท่านั้น (Q16) |
| LINE จริง | 3 | ยังใช้ LINE Simulator |

---

## 2. Transition ใหม่

### 2.1 ตาราง Transition

เคสไม่ได้เดินตามผู้สมัครคนใดคนหนึ่งแล้ว สถานะเคสคำนวณจาก Gap ที่เหลือและ Offer ที่ค้าง (ข้อ 2.6 ก) เพิ่ม 7 เส้น และเลิกใช้ 2 เส้น

| # | จาก | ไป | เกิดเมื่อ |
|---|---|---|---|
| T1 | `WAITING_RESPONSE` | `OUTREACH` | Gap ยังไม่ถูกปิด และเคสไม่มี Offer ค้าง |
| T2 | `WAITING_RESPONSE` | `WAITING_APPROVAL` | คนที่เข้าเวรแล้วรวมกับคนที่รออนุมัติ ปิด Gap ได้ครบ |
| T3 | `WAITING_APPROVAL` | `WAITING_RESPONSE` | Gap ยังไม่ถูกปิดแม้รวมคนที่รออนุมัติ และเคสมี Offer ค้าง เกิดได้หลังมีคนหลุด หรือเมื่อ Offer ที่ถูกพักกลับมากดรับได้ |
| T4 | `WAITING_APPROVAL` | `OUTREACH` | Gap ยังไม่ถูกปิดแม้รวมคนที่รออนุมัติ และเคสไม่มี Offer ค้าง เกิดได้หลังผู้อนุมัติตัดสิน (อนุมัติหรือไม่อนุมัติก็ได้) |
| T5 | `OUTREACH` | `MANUAL_HANDOFF` | `contact_candidate` ไม่เหลือผู้สมัครที่ส่ง Offer ได้ ไม่มีคนรออนุมัติที่เติม Gap ได้ และไม่มี Offer ที่ถูกพักซึ่งยังไม่หมดเวลา |
| T6 | `OPTIMIZING` | `MANUAL_HANDOFF` | Solver ไม่ได้ผู้สมัครเลย (ตอนนี้โยน `NoCandidatesError`) |
| T7 | `OUTREACH` | `WAITING_APPROVAL` | `contact_candidate` ไม่เหลือผู้สมัครที่ส่ง Offer ได้ แต่ยังมีคนรออนุมัติที่เติม Gap ได้ |

เส้นเดิมที่ยังใช้: `OPEN → ASSESSING → OPTIMIZING → OUTREACH → WAITING_RESPONSE`, `WAITING_APPROVAL → EXECUTING → RESOLVED` และทุกสถานะ `→ FAILED`

เส้นเดิมที่เลิกใช้: `WAITING_RESPONSE → SAFETY_VALIDATION` และ `SAFETY_VALIDATION → WAITING_APPROVAL` เพราะ Safety ตรวจรายคนตอนตอบรับ เคสไม่หยุดที่สถานะนี้ (Q31) ค่า `SAFETY_VALIDATION` คงไว้ใน Enum ตกลงแล้ว: PR 0 เพิ่ม T1 ถึง T7 อย่างเดียว ยังไม่ลบสองเส้นนี้ เพราะโค้ดจริงยังใช้อยู่ (`outreach_service` สั่ง `resume()` ไป `SAFETY_VALIDATION` และ Orchestrator มี Handler ของสถานะนี้) ถ้าลบก่อน Golden Path และ E2E จะพัง ลบจริงใน PR 3 ซึ่งเป็น PR ที่ย้าย Safety ไปตรวจตอนตอบรับ

คำที่ใช้ในตาราง

* **Gap ถูกปิด** = Gap ของจำนวนคน, Role และ Skill เป็น 0 ทุกตัว เมื่อนับคนกลุ่มที่ระบุ (Q46)
* **Offer ค้าง** = Offer ของเคสที่ยัง `SENT` ไม่นับ Offer ที่ผู้สมัครกดรับไม่ได้เพราะรับของเคสอื่นค้างอยู่ (Q29)
* **Offer ที่ถูกพัก** = Offer ของเคสที่ยัง `SENT` แต่ผู้สมัครกดรับไม่ได้ชั่วคราว เพราะเขากดรับ Offer ของเคสอื่นไปแล้วและยังรอผล (ข้อ 2.6 ค) ไม่นับเป็น Offer ค้าง เคสจึงส่ง Wave ให้คนอื่นต่อได้ แต่ตราบที่ Offer นี้ยังไม่หมดเวลา เคสต้องไม่ไป `MANUAL_HANDOFF` เพราะผู้สมัครอาจกลับมากดรับได้
* **คนหลุด** = Safety ไม่ผ่าน หรือผู้อนุมัติไม่อนุมัติ Offer ของเขาเป็น `CANCELLED` (Q1, Q7)

ลำดับการตัดสินเมื่อยังมี Gap (กัน `MANUAL_HANDOFF` เร็วเกินไป)

```text
ยังมี Gap
→ มีผู้สมัครรออนุมัติที่เติม Gap ได้ไหม
    → มี:   รออนุมัติ ไม่ Handoff เพียงเพราะรายชื่อหมด
    → ไม่มี: ตรวจ Offer ที่ยังรอตอบ และผู้สมัครที่ยังติดต่อได้
        → มี:   ดำเนินการต่อ
        → ไม่มี: มี Offer ที่ถูกพักและยังไม่หมดเวลาไหม
            → มี:   รอที่ WAITING_RESPONSE จนรู้ผลของเคสที่ผู้สมัครไปรับ หรือจน Offer หมดเวลา
            → ไม่มี: MANUAL_HANDOFF
```

* เคสไม่ไป `MANUAL_HANDOFF` ตอนที่ยังมีคนรออนุมัติที่เติม Gap ได้ เพราะยังมีทางแก้ผ่าน Workflow ปกติ รอจนผู้อนุมัติตัดสิน การอนุมัติไม่มี Timeout (ข้อ 2.7)
* ระหว่างรอ ถ้ายังมีผู้สมัครที่ติดต่อได้ เคสส่ง Wave ต่อได้ตามปกติ การรออนุมัติไม่หยุดการหาคน
* หลังตัดสินครบแล้ว Gap ยังเหลือ และไม่มีอะไรให้ทำต่อ เคสจึงไป `MANUAL_HANDOFF` ผ่าน T4 แล้ว T5
* เคสที่รอ Offer ที่ถูกพักจะถูกปลุกสามทาง ทุกทางเรียก `recompute()` ของเคสนี้ (ข้อ 2.3): เคสที่ผู้สมัครไปรับไม่อนุมัติเขาหรือ Safety ไม่ผ่าน (Offer กลับมากดรับได้), เคสนั้นอนุมัติเขา (Offer ที่ขัดกับเวรใหม่ถูกยกเลิก) หรือ Offer หมดเวลา การรอนี้จึงนานสุดไม่เกินอายุของ Offer (ข้อ 2.7)
* ตัวอย่างที่กติกานี้กัน: A มี Offer ของเคส X และเคส Y โดยเคส Y เหลือ A เป็นคนสุดท้าย A กดรับเคส X ถ้าเคส Y ไป `MANUAL_HANDOFF` ทันที Offer ของ A จะถูกยกเลิก พอเคส X ไม่อนุมัติ A เขาจะกลับไปรับเคส Y ไม่ได้ ซึ่งขัดกับข้อ 2.6 ค

เส้นที่ไม่ต้องมี

* ไม่มีเส้นออกจาก `EXECUTING` นอกจาก `RESOLVED` และ `FAILED`: การจัดเวรรายคนเกิดตอนอนุมัติ เคสผ่าน `EXECUTING` ครั้งเดียวตอน Gap ถูกปิดเพื่อปิดงาน (Q45) และไม่มีการตรวจซ้ำตอนจัดเวร (Q38)
* ไม่มีสถานะ `WAITING_MERGE_WINDOW`: Window อยู่ก่อนเคส (ข้อ 2.5)

### 2.2 สิ่งที่ไม่เปลี่ยน

* `FAILED` ยังตั้งได้จากเส้นทาง D11 เท่านั้น (Exception) Handler ห้ามคืน `FAILED`
* `MANUAL_HANDOFF` → `FAILED` มีอยู่แล้ว ยังไม่เพิ่มเส้นออกจาก `MANUAL_HANDOFF` เส้นอื่น (เป็นงานรอบ 3)
* จุดรอของเคสยังมีสองจุด: `WAITING_RESPONSE`, `WAITING_APPROVAL`
* `CASE_STATUS_CHANGED` ยังเขียนโดย Orchestrator เท่านั้น

### 2.3 ผลต่อ Orchestrator (ไฟล์ของคน 1)

> กฎของ `decide_status()` ในข้อนี้ (3 ค่า 4 ข้อ) ถูกขยายเป็น 6 ค่า 7 ข้อใน PR S ตามรีวิว เพื่อให้เคสที่ไม่เหลือใครให้ติดต่อรอต่อที่จุดรอเดิมได้ ฉบับที่ใช้คือ `docs/workflow.md` ข้อ 5.3

* **ฟังก์ชันคำนวณสถานะเคส** ตัวใหม่ แยกเป็นสองชั้นแบบเดียวกับ `gap_calculator`
  * ชั้นตัดสิน (Pure Function ไม่อ่าน DB): `domain/workflow/case_status.py` มี `decide_status(facts: CaseFacts) -> CaseStatus` โดย `CaseFacts` เป็น Dataclass แบบ Frozen มี 3 ค่า: `gap_closed_by_assigned`, `gap_closed_with_pending`, `has_open_offer` คืนได้ 4 สถานะ ตรวจตามลำดับนี้ ข้อแรกที่จริงคือคำตอบ
    1. `gap_closed_by_assigned` จริง (คนที่ได้เข้าเวรแล้วปิด Gap ครบ) → `EXECUTING`
    2. `gap_closed_with_pending` จริง (รวมคนที่รออนุมัติแล้วปิด Gap ครบ) → `WAITING_APPROVAL`
    3. `has_open_offer` จริง (เคสมี Offer ค้าง) → `WAITING_RESPONSE`
    4. นอกนั้น → `OUTREACH`
  * ไม่มีค่าที่บอกว่า "มีคนรออนุมัติที่เติม Gap ได้" ใน `CaseFacts` เพราะการรออนุมัติไม่หยุดการส่ง Wave (ข้อ 2.1) `contact_candidate` เป็นคนเช็กเรื่องนี้เองตอนไม่เหลือผู้สมัคร (T7)
  * ชั้นลงมือ: `orchestrator.recompute(db: Session, case_id: int) -> CaseStatus` ล็อกเคสแบบเดียวกับ `resume()` ถ้าเคสอยู่ใน `AUTOMATION_STOPPED_STATUSES` (`RESOLVED`, `UNRESOLVED`, `FAILED`, `MANUAL_HANDOFF`) ไม่ทำอะไร คืนสถานะเดิม เพราะเคสที่หยุดแล้วไม่มีเส้นออก นอกนั้นโหลดข้อมูลมาสร้าง `CaseFacts` ถ้าสถานะที่ได้เท่าเดิมไม่เขียนอะไร ถ้าต่างจึงเปลี่ยนสถานะผ่าน `assert_transition()` เขียน `CASE_STATUS_CHANGED` แล้วเดินต่อถ้าสถานะใหม่ไม่ใช่จุดรอ Commit เหมือน `resume()`
  * ผู้เรียก: `outreach_service` (หลังตอบรับ, ปฏิเสธ, Offer หมดเวลา) และ `approval_service` (หลังตัดสิน) เรียก `recompute()` แทนการส่ง `next_status` เอง
  * **เคสอื่นที่ได้รับผลกระทบ:** เมื่อสถานะของผู้สมัครคนหนึ่งเปลี่ยนในเคส X (เขาตอบรับ, เขาหลุดเพราะ Safety ไม่ผ่านหรือไม่ได้รับอนุมัติ, หรือเขาได้เวร) Offer ของเขาในเคสอื่นเปลี่ยนตามไปด้วย คือถูกยกเลิก, เลิกนับเป็น Offer ค้าง หรือกลับมากดรับได้ (ข้อ 2.6 ค) แต่เคสอื่นนั้นไม่มีเหตุการณ์ของตัวเองมาสั่งให้คำนวณสถานะใหม่ ตัวอย่าง: เคส Y รอ A คนเดียว เคส X อนุมัติ A แล้วยกเลิก Offer ของ A ในเคส Y เคส Y จะค้างที่ `WAITING_RESPONSE` โดยไม่มี Offer ค้าง กติกา: หลัง Transaction ของเคส X Commit แล้ว ผู้เรียกเรียก `recompute()` ให้เคสอื่นทุกเคสที่ผู้สมัครคนนั้นมี Offer ที่ยัง `SENT` หรือเพิ่งถูกยกเลิกใน Transaction นั้น ทีละเคส เคสละ Transaction เรียงตาม `case_id`
  * **Job เก็บตก:** การเรียก `recompute()` ให้เคสอื่นเกิดหลัง Commit ถ้าระบบล่มตรงช่วงนั้น การเรียกจะหายไป ทุกรอบของ Job (ข้อ 2.5) จึงเรียก `recompute()` ให้เคสที่อยู่ `WAITING_RESPONSE`, ไม่มี Offer ค้าง (ไม่มี Offer ที่กดรับได้ตอนนี้) และเข้าเงื่อนไขข้อใดข้อหนึ่ง
    * เคสไม่มี Offer ที่เป็น `SENT` เหลือเลย
    * เคสมีแต่ Offer ที่ถูกพัก และใน Plan ยังมีผู้สมัครที่เคสนี้ยังไม่เคยส่ง Offer ให้
  * ตัวอย่างของเงื่อนไขข้อสอง: เคส Y ส่ง Offer ให้ A และยังมี B ที่ติดต่อได้ A กดรับเคส X ทำให้ Offer ของเคส Y ถูกพัก เคส X Commit แล้วระบบล่มก่อนเรียก `recompute()` ของเคส Y พอระบบกลับมา Job เจอเคส Y ตามเงื่อนไขข้อสอง เคส Y จึงส่ง Wave ให้ B ได้โดยไม่ต้องรอ Offer ของ A หมดเวลา
  * Job ไม่ยกเลิก Offer ที่ถูกพัก และไม่ทำให้เคสไป `MANUAL_HANDOFF` ก่อนเวลา เพราะ `contact_candidate` ยังตรวจตามลำดับเดิม (ข้อ 3.2 ขั้นที่ 6) เคสที่มีแต่ Offer ที่ถูกพักและไม่เหลือผู้สมัครที่ยังไม่เคยติดต่อ ไม่เข้าเงื่อนไขของ Job เพราะกำลังรออย่างถูกต้อง
  * ถ้าผู้สมัครที่เหลือถูกข้ามทั้งหมดในรอบนั้น (ไม่ผ่าน Hard Rules หรือเต็มเพดาน Offer) เคสกลับมารอที่ `WAITING_RESPONSE` และ Job ลองใหม่รอบถัดไป จนกว่าจะส่งได้หรือ Offer ที่ถูกพักหมดเวลา (ไม่เกินอายุของ Offer ข้อ 2.7)
  * `MANUAL_HANDOFF` กับ T7 ไม่ได้มาจาก `decide_status()` Handler `contact_candidate` เป็นคนตัดสินตอนเคสอยู่ `OUTREACH` เพราะต้องตรวจ Hard Rules ของผู้สมัครก่อนจึงรู้ว่าเหลือใคร ตอนไม่เหลือผู้สมัคร Handler ตรวจตามลำดับ: มีคนรออนุมัติที่เติม Gap ได้ → `WAITING_APPROVAL` (T7), มี Offer ที่ถูกพักและยังไม่หมดเวลา → `WAITING_RESPONSE`, ไม่มีทั้งสองอย่าง → `MANUAL_HANDOFF` (T5)
* **Safety ไม่เป็นขั้นของเคสแล้ว** `validate_safety` ถูกเรียกใน Transaction ของการตอบรับ ไม่ใช่ Handler ที่ Orchestrator เรียกตามสถานะ
* **การจัดเวรรายคน** อยู่ใน Transaction ของการอนุมัติ Handler ของ `EXECUTING` เหลืองานปิดเคส: ยกเลิก Offer ที่เหลือ แล้วเขียน `CASE_RESOLVED` (Q45)
* T5 กับ T6: Handler คืน `MANUAL_HANDOFF` พร้อม `wait = False` รอบถัดไปของลูปเห็นว่าอยู่ใน `AUTOMATION_STOPPED_STATUSES` แล้วหยุดเอง ต้องเพิ่ม Test ยืนยัน
* `_MAX_STEPS`: เส้น T1 กับ T4 เข้า `OUTREACH` ซึ่งจบได้สามทาง คือ `WAITING_RESPONSE`, `WAITING_APPROVAL` (T7) หรือ `MANUAL_HANDOFF` ทั้งสามเป็นจุดรอหรือจุดหยุด จึงไม่วนไม่จบ ต้องเพิ่ม Test
* คำขออนุมัติที่ค้างกัน `MANUAL_HANDOFF` ไว้ (ข้อ 2.1 ลำดับการตัดสิน และ T7) `contact_candidate` ต้องเช็กคนรออนุมัติก่อนคืน `MANUAL_HANDOFF`

### 2.4 คำถามของข้อนี้ที่ตอบแล้ว

* **Q1** ไม่อนุมัติ = คนนั้นหลุด Offer เป็น `CANCELLED` แล้วคำนวณสถานะเคสใหม่ `reason` ที่ผู้อนุมัติพิมพ์อยู่ใน Audit
* **Q2** ไม่เหลือผู้สมัคร (T5, T6) = `MANUAL_HANDOFF` ไม่ใช่ `FAILED` เพราะไม่ใช่ระบบขัดข้อง
* **Q3** Wave ถัดไปใช้ Plan เดิม ตรวจความพร้อมของคนซ้ำตอนจะส่ง (ข้อ 3) ไม่รัน Solver ใหม่ (Q37)

---


### 2.5 Merge Gap (ทำในรอบ 1)

เขียนตาม Flow ล่าสุด (`newworkflow.png`) ของเดิมที่ให้เคสรอใน `WAITING_MERGE_WINDOW` ยกเลิก

หลักใหม่: **Window อยู่ก่อนเคส** Event ของเวรเดียวกันถูกเก็บเป็น `RECEIVED` รอไว้ พอ Window ปิดจึงคิด Gap ครั้งเดียวจาก Event ทั้งชุด แล้วค่อยเปิดเคสใหม่ หนึ่ง Window เปิดได้หนึ่งเคส และ Event ไม่ถูกเอาไปรวมกับเคสที่มีอยู่แล้ว (Q43) เวรหนึ่งยังมีเคสที่เดินอยู่ได้เคสเดียว

```text
PART A: รับ Event (หนึ่ง Transaction ต่อ Event)
Lock shift → ตรวจ Request → สร้าง Event (RECEIVED) เก็บรายละเอียดใน payload → Commit
          → ยังไม่แก้ Table อื่น (Q41)
          → ถ้าเป็น Event แรกที่ RECEIVED ของเวรนี้ = Window เปิด

PART B: ปิด Window (หนึ่ง Transaction ต่อเวร)
ถึงเวลาปิด = ครบ merge_window_seconds และเคสก่อนหน้าของเวรนี้จบแล้ว (Q43)
         → Lock shift → อ่าน Event ที่ RECEIVED ทั้งหมดของเวรนี้

  วนทีละ Event (เรียงตาม occurred_at, id)
    → Update table ที่เกี่ยวข้องกับ Event ตัวนี้ (การลา, ยกเลิก Roster, patient_count ...)
         └─ Update ไม่ได้ → Event ตัวนี้ = IGNORED เฉพาะตัวนั้น (Q44) ไป Event ตัวถัดไป
    → ตรวจ Threshold จากข้อมูลของเวรหลัง Event ตัวนี้ (Ratio, Role Gap, Skill Gap)
    → จดว่า Event ตัวนี้ผ่านหรือไม่ผ่าน ยังไม่สร้างเคส และยังไม่เขียน required_staff

  ครบทุก Event แล้ว → มี Event ที่ผ่าน Threshold อย่างน้อยหนึ่งตัวไหม
         ├─ ไม่มี → Event ทุกตัวใน Window = IGNORED จบ
         └─ มี   → เขียน required_staff จาก patient_count ค่าสุดท้ายของเวร
                  → คิด Gap จาก Requirement ล่าสุด + Roster
                  → Gap เป็น 0 ทุกตัวไหม (จำนวนคน, Role, Skill)
                       ├─ ใช่    → ไม่สร้างเคส Event ทุกตัวใน Window = IGNORED จบ
                       └─ ไม่ใช่ → สร้างเคสหนึ่งเคส
                                  → Event ทุกตัวใน Window = PROCESSED และ Link เข้าเคส (case_id)
                                    รวมตัวที่ไม่ผ่าน Threshold (Q42) ยกเว้นตัวที่ IGNORED ตาม Q44
                                  → บันทึก Gap หนึ่งแถว → Optimize

Event ที่เข้ามาระหว่าง PART B: รอ Lock ของ shift แล้วเป็น Event แรกของ Window รอบถัดไป
Event ที่เข้ามาตอนเวรมีเคสเดินอยู่: เก็บเป็น RECEIVED รอจนเคสนั้นจบ แล้วจึงเป็น Window รอบถัดไป (Q43)
```

เหตุผลที่สร้างเคสและเขียน `required_staff` หลังวนครบ ไม่ทำกลางลูป: Event ตัวหลังเปลี่ยนข้อมูลที่ Event ตัวก่อนใช้ได้ ตัวอย่าง เวรมี 5 คน Ratio 2 Event แรกแจ้งผู้ป่วย 12 คน ผ่าน Threshold Event ที่สองแจ้งผู้ป่วยเหลือ 10 คน ไม่ผ่าน ถ้าเขียน `required_staff` = 6 ตั้งแต่ Event แรกแล้วไม่เขียนใหม่ Gap จะบอกว่าขาด 1 คน ทั้งที่ผู้ป่วย 10 คนต้องการแค่ 5 คน การเขียนจากค่าสุดท้ายได้ 5 และ Gap เป็น 0 จึงไม่เปิดเคส (ตรวจตัวเลขด้วยโค้ดแล้ว)

#### Window เก็บที่ไหน

ไม่มีตารางใหม่ และไม่มีคอลัมน์ใน `STAFFING_CASES` (ตอน Window เปิดยังไม่มีเคส) อ่านจาก `STAFFING_EVENTS` กับความยาว Window ที่เก็บใน `SHIFT`

| ต้องรู้อะไร | อ่านจาก |
|---|---|
| เวรนี้มี Window เปิดอยู่ไหม | มี Event ที่ `shift_id` นี้ และ `status = RECEIVED` อย่างน้อย 1 แถว |
| Window เปิดตอนไหน | `min(occurred_at)` ของ Event กลุ่มนั้น (`occurred_at` ตั้งจาก `clock.now()` ตอนรับ Event) |
| Window ปิดตอนไหน | เวลาที่ช้ากว่าระหว่าง `min(occurred_at)` + `SHIFT.merge_window_seconds` กับเวลาที่เคสก่อนหน้าของเวรนั้นจบ ถ้าเวรไม่มีเคสเดินอยู่ ใช้ค่าแรกอย่างเดียว (Q43) |
| Event ไหนอยู่ใน Window นี้ | Event ที่ `RECEIVED` ทุกแถวของเวรนั้น |
| Event ไหนเคยอยู่ Window เดียวกัน (ดูย้อนหลัง) | `shift_id` เดียวกัน และ `processed_at` เท่ากัน |
| Event ไหนเป็นของเคสไหน | `STAFFING_EVENTS.case_id` |

คอลัมน์ที่เปลี่ยน (Migration ใหม่)

| ตาราง | Field | Type | Null | หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `SHIFT` | `merge_window_seconds` (เพิ่ม) | integer | NOT NULL | CHECK `>= 0` ความยาว Window ของเวรนี้เป็นวินาที 0 = ไม่รอ |
| `STAFFING_EVENTS` | `processed_at` (เพิ่ม) | timestamptz | NULL | เวลาที่ Window ของ Event นี้ปิด ตั้งเมื่อเป็น `PROCESSED` หรือ `IGNORED` Event ที่ปิดพร้อมกันได้ค่าเดียวกัน (อ่าน `clock.now()` ครั้งเดียวต่อการปิดหนึ่งครั้ง) CHECK: ว่างก็ต่อเมื่อ `status = RECEIVED` |
| `STAFFING_EVENTS` | `case_id` (เพิ่ม) | bigint | NULL | FK `STAFFING_CASES.id` ตั้งตอน Window ปิดให้ Event ทุกตัวของ Window ที่มีเคส (Q42) ยกเว้นตัวที่เป็น `IGNORED` ตาม Q44 ว่างเมื่อเป็น `RECEIVED` หรือ `IGNORED` |
| `STAFFING_CASES` | `event_id` (ลบ) | | | เคสหนึ่งมีได้หลาย Event ความสัมพันธ์จึงย้ายไปอยู่ฝั่ง Event |
| `AUDIT_LOG` | `event_id` (เพิ่ม) | bigint | NULL | FK `STAFFING_EVENTS.id` ตั้งในแถว Audit ที่เป็นเรื่องของ Event ตัวนั้น (Q33) |

`EventStatus` ใช้ 3 ค่าเดิม ไม่เพิ่ม `PROCESSING` เพราะ PART B อยู่ใน Transaction เดียว ไม่มีใครเห็นสถานะระหว่างทาง

#### ทำไม Window ใหม่ไม่ปนกับของเก่า

ต้องจริงทั้งสามข้อ และต้องมี Test ยืนยัน

1. PART B เปลี่ยนสถานะ Event ทั้งชุดใน Transaction เดียว ถ้าพังกลางทาง Rollback ทั้งชุด ทุกตัวยัง `RECEIVED` Window เดิมยังไม่ปิด
2. PART A และ PART B ล็อก shift ตัวเดียวกัน Event ที่มาช้าจึงเข้าได้แค่สองแบบ: Commit ก่อน PART B ล็อก (อยู่ Window เก่า) หรือหลัง PART B เสร็จ (เป็นตัวแรกของ Window ใหม่)
3. สถานะไม่ย้อนกลับ ไม่มีโค้ดไหนเปลี่ยน `PROCESSED` / `IGNORED` กลับเป็น `RECEIVED`

Event หนึ่งตัวจึงอยู่ได้ Window เดียว ส่วน**ตัวเลข Gap** ของ Window ใหม่คิดจากสภาพเวรทั้งหมดตอนนั้น ไม่ใช่เฉพาะ Event ใหม่ (ตั้งใจ ตรงกับ Q26)

#### Gap รวมกันยังไง

ไม่มีการบวกแถว คิดครั้งเดียวตอน Window ปิดจากข้อมูลปัจจุบันของเวร

| ส่วน | รวมยังไง |
|---|---|
| ความต้องการ (`required_staff`) | UPDATE ในแถว Requirement เดิม ครั้งเดียวหลังวนครบทุก Event เมื่อมี Event ที่ผ่าน Threshold อย่างน้อยหนึ่งตัว ใช้ `patient_count` ค่าสุดท้ายของเวร |
| จำนวนคนในเวร | นับใหม่จาก Roster ที่ `ASSIGNED` หลังวนครบทุก Event การลาของทุก Event ใน Window ถูกหักแล้ว |
| `headcount_gap` | `effective_minimum - current_valid_staff` คิดครั้งเดียวจากสองบรรทัดบน (ข้อ 8.2) |
| Gap ของ Role / Skill | คิดใหม่ทุกตัว: จำนวนที่ต้องการ ลบ คนในเวรที่มี Role / Skill นั้น |

#### สิ่งที่ตกลงแล้ว

| หัวข้อ | กติกา |
|---|---|
| ตำแหน่งของ Window | ก่อนเคส เคสเกิดหลัง Window ปิดและเวรขาดคนจริง |
| สถานะเคส | ไม่เพิ่ม `WAITING_MERGE_WINDOW` Merge Gap ไม่เพิ่ม Transition เคสใหม่เดิน `OPEN → ASSESSING` เหมือนเดิม จุดรอของเคสยังมีสองจุด |
| เก็บ Window | อ่านจาก `STAFFING_EVENTS` ตามตารางข้างบน เพิ่ม `processed_at` และ `case_id` |
| Event กับเคส | `STAFFING_EVENTS.case_id` ชี้ไปที่เคส ลบ `STAFFING_CASES.event_id` |
| `EventStatus` | 3 ค่าเดิม ไม่เพิ่ม `PROCESSING` |
| ความยาว Window | `SHIFT.merge_window_seconds` ตั้งได้ต่อเวร ค่าที่ใช้กับการ Merge เริ่มที่ 600 (10 นาที) แล้วปรับ |
| Window = 0 | เวรใน Golden Case ตั้ง `merge_window_seconds = 0` Demo ปกติและ Test เดิมจึงได้ผลเหมือนวันนี้: PART A เรียก PART B ต่อใน Transaction เดียวกัน `POST /events` ยังเดินรวดเดียวถึง `WAITING_RESPONSE` และตอบ `case_id` เหมือนเดิม (ยกเว้นตอนเวรมีเคสเดินอยู่ Event จะรอเป็น `RECEIVED` ดูข้อจำกัดที่รู้) ตั้งเป็น 600 เฉพาะเวรใน Scenario ของการ Merge |
| ปิด Window ใน Demo | เลื่อน Clock ต้องมี Route เลื่อนนาฬิกาและปุ่มในหน้า `demo/control` Route นี้เรียกฟังก์ชันปิด Window ตัวเดียวกับ Job เพราะเลื่อนนาฬิกาอย่างเดียว Job ไม่รันเอง |
| หาเวรที่ถึงเวลาปิด | เวรที่มี Event `RECEIVED`, `min(occurred_at) + merge_window_seconds <= clock.now()` และไม่มีเคสที่ยังเดินอยู่ของเวรนั้น |
| หนึ่ง Window หนึ่งเคส (Q43) | Window หนึ่งสร้างเคสได้มากสุดหนึ่งเคส เคสถูกสร้างหลังวนครบทุก Event เมื่อมี Event ที่ผ่าน Threshold และ Gap สุดท้ายไม่เป็น 0 Event ทุกตัวใน Window Link เข้าเคสนั้น ไม่มีการเอา Event ไปรวมกับเคสของ Window ก่อน |
| Threshold (Q32) | ตรวจตอน Window ปิด **ทีละ Event ตามลำดับ** กับ Event ทุกชนิด ไม่มีชนิดไหนผ่านเสมอ ดู 3 อย่างจากข้อมูลของเวรหลัง Event ตัวนั้น: Ratio, Role Gap, Skill Gap ผ่านเมื่อมีอย่างน้อยหนึ่งอย่างเกิน ข้อมูลสะสม Event ตัวหลังจึงเห็นผลของตัวก่อน รายละเอียดอยู่ใต้ตารางนี้ |
| Event ที่ผ่าน Threshold | ระบบจดไว้ว่าผ่าน ยังไม่สร้างเคสและยังไม่เขียน `required_staff` ทั้งสองอย่างทำหลังวนครบทุก Event จากข้อมูลสุดท้ายของเวร |
| มี Event ผ่าน แต่ Gap สุดท้ายเป็น 0 ทุกตัว | ไม่สร้างเคส Event ทุกตัวใน Window เป็น `IGNORED` เหตุผลอยู่ใน payload ของ `EVENT_IGNORED` เกิดเมื่อ Event ตัวหลังทำให้เวรกลับมาพอ เช่น จำนวนผู้ป่วยลดลง `required_staff` ยังถูกเขียนตามค่าสุดท้าย |
| Update table ที่เกี่ยวข้อง (Q41) | ทำตอน Window ปิด ทีละ Event ไม่ทำตอนรับ Event ตอนรับ Event เขียนแค่แถว Event กับ `EVENT_RECEIVED` |
| Event ที่ไม่ผ่านใน Window ที่มีตัวผ่าน (Q42) | เป็น `PROCESSED` และ Link เข้าเคสเดียวกัน Window ที่มีเคสจึงจบแบบนี้: ทุกตัว `PROCESSED` + Link ยกเว้นตัวที่ Update table ไม่ได้ ซึ่งเป็น `IGNORED` เฉพาะตัวนั้น (Q44) ส่วน Window ที่ไม่มีเคส ทุกตัวเป็น `IGNORED` |
| ผู้แจ้งหาเคสของ Event (Q36) | อ่านจาก `STAFFING_EVENTS.case_id` ผ่าน Route อ่าน Event (ข้อ 6.1) |
| ไม่มี Event ไหนผ่าน | Event ทุกตัวใน Window เป็น `IGNORED` ไม่มีเคส ไม่เขียน `required_staff` ใหม่ ส่วนสิ่งที่ Event แก้ไปแล้วในขั้น Update table ยังอยู่ เช่น การลา, Roster ที่ยกเลิก, `patient_count`, จำนวนของ Role / Skill จาก `REQUIREMENT_CHANGED` |
| Gap | คิดครั้งเดียวหลังวนครบทุก Event ถ้าไม่เป็น 0 จึงสร้างเคสและบันทึก Gap หนึ่งแถว ไม่สร้างต่อ Event |
| Event ที่รับในรอบ 1 (Q32) | ครบทั้งสี่ชนิด: `STAFF_UNAVAILABLE`, `ASSIGNMENT_CANCELLED`, `PATIENT_SURGE`, `REQUIREMENT_CHANGED` |
| Audit ของ Event (Q33) | เพิ่ม `AUDIT_LOG.event_id` แถว Audit ที่เป็นเรื่องของ Event ใส่ `event_id` อย่างเดียว ไม่ใส่ `case_id` ทุกกรณี รวมถึง Window = 0 ใส่ตั้งแต่ตอนเขียน ไม่มีการแก้แถว Audit ทีหลัง |
| Migration (Q34) | ทำเป็น Migration ใหม่ ไม่แก้ไฟล์ Migration เดิม ไม่เติมค่าให้ข้อมูลที่มีอยู่ ทุกคนรัน `make reset` ก่อน |
| Job ปิด Window (Q35) | Service แยกใน `docker-compose.yml` เป็นตัวจับรอบ ทุก 30 วินาทีเรียก Route ภายในของ Backend ให้ Backend ปิด Window ที่ถึงเวลาด้วยนาฬิกาของ Backend เอง |
| Event ของเคสใน Case API (Q36) | ตอบเป็น List `event_ids` แทน `event_id` ตัวเดียว |
| Event ของเวรที่มีเคสเดินอยู่ (Q43) | ไม่เข้าเคสนั้น เก็บเป็น `RECEIVED` รอจนเคสนั้นจบ แล้ว Window ของมันจึงปิดและเปิดเคสใหม่ของตัวเอง แทนคำตอบเดิมของ Q26 |
| เคสก่อนหน้า "จบ" (Q49) | นับ 4 สถานะ: `RESOLVED`, `UNRESOLVED`, `FAILED`, `MANUAL_HANDOFF` |
| Q24, Q25 | ตอบแล้ว ดูข้อ 2.6 |

#### Threshold ดูอะไร (Q32)

| ตัวที่ดู | ผ่านเมื่อ | ข้อมูลที่ใช้ |
|---|---|---|
| Ratio | ผู้ป่วยต่อพยาบาลของเวรเกินค่าที่กำหนด: `patient_count > maximum_patients_per_nurse * จำนวนคนในเวร` | `SHIFT.patient_count`, Roster ที่ `ASSIGNED`, `HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse` |
| Role Gap | มี Role อย่างน้อยหนึ่งตัวที่คนในเวรน้อยกว่าจำนวนที่ต้องการ | Requirement ของ Role, Roster |
| Skill Gap | มี Skill อย่างน้อยหนึ่งตัวที่คนในเวรน้อยกว่าจำนวนที่ต้องการ | Requirement ของ Skill, Roster |

* ผ่านเมื่อข้อใดข้อหนึ่งเป็นจริง ใช้กติกาเดียวกับ Event ทุกชนิด
* เขียน Ratio เป็นการคูณ ไม่ใช่การหาร เพราะเวรที่ไม่เหลือคนจะหารด้วยศูนย์
* ข้อ Ratio ให้ผลเท่ากับ "จำนวนคนในเวร < `ceil(patient_count / maximum_patients_per_nurse)`" คือเทียบกับ `required_staff` ค่าใหม่ ก่อนเขียนลง Requirement (ตรวจด้วยโค้ดแล้ว ตรงกันทุกค่าที่ลอง)
* ไม่ต้องมีคอลัมน์เก็บค่า Threshold เพิ่ม ใช้ค่าที่มีอยู่แล้วทั้งหมด
* ความหมายของ Ratio ข้างบนยืนยันแล้ว
* **Threshold ไม่ดู `minimum_staff` (ยืนยันแล้ว):** เวรที่คนต่ำกว่า `minimum_staff` แต่ Ratio ยังไม่เกินและไม่ขาด Role / Skill เป็น `IGNORED` ตัวอย่าง: ผู้ป่วย 2 คน, `minimum_staff = 2`, เหลือคน 1 คน Ratio = 2 ต่อ 1 ไม่เกิน จึงไม่เปิดเคส `minimum_staff` มีผลหลังผ่าน Threshold แล้วเท่านั้น คือทำให้ `headcount_gap` ที่คิดจาก `effective_minimum` (ข้อ 8.2) มากขึ้นได้

#### Table ที่เกี่ยวข้องของ Event แต่ละชนิด (Q40, Q41)

รอบ 1 รับครบสี่ชนิด ตอนนี้โค้ดรับแค่ชนิดแรก ชนิดอื่น `receive_event()` ตอบ `EventNotSupportedError` กติกาของอีกสามชนิดตกลงแล้ว (Q40) ตารางนี้คือขั้น "Update table ที่เกี่ยวข้อง" ในแผนภาพ

| ชนิด | กลุ่ม | Table ที่ต้องแก้ | สถานะ |
|---|---|---|---|
| `STAFF_UNAVAILABLE` | บุคลากร (มี `staff_id`) | แถว `STAFF_UNAVAILABILITY` และยกเลิก Roster ของคนนั้นในเวร | มีแล้ว |
| `ASSIGNMENT_CANCELLED` | บุคลากร (มี `staff_id`) | Roster ของคนนั้นในเวรเป็น `CANCELLED` ไม่มีแถวการลา | ตกลงแล้ว |
| `PATIENT_SURGE` | ภาระงาน (`staff_id` ว่าง) | `SHIFT.patient_count` = ค่าใหม่ | ตกลงแล้ว |
| `REQUIREMENT_CHANGED` | ภาระงาน (`staff_id` ว่าง) | UPDATE แถวใน `STAFFING_REQUIREMENT_ROLE` / `STAFFING_REQUIREMENT_SKILL` ของเวร ในแถวเดิม | ตกลงแล้ว |

**กติกาของ Q40** (ตกลงแล้ว) ใช้ `POST /events` ตัวเดียว เพิ่ม Field ใน Body ตามชนิด

| ชนิด | ใครแจ้ง | Body ที่เพิ่ม | ตรวจตอนรับ (ไม่ผ่าน = ปฏิเสธ Request) | Audit ตอน Window ปิด |
|---|---|---|---|---|
| `STAFF_UNAVAILABLE` | เจ้าตัว (เดิม) | `end_at` ไม่บังคับ (เดิม) | `404` ไม่มีเวร, `422` `end_at` ไม่หลังเวลาเริ่มเวร, `409` ไม่มี Roster `ASSIGNED` (เดิม) | `UNAVAILABILITY_CREATED` (เดิม) |
| `ASSIGNMENT_CANCELLED` | Head Nurse | `staff_id` ของคนที่ถูกยกเลิก, `reason` | `403` ไม่ใช่ Head Nurse, `409` คนนั้นไม่มี Roster `ASSIGNED` ในเวร, `422` `reason` ว่าง | Action ใหม่ `ASSIGNMENT_CANCELLED` |
| `PATIENT_SURGE` | Head Nurse | `patient_count` = จำนวนผู้ป่วยรวมค่าใหม่ | `403`, `422` ค่าติดลบ | Action ใหม่ `PATIENT_COUNT_UPDATED` (payload มีค่าเก่าและค่าใหม่) |
| `REQUIREMENT_CHANGED` | Head Nurse | `roles`: List ของ `{role_id, required_count}`, `skills`: List ของ `{skill_id, required_count}` ต้องมีอย่างน้อยหนึ่งรายการ | `403`, `422` id ไม่อยู่ใน Requirement ของเวร หรือค่าติดลบ | Action ใหม่ `REQUIREMENT_UPDATED` (payload มีค่าเก่าและค่าใหม่) |

* `payload` ของ Event เก็บ Field ที่เพิ่มใน Body ตามที่ส่งมา PART B อ่านจากตรงนี้ (Q41)
* `PATIENT_SURGE` ส่งค่ารวม ไม่ใช่ส่วนต่าง: Event สองตัวใน Window เดียวทำตามลำดับ ตัวหลังชนะ และทำซ้ำได้โดยค่าไม่เพี้ยน ค่าลดลงก็รับ (จะไม่ผ่าน Threshold เอง)
* "Head Nurse" ตรวจด้วย Role เดียวกับผู้อนุมัติใน `approval_service` (`403` แบบเดียวกัน)
* `REQUIREMENT_CHANGED` แก้ได้แค่จำนวนของ Role / Skill ไม่แก้ `minimum_staff` และ `required_staff` (ตัวหลังมาจากสูตร)
* ของกลางที่ต้องเพิ่ม: `AuditAction` 3 ค่า, `EntityType` 2 ค่า (`SHIFT`, `STAFFING_REQUIREMENTS`), Field ใน `EventCreate`
* หน้า `demo/control`: ปุ่มละชนิด ใช้ค่าตายตัวของ Golden Case
* แถว Audit ทั้งสามใส่ `event_id` แบบเดียวกับ `UNAVAILABILITY_CREATED` (Q33)

#### ผลต่อโค้ด (งานของคน 1 ใน PR M)

* `event_service.receive_event()`: เหลือแค่ล็อกเวร ตรวจ Request สร้าง Event (`RECEIVED`) และเขียน `EVENT_RECEIVED` ส่วนการบันทึกการลา ยกเลิก Roster คิด Gap และเปิดเคส ย้ายไปฟังก์ชันปิด Window ทั้งหมด (Q41) ถ้า Window = 0 เรียกฟังก์ชันนั้นต่อทันที
* ย้ายความสัมพันธ์ Event กับเคส: Model `StaffingCase` (ลบ `event_id`), `StaffingEvent` (เพิ่ม `case_id`), `case_service`, Schema ของ Case API (`event_id` ตัวเดียวใช้ไม่ได้แล้ว), หน้า `cases/[id]` ที่แสดง `event_id`, Seed และ Test ที่สร้างเคสด้วย `event_id`
* ฟังก์ชันใหม่สองตัว: หาเวรที่ถึงเวลาปิด และปิด Window ของเวรเดียว (PART B)
* ฟังก์ชันตรวจ Threshold แยกเป็นของตัวเอง รับข้อมูลของเวรแล้วคืนว่าผ่านเพราะข้อไหน
* `audit_service.log()` รับ `event_id` เพิ่ม (ฟังก์ชันกลาง ต้องแจ้งทีมก่อน) และ `case_service.get_case_timeline()` ดึงแถวของ Event ที่เป็นของเคสด้วย
* Service ใหม่ใน `docker-compose.yml` สำหรับ Job ปิด Window
* คำตอบของ `POST /events` เมื่อ Window > 0: `event_status = RECEIVED`, `case_id = null` หน้าเว็บต้องรับได้ (กระทบข้อ 6)
* เส้น `OPEN → ASSESSING` ไม่เปลี่ยน Test ที่ผ่านเส้นนี้ไม่ต้องแก้

#### คำตอบของคำถามในข้อนี้

* **ความยาว Window** ตอบแล้ว: `SHIFT.merge_window_seconds` (ตารางข้างบน)
* **Event กับเคส (Q36)** ตอบครบแล้ว: `STAFFING_EVENTS.case_id` ลบ `STAFFING_CASES.event_id` Case API ตอบ `event_ids` เป็น List ผู้แจ้งดูเคสของ Event จาก `case_id` ใน Event
* **Timeline ของเคสตอน Window > 0 (Q33)** ตอบแล้ว: เพิ่ม `AUDIT_LOG.event_id`
  * แถวที่ใส่ `event_id`: `EVENT_RECEIVED`, `UNAVAILABILITY_CREATED`, `EVENT_IGNORED` ใส่ตั้งแต่ตอนเขียน
  * Timeline ของเคส = แถวที่ `case_id` เป็นเคสนี้ รวมกับแถวที่ `event_id` เป็น Event ของเคสนี้ (หาจาก `STAFFING_EVENTS.case_id`) เรียงตาม `id` `EVENT_RECEIVED` และแถวการลาทุกแถวขึ้นก่อน `CASE_OPENED` เพราะเคสถูกสร้างหลังวนครบทุก Event
  * Event ที่ `IGNORED` ไม่มีเคส แต่ยังค้น Audit ของมันได้จาก `event_id`
  * ตอบแล้ว: ใส่แค่ `event_id` ทุกกรณี รวมถึง Window = 0 สองแถวแรกจึงไม่มี `case_id` อีกต่อไป Test ที่หาแถวสองแถวนี้ด้วย `case_id` ต้องแก้
* **Threshold (Q32)** ตอบครบแล้ว: ดู Ratio, Role Gap, Skill Gap ไม่ดู `minimum_staff` และรอบ 1 รับ Event ครบสี่ชนิด
* **กติการับ Event สามชนิดใหม่ (Q40)** ตอบแล้ว ตามข้อเสนอ ดูหัวข้อ "Table ที่เกี่ยวข้องของ Event แต่ละชนิด"
* **Update table ที่เกี่ยวข้อง (Q41)** ตอบแล้ว: ทำหลัง Window ปิด ผลที่ตามมา
  * ระหว่างรอ Window คนที่แจ้งลายังเป็น `ASSIGNED` ใน Roster หน้า `roster` และ Solver ของเคสอื่นยังเห็นเขาอยู่ในเวร
  * รายละเอียดของ Event ต้องอยู่ใน `STAFFING_EVENTS.payload` ตั้งแต่ตอนรับ เช่น เวลากลับของคนลา (`end_at`) เพราะ PART B เป็นคนเขียน `STAFF_UNAVAILABILITY`
  * `UNAVAILABILITY_CREATED` ย้ายไปเขียนใน PART B
  * การตรวจ "คนนี้มี Roster `ASSIGNED` ในเวรนี้" ทำตอนรับ Event ได้เหมือนเดิม แต่ไม่กันการแจ้งซ้ำใน Window เดียวกัน เพราะ Roster ยังไม่ถูกยกเลิก
* **Event ที่ Update table ไม่ได้ตอน Window ปิด (Q44)** ตอบแล้ว ตามข้อเสนอ: Event ตัวนั้นเป็น `IGNORED` ตัวเดียว ไม่ Link เข้าเคส เหตุผลอยู่ใน payload ของ `EVENT_IGNORED` ตัวอื่นใน Window เดินต่อตามปกติ ตัวอย่าง: คนเดียวแจ้งลาเวรเดียวกันสองครั้งใน Window เดียว ตัวที่สองไม่มี Roster ให้ยกเลิก
* **Event ที่ไม่ผ่าน Threshold ใน Window ที่มีเคส (Q42)** ตอบแล้ว: `PROCESSED` และ Link เข้าเคส
* **กล่อง "มีการสร้าง Case" (Q43)** ตอบแล้ว: หมายถึงใน Window นั้นมีการสร้างเคสไหม หนึ่ง Window มีเคสเดียว Window ถัดไปของเวรเดียวกันถูกกันไว้ จนถึงเวลาที่ช้ากว่าระหว่างเคสก่อนหน้าจบกับครบ `merge_window_seconds` จึงไม่มีกรณี Event เข้าเคสเดิม
* **Optimize หลังสร้าง Gap (Q37)** ตอบแล้ว: ไม่มีการ Optimize ซ้ำ Solver รันครั้งเดียวตอนเคสเกิด และเคสไม่ได้ Gap เพิ่มกลางทางอีกแล้ว (Q43) ข้อจำกัดเรื่อง Plan เดิมไม่พอจึงไม่มี
* **Migration (Q34)** ตอบครบแล้ว: Migration ใหม่ ไม่เติมค่า ทุกคนรัน `make reset` ก่อน ต้องแจ้งทีมตอน merge PR M
* **Job ปิด Window (Q35)** ตอบครบแล้ว: Service แยกใน `docker-compose.yml` เป็นตัวจับรอบ ทุก 30 วินาทีเรียก Route ภายในของ Backend
  * เหตุผลที่ Service ไม่ตัดสินเอง: เวลาของ Demo ที่ถูกหยุดไว้อยู่ในหน่วยความจำของ Process ของ Backend (`core/clock.py`) Service แยกเห็นแต่เวลาจริง Backend จึงเป็นคนตัดสินด้วยนาฬิกาตัวเดียว
  * ปุ่มเลื่อน Clock ของ Demo เรียกฟังก์ชันปิด Window ตัวเดียวกัน
  * Route ภายใน: `POST /internal/merge-windows/close-due` กันด้วย Secret ใน Header ค่าอ่านจาก env ไม่ Commit ลง Repo

#### ข้อจำกัดที่รู้

* แก้ `merge_window_seconds` ของเวรขณะ Window เปิดอยู่ เวลาปิดเลื่อนตาม เพราะไม่ได้เก็บเวลาปิดไว้
* ถ้า PART B พังกับเวรไหน Event ของเวรนั้นค้าง `RECEIVED` และ Job ลองใหม่ทุกรอบ
* ระหว่างที่เคสของเวรยังเดินอยู่ Event ใหม่ของเวรนั้นไม่ถูกทำอะไร Offer มี Timeout (ข้อ 2.7) แต่การอนุมัติไม่มี เคสที่ค้างรออนุมัติจึงเดินได้นาน คนที่แจ้งลาช่วงนั้นยังเป็น `ASSIGNED` ใน Roster (Q41) และการขาดคนเพิ่มยังไม่ถูกหาคนแทนจนกว่าเคสแรกจบ
* ตอน Window = 0 ถ้าเวรมีเคสเดินอยู่ `POST /events` ตอบ `RECEIVED` ไม่ได้เคสทันที Test ที่ให้สองคนลาเวรเดียวกันแล้วคาดสองเคสทันทีต้องแก้
* ตอน Window = 0 กับ Clock ที่หยุดนิ่งของ Demo Event คนละชุดของเวรเดียวกันได้ `processed_at` เท่ากันได้ ยอมรับ เพราะตอน Window = 0 หนึ่ง Event คือหนึ่งชุดอยู่แล้ว
* `docs/database-schema.md` มีคอลัมน์ที่เปลี่ยนทั้งห้าตัวแล้ว (หัวข้อ 7, 8, 12, 30) รวม CHECK ของ `processed_at`

---

### 2.6 คำตอบชุดล่าสุด: เคสรับหลายคนแบบขนาน และผู้สมัครถือหลาย Offer

ข้อนี้เป็นกติกาหลักของเคสที่รับหลายคน ข้อ 2.1, 3, 4, 5.3, 6, 9, 10 เขียนใหม่ตามข้อนี้แล้ว ถ้าเจอที่ไหนขัดกัน **ให้ยึดข้อนี้**

**ก. สถานะสองระดับ (Q24.2)**

เคสหนึ่งมีผู้สมัครหลายคนพร้อมกัน แต่ละคนอยู่คนละขั้น

* **สถานะรายคน** ไม่มีคอลัมน์เดียวที่เก็บ อ่านจากแถวของผู้สมัคร (ผูกด้วย `candidate_item_id`)

| ผู้สมัครอยู่ขั้นไหน | ดูจาก |
|---|---|
| ยังไม่ถูกติดต่อ | ไม่มีแถว `CANDIDATE_OUTREACH` |
| ส่ง Offer แล้ว รอคำตอบ | `CANDIDATE_OUTREACH.status = SENT` |
| ปฏิเสธ | `status = REJECTED` |
| ตอบรับ รอตรวจ Safety | `status = ACCEPTED` และยังไม่มีแถว `SAFETY_VALIDATION` |
| ตอบรับ แต่ Safety ไม่ผ่าน | `SAFETY_VALIDATION.is_passed = false` และ Offer เป็น `CANCELLED` |
| รออนุมัติ | `APPROVAL_REQUEST.is_pending = true` |
| ไม่ได้รับอนุมัติ | `APPROVAL_REQUEST.is_approved = false` และ Offer เป็น `CANCELLED` |
| ได้รับอนุมัติ | `APPROVAL_REQUEST.is_approved = true` |
| ได้เข้าเวรแล้ว | มีแถว `ROSTER_ASSIGNMENT` แบบ `REPLACEMENT` |

* **สถานะเคส** คำนวณจาก Gap ที่เหลือ ไม่ตามผู้สมัครคนใดคนหนึ่ง (คำว่า "Gap ถูกปิด" และ "Offer ค้าง" นิยามในข้อ 2.1)

| เงื่อนไข | `CaseStatus` |
|---|---|
| คนที่ได้เข้าเวรแล้วปิด Gap ครบ | `EXECUTING` แล้วเป็น `RESOLVED` |
| คนที่ได้เข้าเวรแล้วรวมกับคนที่รออนุมัติ ปิด Gap ครบ | `WAITING_APPROVAL` |
| Gap ยังไม่ถูกปิด และมี Offer ค้าง | `WAITING_RESPONSE` |
| Gap ยังไม่ถูกปิด ไม่มี Offer ค้าง แต่ยังมีผู้สมัครใน Plan ที่ส่ง Offer ได้ | `OUTREACH` (ส่ง Wave ถัดไป) แล้วเป็น `WAITING_RESPONSE` |
| Gap ยังไม่ถูกปิด ไม่เหลือผู้สมัครที่ส่ง Offer ได้ แต่มีคนรออนุมัติที่เติม Gap ได้ | `WAITING_APPROVAL` (T7) รอผู้อนุมัติตัดสินก่อน |
| Gap ยังไม่ถูกปิด ไม่เหลือผู้สมัครที่ส่ง Offer ได้ ไม่มีคนรออนุมัติที่เติม Gap ได้ แต่มี Offer ที่ถูกพักและยังไม่หมดเวลา | `WAITING_RESPONSE` รอผลของเคสที่ผู้สมัครไปรับ หรือรอ Offer หมดเวลา |
| Gap ยังไม่ถูกปิด ไม่เหลือผู้สมัครที่ส่ง Offer ได้ ไม่มีคนรออนุมัติที่เติม Gap ได้ และไม่มี Offer ที่ถูกพัก | `MANUAL_HANDOFF` |

* `SAFETY_VALIDATION` ไม่ใช่สถานะที่เคสหยุดรอ เป็นการตรวจรายคนที่ทำทันทีเมื่อผู้สมัครตอบรับ
* ไม่รอทั้งชุด: คนที่ตอบรับเข้า Safety และขออนุมัติทันที
* คนที่ Safety ไม่ผ่านหรือไม่ได้รับอนุมัติถือว่าหลุด ไม่นับ Offer ของเขาเป็น `CANCELLED` แล้วนับใหม่ เคสถอยจาก `WAITING_APPROVAL` ไป `WAITING_RESPONSE` หรือ `OUTREACH` ได้
* การอนุมัติรายคนไม่ขยับเคสเสมอไป: บันทึกผลของคนนั้น แล้วคำนวณสถานะเคสจากตาราง

**ข. คำตอบอื่นของแบบขนาน**

| # | คำตอบ |
|---|---|
| 24.1 | อนุมัติกดต่อคน หนึ่ง `APPROVAL_REQUEST` ต่อผู้สมัคร |
| 24.3 | คนที่ตอบช้ากด Accept ต่อได้จนกว่า Offer ของเขาจะ Timeout หรือถูกยกเลิก (ข้อ 2.7) |
| 24.4 | จัดเวรทีละคนเมื่อได้รับอนุมัติ ไม่รอครบ |
| 24.5 | ได้คนไม่ครบและไม่เหลือผู้สมัคร: คนที่จัดเวรแล้วอยู่ต่อ เคสไป `MANUAL_HANDOFF` |
| Q25 | ขนาด Wave = จำนวนคนที่ถูกเลือกตามกติกาเติม Target (Q50 ข้อ 8.3) คนหนึ่งคนนับให้ทุก Target ที่เขาตรง จำนวนคนจึงไม่เกินผลรวมของ Target ไม่มีจุดให้ผู้ใช้เลือก |
| Q1 | ไม่อนุมัติ = คนนั้นหลุด Offer เป็น `CANCELLED` นับใหม่ตามตารางข้อ ก (ไม่ใช่ทั้งเคสกลับ `OUTREACH` เสมอ) |
| Q2, Q3, Q5, Q8, Q10, Q12, Q13 | ตามข้อเสนอในข้อ 12 |
| Q7 | Offer ของคนที่ตอบรับแล้วถูกปัดตก (Safety ไม่ผ่าน หรือ Head Nurse ไม่อนุมัติ) เป็น `CANCELLED` |
| Q6 | หน้าเคสบอกเหตุผลที่ผู้สมัครถูกข้าม รหัสเหตุผลอยู่ใน `docs/database-schema.md` หัวข้อ Candidate Skip Reasons |

**ค. ผู้สมัครถือหลาย Offer พร้อมกัน (แทนกฎ "Offer ค้าง" เดิม)**

ผู้สมัครได้รับ Offer จากหลายเคสพร้อมกัน แล้วเลือกเองว่าจะรับอันไหน จำกัดจำนวนด้วย Policy

| เหตุการณ์ | Offer หอ 1 | Offer หอ 2 |
|---|---|---|
| A ได้รับทั้งสอง Offer | รอตอบ กด Accept ได้ | รอตอบ กด Accept ได้ |
| A รับหอ 2 กำลังตรวจหรือรออนุมัติ | ยัง `SENT` แต่กด Accept ไม่ได้ | `ACCEPTED` |
| หอ 2 ไม่อนุมัติ A | กลับมากด Accept ได้ ถ้า Offer ยังใช้ได้ | `CANCELLED` |
| หอ 2 อนุมัติและสร้าง Assignment สำเร็จ | ยกเลิกถ้าขัดกับ Assignment ใหม่ | `ACCEPTED` และมี Assignment |

| เรื่อง | กติกา |
|---|---|
| ตอบรับพร้อมกันสองแท็บ | ล็อกแถว `STAFF` ของผู้สมัครทั้ง Plan ตามลำดับในข้อ 4.3 แล้วตรวจซ้ำก่อนรับ |
| รับหอ 2 แล้วหอ 2 ไม่อนุมัติ | หอ 1 ไม่ต้องส่ง Offer ใหม่ Offer เดิมของหอ 1 กลับมากดได้ |
| เมื่อไหร่ยกเลิก Offer ของหอ 1 | ไม่ยกเลิกตอน A กดรับหอ 2 ยกเลิกหลังหอ 2 จัดเวรให้ A สำเร็จ และเฉพาะ Offer ที่ขัดกับ Assignment ใหม่ |
| "ขัดกัน" | ใช้ Hard Rules ชุดเดียวกัน: เวลาทับ, พักไม่พอ, ชั่วโมงรวมเกิน ไม่ใช่แค่เวลาทับ |
| สิ่งที่ผู้สมัครเห็น | หอ, เวร, เส้นตาย และเหตุผลที่ยกเลิก เส้นตายแสดงได้เมื่อมี `expires_at` คือหลัง PR O |
| จำกัดจำนวน | ตารางใหม่ `OUTREACH_POLICY` |

ตาราง `OUTREACH_POLICY` (Migration ใหม่)

| Field | Type | ความหมาย |
|---|---|---|
| `id` | bigint PK | Policy ID |
| `maximum_concurrent_offers_per_staff` | integer NOT NULL, CHECK > 0 | จำนวน Offer ที่ยังเปิดได้พร้อมกันต่อคน |
| `offer_timeout_seconds` | integer NOT NULL, CHECK > 0 | อายุของ Offer เป็นวินาที Seed = 300 (ข้อ 2.7) |
| `version` | text NOT NULL | รุ่นของ Policy |
| `effective_from` | timestamptz NOT NULL | เวลาเริ่มใช้ |
| `created_at` | timestamptz NOT NULL | เวลาสร้าง |

**ง. คำตอบของคำถามที่ตามมา**

* **Q27** ตอบแล้ว: จัดเวรรายคนทันทีที่ได้รับอนุมัติ ไม่รอครบ ตรงกับ 24.4 และ 24.5
  * ตารางสถานะเคสข้อ ก จึงเขียนแถวแรกว่า "คนที่ได้เข้าเวรแล้ว" ไม่ใช่ "อนุมัติแล้ว" เพราะการจัดเวรเกิดไปแล้วทีละคนตอนอนุมัติ
  * **Q45** ตอบแล้ว ตามข้อเสนอ: การจัดเวรรายคนทำใน Transaction ของการอนุมัติ ไม่เปลี่ยนสถานะเคส พอได้คนครบ เคสผ่าน `EXECUTING` ครั้งเดียวเพื่อปิดงาน (ยกเลิก Offer ที่เหลือ เขียน `CASE_RESOLVED`) แล้วเป็น `RESOLVED` ไม่เพิ่ม Transition ออกจาก `EXECUTING`
* **Q28** ตอบแล้ว ตามข้อเสนอ: เรียงตามเวลาที่ตอบรับ คนที่เกินจำนวนรอเป็นสำรอง (Offer เป็น `ACCEPTED` ยังไม่ตรวจ Safety ยังไม่ขออนุมัติ) ถ้าคนก่อนหน้าหลุด สำรองคนแรกเข้า Safety ต่อ เมื่อเคส `RESOLVED` ยกเลิกทั้ง Offer ที่ยัง `SENT` และของสำรอง
* **Q29** ตอบแล้ว ตามข้อเสนอ: Offer ที่ผู้สมัครกดไม่ได้เพราะรับของเคสอื่นค้างอยู่ ไม่นับเป็น Offer ค้างของเคส เคสส่งชุดถัดไปได้เลย แต่ Offer แบบนี้ (Offer ที่ถูกพัก ข้อ 2.1) ยังกันไม่ให้เคสไป `MANUAL_HANDOFF` ตราบที่ยังไม่หมดเวลา
* **Q30** ตอบแล้ว ตามข้อเสนอ: `maximum_concurrent_offers_per_staff` นับ `SENT` + `ACCEPTED` ของเคสที่ยังเดิน Seed = 3 รหัสตอนข้ามคนที่เต็มเพดาน = `OFFER_LIMIT_REACHED` แทน `HAS_OPEN_OFFER`
* **Q31** ตอบแล้ว ตามข้อเสนอ: คงค่า `SAFETY_VALIDATION` ใน Enum แต่เคสไม่หยุดที่สถานะนี้
* **Q46** ตอบแล้ว: เป้าหมายของเคสคือทำให้ Gap หมด ไม่ใช่ได้คนครบจำนวน
  * ตารางสถานะเคสข้อ ก จึงเขียนด้วย Gap ที่เหลือ ไม่ใช่จำนวนคน: เคส `RESOLVED` เมื่อคนที่ได้เข้าเวรแล้วทำให้ Gap ของจำนวนคน, Role และ Skill เป็น 0 ทุกตัว เคสอยู่ `WAITING_APPROVAL` เมื่อคนที่ได้เข้าเวรแล้วรวมกับคนที่รออนุมัติปิด Gap ได้ครบ
  * สำรอง (Q28) จึงหมายถึงคนที่ตอบรับหลังจาก Gap ถูกปิดครบแล้วด้วยคนที่ตอบรับก่อนหน้า
  * ขนาด Wave อยู่ในข้อ 8.3
* **Q6 ต่อ** ตอบแล้ว: หน้าเคสอ่านเหตุผลที่ข้ามจาก payload ของ Audit (`skipped` ใน `OFFER_SENT` แถวแรกของ Wave หรือใน `MANUAL_HANDOFF`) ไม่เพิ่มคอลัมน์
* **Q26** ถูกแทนด้วย Q43: Event ใหม่ของเวรที่มีเคสเดินอยู่ไม่เพิ่ม Gap บนเคสนั้น รอจนเคสจบแล้วเปิดเคสใหม่ (ข้อ 2.5)
* **Q23** ยกเลิก: ไม่มีการตรวจซ้ำตอนจัดเวร (Q38) อนุมัติแล้วสร้าง Roster ทันที กรณี "ไม่ผ่านตอนจัดเวร" จึงไม่มี ถ้าคนนั้นไม่มาเข้าเวรเป็นเรื่องของ `NO_SHOW` ซึ่งไม่อยู่ในรอบ 1

**จ. ส่วนอื่นของร่าง** เขียนใหม่ตามข้อนี้ครบแล้ว

### 2.7 Timeout ของ Offer (ดึงมาจากรอบ 2)

ตกลงแล้ว (Q56): Offer มี Timeout ในรอบ 1 ส่วนการอนุมัติ**ไม่มี** Timeout หรือ Deadline เคสที่รออนุมัติรอจนผู้อนุมัติตัดสิน

ค่าที่มีอยู่แล้วคือ `OutreachStatus.TIMEOUT` และ Audit Action `OFFER_TIMEOUT` ต้องเพิ่มคอลัมน์สองตัวตามตาราง ตกลงแล้วทั้งตาราง

| หัวข้อ | กติกา |
|---|---|
| ค่าระยะเวลา | คอลัมน์ `OUTREACH_POLICY.offer_timeout_seconds` (integer, NOT NULL, CHECK > 0) Seed = 300 วินาที |
| เวลาหมดอายุของแต่ละ Offer | คอลัมน์ใหม่ `CANDIDATE_OUTREACH.expires_at` ตั้งตอนส่ง = `sent_at` + ค่าใน Policy ไม่เปลี่ยนทีหลัง Offer ใน Wave เดียวกันจึงหมดพร้อมกัน |
| หมดเวลาแล้วยังไม่ตอบ | Offer ที่ยัง `SENT` เป็น `TIMEOUT` เขียน `OFFER_TIMEOUT` หนึ่งแถวต่อ Offer แล้วคำนวณสถานะเคสใหม่ (ไม่มี Offer ค้างแล้ว เคสจึงไป `OUTREACH` ส่ง Wave ถัดไป หรือจบตามข้อ 2.1) |
| ผู้สมัครที่ Timeout | นับว่าเคสนี้ติดต่อไปแล้ว ไม่ส่งซ้ำในเคสเดียวกัน (ข้อ 3.2 ขั้นที่ 4) และ Offer นั้นเลิกนับในเพดานของเขา |
| Offer ที่กดรับไม่ได้เพราะรับของเคสอื่นค้างอยู่ (Q29) | หมดเวลาตามปกติ ไม่หยุดนาฬิกา |
| Offer ที่ตอบรับแล้ว (รวมสำรอง) | ไม่มี Timeout เพราะตอบแล้ว |
| กดตอบหลังหมดเวลา | `409` ไม่เขียน DB `respond` เทียบ `expires_at` กับ `clock.now()` เอง ไม่รอ Job เพราะ Job รันทุก 30 วินาที ช่วงนั้น Offer ที่เลยเวลาแล้วยังเป็น `SENT` การเปลี่ยนเป็น `TIMEOUT` ยังเป็นหน้าที่ของ Job ที่เดียว |
| ใครสั่ง | Service ของ Job ตัวเดียวกับ Merge Gap (ข้อ 2.5) ทุกรอบให้ Backend ปิด Offer ที่หมดเวลา ปุ่มเลื่อน Clock ของ Demo ทำงานเดียวกัน |

* เจ้าของ: คน 3 เพราะเป็นงาน Outreach การต่อเข้ากับ Service ของ Job ทำร่วมกับคน 1 (PR O ข้อ 10)
* ผลต่อ Demo: Clock ของ Demo เป็นตัวเดียวทั้งระบบ เลื่อน Clock เกิน 300 วินาที Offer ที่ยัง `SENT` และส่งไว้ก่อนหน้านั้นจะ `TIMEOUT` ทุกแถว ไม่ว่าเป็นของเคสไหน เรื่องนี้เป็นคนละส่วนกับการปิด Window ซึ่งยังเป็นไปตาม Q43 (Window ปิดเมื่อครบ `merge_window_seconds` และเคสก่อนหน้าของเวรจบแล้ว) Scenario และการสาธิตที่เลื่อน Clock เพื่อปิด Window จึงต้องรู้ว่า Offer ที่ค้างอยู่จะหมดเวลาไปพร้อมกัน


---

## 3. กติกาเลือกผู้สมัครของ Wave (แทน Seam 2 เดิม)

### 3.1 เมื่อไหร่ส่ง Wave

เคสเข้า `OUTREACH` เมื่อ Gap ยังไม่ถูกปิดและเคสไม่มี Offer ค้าง (T1, T4 และครั้งแรกหลัง Solver) Handler `contact_candidate` เป็นที่เดียวที่เลือกคนและส่ง Offer

### 3.2 ขั้นตอนเลือกคน

1. **หา Gap ที่ยังเหลือ** = Gap ของเคส (แถว `STAFFING_GAP` ของเคส) หักด้วยคนที่เข้าเวรแล้ว, คนที่รออนุมัติ และสำรองที่ตอบรับไว้
2. **คิด Target** ของ Skill, Role และจำนวนคนจาก Gap ที่เหลือ: `ceil(gap * 11 / 10)` (ข้อ 8.3)
3. **อ่านผู้สมัคร** จาก Plan ของเคส เรียงตาม `rank` Plan เก็บผู้สมัครทุกคนที่ผ่าน Hard Rules ตอน Solver รัน ไม่ใช่เฉพาะกลุ่มของ Wave แรก (ข้อ 8.3) จึงมีคนเหลือให้ Wave ถัดไป ไม่รัน Solver ใหม่ (Q3, Q37)
4. **ข้ามคนที่ใช้ไม่ได้** และจดเหตุผล
   * เคสนี้ติดต่อไปแล้ว: Offer เป็น `REJECTED`, `CANCELLED`, `TIMEOUT` หรือยัง `SENT` / `ACCEPTED` อยู่ คนกลุ่มนี้ไม่อยู่ใน `skipped` เพราะผลของเขาอยู่ในประวัติ Offer แล้ว
   * ไม่ผ่าน Hard Rules ณ ตอนนี้ (ตัวตรวจเดียวกับ Solver และ Safety ข้อ 7) รหัสเหตุผล = รหัสของกฎ
   * ถือ Offer ครบเพดานแล้ว รหัส `OFFER_LIMIT_REACHED` (ข้อ 3.3)
5. **เลือกคนของ Wave**
   * Wave แรก: ใช้กลุ่มที่ Solver เลือก คือคนใน Plan ที่มีแถว `CANDIDATE_ITEM_TARGET` อยู่แล้ว ไม่เลือกใหม่จากทั้ง Plan ถ้าคนในกลุ่มถูกข้ามในขั้นที่ 4 Target ที่เขาถืออยู่จะว่าง ให้เติมเฉพาะ Target ที่ว่างนั้นจากคนที่เหลือใน Plan ตามลำดับในข้อ 8.3
   * Wave ถัดไป: เติม Target จากคนที่เหลือใน Plan ตามลำดับในข้อ 8.3 จนทุก Target เป็น 0 หรือไม่เหลือผู้สมัคร
   * คนที่ถูกเลือกโดยขั้นนี้ (ไม่ใช่โดย Solver) ต้องได้แถว `CANDIDATE_ITEM_TARGET` ก่อนส่ง Offer Safety จึงมีแถวอ่านทุกคน ไม่ว่าอยู่ Wave ไหน
6. เลือกได้อย่างน้อยหนึ่งคน → ส่ง Offer ทุกคนพร้อมกัน เคสไป `WAITING_RESPONSE` เลือกไม่ได้เลย ตรวจตามลำดับนี้
   * มีคนรออนุมัติที่เติม Gap ได้ → เคสไป `WAITING_APPROVAL` (T7)
   * มี Offer ที่ถูกพักและยังไม่เลย `expires_at` → เคสไป `WAITING_RESPONSE` รอผลของเคสที่ผู้สมัครไปรับ หรือรอ Offer หมดเวลา (ข้อ 2.1)
   * ไม่มีทั้งสองอย่าง → `MANUAL_HANDOFF` (T5)

### 3.3 เพดาน Offer ต่อคน (แทนกฎ "Offer ค้าง" เดิม)

แก้ตามคำตอบ Q30 และ Q52 กฎเดิมของ Solver ("กฎข้อ 4": มี Offer `SENT` ที่ไหนก็ได้ หรือ `ACCEPTED` บนเคสที่ยังเดิน = ใช้คนนั้นไม่ได้) และรหัส `HAS_OPEN_OFFER` เลิกใช้

| หัวข้อ | กติกา |
|---|---|
| กติกาใหม่ | ผู้สมัครถือ Offer ได้พร้อมกันไม่เกิน `OUTREACH_POLICY.maximum_concurrent_offers_per_staff` (Seed = 3) |
| นับอะไร | Offer ของผู้สมัครที่เป็น `SENT` หรือ `ACCEPTED` บนเคสที่ยังเดินอยู่ |
| รหัสตอนข้ามคน | `OFFER_LIMIT_REACHED` |
| อยู่ที่ไหน | ฟังก์ชัน Public ในชั้น Service (ที่เดิมตกลงไว้คือ `availability_service`) รับ `db` กับ List ของ `staff_id` คืน Set ของคนที่เต็มเพดาน ไม่อยู่ใน `domain/constraints/` เพราะต้อง Query `CANDIDATE_OUTREACH` |
| ใครทำ | คน 3 ใน PR 1c (งาน Outreach เป็นของคน 3): ตาราง `OUTREACH_POLICY`, Seed และฟังก์ชันนี้ ส่วนการเปลี่ยน Solver ให้เรียกฟังก์ชันนี้และลบ `_staff_with_open_offers()` ออกจาก `optimization_service` เป็นของคน 2 ใน PR 2a เพราะเป็นไฟล์ของ Solver |
| ใครเรียก | Solver (ตอนสร้าง Plan) และ `contact_candidate` (ขั้นที่ 4 ของข้อ 3.2) |
| Safety ไม่เรียก | ผู้สมัครที่กำลังถูกตรวจมี Offer `ACCEPTED` ของเคสตัวเองอยู่ กติกานี้จึงไม่อยู่ในรายการรหัสของข้อ 7.2 |

กติกาอื่นของการส่ง Wave

* **Lock:** ตอนเลือกคนของ Wave ล็อกแถว `STAFF` ของผู้สมัครทั้ง Plan แบบเดียวกับ Solver (`FOR NO KEY UPDATE` เรียงตาม `id`) ไม่งั้นสองเคสที่เลือกคนพร้อมกันจะนับเพดานของคนเดียวกันผิด
* **คนที่ถูกข้ามต้องไม่หายเงียบ:** ใส่ `skipped` ใน payload ของ `OFFER_SENT` แถวแรกของ Wave หรือของ `MANUAL_HANDOFF` เมื่อไม่เหลือใคร เป็น List ของ `{staff_id, reason}` โดย `reason` เป็นรหัส (Q5) หน้าเคสอ่านเหตุผลจาก payload นี้ (Q6)
* **ผู้สมัครที่รับของเคสอื่นอยู่:** Offer ของเคสนี้ยัง `SENT` แต่กดรับไม่ได้ และไม่นับเป็น Offer ค้างของเคสนี้ (Q29) เคสจึงส่ง Wave ถัดไปได้โดยไม่รอเขา ถ้าเคสไม่เหลือผู้สมัครให้ส่งแล้ว เคสรอ Offer นี้ที่ `WAITING_RESPONSE` ไม่ไป `MANUAL_HANDOFF` จนกว่า Offer จะหมดเวลาหรือถูกยกเลิก (ข้อ 2.1)

### 3.4 คำถามเดิมของข้อนี้

* **Q21** (เคสหนึ่งรับกี่คน) ถูกแทน: เคสรับได้หลายคน เป้าหมายคือ Gap หมด (Q24, Q46)
* **Q22** (ติดต่อซ้ำคนที่ Offer ถูกยกเลิก) ถูกแทน: การตอบรับของคนหนึ่งไม่ยกเลิก Offer ของคนอื่นแล้ว Offer ถูกยกเลิกตอนเคสจบ จึงไม่มีการติดต่อซ้ำในเคสเดียวกัน

---


## 4. แถวที่แต่ละเส้นทางเขียน

### 4.1 สิ่งที่เปลี่ยนจาก Skeleton

* Seam 4 เดิม (`get_accepted_outreach`) ต้องการ Offer `ACCEPTED` ของเคส **หนึ่งแถวพอดี** ใช้ไม่ได้แล้ว เพราะเคสมีคนตอบรับได้หลายคน Safety รับ `outreach_id` ของคนที่เพิ่งตอบรับแทนการค้นจากเคส
* เคสหนึ่งมี `APPROVAL_REQUEST` ที่ค้างได้หลายแถว หนึ่งแถวต่อผู้สมัคร (24.1)
* คนที่ตอบรับแล้วหลุด Offer เป็น `CANCELLED` (Q7) ฟังก์ชันเดียวใน `outreach_service` เป็นคนตั้ง Safety กับ Approval เรียกใช้ (Q8)

### 4.2 ตารางการเขียน

| เหตุการณ์ | ตาราง | ค่าที่เขียน | ใครเขียน |
|---|---|---|---|
| ส่ง Wave | `CANDIDATE_OUTREACH` (แถวใหม่ หนึ่งแถวต่อคน) | `status = SENT`, `sent_at = clock.now()` ค่าเดียวกันทั้ง Wave | `outreach_service.send_offer()` (ตอนนี้รับอันดับ 1 คนเดียว ต้องแก้ให้รับหลาย Item) |
| ปฏิเสธ | `CANDIDATE_OUTREACH` | `status = REJECTED`, `response_at = clock.now()` | `outreach_service.record_response()` |
| ตอบรับ ตอน Gap ยังไม่ถูกปิดด้วยคนที่ตอบรับก่อนหน้า | `CANDIDATE_OUTREACH` | `status = ACCEPTED`, `response_at` | `record_response()` |
| | `SAFETY_VALIDATION` | หนึ่งแถวของคนนี้ ใน Transaction เดียวกับการตอบรับ (ข้อ 7.4) | `safety_service` |
| | `APPROVAL_REQUEST` | แถวใหม่ที่ค้าง เมื่อ Safety ผ่าน | `approval_service` |
| | `CANDIDATE_OUTREACH` | `status = CANCELLED` เมื่อ Safety ไม่ผ่าน ไม่สร้าง `APPROVAL_REQUEST` | `outreach_service` (Q8) |
| ตอบรับ ตอน Gap ถูกปิดครบแล้ว (สำรอง) | `CANDIDATE_OUTREACH` | `status = ACCEPTED`, `response_at` อย่างเดียว ยังไม่ตรวจ Safety (Q28) | `record_response()` |
| ตอบรับ แต่ผู้ตอบรับของเคสอื่นค้างอยู่ | ไม่เขียน | ตอบ `409` (Q39) | |
| อนุมัติ | `APPROVAL_REQUEST` | `approver_id`, `is_approved = true`, `is_pending = false`, `decided_at` | `approval_service.decide()` |
| | `ROSTER_ASSIGNMENT` | แถว `REPLACEMENT` ของคนนั้น ใน Transaction เดียวกัน ไม่ตรวจซ้ำ (Q27, Q38) | `roster_service` |
| | `CANDIDATE_OUTREACH` ของคนนั้นในเคสอื่น | `status = CANCELLED` เฉพาะ Offer ที่ขัดกับเวรใหม่ตาม Hard Rules (ข้อ 2.6 ค) | `outreach_service` |
| ไม่อนุมัติ | `APPROVAL_REQUEST` | `approver_id`, `is_approved = false`, `is_pending = false`, `reason`, `decided_at` | `approval_service.decide()` |
| | `CANDIDATE_OUTREACH` (ของคนที่ไม่ได้รับอนุมัติ) | `status = CANCELLED` | `outreach_service` (Q8) |
| | สำรองคนแรก (ถ้ามี) | เข้า Safety ต่อ เขียนแบบเดียวกับแถว "ตอบรับ" | `safety_service` |
| Gap ถูกปิด (เคสผ่าน `EXECUTING`) | `CANDIDATE_OUTREACH` ของเคสที่ยัง `SENT` และของสำรอง | `status = CANCELLED` | Handler ของ `EXECUTING` ผ่าน `outreach_service` |
| Offer หมดเวลา | `CANDIDATE_OUTREACH` ที่ยัง `SENT` และเลย `expires_at` | `status = TIMEOUT`, `response_at` คงเป็น NULL (ข้อ 2.7) | `outreach_service` เรียกจาก Job |
| เคสเข้า `MANUAL_HANDOFF` (T5) | `CANDIDATE_OUTREACH` ของเคสที่ยัง `SENT` ทุกแถว ตอนนี้เหลือได้แต่ Offer ที่เลย `expires_at` แล้วแต่ Job ยังไม่ได้เปลี่ยนเป็น `TIMEOUT` เพราะ Offer ที่ถูกพักและยังไม่หมดเวลากันไม่ให้เคสมาถึงจุดนี้ (ข้อ 2.1) | `status = CANCELLED` เพราะเคสไม่มีเส้นออกจาก `MANUAL_HANDOFF` | `contact_candidate` ผ่าน `outreach_service` |
| Solver ไม่ได้ใครเลย (T6) | ไม่มีแถวใหม่นอกจาก Audit | | Handler |

### 4.3 ลำดับ Lock

ลำดับเดิมทั้งระบบ: `SHIFT` / `ROSTER_ASSIGNMENT` → `APPROVAL_REQUEST` หรือ `CANDIDATE_OUTREACH` → เคส → `STAFF`

* **ตอบ Offer:** ล็อก Offer ที่ยังไม่จบของเคสทุกแถว เรียงตาม `id` (รวมของผู้ตอบเอง) → เคส → แถว `STAFF` ของผู้สมัครทั้ง Plan ของเคส ใน Query เดียวที่เรียงตาม `id` แล้วตรวจซ้ำว่าผู้ตอบไม่ได้รับของเคสอื่นค้างอยู่ (ข้อ 2.6 ค) ผู้สมัครที่ตอบรับสองเคสพร้อมกันจึงได้ผลสำเร็จเคสเดียว
  * เหตุผลที่ล็อก Offer ทุกแถวของเคส: คำตอบนี้อาจทำให้เคสเข้า `MANUAL_HANDOFF` ซึ่งยกเลิก Offer ที่ยัง `SENT` ของคนอื่น
  * เหตุผลที่ล็อก `STAFF` ทั้ง Plan ไม่ใช่แค่ของผู้ตอบ: คำตอบนี้อาจทำให้เคสส่ง Wave ถัดไปใน Transaction เดียวกัน ซึ่งต้องล็อก `STAFF` ทั้ง Plan ถ้าถือแถวของผู้ตอบไว้ก่อนแล้วค่อยล็อกที่เหลือ สองเคสที่ใช้ผู้สมัครชุดเดียวกันจะค้างกันได้ เช่น เคส A ถือแถวของ 202 แล้วรอ 201 ส่วนเคส B ถือแถวของ 201 แล้วรอ 202
* **ตัดสินอนุมัติ:** การอนุมัติสร้าง Roster อาจเป็นคนสุดท้ายที่ทำให้ Gap ถูกปิด และต้องยกเลิก Offer ของผู้สมัครคนนั้นในเคสอื่นที่ขัดกับเวรใหม่ จึงล็อกตามลำดับ: `SHIFT` → `APPROVAL_REQUEST` → Offer ที่ยังไม่จบของเคสนี้ทุกแถว **รวมกับ** Offer ที่ยังไม่จบของผู้สมัครคนนั้นในเคสอื่น ล็อกใน Query เดียว เรียงตาม `id` → เคส → `STAFF` ของผู้สมัครทั้ง Plan ของเคส ใน Query เดียวที่เรียงตาม `id` เหตุผลที่ต้องล็อก Offer ก่อนเคสและก่อน `STAFF`: การตอบ Offer ล็อก Offer ก่อนแล้วจึงล็อก `STAFF` ถ้าการอนุมัติถือ `STAFF` ก่อนแล้วไปรอ Offer จะค้างกับผู้สมัครที่กดตอบ Offer นั้นพอดี หลังล็อกครบจึงตรวจว่า Offer ไหนขัดกับเวรใหม่ แล้วยกเลิกเฉพาะแถวนั้น
* **ลำดับย่อยในชั้นเดียวกัน:** `APPROVAL_REQUEST` ก่อน `CANDIDATE_OUTREACH` การตอบ Offer สร้าง `APPROVAL_REQUEST` แถวใหม่ได้ แต่ไม่ล็อกแถวที่มีอยู่ จึงไม่สวนกัน
* **Offer หมดเวลา (Job):** ล็อก Offer ที่ยังไม่จบของเคสทุกแถว เรียงตาม `id` → เคส → `STAFF` ของผู้สมัครทั้ง Plan ของเคส แบบเดียวกับการตอบ Offer เพราะเคสอาจส่ง Wave ถัดไปหรือเข้า `MANUAL_HANDOFF` ได้เหมือนกัน
* **กติการวม:** ทุกเส้นทางที่เรียก `recompute()` ล็อกตามลำดับเดียวกัน: Offer ที่ยังไม่จบของเคสทุกแถว → เคส → `STAFF` ของผู้สมัครทั้ง Plan แถวของตารางเดียวกันที่ Transaction หนึ่งจะล็อก ต้องล็อกใน Query เดียวที่เรียงตาม `id` ห้ามล็อกบางแถวก่อนแล้วมาล็อกเพิ่มทีหลัง
* **เคสอื่นที่ได้รับผลกระทบ (ข้อ 2.3):** `recompute()` ของเคสอื่นทำหลัง Commit ใน Transaction ของตัวเอง จึงเริ่มล็อกจาก Offer ของเคสนั้นตามลำดับปกติ ไม่ถือ Lock ของเคสแรกค้างไว้
* **Safety ไม่ผ่าน:** ตั้ง Offer ของผู้ตอบเป็น `CANCELLED` ใน Transaction ของการตอบรับ ซึ่งถือ Lock ของแถวนั้นอยู่แล้ว
* **เลือกคนของ Wave:** `contact_candidate` ล็อกแถว `STAFF` ของทั้ง Plan เรียงตาม `id` (ข้อ 3.3) ถ้าถูกเรียกต่อจากการตอบ Offer, การอนุมัติ หรือ Job แถวพวกนี้ถูกล็อกไว้แล้วตั้งแต่ต้น Transaction จึงไม่มีการรอเพิ่ม
* **ปิด Window (ข้อ 2.5):** ล็อก `SHIFT` ก่อน แล้วจึงแก้ Roster ตรงลำดับเดิม
* ลำดับ Lock ในหัวข้อนี้ตกลงแล้ว แต่ยังเป็นการวิเคราะห์ ไม่มี Test พิสูจน์ ต้องมี Test สอง Connection อย่างน้อยสี่กรณี: สองคนตอบรับเคสเดียวกันพร้อมกัน, คนเดียวตอบรับสองเคสพร้อมกัน, ตอบรับกับอนุมัติคนสุดท้ายพร้อมกัน, สองเคสที่ใช้ผู้สมัครชุดเดียวกันตอบ Offer แล้วส่ง Wave ถัดไปพร้อมกัน (ข้อ 13)

---


## 5. Audit

### 5.1 Action ที่ใช้

สี่ตัวนี้มีใน `AuditAction` แล้ว Action ที่ต้องเพิ่มใน Enum มีสามตัวของ Event ชนิดใหม่ (ข้อ 2.5 Q40): `ASSIGNMENT_CANCELLED`, `PATIENT_COUNT_UPDATED`, `REQUIREMENT_UPDATED`

| Action | ใครเขียน | Actor | entity_type | payload ขั้นต่ำ |
|---|---|---|---|---|
| `OFFER_REJECTED` | `outreach_service` | user (ผู้สมัคร) | CANDIDATE_OUTREACH | `outreach_id`, `staff_id` |
| `SAFETY_FAILED` | `validate_safety` | `safety_rule_engine` | SAFETY_VALIDATION | `validation_id`, `staff_id`, `outreach_id`, `failed_rules` (List ของรหัส) |
| `APPROVAL_REJECTED` | `approval_service` | user (ผู้อนุมัติ) | APPROVAL_REQUEST | `approval_id`, `staff_id` (ผู้สมัคร), `outreach_id`, `reason` |
| `MANUAL_HANDOFF` | Handler ที่หยุดเคส (`contact_candidate` หรือ `optimize`) | Actor ของ Handler นั้น | STAFFING_CASES | `reason` (รหัส), `stopped_at` (State ที่หยุด), `cancelled_outreach_ids` (Offer ที่ยัง `SENT` ซึ่งถูกยกเลิกตอนเคสหยุด ว่างได้) |

รหัส `reason` ของ `MANUAL_HANDOFF`: `NO_CANDIDATE_LEFT` (T5), `NO_FEASIBLE_PLAN` (T6)

Action เดิมที่ payload เปลี่ยนเพราะ Wave

* `OFFER_SENT`: ยังเป็นหนึ่งแถวต่อคน เรียงตาม `rank` payload เดิม (`outreach_id`, `staff_id`, `channel`) เพิ่ม `wave` (เลข Wave ของเคส เริ่มที่ 1) แถวแรกของ Wave มี `skipped` (Q5)
* `OFFER_ACCEPTED`: ไม่เพิ่ม `cancelled_outreach_ids` เพราะการตอบรับไม่ยกเลิก Offer ของคนอื่นทันที (ข้อ 2.6)
* `CASE_RESOLVED`: เพิ่ม `cancelled_outreach_ids` = Offer ของเคสที่ถูกยกเลิกตอนได้คนครบ ทั้งที่ยัง `SENT` และของสำรอง (Q28)
* `ASSIGNMENT_CREATED`: เพิ่ม `cancelled_outreach_ids` = Offer ของเคสอื่นที่ขัดกับเวรใหม่ของผู้สมัคร (ข้อ 2.6 ค) ว่างได้
* `WORKFLOW_FAILED`: ไม่เปลี่ยนความหมาย ยังแปลว่าเคส `FAILED` ตาม D11 เท่านั้น ไม่มีกรณีจัดเวรรายคนไม่ผ่าน เพราะไม่มีการตรวจซ้ำตอนจัดเวร (Q38)

### 5.2 กติกา

* `CASE_STATUS_CHANGED` ยังเขียนโดย Orchestrator เท่านั้น ทุกเส้นใหม่จะมีแถวนี้เอง
* ไม่เพิ่ม Action สำหรับการตั้ง Offer เป็น `CANCELLED` ให้ `outreach_id` ใน payload ของ `SAFETY_FAILED` / `APPROVAL_REJECTED` บอกแทน ส่วน Offer ที่ถูกยกเลิกเพราะเคสได้คนครบ, เพราะเคสเข้า `MANUAL_HANDOFF` หรือเพราะขัดกับเวรใหม่ของผู้สมัคร ให้ `cancelled_outreach_ids` ของ Action ในจังหวะนั้นบอก (ข้อ 5.1, Q28)
* `payload` ยังห้ามมีข้อมูลผู้ป่วยรายบุคคลและ `password_hash` `reason` ของการไม่อนุมัติเป็นข้อความที่ผู้อนุมัติพิมพ์ ตอนนี้ `APPROVAL_APPROVED` ก็เก็บ `reason` อยู่แล้ว คงแบบเดียวกัน
* `GOLDEN_PATH_AUDIT_ACTIONS` **เปลี่ยน**: Golden Case ขาดจำนวนคน 1 และขาด Role RN 1 Target = จำนวนคน 2, RN 2 ผู้สมัครทุกคนเป็น RN คนหนึ่งคนจึงนับให้ทั้งสอง Target Wave แรก = 201, 202 มี `OFFER_SENT` สองแถว (จำลองกติกาเติม Target ด้วยโค้ดแล้ว) E2E เทียบลำดับแบบตรงตัวทุกแถว จึงต้องแก้ค่าคงที่และ E2E ใน PR เดียวกับที่เปิด Wave (PR 2b) Merge Gap ไม่เปลี่ยนค่าคงที่นี้ เพราะเวรใน Golden Case ใช้ Window = 0

### 5.3 ลำดับ Audit ที่คาดหวังของแต่ละกรณี (ไม่นับ `CASE_STATUS_CHANGED`)

เขียนใหม่ตาม Flow ปัจจุบัน: Window อยู่ก่อนเคส (ข้อ 2.5) และเคสรับหลายคนแบบขนาน (ข้อ 2.6) ใช้เป็นเกณฑ์ของ Integration Test

วิธีอ่าน

* ลำดับแบ่งเป็นสองช่วง **ช่วงต้น** ตั้งแต่รับ Event ถึงได้ Gap และ **ช่วงหาคน** ตั้งแต่ Solver ถึงเคสจบ เคสหนึ่งเคส = ช่วงต้นหนึ่งกรณี ต่อด้วยช่วงหาคนหนึ่งกรณี
* ลำดับของผู้สมัครคนเดียวกันตายตัว: `OFFER_SENT` → `OFFER_ACCEPTED` → `SAFETY_PASSED` → `APPROVAL_REQUESTED` → `APPROVAL_APPROVED` → `ASSIGNMENT_CREATED`
* ลำดับข้ามคนขึ้นกับว่าใครกดก่อน ลำดับข้างล่างคือลำดับเมื่อ Test กดตามที่เขียน
* ขนาด Wave ตามกติกาเติม Target ข้อ 8.3 Golden Case: Target = จำนวนคน 2, RN 2 ได้ Wave แรก 2 คน คือ 201 กับ 202
* การตอบรับของคนหนึ่ง**ไม่**ยกเลิก Offer ของคนอื่นทันที (ข้อ 2.6) Offer ที่เหลือถูกยกเลิกตอนเคส `RESOLVED` และรายการอยู่ใน `cancelled_outreach_ids` ของ `CASE_RESOLVED` (Q28)
* จัดเวรรายคน: `ASSIGNMENT_CREATED` ของแต่ละคนตามหลัง `APPROVAL_APPROVED` ของคนนั้นทันที (Q27)

#### ช่วงต้น: รับ Event ถึงได้ Gap

| กรณี | เขียนตอนรับ Event (PART A) | เขียนตอน Window ปิด (PART B) |
|---|---|---|
| ต1. Window = 0 เวรขาดคน | `EVENT_RECEIVED` | `UNAVAILABILITY_CREATED`, `CASE_OPENED`, `GAP_ASSESSED` อยู่ใน Request เดียวกับ PART A ลำดับที่เห็นเหมือนวันนี้ |
| ต2. Window = 0 ไม่ผ่าน Threshold | `EVENT_RECEIVED` | `UNAVAILABILITY_CREATED`, `EVENT_IGNORED` ไม่มีเคส เหมือนวันนี้ |
| ต3. Window > 0 มี 2 Event มีตัวที่ผ่าน Threshold และ Gap สุดท้ายไม่เป็น 0 | `EVENT_RECEIVED` หนึ่งแถวต่อ Event (คนละ Request) | `UNAVAILABILITY_CREATED` หนึ่งแถวต่อ Event ตามลำดับ Event แล้ว `CASE_OPENED` หนึ่งแถว และ `GAP_ASSESSED` หนึ่งแถวท้ายสุด |
| ต4. Window > 0 ไม่มี Event ไหนผ่าน Threshold | `EVENT_RECEIVED` หนึ่งแถวต่อ Event | `UNAVAILABILITY_CREATED` หนึ่งแถวต่อ Event แล้ว `EVENT_IGNORED` หนึ่งแถวต่อ Event ไม่มีเคส |
| ต5. Window > 0 มี Event ที่ผ่าน Threshold แต่ Gap สุดท้ายเป็น 0 | `EVENT_RECEIVED` หนึ่งแถวต่อ Event | Action ของแต่ละ Event ตามลำดับ (เช่น `PATIENT_COUNT_UPDATED` สองแถว) แล้ว `EVENT_IGNORED` หนึ่งแถวต่อ Event ไม่มีเคส |

* ต3: `EVENT_RECEIVED` และ `UNAVAILABILITY_CREATED` ถูกเขียนตอนยังไม่มีเคส แต่มี `event_id` จึงขึ้น Timeline ของเคสหลัง Window ปิด และอยู่ก่อน `CASE_OPENED` ทุกแถว (Q33) ไม่มี Action เพิ่ม
* ต4 กับ ต5: `EVENT_IGNORED` เกิดได้สองทาง คือไม่มี Event ไหนผ่าน Threshold (ต4, Q32) หรือมีตัวที่ผ่านแต่ Gap ที่คิดจากข้อมูลสุดท้ายเป็น 0 ทุกตัว (ต5) payload ของ `EVENT_IGNORED` บอกว่าเป็นทางไหน
* payload ของ `CASE_OPENED` ยังมี `event_id` ตัวเดียว คือ Event ตัวแรกที่ผ่าน Threshold ไม่เปลี่ยนเป็น List รายการ Event ครบทุกตัวของเคสอ่านจาก `STAFFING_EVENTS.case_id` และ Case API ตอบเป็น `event_ids` (Q36)
* ทุกกรณี: `EVENT_RECEIVED` กับ `UNAVAILABILITY_CREATED` มี `event_id` ไม่มี `case_id` (Q33) ขึ้น Timeline ของเคสผ่าน `event_id` เรียงตาม `id` ของ Audit
* ตารางนี้เขียนด้วย `STAFF_UNAVAILABLE` Event อีกสามชนิดเขียน Action ของตัวเองแทน `UNAVAILABILITY_CREATED` ในตำแหน่งเดียวกัน: `ASSIGNMENT_CANCELLED`, `PATIENT_COUNT_UPDATED`, `REQUIREMENT_UPDATED` (ข้อ 2.5 Q40)
* `UNAVAILABILITY_CREATED` อยู่คอลัมน์ขวาทุกกรณี เพราะ Update table ทำตอน Window ปิด (Q41) ผลคือใน ต3 ลำดับตาม `id` เป็น `EVENT_RECEIVED` ทุกตัวก่อน แล้วจึงเป็นแถวของ PART B ตามลำดับในตาราง ไม่สลับเป็นคู่กับ `EVENT_RECEIVED`
* ต3: Event ที่ไม่ผ่าน Threshold แต่อยู่ Window เดียวกับตัวที่ผ่าน เป็น `PROCESSED` และ Link เข้าเคส ไม่มี `EVENT_IGNORED` (Q42)
* ไม่มีกรณี Event เข้าเคสเดิม: Event ของเวรที่มีเคสเดินอยู่รอเป็น `RECEIVED` จนเคสนั้นจบ แล้วเดินตาม ต3, ต4 หรือ ต5 (Q43)
* Event ที่ Update table ไม่ได้ (Q44): Event ตัวนั้นได้ `EVENT_IGNORED` พร้อมเหตุผลใน payload ไม่มี `UNAVAILABILITY_CREATED`

#### ช่วงหาคน: เคสขาด 1 คน (Golden Case)

Wave แรก = 201, 202 ผู้สมัครทั้งหมดมี 201, 202, 203

**Golden Path. 201 รับ, อนุมัติ**
`SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_ACCEPTED` (201), `SAFETY_PASSED` (201), `APPROVAL_REQUESTED` (201), `APPROVAL_APPROVED` (201), `ASSIGNMENT_CREATED` (201), `CASE_RESOLVED`
Offer ของ 202 ยัง `SENT` จนเคส `RESOLVED` แล้วเป็น `CANCELLED` (อยู่ใน `cancelled_outreach_ids` ของ `CASE_RESOLVED`)
ลำดับเต็มของ Golden Path = ต1 ต่อด้วยบรรทัดนี้ รวม 13 แถว ต่างจากวันนี้ที่ `OFFER_SENT` มีสองแถว

**ก. 201 ปฏิเสธ, 202 รับ, อนุมัติ**
`SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_REJECTED` (201), `OFFER_ACCEPTED` (202), `SAFETY_PASSED` (202), `APPROVAL_REQUESTED` (202), `APPROVAL_APPROVED` (202), `ASSIGNMENT_CREATED` (202), `CASE_RESOLVED`
ไม่มี `OFFER_SENT` เพิ่มหลัง 201 ปฏิเสธ เพราะ Offer ของ 202 ยังค้าง

**ข. 201 รับ, Safety ไม่ผ่าน, 202 รับ, อนุมัติ**
`SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_ACCEPTED` (201), `SAFETY_FAILED` (201), `OFFER_ACCEPTED` (202), `SAFETY_PASSED` (202), `APPROVAL_REQUESTED` (202), `APPROVAL_APPROVED` (202), `ASSIGNMENT_CREATED` (202), `CASE_RESOLVED`
201 หลุด Offer ของ 201 เป็น `CANCELLED` ไม่มี Wave 2 เพราะ Offer ของ 202 ยังค้างให้กดรับได้

**ค. 201 รับ, ผู้อนุมัติไม่อนุมัติ, 202 รับ, อนุมัติ**
`SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_ACCEPTED` (201), `SAFETY_PASSED` (201), `APPROVAL_REQUESTED` (201), `APPROVAL_REJECTED` (201), `OFFER_ACCEPTED` (202), `SAFETY_PASSED` (202), `APPROVAL_REQUESTED` (202), `APPROVAL_APPROVED` (202), `ASSIGNMENT_CREATED` (202), `CASE_RESOLVED`
เคสอยู่ `WAITING_APPROVAL` ตอนรอผลของ 201 แล้วถอยไป `WAITING_RESPONSE` เมื่อ 201 ไม่ได้รับอนุมัติ

**ง. ทุกคนปฏิเสธ**
`SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_REJECTED` (201), `OFFER_REJECTED` (202), `OFFER_SENT` (203, Wave 2), `OFFER_REJECTED` (203), `MANUAL_HANDOFF` (`NO_CANDIDATE_LEFT`)
Wave 2 มี Target เท่า Wave แรก แต่เหลือผู้สมัครคนเดียว

**จ2. Offer หมดเวลาทั้ง Wave แล้ว 203 รับ, อนุมัติ**
`SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_TIMEOUT` (201), `OFFER_TIMEOUT` (202), `OFFER_SENT` (203, Wave 2), `OFFER_ACCEPTED` (203), `SAFETY_PASSED` (203), `APPROVAL_REQUESTED` (203), `APPROVAL_APPROVED` (203), `ASSIGNMENT_CREATED` (203), `CASE_RESOLVED`
Offer ของ 201 กับ 202 เป็น `TIMEOUT` ตามข้อ 2.7 เคสไม่มี Offer ค้างจึงส่ง Wave 2

**จ. Solver ไม่ได้ใครเลย**
`SOLVER_EXECUTED`, `MANUAL_HANDOFF` (`NO_FEASIBLE_PLAN`) มี `SOLVER_EXECUTED` ก่อนตาม Q12

**ฉ. 201 กับ 202 รับทั้งคู่ (ตอบรับหลัง Gap ถูกปิดครบแล้ว)**
`SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_ACCEPTED` (201), `SAFETY_PASSED` (201), `APPROVAL_REQUESTED` (201), `OFFER_ACCEPTED` (202), `APPROVAL_APPROVED` (201), `ASSIGNMENT_CREATED` (201), `CASE_RESOLVED`
202 ตอบรับทีหลังจึงเป็นสำรอง ไม่มี `SAFETY_PASSED` และ `APPROVAL_REQUESTED` ของ 202 Offer ของ 202 เป็น `CANCELLED` ตอนเคส `RESOLVED` (Q28) ถ้า 201 ไม่ได้รับอนุมัติ 202 จึงเข้า Safety ต่อ

#### ช่วงหาคน: เคสที่ต้องใช้มากกว่า 1 คน (Scenario ของการ Merge)

เวรขาดจำนวนคน 2 ทุกคนเป็น RN: Target = จำนวนคน 3 Wave แรก = 201, 202, 203

**ช. 201 กับ 202 รับ, อนุมัติทั้งคู่ Gap หมดเมื่อได้ทั้งสองคน**
`SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_SENT` (203), `OFFER_ACCEPTED` (201), `SAFETY_PASSED` (201), `APPROVAL_REQUESTED` (201), `OFFER_ACCEPTED` (202), `SAFETY_PASSED` (202), `APPROVAL_REQUESTED` (202), `APPROVAL_APPROVED` (201), `ASSIGNMENT_CREATED` (201), `APPROVAL_APPROVED` (202), `ASSIGNMENT_CREATED` (202), `CASE_RESOLVED`
201 ได้เข้าเวรทันทีที่ได้รับอนุมัติ ไม่รอ 202 (Q27)

**ซ. Gap ไม่หมด: 201 รับและได้รับอนุมัติ, 202 กับ 203 ปฏิเสธ, ไม่เหลือผู้สมัคร**
`SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_SENT` (203), `OFFER_ACCEPTED` (201), `SAFETY_PASSED` (201), `APPROVAL_REQUESTED` (201), `APPROVAL_APPROVED` (201), `ASSIGNMENT_CREATED` (201), `OFFER_REJECTED` (202), `OFFER_REJECTED` (203), `MANUAL_HANDOFF` (`NO_CANDIDATE_LEFT`)
201 ได้เข้าเวรและอยู่ต่อ เคสจบที่ `MANUAL_HANDOFF` (24.5, Q27)

ไม่มีกรณี "จัดเวรไม่ผ่าน" เพราะไม่มีการตรวจซ้ำตอนจัดเวร (Q38)

---

## 6. API และหน้าเว็บ

เขียนใหม่ตาม Flow ปัจจุบัน (ข้อ 2.5, 2.6)

### 6.1 คำตอบที่เปลี่ยน

| Route | ตอนนี้ | รอบ 1 |
|---|---|---|
| `POST /events` เวรที่ `merge_window_seconds = 0` | `201` `{event_id, event_status, case_id, case_status}` | เหมือนเดิมเมื่อเวรไม่มีเคสเดินอยู่: `PROCESSED` พร้อมเคส หรือ `IGNORED` ไม่มีเคส ถ้าเวรมีเคสเดินอยู่ ตอบ `RECEIVED`, `case_id = null` เพราะ Event ต้องรอเคสนั้นจบ (Q43) |
| `POST /events` กับ `event_type` อีกสามชนิด | `422` (`EventNotSupportedError`) | รับได้ Body และการตรวจของแต่ละชนิดอยู่ในข้อ 2.5 (Q40) |
| `POST /events` เวรที่ `merge_window_seconds > 0` | (ไม่มี) | `201` `{event_id, event_status: "RECEIVED", case_id: null, case_status: null}` เคสยังไม่เกิดจนกว่า Window ปิด |
| `POST /demo/clock/advance` (ใหม่) | (ไม่มี) | รับ `{seconds}` เลื่อน Clock ของ Demo แล้วปิด Window ที่ถึงเวลา และปิด Offer ที่หมดเวลา (ข้อ 2.7) ตอบเวลาใหม่กับรายการเวรที่ปิด Window |
| `GET /events/{event_id}` (ใหม่) | (ไม่มี) | ตอบ `{event_id, event_status, case_id, case_status}` รูปเดียวกับคำตอบของ `POST /events` ให้ผู้แจ้งดูว่า Event ของตัวเองกลายเป็นเคสไหน (Q36) |
| `POST /demo/line-sim/respond` กับ `REJECT` | `422` ไม่เขียน DB | `200` `{outreach_id, outreach_status: "REJECTED", case_id, case_status}` |
| `POST /approvals/{id}/decision` กับ `approved = false` | `422` ไม่เขียน DB | `200` `{approval_id, is_approved: false, case_id, case_status}` |
| `GET /cases/{id}/audit` | แถวที่ `case_id` เป็นเคสนี้ | รวมแถวที่ `event_id` เป็น Event ของเคสนี้ด้วย เรียงตาม `id` (Q33) |
| `GET /cases/{id}` | มี `event_id` ตัวเดียว | `event_ids` เป็น List (Q36) ต้องแก้ Type ฝั่ง Frontend ส่วน Gap แสดง `effective_minimum` กับ `headcount_gap` (Q20) จากแถว `STAFFING_GAP` ล่าสุด |
| `POST /internal/merge-windows/close-due` (ใหม่) | (ไม่มี) | Service ของ Job เรียกทุก 30 วินาที (Q35) กันด้วย Secret ใน Header ค่าจาก env |

`POST /events`

* รูปแบบ Body ไม่เปลี่ยน `case_id` กับ `case_status` เป็น null ได้อยู่แล้ว มีแค่ค่าใหม่ `event_status = RECEIVED`
* `case_id = null` มีสองความหมาย แยกด้วย `event_status`: `IGNORED` = จะไม่มีเคส, `RECEIVED` = รอ Window ปิดก่อน
* หลัง Window ปิด ผู้แจ้งดูเคสของ Event จาก `case_id` ใน Event ผ่าน Route อ่าน Event (Q36)

`respond` และ `decision`

* รูปแบบ Body ของคำตอบไม่เปลี่ยน มีแค่ค่าใหม่ จึงไม่ต้องแก้ Type ฝั่ง Frontend
* `case_status` ในคำตอบเป็นค่าที่คำนวณจากตารางสถานะเคส (ข้อ 2.6 ก): `WAITING_RESPONSE`, `WAITING_APPROVAL`, `RESOLVED`, `MANUAL_HANDOFF` หรือ `FAILED` (D11)
* `respond` รับคำตอบได้เมื่อ Offer ยัง `SENT` และยังไม่เลย `expires_at` (24.3, ข้อ 2.7) แทนกติกาเดิมที่เคสต้องอยู่ `WAITING_RESPONSE` เคสที่จบที่ `RESOLVED` หรือ `MANUAL_HANDOFF` ไม่มี Offer `SENT` เหลือ เพราะถูกยกเลิกตอนเคสจบ (ข้อ 4.2)
* Offer ที่ถูก `CANCELLED` หรือ `TIMEOUT` แล้ว กดตอบได้ `409` ตามการตรวจเดิม
* เคสที่หยุดแล้ว: ถ้าเคสอยู่ใน `AUTOMATION_STOPPED_STATUSES` (`RESOLVED`, `UNRESOLVED`, `FAILED`, `MANUAL_HANDOFF`) ทั้ง `respond` และ `decision` ตอบ `409` ไม่เขียน DB กรณีที่เกิดจริงคือเคส `FAILED`: เคสล้มจาก Exception (D11) จึงไม่มีขั้นยกเลิก Offer และคำขออนุมัติที่เหลือ ถ้าไม่กันไว้ ผู้สมัครกดรับได้ และผู้อนุมัติกดอนุมัติแล้วได้ Roster ของเคสที่ล้มไปแล้ว Offer ของเคสแบบนี้ค้างเป็น `SENT` จนหมดเวลาตามข้อ 2.7 (ตอนหมดเวลา `recompute()` ไม่ทำอะไรกับเคสที่หยุดแล้ว ข้อ 2.3)
* Offer ที่ยัง `SENT` แต่กดรับไม่ได้ เพราะผู้ตอบรับ Offer ของเคสอื่นค้างอยู่ (ข้อ 2.6 ค): ตอบ `409` (Q39) ข้อความต้องต่างจาก `409` ของ Offer ที่ถูกยกเลิก เพื่อให้หน้า `line-sim` บอกเหตุผลได้
* `decision` ตัดสินทีละคน เคสหนึ่งมีคำขออนุมัติค้างได้หลายแถวพร้อมกัน (24.1)
* การตรวจที่มาก่อนยังเหมือนเดิม: respond ตรวจ `outreach_id` (PR #30), decision ตรวจ `404 → 403 → 409`
* ลบข้อ 9.2 ของ `workflow.md` ("ขอบเขตของ Skeleton") ส่วนที่บอกว่า `REJECT` และไม่อนุมัติตอบ `422`
* `reason` ตอนไม่อนุมัติ: บังคับและไม่ว่าง ไม่ส่งเหตุผลให้ตอบ `422` (Q13)

### 6.2 หน้าเว็บที่ต้องแก้ตาม

| หน้า | เจ้าของ | ต้องแก้ |
|---|---|---|
| `demo/control` | คน 1 | **เปลี่ยน** (1) ปุ่มเลื่อน Clock ที่เรียก Route ใหม่ (2) ผลของการส่ง Event: ตอนนี้ `case_id = null` ขึ้นว่า "No case opened" ซึ่งผิดเมื่อ `event_status = RECEIVED` ต้องขึ้นว่ารอ Window ปิด รอบ 1 ไม่เพิ่มปุ่มโหลด Scenario (Q16) |
| `demo/line-sim` | คน 3 | เอาข้อความ "Rejection is not supported" ออก ปุ่ม Reject ใช้งานจริง ผู้สมัครคนเดียวเห็น Offer จากหลายเคสพร้อมกัน แต่ละ Offer แสดงหอ, เวร และเส้นตาย (เส้นตายเพิ่มใน PR O พร้อมคอลัมน์ `expires_at` ส่วนอื่นอยู่ PR 2b) Offer ที่กดรับไม่ได้ตอนนี้ต้องบอกว่าทำไม Offer ที่ถูกยกเลิกแสดงเหตุผล (ข้อ 2.6 ค) |
| `approvals` | คน 1 | ปุ่ม Reject ตอนนี้แสดง `422` เป็น Error ต้องแสดงผลสำเร็จ และมีช่องกรอก `reason` (Q13) เคสเดียวมีได้หลายแถว หนึ่งแถวต่อผู้สมัคร แต่ละแถวต้องบอกว่าเป็นของเคสไหนและเคสยังขาดกี่คน |
| `cases/[id]` | คน 2 | (1) ผู้สมัครหลายคนอยู่คนละขั้นพร้อมกัน แสดงสถานะรายคนตามตารางข้อ 2.6 ก (2) เหตุผลที่ผู้สมัครถูกข้าม (Q6) (3) รายการ Event ของเคสแทน `event_id` ตัวเดียว (Q36) (4) Gap แสดง `effective_minimum` กับ `headcount_gap` ของแถวล่าสุด (Q20) (5) Timeline ยาวขึ้น ต้องเช็กว่า `MANUAL_HANDOFF` ยัง Poll ต่อตามที่ออกแบบไว้ |
| `roster` | คน 3 | ไม่เปลี่ยน |

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

### 7.2 รอบ 1 ทำข้อไหน

ตกลงแล้วตามตารางนี้ คน 2 ยืนยันความหมายของคอลัมน์ Policy แล้ว (หัวข้อ "ความหมายของคอลัมน์ใน `HARD_CONSTRAINT_POLICY`" ท้ายข้อ 7.2)

| รหัส | มาจาก | รอบ 1 | หมายเหตุ |
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
| `CONSECUTIVE_SHIFTS_EXCEEDED` | `maximum_consecutive_shifts` (คอลัมน์ใหม่) | ทำ | นิยามอยู่ใต้ตาราง หัวข้อ "เพดานสองตัว" |
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
| แหล่งข้อมูล | Hard Rule สองข้อนี้คิดชั่วโมงสดจาก Roster ทุกครั้งที่ตรวจ ส่วนการจัดอันดับอ่าน `hours_this_week` และ `overtime_hours` จาก `STAFF_WORKING_TIME_SNAPSHOT` (Q54) ซึ่ง `working_time_service` เขียนตอน Optimize (ข้อ 8.3) ทั้งสองที่ต้องใช้นิยามวันและสัปดาห์ของตารางนี้ ค่าต่างกันได้เพราะ Snapshot เป็นค่าตอน Optimize ส่วน Hard Rule เป็นค่าตอนตรวจ เวรต่อเนื่องไม่ได้อ่านจาก Snapshot ทั้งการตรวจและการให้คะแนนใช้ `projected_consecutive_shifts` ที่คำนวณจาก Roster รวมเวรที่เสนอ (หัวข้อ "เพดานสองตัว") |
| `validation_snapshot` | เก็บผลรวมที่คำนวณได้และค่าเพดานใต้ Key `details` เช่น `{"weekly_hours": 56, "weekly_limit": 52}` (รูปเต็มอยู่ข้อ 7.4) |

ข้อจำกัดที่รู้

* ข้อชั่วโมงรายสัปดาห์นับตามสัปดาห์ปฏิทิน จึงไม่กันการขึ้นเวรติดกันข้ามสัปดาห์ เรื่องนั้นกันด้วย `CONSECUTIVE_SHIFTS_EXCEEDED` ซึ่งนับจากเวลาจริง ไม่รีเซ็ตตอนเปลี่ยนสัปดาห์
* ข้อรายวันยังไม่มีกรณีที่ไม่ผ่านโดยลำพังกับเวร 8 ชั่วโมงในตอนนี้ จึงมีแค่ Unit Test

#### เพดานสองตัว: ชั่วโมงรายสัปดาห์ และเวรต่อเนื่อง (ตกลงแล้ว)

ตัวเลขทั้งสองเป็น Hard Constraint ของระบบ ไม่ใช่ค่าตัวอย่าง ส่วน OT รายสัปดาห์**ไม่เป็น** Hard Constraint เกินได้ ใช้เป็น Soft Constraint อย่างเดียว (ท้ายหัวข้อนี้)

| เพดาน | คอลัมน์ใน `HARD_CONSTRAINT_POLICY` | Seed | รหัสเมื่อไม่ผ่าน |
|---|---|---|---|
| ชั่วโมงทำงานรวมหลังเพิ่มเวร ต่อสัปดาห์ | `maximum_weekly_hours` (มีอยู่แล้ว) | 52 | `WEEKLY_HOURS_EXCEEDED` |
| จำนวนเวรต่อเนื่องหลังเพิ่มเวร | `maximum_consecutive_shifts` (ใหม่: integer NOT NULL, CHECK >= 0) | 7 | `CONSECUTIVE_SHIFTS_EXCEEDED` |

* ตัวตรวจประเมินผล**หลังรวมเวรที่เสนอ** เท่ากับเพดานถือว่าผ่าน เกินเพดานถือว่าไม่ผ่าน
* คะแนน Soft Constraint ชดเชยการผิด Hard Constraint ไม่ได้ คนที่ไม่ผ่านถูกคัดออกก่อนคิดคะแนน
* ต้องผ่านแยกจากกฎเดิม: `maximum_daily_hours` = 12 (ชั่วโมงรวมต่อวัน), `maximum_weekly_hours` = 52 (ชั่วโมงรวมต่อสัปดาห์), `minimum_rest_hours` = 11 (พักขั้นต่ำระหว่างเวร)

**การนับเวรต่อเนื่อง**

* นับ Assignment ของผู้สมัครที่สถานะอยู่ใน `COMMITTED_ROSTER_STATUSES` ไม่รวม `CANCELLED`
* เรียงเวรตาม `start_at` ช่วงพัก = `start_at` ของเวรถัดไป ลบ `end_at` ของเวรก่อนหน้า
* พักไม่เกิน 24 ชั่วโมง → อยู่ในลำดับเวรต่อเนื่องเดียวกัน (พัก 24 ชั่วโมงพอดียังนับต่อเนื่อง)
* พักเกิน 24 ชั่วโมง → ตัดลำดับ เริ่มนับใหม่
* ใช้เวลาจริง ไม่รีเซ็ตเพราะเปลี่ยนวันหรือเปลี่ยนสัปดาห์
* เวรที่ทับกันเป็นเรื่องของ `SHIFT_CONFLICT` แยกต่างหาก
* ค่าที่ตรวจและให้คะแนนคือ `projected_consecutive_shifts`: แทรกเวรที่เสนอเข้าตาราง แล้วนับลำดับที่มีเวรนั้น ต้องดูทั้งเวรก่อนหน้าและเวรถัดไป เพราะเวรใหม่อาจเชื่อมสองลำดับเข้าด้วยกัน ค่านี้อยู่ใน Calculation Context ไม่เก็บลง Snapshot
* Hard Rule: `projected_consecutive_shifts` เกิน `maximum_consecutive_shifts` → `CONSECUTIVE_SHIFTS_EXCEEDED`
* Soft Constraint: `consecutive_shift_cost` = `projected_consecutive_shifts` ค่ามากได้ Penalty มาก ใช้เรียงคนที่ยังอยู่ในเพดาน (ข้อ 8.3)
* ค่าใน Snapshot: `consecutive_shifts` คือจำนวนเวรในลำดับปัจจุบัน ณ `captured_at` ถ้าไม่มีเวรกำลังทำงานและพักจากเวรล่าสุดเกิน 24 ชั่วโมงแล้ว ค่าเป็น 0

| เวรก่อนจบ | เวรใหม่เริ่ม | พัก | ผล |
|---|---|---|---|
| จันทร์ 16:00 | อังคาร 08:00 | 16 ชั่วโมง | นับต่อเนื่อง |
| จันทร์ 16:00 | อังคาร 16:00 | 24 ชั่วโมง | ยังนับต่อเนื่อง |
| จันทร์ 16:00 | พุธ 08:00 | 40 ชั่วโมง | เริ่มลำดับใหม่ |

**OT รายสัปดาห์ (ไม่เป็น Hard Constraint)**

* ไม่มีเพดาน OT และไม่มีรหัสไม่ผ่านของ OT ผู้สมัครที่ทำ OT มากยังถูกเลือกได้
* OT มีผลทางเดียวคือ Soft Constraint: `projected_overtime_cost` ใช้ `STAFF_WORKING_TIME_SNAPSHOT.overtime_hours` คนที่ทำ OT ในสัปดาห์นี้มากกว่าได้ Penalty มากกว่า (ข้อ 8.3)
* `overtime_hours` คือ OT จริงที่ทำไปแล้วในสัปดาห์ รวมจาก `ATTENDANCE.overtime_minutes` ของแถวที่สรุปแล้ว ตามขอบเขตสัปดาห์ของ Q14
* นิยามข้อมูลใน `ATTENDANCE`
  * `work_minutes` = เวลาทำงานจริงทั้งหมด รวม OT
  * `overtime_minutes` = ส่วนของเวลาทั้งหมดที่เป็น OT ไม่บวกเพิ่มเข้า `work_minutes` อีกครั้ง
  * ต้องมี `0 <= overtime_minutes <= work_minutes`
  * NULL หมายถึงข้อมูลยังไม่ครบ ไม่ใช่ 0 แถวที่ "สรุปแล้ว" คือแถวที่ `check_out_at`, `work_minutes` และ `overtime_minutes` ไม่เป็น NULL ทั้งสามค่า แถวที่ยังไม่สรุปไม่ถูกนับ
* ไม่มีการคิด OT ล่วงหน้าของเวรที่เสนอ จึงไม่ต้องมีคอลัมน์ OT ตามแผนใน Roster และไม่ต้องเชื่อม `ATTENDANCE` กับ Assignment


#### ความหมายของคอลัมน์ใน `HARD_CONSTRAINT_POLICY` (คำตอบของคน 2)

คอลัมน์ที่เป็นกฎรายผู้สมัคร

| คอลัมน์ | ชนิด | ความหมาย | รหัสเมื่อไม่ผ่าน |
|---|---|---|---|
| `require_active_staff` | ธง | ผู้สมัครต้องมี `STAFF.status = ACTIVE` | `STAFF_NOT_ACTIVE` |
| `prevent_shift_conflict` | ธง | ผู้สมัครต้องไม่มี Roster ในเวรอื่นที่เวลาชนกับเวรของเคส | `SHIFT_CONFLICT` |
| `require_matching_role` | ธง | ผู้สมัครต้องมี Role ที่เคสขาด | `ROLE_MISMATCH` |
| `require_matching_skill` | ธง | ผู้สมัครต้องมี Skill ที่เคสขาด | `SKILL_MISMATCH` |
| `minimum_rest_hours` | ตัวเลข | ช่วงพักระหว่างเวรต้องไม่น้อยกว่าค่านี้ ตรวจทั้งก่อนและหลังเวรของเคส เท่ากันถือว่าผ่าน | `INSUFFICIENT_REST` |
| `maximum_daily_hours` | ตัวเลข | ชั่วโมงทำงานรวมในหนึ่งวัน รวมเวรของเคส ต้องไม่เกินค่านี้ (นิยามวันตาม Q14) | `DAILY_HOURS_EXCEEDED` |
| `maximum_weekly_hours` | ตัวเลข | ชั่วโมงทำงานรวมในหนึ่งสัปดาห์ รวมเวรของเคส ต้องไม่เกินค่านี้ (นิยามสัปดาห์ตาม Q14) | `WEEKLY_HOURS_EXCEEDED` |
| `maximum_consecutive_shifts` | ตัวเลข (ใหม่) | จำนวนเวรต่อเนื่องหลังรวมเวรของเคสต้องไม่เกินค่านี้ พักไม่เกิน 24 ชั่วโมงนับว่าต่อเนื่อง Seed = 7 | `CONSECUTIVE_SHIFTS_EXCEEDED` |
| `preserve_source_ward_minimum` | ธง | การดึงคนจากหออื่นต้องไม่ทำให้เวรของหอต้นทางต่ำกว่าเป้าหมายของเวรนั้น เป้าหมายใช้สูตรเดียวกับการคิด Gap: `max(minimum_staff, required_staff)` เมื่อ `preserve_minimum_staffing` เปิด และ `required_staff` เมื่อปิด (Q15, Q51) | `SOURCE_WARD_MINIMUM_VIOLATION` |

คอลัมน์ที่ไม่ใช่กฎรายผู้สมัคร

| คอลัมน์ | ความหมาย | ใช้ที่ |
|---|---|---|
| `maximum_patients_per_nurse` | จำนวนผู้ป่วยสูงสุดต่อพยาบาลหนึ่งคน ใช้คำนวณ `required_staff` | Coverage |
| `preserve_minimum_staffing` | ธงที่บอกว่าเป้าหมายจำนวนคนของเวรต้องไม่ต่ำกว่า `minimum_staff` หรือไม่ (Q15) | Coverage |

กฎที่ไม่มีคอลัมน์ใน Policy จึงตรวจเสมอ

| รหัส | ความหมาย |
|---|---|
| `ALREADY_ON_SHIFT` | ผู้สมัครมี Roster ในเวรของเคสอยู่แล้ว |
| `UNAVAILABLE` | ผู้สมัครมี `STAFF_UNAVAILABILITY` ชนช่วงเวลาของเวร |

กติการ่วม

* ธงที่เป็น `false` = ไม่ตรวจข้อนั้น
* คอลัมน์ตัวเลขไม่มีธงปิด จึงตรวจเสมอ
* Roster ที่นับคือสถานะใน `COMMITTED_ROSTER_STATUSES`

จุดที่คำตอบของคน 2 ไม่ตรงกับคำตอบก่อนหน้า ตัดสินแล้ว

* **Q51 `preserve_source_ward_minimum`:** ตาม Q15 ทั้งหมด: เทียบกับเป้าหมายสูตรเดียวกับการคิด Gap (`max(minimum_staff, required_staff)` เมื่อ `preserve_minimum_staffing` เปิด), รหัส `SOURCE_WARD_MINIMUM_VIOLATION`, รอบ 1 เขียนกฎกับ Unit Test
* **Q52 `HAS_OPEN_OFFER`:** เลิกใช้ ใช้เพดานของ `OUTREACH_POLICY` และรหัส `OFFER_LIMIT_REACHED` ตาม Q30 (ข้อ 3.3)
* **Q55 `ROLE_MISMATCH` / `SKILL_MISMATCH`:** ประเมินตาม Coverage ที่ผู้สมัครถูกเลือกมาเติม ไม่บังคับให้ทุกคนปิดทุก Gap ของเคส
  * ผู้สมัครที่ถูกเลือกมาเติมจำนวนคน ไม่มี Skill ที่เคสขาดก็ผ่านได้
  * แต่ Role ของเขาต้องเป็น Role ที่ Requirement ของเวรมี (ข้อ 8.3) ผู้สมัครที่ไม่ได้ถูกเลือกมาเติม Role ใด (เติมจำนวนคนหรือ Skill อย่างเดียว) ไม่มีแถว `ROLE` ใน `CANDIDATE_ITEM_TARGET` ผู้เรียกตัวตรวจจึงต้องส่ง Role ของ Requirement ของเวรเป็น `target_role_ids` แทน ไม่ส่ง Set ว่าง ไม่งั้นผู้สมัครที่มี Role ที่เวรไม่ใช้จะไม่ถูกตัดด้วย `ROLE_MISMATCH` Set ว่างใช้เฉพาะเมื่อ Requirement ไม่ระบุ Role เลย ทำใน Loader ตัวเดียวของ PR 2a ที่ Solver, การเลือกคนของ Wave และ Safety (PR 3) เรียกร่วมกัน
  * กลุ่มคนที่ได้เข้าเวรรวมกันต้องครอบคลุมจำนวนคน, Role และ Skill ครบก่อนเคสจะ `RESOLVED`
  * Solver, การเลือกคนของ Wave, Safety และการตัดสินว่า Gap ของเคสถูกปิด (`gap_closed_by_assigned` ข้อ 2.3) ใช้ความหมายเดียวกัน เพื่อไม่ตัดผู้สมัครที่ Solver เลือกมาเติมจำนวนคนอย่างถูกต้อง
  * ที่เก็บ: ตารางใหม่ `CANDIDATE_ITEM_TARGET` เป็นตารางลูกของ `CANDIDATE_ITEMS` (ข้อ 8.3) Solver เขียนให้กลุ่มของ Wave แรกตอนสร้าง Plan `contact_candidate` เขียนให้ทุกคนที่มันเลือกเอง ทั้งคนที่เติมแทนใน Wave แรกและคนของ Wave ถัดไป ก่อนส่ง Offer (ข้อ 3.2 ขั้นที่ 5) Safety อ่านตอนตรวจ
  * ความหมายของ `require_matching_role` / `require_matching_skill` ในตารางข้างบน ("ต้องมี Role / Skill ที่เคสขาด") จึงใช้กับผู้สมัครที่ถูกเลือกมาเติม Role / Skill นั้นเท่านั้น

### 7.3 Interface

* ตัวตรวจเป็น Pure Function ใน `domain/constraints/` (ไฟล์มีชื่อใน `repo-structure.md` แล้ว: `codes.py`, `context.py`, `hard_rules.py`, `evaluator.py`) ไม่อ่าน DB เอง ผู้เรียกโหลดข้อมูลแล้วส่งเข้าไป แบบเดียวกับ `gap_calculator`
* ผลที่คืน: List ของรหัสที่ไม่ผ่าน (ว่าง = ผ่าน) ไม่ใช่ Exception เพราะ Safety ต้องบันทึกครบทุกข้อที่ไม่ผ่าน
* ผู้เรียกสามที่ต้องได้ผลเดียวกันจากข้อมูลเดียวกัน: Solver (คัดคนออก), `contact_candidate` (ข้ามคน ข้อ 3), Safety (บันทึกผล)
* **Q17** `availability_service.assert_available()` คำตอบล่าสุด (คน 2): **ลบ** แทนคำตอบเดิมที่ให้คงไว้เป็นเปลือก
  * Execute ไม่ตรวจซ้ำตอนจัดเวร (Q38) `roster_service` ของคน 3 จึงเลิกเรียก
  * Safety (`safety_service`) เรียกตัวตรวจใหม่ใน `domain/constraints/` ตรง ๆ เพราะต้องได้ List ของรหัสทุกข้อไปบันทึก (ข้อ 7.4)
  * ฟังก์ชันนี้จึงไม่เหลือผู้เรียก ลบพร้อม `unavailable_staff()`, Exception สามตัวเดิม (`StaffNotActiveError`, `StaffAlreadyOnShiftError`, `StaffUnavailableError`) และ `CandidateNotAvailableError` ใน PR 3 `unavailable_staff()` คืน Exception พวกนี้ และผู้เรียกที่เหลือคือ Solver ซึ่งเปลี่ยนไปใช้ตัวตรวจใหม่ใน PR 2a ก่อนแล้ว Test เดิมของสองฟังก์ชันนี้ย้ายไปตรวจตัวตรวจใหม่
  * ข้อจำกัดที่รู้: คนที่แจ้งลาหลังตอบรับแต่ก่อนได้รับอนุมัติ จะยังได้ Roster
* Policy ที่ใช้: `policy_service.get_hard_constraint_policy(db)` ตัวเดิม (ตรึง `id = 1`) ธง Boolean ใน Policy ที่เป็น `false` = ข้ามข้อนั้น

### 7.4 สิ่งที่ Safety บันทึก

| คอลัมน์ | ค่า |
|---|---|
| `SAFETY_VALIDATION.is_passed` | `false` เมื่อมีรหัสไม่ผ่านอย่างน้อยหนึ่งข้อ |
| `failure_reason` | รหัสที่ไม่ผ่าน คั่นด้วย `,` เรียงตามลำดับในตาราง 7.2 ไม่ใช่ข้อความอิสระ |
| `validation_snapshot` | รูปที่ตกลง: `{"staff_id": 201, "shift_id": 1, "policy_id": 1, "checked_rules": ["STAFF_NOT_ACTIVE", "SHIFT_CONFLICT"], "failed_rules": ["SHIFT_CONFLICT"]}` `checked_rules` คือกฎที่ตรวจจริง (ธงที่ปิดไม่อยู่ในนี้) `failed_rules` ว่าง = ผ่าน ผลรวมกับเพดานของข้อชั่วโมง (Q14) ใส่เพิ่มใต้ Key `details` เช่น `{"weekly_hours": 56, "weekly_limit": 52}` เมื่อมีการตรวจข้อนั้น ข้อเวรต่อเนื่องใส่ใต้ `details` แบบเดียวกัน: `projected_consecutive_shifts` กับ `consecutive_limit` |
| `hard_constraint_policy_id` | Policy ที่ใช้ตรวจจริง |

กรณีที่ยังเป็น `FAILED` (D11) ไม่ใช่ Safety ไม่ผ่าน: ข้อมูลผิดรูป เช่น `ProposedShiftMismatchError`, Item ไม่ได้อยู่ในเคสนี้, Offer ที่ส่งมาตรวจไม่ใช่ `ACCEPTED` พวกนี้คือระบบผิด ไม่ใช่ผู้สมัครไม่เหมาะ

---

## 8. Coverage (งานของคน 1 ที่ Solver ต้องใช้)

### 8.1 ตอนนี้

* `gap_calculator` คิด `minimum_required_staff = ceil(patient_count / patients_per_nurse)` และ Gap ของ Role / Skill ตาม Requirement
* `STAFFING_GAP` + แถว Role / Skill ถูกบันทึกแล้ว พร้อม Snapshot
* `STAFFING_REQUIREMENTS.required_staff` และ `minimum_staff` **ไม่ถูกใช้** (เอกสารเขียนไว้ชัดว่าไม่ใช้เป็นเป้าหมาย) รอบ 1 เปลี่ยนเป็นใช้ทั้งสองค่าตาม Q18
* Solver ยังไม่อ่าน Gap เลย ผู้สมัครตายตัว 201, 202, 203

### 8.2 "Minimum" คืออะไร

ชื่องานคือ "Role + Skill + Minimum" แต่ตอนนี้มีตัวเลขจำนวนคนสองแหล่ง

**Q18** `required_staff` และ `minimum_staff` ใน Requirement ใช้ทำอะไร คำตอบ

| หัวข้อ | กติกา |
|---|---|
| `required_staff` | จำนวนคนที่ต้องการตามภาระงาน = `ceil(patient_count / patients_per_nurse)` เก็บไว้ใน Requirement และคำนวณใหม่ใน PART B ครั้งเดียวหลังวนครบทุก Event เมื่อมี Event ที่ผ่าน Threshold จาก `patient_count` ค่าสุดท้าย (ข้อ 2.5) โดย **UPDATE ในแถว Requirement เดิม** ไม่สร้างแถวใหม่ |
| `minimum_staff` | ค่าคงที่ของแต่ละเวร คือจำนวนคนขั้นต่ำที่เวรต้องมีเสมอ |
| เป้าหมายจำนวนคน | `max(required_staff, minimum_staff)` เมื่อ `preserve_minimum_staffing` เปิด และ `required_staff` เมื่อปิด (Pseudo Code ใต้ตาราง) |
| `headcount_gap` | `max(เป้าหมาย - จำนวนคนในเวร, 0)` |
| `calculate_gap()` | รับ `required_staff` และ `minimum_staff` แทน `patient_count` และ `patients_per_nurse` (แก้ Signature ต้องแจ้งทีมก่อน) |
| สูตร `ceil` | แยกเป็นฟังก์ชันของตัวเอง ใช้ตอนเขียน `required_staff` (Seed และ PART B ของ Merge Gap) |
| Snapshot ใน `STAFFING_GAP` | เก็บ `effective_minimum` (เป้าหมายที่ใช้คิด) คอลัมน์เดียว `required_staff` และ `minimum_staff` อ่านผ่าน `staffing_requirement_id` ไม่เก็บซ้ำ รายละเอียดอยู่ใต้ Pseudo Code |
| Test | `required_staff` ใน Seed ต้องตรงกับสูตร และเพิ่มกรณีที่ `minimum_staff` มากกว่า `required_staff` |
| แก้เอกสาร | `workflow.md` ข้อ 3 และ Docstring ของ `gap_calculator` ที่บอกว่าไม่ใช้ `required_staff` |
| Threshold | ตอบแล้ว: ดู Ratio, Role Gap, Skill Gap ตอน Window ปิด (ข้อ 2.5, Q32) `required_staff` ถูกเขียนใหม่ใน PART B หลังวนครบทุก Event เมื่อมี Event ที่ผ่าน Threshold |

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

สิ่งที่ตามมา

* **ข้อมูลไม่ตรงกันได้:** `PATIENT_SURGE` เปลี่ยน `patient_count` ใน PART B ตอนถึงคิวของ Event ตัวนั้น (Q41) แต่ `required_staff` ถูกเขียนใหม่เฉพาะเมื่อ Window นั้นมี Event ที่ผ่าน Threshold ถ้าไม่มี สองค่านี้จะไม่ตรงกันจนกว่าจะมี Window ที่มี Event ผ่าน เป็นไปตามที่ออกแบบ (ไม่ผ่าน Threshold = ไม่เขียน `required_staff`)
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
  * แถว `STAFFING_GAP` เก่าตอน Migration: ใช้แนวเดียวกับ Q34 คือไม่เติมค่าย้อนหลัง ให้ `make reset` (ยืนยันแล้ว) ต้องแจ้งทีมว่าหลัง merge ทุกคนต้อง Reset
  * ไฟล์ที่แก้: Migration ใหม่, Model `StaffingGap`, `gap_service` (`assess_shift()`, `record_gap()`), `docs/database-schema.md`, Test ที่ตรวจสองคอลัมน์เดิม
* `gap_service.assess_shift()` ต้องโหลด Requirement มาใช้กับ Headcount ด้วย (ตอนนี้ใช้แค่ Role / Skill) และต้องอ่านธง `preserve_minimum_staffing` จาก Policy

### 8.3 Seam ใหม่ "Gap → Solver"

Solver ต้องรู้ว่าต้องหาคนแบบไหน ตกลงแล้วตามตารางนี้

| หัวข้อ | กติกา |
|---|---|
| แถวที่อ่าน | `STAFFING_GAP` ของเคส ที่ `id` มากสุด ไม่เจอ → Error (เคสผ่าน `ASSESSING` มาแล้วต้องมี) |
| Role ที่ต้องการ | แถว `STAFFING_GAP_ROLE` ที่ `gap_count > 0` |
| Skill ที่ต้องการ | แถว `STAFFING_GAP_SKILL` ที่ `gap_count > 0` |
| ผู้สมัครที่ผ่าน | ไม่ต้องปิดทุก Gap ด้วยคนเดียว ผู้สมัครผ่านเมื่อช่วยปิด Gap ที่ยังเหลืออย่างน้อยหนึ่งอย่าง |
| เป้าหมายของเคส | คนที่ได้มารวมกันต้องปิด Gap ครบ ไม่เหลือ Gap ค้าง ตัวอย่าง: คนที่มี Skill A + B ลา เกิด Gap ทั้งสอง Skill แก้ได้สองแบบ คือหา 1 คนที่มีทั้ง A + B หรือหาคนที่มี A กับคนที่มี B รวม 2 คน |
| อันดับของผู้สมัคร | กลุ่มของ Wave แรกเลือกด้วยคอลัมน์ `*_weight` ใน `SOFT_CONSTRAINT_POLICY` (สูตร `plan_penalty`) ส่วน `rank` เรียงด้วย `ranking_key` ใช้ตั้งแต่รอบ 1 (Q47, Q53) `optimization_priority` เป็นป้ายบอกลำดับความสำคัญ ไม่เข้าสูตร รายละเอียดอยู่ใต้ตาราง |
| Target ของ Wave (Q46) | คิดแยกตาม Gap แต่ละแบบ: Target = `ceil(gap * 11 / 10)` คิดด้วยจำนวนเต็ม ไม่ใช้ทศนิยม มีสามชนิด: ราย Skill, ราย Role และจำนวนคนรวม |
| จำนวนคนของ Wave (Q50) | จำนวนคนที่ถูกเลือกตามกติกาเติม Target ใต้ตาราง คนหนึ่งคนนับให้ทุก Target ที่เขาตรง จึงน้อยกว่าหรือเท่ากับผลรวมของ Target |
| ไม่มี Role / Skill Gap เลย (ขาดแค่จำนวนคน) | ผู้สมัคร Role ไหนก็ได้ที่ Requirement ของเวรมี |
| ใครโหลด | ฟังก์ชันเดียวใน `gap_service` ให้ Solver และ Safety เรียก ไม่เขียน Query เอง |

ตัวอย่างที่ใช้ทดสอบได้กับ Seed ปัจจุบัน: 101 (RN มี Skill ICU) ลาเวร 1 → ขาดจำนวนคน 1, RN 1, ICU 1 → Target = จำนวนคน 2, RN 2, ICU 2 → เติม ICU ก่อน ได้ 201 กับ 203 ซึ่งเป็น RN ทั้งคู่ Target ทุกตัวจึงครบ → Wave แรก = 201, 203 ส่วน 202 ไม่มี ICU แต่ยังผ่าน Hard Rules เพราะปิดจำนวนคนกับ RN ได้ เขาแค่ไม่ถูกเลือกใน Wave นี้เพราะ Target ครบแล้ว และยังอยู่ใน Plan ให้ Wave ถัดไป

#### `OptimizationObjective` (คำตอบของคน 2)

เป้าหมายแบบ Soft ที่ Solver ใช้เรียงอันดับผู้สมัคร หลังคัดคนที่ไม่ผ่าน Hard Rules ออกแล้ว

| ค่า | ความหมาย | วัดจาก | คอลัมน์ใน Policy |
|---|---|---|---|
| `MIN_CANDIDATE_COUNT` | ใช้ผู้สมัครให้น้อยที่สุดที่ยังปิด Gap ได้ครบ และไม่ต่ำกว่าจำนวนคนขั้นต่ำตาม Ratio เลือกคนที่ปิดได้หลาย Gap พร้อมกันก่อน | จำนวนคนในกลุ่มที่เลือก | `candidate_count_weight` |
| `CANDIDATE_SOURCE` | เลือกคนจากแหล่งที่ใกล้ก่อน: `SAME_WARD` ก่อน `FLOAT_POOL` ก่อน `CROSS_WARD` | `CANDIDATE_ITEMS.source` เทียบกับลำดับใน Policy | `candidate_source_priority` |
| `WEEKLY_WORKLOAD_FAIRNESS` | เลือกคนที่ชั่วโมงทำงานสะสมของสัปดาห์นี้น้อยกว่าก่อน | ชั่วโมงทำงานสะสมของสัปดาห์ | `workload_imbalance_weight` |
| `MIN_PROJECTED_OVERTIME` | เลือกคนที่ทำ OT ในสัปดาห์นี้น้อยกว่าก่อน | `overtime_hours` ใน Snapshot คือ OT จริงที่ทำไปแล้วในสัปดาห์ | `projected_overtime_weight` |
| `MIN_CONSECUTIVE_SHIFT` | เลือกคนที่รับเวรนี้แล้วมีเวรต่อเนื่องน้อยกว่าก่อน | `projected_consecutive_shifts` คือจำนวนเวรต่อเนื่องหลังแทรกเวรที่เสนอ คำนวณจาก Roster (ข้อ 7.2) | `consecutive_shift_weight` |

ลำดับความสำคัญที่ทีมตกลง (ปรับตาม Q53)

1. ปิด Role และ Skill ให้ครบ (เงื่อนไขบังคับ ไม่ใช่ค่าใน Enum)
2. `MIN_CANDIDATE_COUNT`: ใช้ผู้สมัครให้น้อยที่สุด และไม่ต่ำกว่าจำนวนคนขั้นต่ำตาม Ratio
3. `CANDIDATE_SOURCE`: Same Ward ก่อน Float Pool ก่อน Cross-Ward
4. `WEEKLY_WORKLOAD_FAIRNESS`: ชั่วโมงทำงานสะสมของสัปดาห์
5. `MIN_CONSECUTIVE_SHIFT`
6. `MIN_PROJECTED_OVERTIME`: OT ที่ทำไปแล้วในสัปดาห์นี้

กติกาที่ตามมา

* **Q53** รอบ 1 ใช้ครบทั้ง 5 ค่าใน Enum รวม `MIN_CONSECUTIVE_SHIFT` และใช้คอลัมน์ `*_weight` คำนวณคะแนน ลำดับข้างบนเป็นป้ายแนะนำการตั้ง Weight
* **Q54** `STAFF_WORKING_TIME_SNAPSHOT` ย้ายมาใช้ในรอบ 1 การให้คะแนนอ่านจาก Snapshot สองค่า คือ `hours_this_week` (ชั่วโมงสะสม) และ `overtime_hours` (OT) ส่วนคะแนนเวรต่อเนื่องไม่ได้อ่านจาก Snapshot ใช้ `projected_consecutive_shifts` ที่คำนวณจาก Roster รวมเวรที่เสนอ (ข้อ 7.2) คอลัมน์ `consecutive_shifts` และ `consecutive_night_shifts` ใน Snapshot ยังเก็บตามนิยามปัจจุบัน คือค่าก่อนเพิ่มเวร ณ `captured_at` ไม่ใช้ตรวจและไม่ใช้ให้คะแนนในรอบ 1
* `CANDIDATE_SOURCE` ไม่มีผลในรอบ 1 เพราะผู้สมัครทุกคนมาจากหอเดียวกัน

สูตรคะแนน (ค่าน้อยกว่าดีกว่า)

```text
plan_penalty =
    candidate_count_weight    × candidate_count_cost
  + consecutive_shift_weight  × consecutive_shift_cost
  + workload_imbalance_weight × workload_imbalance_cost
  + projected_overtime_weight × projected_overtime_cost
  + roster_change_weight      × roster_change_cost
  + candidate_source_weight   × candidate_source_cost
```

| Cost | ความหมาย |
|---|---|
| `candidate_count_cost` | จำนวนผู้สมัครไม่ซ้ำที่เลือก โดยต้องครอบคลุม Target รวมสำรองก่อน |
| `consecutive_shift_cost` | ผลรวม `projected_consecutive_shifts` ของคนในกลุ่ม คือจำนวนเวรต่อเนื่องหลังแทรกเวรที่เสนอ (นิยามในข้อ 7.2) |
| `workload_imbalance_cost` | ผลรวมชั่วโมงของสัปดาห์ (`hours_this_week`) ของคนในกลุ่ม |
| `projected_overtime_cost` | ผลรวม `overtime_hours` จาก Snapshot ของคนในกลุ่ม ชื่อ Cost, Enum และคอลัมน์ Weight ยังมีคำว่า projected เพราะเป็นชื่อที่มีอยู่แล้ว แต่ค่าที่ใช้คือ OT จริงของสัปดาห์ OT ไม่มีเพดานแบบ Hard Constraint (ข้อ 7.2) |
| `roster_change_cost` | จำนวน Assignment เดิมที่ต้องย้ายหรือเปลี่ยน |
| `candidate_source_cost` | ต้นทุนจากแหล่งที่มาของผู้สมัครในกลุ่ม: Same Ward ต่ำสุด, Float Pool, Cross-Ward สูงสุด ตามลำดับใน `candidate_source_priority` |

* `roster_change_cost` เป็น 0 เสมอในรอบ 1 เพราะรอบ 1 เพิ่มเวรอย่างเดียว ไม่ย้ายเวรเดิม
* พจน์ของ `CANDIDATE_SOURCE` ใช้คอลัมน์ใหม่ `SOFT_CONSTRAINT_POLICY.candidate_source_weight` (numeric, NOT NULL) เพิ่มใน PR 2a ตกลงแล้ว ส่วน `candidate_source_priority` ยังใช้บอกลำดับของแหล่งที่มา
* ลำดับความสำคัญ 2 ถึง 6 เป็นป้ายแนะนำว่าควรตั้ง Weight ตัวไหนมากกว่า ไม่ใช่ข้อบังคับว่าต้องเรียงมากไปน้อยเสมอ ปรับค่าได้

ค่า Seed ของ `SOFT_CONSTRAINT_POLICY` (กำหนดแล้ว)

| คอลัมน์ | ค่า Seed | หน่วยของ Cost ที่คูณ |
|---|---|---|
| `candidate_count_weight` | 1000 | จำนวนคนในกลุ่มที่เลือก |
| `candidate_source_weight` | 200 | ผลรวมของลำดับแหล่งที่มาของแต่ละคน: Same Ward = 0, Float Pool = 1, Cross-Ward = 2 |
| `workload_imbalance_weight` | 1 | ผลรวมชั่วโมงของสัปดาห์ (`hours_this_week`) ของแต่ละคน |
| `consecutive_shift_weight` | 5 | ผลรวมจำนวนเวรติดกันของแต่ละคนหลังรวมเวรของเคส |
| `projected_overtime_weight` | 2 | ผลรวมชั่วโมง OT ของสัปดาห์ (`overtime_hours`) ของแต่ละคน |
| `roster_change_weight` | 300 | จำนวน Assignment เดิมที่ต้องย้าย (รอบ 1 เป็น 0 เสมอ) |
| `candidate_source_priority` | `["SAME_WARD", "FLOAT_POOL", "CROSS_WARD"]` | ลำดับที่ใช้คิด `candidate_source_cost` และ `source_priority` |
| `optimization_priority` | `["MIN_CANDIDATE_COUNT", "CANDIDATE_SOURCE", "WEEKLY_WORKLOAD_FAIRNESS", "MIN_CONSECUTIVE_SHIFT", "MIN_PROJECTED_OVERTIME"]` | ป้ายลำดับ ไม่เข้าสูตร |

* เหตุผลของค่า: เพิ่มคนหนึ่งคนมีต้นทุน 1000 ส่วนพจน์ภาระงานของคนหนึ่งคนคือ ชั่วโมงของสัปดาห์ × 1 + เวรต่อเนื่อง × 5 + OT × 2 สองพจน์แรกมีเพดานจาก Hard Constraint (52 ชั่วโมง, 7 เวร ข้อ 7.2) รวมกันไม่เกิน 87 ส่วน OT ไม่มีเพดาน ถ้า OT ของสัปดาห์เป็น 12 ชั่วโมง คนหนึ่งคนได้ 111 และกลุ่มที่ใช้คนน้อยกว่าชนะเสมอตราบที่กลุ่มมีไม่เกิน 9 คน ถ้า OT สูงถึง 52 ชั่วโมง คนหนึ่งคนได้ 191 และยังชนะเสมอตราบที่กลุ่มมีไม่เกิน 5 คน การเทียบ 1 คนกับ 2 คนจะกลับผลได้ก็ต่อเมื่อ OT เกิน 456.5 ชั่วโมงต่อสัปดาห์ ซึ่งเป็นไปไม่ได้ (ตรวจด้วยโค้ดแล้ว) ทั้งหมดนี้จริงเมื่อผู้สมัครมาจากแหล่งเดียวกัน ถ้าต่างแหล่งกัน พจน์แหล่งที่มาเพิ่มได้ถึง 400 ต่อคน (Cross-Ward) กลุ่มที่คนน้อยกว่าจึงไม่ชนะเสมอ รอบ 1 ผู้สมัครมาจากหอเดียวกันทั้งหมด จึงไม่เจอกรณีนี้
* ตรวจด้วยโค้ดกับตัวอย่าง 6 คู่แล้ว ได้ลำดับตามที่ตั้งใจทุกคู่: คนเดียวที่เหนื่อยที่สุดชนะสองคนที่ว่าง, Same Ward ที่เหนื่อยที่สุดชนะ Float Pool ที่ว่าง, Float Pool ชนะ Cross-Ward, 24 ชั่วโมงชนะ 40 ชั่วโมง, เวรติดกันมากกว่า 2 เวรชนะทำงานมากกว่า 16 ชั่วโมง, OT 4 ชั่วโมงชนะเวรติดกันมากกว่า 2 เวร
* ค่าเดิมใน Seed เป็น 1 ทุกตัว (ตัวแทนชั่วคราว) เปลี่ยนใน PR 2a พร้อมคอลัมน์ `candidate_source_weight`
* Golden Path กำหนด Wave แรกเป็น 201, 202 (ข้อ 5.3) ข้อมูลตั้งต้นของ Golden Case จึงต้องทำให้กลุ่มนี้ได้ `plan_penalty` ต่ำสุด ข้อมูลที่ Seed คือแถว Roster (และ `ATTENDANCE` ถ้าต้องมี OT) ที่ `working_time_service` ใช้คำนวณ ไม่ใช่แถวใน `STAFF_WORKING_TIME_SNAPSHOT` เพราะ Service เขียน Snapshot แถวใหม่ทุกครั้งที่ Solver รัน แถวที่ Seed ไว้จะไม่ถูกใช้
* หน่วยของ Cost ในตารางยืนยันแล้ว: ภาระงานนับเป็นชั่วโมงรวม ไม่ใช่ระยะห่างจากค่าเฉลี่ย ค่า Seed ชุดนี้จึงใช้ได้


จากคะแนนของ Plan ไปเป็น `rank` รายคน

```text
Solver คัดคนที่ไม่ผ่าน Hard Rules ออก
→ ใช้สูตร plan_penalty เลือกกลุ่มที่ปิด Target ได้ครบและคะแนนต่ำสุด กลุ่มนี้คือ Wave แรก
→ Candidate Plan เก็บผู้สมัครทุกคนที่ผ่าน Hard Rules ไม่ใช่เฉพาะกลุ่มที่เลือก
→ คำนวณ ranking_key ของแต่ละคนใน Plan
→ บันทึก rank = 1, 2, 3, ... คนในกลุ่มที่เลือกมาก่อน เรียงตาม ranking_key แล้วตามด้วยคนที่เหลือ เรียงตาม ranking_key
```

`ranking_key` เป็นค่าชั่วคราวที่ Python สร้างเพื่อเรียงผู้สมัคร ไม่เก็บลง DB

```text
ranking_key = (
    source_priority,         # Same Ward → Float Pool → Cross-Ward
    hours_this_week,         # น้อยก่อน
    consecutive_shift_cost,
    projected_overtime,
    staff_id,                # ตัดสินเมื่อทุกค่าเท่ากัน
)
```

| ค่าใน Key | แหล่งข้อมูล |
|---|---|
| `source_priority` | `CANDIDATE_ITEMS.source` เทียบลำดับใน `SOFT_CONSTRAINT_POLICY.candidate_source_priority` |
| `hours_this_week` | `STAFF_WORKING_TIME_SNAPSHOT.hours_this_week` |
| `consecutive_shift_cost` | `projected_consecutive_shifts` ของคนนั้น คิดจาก Roster และเวรที่เสนอ (ข้อ 7.2) |
| `projected_overtime` | `STAFF_WORKING_TIME_SNAPSHOT.overtime_hours` |
| `staff_id` | ID ของผู้สมัคร |

สูตรสองตัวนี้ทำงานคนละหน้าที่ (ตกลงแล้ว)

* `plan_penalty` ตัดสินว่าใช้กี่คน และเป็นกลุ่มไหน
* `ranking_key` ใช้เรียงลำดับคนเพื่อบันทึก `rank` เท่านั้น ไม่ใช้เลือกกลุ่ม
* สองตัวให้ผลต่างกันได้ ตัวอย่าง: A ทำงาน 40 ชั่วโมง เวรติดกัน 0, B ทำงาน 39 ชั่วโมง เวรติดกัน 5 สูตร Weight ให้ A = 40, B = 64 จึงเลือก A แต่ `ranking_key` ดูชั่วโมงก่อน จึงเรียง B ก่อน (ตรวจด้วยโค้ดแล้ว) เมื่อขัดกันเรื่องใครอยู่ในกลุ่ม ให้ยึด `plan_penalty`
* ถ้าคะแนนเท่ากัน เรียงจาก `staff_id` น้อยไปมาก ทั้งตอนเลือกกลุ่มและตอนเรียงคน ผลจึงซ้ำเดิมทุกครั้ง (ยืนยันแล้ว)

ใครเขียน `STAFF_WORKING_TIME_SNAPSHOT`

```text
optimization_service
→ working_time_service โหลดข้อมูลและคำนวณ
→ บันทึก STAFF_WORKING_TIME_SNAPSHOT
→ เตรียม Input ให้ Solver
→ บันทึก Plan
```

* `working_time_service` (ไฟล์ใหม่) เป็นผู้เขียนเพียงจุดเดียว
* ที่มาของค่าใน Snapshot: `hours_this_week` คิดจาก Roster ที่สถานะอยู่ใน `COMMITTED_ROSTER_STATUSES` ตามนิยามวันและสัปดาห์ของ Q14 `consecutive_shifts` และ `consecutive_night_shifts` คิดจาก Roster ชุดเดียวกันด้วยกติกาพักไม่เกิน 24 ชั่วโมง ส่วน `overtime_hours` คือ OT จริงของสัปดาห์จาก `ATTENDANCE.overtime_minutes` ที่สรุปแล้ว (นิยามทั้งหมดอยู่ข้อ 7.2 หัวข้อ "เพดานสองตัว")
* ใช้เวลาอ้างอิงเดียวกันสำหรับผู้สมัครทุกคนในรอบ Optimize นั้น
* ไม่ Commit เอง ผู้เรียกคุม Transaction
* เพิ่มคอลัมน์ `working_time_snapshot_id` ใน `CANDIDATE_ITEMS` เพื่อระบุว่าใช้ Snapshot แถวไหน (Migration ใหม่ใน PR 2a)
* นิยามวัน / สัปดาห์ และข้อมูลคำนวณประกอบ เก็บใน `CANDIDATE_PLANS.input_snapshot`
* Safety อ่านข้อมูลใหม่ทุกครั้ง ไม่ใช้ Snapshot เก่าเป็นหลักฐานว่าผู้สมัครยังผ่านกฎ
* คำตอบเขียนว่า Execute ต้องอ่านข้อมูลใหม่ด้วย แต่ Q38 ตอบไว้ว่า Execute ไม่ตรวจซ้ำตอนจัดเวร ร่างนี้ยึด Q38: Execute ไม่ตรวจ จึงไม่มีการอ่าน


#### สิ่งที่กำหนดเพิ่มตอนทำ PR 2a

ร่างไม่ได้ระบุเรื่องต่อไปนี้ PR 2a กำหนดไว้ดังนี้ รายละเอียดของโค้ดอยู่ `docs/workflow.md` ข้อ 8 แถว Solver

* Pool ของผู้สมัคร = พนักงานทุกคนที่ `home_ward_id` ตรงกับหอของเวรของเคส
* เวลาอ้างอิงของ Snapshot = `clock.now()` หนึ่งค่าต่อรอบ Optimize (`captured_at`) "วันนี้" และ "สัปดาห์นี้" คือวันและสัปดาห์ของ `captured_at`
* `rest_hours` ยัง NOT NULL: เป็น 0 ตอนกำลังอยู่เวร และเป็น 0 เมื่อไม่มีเวรก่อนหน้า
* Target ที่ผู้สมัครมีไม่พอถูกลดลงเท่าจำนวนคนที่ตรง แล้วเลือกกลุ่มที่ปิด Target ที่ลดแล้วได้ครบและ `plan_penalty` ต่ำสุด
* คะแนนเท่ากัน: เลือกกลุ่มที่คนน้อยกว่า แล้วกลุ่มที่ `staff_id` น้อยกว่า
* ผู้สมัครที่ปิด Gap ไม่ได้สักอย่าง (เกิดเมื่อ `headcount_gap = 0`) ไม่อยู่ใน Plan
* `solver_status`: `FEASIBLE` เมื่อมีผู้สมัครอย่างน้อยหนึ่งคน `INFEASIBLE` เมื่อไม่มี
* กฎ Offer ค้างเดิมถูกลบใน PR 2a ตามข้อ 3.3 ระหว่างที่ PR 2b ยังไม่เข้า `staging` ผู้สมัครที่ได้ Offer จากสองเคสพร้อมกันจะตอบไม่ได้ (`docs/workflow.md` ข้อ 8 แถว Response)

#### ลำดับการเติม Target ของ Wave (คำตอบของคน 2)

ลำดับการเติม

1. Skill ก่อน เริ่มจาก Skill ที่มีผู้สมัครตรงน้อยที่สุด ถ้าเท่ากันเรียงตาม `skill_id`
2. Role ที่ยังเหลือ เรียงแบบเดียวกัน
3. จำนวนคนรวมที่ยังเหลือ

เมื่อเลือกคนหนึ่งคน

* คนนั้นถูกนับให้ทุก Target ที่เขาตรงพร้อมกัน: จำนวนคนรวมลด 1, Role ของเขาลด 1 และทุก Skill ที่เขามีและยังขาดลด 1
* คนหนึ่งคนอยู่ในรายชื่อผู้สมัครครั้งเดียว ไม่ว่าตรงกี่ Target
* Target ที่เป็น 0 แล้วไม่ถูกเติมต่อ

เลือกใครก่อนในแต่ละ Target

1. คนที่ปิด Target ที่ยังเหลือได้มากที่สุด (`MIN_CANDIDATE_COUNT`)
2. ตาม `ranking_key` (แหล่งที่มา, ชั่วโมงของสัปดาห์, เวรติดกัน, OT)
3. ถ้ายังเท่ากัน เรียงตาม `staff_id` (ตัวสุดท้ายของ `ranking_key`)

ลำดับนี้ใช้ที่ไหน

* ใน Solver: กลุ่มของ Wave แรกตัดสินด้วย `plan_penalty` ลำดับการเติมใช้บอกว่าแต่ละคนในกลุ่มถูกนับให้ Target ไหน เพื่อเขียน `CANDIDATE_ITEM_TARGET`
* ใน `contact_candidate` ของ Wave ถัดไป: ไม่มีการรัน Solver ใหม่ จึงเลือกคนด้วยลำดับนี้ โดยข้อ 2 ใช้ `rank` ใน Plan แทน `ranking_key` เพราะ `ranking_key` ไม่เก็บลง DB

หยุดเมื่อทุก Target เป็น 0 หรือไม่เหลือผู้สมัคร

ตัวอย่าง: ขาด ICU 1, RN 2, จำนวนคน 2 ได้ Target เป็น ICU 2, RN 3, จำนวนคน 3 ผู้สมัคร: A (RN, ICU), B (RN, ICU), C (RN), D (RN)

| ขั้น | เลือก | ICU | RN | จำนวนคน |
|---|---|---|---|---|
| เริ่ม | | 2 | 3 | 3 |
| เติม ICU | A | 1 | 2 | 2 |
| เติม ICU | B | 0 | 1 | 1 |
| เติม RN | C | 0 | 0 | 0 |

ได้ Wave เป็น A, B, C รวม 3 คน D ไม่ถูกเลือกเพราะทุก Target ครบแล้ว (จำลองกติกาด้วยโค้ดแล้ว ได้ผลตรงกับตารางนี้)

#### ตาราง `CANDIDATE_ITEM_TARGET` (Q55)

ตารางลูกของ `CANDIDATE_ITEMS` เก็บว่าผู้สมัครแต่ละคนถูกเลือกมาเติม Target ไหน คนหนึ่งคนมีได้หลายแถว (Migration ใหม่ใน PR 2a) ผู้เขียนมีสองจุด: Solver เขียนให้กลุ่มของ Wave แรก และ `contact_candidate` เขียนให้ทุกคนที่มันเลือกเอง ทั้งคนที่เติมแทนใน Wave แรกและคนของ Wave ถัดไป

| Field | Type | Null | Key / ความหมาย |
|---|---|---|---|
| `id` | bigint | NOT NULL | PK |
| `candidate_item_id` | bigint | NOT NULL | FK `CANDIDATE_ITEMS.id` |
| `target_type` | text | NOT NULL | `HEADCOUNT`, `ROLE`, `SKILL` |
| `role_id` | bigint | NULL | FK `ROLE.id` ใช้เมื่อ Target เป็น `ROLE` |
| `skill_id` | bigint | NULL | FK `SKILL.id` ใช้เมื่อ Target เป็น `SKILL` |
| `selection_type` | text | NOT NULL | `PRIMARY` หรือ `RESERVE` |

* ตัวอย่าง: A (RN, ICU) ถูกเลือกมาเติม ICU ได้สามแถว คือ `SKILL` (ICU), `ROLE` (RN), `HEADCOUNT` ส่วน C (RN) ได้สองแถว คือ `ROLE` (RN), `HEADCOUNT` Safety ของ C จึงไม่ตรวจ ICU
* ของกลางที่ต้องเพิ่ม: Enum สองตัวสำหรับ `target_type` และ `selection_type`
* CHECK (ตกลงแล้ว): `role_id` มีค่าเฉพาะเมื่อ `target_type = ROLE` และ `skill_id` มีค่าเฉพาะเมื่อ `target_type = SKILL`
* คำว่า "สำรอง" มีสองความหมาย ต้องไม่ปนกัน: `selection_type = RESERVE` คือคนส่วนเกิน 10% ที่ Solver เลือกเผื่อไว้ตอนคิด Target ส่วนสำรองของ Q28 คือคนที่ตอบรับหลัง Gap ถูกปิดครบแล้ว
* ข้อจำกัดที่รู้: แถวของคนหนึ่งคนถูกเขียนครั้งเดียวตอนเขาถูกเลือก ไม่แก้ทีหลัง ถ้าคนที่ถูกเลือกมาเติม Skill ปฏิเสธ คนอื่นใน Wave เดียวกันยังถือ Target เดิมของตัวเอง Wave ถัดไปคิด Target ใหม่จาก Gap ที่เหลือ จึงเลือกคนมาเติม Skill นั้นอีกรอบ ตัวกันสุดท้ายคือเคส `RESOLVED` ได้ก็ต่อเมื่อคนที่ได้เข้าเวรจากเคสนี้ปิด Gap ของเคสครบทุกตัว (`gap_closed_by_assigned` ข้อ 2.3)


### 8.4 คำถามอื่นของ Coverage

* **Q11** Gap มากกว่า 1 (เช่น 104 กับ 105 ลาเวรเดียวกัน ตอนนี้ได้สองเคสแยกกัน) และการส่ง Offer รอบ 1 จะส่งทีละคนหรือส่งเป็น Wave
  * หนึ่ง Wave = ส่ง Offer ให้ผู้สมัครหลายคนพร้อมกันตามลำดับ `rank` ทุกแถวเป็น `SENT`
  * ขนาด Wave: Target ต่อ Gap แต่ละแบบ = `ceil(gap * 11 / 10)` แล้วเลือกคนตามกติกาเติม Target (ข้อ 8.3) แทนสูตรเดิม `headcount_gap` + สำรอง
  * รับคนตามลำดับที่ตอบ `ACCEPT` จน Gap ถูกปิด คนที่ตอบรับหลังจากนั้นเป็นสำรอง Offer ที่ยัง `SENT` และของสำรองเป็น `CANCELLED` ตอนเคส `RESOLVED` (Q28)
  * ทั้ง Wave Reject หรือไม่ผ่าน Safety จนไม่ครบ → ส่ง Wave ถัดไปจากคนที่เหลือใน Plan ไม่เหลือใคร → `MANUAL_HANDOFF` (T5)
  * การรวม Event ของเวรเดียวกันทำในรอบ 1 แล้ว ด้วย Merge Gap (ข้อ 2.5) ไม่ใช่งานรอบ 4
* **Q19** ก่อน `RESOLVED` คิด Gap ของเวรใหม่จากสภาพเวรตอนนั้นไหม คำตอบ: ไม่คิดใหม่ เคสเทียบกับแถว Gap ของเคสเองที่จดไว้ตอนเปิดเคส ถ้าคนที่ได้เข้าเวรจากเคสนี้ปิด Gap นั้นครบ เคสเป็น `RESOLVED` (นี่คือการตรวจที่ Q55 พูดถึง ไม่ขัดกัน) การขาดคนที่เกิดเพิ่มระหว่างทางเป็นเรื่องของ Window ถัดไปและเคสใหม่ (Q43)
* **Q20** `GET /cases/{id}` คืนค่าที่ใช้คำนวณ Gap ด้วยไหม คำตอบ: เพิ่ม ตอนนี้หน้าเว็บแสดงแค่ "Short by 1" โดยไม่บอกว่าจากกี่คน
  * ค่าที่คืน: `effective_minimum` และ `headcount_gap` จากแถว Gap เท่านั้น สองค่านี้จดไว้ตอนคิด จึงถูกเสมอ ชื่อ Field: เพิ่ม `effective_minimum: int` ใน `GapView` ข้าง `headcount_gap` ที่มีอยู่ (`gap.effective_minimum`, `gap.headcount_gap`) และใน `CaseDetail` เปลี่ยน `event_id: int` เป็น `event_ids: list[int]` เรียงตาม `id` (Q36)
  * ไม่คืน `required_staff` กับ `minimum_staff` เพราะ Requirement ถูก UPDATE ในแถวเดิม ค่าที่อ่านได้อาจไม่ใช่ค่าตอนคิด (ข้อ 8.2)
  * `patient_count` กับ `patients_per_nurse` ไม่คืน เพราะคอลัมน์ถูกลบจาก `STAFFING_GAP` แล้ว (ข้อ 8.2)
  * จำนวนคนในเวรตอนคิดไม่มีคอลัมน์เก็บ (ไม่อยู่ในรายการคอลัมน์ที่ตกลง) ถ้าหน้าเว็บจะแสดง ให้คิดจาก `effective_minimum - headcount_gap` ได้เฉพาะเมื่อ `headcount_gap > 0` ถ้า `headcount_gap = 0` (เคสที่ขาดแค่ Role หรือ Skill) สูตรนี้ผิด เพราะเวรอาจมีคนมากกว่า `effective_minimum` หน้าเว็บจึงไม่แสดงจำนวนคนในเวรของเคสแบบนั้น
  * เพิ่ม Field ใน Response = แก้ Type ฝั่ง Frontend และหน้า `cases/[id]` ของคน 2

---

## 9. Seed Scenario และ Test

### 9.1 Scenario ที่ต้องมี

ตอนนี้มีแค่ `seed/scenarios/golden_case.py` เจ้าของในตารางกำหนดแล้ว

| ไฟล์ | เจ้าของ | สถานการณ์ | ข้อมูลที่ต้องเพิ่มจาก Golden Case |
|---|---|---|---|
| `candidate_reject.py` | คน 3 | 201 ปฏิเสธ 202 รับ (กรณี ก) และทุกคนปฏิเสธจนต้องส่ง Wave 2 (กรณี ง) | ไม่ต้องเพิ่ม |
| `head_nurse_reject.py` | คน 3 | 900 ไม่อนุมัติ 201 (กรณี ค) | ไม่ต้องเพิ่ม |
| `safety_failure.py` | คน 2 | 201 รับแล้ว Safety ไม่ผ่าน (กรณี ข) | ต้องทำให้ 201 ผิด Rule **หลัง** ได้ Offer เช่น เพิ่ม Roster เวรอื่นที่ชนเวลา ระหว่างรอคำตอบ |
| `no_feasible_solution.py` | คน 2 | ไม่มีผู้สมัครผ่าน Hard Rules เลย (กรณี จ) | ทำให้ 201, 202, 203 ไม่ผ่านทั้งหมด |
| (ใหม่) Skill Gap | คน 1 + คน 2 | 101 ลา Wave แรกต้องเป็นคนที่มี ICU คือ 201 กับ 203 (ข้อ 8.3) | ไม่ต้องเพิ่ม |
| (ใหม่) Merge Gap | คน 1 | สองคนลาเวรเดียวกันใน Window เดียว ได้เคสเดียวที่ต้องใช้ 2 คน (กรณี ต3, ช, ซ) และ Event ที่มาตอนเคสยังเดินอยู่ต้องรอ (Q43) | เวรที่ `merge_window_seconds = 600` |
| (ใหม่) Threshold | คน 1 | Event ที่ไม่ผ่าน Threshold ทั้ง Window (กรณี ต4), Event แรกผ่านแต่ Event หลังทำให้ Gap กลับเป็น 0 (กรณี ต5) และเวรต่ำกว่า `minimum_staff` แต่ไม่ผ่าน Threshold (Q32) | เวรที่คนเกินความต้องการ |
| (ใหม่) Event ชนิดใหม่ | คน 1 | `ASSIGNMENT_CANCELLED`, `PATIENT_SURGE`, `REQUIREMENT_CHANGED` แต่ละชนิดทำให้เกิดเคส | ผู้ใช้ที่เป็น Head Nurse มีอยู่แล้ว (900) |
| (ใหม่) หลาย Offer ต่อคน | คน 3 | ผู้สมัครคนเดียวได้ Offer จากสองเคส รับอันหนึ่ง อีกอันกดไม่ได้ แล้วกลับมากดได้เมื่อไม่ได้รับอนุมัติ เต็มเพดาน และเคสที่เหลือผู้สมัครคนเดียวซึ่งไปรับเคสอื่นต้องรอ ไม่ไป `MANUAL_HANDOFF` (ข้อ 2.1, 2.6 ค) | เวรที่สองซึ่งขาดคนและใช้ผู้สมัครชุดเดียวกัน |
| (ใหม่) Soft Constraint | คน 2 | ผู้สมัครที่ผ่าน Hard Rules เท่ากัน กลุ่มที่ถูกเลือกต่างกันตาม Weight | แถว Roster ที่ `working_time_service` ใช้คำนวณ และ `SOFT_CONSTRAINT_POLICY` |

**Q16** Scenario โหลดยังไง คำตอบ: รอบ 1 ใช้ใน Test เท่านั้น แต่ทุกไฟล์เขียน Interface เดียวกัน เพื่อให้เพิ่มปุ่มโหลดทีหลังได้โดยไม่ต้องรื้อ

| หัวข้อ | กติกา |
|---|---|
| `POST /demo/reset` | ไม่เปลี่ยน ไม่รับ Parameter โหลด Golden Case อย่างเดียว |
| หน้า `demo/control` | ไม่มีปุ่มเลือก Scenario ในรอบ 1 (ปุ่มที่เพิ่มในรอบนี้คือเลื่อน Clock และส่ง Event ชนิดใหม่ ข้อ 6.2) |
| Interface ของไฟล์ Scenario | ทุกไฟล์ใน `seed/scenarios/` มี `seed(db: Session) -> None` แบบเดียวกับ `golden_case.seed()` ที่มีอยู่ ไม่ Commit ผู้เรียกเป็นเจ้าของ Transaction |
| ข้อมูลตั้งต้น | Scenario เรียกต่อจาก `base_data.seed(db)` และ `golden_case.seed(db)` เพิ่มเฉพาะแถวที่ต่างจาก Golden Case ไม่ก๊อปข้อมูล Golden Case ไปเขียนซ้ำ |
| ID ที่ใส่เอง | ถ้าไฟล์ไหนใส่ `id` เอง ต้องเลื่อน Sequence ของตารางนั้นตาม แบบที่ Seed เดิมทำ |
| เหตุการณ์กลางทาง | สิ่งที่ต้องเกิดหลังเคสเริ่มเดิน (เช่น 201 ได้เวรชนเวลาหลังได้ Offer ใน `safety_failure`) ไม่อยู่ใน `seed()` ให้แยกเป็นฟังก์ชันของตัวเองในไฟล์เดียวกัน Test เรียกตอนที่ต้องการ |
| ใครเรียก | Fixture ของ Test เท่านั้น |

### 9.2 กติกาของ Test

* ทุกกรณีใน 5.3 มี Integration Test ที่ตรวจลำดับ Audit ตรงตามนั้น และตรวจสถานะสุดท้ายของเคส
* กรณีที่จบ `RESOLVED` ตรวจ Roster ด้วย: คนที่ได้ `REPLACEMENT` ต้องเป็นคนที่ได้รับอนุมัติ และ Gap ของเคสต้องถูกปิดครบทุกตัว เทียบกับแถว Gap ของเคสเอง (Q19)
* `test_transitions.py`: ตารางที่ยอมรับเพิ่ม T1 ถึง T7 ใน PR 0 (ไฟล์ของคน 1) ส่วนสองเส้นของ `SAFETY_VALIDATION` เอาออกใน PR 3 พร้อมกับโค้ดที่เลิกใช้สองเส้นนี้ (ข้อ 2.1)
* `tests/e2e/test_workforce_recovery.py` ต้องเขียวบน `staging` ตลอด ลำดับ Golden Path เปลี่ยนเพราะ Wave (ข้อ 5.3) แก้ E2E พร้อม `GOLDEN_PATH_AUDIT_ACTIONS` ใน PR 2b ระหว่างที่ PR 2b, 3, 4 ยังเข้า Branch รวมไม่ครบ E2E ของ Branch รวมแดงได้ แต่ต้องเขียวก่อน merge เข้า `staging` (ข้อ 10)
* Merge Gap: Test เดิมของการรับ Event ต้องเขียวเมื่อเวรใช้ Window = 0 เพิ่ม Test ว่าปิด Window สองรอบติดกันแล้วรอบสองแตะเฉพาะ Event ใหม่ และ Test ว่า PART B พังกลางทางแล้ว Event ทุกตัวยัง `RECEIVED` (ข้อ 2.5)
* Test ที่ให้สองคนลาเวรเดียวกันแล้วคาดสองเคสทันที ต้องแก้ เพราะ Event ตัวที่สองรอจนเคสแรกจบ (Q43)
* Test ที่หาแถว `EVENT_RECEIVED` / `UNAVAILABILITY_CREATED` ด้วย `case_id` ต้องแก้ไปใช้ `event_id` (Q33)
* Test ที่สร้างเคสด้วย `STAFFING_CASES.event_id` ต้องแก้ตามการย้ายไป `STAFFING_EVENTS.case_id` (PR M)
* Test ที่สมมติว่ามี Offer `SENT` แถวเดียว หรือว่า 202 ไม่มี Offer ตอน 201 ยังไม่ตอบ ต้องแก้ใน PR 2b
* Test สอง Connection ตามข้อ 4.3: สองคนตอบรับเคสเดียวกันพร้อมกัน, คนเดียวตอบรับสองเคสพร้อมกัน, ตอบรับกับอนุมัติคนสุดท้ายพร้อมกัน, สองเคสที่ใช้ผู้สมัครชุดเดียวกันตอบ Offer แล้วส่ง Wave ถัดไปพร้อมกัน ต้องไม่ค้างและไม่ได้คนเกิน
* Test ของเคสอื่นที่ได้รับผลกระทบ (ข้อ 2.3): เคส Y รอ A คนเดียว เคส X อนุมัติ A เคส Y ต้องเดินต่อเอง (ส่ง Wave ถัดไปหรือ `MANUAL_HANDOFF`) และ A ตอบรับเคส X แล้วเคส Y ที่รอ A คนเดียวต้องส่ง Wave ถัดไปได้
* Test ของ Offer ที่ถูกพัก (ข้อ 2.1) สองกรณี: (1) A กดรับเคส X ขณะที่เคส Y เหลือ A คนเดียว เคส Y ต้องรอที่ `WAITING_RESPONSE` และ Offer ยัง `SENT` เคส X ไม่อนุมัติ A แล้ว A กดรับเคส Y ได้ (2) สถานการณ์เดียวกัน แต่ Offer ของเคส Y หมดเวลาก่อน A จะกดรับไม่ได้ และเคส Y เดินต่อไป `MANUAL_HANDOFF`
* Test ของ Job เก็บตก (ข้อ 2.3): A กดรับเคส X แล้วจำลองระบบล่มหลัง Commit ก่อนเรียก `recompute()` ของเคส Y (เคส Y ยังมี B ที่ติดต่อได้) รัน Job แล้วเคส Y ต้องส่ง Offer ให้ B ได้ และ Offer ของ A ในเคส Y ยังเป็น `SENT` ไม่ถูกยกเลิก
* Fixture `stub_handlers` ใน `tests/integration/conftest.py` คืนเส้น Golden Path แบบเดิมที่ผ่าน `SAFETY_VALIDATION` ต้องแก้ตามตาราง Transition ใหม่ใน PR 3 ไม่ใช่ PR S ตามที่เคยเขียนไว้ เพราะ Fixture นี้บังคับให้มี Stub ครบทุก Handler ใน `orchestrator.HANDLERS` และ Handler ของ `SAFETY_VALIDATION` ยังอยู่จนกว่า PR 3 จะลบ PR S จึงไม่แตะ Fixture นี้
* Test ที่ตอนนี้คาดหวัง `422` ของ `REJECT` และไม่อนุมัติ, Test ที่คาด `FAILED` จาก `NoCandidatesError` / Safety ไม่ผ่าน และ Test ของ `assert_available()` ต้องเปลี่ยนใน PR ของเจ้าของเส้นทางนั้น

---


## 10. ลำดับ PR

Branch Protection เปิดแล้ว ทุก PR ที่เข้า `staging` ต้องมี `staging` ล่าสุดและ CI เขียว เจ้าของและการแบ่ง PR กำหนดแล้วตามตาราง

PR 2b, 3 และ 4 เข้า Branch รวมหนึ่ง Branch ที่แตกจาก `staging` ก่อน แล้วจึง merge Branch รวมเข้า `staging` ครั้งเดียว เหตุผล: หลัง PR 2b ระบบส่ง Offer เป็น Wave แล้ว แต่ Safety (PR 3) กับการอนุมัติ (PR 4) ยังเป็นโค้ดที่สมมติว่ามีคนตอบรับคนเดียว ถ้าเข้า `staging` ทีละตัว `staging` จะอยู่ในสภาพครึ่งเก่าครึ่งใหม่ แต่ละ PR ยังรีวิวแยกกันและมี CI ของตัวเอง (CI รันกับ PR ทุกตัวไม่ว่าเข้า Branch ไหน) Branch รวมต้องดึง `staging` ล่าสุดเป็นระยะ และต้องเขียวทั้งหมดรวม E2E ก่อน merge เข้า `staging`

| ลำดับ | PR | ใครทำ | มีอะไร | ต้องเข้าก่อน |
|---|---|---|---|---|
| 0 | Contract | คน 1 | ย้ายร่างนี้เข้า `workflow.md`, `transitions.py` + `test_transitions.py` (เพิ่ม T1 ถึง T7 สองเส้นของ `SAFETY_VALIDATION` ยังอยู่), `enums.py` (`AuditAction` 3 ค่า, `EntityType` 2 ค่า) ยังไม่เปลี่ยนพฤติกรรม | ทุกตัวข้างล่าง |
| 1a | Hard Rules: ตัวตรวจ + รหัส | คน 2 | `domain/constraints/` + Unit Test ยังไม่ต่อกับ Workflow, Migration: `HARD_CONSTRAINT_POLICY.maximum_consecutive_shifts` และ CHECK ของ `ATTENDANCE.overtime_minutes` (ข้อ 7.2) ทุกคนต้อง `make reset` หลัง merge | 2a, 2b, 3 |
| 1b | Coverage ตาม Q18 | คน 1 | `calculate_gap()` Signature ใหม่, ฟังก์ชันสูตร `ceil`, Migration ของ `STAFFING_GAP` (เพิ่ม `effective_minimum`, ลบ `patient_count` กับ `patients_per_nurse`), ฟังก์ชันอ่าน Gap ให้ Solver (ข้อ 8.3) | M, 2a |
| 1c | เพดาน Offer ต่อคน | คน 3 | ตาราง `OUTREACH_POLICY` + Seed, ฟังก์ชันเพดาน (ข้อ 3.3) ยังไม่มีใครเรียก | 2a, 2b |
| M | Merge Gap | คน 1 | Migration (`SHIFT.merge_window_seconds`, `STAFFING_EVENTS.processed_at` และ `case_id`, ลบ `STAFFING_CASES.event_id`, `AUDIT_LOG.event_id`), แยกการรับ Event กับการปิด Window, Threshold, Event สี่ชนิด, หนึ่ง Window หนึ่งเคส, Timeline ผ่าน `event_id`, Service ของ Job + Route ภายใน, Route เลื่อน Clock และ Route อ่าน Event, หน้า `demo/control` ทุกคนต้อง `make reset` หลัง merge | หลัง 0 และ 1b ก่อน 2b (Q48) |
| S | สถานะเคสคำนวณจาก Gap | คน 1 | ฟังก์ชันคำนวณสถานะเคสใน Orchestrator (ข้อ 2.3) ยังไม่มีใครเรียกจนกว่า 2b ส่วน `stub_handlers` ย้ายไป PR 3 เพราะ Handler ของ `SAFETY_VALIDATION` ยังอยู่ | 2b, 3, 4 |
| 2a | Solver | คน 2 | Solver ใช้ Hard Rules + Gap, เลือกกลุ่มด้วยน้ำหนัก และเรียง `rank` ด้วย `ranking_key`, กติกาเติม Target, ตาราง `CANDIDATE_ITEM_TARGET` (Q55), คอลัมน์ Weight ของ `CANDIDATE_SOURCE`, `ranking_key`, `working_time_service` + `STAFF_WORKING_TIME_SNAPSHOT` + `CANDIDATE_ITEMS.working_time_snapshot_id`, เปลี่ยนไปเรียกฟังก์ชันเพดาน Offer และลบกฎ Offer ค้างเดิม, T6, Scenario `no_feasible_solution` | 2b |
| 2b | Wave + ตอบ Offer | คน 3 | `contact_candidate` (ข้อ 3.2 รวมการเขียน `CANDIDATE_ITEM_TARGET` ให้ทุกคนที่มันเลือกเอง การรอ Offer ที่ถูกพัก และการยกเลิก Offer ตอนเคสเข้า `MANUAL_HANDOFF`), `outreach_service` (ส่งหลายคน, Reject, ตอบรับหลายคน, สำรอง, หลาย Offer ต่อคน, `409`), หน้า `line-sim` (ยังไม่แสดงเส้นตาย), Scenario `candidate_reject`, `GOLDEN_PATH_AUDIT_ACTIONS` + E2E, เรียก `recompute()` ให้เคสอื่นที่ได้รับผลกระทบหลังตอบรับ (ข้อ 2.3) | เข้า Branch รวม ก่อน 3, 4 |
| 3 | Safety รายคน | คน 2 | `safety_service` ตรวจตอนตอบรับและบันทึกผลไม่ผ่าน, ย้ายการสร้าง `APPROVAL_REQUEST` และการเขียน `APPROVAL_REQUESTED` ไปเป็นฟังก์ชันใน `approval_service` ที่ `safety_service` เรียกเมื่อ Safety ผ่าน (ไฟล์ของคน 3 แจ้งก่อนแก้), ลบ `assert_available()` และ `unavailable_staff()` พร้อมบรรทัดที่เรียก `assert_available()` ใน `roster_service` เพราะ PR 3 เข้าก่อน PR 4 ที่ย้ายการสร้าง Roster (ไฟล์ของคน 3 แจ้งก่อนแก้), ลบสองเส้นของ `SAFETY_VALIDATION` ออกจาก `transitions.py` + `test_transitions.py` และ Handler ของสถานะนี้ใน Orchestrator, Scenario `safety_failure` | เข้า Branch รวม หลัง 2b ก่อน 4 |
| 4 | อนุมัติและจัดเวรรายคน | คน 3 | `approval_service` (ไม่อนุมัติ, `reason`, เลื่อนสำรอง), จัดเวรใน Transaction ของการอนุมัติ, ยกเลิก Offer ที่ขัดกับเวรใหม่, Handler ของ `EXECUTING` ปิดเคส, เรียก `recompute()` ให้เคสอื่นที่ได้รับผลกระทบหลังตัดสิน (ข้อ 2.3), `409` กับเคสที่หยุดแล้ว, Scenario `head_nurse_reject` | เข้า Branch รวม หลัง 3 แล้ว merge Branch รวมเข้า `staging` ก่อน O, 5, 6 |
| O | Timeout ของ Offer | คน 3 | คอลัมน์ `OUTREACH_POLICY.offer_timeout_seconds` (Seed 300) และ `CANDIDATE_OUTREACH.expires_at`, การปิด Offer ที่หมดเวลา, แสดงเส้นตายของ Offer ในหน้า `line-sim`, ต่อเข้ากับ Service ของ Job (ข้อ 2.7), Job เก็บตกเคสที่ไม่มี Offer ค้าง (ข้อ 2.3) | หลัง M, 1c และ Branch รวมเข้า `staging` |
| 5 | หน้า `approvals` | คน 1 | Reject ใช้งานจริง + `reason`, หลายแถวต่อเคส | หลัง Branch รวมเข้า `staging` |
| 6 | หน้า `cases/[id]` | คน 2 | สถานะรายคน, เหตุผลที่ข้าม, `event_ids`, `effective_minimum` | หลัง Branch รวมเข้า `staging` |

ข้อที่เสี่ยงพังเงียบ (เคยเจอในขั้นที่ 4)

* PR M ลบ `STAFFING_CASES.event_id` Test ของทุกคนที่สร้างเคสตรง ๆ จะแดงหลังรวม จึงให้เข้าก่อน 2b และแจ้งทีมก่อน merge
* PR S เปลี่ยนวิธีที่เคสเปลี่ยนสถานะ PR 2b, 3, 4 ต้องมี Test ที่รันกับฟังก์ชันคำนวณสถานะตัวจริง ไม่ใช่ Stub
* PR 2a เปลี่ยนว่าใครอยู่ใน Plan และอันดับ Test ของคน 3 ที่สมมติว่ามี 201, 202, 203 ครบและเรียงตามเลข อาจแดงหลังรวม ให้ Test อ่านผู้สมัครจาก Plan จริง
* PR 2b เปลี่ยน Golden Path (`OFFER_SENT` สองแถว และ 202 มี Offer) Test ของคนอื่นที่ตรวจลำดับ Audit ทั้งเส้นหรือสมมติว่า 202 ว่าง จะแดงหลังรวม
* PR 3 กับ PR 4 ทำงานใน Transaction ของ PR 2b (ตอบรับ) ทั้งคู่ต้องเทียบลำดับ Lock กับข้อ 4.3 สามตัวนี้จึงเข้า Branch รวมและทดสอบด้วยกันก่อนเข้า `staging`
* ทุก PR จะชนกันที่ `workflow.md` ข้อ 13 เหมือนเดิม เก็บทุกแถว

---


## 11. ผลต่อเอกสารและไฟล์กลาง

| ไฟล์ | ต้องแก้ | ใคร |
|---|---|---|
| `docs/workflow.md` ข้อ 3 | การรับ Event แยกเป็นรับกับปิด Window, Threshold, Event สี่ชนิด (ข้อ 2.5) และเป้าหมายจำนวนคนจาก `effective_minimum` (ข้อ 8.2) | PR 0 |
| ข้อ 4, 5 | ตาราง Transition ใหม่ (ข้อ 2.1) `MANUAL_HANDOFF` ใช้แล้ว เคสไม่หยุดที่ `SAFETY_VALIDATION` | PR 0 |
| ข้อ 6.4 | Seam ของ Outreach, Response, Safety, Approval, Execute เขียนใหม่ตามข้อ 3 และ 4 กติกา Lock ตามข้อ 4.3 | PR 0 |
| ข้อ 7 | ตาราง Audit และลำดับของแต่ละกรณี (ข้อ 5) | PR 0 |
| ข้อ 8 | เปลี่ยนชื่อจาก "Stub ของแต่ละขั้น" และอัปเดตทุกแถว | เจ้าของแต่ละแถว ใน PR ของตัวเอง |
| ข้อ 9 | คำตอบของ API ที่เปลี่ยนและ Route ใหม่ (ข้อ 6.1) ลบส่วน `422` | PR 0 |
| ข้อ 12 | ย้ายเรื่องที่ทำแล้วออก | PR สุดท้ายของรอบ |
| `domain/workflow/transitions.py`, `test_transitions.py` | เพิ่ม T1 ถึง T7 | PR 0 |
| `domain/workflow/transitions.py`, `test_transitions.py` | เอาสองเส้นของ `SAFETY_VALIDATION` ออก | PR 3 |
| `domain/enums.py` | `AuditAction` เพิ่ม `ASSIGNMENT_CANCELLED`, `PATIENT_COUNT_UPDATED`, `REQUIREMENT_UPDATED` `EntityType` เพิ่ม `SHIFT`, `STAFFING_REQUIREMENTS` | PR 0 |
| `domain/enums.py` | Enum ใหม่สองตัวของ `CANDIDATE_ITEM_TARGET`: ค่าของ `target_type` และ `selection_type` (ข้อ 8.3) | PR 2a |
| `domain/enums.py` `GOLDEN_PATH_AUDIT_ACTIONS` | `OFFER_SENT` สองแถว | PR 2b |
| `audit_service.log()` | รับ `event_id` เพิ่ม | PR M แจ้งทีมก่อน |
| `gap_calculator` (Signature + Docstring), Migration ของ `STAFFING_GAP` | รับ `required_staff` / `minimum_staff`, เพิ่ม `effective_minimum`, ลบ `patient_count` และ `patients_per_nurse` | PR 1b แจ้งทีมก่อน และแจ้งให้ Reset หลัง merge |
| Migration ของ `SHIFT`, `STAFFING_EVENTS`, `STAFFING_CASES`, `AUDIT_LOG` | คอลัมน์ของ Merge Gap (ข้อ 2.5) กระทบ Case API, หน้า `cases/[id]`, Seed และ Test ที่สร้างเคส | PR M แจ้งทีมก่อน และแจ้งให้ Reset หลัง merge |
| Migration ของ `OUTREACH_POLICY` | ตารางใหม่ (ข้อ 2.6 ค) | PR 1c (คน 3) |
| Migration ของ `HARD_CONSTRAINT_POLICY`, `ATTENDANCE` | `maximum_consecutive_shifts` และ CHECK `0 <= overtime_minutes <= work_minutes` (ข้อ 7.2) กระทบ Seed ของ Policy | PR 1a (คน 2) แจ้งทีมก่อน และแจ้งให้ Reset หลัง merge |
| Migration ของ `CANDIDATE_ITEMS`, `CANDIDATE_ITEM_TARGET`, `SOFT_CONSTRAINT_POLICY`, `working_time_service` (ไฟล์ใหม่) | คอลัมน์ `working_time_snapshot_id`, ตารางใหม่ `CANDIDATE_ITEM_TARGET`, คอลัมน์ Weight ของ `CANDIDATE_SOURCE` และผู้เขียน Snapshot จุดเดียว (ข้อ 8.3) | PR 2a |
| Migration ของ `OUTREACH_POLICY`, `CANDIDATE_OUTREACH` | Timeout ของ Offer (ข้อ 2.7) | PR O |
| `docker-compose.yml`, ไฟล์ env ตัวอย่าง | Service ของ Job และ Secret ของ Route ภายใน (ค่า Secret จริงไม่ Commit) | PR M |
| `availability_service` | ลบ `assert_available()`, `unavailable_staff()` และ Exception ที่เกี่ยว (Q17) เพิ่มฟังก์ชันเพดาน Offer (ข้อ 3.3) | PR 3, PR 1c |
| `tests/integration/conftest.py` `stub_handlers` | เส้น Golden Path ใหม่ที่ไม่ผ่าน `SAFETY_VALIDATION` | PR 3 (ลบพร้อม Handler ของสถานะนี้) |
| `docs/database-schema.md` | คอลัมน์ของ Merge Gap ใส่แล้ว ยังต้องเพิ่ม `OUTREACH_POLICY`, คอลัมน์ของ `STAFFING_GAP` และแก้หัวข้อ Candidate Skip Reasons ให้ตรงกับข้อ 3 (รหัส `SOURCE_WARD_MINIMUM_VIOLATION`, `OFFER_LIMIT_REACHED`, การส่งเป็น Wave) | PR 0 |
| `docs/workflow.md` ข้อ 12 แถว "การใช้ `PENDING_APPROVAL` ใน Roster" | เอาคำว่า Wave ออกจากเงื่อนไข เพราะ Wave ใช้แล้ว | PR 0 |
| `docs/walking-skeleton.md` | ตาราง "หลัง Skeleton" ใส่สถานะของรอบ 1 | PR สุดท้ายของรอบ |

---


## 12. รายการคำถามและคำตอบ

ทุกข้อมีคำตอบแล้ว ช่อง "ข้อเสนอ" ของข้อที่ตอบแล้วคือคำตอบที่ใช้

| # | คำถาม | ข้อเสนอ | ขวางใคร |
|---|---|---|---|
| Q1 | ไม่อนุมัติแล้วไปไหน | ตอบแล้ว: คนนั้นหลุด Offer เป็น `CANCELLED` นับใหม่ (ข้อ 2.6) | 3, 1 |
| Q2 | ไม่เหลือผู้สมัครเป็นสถานะอะไร | ตอบแล้ว ตามข้อเสนอ: `MANUAL_HANDOFF` | 2, 3 |
| Q3 | ส่ง Wave ถัดไปด้วย Plan เดิมหรือรัน Solver ใหม่ | ตอบแล้ว ตามข้อเสนอ: Plan เดิม + ตรวจความพร้อมซ้ำ | 2, 3 |
| Q4 | กฎ "มี Offer ค้าง" ย้ายไปอยู่ไฟล์ไหน ใครย้าย | ถูกแทน: กฎนี้เลิกใช้ ใช้เพดานของ `OUTREACH_POLICY` คน 3 ทำตารางและฟังก์ชันใน PR 1c คน 2 เปลี่ยน Solver ให้เรียกใน PR 2a (ข้อ 3.3) | 2, 3 |
| Q5 | คนที่ถูกข้ามตอนเลือกคนของ Wave บันทึกยังไง | ตอบแล้ว ตามข้อเสนอ: `skipped` ใน `OFFER_SENT` แถวแรกของ Wave เมื่อส่งได้ หรือใน `MANUAL_HANDOFF` เมื่อไม่เหลือใคร | 3 |
| Q6 | `GET /cases/{id}` ต้องบอกเหตุผลที่ผู้สมัครถูกข้ามไหม | ตอบครบแล้ว: บอกเหตุผล รหัสอยู่ใน `database-schema.md` หัวข้อ Candidate Skip Reasons หน้าเคสอ่านจาก payload ของ Audit (ข้อ 2.6) | 1, 2 |
| Q7 | Offer ของคนที่ถูกปัดตกหลังตอบรับ ตั้งเป็น `CANCELLED` ใช่ไหม | ตอบแล้ว ตามข้อเสนอ: ใช่ | 2, 3 |
| Q8 | ใครเป็นคนตั้ง `CANCELLED` | ตอบแล้ว ตามข้อเสนอ: ฟังก์ชันเดียวใน `outreach_service` ให้ Safety และ Approval เรียก | 2, 3 |
| Q9 | ยอมรับกติกา "แถว `ACCEPTED` แก้ได้ภายใต้ Lock ของเคส" ไหม | เคยตอบว่ายอมรับ แต่กติกานี้ไม่ใช้แล้ว แทนด้วยลำดับ Lock ในข้อ 4.3 (ล็อก Offer ที่ยังไม่จบของเคสทุกแถวก่อนล็อกเคส) | ทุกคน |
| Q10 | เพิ่ม Audit Action สำหรับ `CANCELLED` ไหม | ตอบแล้ว: ไม่เพิ่ม ส่วน `cancelled_outreach_ids` ย้ายออกจาก `OFFER_ACCEPTED` ไปอยู่ Action ของจังหวะที่ยกเลิกจริง (Q28 ข้อ 5.1) | 3 |
| Q11 | ส่ง Offer ทีละคนหรือเป็น Wave ขนาดเท่าไหร่ | ตอบแล้ว: Wave ขนาดตาม Target ต่อ Gap และกติกาเติม Target (ข้อ 8.3) | ทุกคน |
| Q12 | Solver ไม่ได้ใครเลย เขียน `SOLVER_EXECUTED` และแถว Plan (`INFEASIBLE`) ก่อน `MANUAL_HANDOFF` ไหม | ตอบแล้ว ตามข้อเสนอ: เขียน เพื่อให้ Timeline บอกว่า Solver รันแล้ว | 2 |
| Q13 | `reason` ตอนไม่อนุมัติบังคับไหม | ตอบแล้ว ตามข้อเสนอ: บังคับ ไม่ว่าง | 3, 1 |
| Q14 | รอบ 1 ทำ Rule ชั่วโมงรายวันและรายสัปดาห์ไหม นิยามวันกับสัปดาห์ยังไง | ตอบแล้ว: ทำทั้งสองข้อ วัน = วันที่ของ `start_at`, สัปดาห์ = จันทร์ถึงจันทร์ ตามเวลา Asia/Bangkok (ข้อ 7.2) | 2 |
| Q15 | `preserve_minimum_staffing` กับ `preserve_source_ward_minimum` ต่างกันยังไง ใครตรวจ | ตอบแล้ว: ธงแรกกำหนดเป้าหมายของเวรที่ขาดคน (คน 1) ธงที่สองเป็น Hard Rule `SOURCE_WARD_MINIMUM_VIOLATION` ของเวรต้นทาง เทียบกับเป้าหมายสูตรเดียวกับการคิด Gap (คน 2, ข้อ 7.2) | 1, 2 |
| Q16 | Scenario โหลดผ่าน Test อย่างเดียว หรือมีปุ่มในหน้า Demo | ตอบแล้ว: Test อย่างเดียว ทุกไฟล์มี `seed(db)` แบบเดียวกัน (ข้อ 9.1) | ทุกคน |
| Q17 | `assert_available()` คงไว้เป็นเปลือก หรือให้ Execute เปลี่ยนไปเรียกตัวใหม่ | เปลี่ยนคำตอบ: ลบ `assert_available()` (คน 2) Execute ไม่ตรวจซ้ำ (Q38) Safety เรียกตัวตรวจใหม่ (ข้อ 7.3) | 2, 3 |
| Q18 | `required_staff` และ `minimum_staff` ใช้ทำอะไร | ตอบแล้ว: เป้าหมาย = `max(required_staff, minimum_staff)` เมื่อ `preserve_minimum_staffing` เปิด โดย `required_staff` เก็บใน Requirement ตามสูตร `ceil` (ข้อ 8.2) | 1, 2 |
| Q19 | ก่อน `RESOLVED` คิด Gap ของเวรใหม่จากสภาพเวรตอนนั้นไหม | ตอบแล้ว: ไม่คิดใหม่ เคสเทียบกับแถว Gap ของเคสเอง (ข้อ 8.4) | 1 |
| Q20 | `GET /cases/{id}` คืนค่าที่ใช้คำนวณ Gap เพิ่มไหม | ตอบแล้ว: เพิ่ม `effective_minimum` คู่กับ `headcount_gap` ไม่คืน `required_staff` / `minimum_staff` (ข้อ 8.4) | 1, 2 |
| Q21 | เคสหนึ่งรับคนมาแทนกี่คน | แทนด้วย Q24 เพราะ Merge Gap ทำให้เคสขาดได้มากกว่า 1 คน | ทุกคน |
| Q22 | คนที่ Offer ถูกยกเลิกตอนยังไม่ตอบ ติดต่อซ้ำใน Wave ถัดไปได้ไหม | ถูกแทน: การตอบรับของคนหนึ่งไม่ยกเลิก Offer ของคนอื่นแล้ว Offer ถูกยกเลิกตอนเคสจบ จึงไม่มีการติดต่อซ้ำในเคสเดียวกัน (ข้อ 3.4) | 3, 2 |
| Q23 | ไม่ผ่าน Hard Rules ตอน Execute แล้วเคสไปไหน | ยกเลิก: ไม่มีการตรวจซ้ำตอนจัดเวร (Q38) | 2, 3 |
| Q24 | เคสที่ขาดมากกว่า 1 คน เดินทีละคนหรือขนาน | ตอบแล้ว: ขนาน (ข้อ 2.6) คำถามที่ตามมาคือ Q27 ถึง Q31 ตอบครบแล้ว | ทุกคน |
| Q25 | ขนาดของ Wave | ตอบแล้ว: Target ต่อ Gap = `ceil(gap * 11 / 10)` แล้วเลือกคนตามกติกาเติม Target (ข้อ 8.3) | 3, 1 |
| Q26 | Event ใหม่ของเวรที่มีเคสเดินอยู่ | ถูกแทนด้วย Q43: รอจนเคสจบ แล้วเปิดเคสใหม่ ไม่เพิ่ม Gap บนเคสเดิม | 1, 3 |
| Q27 | จัดเวรทันทีรายคน หรือรอครบแล้วจัดทีเดียว | ตอบแล้ว: รายคน (ข้อ 2.6 ง) | 1, 3 |
| Q28 | คนตอบรับเกินจำนวน ใครได้ไปต่อ และยกเลิกที่เหลือเมื่อไหร่ | ตอบแล้ว ตามข้อเสนอ: เรียงตามเวลาตอบรับ ที่เกินเป็นสำรอง ยกเลิกเมื่อ `RESOLVED` | 3 |
| Q29 | Offer ที่ผู้สมัครกดไม่ได้เพราะรับที่อื่นอยู่ นับเป็น Offer ค้างของเคสไหม | ตอบแล้ว ตามข้อเสนอ: ไม่นับ | 3, 1 |
| Q30 | เพดาน Offer ต่อคน นับสถานะไหน Seed เท่าไหร่ รหัสเหตุผล | ตอบแล้ว ตามข้อเสนอ: `SENT` + `ACCEPTED` ที่ยังเดิน, 3, `OFFER_LIMIT_REACHED` | 2, 3 |
| Q31 | สถานะ `SAFETY_VALIDATION` ของเคสยังใช้ไหม | ตอบแล้ว ตามข้อเสนอ: คงใน Enum เคสไม่หยุดที่นี่ | 1, 2 |
| Q32 | Threshold วัดอะไร | ตอบครบแล้ว: Ratio, Role Gap, Skill Gap ผ่านเมื่อข้อใดข้อหนึ่งเกิน ไม่ดู `minimum_staff` รอบ 1 รับ Event ครบสี่ชนิด (ข้อ 2.5) | 1 |
| Q33 | Timeline ของเคสตอน Window > 0 เห็นการลาที่เป็นต้นเหตุยังไง | ตอบครบแล้ว: เพิ่ม `AUDIT_LOG.event_id` Timeline รวมแถวของ Event ที่เป็นของเคส แถวของ Event ใส่แค่ `event_id` ทุกกรณี (ข้อ 2.5) | 1, 2 |
| Q34 | Migration ของ Merge Gap | ตอบครบแล้ว: Migration ใหม่ ไม่เติมค่า ทุกคน `make reset` | 1 |
| Q35 | รอบ 1 สร้าง Job ที่ปิด Window เองตามเวลาจริงไหม | ตอบครบแล้ว: Service แยกใน `docker-compose.yml` เรียก Route ภายในของ Backend ทุก 30 วินาที Route คือ `POST /internal/merge-windows/close-due` กันด้วย Secret ใน Header (ข้อ 2.5) | 1 |
| Q36 | Case API ตอบ Event ของเคสรูปไหน และผู้แจ้งรู้ได้ยังไงว่า Event ของตัวเองกลายเป็นเคสไหนหลัง Window ปิด | ตอบครบแล้ว: `event_ids` เป็น List ผู้แจ้งดูจาก `case_id` ใน Event | 1, 2 |
| Q37 | Solver รันใหม่ไหมเมื่อ Gap ของเคสเพิ่ม | ตอบแล้ว: ไม่ Optimize ซ้ำ และเคสไม่ได้ Gap เพิ่มกลางทางแล้ว (Q43) | 2, 3 |
| Q38 | จัดเวรไม่ผ่านบันทึก Audit ด้วย Action ไหน | ตอบแล้ว: ไม่มีกรณีนี้ อนุมัติแล้วสร้าง Roster ทันที ไม่ตรวจซ้ำ ไม่มาเข้าเวรคือ `NO_SHOW` (ไม่อยู่ในรอบ 1) | 3, 1 |
| Q39 | กดรับ Offer ที่ยัง `SENT` แต่กดไม่ได้เพราะรับของเคสอื่นค้างอยู่ ตอบ Status Code อะไร | ตอบแล้ว: `409` | 3 |
| Q40 | กติการับ Event สามชนิดใหม่ (`ASSIGNMENT_CANCELLED`, `PATIENT_SURGE`, `REQUIREMENT_CHANGED`) | ตอบแล้ว ตามข้อเสนอ (ข้อ 2.5) | 1 |
| Q41 | ขั้น "Update table ที่เกี่ยวข้อง" ทำตอนรับ Event หรือตอน Window ปิด | ตอบแล้ว: ตอน Window ปิด (ข้อ 2.5) | 1, 3 |
| Q42 | Event ที่ไม่ผ่าน Threshold แต่อยู่ Window เดียวกับตัวที่ผ่าน เป็นสถานะอะไร และ Link เข้าเคสไหม | ตอบแล้ว: `PROCESSED` และ Link เข้าเคส | 1 |
| Q43 | กล่อง "มีการสร้าง Case" ท้ายแผนภาพ | ตอบแล้ว: หนึ่ง Window หนึ่งเคส Window ถัดไปของเวรรอจนเคสก่อนหน้าจบและครบ `merge_window_seconds` (ข้อ 2.5) | 1 |
| Q44 | Event ที่ Update table ไม่ได้ตอน Window ปิด (เช่น แจ้งลาซ้ำ) เป็นสถานะอะไร | ตอบแล้ว ตามข้อเสนอ: `IGNORED` ตัวเดียว ตัวอื่นเดินต่อ | 1 |
| Q45 | สถานะ `EXECUTING` ของเคสใช้ทำอะไร เมื่อจัดเวรรายคนตอนอนุมัติ | ตอบแล้ว ตามข้อเสนอ: ผ่านครั้งเดียวตอนได้คนครบเพื่อปิดงาน | 1, 3 |
| Q46 | เคส "ได้คนครบ" นับยังไง | ตอบแล้ว: เป้าหมายคือ Gap หมด ไม่ใช่จำนวนคน ขนาด Wave เป็นไปตามกติกาเติม Target (Q50 ข้อ 8.3) | ทุกคน |
| Q47 | รอบ 1 ใช้น้ำหนักจาก `SOFT_CONSTRAINT_POLICY` เลยไหม | ตอบแล้ว: ใช้ในรอบ 1 คะแนนคิดจากคอลัมน์ `*_weight` ส่วน `optimization_priority` เป็นป้ายบอกลำดับ ไม่เข้าสูตร (Q53 ข้อ 8.3) | 2 |
| Q48 | ลำดับ PR M กับ PR 2b | ตอบแล้ว: PR M ก่อน | 1, 3 |
| Q49 | เคสก่อนหน้า "จบ" นับสถานะไหน | ตอบแล้ว: `RESOLVED`, `UNRESOLVED`, `FAILED`, `MANUAL_HANDOFF` | 1 |
| Q50 | จำนวนคนของ Wave | ตอบแล้ว: ตามกติกาเติม Target ของคน 2 (ข้อ 8.3) | 2, 3 |
| Q51 | `preserve_source_ward_minimum` เทียบกับค่าไหน | ตอบแล้ว: ตาม Q15 เป้าหมายสูตรเดียวกับการคิด Gap คือ `max(minimum_staff, required_staff)` เมื่อ `preserve_minimum_staffing` เปิด (ข้อ 7.2) | 1, 2 |
| Q52 | `HAS_OPEN_OFFER` ยังใช้ไหม | ตอบแล้ว: เลิกใช้ ใช้ `OFFER_LIMIT_REACHED` ตาม Q30 | 2, 3 |
| Q53 | รอบ 1 ใช้ `MIN_CONSECUTIVE_SHIFT` ไหม และใช้ Weight หรือแค่ลำดับ | ตอบแล้ว: ใช้ และใช้ Weight คำนวณ ลำดับ 6 ข้ออยู่ข้อ 8.3 | 2 |
| Q54 | `MIN_PROJECTED_OVERTIME` วัดจากอะไรในรอบ 1 | ตอบแล้ว: ย้าย Working Time Snapshot มารอบ 1 (ข้อ 8.3) | 2 |
| Q55 | `ROLE_MISMATCH` / `SKILL_MISMATCH` ไม่ผ่านเมื่อไหร่ | ตอบแล้ว: ประเมินตาม Coverage ที่ผู้สมัครถูกเลือกมาเติม กลุ่มที่ได้เข้าเวรต้องครอบคลุมครบก่อน `RESOLVED` (ข้อ 7.2) | 2 |
| Q56 | Timeout ของ Offer ทำในรอบ 1 ไหม และการอนุมัติมี Timeout ไหม | ตอบแล้ว: Offer หมดเวลาใน 300 วินาที (`OUTREACH_POLICY.offer_timeout_seconds`) การอนุมัติไม่มี Timeout (ข้อ 2.7) | 3, 1 |

รายละเอียดที่เคยค้างไว้กำหนดครบแล้ว: ค่า Seed ของ Weight (ข้อ 8.3), รูปของ `validation_snapshot` (ข้อ 7.4), ฟังก์ชันคำนวณสถานะเคส (ข้อ 2.3), ชื่อ Field ใน Case API (ข้อ 8.4), เจ้าของ PR และ Scenario (ข้อ 9.1, 10), Timeout ของ Offer (ข้อ 2.7)

ไม่มีข้อไหนรอคำตอบแล้ว หน่วยของ Cost และการตัดสินเมื่อคะแนนเท่ากันยืนยันแล้ว (ข้อ 8.3)

---

## 13. สิ่งที่ฉันยังไม่ได้ตรวจ

* ข้อ 2.1, 3, 4, 9, 10, 11 เขียนใหม่จากคำตอบในแชท ยังไม่ได้ไล่โค้ดของ `outreach_service`, `approval_service`, `roster_service` ว่าแต่ละข้อต้องแก้กี่จุด และจำนวน Test ที่จะแดงยังไม่ได้นับ
* ยังไม่ได้ไล่ Test ทั้งหมดว่าตัวไหนจะแดงเมื่อเปลี่ยนคำตอบ `422` และ `FAILED` รายการในข้อ 9.2 มาจากการอ่านโค้ดของ Service ไม่ได้รัน
* ข้อ 4.3 เรื่อง Lock เป็นการวิเคราะห์ ยังไม่ได้ดูว่า `roster_service` ล็อกอะไรตอนสร้าง Roster วันนี้ และยังไม่มี Test พิสูจน์ ต้องมี Test สอง Connection แบบที่ทำกับ Orchestrator และ Solver
* ยังไม่ได้ไล่โค้ดของ `record_response` และ `send_offer` ว่าต้องแก้กี่จุด และยังไม่ได้นับ Test ที่จะแดงเมื่อ Golden Path มี `OFFER_SENT` สองแถว
* ข้อ 2.5 Merge Gap เขียนจากแผนภาพและคำตอบในแชท ยังไม่ได้ไล่โค้ดการรับ Event ว่าการหา "เคสเปิดของเวรนี้" ต้องล็อกอะไรเพิ่ม และยังไม่ได้นับ Test ที่เรียก `receive_event()` แล้วคาดผลของ Gap ทันที ซึ่งต้องผ่านได้เมื่อ Window = 0
* ตาราง Hard Rules ข้อ 7.2: คน 2 ยืนยันความหมายของคอลัมน์แล้ว และเทียบกับ Model `HardConstraintPolicy` ทีละคอลัมน์แล้วใน PR 1a (ตรวจแล้ว): คอลัมน์ที่ตารางอ้างมีใน Model ครบทุกตัว โดย `maximum_consecutive_shifts` เพิ่มใน PR เดียวกัน
