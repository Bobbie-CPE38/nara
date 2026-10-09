# แผน Walking Skeleton (ฉบับปรับใหม่)

> อิงจาก `docs/workflow.md` (2026-10-08), `docs/database-schema.md`, `docs/repo-structure.md` และ `backend/app/domain/enums.py`
> เป้าหมาย: Golden Path ในข้อ 11 ของ `workflow.md` วิ่งครบตั้งแต่ `POST /events` ถึง `RESOLVED` และ E2E Test เขียวใน CI

---

## สิ่งที่เปลี่ยนจากแผนเดิม

| เรื่อง | แผนเดิม | ตอนนี้ |
|---|---|---|
| Contract (ขั้นที่ 0) | ต้องนั่งตกลงกันครึ่งวัน | เกือบเสร็จแล้ว (`workflow.md`, `enums.py`, `database-schema.md`) เหลือแก้จุดไม่ตรงกันไม่กี่ข้อ |
| Schema | สร้างแค่ 17 ตาราง | Schema ล็อกแล้ว สร้าง Model ครบ 30 ตารางใน Migration แรก แต่ Seed เฉพาะที่ Golden Path ใช้ |
| ID | ยังไม่ตัดสิน | `bigint` ทุกตาราง |
| ผู้กระทำใน Audit | ข้อความ | `ACTORS.id` |
| การรับ Event | สร้างเคสเสมอ | ตรวจ Gap ก่อน ไม่มี Gap → Event `IGNORED` ไม่สร้างเคส |
| การลา | `STAFF.status` / `UNPLANNED_LEAVE` Event | Event `STAFF_UNAVAILABLE` + แถว `STAFF_UNAVAILABILITY` (`reason = UNPLANNED_LEAVE`) + Roster ของคนลา `CANCELLED` |
| Gap | Stub คืนค่าตายตัว | `gap_calculator` ของจริงแบบง่ายตั้งแต่ Skeleton (เพราะการรับ Event ต้องใช้) |
| Golden Case | N001–N003 | ID 101–105, 201–203, 900 พร้อมเวร 2 สำหรับ Test Event ที่ไม่มี Gap |
| ผู้ใช้ | ไม่ได้กำหนด | Header `X-Demo-User: <staff_id>` |
| เวลา | `datetime.now()` | `core/clock.py` ตั้งค่าได้ (Demo = `D 21:00 +07:00`) |

---

## ขั้นที่ 0: เก็บงาน Contract ให้ตรงกัน (ครึ่งวัน, ทั้งทีม)

จากการเทียบไฟล์ทั้งหมด มีจุดที่ไม่ตรงกันที่ต้องแก้ก่อนเขียนโค้ด

| # | จุดที่ไม่ตรง | แก้เป็น |
|---|---|---|
| 0.1 | `workflow.md` ข้อ 5.1 ใช้ handler `intake_event` สำหรับ `OPEN → ASSESSING` แต่ Repo ไม่มีไฟล์นี้ | เพิ่ม `workflow/handlers/intake_event.py` (ทำแค่คืน `ASSESSING`) |
| 0.2 | `workflow.md` ข้อ 6.3 ใช้ `services/actor_service.py` แต่ Repo มีแค่ `actor_repository.py` | เพิ่ม `services/actor_service.py` |
| 0.3 | `enums.py` เพิ่ม `UNAVAILABILITY_CREATED` ใน `GOLDEN_PATH_AUDIT_ACTIONS` แล้ว แต่ `workflow.md` ข้อ 7 ยังไม่มีแถวนี้ | เพิ่มแถว: `event_service`, Actor user (คนที่ลา), `STAFF_UNAVAILABILITY`, payload `unavailability_id`, `staff_id`, `reason`, `start_at`, `end_at` |
| 0.4 | `seed/scenarios/test_manual_handoff.py`, `test_integration_unavailable.py` ขึ้นต้นด้วย `test_` pytest จะเก็บไปรันเป็น Test | เปลี่ยนชื่อเป็น `manual_handoff.py`, `integration_unavailable.py` |
| 0.5 | `handlers/process_approval.py` มีใน Repo แต่ `WAITING_APPROVAL` เป็นจุดรอ ไม่มี Handler | เก็บไว้สำหรับ Auto-Approval ภายหลัง Skeleton ไม่ใช้ |
| 0.6 | `domain/workflow/states.py` ซ้ำกับ `CaseStatus` และกลุ่มสถานะใน `enums.py` | ตัด `states.py` ทิ้ง เก็บ `transitions.py` เป็นที่เดียวที่นิยาม Transition ที่อนุญาต Orchestrator ใช้ตรวจ `next_status` |
| 0.7 | `STAFF.email`, `password_hash` เป็น NOT NULL แต่ Skeleton ไม่มี Login | Seed ใช้ค่าปลอม เช่น `105@demo.local` และ `"!"` |
| 0.8 | `ACTORS.name` ของ user = รหัสพนักงาน แต่ `STAFF.id` เป็นตัวเลข | ใช้ `str(staff.id)` |

