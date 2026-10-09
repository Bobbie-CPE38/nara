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
| D11 | เกิด Exception ระหว่าง Workflow: Rollback รอบนั้น เปิด Transaction ใหม่ ตั้งเคสเป็น `FAILED` และบันทึก `WORKFLOW_FAILED` | ไม่มีเคสค้างกลางทางโดยไม่มีใครรู้ |
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
* ขั้นตอน 1–3 อยู่ใน Transaction เดียว ถ้าพังกลางทาง Event ไม่ถูกบันทึกเลย
* `STAFF.status` ของคนที่ลาไม่เปลี่ยน (ยังเป็น `ACTIVE`)
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

**จุดรอ** คือ State ที่ Orchestrator หยุด และเดินต่อเมื่อ API ภายนอกเปลี่ยน State แล้วเรียก `orchestrator.advance(case_id)`

---

## 5. Transition

### 5.1 Golden Path

| จาก | ไป | ใครสั่ง | เกิดเมื่อ |
|---|---|---|---|
| — | `OPEN` | `event_service` | Event มี Gap (ข้อ 3) |
| `OPEN` | `ASSESSING` | handler `intake_event` | ทันที |
| `ASSESSING` | `OPTIMIZING` | handler `assess_staffing` | บันทึก Gap แล้ว `headcount_gap > 0` |
| `OPTIMIZING` | `OUTREACH` | handler `optimize` | ได้รายชื่อผู้สมัครอย่างน้อย 1 คน |
| `OUTREACH` | `WAITING_RESPONSE` | handler `contact_candidate` | ส่ง Offer แล้ว (`wait=True`) |
| `WAITING_RESPONSE` | `SAFETY_VALIDATION` | `outreach_service.record_response()` | ผู้สมัครตอบ `ACCEPT` แล้วเรียก `advance()` |
| `SAFETY_VALIDATION` | `WAITING_APPROVAL` | handler `validate_safety` | ผ่าน Safety สร้าง Approval Request แล้ว (`wait=True`) |
| `WAITING_APPROVAL` | `EXECUTING` | `approval_service.decide()` | อนุมัติ แล้วเรียก `advance()` |
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

### 6.2 Orchestrator

```python
# workflow/orchestrator.py
def advance(db: Session, case_id: int) -> None
```

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

* `log()` **ห้าม Commit เอง**
* `action` และ `entity_type` ต้องเป็น Enum ห้ามพิมพ์ข้อความเอง
* `payload` ห้ามมีข้อมูลผู้ป่วยรายบุคคล เหตุผลการลาแบบข้อความอิสระ หรือ `password_hash`
* Composite Key (เช่น `STAFF_SKILL`) ยังไม่ต้อง Audit ใน Skeleton จึงยังไม่ต้องตัดสินรูปแบบ `entity_id`

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
| Gap | ใช้ `gap_calculator` จริงแบบง่าย: นับคนที่ `ASSIGNED` เทียบ Requirement | STAFFING_GAP (+ ROLE, SKILL) |
| Solver | คืนผู้สมัคร 3 คนตายตัวตาม Golden Case `solver_status = FEASIBLE`, `solver_version = "stub"` | CANDIDATE_PLANS, CANDIDATE_ITEMS |
| Outreach | สร้าง Outreach ให้อันดับ 1 สถานะ `SENT` ไม่ส่ง LINE จริง | CANDIDATE_OUTREACH |
| Response | LINE Simulator ส่ง `ACCEPT` → `ACCEPTED` | CANDIDATE_OUTREACH |
| Safety | `is_passed = true`, `validation_snapshot = {}` | SAFETY_VALIDATION, APPROVAL_REQUEST |
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

| id | ชื่อ | role | skill | บทบาทใน Demo |
|---|---|---|---|---|
| 101 | พิมพ์ชนก | RN | ICU, BLS | อยู่เวร |
| 102 | ธนพล | RN | ICU | อยู่เวร |
| 103 | วรรณา | RN | BLS | อยู่เวร |
| 104 | กิตติ | RN | BLS | อยู่เวร |
| 105 | สุดารัตน์ | RN | BLS | อยู่เวร **และแจ้งลา** |
| 201 | อรุณี | RN | ICU, BLS | ผู้สมัครอันดับ 1 **ตอบรับ** |
| 202 | ภานุ | RN | BLS | ผู้สมัครอันดับ 2, อยู่เวร 2 |
| 203 | ชลธิชา | RN | ICU | ผู้สมัครอันดับ 3, อยู่เวร 2 |
| 900 | มาลัย | HEAD_NURSE | — | ผู้อนุมัติ |

**SHIFT**
* 1 = ICU, `NIGHT`, `D 23:00` – `D+1 07:00`, `patient_count = 10`
* 2 = ICU, `DAY`, `D+2 07:00` – `D+2 15:00`, `patient_count = 2` (ใช้กับ Test ข้อ 10.4 เท่านั้น)

**STAFFING_REQUIREMENTS**
* 1 = shift 1, `required_staff = 5`, `minimum_staff = 4`, ROLE: RN = 5, SKILL: ICU = 2
* 2 = shift 2, `required_staff = 1`, `minimum_staff = 1`, ROLE: RN = 1, ไม่มี SKILL

**ROSTER_ASSIGNMENT**
* 101–105 ในเวร 1: `ASSIGNED`, `REGULAR`
* 202, 203 ในเวร 2: `ASSIGNED`, `REGULAR` (เกิน Requirement 1 คน)

**ACTORS** 6 ตัวตาม `ActorName` + 1 ตัวต่อพนักงานแต่ละคน

**Policy** `HARD_CONSTRAINT_POLICY` 1 แถว (พัก 11 ชม., วันละ 12 ชม., สัปดาห์ละ 52 ชม.) และ `SOFT_CONSTRAINT_POLICY` 1 แถว (ค่าตามตัวอย่างในคู่มือ Schema)

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
| Event กลุ่มภาระงาน (`PATIENT_SURGE` ฯลฯ) | ต้องสร้าง Requirement เวอร์ชันใหม่ก่อนประเมิน |

---

## 13. ประวัติการเปลี่ยนแปลง

| วันที่ | เปลี่ยนอะไร | ใครเสนอ |
|---|---|---|
| YYYY-MM-DD | ร่างแรกสำหรับ Walking Skeleton ตาม Schema v5 + ACTORS + Event status | ทีม |
| 2026-10-08 | ปรับตาม `docs/database-schema.md`: `STAFF_UNAVAILABILITY`, Event type `STAFF_UNAVAILABLE` / `REQUIREMENT_CHANGED`, `PENDING_APPROVAL`, เพิ่มเวร 2 สำหรับ Test Event ที่ไม่มี Gap | ทีม |
| 2026-10-09 | ปิดขั้นที่ 0 ของ `walking-skeleton.md`: เพิ่ม `UNAVAILABILITY_CREATED` ในข้อ 7 ให้ตรงกับ `GOLDEN_PATH_AUDIT_ACTIONS`, `ACTORS.name` ของ user = `str(staff.id)` | ทีม |
