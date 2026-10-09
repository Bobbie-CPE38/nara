# Workflow Contract

> ข้อตกลงร่วมของทีม ใช้คู่กับ `backend/app/domain/enums.py` และ `docs/database-schema.md`
> ถ้าจะเปลี่ยนอะไรในไฟล์นี้ แจ้งทั้งทีมก่อน และแก้ใน PR เดียวกับโค้ดที่เกี่ยวข้อง
>
> ขอบเขต: Walking Skeleton (Golden Path เท่านั้น)
> อัปเดตล่าสุด: 2026-10-08

---

## 1. การตัดสินใจหลัก

| # | การตัดสินใจ | เหตุผล |
|---|---|---|
| D1 | `STAFFING_CASES.status` ใน DB เป็นความจริงเดียวของสถานะเคส | เคสต้องรอคนตอบเป็นนาทีถึงชั่วโมง State ต้องอยู่รอดแม้ Server Restart |
| D2 | Skeleton ใช้ Orchestrator เป็น Python ธรรมดา LangGraph อยู่ในแผนแต่อยู่นอก Skeleton | ทำ Golden Path ให้วิ่งก่อน Handler ออกแบบให้ห่อด้วย LangGraph ภายหลังได้โดยไม่ต้องแก้ข้างใน |
| D3 | เฉพาะ Orchestrator เท่านั้นที่เปลี่ยน `case.status` และบันทึก `CASE_STATUS_CHANGED` ทุกครั้ง | Timeline ครบโดยไม่ต้องพึ่งให้ทุก Handler จำไปบันทึก และตรวจ Transition ได้ในที่เดียว |
| D4 | Handler และ Audit ใช้ DB Session เดียวกัน Orchestrator Commit ครั้งเดียวต่อรอบ | งานกับ Audit ของมันสำเร็จหรือล้มเหลวพร้อมกัน |
| D5 | ไม่สร้างเคสถ้าไม่มี Gap Event ที่ไม่มี Gap ถูกตั้งเป็น `IGNORED` | ไม่มีเคสขยะในระบบ (ดูข้อ 3) |
| D6 | Skeleton ทำงาน Sync ภายใน HTTP Request ยังไม่ใช้ Celery | ลดชิ้นส่วนที่ต้องตั้งค่าช่วงแรก |
| D7 | ID ทุกตารางเป็น `bigint` | ตัดสินแล้วจากทีม |
| D8 | Enum เป็น Python `StrEnum` ใน `domain/enums.py` เก็บใน DB เป็น `text` ยังไม่ใส่ DB ENUM หรือ CHECK | ค่าหลายตัวยังไม่ยืนยัน แก้ได้โดยไม่ต้อง Migration |
| D9 | Skeleton ยังไม่มี Login ระบุตัวผู้ใช้ด้วย Header `X-Demo-User: <staff_id>` | `approver_id` และ Actor ต้องมีค่า |
| D10 | เวลาของระบบมาจาก `core/clock.py` ที่ตั้งค่าได้ ห้ามเรียก `datetime.now()` ตรง ๆ | Demo และ Test ต้องได้ผลเหมือนเดิมทุกครั้ง |
| D11 | เกิด Exception ระหว่าง Workflow: Rollback งานของรอบนั้นด้วย Savepoint (งานของผู้เรียกใน Transaction เดียวกันยังอยู่) ตั้งเคสเป็น `FAILED` และบันทึก `WORKFLOW_FAILED` แล้ว Commit รายละเอียดดูข้อ 6.2 | ไม่มีเคสค้างกลางทางโดยไม่มีใครรู้ |
| D12 | Skeleton ยังไม่มี LLM, OR-Tools, LINE จริง, Aggregation | ใช้ Stub ทั้งหมด แล้วเปลี่ยนเป็นของจริงทีละส่วน |

---

## 2. การเปลี่ยน Schema เพิ่มจาก v5

ต้องทำก่อนสร้าง Migration แรก รายละเอียดครบทุกคอลัมน์อยู่ที่ `docs/database-schema.md`

| ตาราง | เปลี่ยน | เหตุผล |
|---|---|---|
| ทุกตาราง | `id` และ FK เป็น `bigint` (ยกเว้น `CONTACTS.line_id`, `line_uid`) | D7 |
| `STAFF` | ตัด `PLANNED_LEAVE`, `UNPLANNED_LEAVE` ออกจาก Staff status เหลือ `ACTIVE` / `INACTIVE` | การลาเก็บที่ `STAFF_UNAVAILABILITY` ที่เดียว |
| `STAFF_UNAVAILABILITY` (เดิม `STAFF_AVAILABILITY`) | ตัด `is_available`, `reason` → `NOT NULL`, Reason เป็น `PLANNED_LEAVE` / `UNPLANNED_LEAVE` / `NO_SHOW` (ตัด `OTHER`), `end_at` → `NULL` ได้ | เก็บเฉพาะช่วงที่ไม่พร้อม ไม่มีแถว = พร้อม (เฉพาะ `STAFF.status = ACTIVE`) |
| `STAFFING_EVENTS` | เพิ่ม `status text NOT NULL` ค่า `RECEIVED` / `PROCESSED` / `IGNORED` | เก็บผลของ Event ที่ไม่มี Gap (ไม่มีเคสให้เก็บ) และใช้ต่อตอนทำ Aggregation |
| `STAFFING_EVENTS` | ตัด `UNPLANNED_LEAVE` ออกจาก Event type (ใช้ `STAFF_UNAVAILABLE` แทน), รวม `STAFFING_` / `ROLE_` / `SKILL_REQUIREMENT_CHANGED` เป็น `REQUIREMENT_CHANGED` | เหตุผลของการไม่พร้อมดูที่ `STAFF_UNAVAILABILITY.reason` |
| `ROSTER_ASSIGNMENT` | เพิ่ม `PENDING_APPROVAL` ใน Roster status | เตรียมไว้สำหรับข้อ 12 |
| `STAFFING_CASES` | ตัด `IGNORED` ออกจาก Case status | เคสจะไม่มีวันอยู่ในสถานะนี้ตาม D5 |
| `ACTORS` (ใหม่) | `id bigint PK`, `name text NOT NULL`, `actor_type text NOT NULL`, `staff_id bigint NULL FK STAFF.id` | ผู้กระทำทุกแบบอ้างด้วย ID เดียว และผูกคนกับพนักงานได้ |
| `AUDIT_LOG` | `actor_id` เป็น `bigint NOT NULL FK ACTORS.id` และตัด `actor_type` ออก (ย้ายไปอยู่ที่ ACTORS), `entity_id` → `bigint NULL`, เพิ่ม `STAFF_UNAVAILABILITY` ใน Entity type และ `UNAVAILABILITY_CREATED` / `UNAVAILABILITY_UPDATED` ใน Audit action | ประเภทเป็นคุณสมบัติของผู้กระทำ ไม่ใช่ของแต่ละเหตุการณ์ |
| `APPROVAL_REQUEST` | `required_approver_role` → `bigint FK ROLE.id` | ชั่วคราวสำหรับ Skeleton (ข้อ 12) |

กติกาของ `ACTORS`

* `actor_type = user` → `staff_id` ต้องมีค่า, `name` = `str(staff.id)` สร้างแถวพร้อมกับการสร้าง `STAFF`
* `actor_type = system` / `component` → `staff_id` เป็น NULL, `name` = ค่าจาก `ActorName`
* Seed สร้าง Actor ที่ไม่ใช่คนทั้ง 6 ตัวไว้เสมอ

---

## 3. การรับ Event

```
POST /events
  1. บันทึก STAFFING_EVENTS (status = RECEIVED)                → Audit EVENT_RECEIVED
  2. ถ้าเป็น STAFF_UNAVAILABLE ที่ผูกกับเวร:
       - สร้าง STAFF_UNAVAILABILITY (reason = UNPLANNED_LEAVE,
         start_at = SHIFT.start_at, end_at = เวลากลับที่แจ้ง หรือ SHIFT.end_at ถ้าไม่ได้แจ้ง)
       - ROSTER_ASSIGNMENT ของคนนั้นในเวรนั้น → CANCELLED
  3. ตรวจ Coverage เบื้องต้น ด้วย gap_calculator ตัวเดียวกับขั้น ASSESSING
       - ไม่มี Gap: Event → IGNORED                            → Audit EVENT_IGNORED (case_id = NULL)
       - มี Gap:   Event → PROCESSED, สร้าง STAFFING_CASES (OPEN) → Audit CASE_OPENED
                   แล้วเรียก orchestrator.advance(case_id)
```

* `required_replacement_time` = `SHIFT.start_at`
* Request: `POST /events` พร้อม `X-Demo-User` และ Body `{event_type, shift_id, end_at?}` ผู้แจ้งคือ `user.staff.id`
  `end_at` คือเวลากลับที่แจ้ง ต้องมี Timezone และอยู่หลัง `SHIFT.start_at` ไม่ส่งมา = ถึง `SHIFT.end_at`
* Skeleton รับเฉพาะ `STAFF_UNAVAILABLE` Event type อื่นยังไม่มีกติการับ (ข้อ 12)
* ตรวจทุกข้อ**ก่อนเขียนแถวแรก** คำขอที่ถูกปฏิเสธจึงไม่ทิ้งอะไรไว้ใน DB ตามลำดับนี้

  | ตรวจ | ไม่ผ่านตอบ |
  |---|---|
  | `event_type` เป็น `STAFF_UNAVAILABLE` | `422` |
  | `shift_id` อยู่ในช่วง `bigint` (1 ถึง 9223372036854775807) | `422` |
  | มี Shift ID นั้น | `404` |
  | `end_at` อยู่หลัง `SHIFT.start_at` (ถ้าส่งมา) | `422` |
  | ผู้แจ้งมี Roster `ASSIGNED` ในเวรนั้นหนึ่งแถวพอดี | ไม่มี → `409`, มีหลายแถว → Error |

  `409` ครอบคลุมทั้งคนที่ไม่ได้อยู่เวรนั้นและการแจ้งลาซ้ำ (แถว Roster ถูก `CANCELLED` ไปแล้วจากครั้งแรก)