**เสร็จเมื่อ:** แก้ 0.1–0.8 ใน PR เดียว ทุกคนรีวิวผ่าน

---

## ขั้นที่ 1: Infra (วันที่ 1)

| งาน | คน | ไฟล์ |
|---|---|---|
| Postgres + Backend + Frontend ใน Compose (Redis ใส่ไว้แต่ยังไม่ใช้) พร้อม Healthcheck | 1 | `docker-compose.yml` |
| `/health` เช็ก DB (มีไฟล์แล้ว) + CORS + Config | 1 | `main.py`, `core/config.py`, `db/session.py` |
| `Base`, `alembic init`, `env.py` อ่าน `DATABASE_URL` และ `Base.metadata` | 1 | `db/base.py`, `alembic/env.py` |
| Clock ตั้งเวลาได้ | 1 | `core/clock.py` |
| `Makefile`: `up`, `down`, `logs`, `test`, `reset` (Seed เป็นคำสั่งว่างไว้ก่อน) | 1 | `Makefile` |
| ruff, mypy, pytest, `conftest.py` สร้าง Test DB | 2 | `pyproject.toml`, `tests/conftest.py` |
| CI: lint + test | 2 | `.github/workflows/ci.yml` |
| Next.js + Tailwind + Layout + หน้า `/` เรียก `/health` (มีไฟล์แล้ว) | 3 | `frontend/` |
| `lib/api.ts` ใส่ `X-Demo-User` ให้อัตโนมัติ + `hooks/usePolling.ts` | 3 | `frontend/src/lib`, `hooks` |

**เสร็จเมื่อ:** ทุกคน Clone แล้ว `make up` เห็น API ok, Database ok และ CI เขียว

---

## ขั้นที่ 2: Model, Migration และ Seed (วันที่ 2)

### 2.1 Model ครบ 30 ตาราง แบ่งตามเจ้าของ

แบ่งให้ทำพร้อมกันได้ ทุกคนเขียน Model ตาม `database-schema.md` ตรงตัว

| คน | Model |
|---|---|
| 1 | `staff`, `actor`, `ward`, `skill`, `role`, `staff_skill`, `shift`, `staffing_event`, `staffing_requirement` (+ role, skill), `staffing_case`, `staff_unavailability`, `roster_assignment`, `staffing_gap` (+ role, skill) |
| 2 | `hard_constraint_policy`, `soft_constraint_policy`, `approval_policy`, `candidate_plan`, `candidate_item`, `safety_validation`, `staff_working_time_snapshot` |
| 3 | `contact`, `candidate_outreach`, `approval_request`, `structured_handover`, `attendance`, `audit_log` |

### 2.2 Migration แรก

คน 1 รวม Model ทั้งหมด แล้วสร้าง Migration เดียวด้วย `alembic revision --autogenerate -m "initial schema"` Constraint 4 ข้อท้าย `database-schema.md` (CHECK `staff_id` ตามกลุ่ม Event, CHECK Actor ที่เป็น user, UNIQUE `staff_id`, UNIQUE `name` ของ Component) ประกาศไว้ใน `__table_args__` ของ Model `actor` และ `staffing_event` แล้ว autogenerate จึงสร้างให้เอง ไม่ต้องเพิ่มด้วยมือ ให้เปิดไฟล์ Migration ตรวจว่าออกมาครบ 4 ข้อก่อนรัน

### 2.3 Seed