* การรับ Event ทำ**ทีละคำขอต่อเวร**: ล็อกแถว `SHIFT` ก่อน แล้วจึงล็อกแถว Roster ของผู้แจ้ง (ลำดับนี้เสมอ) ด้วย `SELECT ... FOR NO KEY UPDATE`
  และถือ Lock จน Commit
  * คนละคนแจ้งลาเวรเดียวกันพร้อมกัน: ถ้าไม่ล็อกเวร แต่ละคำขอจะยกเลิก Roster ของตัวเอง แต่ยังเห็นอีกคนเป็น `ASSIGNED`
    (ยังไม่ Commit) ทั้งสอง Event จึงเป็น `IGNORED` ทั้งที่เวรขาดคนแล้ว เมื่อล็อกเวร คำขอที่สองจะเห็นผลของคำขอแรกก่อนตรวจ Gap
  * คนเดียวกันแจ้งลาเวรเดียวกันซ้ำพร้อมกัน: คำขอที่สองเห็นแถว Roster ถูก `CANCELLED` แล้วได้ `409` ไม่เกิด Event หรือเคสซ้ำ
  * Lock นี้คุมเฉพาะการรับ Event ขั้นอื่นที่เขียน Roster (เช่น `execute_assignment`) ยังไม่ได้ล็อกเวร
    Lock ต่อ Shift ทั้งระบบเป็นงานหลัง Skeleton (`core/locks.py`)
* แถว Audit ของ Event (`EVENT_RECEIVED`, `UNAVAILABILITY_CREATED`) เขียน**หลัง**สร้างเคส เพื่อให้มี `case_id` ของเคสนั้น
  และขึ้นใน Timeline ของเคสตามลำดับของข้อ 7 Event ที่ `IGNORED` ทั้งสามแถวมี `case_id = NULL`
* `EVENT_IGNORED` ใช้ Actor `workflow_orchestrator` เหมือน `CASE_OPENED` (เป็นการตัดสินของระบบ) `entity_type = STAFFING_EVENTS`
  payload `event_id`, `shift_id`
* Event ที่ `IGNORED` ไม่มีรอบของ Orchestrator `event_service` จึง Commit เอง Event ที่เปิดเคส Orchestrator Commit ให้ (ข้อ 6.2)
* ตรวจ Gap ด้วย `gap_service.assess_shift(db, shift)` ซึ่งโหลด Requirement ผ่าน `requirement_service.get_current_requirement()`
  (Seam 10) ขั้น `ASSESSING` ต้องเรียกฟังก์ชันเดียวกันนี้
* ขั้นตอน 1–3 อยู่ใน Transaction เดียว ถ้าพังกลางทาง Event ไม่ถูกบันทึกเลย
* `STAFF.status` ของคนที่ลาไม่เปลี่ยน (ยังเป็น `ACTIVE`)
* เป้าหมายจำนวนคนมาจากภาระงาน: `minimum_required_staff = ceil(SHIFT.patient_count / patients_per_nurse)`
  และ `headcount_gap = max(minimum_required_staff - current_valid_staff, 0)`
  ใน Skeleton `current_valid_staff` คือคนไม่ซ้ำที่มี Roster `ASSIGNED` ในเวรนั้น
  ใน Skeleton ใช้ `HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse` เป็น Ratio เดียวทั้งโรงพยาบาล
  ทั้ง `event_service` และ `assess_staffing` โหลดด้วย `policy_service.get_hard_constraint_policy(db)`
  ซึ่งเลือก Policy `id=1` ตาม Seed แล้วส่ง `patients_per_nurse=policy.maximum_patients_per_nurse`
  ให้ `calculate_gap()`; ไม่มีค่า Default / Fallback ใน Calculator และไม่มีคอลัมน์ Ratio ใน WARD
  ค่านี้ไม่ใช่ `APPROVAL_POLICY.ratio` (ตัวคูณสำหรับ Auto-approval)
* ตรวจ Role / Skill ตาม Requirement แยกจาก Headcount; ขาดอย่างใดอย่างหนึ่งก็ถือว่ามี Gap
  แม้จำนวนคนจะเพียงพอตาม Ratio แล้วก็ตาม
* Skeleton ตรึง Hard Policy `id=1` ตลอด Demo ไม่แก้ค่าระหว่างที่มีเคสทำงาน; การเลือกเวอร์ชันตาม
  `effective_from` และ Ratio แยก Ward เป็นงานภายหลัง
* `STAFFING_GAP` ยังไม่มี FK ไป Hard Policy จึงยังย้อนดูเวอร์ชันที่ใช้คำนวณ Gap ไม่ได้โดยตรง
  แม้ `CANDIDATE_PLANS` / `SAFETY_VALIDATION` จะมี FK แล้ว; ต้องเพิ่ม FK หรือ Snapshot ก่อนรองรับการเปลี่ยน Policy ระหว่างเคส
* `PLANNED_LEAVE` (ลาที่ไม่ชนเวรที่มี Roster) ไม่สร้าง Event และ `NO_SHOW` (ระบบสร้างเองจาก `ATTENDANCE`) อยู่นอก Skeleton ดูข้อ 12

---

## 4. Case Status

| Status | ความหมาย | ประเภท | ใช้ใน Skeleton |
|---|---|---|---|
| `OPEN` | เปิดเคสแล้ว พบว่ามี Gap | อัตโนมัติ | ✅ |
| `ASSESSING` | ประเมินและบันทึก `STAFFING_GAP` | อัตโนมัติ | ✅ |
| `OPTIMIZING` | สร้างรายชื่อผู้สมัคร (Solver) | อัตโนมัติ | ✅ |
| `OUTREACH` | กำลังส่ง Offer | อัตโนมัติ (ชั่วคราว) | ✅ |
| `WAITING_RESPONSE` | รอผู้สมัครตอบ | **จุดรอ** | ✅ |
| `SAFETY_VALIDATION` | ตรวจ Hard Constraint ซ้ำหลังตอบรับ | อัตโนมัติ | ✅ |
| `WAITING_APPROVAL` | รอผู้อนุมัติ | **จุดรอ** | ✅ |
| `EXECUTING` | อัปเดต Roster | อัตโนมัติ | ✅ |
| `RESOLVED` | หาคนแทนได้และบันทึกแล้ว | สิ้นสุด | ✅ |
| `MANUAL_HANDOFF` | ส่งต่อให้คนจัดการ Workflow อัตโนมัติหยุด | หยุดอัตโนมัติ | ภายหลัง |
| `UNRESOLVED` | คนจัดการแล้วแต่แก้ไม่ได้ | สิ้นสุด | ภายหลัง |
| `FAILED` | ระบบหรือบริการขัดข้อง | สิ้นสุด | ✅ (ตาม D11) |

**จุดรอ** คือ State ที่ Orchestrator หยุด และเดินต่อเมื่อ Service ของ API ภายนอกเรียก `orchestrator.resume(db, case_id, next_status)` Service ไม่แก้ `case.status` เอง (D3)

---

## 5. Transition

### 5.1 Golden Path

| จาก | ไป | ใครสั่ง | เกิดเมื่อ |
|---|---|---|---|
| — | `OPEN` | `event_service` | Event มี Gap (ข้อ 3) |
| `OPEN` | `ASSESSING` | handler `intake_event` | ทันที |
| `ASSESSING` | `OPTIMIZING` | handler `assess_staffing` | บันทึก Gap แล้ว `result.has_gap` เป็น True (Headcount หรือ Role หรือ Skill ขาด) |
| `OPTIMIZING` | `OUTREACH` | handler `optimize` | ได้รายชื่อผู้สมัครอย่างน้อย 1 คน |
| `OUTREACH` | `WAITING_RESPONSE` | handler `contact_candidate` | ส่ง Offer แล้ว (`wait=True`) |
| `WAITING_RESPONSE` | `SAFETY_VALIDATION` | `outreach_service.record_response()` | ผู้สมัครตอบ `ACCEPT` แล้วเรียก `orchestrator.resume(db, case_id, SAFETY_VALIDATION)` |
| `SAFETY_VALIDATION` | `WAITING_APPROVAL` | handler `validate_safety` | ผ่าน Safety สร้าง Approval Request แล้ว (`wait=True`) |
| `WAITING_APPROVAL` | `EXECUTING` | `approval_service.decide()` | อนุมัติ แล้วเรียก `orchestrator.resume(db, case_id, EXECUTING)` |
| `EXECUTING` | `RESOLVED` | handler `execute_assignment` | สร้าง Roster ของผู้มาแทนแล้ว |

### 5.2 ทุก State ที่ไม่ใช่สิ้นสุด

| จาก | ไป | เกิดเมื่อ |
|---|---|---|
| ทุก State ที่ไม่ใช่สิ้นสุด | `FAILED` | Exception ระหว่าง Workflow (D11) |

Transition ของกรณีพิเศษ (Reject, Timeout, Safety ไม่ผ่าน, ไม่อนุมัติ, ไม่มีผู้สมัคร) เพิ่มในข้อนี้เมื่อ Implement

---

## 6. Signature ที่ใช้ร่วมกัน

### 6.1 Handler

```python
# workflow/handlers/base.py
class HandlerResult(BaseModel):
    next_status: CaseStatus
    wait: bool = False   # True = หยุดรอ Event ภายนอก

def handle(db: Session, case: StaffingCase) -> HandlerResult: ...
```

* **ห้าม** แก้ `case.status` เอง ให้คืนผ่าน `next_status`
* **ห้าม** เรียก `db.commit()`
* ต้องเรียก `audit_service.log()` สำหรับงานของตัวเอง (ยกเว้น `CASE_STATUS_CHANGED` ซึ่ง Orchestrator ทำ)
* `wait=True` ต้องคู่กับ `next_status` ที่เป็นจุดรอ (`WAITING_RESPONSE`, `WAITING_APPROVAL`) เท่านั้น และจุดรอต้องมี `wait=True` เสมอ
* Handler **ห้ามคืน** `next_status = FAILED` ถ้างานล้มเหลวให้โยน Exception เพื่อให้ Orchestrator บันทึก `WORKFLOW_FAILED` ตาม D11
* Handler ที่ฝ่าฝืนข้อใดข้อหนึ่ง (แก้ `case.status` เอง, `wait` ไม่ตรง, คืน `FAILED`, Transition ไม่อยู่ในข้อ 5) ทำให้เคสเป็น `FAILED` ตาม D11

### 6.2 Orchestrator

```python
# workflow/orchestrator.py
def advance(db: Session, case_id: int) -> None
def resume(db: Session, case_id: int, next_status: CaseStatus) -> None

HANDLERS: dict[CaseStatus, Handler]      # State อัตโนมัติ → Handler ที่รันใน State นั้น
```

* `advance()` ใช้หลังสร้างเคส (`event_service`) เดินจาก State ปัจจุบัน ถ้าเคสอยู่ที่จุดรอหรือ State ที่หยุดแล้วจะไม่ทำอะไร
* `resume()` ใช้ออกจากจุดรอ: ตรวจ Transition, เปลี่ยน State, บันทึก `CASE_STATUS_CHANGED` แล้วเดินต่อเหมือน `advance()`
  ถ้าเคสไม่ได้อยู่ที่จุดรอหรือ Transition ไม่ถูกต้อง จะโยน `InvalidTransitionError` โดยไม่แตะเคสและ**ไม่**ทำให้เคสเป็น `FAILED`
  (เกิดเมื่อสองคำขอของเคสเดียวกันมาพร้อมกัน เช่น กด `ACCEPT` หรือกดอนุมัติสองครั้งติดกัน) Route ควรตอบ `409`
  `resume()` ไม่รับ `next_status = FAILED` เช่นกัน เพราะ `FAILED` ตั้งได้จากเส้นทาง D11 ของ Orchestrator เท่านั้น
  ก่อนตรวจ `resume()` จะ Flush งานที่ผู้เรียกค้างไว้ (เช่น แถว Outreach และ Audit `OFFER_ACCEPTED`) ดังนั้นเมื่อได้ `InvalidTransitionError`
  ผู้เรียก**ห้าม Commit** ให้ตอบ `409` แล้วปล่อยให้ Session Rollback (`get_db` ปิด Session ซึ่ง Rollback ให้อยู่แล้ว)
* ล็อกแถวของเคสด้วย `SELECT ... FOR NO KEY UPDATE` คำขอที่สองของเคสเดียวกันจะรอจนรอบแรกจบ
  (ไม่ใช้ `FOR UPDATE` เพราะแถว Audit ที่ผู้เรียก Insert ไว้ก่อนถือ Lock `KEY SHARE` บนเคสผ่าน FK สองคำขอแบบนี้จะ Deadlock กัน)
* ลำดับ Lock ทั้งระบบ: แถว `SHIFT` และ `ROSTER_ASSIGNMENT` (รับ Event) → แถวเคส → แถว `STAFF` (Solver ข้อ 8)
  แถว `STAFF` มาท้ายสุดเสมอและล็อกเรียงตาม `id` ห้ามโค้ดใหม่ล็อก `STAFF` ก่อนแล้วค่อยล็อกเคสหรือเวร ไม่งั้นจะ Deadlock
* ไม่มีเคส ID นั้น โยน `CaseNotFoundError`
* D11 ทำด้วย Savepoint: รอบที่พังถูก Rollback กลับไปที่จุดเริ่มรอบ งานที่ผู้เรียกทำไว้ก่อนใน Transaction เดียวกัน
  (Event, เคส, คำตอบของผู้สมัคร) ยังอยู่ จากนั้นเคสเป็น `FAILED` พร้อม `CASE_STATUS_CHANGED` และ `WORKFLOW_FAILED`
  (payload: `from`, `failed_at`, `error_type` ไม่เก็บข้อความ Error เพราะอาจมีข้อมูลต้องห้าม) แล้ว Commit
* ทั้งสองฟังก์ชัน**ไม่โยน** Exception ของ Handler ต่อ ผู้เรียกดูผลจาก `case.status` รายละเอียดอยู่ใน Log ของ Server
  ยกเว้นกรณีเดียว: ถ้าการบันทึก `FAILED` เองล้มเหลว (เช่น ไม่มี Actor `workflow_orchestrator`) Exception นั้นจะหลุดออกมาและไม่มีอะไรถูก Commit
* ผู้เรียกไม่ต้อง Commit ก่อนเรียก และไม่ต้อง Commit หลังเรียก Orchestrator Commit ให้ทั้ง Transaction

* เดินต่อจนเจอจุดรอหรือ State สิ้นสุด แล้ว Commit
* ตรวจ `next_status` ของ Handler กับ `domain/workflow/transitions.py` ก่อนเปลี่ยน State (ตารางเดียวของข้อ 5)
* ทุกการเปลี่ยน State: บันทึก `CASE_STATUS_CHANGED` ด้วย Actor `workflow_orchestrator`
* ห่อทั้งรอบด้วย try/except ตาม D11

### 6.3 Audit Service

```python
# services/audit_service.py
def log(db: Session, *, case_id: int | None, actor_id: int,
        action: AuditAction, entity_type: EntityType, entity_id: int | None,
        payload: dict) -> None
```

```python
# services/actor_service.py
def component_id(db: Session, name: ActorName) -> int        # Actor ที่ไม่ใช่คน
def user_id(db: Session, staff_id: int) -> int               # Actor ของพนักงาน
```

* `component_id()` รับเฉพาะ `ActorName` และทั้งสองฟังก์ชันโยน `ActorNotFoundError` เมื่อไม่มี Actor (Seed ไม่ครบ) ไม่คืน `None`
* `actor_service` และ `get_demo_user` อ่านด้วย SELECT และ `SessionLocal` ปิด autoflush แถว `ACTORS` / `STAFF` ที่เพิ่งเพิ่มใน Session เดียวกันต้อง `db.flush()` ก่อนจึงจะหาเจอ
* `log()` **ห้าม Commit เอง**
* `action` และ `entity_type` ต้องเป็น Enum ห้ามพิมพ์ข้อความเอง
* `payload` ห้ามมีข้อมูลผู้ป่วยรายบุคคล เหตุผลการลาแบบข้อความอิสระ หรือ `password_hash`
* Composite Key (เช่น `STAFF_SKILL`) ยังไม่ต้อง Audit ใน Skeleton จึงยังไม่ต้องตัดสินรูปแบบ `entity_id`

### 6.4 จุดส่งต่อระหว่างขั้น (Seam)

แต่ละขั้นของขั้นที่ 4 หาแถวที่ขั้นก่อนหน้าเขียนไว้ตามกติกานี้ เพื่อให้ทำขนานกันได้โดยไม่ต้องรอโค้ดของกัน

* ที่เขียนว่า **หนึ่งแถวพอดี** ถ้าเจอ 0 แถวหรือหลายแถวถือเป็น Error ห้ามหยิบแถวแรกมาใช้เงียบ ๆ
  ใน Handler ให้โยน Exception (D11 เปลี่ยนเป็น `FAILED`) ใน Route ให้ตอบเป็น HTTP Error
* Model ยังไม่มี ORM `relationship()` สักตัว ให้โหลดหรือ Join ผ่านคอลัมน์ FK เช่น โหลด `CANDIDATE_PLANS` จาก `item.plan_id`
* "ล่าสุด" หมายถึง `id` มากสุดเสมอ ห้ามเรียงด้วยคอลัมน์เวลา เพราะ Clock ของ Demo หยุดนิ่งหลัง Reset ทุกแถวจึงมีเวลาเท่ากัน