| ไฟล์ | ข้อมูล |
|---|---|
| `seed/base_data.py` | Actor ที่ไม่ใช่คน 6 ตัว, Policy อย่างละ 1 แถว (Hard, Soft, Approval), แต่ละตารางใช้ `id = 1` เป็น ID คงที่สำหรับ Demo |
| `seed/scenarios/golden_case.py` | ข้อมูลตาม `workflow.md` ข้อ 10.2 ทั้งหมด รวม Actor ของพนักงานทุกคน |
| `POST /demo/reset` + `make reset` | Drop → `alembic upgrade head` → ตั้ง Clock เป็น `D 21:00 +07:00` ใน API Process → base_data → golden_case → Commit |

ตั้ง Clock ก่อน Seed เพื่อให้ Timestamp ของข้อมูลเริ่มต้นมาจาก `clock.now()` ที่เวลา Demo เดียวกัน และคง Clock นี้ไว้ให้ Workflow ใช้ต่อหลัง Reset โดย `D` คือวันที่ปัจจุบันตามเวลาจริงในประเทศไทย ไม่ใช่วันที่ที่ Freeze ไว้จาก Reset ครั้งก่อน ส่วน Policy `id = 1` เป็นข้อตกลงของ Demo แยกกันในแต่ละตาราง ไม่ใช่กฎสำหรับ Policy ทุก Version ในอนาคต

**เสร็จเมื่อ:** `make reset` แล้วเปิด DB เห็น RN 5 คนในเวร 1, ICU 2 คน (101, 102), 202 กับ 203 ในเวร 2

---

## ขั้นที่ 3: โครงกลางที่ทุกคนเสียบงาน (วันที่ 2–3)

| งาน | คน | ไฟล์ | เสร็จเมื่อ |
|---|---|---|---|
| `actor_service.component_id()`, `user_id()` | 1 | `services/actor_service.py` | คืน ID ถูกต้องจาก Seed |
| `audit_service.log()` (ห้าม Commit) | 3 | `services/audit_service.py` | เขียนลง `AUDIT_LOG` ได้ ต้อง Merge ก่อนใครเริ่มขั้นที่ 4 |
| `get_demo_user` อ่าน `X-Demo-User` | 1 | `api/dependencies.py` | ไม่มี Header → 401 |
| `HandlerResult` | 1 | `workflow/handlers/base.py` | |
| `ALLOWED_TRANSITIONS` + `assert_transition()` ตาม `workflow.md` ข้อ 5 | 1 | `domain/workflow/transitions.py` | Unit Test ผ่าน |
| `advance()` + ตรวจ Transition + บันทึก `CASE_STATUS_CHANGED` + D11 (`FAILED`) | 1 | `workflow/orchestrator.py` | Integration Test: Handler ปลอมโยน Exception แล้วเคสเป็น `FAILED` |
| Handler ว่างทุกตัว คืน State ถัดไปตาม `workflow.md` ข้อ 5.1 | 1 | `workflow/handlers/*.py` | Push ขึ้น Main ทันทีให้คนอื่นเริ่มได้ |
| `gap_calculator` Pure Function + Unit Test | 1 | `domain/staffing/gap_calculator.py` | ทดสอบกรณีขาด RN 1, ขาด Skill, ไม่ขาด |

`gap_calculator` ทำจริงตั้งแต่ตอนนี้ เพราะทั้ง `POST /events` และขั้น `ASSESSING` ใช้ตัวเดียวกัน