| # | Seam | เจ้าของ | กติกา |
|---|---|---|---|
| 1 | Plan ล่าสุด | คน 2 → คน 3 | `CANDIDATE_PLANS` ที่ `case_id = case.id` เรียง `id` จากมากไปน้อย เอาแถวแรก ไม่เจอ → Error |
| 2 | Plan → Outreach | คน 3 | `CANDIDATE_ITEMS` ที่ `rank = 1` ใน Plan นั้น หนึ่งแถวพอดี |
| 3 | Respond | คน 3 | ทำตามลำดับ: (1) ผู้ตอบคือ `user.staff.id` จาก `X-Demo-User` Body ไม่มี Outreach ID (2) `CANDIDATE_OUTREACH` ที่ `status = SENT` บนเคสที่ `status = WAITING_RESPONSE` และ Join ไปที่ Item ซึ่ง `staff_id = user.staff.id` หนึ่งแถวพอดี ไม่เจอ → `409` (ตอบไปแล้วหรือไม่มี Offer) เจอหลายแถว → Error เพราะ Skeleton ส่ง Offer เดียว (3) `REJECT` → `422` ไม่เขียน DB (ข้อ 9.2) (4) `ACCEPT` → `status = ACCEPTED`, `response_at = clock.now()` แล้วเรียก `orchestrator.resume(db, case_id, SAFETY_VALIDATION)` |
| 4 | Outreach → Safety | คน 3 → คน 2 | โหลดผ่าน `outreach_service.get_accepted_outreach(db, case_id)` ต้องมี `CANDIDATE_OUTREACH` ของเคสที่ `status = ACCEPTED` หนึ่งแถวพอดี ไม่เจอ → `NoResultFound`, หลายแถว → `MultipleResultsFound` ให้ Handler ปล่อย Error ไปยัง D11 |
| 5 | Safety → Approval Request | คน 2 | `case_id` = เคสนั้น `candidate_item_id` = Item ของ Outreach ที่ตอบรับ โหลด Plan จาก `item.plan_id` แล้วตรวจ `plan.case_id == case.id` (FK สองตัวไม่ได้รับประกันข้อนี้) ตั้ง `approval_mode = MANUAL`, `required_approver_role` = `id` ของ Role ชื่อ `HEAD_NURSE` (ค้นด้วยชื่อ), `is_pending = true`, `requested_at = clock.now()` |
| 6 | รายการรออนุมัติ | คน 3 | `GET /approvals?pending=true` คืนแถวที่ `is_pending = true` เรียงด้วย `id` จากน้อยไปมาก ใน Skeleton เคสหนึ่งมีได้ไม่เกินหนึ่งแถว |
| 7 | Decide | คน 3 | ตรวจตามลำดับ: ไม่มี Request ID นั้น → `404`; `user.staff.role_id != required_approver_role` → `403` (`get_demo_user` ไม่ตรวจ Role ดูข้อ 9); ไม่ได้ Pending → `409`; `approved = false` → `422` ไม่เขียน DB (ข้อ 9.2) ถ้าอนุมัติ: `approver_id = user.staff.id`, `is_approved = true`, `decided_at = clock.now()`, `is_pending = false` แล้วเรียก `orchestrator.resume(db, case_id, EXECUTING)` |
| 8 | Approval → Execute | คน 3 (คน 2 ถ้าย้ายงาน Roster) | Request ของเคสที่ `is_pending = false` **และ** `is_approved = true` หนึ่งแถวพอดี สร้าง Roster จาก Item ของ Request นั้น: `staff_id = item.staff_id`, `shift_id = item.proposed_shift_id`, `status = ASSIGNED`, `assignment_type = REPLACEMENT`, `candidate_source = item.source` |
| 9 | Timeline | คน 1 | `GET /cases/{id}/audit` เรียงด้วย `id` |
| 10 | Requirement ของเวร | คน 1 (รับ Event + Gap) | `STAFFING_REQUIREMENTS` ที่ `shift_id` ของเวรนั้น เรียง `id` จากมากไปน้อย เอาแถวแรก ไม่เจอ → Error ตารางนี้ไม่มี Unique ที่ `shift_id` จึงมีหลายเวอร์ชันได้ (Seed มีเวรละแถว) การรับ Event และ `assess_staffing` ต้องโหลดผ่าน**ฟังก์ชันเดียวกัน** เพื่อให้เห็น Requirement ตัวเดียวกันเสมอ แถว Gap เก็บ `id` นี้ใน `staffing_requirement_id` |

Seam 4 Flush คำตอบที่ค้างอยู่ก่อนค้นหา เพื่อรองรับ `autoflush=False`
Lookup ไม่สร้างแถวใหม่ ไม่ Commit ไม่เขียน Audit และไม่เพิ่ม Row Lock

### 6.5 คอลัมน์เวลา

คอลัมน์ที่บันทึกว่าขั้นนั้นทำงานเมื่อไร ต้องใส่ค่า `clock.now()` เองโดยขั้นที่เขียนแถว ห้ามใช้ `datetime.now()` (D10)

| คอลัมน์ | Null | ใครใส่ | ถ้าลืม |
|---|---|---|---|
| `STAFFING_GAP.computed_at` | NOT NULL | Gap | `IntegrityError` → เคส `FAILED` |
| `CANDIDATE_PLANS.generated_at` | NOT NULL | Solver | `IntegrityError` → เคส `FAILED` |
| `SAFETY_VALIDATION.validated_at` | NOT NULL | Safety | `IntegrityError` → เคส `FAILED` |
| `APPROVAL_REQUEST.requested_at` | NOT NULL | Safety | `IntegrityError` → เคส `FAILED` |
| `CANDIDATE_OUTREACH.sent_at` | NULL | Outreach | ไม่ Error แต่ข้อมูลหาย |
| `CANDIDATE_OUTREACH.response_at` | NULL | Respond | ไม่ Error แต่ข้อมูลหาย |
| `APPROVAL_REQUEST.decided_at` | NULL | Decide | ไม่ Error แต่ข้อมูลหาย |

คอลัมน์เวลาอีกสองชนิดไม่ต้องใส่ตามตารางนี้

* `created_at` ใส่ให้เองด้วย `default` และ `updated_at` ด้วย `default` กับ `onupdate`
* คอลัมน์เวลาที่มีความหมายของตัวเองทำตามสเปกของมัน เช่น `STAFFING_CASES.required_replacement_time = SHIFT.start_at`,
  `STAFFING_EVENTS.occurred_at` และเวลาของ `STAFF_UNAVAILABILITY` ตามข้อ 3

---

## 7. Audit ของ Golden Path

| Action | ใครเขียน | Actor | entity_type | payload ขั้นต่ำ |
|---|---|---|---|---|
| `EVENT_RECEIVED` | `event_service` | user (คนที่ลา) | STAFFING_EVENTS | `event_type`, `shift_id`, `staff_id` |
| `UNAVAILABILITY_CREATED` | `event_service` | user (คนที่ลา) | STAFF_UNAVAILABILITY | `unavailability_id`, `staff_id`, `reason`, `start_at`, `end_at` |
| `CASE_OPENED` | `event_service` | `workflow_orchestrator` | STAFFING_CASES | `event_id`, `shift_id`, `headcount_gap` |
| `CASE_STATUS_CHANGED` | Orchestrator | `workflow_orchestrator` | STAFFING_CASES | `from`, `to` |
| `GAP_ASSESSED` | `assess_staffing` | `staffing_gap_assessment_agent` | STAFFING_GAP | `gap_id`, `headcount_gap`, `role_gaps`, `skill_gaps` |
| `SOLVER_EXECUTED` | `optimize` | `constraint_fair_scheduling_agent` | CANDIDATE_PLANS | `plan_id`, `solver_status`, `candidate_count` |
| `OFFER_SENT` | `contact_candidate` | `outreach_agent` | CANDIDATE_OUTREACH | `outreach_id`, `staff_id`, `channel` |
| `OFFER_ACCEPTED` | `outreach_service` | user (ผู้สมัคร) | CANDIDATE_OUTREACH | `outreach_id`, `staff_id` |
| `SAFETY_PASSED` | `validate_safety` | `safety_rule_engine` | SAFETY_VALIDATION | `validation_id`, `staff_id` |
| `APPROVAL_REQUESTED` | `validate_safety` | `workflow_orchestrator` | APPROVAL_REQUEST | `approval_id`, `approval_mode` |
| `APPROVAL_APPROVED` | `approval_service` | user (ผู้อนุมัติ) | APPROVAL_REQUEST | `approval_id`, `reason` |
| `ASSIGNMENT_CREATED` | `execute_assignment` | `workflow_orchestrator` | ROSTER_ASSIGNMENT | `assignment_id`, `staff_id`, `assignment_type` |
| `CASE_RESOLVED` | `execute_assignment` | `workflow_orchestrator` | STAFFING_CASES | `assignment_ids` |

ลำดับนี้คือ `GOLDEN_PATH_AUDIT_ACTIONS` ใน `enums.py` ที่ E2E Test ใช้ตรวจ

---

## 8. Stub ของแต่ละขั้น

| ขั้น | Stub ทำอะไร | ตารางที่เขียน |
|---|---|---|
| Event | ตามข้อ 3 (ของจริงตั้งแต่ Skeleton) | STAFFING_EVENTS, STAFF_UNAVAILABILITY, ROSTER_ASSIGNMENT, STAFFING_CASES |
| Gap | โหลด Hard Policy `id=1` ผ่าน `policy_service`; ใช้ `gap_calculator` เทียบคนที่ `ASSIGNED` กับ `ceil(patient_count / policy.maximum_patients_per_nurse)` และ Role / Skill กับ Requirement; ใช้ `result.has_gap` | STAFFING_GAP (+ ROLE, SKILL) |
| Solver | เริ่มจากผู้สมัคร 3 คนตายตัวตาม Golden Case แล้วตัดคนที่ไม่ `ACTIVE`, มี Roster ในเวรของเคสที่สถานะอยู่ใน `COMMITTED_ROSTER_STATUSES` หรือมี `STAFF_UNAVAILABILITY` ชนช่วงเวลาของเวรนั้น (`end_at` เป็น NULL = ไม่พร้อมตั้งแต่ `start_at`) ออก กติกาอยู่ใน `services/availability_service.py` ใช้ร่วมกับ Safety ไม่เช็กเวรอื่นที่เวลาชนกัน (Hard Rules ของจริงทำภายหลัง) กฎข้อที่ 4 เฉพาะ Solver: ตัดคนที่มี Offer ค้างอยู่ คือ `CANDIDATE_OUTREACH` ที่ `SENT` (ของเคสไหนก็ได้ เพราะ Seam 3 ต้องเจอ Offer `SENT` ของผู้ตอบหนึ่งแถวพอดี ถ้ามีสองแถว ทั้งสองเคสจะค้างที่ `WAITING_RESPONSE`) หรือ `ACCEPTED` ที่เคสยังไม่อยู่ใน `AUTOMATION_STOPPED_STATUSES` กฎนี้อยู่ใน `optimization_service` ไม่อยู่ใน `availability_service` เพราะผู้สมัครที่ Safety เช็กมี Offer `ACCEPTED` ของตัวเองเสมอ ก่อนเช็กกติกา Solver ล็อกแถว `STAFF` ของผู้สมัคร (`FOR NO KEY UPDATE` เรียงตาม `id`) จนรอบนั้น Commit ที่ `WAITING_RESPONSE` เคสที่วางแผนพร้อมกันจะรอแล้วเห็น Offer ของเคสแรก จึงไม่เลือกคนเดียวกัน ใส่ `rank` ใหม่ 1, 2, 3 ต่อกัน `solver_status = FEASIBLE`, `solver_version = "stub"` ถ้าไม่เหลือใครเลย โยน `NoCandidatesError` โดยไม่เขียน Plan เคสเป็น `FAILED` ตาม D11 (ข้อ 5 ยังไม่มี Transition ของกรณีนี้) | CANDIDATE_PLANS, CANDIDATE_ITEMS |
| Outreach | สร้าง Outreach ให้อันดับ 1 สถานะ `SENT` ไม่ส่ง LINE จริง | CANDIDATE_OUTREACH |
| Response | LINE Simulator ส่ง `ACCEPT` → `ACCEPTED` | CANDIDATE_OUTREACH |
| Safety | ตรวจว่า `proposed_shift_id` ของ Item ที่ตอบรับเป็นเวรของเคส (Execute จัดเวรตาม `proposed_shift_id` ตาม Seam 8) ไม่ตรงโยน `ProposedShiftMismatchError` แล้วเช็กผู้สมัครที่ตอบรับซ้ำด้วยกติกา 3 ข้อเดียวกับ Solver (`services/availability_service.py`: `ACTIVE`, ไม่มี Roster ในเวรของเคสที่สถานะอยู่ใน `COMMITTED_ROSTER_STATUSES`, ไม่มี `STAFF_UNAVAILABILITY` ชนเวร) เพราะสถานการณ์เปลี่ยนได้ระหว่างรอคำตอบ ไม่ผ่านข้อใด โยน Exception ที่ชื่อบอกสาเหตุ (`StaffNotActiveError`, `StaffAlreadyOnShiftError`, `StaffUnavailableError`) โดยไม่เขียน SAFETY_VALIDATION และ APPROVAL_REQUEST เคสเป็น `FAILED` ตาม D11 ถ้าผ่าน: `is_passed = true`, `validation_snapshot = {}` การบันทึก `is_passed = false` + `SAFETY_FAILED` แล้วไปผู้สมัครคนถัดไป รอ Transition ในข้อ 5 | SAFETY_VALIDATION, APPROVAL_REQUEST |
| Approval | `approval_mode = MANUAL` ผู้อนุมัติกดในหน้าเว็บ | APPROVAL_REQUEST |
| Roster | สร้างแถว `ASSIGNED` + `REPLACEMENT` + `SAME_WARD` | ROSTER_ASSIGNMENT |

`CANDIDATE_PLANS` และ `SAFETY_VALIDATION` อ้าง Policy แบบ NOT NULL จึงต้อง Seed `HARD_CONSTRAINT_POLICY` และ `SOFT_CONSTRAINT_POLICY` อย่างละ 1 แถว แม้ Stub ยังไม่ได้ใช้ค่าข้างใน

---

## 9. API

| Method | Path | ใช้ทำอะไร | เจ้าของ |
|---|---|---|---|
| POST | `/events` | รับ Event ตามข้อ 3 | คน 1 |
| GET | `/cases/{id}` | สถานะเคส + Gap + Candidate | คน 1 |
| GET | `/cases/{id}/audit` | Timeline ของเคส | คน 1 |
| GET | `/demo/line-sim/offers?staff_id=` | Offer ที่ผู้สมัครได้รับ | คน 3 |
| POST | `/demo/line-sim/respond` | ผู้สมัครตอบ `ACCEPT` / `REJECT` | คน 3 |
| GET | `/approvals?pending=true` | รายการรออนุมัติ | คน 3 |
| POST | `/approvals/{id}/decision` | อนุมัติ / ไม่อนุมัติ | คน 3 |
| GET | `/roster?shift_id=` | ตารางเวรของเวรนั้น | คน 3 |
| POST | `/demo/reset` | ล้าง DB โหลด Golden Case ตั้ง Clock ใหม่ | คน 1 |

ทุก Request ที่ต้องรู้ตัวผู้ใช้ส่ง Header `X-Demo-User: <staff_id>` (D9)

Route ที่ต้องรู้ตัวผู้ใช้ประกาศ Dependency จาก `api/dependencies.py`

```python
# api/dependencies.py
def get_db() -> Iterator[Session]                       # Session ต่อ Request ไม่ Commit ให้
def get_demo_user(db, x_demo_user) -> CurrentUser       # ผู้ใช้จาก X-Demo-User

class CurrentUser:                                      # frozen dataclass
    staff: Staff                                        # แถวพนักงานของ Session เดียวกับ db
    actor_id: int                                       # ACTORS.id ของพนักงานคนนี้

DbSession = Annotated[Session, Depends(get_db)]
DemoUser = Annotated[CurrentUser, Depends(get_demo_user)]

@router.post("/{approval_id}/decision")                 # routes/approvals.py มี Prefix /approvals แล้ว
def decide(approval_id: int, db: DbSession, user: DemoUser):
    approver_id = user.staff.id
    audit_service.log(db, actor_id=user.actor_id, ...)
```

* ใช้ `user.staff.id` เป็น `approver_id` และ `user.actor_id` เป็น Actor ของ Audit ได้เลย Route **ไม่ต้อง**เรียก `actor_service.user_id()` ซ้ำ เพราะ `get_demo_user` อ่าน Staff กับ Actor มาใน Query เดียวแล้ว
* `actor_service.user_id()` ยังใช้สำหรับโค้ดที่มีแค่ `staff_id` ไม่ได้มาจาก Request เช่น Handler ที่เขียน Audit แทนพนักงาน
* ตอบ `401` เมื่อไม่มี Header, ค่าไม่ใช่เลขจำนวนเต็มบวกในช่วง `bigint` (1 ถึง 9223372036854775807), ไม่มีพนักงาน ID นั้น, พนักงานไม่ `ACTIVE` หรือพนักงานไม่มีแถวใน `ACTORS`
* ไม่ตรวจ Role การจำกัดว่าใครอนุมัติได้เป็นงานของ Route นั้นเอง

### 9.1 ไฟล์ Route และ Error ที่ใช้ร่วมกัน

Router ทุกตัวของขั้นที่ 4 มีไฟล์และลงทะเบียนใน `main.py` ไว้แล้ว เจ้าของเพิ่ม Route ในไฟล์ของตัวเอง **ไม่ต้องแก้ `main.py`**

| ไฟล์ | Prefix |
|---|---|
| `api/routes/events.py` | `/events` |
| `api/routes/cases.py` | `/cases` |
| `api/routes/approvals.py` | `/approvals` |
| `api/routes/roster.py` | `/roster` |
| `api/routes/line_sim.py` | `/demo/line-sim` |
| `api/routes/demo.py` | `/demo` (มีแค่ `/demo/reset`) |

Error สองตัวนี้ถูกแปลงเป็น HTTP ให้ที่เดียวใน `api/exception_handlers.py` Route ไม่ต้อง `try/except` เอง

| Exception | ตอบ | เกิดเมื่อ |
|---|---|---|
| `InvalidTransitionError` | `409` | `orchestrator.resume()` ปฏิเสธ เมื่อสองคำขอของเคสเดียวกันมาพร้อมกัน (Race): ทั้งคู่ผ่านการค้นแถวก่อนที่ตัวใดจะ Commit แล้วตัวที่สองถูกปฏิเสธ |
| `CaseNotFoundError` | `404` | ไม่มีเคส ID นั้น |

Handler นี้เป็นตาข่ายชั้นสุดท้าย ไม่ได้แทนการตรวจใน Route: คำขอซ้ำที่มา**หลัง**คำขอแรกเสร็จแล้ว ต้องถูกจับด้วยการค้นแถวของ Seam 3 และ 7 (ไม่เจอ Offer ที่ `SENT` หรือ Request ไม่ได้ Pending → `409`) ก่อนถึง `resume()`

ทั้งสองกรณี Route **ห้าม Commit** `get_db` ปิด Session ซึ่ง Rollback งานที่ Flush ไปแล้วให้เอง Exception อื่นตอบ `500` ตามปกติ

### 9.2 ขอบเขตของ Skeleton: มีแต่คำตอบของ Golden Path ที่ทำให้เคสเดิน

ข้อ 5 ยังไม่มี Transition ของการปฏิเสธและการไม่อนุมัติ จนกว่าจะเพิ่ม ให้ทำดังนี้ โดยการตรวจที่มาก่อนใน Seam 3 และ 7 ยังทำตามเดิม

* `POST /demo/line-sim/respond`: ไม่มี Offer ที่เปิดอยู่ → `409` ถ้ามี Offer และคำตอบคือ `REJECT` → `422` ไม่เขียนอะไรลง DB
* `POST /approvals/{id}/decision`: `404` / `403` / `409` ตาม Seam 7 ถ้าผ่านทั้งหมดและ `approved = false` → `422` ไม่เขียนอะไรลง DB