สัญญาที่ใช้ร่วมกัน: `domain/staffing/gap_calculator.py` มี
`calculate_gap(*, shift_id, patient_count, patients_per_nurse, required_roles, required_skills, roster) -> GapResult`
โดย `required_roles` / `required_skills` เป็น Mapping ของ ID → จำนวนที่ต้องการ
และ `roster` เป็นรายการ `RosterMember` จาก `domain/staffing/coverage.py`
(`staff_id`, `shift_id`, `status`, `role_id`, `skill_ids` เป็นชุด Skill ทั้งหมดของคนนั้น)
ผู้เรียกโหลดข้อมูลจาก DB; Calculator นับคนไม่ซ้ำเฉพาะ `ASSIGNED` ในเวรเป้าหมาย
ใช้ `minimum_required_staff = ceil(patient_count / patients_per_nurse)` เป็นเป้าหมายจำนวนคน
โดย `patient_count` มาจาก Shift; ทั้ง `event_service` และ `assess_staffing` โหลด Policy
ด้วย `services/policy_service.py::get_hard_constraint_policy(db)` (Skeleton ตรึง `id=1`)
แล้วส่ง `patients_per_nurse=policy.maximum_patients_per_nurse` ค่า Seed คือ 2 ใช้ทั้งโรงพยาบาล
Calculator รับ `int` หรือ `Decimal` ที่มากกว่า 0 และเป็นค่าจำกัด โดยไม่มี Default
ถ้าไม่มี Policy ให้ Error แทนการเดาค่า; ไม่แก้ Policy กลาง Demo
เพิ่มคอลัมน์ด้วย Migration `a73d9e2c4b10` ซึ่ง Backfill Policy เดิมด้วยค่า Demo 2
อัปเกรด DB เดิมด้วย `docker compose exec -T backend alembic upgrade head` โดยไม่ต้อง Reset ข้อมูล
ห้ามใช้ `APPROVAL_POLICY.ratio` ซึ่งเป็นตัวคูณ Auto-approval
ไม่ใช้ `STAFFING_REQUIREMENTS.required_staff` / `minimum_staff` เป็นเป้าหมาย และไม่เขียน DB / Audit
ผลมี `minimum_required_staff`, `headcount_gap`, `role_gaps` / `skill_gaps` (ID → `required_count`, `current_count`,
`gap_count`) โดย Gap ต่ำสุดคือ 0 และเก็บรายการที่ไม่ขาดไว้ด้วย
ใช้ `result.has_gap` ตรวจว่าขาดจำนวนคน **หรือ** Role **หรือ** Skill; ห้ามบวก Gap ทั้งสามชนิดเข้าด้วยกัน

ข้อจำกัด: `STAFFING_GAP` ยังไม่เก็บ Policy ID; การย้อนดูเวอร์ชันของ Gap และ Ratio แยก Ward เป็นงานภายหลัง

ก่อน Wiring PR เริ่มบันทึก Gap ต้องเพิ่ม Snapshot `patient_count` และ `patients_per_nurse`
(หรือ Policy ID ของเวอร์ชันที่ไม่แก้ย้อนหลัง) ใน `STAFFING_GAP` พร้อม Migration
และเติม `assess_staffing` ให้ใช้ `result.has_gap` ตามข้อ 5.1; ปัจจุบัน Handler ยังเป็น Stub

**เสร็จเมื่อ:** สร้างเคสด้วยมือ เรียก `advance()` แล้วเคสเดินจาก `OPEN` ไปหยุดที่ `WAITING_RESPONSE` พร้อม `CASE_STATUS_CHANGED` 4 แถว

---

## ขั้นที่ 4: เติม Stub ทุกขั้น (วันที่ 3–4, ทำพร้อมกัน)

| ขั้น | คน | ไฟล์ | ทำอะไร | ตาราง | Audit |
|---|---|---|---|---|---|
| รับ Event | 1 | `routes/events.py`, `event_service.py`, `unavailability_service.py` | ตาม `workflow.md` ข้อ 3: บันทึก Event → สร้าง Unavailability → Roster คนลา `CANCELLED` → `gap_calculator` → `IGNORED` หรือเปิดเคส → `advance()` | EVENTS, STAFF_UNAVAILABILITY, ROSTER_ASSIGNMENT, CASES | `EVENT_RECEIVED`, `UNAVAILABILITY_CREATED`, `EVENT_IGNORED` / `CASE_OPENED` |
| Gap | 1 | `handlers/assess_staffing.py`, `gap_service.py` | เรียก `gap_calculator` บันทึกผล | STAFFING_GAP (+ ROLE, SKILL) | `GAP_ASSESSED` |
| Solver | 2 | `handlers/optimize.py`, `optimization_service.py` | Plan + Items 201, 202, 203 ตายตัว `FEASIBLE`, `"stub"`, อ้าง Policy จาก Seed | CANDIDATE_PLANS, CANDIDATE_ITEMS | `SOLVER_EXECUTED` |
| Outreach | 3 | `handlers/contact_candidate.py`, `outreach_service.py`, `integrations/line/mock.py` | Outreach ให้อันดับ 1 สถานะ `SENT` ผ่าน LINE Mock คืน `wait=True` | CANDIDATE_OUTREACH | `OFFER_SENT` |
| Response | 3 | `routes/demo.py` (line-sim), `outreach_service.record_response()` | `ACCEPT` → `ACCEPTED` แล้วเรียก `orchestrator.resume(db, case_id, SAFETY_VALIDATION)` (ไม่แก้ `case.status` เอง) | CANDIDATE_OUTREACH, CASES | `OFFER_ACCEPTED` |
| Safety | 2 | `handlers/validate_safety.py`, `safety_service.py` | `is_passed = true`, snapshot `{}`, สร้าง Approval Request (`MANUAL`, Role HEAD_NURSE) คืน `wait=True` | SAFETY_VALIDATION, APPROVAL_REQUEST | `SAFETY_PASSED`, `APPROVAL_REQUESTED` |
| Approval | 3 | `routes/approvals.py`, `approval_service.decide()` | ผู้อนุมัติ = `X-Demo-User` แล้วเรียก `orchestrator.resume(db, case_id, EXECUTING)` (ไม่แก้ `case.status` เอง) | APPROVAL_REQUEST, CASES | `APPROVAL_APPROVED` |
| Roster | 3 | `handlers/execute_assignment.py`, `roster_service.py` | Roster ของ 201: `ASSIGNED` + `REPLACEMENT` + `SAME_WARD` | ROSTER_ASSIGNMENT | `ASSIGNMENT_CREATED`, `CASE_RESOLVED` |
| อ่านข้อมูล | 1 | `routes/cases.py` | `GET /cases/{id}`, `GET /cases/{id}/audit` | | |
| อ่านข้อมูล | 3 | `routes/roster.py`, `routes/approvals.py` | `GET /roster`, `GET /approvals?pending=true`, `GET /demo/line-sim/offers` | | |

**กติกา**

* Branch ต่อขั้น PR เล็ก Merge อย่างน้อยวันละครั้ง
* ห้ามแก้ Enum, Signature หรือ Transition เอง ต้องแก้ `workflow.md` ใน PR เดียวกันและแจ้งทีม
* Handler ห้าม Commit, ห้ามแก้ `case.status`
* ทุกแถวที่สร้างใช้เวลาจาก `clock.now()`

---

## ขั้นที่ 5: Frontend ขั้นต่ำ (วันที่ 3–4, คู่กับขั้นที่ 4)

| หน้า | แสดงอะไร | คน |
|---|---|---|
| `demo/control` | ปุ่ม Reset, ปุ่ม "105 แจ้งลาเวร 1", ปุ่ม "203 แจ้งลาเวร 2" (กรณีไม่มี Gap) | 1 |
| `cases/[id]` | สถานะ, Gap, ผู้สมัครพร้อมอันดับ, Timeline จาก Audit (Poll 2 วินาที) | 1 + 2 |
| `demo/line-sim` | เลือก Staff ดู Offer ปุ่มรับ/ปฏิเสธ | 3 |
| `approvals` | รายการรออนุมัติ ปุ่มอนุมัติ/ไม่อนุมัติ (ใช้ตัวตน 900) | 3 |
| `roster` | คนในเวร 1 พร้อมสถานะ | 3 |

ตารางธรรมดาก็พอ ยังไม่ต้องออกแบบหน้าตา

---

## ขั้นที่ 6: Test และ CI (วันที่ 5)

| Test | คน | ตรวจอะไร |
|---|---|---|
| `tests/e2e/test_workforce_recovery.py` | 3 | Golden Path ครบ, Roster ของ 201 เป็น `REPLACEMENT`, Audit ครบตาม `GOLDEN_PATH_AUDIT_ACTIONS` ตามลำดับ |
| `tests/integration/test_event_ignored.py` | 1 | Event ที่ไม่มี Gap (203 ลาเวร 2) → `IGNORED` ไม่มีเคส |
| `tests/integration/test_orchestrator.py` | 1 | Exception กลางทาง → Rollback, `FAILED` + `WORKFLOW_FAILED` (D11) |
| `tests/unit/workflow/test_transitions.py` | 1 | Transition ของ Golden Path ผ่าน, คู่ที่ไม่อยู่ในตารางโยน Error, State สิ้นสุดไปต่อไม่ได้, ทุก State ที่ไม่ใช่สิ้นสุดไป `FAILED` ได้ |