Seam 3 ใช้ `outreach_service.record_response()` โดย Route ส่ง `user.staff.id` และ
`user.actor_id` จาก Dependency Body รับแค่ `{"response": "ACCEPT"}` หรือ `{"response": "REJECT"}`
ไม่รับ `outreach_id` / `staff_id` หรือฟิลด์อื่น Service ค้น Offer ที่ `SENT` ของผู้ตอบผ่าน
`CANDIDATE_ITEMS.staff_id` และเฉพาะเคสที่ `STAFFING_CASES.status = WAITING_RESPONSE`
Offer ที่ยังเป็น `SENT` บนเคสสถานะอื่นไม่นับและไม่ขวางการตอบ Offer ของเคสที่กำลังรอคำตอบ
Service ล็อกเฉพาะแถว Outreach ตามลำดับ `id` ก่อนตรวจคำตอบ
ลำดับการล็อกคือ **Outreach ก่อน Case** (`resume()` ล็อก Case): งาน Timeout ในอนาคตต้องใช้ลำดับเดียวกันเพื่อไม่ให้ Deadlock
ไม่เจอหรือเจอหลายแถวตอบ `409` โดยไม่เขียนอะไร การ `ACCEPT` ตั้ง `response_at = clock.now()`
เขียน `OFFER_ACCEPTED` ด้วย Actor ของผู้ตอบ แล้วเรียก `resume(..., SAFETY_VALIDATION)`
คำขอซ้ำหลังคำขอแรก Commit ตอบ `409` และไม่เขียน Audit ซ้ำ Service / Route ไม่ Commit เอง

เส้นทางปฏิเสธแต่ละเส้นจะได้ Transition การเขียน DB และ Status Code ของตัวเองเมื่อ Implement หลัง Skeleton

**Seam 7 — `POST /approvals/{id}/decision`**

Body รับ `approved` เป็น JSON Boolean และ `reason` เป็น String หรือ `null` (ไม่ส่งเท่ากับ `null`)
ไม่รับฟิลด์อื่น ตัวตนและ Role มาจาก `X-Demo-User` เท่านั้น ID ต้องเป็นจำนวนเต็มบวกในช่วง PostgreSQL bigint
`approval_service.decide()` ตรวจตาม Seam 7 ก่อนเขียนข้อมูล และล็อก **Approval Request ก่อน Case**
(`resume()` ล็อก Case) งาน Timeout / ผู้เขียนข้อมูลอื่นในอนาคตต้องใช้ลำดับเดียวกันเพื่อเลี่ยง Deadlock
การอนุมัติตั้ง `approver_id`, `is_approved=true`, `is_pending=false`, `reason`, `decided_at=clock.now()`
เขียน `APPROVAL_APPROVED` ด้วย Actor ของผู้อนุมัติ แล้วเรียก `resume(..., EXECUTING)`
Service / Route ไม่ Commit และไม่แก้ `case.status`; Error จาก `resume()` ต้องปล่อยให้ Request Rollback
ถ้า Execution ล้มเหลวแต่ Orchestrator บันทึก `FAILED` ได้ ให้ตอบ `200` พร้อมสถานะ `FAILED` และเก็บผลอนุมัติไว้
การสร้าง Roster ใน Seam 8 เป็นงานคน 2 และอยู่นอก PR นี้

### 9.3 รูปแบบคำตอบ

Workflow ที่จบเป็น `FAILED` ถือเป็นผลที่บันทึกแล้ว ให้ตอบ `200` / `201` และใส่สถานะใน Body
ถ้า Orchestrator บันทึก `FAILED` เองไม่สำเร็จ Exception จะหลุดออกมาและ Route ตอบ `500` ตามปกติ (ข้อ 6.2)

การตั้งชื่อ: `GET` ที่คืน Resource ชนิดเดียวใช้ `id` / `status` เฉย ๆ สำหรับฟิลด์ของ Resource นั้น
`POST` ที่คำตอบครอบคลุมหลาย Resource ใส่ Prefix ทุกฟิลด์ (`case_id`, `case_status`, ...)

เวลา: ทุกค่าเวลาในคำตอบของ API เป็น ISO 8601 ที่มี Offset `+07:00` เสมอ เช่น `2026-10-09T21:00:00+07:00`
PostgreSQL คืน `timestamptz` ตาม Timezone ของ Session ซึ่งเป็น UTC ฟิลด์เวลาใน Schema ของ API จึงต้องใช้ชนิด `AppDatetime`
(`app/schemas/types.py`) ซึ่งแปลงเป็น `+07:00` ให้ ห้ามใช้ `datetime` เฉย ๆ ไม่งั้นแถวที่อ่านจาก DB จะออกเป็น `...Z`
เวลาที่ใส่ใน `payload` ของ Audit เป็นข้อความ ผู้เขียนต้องแปลงเองด้วย `.astimezone(clock.APP_TIMEZONE).isoformat()`

**คำตอบของ POST**

| Route | Code | Body |
|---|---|---|
| `POST /events` | `201` | `{event_id, event_status, case_id, case_status}` เมื่อ Event เป็น `IGNORED` ทั้ง `case_id` และ `case_status` เป็น `null` คำขอที่ถูกปฏิเสธตอบ `401` / `404` / `409` / `422` ตามข้อ 3 |
| `POST /demo/line-sim/respond` | `200` | `{outreach_id, outreach_status, case_id, case_status}` |
| `POST /approvals/{id}/decision` | `200` | `{approval_id, is_approved, case_id, case_status}` |

**Key ของ GET ที่ E2E Test อ่านอยู่แล้ว** (`walking-skeleton.md` ขั้นที่ 6) ต้องตรงตามนี้ ไม่งั้น E2E แดง

| Route | รูปแบบที่ E2E ต้องการ | จุดที่พลาดง่าย |
|---|---|---|
| `GET /cases/{id}` | Object ที่มี `status` | ใช้ `case_status` ตามคำตอบของ POST |
| `GET /cases/{id}/audit` | JSON **List** ที่ชั้นบนสุด แต่ละตัวมี `action` เรียงด้วย `id` (Seam 9) | ห่อ List ด้วย `{items: [...]}` |
| `GET /approvals?pending=true` | JSON **List** ที่ชั้นบนสุด แต่ละตัวมี `id` | ใช้ `approval_id` ตามคำตอบของ Decision |

ฟิลด์ที่เหลือของ `GET` แต่ละตัว เจ้าของ Route ส่งร่างรายการฟิลด์ให้ Frontend **ตั้งแต่เริ่มทำ** ไม่ต้องรอ Backend เสร็จ
แล้วเขียนรูปแบบสุดท้ายลงข้อนี้ใน PR ของ Route ตัวเอง Frontend ทำตามข้อนี้

**เมื่อ Conflict ในข้อ 9:** หลาย PR จะเติมรูปแบบของ `GET` ที่นี่ ให้เก็บไว้ทั้งสองฝั่ง

**`GET /cases/{id}`** (คน 1) ไม่ต้องมี `X-Demo-User` ไม่มีเคส ID นั้น → `404` ID นอกช่วง `bigint` (1 ถึง 9223372036854775807) → `422`

```json
{
  "id": 1,
  "status": "WAITING_RESPONSE",
  "event_id": 1,
  "shift_id": 1,
  "required_replacement_time": "2026-10-09T23:00:00+07:00",
  "created_at": "2026-10-09T21:00:00+07:00",
  "updated_at": "2026-10-09T21:00:00+07:00",
  "gap": {
    "id": 1,
    "headcount_gap": 1,
    "computed_at": "2026-10-09T21:00:00+07:00",
    "roles": [{"id": 1, "name": "RN", "required_count": 5, "current_count": 4, "gap_count": 1}],
    "skills": [{"id": 1, "name": "ICU", "required_count": 2, "current_count": 2, "gap_count": 0}]
  },
  "candidates": [
    {"candidate_item_id": 1, "rank": 1, "staff_id": 201, "first_name": "Arunee", "last_name": "Demo",
     "source": "SAME_WARD", "outreach_status": "SENT"}
  ]
}
```

* `gap` เป็น `null` จนกว่าขั้น `ASSESSING` จะบันทึก `STAFFING_GAP` ถ้ามีหลายแถวใช้แถวที่ `id` มากสุด
  ใน `roles` / `skills` ฟิลด์ `id` คือ Role ID / Skill ID
* `candidates` เป็น `[]` จนกว่า Solver จะบันทึก Plan ใช้ Plan ที่ `id` มากสุดของเคส (Seam 1) เรียงตาม `rank`
* `outreach_status` เป็น `null` จนกว่าจะมี Outreach ของผู้สมัครคนนั้น ถ้ามีหลายแถวใช้แถวที่ `id` มากสุด

**`GET /cases/{id}/audit`** (คน 1) ไม่ต้องมี `X-Demo-User` ไม่มีเคส ID นั้น → `404` ID นอกช่วง `bigint` (1 ถึง 9223372036854775807) → `422`

```json
[
  {
    "id": 3,
    "action": "CASE_OPENED",
    "actor_id": 2,
    "actor_name": "workflow_orchestrator",
    "actor_type": "component",
    "entity_type": "STAFFING_CASES",
    "entity_id": 1,
    "payload": {"event_id": 1, "shift_id": 1, "headcount_gap": 1},
    "created_at": "2026-10-09T21:00:00+07:00"
  }
]
```

* เป็น List ที่ชั้นบนสุด มีเฉพาะแถวที่ `case_id` ตรงกับเคส เรียงด้วย `id` จากน้อยไปมาก (Seam 9) เคสที่ยังไม่มี Audit คืน `[]`
* `actor_name` ของ Actor ที่เป็นพนักงานคือ `str(staff.id)` เช่น `"105"`

---

## 10. Golden Case

### 10.1 สถานการณ์

พยาบาล RN ในหอ ICU แจ้งลาป่วยกะทันหันก่อนเวรดึก 2 ชั่วโมง ทำให้กำลังคนต่ำกว่าที่ต้องการ 1 คน ทักษะ ICU ยังครบ ระบบหาคนแทนจากหอเดียวกันได้ในผู้สมัครคนแรก

### 10.2 ข้อมูล Seed

**เวลา** Clock ของ Demo = `D 21:00 +07:00` (D = วันที่ Demo)

**Master Data**

| ตาราง | ข้อมูล |
|---|---|
| WARD | 1 = ICU |
| ROLE | 1 = RN, 2 = HEAD_NURSE |
| SKILL | 1 = ICU, 2 = BLS |