```python
def test_golden_path(client):
    client.post("/demo/reset")
    r = client.post("/events", headers={"X-Demo-User": "105"},
                    json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1})
    case_id = r.json()["case_id"]
    assert case(client, case_id)["status"] == "WAITING_RESPONSE"

    client.post("/demo/line-sim/respond", headers={"X-Demo-User": "201"},
                json={"response": "ACCEPT"})
    assert case(client, case_id)["status"] == "WAITING_APPROVAL"

    approval_id = client.get("/approvals?pending=true",
                             headers={"X-Demo-User": "900"}).json()[0]["id"]
    client.post(f"/approvals/{approval_id}/decision", headers={"X-Demo-User": "900"},
                json={"approved": True})
    assert case(client, case_id)["status"] == "RESOLVED"

    actions = [a["action"] for a in client.get(f"/cases/{case_id}/audit").json()
               if a["action"] != "CASE_STATUS_CHANGED"]
    assert actions == [a.value for a in GOLDEN_PATH_AUDIT_ACTIONS]
```

ตั้ง CI ให้รัน Test ชุดนี้ทุก PR นับจากนี้ PR ที่ทำให้แดงห้าม Merge

---

## Checklist ว่า Skeleton เสร็จ

- [x] แก้ 0.1–0.8 แล้ว
- [ ] `make up` รันได้ทุกเครื่อง, `/health` ตอบ DB ok
- [x] `make reset` ได้ Golden Case ครบ (ยืนยันด้วย `tests/integration/test_demo_reset.py` และ `test_seed.py`)
- [ ] กด "105 แจ้งลา" → เคสหยุดที่ `WAITING_RESPONSE`, Roster ของ 105 `CANCELLED`
- [ ] กด "203 แจ้งลาเวร 2" → ไม่มีเคสใหม่ Event `IGNORED`
- [ ] 201 กดรับใน LINE Sim → `WAITING_APPROVAL`
- [ ] 900 กดอนุมัติ → `RESOLVED`, 201 อยู่ในตารางเวร
- [ ] Timeline แสดงครบทุกขั้น
- [ ] E2E Test เขียวใน CI

---

## หลัง Skeleton: เปลี่ยน Stub เป็นของจริง

| ลำดับ | คน 1 | คน 2 | คน 3 |
|---|---|---|---|
| 1 | Coverage ครบ (Role + Skill + Minimum) | Hard Rules จริงใน `domain/constraints/` ใช้ร่วมกันทั้ง Solver และ Safety | Reject → ไปคนถัดไป, Head Nurse ไม่อนุมัติ |
| 2 | ทุกที่ที่เช็กว่าว่างใช้ `COMMITTED_ROSTER_STATUSES` + `STAFF_UNAVAILABILITY` | OR-Tools: Hard ก่อน แล้วค่อย Soft | Celery + Redis: Candidate Timeout |
| 3 | Manual Handoff, Escalation | Working Time Snapshot, Score Breakdown, คำอธิบายอันดับ | LINE จริง + Webhook + ตรวจ Signature |
| 4 | Aggregation + Lock ต่อ Shift (`core/locks.py`) | Cross-Ward + `preserve_source_ward_minimum`, ผู้อนุมัติ = Supervisor | Approval Timeout, Auto-Approval (หลังนิยาม `ratio` / `incoming_count`) |
| 5 | ห่อ Orchestrator ด้วย LangGraph (ทางเลือก 2) | NO_SHOW (`detect_no_show`) | Handover |
| 6 | LLM Node สรุปสถานการณ์ (ถ้าทีมเลือกทางเลือก 4) | | LLM ตีความคำตอบอิสระ (ถ้าทีมเลือกทางเลือก 4) |

ทุกครั้งที่ทำกรณีใหม่ เปิดใช้ Seed Scenario และ Integration Test ของกรณีนั้นไปด้วย Golden Path ต้องเขียวตลอด