**STAFF** (ทั้งหมด `ACTIVE`, `home_ward_id = 1`)

Seed ใช้ชื่อภาษาอังกฤษตามตารางด้านล่าง และ `last_name = "Demo"` ทุกคนสำหรับข้อมูลสาธิต

| id | ชื่อ | role | skill | บทบาทใน Demo |
|---|---|---|---|---|
| 101 | Pimchanok | RN | ICU, BLS | อยู่เวร |
| 102 | Thanaphon | RN | ICU | อยู่เวร |
| 103 | Wanna | RN | BLS | อยู่เวร |
| 104 | Kitti | RN | BLS | อยู่เวร |
| 105 | Sudarat | RN | BLS | อยู่เวร **และแจ้งลา** |
| 201 | Arunee | RN | ICU, BLS | ผู้สมัครอันดับ 1 **ตอบรับ** |
| 202 | Phanu | RN | BLS | ผู้สมัครอันดับ 2, อยู่เวร 2 |
| 203 | Chonthicha | RN | ICU | ผู้สมัครอันดับ 3, อยู่เวร 2 |
| 900 | Malai | HEAD_NURSE | — | ผู้อนุมัติ |

**SHIFT**
* 1 = ICU, `NIGHT`, `D 23:00` – `D+1 07:00`, `patient_count = 10`
* 2 = ICU, `DAY`, `D+2 07:00` – `D+2 15:00`, `patient_count = 2` (ใช้กับ Test ข้อ 10.4 เท่านั้น)

**STAFFING_REQUIREMENTS**
* 1 = shift 1, `required_staff = 5`, `minimum_staff = 4`, ROLE: RN = 5, SKILL: ICU = 2
* 2 = shift 2, `required_staff = 1`, `minimum_staff = 1`, ROLE: RN = 1, ไม่มี SKILL

Golden Case ใช้ `HARD_CONSTRAINT_POLICY(id=1).maximum_patients_per_nurse = 2` จาก Seed
เพื่อให้ผู้ป่วย 10 คนต้องการพยาบาล 5 คน และผู้ป่วย 2 คนต้องการ 1 คน
ค่านี้เป็น Ratio เดียวทั้งโรงพยาบาลสำหรับ Skeleton ไม่ใช่ค่า Auto-approval
`required_staff` เป็นจำนวนเป้าหมายที่บันทึกใน Requirement และ `minimum_staff` เป็นจำนวนขั้นต่ำ
ที่เก็บไว้สำหรับกฎความปลอดภัยในอนาคต เช่น การย้ายคนออกจากเวรต้นทาง
Skeleton เก็บทั้งสองตาม Schema เดิม แต่ยังไม่ใช้ตัดสิน Headcount Gap; ใช้สูตรจาก Patient Count แทน
ส่วน `STAFFING_REQUIREMENT_ROLE` / `STAFFING_REQUIREMENT_SKILL` ยังใช้คำนวณ Role / Skill Gap

**ROSTER_ASSIGNMENT**
* 101–105 ในเวร 1: `ASSIGNED`, `REGULAR`
* 202, 203 ในเวร 2: `ASSIGNED`, `REGULAR` (เกิน Requirement 1 คน)

**ACTORS** 6 ตัวตาม `ActorName` + 1 ตัวต่อพนักงานแต่ละคน

**Policy** อย่างละ 1 แถว แต่ละตารางใช้ `id = 1`, `version = "demo-stub-v1"`

* `HARD_CONSTRAINT_POLICY`: พัก 11 ชม., วันละไม่เกิน 12 ชม., สัปดาห์ละไม่เกิน 52 ชม., `maximum_patients_per_nurse = 2`
* `SOFT_CONSTRAINT_POLICY`: Weight ทั้ง 5 ตัว = 1 เป็น Placeholder สำหรับ Demo เนื่องจากตัวอย่างในคู่มือ Schema v5 ไม่อยู่ใน Repo นี้ ไม่ใช่ค่าที่ตกลงสำหรับ Solver จริง โดย `candidate_source_priority` และ `optimization_priority` เป็น List ของค่า Enum ตามลำดับที่ประกาศใน `CandidateSource` และ `OptimizationObjective` ตามลำดับ
* `APPROVAL_POLICY`: `ratio = 2`, `incoming_count = 10` ตามข้อตกลงทีม แต่ Golden Path ใช้ MANUAL approval จึงยังไม่ใช้ค่าเหล่านี้ตัดสินอัตโนมัติ

### 10.3 ผลที่คาดหวัง

| ขั้น | ผล |
|---|---|
| ก่อนลา | RN 5/5, ICU 2/2 (101, 102) ไม่มี Gap |
| 105 แจ้งลา | Event `PROCESSED`, `STAFF_UNAVAILABILITY` ของ 105 (`UNPLANNED_LEAVE`, `D 23:00` – `D+1 07:00`), Roster ของ 105 → `CANCELLED`, เปิดเคส |
| Gap | `headcount_gap = 1`, RN ขาด 1, ICU ไม่ขาด |
| Solver | 201, 202, 203 ตามลำดับ |
| Outreach | Offer ถึง 201 สถานะ `SENT` |
| 201 ตอบรับ | ผ่าน Safety รออนุมัติ |
| 900 อนุมัติ | Roster ของ 201 `ASSIGNED` + `REPLACEMENT` เคส `RESOLVED` RN 5/5 อีกครั้ง |

### 10.4 ข้อมูลเผื่อ Test อื่น (ใช้ Seed เดียวกัน)

* **Event ที่ไม่มี Gap:** 203 ส่ง `STAFF_UNAVAILABLE` ของเวร 2 → สร้าง `STAFF_UNAVAILABILITY` (`UNPLANNED_LEAVE`), Roster ของ 203 → `CANCELLED`, 202 ยังครบ RN 1/1 → Event `IGNORED` ไม่มีเคส
* **ผู้สมัครปฏิเสธ (ภายหลัง):** 201 ตอบ `REJECT` → ระบบไป 202

---

## 11. ลำดับเหตุการณ์ของ Golden Path

```
[Demo Control]  POST /events   (X-Demo-User: 105, STAFF_UNAVAILABLE, shift 1)
   Event PROCESSED → OPEN → ASSESSING → OPTIMIZING → OUTREACH → WAITING_RESPONSE   (หยุด)

[LINE Sim]      POST /demo/line-sim/respond   (X-Demo-User: 201, ACCEPT)
   → SAFETY_VALIDATION → WAITING_APPROVAL                                          (หยุด)

[Approvals]     POST /approvals/{id}/decision   (X-Demo-User: 900, approved = true)
   → EXECUTING → RESOLVED                                                          (จบ)
```

Test ที่ยืนยัน Flow นี้: `backend/tests/e2e/test_workforce_recovery.py` ต้องผ่านทุก PR

---

## 12. เรื่องที่ทำภายหลัง (ไม่อยู่ใน Skeleton)

| เรื่อง | หมายเหตุ |
|---|---|
| การใช้ `PENDING_APPROVAL` ใน Roster | ค่ามีใน Enum แล้ว แต่ Skeleton ยังไม่ใช้ ต้องใช้เมื่อรองรับ Gap > 1, ส่ง Offer แบบ Wave หรือหลายเคสพร้อมกัน |
| `NO_SHOW` | ตรวจ check-in ใน `ATTENDANCE` หลัง `SHIFT.start_at` + เวลาผ่อนผัน (สมมติ 15 นาที) แล้วสร้าง `STAFF_UNAVAILABILITY` + Event `STAFF_UNAVAILABLE` ทีละเวร |
| แก้ `end_at` ของ `STAFF_UNAVAILABILITY` | กลับเร็ว / หยุดนานกว่าที่บันทึก / ใส่วันกลับเมื่อเคยเป็น NULL → Audit `UNAVAILABILITY_UPDATED` |
| การรวม Event + `case_id` ใน STAFFING_EVENTS | ใช้ `EventStatus.RECEIVED` เป็นคิวรอรวม |
| Celery, Timeout, Approval Timeout | |
| Auto-Approval | Future feature: activate when the nurse-to-patient ratio exceeds twice the ward's required ratio (`ratio = 2`). `incoming_count` refers to staff awaiting approval by the head nurse or nurse supervisor (policy value = 10); its comparison rule remains to be defined. Skeleton uses MANUAL approval. |
| รูปแบบ `required_approver_role` | Skeleton เก็บ `ROLE.id` ของ HEAD_NURSE ไปก่อน |
| LangGraph | ดูทางเลือกในเอกสารแยก |
| Event กลุ่มภาระงาน (`PATIENT_SURGE` ฯลฯ) | อัปเดต `SHIFT.patient_count` แล้วคำนวณ Headcount จาก Ratio เดียวกันก่อนประเมิน ไม่ต้องสร้าง Requirement ใหม่เพียงเพราะ Patient Count เปลี่ยน; ถ้า Role / Skill Requirement เปลี่ยน ต้องอัปเดต Requirement ก่อนประเมิน การรับ Event กลุ่มนี้ยังเป็นงานภายหลัง |

---

## 13. ประวัติการเปลี่ยนแปลง

**เมื่อ Conflict ในตารางนี้:** เก็บไว้ทั้งสองแถว แถวที่วันที่เดียวกันเรียงตามลำดับที่ Merge

| วันที่ | เปลี่ยนอะไร | ใครเสนอ |
|---|---|---|
| YYYY-MM-DD | ร่างแรกสำหรับ Walking Skeleton ตาม Schema v5 + ACTORS + Event status | ทีม |
| 2026-10-08 | ปรับตาม `docs/database-schema.md`: `STAFF_UNAVAILABILITY`, Event type `STAFF_UNAVAILABLE` / `REQUIREMENT_CHANGED`, `PENDING_APPROVAL`, เพิ่มเวร 2 สำหรับ Test Event ที่ไม่มี Gap | ทีม |
| 2026-10-09 | ปิดขั้นที่ 0 ของ `walking-skeleton.md`: เพิ่ม `UNAVAILABILITY_CREATED` ในข้อ 7 ให้ตรงกับ `GOLDEN_PATH_AUDIT_ACTIONS`, `ACTORS.name` ของ user = `str(staff.id)` | ทีม |
| 2026-10-09 | Gap Calculator ใช้ `ceil(patient_count / patients_per_nurse)` จาก `HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse` (Ratio เดียวทั้งโรงพยาบาล, Seed id=1 ค่า 2); เพิ่ม Migration และ shared policy loader; เปิดเคสและ ASSESSING ใช้ `has_gap`; ปรับ Requirement / PATIENT_SURGE และระบุข้อจำกัดประวัติ Policy ของ Gap | ทีม |
| 2026-10-09 | ขั้นที่ 3: ข้อ 6.3 `actor_service` โยน `ActorNotFoundError` เมื่อไม่มี Actor, ข้อ 9 เพิ่ม Dependency `get_db` / `get_demo_user` (คืน `CurrentUser` ที่มี `staff` และ `actor_id`) และเงื่อนไข `401` ของ `X-Demo-User` | คน 1 |
| 2026-10-09 | ขั้นที่ 3 Orchestrator: ข้อ 6.2 เพิ่ม `resume()` สำหรับออกจากจุดรอ (Service ไม่แก้ `case.status` เอง), `HANDLERS`, ล็อกแถวเคส, D11 ทำด้วย Savepoint และไม่โยน Exception ต่อ; ข้อ 6.1 เพิ่มกติกา `wait` คู่กับจุดรอ; ข้อ 4 และ 5.1 เปลี่ยนจาก `advance()` เป็น `resume()` ที่จุดรอ | คน 1 |
| 2026-10-09 | Orchestrator ตามรีวิว: ล็อกเป็น `FOR NO KEY UPDATE`, `resume()` และ Handler ห้ามใช้ `FAILED` เป็น `next_status`, D11 ในข้อ 1 ใช้ Savepoint, ข้อ 6.2 เพิ่มว่าผู้เรียกห้าม Commit หลัง `InvalidTransitionError` และข้อยกเว้นของการไม่โยน Exception | คน 1 |
| 2026-10-09 | เตรียมขั้นที่ 4: ข้อ 6.4 Seam ระหว่างขั้น, ข้อ 6.5 คอลัมน์เวลา, ข้อ 9.1 ไฟล์ Route และ Error ร่วม (`409` / `404`), ข้อ 9.2 `REJECT` และไม่อนุมัติตอบ `422`, ข้อ 9.3 รูปแบบคำตอบและ Key ที่ E2E ใช้, กติกาเมื่อ Conflict ในข้อ 9 และ 13; line-sim ย้ายไป `routes/line_sim.py` | ทีม |
| 2026-10-09 | ตามรีวิว PR เตรียมขั้นที่ 4: Seam 1 ไม่เจอ Plan เป็น Error, Seam 6 เรียงด้วย `id`, ข้อ 9.1 ระบุว่า `409` จาก `InvalidTransitionError` เกิดจาก Race และ Route ยังต้องตรวจคำขอซ้ำเอง, ตัวอย่างในข้อ 9 ใช้ Path ที่ไม่ซ้ำ Prefix | ทีม |
| 2026-10-09 | ขั้นที่ 4 Seam 2: Contact Handler ส่ง Mock Offer ให้อันดับ 1 ของ Plan ล่าสุด, บังคับ Item หนึ่งแถวพอดี, ตั้ง `sent_at` และเขียน `OFFER_SENT` โดยไม่ Commit; เพิ่ม Test การ Rollback และ D11 | คน 3 |
| 2026-10-09 | ขั้นที่ 4 Seam 3: `POST /demo/line-sim/respond` ใช้ผู้ตอบจาก Header, ล็อก Offer ที่ `SENT` หนึ่งแถวพอดี, รับ `ACCEPT` และเขียน Audit ก่อน `resume(SAFETY_VALIDATION)`; `REJECT` ตอบ `422`, คำขอซ้ำ / Offer ไม่ชัดเจนตอบ `409`; เพิ่ม Test Race และ Request Rollback | คน 3 |
| 2026-10-09 | ขั้นที่ 4 Seam 4: เพิ่ม `outreach_service.get_accepted_outreach()` เป็น Lookup ของ Offer ที่ตอบรับหนึ่งแถวพอดีต่อเคสสำหรับ Safety; Flush ก่อนอ่าน ไม่ Commit / เขียน Audit; เพิ่ม Test ขอบเขตเคส, Cardinality และ D11 | คน 3 |
| 2026-10-09 | ขั้นที่ 4 Route อ่านข้อมูลของเคส: ข้อ 9.3 เพิ่มรูปแบบคำตอบของ `GET /cases/{id}` และ `GET /cases/{id}/audit` (Seam 9) และกติกาว่าเวลาในคำตอบของ API เป็น `+07:00` ผ่านชนิด `AppDatetime`; `CaseNotFoundError` ย้ายไป `app/domain/errors.py` | คน 1 |
| 2026-10-09 | ขั้นที่ 4 Solver: ข้อ 8 Stub ตัดผู้สมัครที่ไม่ `ACTIVE`, อยู่เวรของเคสแล้ว หรือไม่พร้อมในช่วงเวรนั้น ใส่ `rank` ใหม่ไม่ข้ามเลข และไม่เหลือใครเป็น `FAILED` (`NoCandidatesError`) กติกาอยู่ใน `availability_service` ใช้ร่วมกับ Safety; Test ใช้ Fixture `stub_handlers` กลางใน `tests/integration/conftest.py` | คน 2 |
| 2026-10-09 | ขั้นที่ 4 รับ Event: ข้อ 3 เพิ่ม Request Body, ลำดับการตรวจและ Status Code (`404` / `409` / `422`), การล็อกแถว `SHIFT` และ Roster ให้รับ Event ทีละคำขอต่อเวร, ลำดับและ `case_id` ของ Audit, Actor ของ `EVENT_IGNORED`, `gap_service.assess_shift()` และ `requirement_service.get_current_requirement()` (Seam 10) | คน 1 |
| 2026-10-09 | ขั้นที่ 4 Safety: ข้อ 8 Stub เช็กผู้สมัครที่ตอบรับซ้ำด้วยกติกาเดียวกับ Solver (`availability_service`) ไม่ผ่านเป็น `FAILED` พร้อม `error_type` ที่บอกสาเหตุ โดยไม่เขียน SAFETY_VALIDATION / APPROVAL_REQUEST; `SAFETY_FAILED` + ผู้สมัครคนถัดไปรอ Transition ในข้อ 5 | คน 2 |
| 2026-10-10 | ขั้นที่ 4 Solver ตามรีวิว: ข้อ 8 กฎข้อที่ 4 ตัดผู้สมัครที่มี Offer ค้าง (`SENT` หรือ `ACCEPTED` ของเคสที่ยังไม่หยุด) เฉพาะ Solver ไม่ใช้กับ Safety เพื่อให้สองเคสที่เปิดพร้อมกันไม่ส่ง Offer ให้คนเดียวกันจน Seam 3 ตอบรับไม่ได้; Merge staging แล้วลบ Stub ชุดเก่าใน `test_orchestrator.py` | คน 2 |
| 2026-10-10 | ขั้นที่ 4 Solver ตามรีวิว: ข้อ 8 Solver ล็อกแถว `STAFF` ของผู้สมัครก่อนเช็กกติกา สองเคสที่วางแผนพร้อมกันจึงไม่ได้ผู้สมัครคนเดียวกัน; ข้อ 6.2 เพิ่มลำดับ Lock (เวร/Roster → เคส → `STAFF`) | คน 2 |
| 2026-10-10 | ขั้นที่ 4 Safety ตามรีวิว: ข้อ 8 ตรวจว่า `proposed_shift_id` ของ Item ที่ตอบรับเป็นเวรของเคสก่อนเช็กผู้สมัคร ไม่ตรงเป็น `FAILED` (`ProposedShiftMismatchError`) โดยไม่เขียนแถว | คน 2 |
| 2026-10-10 | ตามรีวิว Seam 3: นับเฉพาะ Offer `SENT` บนเคส `WAITING_RESPONSE`; Test แทน Safety Handler เพื่อแยกจาก Seam 5 และตรวจว่า Offer ค้างบนเคสอื่นไม่ขวางคำตอบ รวมทั้ง Rollback หลัง Race ที่ `resume()` | คน 3 |
| 2026-10-10 | ตามรีวิว Seam 4: Lookup Flush คำตอบก่อนอ่าน ลดคำอธิบายที่ซ้ำ Seam 5 และปรับ Test สำหรับ Session ที่ปิด Autoflush | คน 3 |
| 2026-10-10 | Seam 4 เชื่อมกับ Safety ตัวจริง: `safety_service` ใช้ Lookup กลางแทน Query ซ้ำ; Test Resume และ D11 ใช้ Handler ตัวจริง ตรวจ Validation / Approval และ Rollback | คน 3 |
| 2026-10-10 | ขั้นที่ 4 Seam 7: เพิ่ม Route / Schema / `approval_service.decide()` ตรวจ `404 → 403 → 409 → 422`, ล็อก Request กันอนุมัติซ้ำ, เขียน Audit และ `resume(EXECUTING)` | คน 3 |
| 2026-10-10 | ตามรีวิว Seam 7: รวม staging คืนเจ้าของ Seam 8 ใช้ `MAX_BIGINT` และล็อก Request แบบ `FOR NO KEY UPDATE`; Test ใช้ Main App และ Error Handler ตัวจริง | คน 3 |
