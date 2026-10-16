
# Database Schema & Enum (แผนที่จะ Implement)


> สรุปจากคู่มือ Schema v5 + การตัดสินใจล่าสุดของทีม ใช้คู่กับ `docs/workflow.md` และ `backend/app/domain/enums.py`
> สถานะ: สร้างแล้วใน Migration แรก (`backend/alembic/versions/2026_10_09_0646-63c7709cfe6c_initial_schema.py`)
> Migration ถัดจากนั้น เรียงตามลำดับ:
> * `a73d9e2c4b10` เพิ่ม `HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse` (Backfill Policy เดิม = 2 สำหรับ Demo)
> * `b82e4f6a901c` ย่อชื่อ CHECK ของคอลัมน์นั้นเป็น `ck_hard_constraint_policy_patients_per_nurse_valid` (กติกาเดิม)
> * `c4d7e19a52f3` เพิ่ม Snapshot `patient_count` และ `patients_per_nurse` ใน `STAFFING_GAP` พร้อม CHECK (ไม่ Backfill, ดูข้อ 24)
> * `d5e8f20b63a4` แทน Snapshot สองคอลัมน์นั้นด้วย `STAFFING_GAP.effective_minimum` (รอบ 1 PR 1b ไม่ Backfill ให้ `make reset`)
> * `e1f5a8b3c6d2` (รอบ 1 PR 1a) เพิ่ม `HARD_CONSTRAINT_POLICY.maximum_consecutive_shifts` พร้อม CHECK (Backfill Policy เดิม = 7) และ CHECK ของ `ATTENDANCE.overtime_minutes`
> * `d91a6c8e203f` เพิ่ม `OUTREACH_POLICY` และ CHECK เพดาน Offer มากกว่า 0 (PR 1c; Migration สร้างตารางว่าง ต้อง `make reset` เพื่อโหลด Policy ของ Demo)
> * `f2a6b9c4d7e1` (รอบ 1 PR M) คอลัมน์ของ Merge Gap เช่น `SHIFT.merge_window_seconds`, `STAFFING_EVENTS.case_id` และ `AUDIT_LOG.event_id` รายการครบอยู่ในไฟล์ Migration
> * `f3a7c1d9e5b2` (รอบ 1 PR 2a) เพิ่มตาราง `CANDIDATE_ITEM_TARGET` พร้อม CHECK สองข้อ, `CANDIDATE_ITEMS.working_time_snapshot_id` และ `SOFT_CONSTRAINT_POLICY.candidate_source_weight` (Backfill Policy เดิม = 200)
> * `a4b8c2d6e9f1` (รอบ 1 PR O) `OUTREACH_POLICY.offer_timeout_seconds` และ `CANDIDATE_OUTREACH.expires_at`
> * `b7d2f8a1c6e4` (รอบ 2 PR T) `APPROVAL_POLICY.approval_timeout_seconds`, เส้นตายและ `outreach_id` ของ `APPROVAL_REQUEST`, `SAFETY_VALIDATION.outreach_id`
> * `c9e4a7b2d5f8` (รอบ 2 PR B) `SOFT_CONSTRAINT_POLICY.solver_time_limit_seconds`
> * `b7d3e5a1c9f2` (รอบ 2 PR H) ตาราง `MANUAL_ASSIGNMENT` (ข้อ 31)
>
> * `c6e9a2b4d8f1` (รอบ 3 PR L) งานส่งในแถว Offer และตาราง `LINE_WEBHOOK_EVENT`
>
> * `d7f0b3c5e9a2` (รอบ 3 PR K) ตาราง `LINE_ACCOUNT_LINK_CODE` และ UNIQUE `CONTACTS.line_uid`
>
> * `e1a4c7f2b9d6` (รอบ 3 PR X) ตาราง `RANK_EXPLANATION` และ `LLM_CALL_LOG`
>
> * `a9c3e7f1b5d2` (รอบ 4 PR T1) `CANDIDATE_ITEMS.cover_start_at`, `cover_end_at`, `source_assignment_id` พร้อม CHECK สองข้อ
>
> * `b8d4f1a6c2e9` (รอบ 4 PR T2) เวลาจริงและลิงก์การย้ายใน `ROSTER_ASSIGNMENT`
>
> * `c4e8a2f6d1b3` (รอบ 4 PR C1) `WARD.is_float_pool`
>
> * `c6e2b9f4a1d7` (รอบ 4 PR T3) `STAFFING_GAP.evaluated_from` และตาราง Gap รายช่วง `STAFFING_GAP_INTERVAL`, `STAFFING_GAP_ROLE_INTERVAL`, `STAFFING_GAP_SKILL_INTERVAL` ไม่ Backfill
>
> * `f2a7c9d4e6b8` (รอบ 4 PR S) `APPROVAL_WARD_DECISION` และ `APPROVAL_POLICY.supervisor_after_seconds`
>
> **Migration head ปัจจุบัน: `f2a7c9d4e6b8`** ตรวจด้วย `alembic heads` ต้องได้ head เดียว


## สรุปการตัดสินใจ


| เรื่อง | ตัดสินว่า |
|---|---|
| จำนวนตาราง | 32 ตาราง (29 เดิม + `ACTORS` + `OUTREACH_POLICY` + `CANDIDATE_ITEM_TARGET`) |
| ชนิด ID | `bigint` ทุกตาราง (รวม FK ทุกตัว) |
| เก็บ Enum | Python `StrEnum` → คอลัมน์ `text` ยังไม่ใส่ DB ENUM / CHECK |
| `created_at` / `updated_at` | `timestamptz` ตั้งค่าจาก `core/clock.py` ไม่พึ่ง Default ของ DB |
| Event ที่ไม่มี Gap | `STAFFING_EVENTS.status = IGNORED` ไม่สร้างเคส |
| การลาและช่วงที่ไม่พร้อม | เก็บที่ `STAFF_UNAVAILABILITY` เท่านั้น `STAFF.status` ไม่เก็บการลา |
| ไม่มีแถวใน `STAFF_UNAVAILABILITY` | ถือว่าพร้อม (เฉพาะ `STAFF.status = ACTIVE`) |
| Event ของ `UNPLANNED_LEAVE` และ `NO_SHOW` | ใช้ `STAFF_UNAVAILABLE` เหตุผลดูที่ `STAFF_UNAVAILABILITY.reason` |
| `STAFF_UNAVAILABILITY.reason` | ไม่เปลี่ยนหลังสร้างแถว |
| ผู้กระทำใน Audit | อ้าง `ACTORS.id` แทนข้อความ |


## เปลี่ยนจากคู่มือ v5


| ตาราง | เปลี่ยน |
|---|---|
| ทุกตาราง | `id` และ FK จาก `text` → `bigint` (ยกเว้น `CONTACTS.line_id`, `line_uid` ที่ยังเป็น text) |
| `ACTORS` | ตารางใหม่ |
| `STAFF` | ตัด `PLANNED_LEAVE`, `UNPLANNED_LEAVE` ออกจาก Staff status |
| `STAFF_AVAILABILITY` | เปลี่ยนชื่อเป็น `STAFF_UNAVAILABILITY`, ตัด `is_available`, `reason` → `NOT NULL`, เพิ่ม `NO_SHOW` และตัด `OTHER` ใน Availability reason, `end_at` → `NULL` ได้ |
| `STAFFING_EVENTS` | เพิ่ม `status`, ตัด `UNPLANNED_LEAVE` ออกจาก Event type (ใช้ `STAFF_UNAVAILABLE` แทน), รวม `STAFFING_`, `ROLE_`, `SKILL_REQUIREMENT_CHANGED` เป็น `REQUIREMENT_CHANGED` |
| `ROSTER_ASSIGNMENT` | เพิ่ม `PENDING_APPROVAL` ใน Roster status |
| `STAFFING_CASES` | ตัด `IGNORED` ออกจาก Case status |
| `AUDIT_LOG` | `actor_id` → `bigint NOT NULL FK ACTORS.id`, ตัด `actor_type`, `entity_id` → `bigint NULL`, เพิ่ม `STAFF_UNAVAILABILITY` ใน Entity type, เพิ่ม `UNAVAILABILITY_CREATED`, `UNAVAILABILITY_UPDATED` ใน Audit action |
| `APPROVAL_REQUEST` | `required_approver_role` → `bigint FK ROLE.id` (ชั่วคราวสำหรับ Skeleton) |


---


## ตาราง


### 1. STAFF


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `first_name` | text | NOT NULL |  |  |
| `last_name` | text | NOT NULL |  |  |
| `email` | text | NOT NULL |  |  |
| `password_hash` | text | NOT NULL |  |  |
| `role_id` | bigint | NOT NULL | FK ROLE.id |  |
| `home_ward_id` | bigint | NOT NULL | FK WARD.id |  |
| `status` | text | NOT NULL |  | `StaffStatus` (ไม่มีค่าการลา) |
| `created_at` | timestamptz | NOT NULL |  |  |
| `updated_at` | timestamptz | NOT NULL |  |  |


กติกา Deactivation: เมื่อเปลี่ยน `STAFF.status` เป็น `INACTIVE` Flow ที่แก้สถานะต้องยกเลิก
Roster ในอนาคตของคนนั้นด้วย; Coverage นับจาก Roster `ASSIGNED` และไม่กรอง `STAFF.status` ซ้ำ
ส่วน `HARD_CONSTRAINT_POLICY.require_active_staff` ใช้ตรวจสิทธิ์ผู้สมัครมาแทน
การยกเลิก Roster เมื่อ Deactivate ยังเป็นงานของ Flow นั้น ไม่ใช่งานของ Gap Calculator

### 2. ACTORS **(ใหม่)**


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `name` | text | NOT NULL |  | user: `str(STAFF.id)` / อื่น ๆ: `ActorName` |
| `actor_type` | text | NOT NULL |  | `ActorType` |
| `staff_id` | bigint | NULL | FK STAFF.id | ต้องมีค่าเมื่อ `actor_type = user` |


### 3. WARD


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `name` | text | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |
| `updated_at` | timestamptz | NOT NULL |  |  |
| `deactivated_at` | timestamptz | NULL |  |  |
| `is_active` | boolean | NOT NULL |  |  |
| `is_float_pool` | boolean | NOT NULL |  | Default false (รอบ 4 PR C1) หอ Float Pool ไม่มีเวรของตัวเอง คนที่หอบ้านเป็นหอนี้ได้ `source = FLOAT_POOL` ข้อ 6.19 ของ `workflow.md` |


### 4. SKILL


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `name` | text | NOT NULL |  |  |


### 5. ROLE


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `name` | text | NOT NULL |  |  |


### 6. STAFF_SKILL


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `staff_id` | bigint | NOT NULL | PK FK STAFF.id |  |
| `skill_id` | bigint | NOT NULL | PK FK SKILL.id |  |


### 7. SHIFT


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `ward_id` | bigint | NOT NULL | FK WARD.id |  |
| `patient_count` | integer | NOT NULL |  |  |
| `start_at` | timestamptz | NOT NULL |  |  |
| `end_at` | timestamptz | NOT NULL |  |  |
| `shift_type` | text | NOT NULL |  | `ShiftType` |
| `is_active` | boolean | NOT NULL |  |  |
| `deactivated_at` | timestamptz | NULL |  |  |
| `merge_window_seconds` | integer | NOT NULL |  | CHECK `>= 0` (`ck_shift_merge_window_seconds_non_negative`) ความยาว Merge Window ของเวรนี้เป็นวินาที 0 = ไม่รอ ไม่มีค่า Default ใน DB |


### 8. STAFFING_EVENTS


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `event_type` | text | NOT NULL |  | `EventType` |
| `shift_id` | bigint | NOT NULL | FK SHIFT.id |  |
| `occurred_at` | timestamptz | NOT NULL |  |  |
| `staff_id` | bigint | NULL | FK STAFF.id | ต้องมีค่าเมื่อเป็น Event กลุ่มบุคลากร (CHECK ตาม `event_type`) **(ใหม่ v5)** |
| `payload` | jsonb | NOT NULL |  | `{}` ถ้าไม่มีรายละเอียด **(ใหม่ v5)** |
| `status` | text | NOT NULL |  | `EventStatus` **(ใหม่)** |
| `processed_at` | timestamptz | NULL |  | เวลาที่ Merge Window ของ Event นี้ปิด ว่างเมื่อ `status = RECEIVED` ตั้งเมื่อเป็น `PROCESSED` หรือ `IGNORED` Event ที่ปิดพร้อมกันได้ค่าเดียวกัน CHECK `ck_staffing_events_processed_at_matches_status`: ว่างก็ต่อเมื่อ `status = RECEIVED` |
| `case_id` | bigint | NULL | FK STAFFING_CASES.id | เคสที่ Event นี้เป็นส่วนหนึ่ง ตั้งตอน Merge Window ปิดเมื่อเป็น `PROCESSED` ว่างเมื่อเป็น `RECEIVED` หรือ `IGNORED` เคสหนึ่งมีได้หลาย Event |


### 9. STAFFING_REQUIREMENTS


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `shift_id` | bigint | NOT NULL | FK SHIFT.id |  |
| `required_staff` | integer | NOT NULL |  | จำนวนคนที่ต้องการตามภาระงาน = `ceil(patient_count / maximum_patients_per_nurse)` เป็น Input ของ Headcount Gap ตั้งแต่รอบ 1 PR 1b ค่า Seed ตรงกับสูตร และ PART B ของ Merge Gap (PR M) จะ UPDATE ในแถวเดิมเมื่อจำนวนผู้ป่วยเปลี่ยน (`workflow.md` ข้อ 3.6) |
| `minimum_staff` | integer | NOT NULL |  | จำนวนคนขั้นต่ำคงที่ของเวร เป็น Input ของ Headcount Gap ตั้งแต่รอบ 1 PR 1b: เป้าหมาย = `max(required_staff, minimum_staff)` เมื่อ `HARD_CONSTRAINT_POLICY.preserve_minimum_staffing` เปิด และ `required_staff` อย่างเดียวเมื่อปิด |
| `created_at` | timestamptz | NOT NULL |  |  |


### 10. STAFFING_REQUIREMENT_ROLE


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `staffing_requirement_id` | bigint | NOT NULL | PK FK STAFFING_REQUIREMENTS.id |  |
| `role_id` | bigint | NOT NULL | PK FK ROLE.id |  |
| `required_count` | integer | NOT NULL |  |  |


### 11. STAFFING_REQUIREMENT_SKILL


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `staffing_requirement_id` | bigint | NOT NULL | PK FK STAFFING_REQUIREMENTS.id |  |
| `skill_id` | bigint | NOT NULL | PK FK SKILL.id |  |
| `required_count` | integer | NOT NULL |  |  |


### 12. STAFFING_CASES


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `shift_id` | bigint | NOT NULL | FK SHIFT.id |  |
| `status` | text | NOT NULL |  | `CaseStatus` (ไม่มี `IGNORED`) |
| `required_replacement_time` | timestamptz | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |
| `updated_at` | timestamptz | NOT NULL |  |  |


### 13. STAFF_UNAVAILABILITY **(เปลี่ยนชื่อจาก STAFF_AVAILABILITY)**


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `start_at` | timestamptz | NOT NULL |  |  |
| `end_at` | timestamptz | NULL |  | NULL = ยังไม่รู้วันกลับ |
| `reason` | text | NOT NULL |  | `AvailabilityReason` **(ใหม่ v5)** |


เก็บเฉพาะช่วงที่ไม่พร้อม ไม่มีแถว = พร้อม (เฉพาะ `STAFF.status = ACTIVE`) จึงไม่มี `is_available` แล้ว ลายาว เช่น ลาคลอด ใช้ `PLANNED_LEAVE` แถวเดียวที่ `end_at` ไกล


| `reason` | เงื่อนไข | `end_at` ตอนสร้างแถว | Event |
|---|---|---|---|
| `PLANNED_LEAVE` | แจ้งลา และช่วงที่ลาไม่ชนเวรที่มี `ROSTER_ASSIGNMENT` สถานะ `ASSIGNED` หรือ `PENDING_APPROVAL` | วันสิ้นสุดการลาที่อนุมัติ | ไม่สร้าง |
| `UNPLANNED_LEAVE` | แจ้งลาก่อนระบบบันทึก `NO_SHOW` และช่วงที่ลาชนเวรที่มี `ROSTER_ASSIGNMENT` สถานะ `ASSIGNED` หรือ `PENDING_APPROVAL` | เวลากลับที่บุคลากรแจ้ง ถ้าแจ้งแค่ว่ามาเวรนี้ไม่ได้ ใช้ `SHIFT.end_at` | `STAFF_UNAVAILABLE` |
| `NO_SHOW` | มีเวร ไม่แจ้งลา และไม่มี check-in ใน `ATTENDANCE` ภายในเวลาผ่อนผันหลัง `SHIFT.start_at` (สมมติ 15 นาที) ระบบสร้างแถวเอง | `SHIFT.end_at` ของเวรที่ขาด | `STAFF_UNAVAILABLE` |


**`reason` ไม่เปลี่ยนหลังสร้างแถว**


`reason` บอกสิ่งที่ระบบรู้ตอนเวรเริ่ม ถ้า `NO_SHOW` แล้วแจ้งลาย้อนหลัง แถวยังเป็น `NO_SHOW`


**การเปลี่ยน `end_at`**


* กลับมาเร็วกว่าที่บันทึก: ลด `end_at` เป็นเวลาที่กลับจริง รวมถึง `NO_SHOW` แล้วมาสาย ให้ใช้เวลา check-in
* หยุดนานกว่าที่บันทึก: ขยาย `end_at` หรือเพิ่มแถวใหม่
* ไม่รู้วันกลับ: `end_at` เป็น NULL ถือว่าไม่พร้อมตั้งแต่ `start_at` จนกว่าจะใส่ค่า เมื่อรู้วันกลับให้ใส่ `end_at`
* `NO_SHOW` หลายเวรติดกัน: ระบบตรวจทีละเวรและสร้างแถวใหม่ทุกเวร ไม่เดาล่วงหน้า


### 14. ROSTER_ASSIGNMENT


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `shift_id` | bigint | NOT NULL | FK SHIFT.id |  |
| `status` | text | NOT NULL |  | `RosterStatus` |
| `assignment_type` | text | NOT NULL |  | `AssignmentType` |
| `candidate_source` | text | NULL |  | `CandidateSource` |
| `actual_start_at` | timestamptz | NULL |  | ว่าง = `SHIFT.start_at` |
| `actual_end_at` | timestamptz | NULL |  | ว่าง = `SHIFT.end_at`; CHECK start < end เมื่อมีทั้งคู่ |
| `transferred_from_assignment_id` | bigint | NULL | FK ROSTER_ASSIGNMENT.id, UNIQUE | แถวต้นทางของการย้าย |
| `created_at` | timestamptz | NOT NULL |  |  |
| `updated_at` | timestamptz | NOT NULL |  |  |


CHECK ของ `actual_start_at` / `actual_end_at` ตรวจได้เฉพาะเมื่อมีทั้งคู่ ส่วน mixed NULL ต้องตรวจปลายช่วงหลัง fallback กับเวลา Shift ผ่าน `roster_time_service.effective_interval()` ใน writer (replacement และ `create_transfer()` ของ C2 และ C3 เรียกแล้วหลังล็อก Shift) การเขียน SQL โดยตรงไม่ผ่านตัวตรวจนี้

### 15. CANDIDATE_PLANS


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `solver_status` | text | NOT NULL |  | `SolverStatus` |
| `generated_at` | timestamptz | NOT NULL |  |  |
| `execution_time_ms` | integer | NOT NULL |  |  |
| `objective_score` | numeric | NULL |  |  |
| `solver_version` | text | NOT NULL |  | รอบ 2 PR B = `"cp-sat-v1"` (รอบ 1 = `"weighted-v1"`, Skeleton = `"stub"`) |
| `hard_constraint_policy_id` | bigint | NOT NULL | FK HARD_CONSTRAINT_POLICY.id |  |
| `soft_constraint_policy_id` | bigint | NOT NULL | FK SOFT_CONSTRAINT_POLICY.id |  |
| `input_snapshot` | jsonb | NOT NULL |  | ค่าที่ Solver ใช้คิด: `captured_at`, `timezone`, `day`, `week_start`, `gap_id`, `targets`, `weights` (ค่าน้ำหนักของ `SoftWeights` เป็นข้อความ `"เศษ/ส่วน"` พร้อม `source_order`), `candidates` (ค่าของแต่ละคนเรียงตาม `rank` มี `hours_this_week_exact`, `overtime_hours_exact`, `penalty_exact` เป็นข้อความ `"เศษ/ส่วน"` คู่กับช่อง `float` เดิมที่ใช้แสดงผลอย่างเดียว; Plan ก่อน PR E ไม่มี `weights` และช่อง `_exact`), `skipped` (ช่วงที่แต่ละ `candidates[]` มีเพิ่มในรอบ 4 PR T1 คือ `cover_start_at`, `cover_end_at`, `source_assignment_id` `source_assignment_id` มีค่าตั้งแต่ C2 สำหรับผู้สมัครที่ย้ายทั้งเวร (`cover_*` ว่าง) และตั้งแต่ C3 `cover_*` มีค่าเมื่อย้ายบางส่วนของเวร และเป็น `null` สำหรับคนอื่น; รอบ 4 PR T4 เพิ่ม key ระดับบน `intervals` (ช่วงที่ยังขาด: `start_at`, `end_at` และ `headcount` / `roles` / `skills` รูปเดียวกับ `targets`) กับ `partial_plan` (boolean, true เมื่อ Wave แรกมาจากแผนบางส่วน) และในแต่ละ `candidates[]` ของ Wave แรกเพิ่ม `credits` (`target_type`, `selection_type`, `role_id`, `skill_id`, `start_at`, `end_at` ช่วงที่เครดิตนับ ว่าง = ทั้งเวร) ตัวอ่านคะแนนไม่สนใจ key ที่ไม่รู้จัก) |


### 16. CANDIDATE_ITEMS


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `plan_id` | bigint | NOT NULL | FK CANDIDATE_PLANS.id |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `rank` | integer | NOT NULL |  |  |
| `source` | text | NOT NULL |  | `CandidateSource` |
| `proposed_shift_id` | bigint | NOT NULL | FK SHIFT.id |  |
| `working_time_snapshot_id` | bigint | NULL | FK STAFF_WORKING_TIME_SNAPSHOT.id | Snapshot ที่ Solver ใช้ตอนจัดอันดับผู้สมัครคนนี้ เพิ่มใน PR 2a NULL เฉพาะแถวที่เขียนก่อน PR 2a |
| `cover_start_at` | timestamptz | NULL |  | เริ่มช่วงที่ผู้สมัครมาทำ ว่างทั้ง `cover_start_at` และ `cover_end_at` = ทั้งเวร (รอบ 4 PR T1) |
| `cover_end_at` | timestamptz | NULL |  | สิ้นสุดช่วงที่ผู้สมัครมาทำ |
| `source_assignment_id` | bigint | NULL | FK ROSTER_ASSIGNMENT.id | แถว Roster ของเวรต้นทางที่ผู้สมัครถูกย้ายออกมา ว่าง = ไม่ใช่การย้าย (รอบ 4 PR T1) |

CHECK `ck_candidate_items_cover_both_or_neither`: `(cover_start_at IS NULL) = (cover_end_at IS NULL)` และ `ck_candidate_items_cover_in_order`: `cover_start_at < cover_end_at` ประกาศใน `__table_args__` ของ Model แถวเดิมทุกแถวได้ NULL ทั้งสามคอลัมน์ (ทั้งเวร ไม่ใช่การย้าย)


### 16.1 CANDIDATE_ITEM_TARGET


ตารางลูกของ `CANDIDATE_ITEMS` เก็บว่าผู้สมัครถูกเลือกมาเติม Target ไหน คนหนึ่งคนมีได้หลายแถว

| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `candidate_item_id` | bigint | NOT NULL | FK CANDIDATE_ITEMS.id |  |
| `target_type` | text | NOT NULL |  | `TargetType`: `HEADCOUNT`, `ROLE`, `SKILL` |
| `role_id` | bigint | NULL | FK ROLE.id | ใช้เมื่อ Target เป็น `ROLE` |
| `skill_id` | bigint | NULL | FK SKILL.id | ใช้เมื่อ Target เป็น `SKILL` |
| `selection_type` | text | NOT NULL |  | `SelectionType`: `PRIMARY` หรือ `RESERVE` |

CHECK `ck_candidate_item_target_role_id_matches_target_type`: `(target_type = 'ROLE') = (role_id IS NOT NULL)` และ `ck_candidate_item_target_skill_id_matches_target_type`: `(target_type = 'SKILL') = (skill_id IS NOT NULL)` ประกาศใน `__table_args__` ของ Model

ผู้เขียนมีสองจุด ผ่าน `optimization_service.record_item_targets()`: Solver เขียนให้กลุ่มของ Wave แรก และ `contact_candidate` เขียนให้ทุกคนที่มันเลือกเอง (PR 2b) คนหนึ่งคนได้แถวของทุก Target ที่ยังไม่เป็น 0 ตอนเขาถูกเลือก คนที่ถูกนับภายในจำนวน Gap ของ Target นั้นเป็น `PRIMARY` ที่เกินจาก Gap จนถึง Target เป็น `RESERVE` แถวไม่ถูกแก้ทีหลัง


### 17. CONTACTS


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `line_id` | text | NULL |  |  |
| `line_uid` | text | NULL |  |  |
| `is_active` | boolean | NOT NULL |  |  |


PR K เพิ่ม `uq_contacts_line_uid` UNIQUE ทุก line_uid ที่ไม่เป็น NULL รวมแถว inactive; NULL ซ้ำได้ Migration หยุดเมื่อ legacy UID ซ้ำโดยไม่แก้เจ้าของเอง

### 18. CANDIDATE_OUTREACH


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `candidate_item_id` | bigint | NOT NULL | FK CANDIDATE_ITEMS.id |  |
| `channel` | text | NOT NULL |  | `Channel` |
| `sent_at` | timestamptz | NULL |  |  |
| `response_at` | timestamptz | NULL |  |  |
| `expires_at` | timestamptz | NULL |  | เวลาหมดอายุของ Offer ตั้งตอนส่ง = `sent_at` + `OUTREACH_POLICY.offer_timeout_seconds` เมื่อ `clock.now() >= expires_at` แล้วยัง `SENT` จะเป็น `TIMEOUT` โดย Job; CHECK `status != SENT OR expires_at IS NOT NULL` |
| `status` | text | NOT NULL |  | `OutreachStatus` |


**งานส่ง LINE (รอบ 3 PR L, Migration `c6e9a2b4d8f1`)**

| Field | Type | Null | หมายเหตุ |
|---|---|---|---|
| `delivery_status` | text | NULL | `PENDING`, `ACCEPTED` (LINE รับ API แล้ว ไม่ใช่ผู้สมัครตอบรับ), `FAILED`, `CANCELLED`, `NO_CONTACT` (ไม่มีบัญชี LINE ให้ส่ง; Offer ยังเป็น SENT); NULL สำหรับโหมดจำลองและประวัติเดิม |
| `delivery_attempts` | integer | NOT NULL | Default 0, CHECK 0 ถึง 3; 429/401/403 ไม่นับ |
| `delivery_retry_key` | text | NULL | UUID ที่ใช้เหมือนเดิมทุกครั้งต่อ Offer |
| `delivery_payload` | jsonb | NULL | ผู้รับและข้อความคงที่ ไม่เปลี่ยนระหว่าง retry; Offer ใหม่ไม่มี binding ให้เป็น NULL/NO_CONTACT; intent เดิมที่ binding เปลี่ยนเก็บ payload เดิมแต่หยุดส่งเป็น NO_CONTACT โดยไม่เปลี่ยนสถานะ Offer |
| `delivery_next_attempt_at` | timestamptz | NULL | เวลาลองครั้งถัดไปจาก backend clock |
| `delivery_claim` | text | NULL | UUID ของผู้ส่งที่จองงานครั้งนี้ |
| `delivery_lease_until` | timestamptz | NULL | หมดสิทธิ์จองหลัง 60 วินาที ให้ Job เก็บตกเมื่อ process ล่ม |
| `delivery_last_result` | text | NULL | รหัส HTTP หรือ `TIMEOUT`; ไม่เก็บ Secret หรือ body ที่ LINE คืน |

Partial index `ix_candidate_outreach_delivery_due` ใช้กับ `delivery_status = PENDING` การส่งเริ่มหลัง Transaction ของ Wave Commit แล้วเท่านั้น

### 19. ATTENDANCE


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `shift_id` | bigint | NULL | FK SHIFT.id | เวรของ check-in (`workflow.md` ข้อ 6.24) ไม่ Backfill แถวที่ว่างนับ OT ตามเดิมแต่ไม่นับเป็น check-in ของเวรใด |
| `check_in_at` | timestamptz | NOT NULL |  | มาจาก `app.core.clock.now()` (รอบ 5) |
| `check_out_at` | timestamptz | NULL |  |  |
| `work_minutes` | integer | NULL |  | เวลาทำงานจริงทั้งหมด รวม OT |
| `overtime_minutes` | integer | NULL | CHECK | ส่วนของ `work_minutes` ที่เป็น OT CHECK `0 <= overtime_minutes <= work_minutes` NULL = ข้อมูลยังไม่ครบ ไม่ใช่ 0 |
| `synced_at` | timestamptz | NOT NULL |  |  |

UNIQUE (`staff_id`, `shift_id`) เฉพาะแถวที่ `shift_id` ไม่ว่าง (Partial Unique Index `uq_attendance_staff_shift`) กด check-in ซ้ำได้แถวเดิม

CHECK `ck_attendance_overtime_within_work`: `overtime_minutes >= 0 AND overtime_minutes <= work_minutes` ผ่านเมื่อคอลัมน์ใดคอลัมน์หนึ่งเป็น NULL เพราะแถวนั้นยังไม่สรุป จึงยังไม่มีค่าให้เทียบ


### 20. STAFF_WORKING_TIME_SNAPSHOT


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `hours_today` | numeric | NOT NULL |  | ชั่วโมงของเวรที่เริ่มในวันเดียวกับ `captured_at` (Asia/Bangkok) นับทั้งเวร รวมเวรที่ยังไม่เริ่ม |
| `hours_this_week` | numeric | NOT NULL |  | ชั่วโมงของเวรที่เริ่มในสัปดาห์ของ `captured_at` (จันทร์ 00:00 ถึงจันทร์ถัดไป) รวมเวรที่ยังไม่เริ่ม ไม่รวมเวรที่เคสเสนอ ใช้ให้คะแนน |
| `rest_hours` | numeric | NOT NULL |  | ชั่วโมงตั้งแต่เวรล่าสุดจบถึง `captured_at` เป็น 0 ตอนกำลังอยู่เวร และเป็น 0 เมื่อไม่มีเวรก่อนหน้า (แยกสองกรณีนี้ไม่ได้) ไม่ใช้ตรวจหรือให้คะแนนในรอบ 1 |
| `overtime_hours` | numeric | NOT NULL |  | OT ที่ทำไปแล้วในสัปดาห์ของ `captured_at` รวมจาก `ATTENDANCE.overtime_minutes` ของแถวที่สรุปแล้ว นับตาม `check_in_at` ใช้ให้คะแนน |
| `consecutive_shifts` | integer | NOT NULL |  | จำนวนเวรในลำดับเวรต่อเนื่องปัจจุบัน ณ `captured_at` เป็น 0 เมื่อพักจากเวรล่าสุดเกิน 24 ชั่วโมง ไม่ใช้ตรวจหรือให้คะแนนในรอบ 1 |
| `consecutive_night_shifts` | integer | NOT NULL |  | จำนวนเวร `NIGHT` ติดกันที่ท้ายลำดับนั้น ไม่ใช้ตรวจหรือให้คะแนนในรอบ 1 |
| `captured_at` | timestamptz | NOT NULL |  | เวลาอ้างอิงของ Snapshot = `clock.now()` ของรอบ Optimize ค่าเดียวกันทุกคนในรอบ |

`working_time_service.capture()` เป็นผู้เขียนจุดเดียว (PR 2a) เขียนแถวใหม่ทุกครั้งที่ Solver รัน ไม่แก้แถวเดิม นับเฉพาะ Roster ที่สถานะอยู่ใน `COMMITTED_ROSTER_STATUSES` เวรที่จบก่อนต้นสัปดาห์เกิน 31 วันไม่ถูกโหลด ลำดับเวรต่อเนื่องที่ยาวกว่านั้นจึงถูกตัด


### 21. APPROVAL_POLICY


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `ratio` | numeric | NOT NULL |  | จำนวนคำขอรออนุมัติที่ Head Nurse หนึ่งคนรับไหว ใช้คำนวณเพดานของ Auto-Approval (`docs/workflow.md` ข้อ 6.22, รอบ 4 PR A) Seed = 2 ความหมายเดิม (ตัวคูณ Ratio ผู้ป่วยต่อพยาบาล) ยกเลิกในรอบ 4 |
| `approval_timeout_seconds` | integer | NOT NULL | CHECK > 0 | Seed = 900; ใช้ตั้งเส้นตายตอนสร้างคำขอ PR T |
| `supervisor_after_seconds` | integer | NOT NULL | CHECK > 0 และ < approval_timeout_seconds | Seed = 600; Supervisor กดแทนได้ตั้งแต่ requested_at + ค่านี้ (PR S) |
| `incoming_count` | integer | NOT NULL |  | เพดานสูงสุดของคิวคำขอรออนุมัติต่อหอ เพดานของ Auto-Approval คือค่าที่ต่ำกว่าระหว่าง `ratio` × จำนวน Head Nurse ที่ Active ของหอ กับค่านี้ (`docs/workflow.md` ข้อ 6.22) Seed = 10 |
| `version` | text | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |


### 22. HARD_CONSTRAINT_POLICY


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `version` | text | NOT NULL |  |  |
| `minimum_rest_hours` | numeric | NOT NULL |  | gap ขั้นต่ำของการจบ shift หนึ่งไปอีก shift หนึ่ง ใช้ปฏิเสธการจัดเวรที่พักไม่พอ |
| `maximum_daily_hours` | numeric | NOT NULL |  |  |
| `maximum_weekly_hours` | numeric | NOT NULL |  |  |
| `maximum_consecutive_shifts` | integer | NOT NULL | CHECK | เพิ่มในรอบ 1: จำนวนเวรต่อเนื่องสูงสุดหลังรวมเวรที่เสนอ CHECK `ck_hard_constraint_policy_consecutive_shifts_non_negative` (`>= 0`) Seed = 7 พักไม่เกิน 24 ชั่วโมงนับว่าต่อเนื่อง ไม่มี Default หลัง Migration |
| `maximum_patients_per_nurse` | numeric | NOT NULL |  | จำนวนผู้ป่วยสูงสุดต่อพยาบาล ใช้ Ratio เดียวทั้งโรงพยาบาลใน Skeleton; Seed = 2; CHECK มากกว่า 0 และเป็นค่าจำกัด; ไม่มี Default หลัง Migration |
| `prevent_shift_conflict` | boolean | NOT NULL |  |  |
| `require_matching_role` | boolean | NOT NULL |  |  |
| `require_matching_skill` | boolean | NOT NULL |  |  |
| `require_active_staff` | boolean | NOT NULL |  | ผู้สมัครมาแทนต้อง ACTIVE; เมื่อ Deactivate ต้องยกเลิก Roster ในอนาคตตามกติกาข้อ 1 |
| `preserve_minimum_staffing` | boolean | NOT NULL |  |  |
| `preserve_source_ward_minimum` | boolean | NOT NULL |  |  |
| `effective_from` | timestamptz | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |


### 23. SOFT_CONSTRAINT_POLICY


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `version` | text | NOT NULL |  |  |
| `candidate_count_weight` | numeric | NOT NULL |  |  |
| `consecutive_shift_weight` | numeric | NOT NULL |  |  |
| `workload_imbalance_weight` | numeric | NOT NULL |  |  |
| `projected_overtime_weight` | numeric | NOT NULL |  |  |
| `roster_change_weight` | numeric | NOT NULL |  |  |
| `candidate_source_weight` | numeric | NOT NULL |  | Weight ของพจน์แหล่งที่มาใน `plan_penalty` Seed = 200 ลำดับของแหล่งที่มายังอ่านจาก `candidate_source_priority` ไม่มี Default หลัง Migration |
| `candidate_source_priority` | jsonb | NOT NULL |  |  |
| `optimization_priority` | jsonb | NOT NULL |  |  |
| `effective_from` | timestamptz | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |
| `solver_time_limit_seconds` | integer | NOT NULL | CHECK > 0 | Seed = 3; เพดานเวลารวมของการเรียก `solve()` หนึ่งครั้ง (`workflow.md` ข้อ 6.14) Migration `c9e4a7b2d5f8` เติม 3 ให้ Policy เดิม รอบ 2 PR B |

ค่า Seed ของรอบ 1: `candidate_count_weight = 1000`, `candidate_source_weight = 200`, `workload_imbalance_weight = 1`, `consecutive_shift_weight = 5`, `projected_overtime_weight = 2`, `roster_change_weight = 300` Weight ต้องไม่ติดลบ ไม่งั้น Solver โยน Error และเคสเป็น `FAILED`


### 23.1 OUTREACH_POLICY


กติกาของ Offer ต่อผู้สมัคร ตารางและ `maximum_concurrent_offers_per_staff` เพิ่มใน PR 1c ส่วน `offer_timeout_seconds` เพิ่มใน PR O

Model และ Migration `d91a6c8e203f` เพิ่มแล้วใน PR 1c Seed เป็น `id=1`, `version=demo-outreach-v1` และเพดาน 3 โหลดด้วย `policy_service.get_outreach_policy()` ตาม `id=1`; `effective_from` ยังไม่ได้ใช้เลือกเวอร์ชัน

| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `maximum_concurrent_offers_per_staff` | integer | NOT NULL | CHECK | จำนวน Offer ที่ยังเปิดได้พร้อมกันต่อคน นับ Offer ที่ `SENT` หรือ `ACCEPTED` บนเคสที่ยังเดินอยู่ CHECK `> 0` Seed = 3 |
| `offer_timeout_seconds` | integer | NOT NULL | CHECK | อายุของ Offer เป็นวินาที ใช้ตั้ง `CANDIDATE_OUTREACH.expires_at` ตอนส่ง CHECK `> 0` Seed = 300 |
| `version` | text | NOT NULL |  |  |
| `effective_from` | timestamptz | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |


### 24. STAFFING_GAP


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `staffing_requirement_id` | bigint | NOT NULL | FK STAFFING_REQUIREMENTS.id |  |
| `headcount_gap` | integer | NOT NULL |  | `max(effective_minimum - จำนวนคนในเวร, 0)` |
| `effective_minimum` | integer | NOT NULL |  | เป้าหมายจำนวนคนที่ใช้คิด Gap แถวนี้: `max(required_staff, minimum_staff)` เมื่อ `preserve_minimum_staffing` เปิด และ `required_staff` เมื่อปิด |
| `computed_at` | timestamptz | NOT NULL |  |  |
| `evaluated_from` | timestamptz | NULL |  | จุดเริ่มของช่วงที่วัด `max(Backend Clock ตอนประเมิน, เวลาเริ่มเวร)` เวรที่จบไปแล้วตอนประเมินวัดทั้งเวร จึงเป็นเวลาเริ่มเวร ว่างสำหรับแถวก่อนรอบ 4 (รอบ 4 PR T3) |




`effective_minimum` คือเป้าหมายที่ใช้คิด Gap แถวนั้นจริง `required_staff` และ `minimum_staff` อ่านผ่าน `staffing_requirement_id` ไม่เก็บซ้ำ
แต่ `required_staff` ถูก UPDATE ในแถวเดิม ค่าที่อ่านได้จึงเป็นค่าปัจจุบัน ค่าเดียวที่บอกเป้าหมายตอนคิดคือ `effective_minimum`
Migration `d5e8f20b63a4` แทน Snapshot เดิม (`patient_count`, `patients_per_nurse` และ CHECK `ck_staffing_gap_patients_per_nurse_valid`) ด้วยคอลัมน์นี้ ไม่ Backfill ทั้งขาขึ้นและขาลง และหยุดถ้ามีแถวใน `STAFFING_GAP` (ให้ `make reset` ก่อน)

รอบ 4 PR T3: `headcount_gap` และตัวเลขใน `STAFFING_GAP_ROLE` กับ `STAFFING_GAP_SKILL` คือช่วงที่ขาดมากที่สุดของแต่ละด้านจากตารางรายช่วง (ข้อ 26.1 ถึง 26.3) ไม่บวกข้ามช่วง ใช้แสดงผลได้ แต่การตัดสิน `RESOLVED` อ่านตารางรายช่วง แถวที่ไม่มีแถวรายช่วง (ก่อนรอบ 4) ถือว่าขาดทั้งเวรตามตัวเลขในแถวนี้

### 25. STAFFING_GAP_ROLE


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `gap_id` | bigint | NOT NULL | PK FK STAFFING_GAP.id |  |
| `role_id` | bigint | NOT NULL | PK FK ROLE.id |  |
| `required_count` | integer | NOT NULL |  |  |
| `current_count` | integer | NOT NULL |  |  |
| `gap_count` | integer | NOT NULL |  |  |


### 26. STAFFING_GAP_SKILL


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `gap_id` | bigint | NOT NULL | PK FK STAFFING_GAP.id |  |
| `skill_id` | bigint | NOT NULL | PK FK SKILL.id |  |
| `required_count` | integer | NOT NULL |  |  |
| `current_count` | integer | NOT NULL |  |  |
| `gap_count` | integer | NOT NULL |  |  |


### 26.1 STAFFING_GAP_INTERVAL (รอบ 4 PR T3)


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `gap_id` | bigint | NOT NULL | FK STAFFING_GAP.id | มี Index |
| `start_at` | timestamptz | NOT NULL |  | เริ่มช่วง |
| `end_at` | timestamptz | NOT NULL |  | จบช่วง (ไม่รวม) |
| `required_count` | integer | NOT NULL |  |  |
| `current_count` | integer | NOT NULL |  | คนที่อยู่ตลอดช่วงนี้ |
| `gap_count` | integer | NOT NULL |  |  |

UNIQUE `(gap_id, start_at)`


ช่วง `[start_at, end_at)` แบ่งตามเวลาที่คนในเวรเข้าหรือออกจริง (เวลาจริงของ `ROSTER_ASSIGNMENT` ข้อ 6.20 ของ `workflow.md`) ตั้งแต่ `STAFFING_GAP.evaluated_from` ถึงเวลาจบเวร ช่วงติดกันที่ตัวเลขเท่ากันถูกรวมเป็นช่วงเดียว เวรที่ทุกคนทำทั้งเวรจึงมีช่วงเดียว ทั้งสามตารางใช้ช่วงชุดเดียวกัน และเก็บทุกช่วงรวมช่วงที่ไม่ขาด CHECK `start_at < end_at` และ `gap_count = GREATEST(required_count - current_count, 0)` ตัวเลขไม่ติดลบ

### 26.2 STAFFING_GAP_ROLE_INTERVAL (รอบ 4 PR T3)


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `gap_id` | bigint | NOT NULL | FK STAFFING_GAP.id | มี Index |
| `role_id` | bigint | NOT NULL | FK ROLE.id |  |
| `start_at` | timestamptz | NOT NULL |  | เริ่มช่วง |
| `end_at` | timestamptz | NOT NULL |  | จบช่วง (ไม่รวม) |
| `required_count` | integer | NOT NULL |  |  |
| `current_count` | integer | NOT NULL |  | คนที่อยู่ตลอดช่วงนี้ |
| `gap_count` | integer | NOT NULL |  |  |

UNIQUE `(gap_id, role_id, start_at)`


### 26.3 STAFFING_GAP_SKILL_INTERVAL (รอบ 4 PR T3)


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `gap_id` | bigint | NOT NULL | FK STAFFING_GAP.id | มี Index |
| `skill_id` | bigint | NOT NULL | FK SKILL.id |  |
| `start_at` | timestamptz | NOT NULL |  | เริ่มช่วง |
| `end_at` | timestamptz | NOT NULL |  | จบช่วง (ไม่รวม) |
| `required_count` | integer | NOT NULL |  |  |
| `current_count` | integer | NOT NULL |  | คนที่อยู่ตลอดช่วงนี้ |
| `gap_count` | integer | NOT NULL |  |  |

UNIQUE `(gap_id, skill_id, start_at)`


### 27. SAFETY_VALIDATION


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `candidate_item_id` | bigint | NOT NULL | FK CANDIDATE_ITEMS.id |  |
| `outreach_id` | bigint | NOT NULL | FK CANDIDATE_OUTREACH.id | Offer ของผล Safety รอบนี้ PR T |
| `hard_constraint_policy_id` | bigint | NOT NULL | FK HARD_CONSTRAINT_POLICY.id |  |
| `is_passed` | boolean | NOT NULL |  |  |
| `failure_reason` | text | NULL |  |  |
| `validation_snapshot` | jsonb | NOT NULL |  |  |
| `validated_at` | timestamptz | NOT NULL |  |  |


### 28. APPROVAL_REQUEST


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `candidate_item_id` | bigint | NOT NULL | FK CANDIDATE_ITEMS.id |  |
| `outreach_id` | bigint | NOT NULL | FK CANDIDATE_OUTREACH.id | Offer ของคำขอรอบนี้ PR T |
| `expires_at` | timestamptz | NOT NULL | | เส้นตาย snapshot ตอนสร้าง; ตัดสินได้เมื่อ now < expires_at |
| `is_timed_out` | boolean | NOT NULL | | Default false; Job เท่านั้นตั้ง true |
| `required_approver_role` | bigint | NULL | FK ROLE.id | Skeleton เก็บ ROLE.id ของ HEAD_NURSE |
| `approval_mode` | text | NOT NULL |  | `ApprovalMode` |
| `is_pending` | boolean | NOT NULL |  | สถานะอ่านจาก `is_pending` / `is_approved` / `decided_at` |
| `approver_id` | bigint | NULL | FK STAFF.id |  |
| `is_approved` | boolean | NULL |  |  |
| `reason` | text | NULL |  |  |
| `decided_at` | timestamptz | NULL |  |  |
| `requested_at` | timestamptz | NOT NULL |  |  |


### 28.1 APPROVAL_WARD_DECISION (PR S)

หนึ่งแถวต่อการตัดสินของคนในแต่ละฝั่ง คำขอหอเดียวใช้ DESTINATION; การย้ายใช้ DESTINATION และ SOURCE ตามหอของเวรต้นทาง ไม่ใช่หอบ้านของผู้สมัคร UNIQUE (`approval_request_id`, `side`) คำขอก่อน S ไม่ Backfill แถวประวัติ

| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK | |
| `approval_request_id` | bigint | NOT NULL | FK APPROVAL_REQUEST.id | |
| `ward_id` | bigint | NOT NULL | FK WARD.id | |
| `side` | text | NOT NULL | UNIQUE ร่วม | `ApprovalSide`: DESTINATION / SOURCE |
| `approver_id` | bigint | NOT NULL | FK STAFF.id | ผู้กดจริง |
| `decided_as` | text | NOT NULL | | `ApproverCapacity`: HEAD_NURSE / SUPERVISOR |
| `is_approved` | boolean | NOT NULL | | |
| `reason` | text | NULL | | เหตุผลของฝั่งนั้น |
| `decided_at` | timestamptz | NOT NULL | | |

การอนุมัติฝั่งแรกไม่เปลี่ยนผลรวมของ APPROVAL_REQUEST (`is_pending=true`, `is_approved/approver_id/decided_at=null`) ฝั่งสุดท้ายหรือการปฏิเสธจึงเขียนผลรวม Timeout คงประวัติฝั่งที่กดแล้ว Auto-Approval ไม่เขียนตารางนี้

Migration ตั้ง delay ของ Policy เดิมเป็น `min(600, approval_timeout_seconds - 1)` เพื่อรองรับ Policy ที่สั้นกว่า 600 วินาที ถ้า timeout <= 1 หยุดก่อน DDL ต้องแก้ Policy ก่อนอัปเกรด ไม่เปลี่ยนเส้นตายของคำขอเดิม `supervisor_from` คำนวณจากเวลาสร้างกับ Policy ปัจจุบันเมื่ออ่าน

### 29. STRUCTURED_HANDOVER


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `shift_id` | bigint | NOT NULL | FK SHIFT.id |  |
| `incoming_staff_id` | bigint | NULL | FK STAFF.id |  |
| `roster_assignment_id` | bigint | NOT NULL | FK ROSTER_ASSIGNMENT.id, UNIQUE | **[รอบ 5 · PR H1]** แถว Roster ของคนที่มาแทน หนึ่ง Handover ต่อหนึ่งแถว ตารางไม่มีแถวเดิม จึงไม่ต้อง Backfill |
| `content` | jsonb | NOT NULL |  | รูปข้อมูลอยู่ที่ `workflow.md` ข้อ 6.25 (`version` = 1) |
| `generated_at` | timestamptz | NOT NULL |  |  |
| `delivery_*` | | | | **[รอบ 5 · PR H2]** สถานะการส่งทาง LINE ชุดเดียวกับของ `CANDIDATE_OUTREACH` (`delivery_status`, `delivery_attempts`, `delivery_retry_key`, `delivery_payload`, `delivery_next_attempt_at`, `delivery_claim`, `delivery_lease_until`, `delivery_last_result`) H2 ตั้งชื่อและ CHECK ให้ตรงกับของ Offer |


### 30. AUDIT_LOG


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NULL | FK STAFFING_CASES.id |  |
| `event_id` | bigint | NULL | FK STAFFING_EVENTS.id | ตั้งในแถวที่เป็นเรื่องของ Event ตัวนั้น (`EVENT_RECEIVED`, `EVENT_IGNORED`, `UNAVAILABILITY_CREATED`, `ASSIGNMENT_CANCELLED`, `PATIENT_COUNT_UPDATED`, `REQUIREMENT_UPDATED`) แถวพวกนี้ไม่ใส่ `case_id` Timeline ของเคสรวมแถวของ Event ที่เป็นของเคสด้วย |
| `actor_id` | bigint | NOT NULL | FK ACTORS.id |  |
| `entity_type` | text | NOT NULL |  | `EntityType` |
| `entity_id` | bigint | NULL |  | NULL ได้สำหรับ composite key (ยังไม่ Audit ใน Skeleton) |
| `action` | text | NOT NULL |  | `AuditAction` |
| `payload` | jsonb | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |


`actor_type` ถูกย้ายไปอยู่ที่ `ACTORS` ไม่มีในตารางนี้แล้ว


### 31. MANUAL_ASSIGNMENT **(ใหม่ในรอบ 2)**

หนึ่งแถวต่อการที่ Head Nurse จัดคนหนึ่งคนเข้าเวรของเคสที่อยู่ `MANUAL_HANDOFF` (รอบ 2 PR H, Migration `b7d3e5a1c9f2`) ผูกแถว Roster กับเคส ซึ่ง `ROSTER_ASSIGNMENT` ทำเองไม่ได้

| Field | Type | Null | Key | หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id | เคสที่เวรนี้ปิด Gap ให้ |
| `roster_assignment_id` | bigint | NOT NULL | FK ROSTER_ASSIGNMENT.id, UNIQUE | เวรหนึ่งแถวปิด Gap ให้ได้เคสเดียว ผู้ถูกจัด เวร และสถานะอ่านจากแถวนี้ ไม่เก็บซ้ำ |
| `assigned_by` | bigint | NOT NULL | FK STAFF.id | Head Nurse ที่กด |
| `reason` | text | NULL |  | หมายเหตุของการจัด ไม่เกิน 500 ตัวอักษร ไม่มีผลต่อการตรวจกฎ |
| `created_at` | timestamptz | NOT NULL |  |  |

* ไม่มีคอลัมน์รหัสกฎที่ข้าม เพราะการจัดคนเองต้องผ่าน Hard Rules ทุกข้อ (R2-Q14)
* ไม่ผูกกับ `CANDIDATE_ITEMS` เพราะคนที่ถูกเลือกอาจไม่อยู่ใน Plan


---


### 32. LINE_WEBHOOK_EVENT (รอบ 3 PR L)

| Field | Type | Null | Key | หมายเหตุ |
|---|---|---|---|---|
| `webhook_event_id` | text | NOT NULL | PK | รหัส Event จาก LINE; PK กันการประมวลผลพร้อมกันซ้ำ |
| `processed_at` | timestamptz | NOT NULL | | เวลาจาก backend clock เมื่อจัดการ Event |

Commit พร้อมผลของ Event ใน Transaction เดียว ส่วนการปฏิเสธทางธุรกิจบันทึกแถว terminal แล้วตอบ 200 ไม่เก็บข้อความรหัส LINK, Signature หรือ reply token

### 33. LINE_ACCOUNT_LINK_CODE (รอบ 3 PR K)

| Field | Type | Null | หมายเหตุ |
|---|---|---|---|
| `id` | bigint | NOT NULL | PK |
| `staff_id` | bigint | NOT NULL | FK STAFF; index |
| `code_hash` | text | NOT NULL | UNIQUE SHA-256 hex 64 ตัว; ไม่เก็บรหัสจริง |
| `created_at` | timestamptz | NOT NULL | Backend Clock |
| `expires_at` | timestamptz | NOT NULL | created_at + 10 นาที; CHECK > created_at |
| `used_at` | timestamptz | NULL | ใช้สำเร็จพร้อม Contact/Audit/dedup ใน Transaction เดียว |
| `revoked_at` | timestamptz | NULL | revoke รหัสที่ยังไม่ใช้เมื่อปลดบัญชี |

CHECK `used_at IS NULL OR revoked_at IS NULL`; รหัสที่ใช้แล้วไม่ถูก revoke ย้อนหลัง รหัสที่หมดอายุหรือ revoke ใช้ไม่ได้ ล็อก Staff → Code → Contact; เก็บประวัติไว้และไม่บันทึก hash/รหัส/LINE UID ลง Audit

### 34. RANK_EXPLANATION (รอบ 3 PR X)

| Field | Type | Null | หมายเหตุ |
|---|---|---|---|
| `id` | bigint | NOT NULL | PK |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES |
| `plan_id` | bigint | NOT NULL | FK CANDIDATE_PLANS |
| `prompt_version` | text | NOT NULL | เช่น `rank-explanation-v2` |
| `status` | text | NOT NULL | `ExplanationStatus` (ไม่มี CHECK ตาม D8) |
| `input_hash` | text | NULL | SHA-256 hex ของ `input_payload` แบบ Canonical |
| `input_payload` | jsonb | NULL | ที่ส่งให้ LLM จริง มีแต่ตัวเลข อันดับ ชื่อพจน์ ไม่มีชื่อหรือ `staff_id` |
| `text` | text | NULL | ตั้งเมื่อ `READY` เท่านั้น |
| `provider`, `model_id` | text | NULL | ตั้งเมื่อ `READY` (`model_id` เป็น NULL ของ `fake`) |
| `attempts` | integer | NOT NULL | default 0; นับ Attempt ถาวร |
| `claim` | uuid | NULL | ผู้ถือ Claim ของ Sweep |
| `lease_until` | timestamptz | NULL | Claim หมดอายุหลังเวลานี้ |
| `failure_reason` | text | NULL | ค่าของ `LlmCallStatus` หรือ `INVALID_INPUT`, `NO_CANDIDATES`, `ATTEMPTS_EXHAUSTED`; ไม่เก็บข้อความ Error ของ SDK |
| `created_at`, `updated_at` | timestamptz | NOT NULL | Backend Clock |
| `ready_at` | timestamptz | NULL | |

UNIQUE (`plan_id`, `prompt_version`); partial index `ix_rank_explanation_pending` บน `id` เมื่อ `status = 'PENDING'` แถวเกิดใน Transaction ของ Plan (เมื่อ `LLM_ENABLED`) และ Job เป็นผู้เติมผล

### 35. LLM_CALL_LOG (รอบ 3 PR X)

| Field | Type | Null | หมายเหตุ |
|---|---|---|---|
| `id` | bigint | NOT NULL | PK |
| `explanation_id` | bigint | NOT NULL | FK RANK_EXPLANATION |
| `case_id`, `plan_id` | bigint | NOT NULL | ไม่มี FK; `plan_id` มี index |
| `provider`, `prompt_version` | text | NOT NULL | |
| `model_id`, `region`, `input_hash` | text | NULL | |
| `attempt` | integer | NOT NULL | เริ่มที่ 1; UNIQUE (`explanation_id`, `attempt`) |
| `status` | text | NOT NULL | `LlmCallStatus` เริ่มที่ `IN_FLIGHT` ก่อนเรียก; ถ้าค้าง = เครื่องล่มและไม่ทราบ Token |
| `error_type` | text | NULL | ชื่อ Exception หรือรหัส Error เท่านั้น |
| `input_tokens`, `output_tokens`, `total_tokens` | integer | NULL | NULL = ไม่ทราบ ไม่ใช่ 0 |
| `duration_ms` | integer | NULL | |
| `input_price_per_mtok_usd`, `output_price_per_mtok_usd` | numeric(12,6) | NULL | ราคาต่อล้าน Token ที่ใช้ |
| `estimated_cost_usd` | numeric(14,8) | NULL | คำนวณเมื่อทราบทั้ง Token และราคา |
| `started_at` | timestamptz | NOT NULL | |
| `finished_at` | timestamptz | NULL | |
| `created_at` | timestamptz | NOT NULL | Backend Clock |

ไม่เก็บ Prompt หรือข้อความตอบ

## Enum


ค่าทั้งหมดอยู่ใน `backend/app/domain/enums.py` ตารางนี้สรุปว่าแต่ละตัวใช้ที่คอลัมน์ไหน


| Enum | ใช้ที่ | ค่า |
|---|---|---|
| `EventType` | STAFFING_EVENTS.event_type | `STAFF_UNAVAILABLE`, `ASSIGNMENT_CANCELLED`, `PATIENT_SURGE`, `REQUIREMENT_CHANGED` |
| `EventStatus` | STAFFING_EVENTS.status | `RECEIVED`, `PROCESSED`, `IGNORED` |
| `CaseStatus` | STAFFING_CASES.status | `OPEN`, `ASSESSING`, `OPTIMIZING`, `OUTREACH`, `WAITING_RESPONSE`, `SAFETY_VALIDATION`, `WAITING_APPROVAL`, `EXECUTING`, `RESOLVED`, `MANUAL_HANDOFF`, `UNRESOLVED`, `FAILED` |
| `StaffStatus` | STAFF.status | `ACTIVE`, `INACTIVE` |
| `ShiftType` | SHIFT.shift_type | `DAY`, `EVENING`, `NIGHT` |
| `AvailabilityReason` | STAFF_UNAVAILABILITY.reason | `PLANNED_LEAVE`, `UNPLANNED_LEAVE`, `NO_SHOW` |
| `RosterStatus` | ROSTER_ASSIGNMENT.status | `PENDING_APPROVAL`, `ASSIGNED`, `CANCELLED`, `COMPLETED` |
| `AssignmentType` | ROSTER_ASSIGNMENT.assignment_type | `REGULAR`, `REPLACEMENT` |
| `CandidateSource` | ROSTER_ASSIGNMENT.candidate_source, CANDIDATE_ITEMS.source | `SAME_WARD`, `FLOAT_POOL`, `CROSS_WARD` |
| `SolverStatus` | CANDIDATE_PLANS.solver_status | `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `MODEL_INVALID`, `UNKNOWN` |
| `OptimizationObjective` | SOFT_CONSTRAINT_POLICY.optimization_priority (ใน JSON) | `MIN_CANDIDATE_COUNT`, `MIN_CONSECUTIVE_SHIFT`, `CANDIDATE_SOURCE`, `WEEKLY_WORKLOAD_FAIRNESS`, `MIN_PROJECTED_OVERTIME` |
| `TargetType` | CANDIDATE_ITEM_TARGET.target_type | `HEADCOUNT`, `ROLE`, `SKILL` |
| `SelectionType` | CANDIDATE_ITEM_TARGET.selection_type | `PRIMARY`, `RESERVE` |
| `ManualHandoffReason` | `reason` ใน payload ของ `MANUAL_HANDOFF` (ไม่เก็บเป็นคอลัมน์) | `NO_CANDIDATE_LEFT`, `NO_FEASIBLE_PLAN`, `SOLVER_TIMEOUT` (รอบ 2 PR B: Solver หมดเวลาโดยยังไม่มีแผน) |
| `OutreachStatus` | CANDIDATE_OUTREACH.status | `PENDING`, `SENT`, `ACCEPTED`, `REJECTED`, `TIMEOUT`, `FAILED`, `CANCELLED` |
| `CandidateResponse` | API ของ LINE / LINE Sim (ไม่เก็บใน DB) | `ACCEPT`, `REJECT` |
| `Channel` | CANDIDATE_OUTREACH.channel | `LINE` |
| `ValidationResult` | ผลตรวจรายข้อใน validation_snapshot | `PASS`, `FAIL` |
| `ApprovalMode` | APPROVAL_REQUEST.approval_mode | `MANUAL`, `AUTO` |
| `ApprovalOutcome` | API การตัดสิน (ไม่เก็บเป็นคอลัมน์) | `WAITING_OTHER_WARD`, `ASSIGNED`, `REJECTED`, `TRANSFER_CANCELLED`, `EXECUTION_FAILED` |
| `ApprovalSide` | APPROVAL_WARD_DECISION.side (รอบ 4 PR S) | `DESTINATION`, `SOURCE` |
| `ApproverCapacity` | APPROVAL_WARD_DECISION.decided_as (รอบ 4 PR S) | `HEAD_NURSE`, `SUPERVISOR` |
| `TransferFailureReason` | payload `reason` ของ `TRANSFER_CHECK_FAILED` (รอบ 4 PR C2 เขียนแล้ว) | `SOURCE_COVERAGE_LOST`, `DESTINATION_WINDOW_PASSED`, `HARD_RULE_FAILED` (C3 ลบ `SOURCE_SHIFT_STARTED` ออกตาม R4-Q43 แถว Audit เก่าที่ C2 เขียนไว้ตอนอนุมัติครบหลังเวรต้นทางเริ่มอาจยังมีค่านี้ ตัวอ่านเก็บเป็นข้อความดิบ) |
| `ActorType` | ACTORS.actor_type | `user`, `system`, `component` |
| `ActorName` | ACTORS.name (ที่ไม่ใช่ user) | `system`, `workflow_orchestrator`, `staffing_gap_assessment_agent`, `constraint_fair_scheduling_agent`, `outreach_agent`, `safety_rule_engine` |
| `EntityType` | AUDIT_LOG.entity_type | `STAFFING_EVENTS`, `STAFFING_CASES`, `STAFFING_GAP`, `CANDIDATE_PLANS`, `CANDIDATE_OUTREACH`, `SAFETY_VALIDATION`, `APPROVAL_REQUEST`, `ROSTER_ASSIGNMENT`, `STRUCTURED_HANDOVER`, `STAFF_UNAVAILABILITY`, `SHIFT`, `STAFFING_REQUIREMENTS` และค่าที่เพิ่มในรอบ 3: `CONTACTS`, `ATTENDANCE` |
| `ExplanationStatus` | RANK_EXPLANATION.status (รอบ 3 PR X) | `PENDING`, `READY`, `FAILED`, `SKIPPED` |
| `LlmCallStatus` | LLM_CALL_LOG.status (รอบ 3 PR X) | `IN_FLIGHT`, `SUCCEEDED`; ลองซ้ำได้: `TIMEOUT`, `THROTTLED`, `SERVICE_ERROR`; ไม่ลองซ้ำ: `CONFIG_ERROR`, `TRUNCATED`, `INVALID_OUTPUT` |
| `AuditAction` | AUDIT_LOG.action | `EVENT_RECEIVED`, `EVENT_IGNORED`, `CASE_OPENED`, `CASE_STATUS_CHANGED`, `CASE_RESOLVED`, `MANUAL_HANDOFF`, `WORKFLOW_FAILED`, `GAP_ASSESSED`, `SOLVER_EXECUTED`, `OFFER_SENT`, `OFFER_ACCEPTED`, `OFFER_REJECTED`, `OFFER_TIMEOUT`, `SAFETY_PASSED`, `SAFETY_FAILED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `APPROVAL_REJECTED`, `APPROVAL_TIMEOUT`, `ASSIGNMENT_CREATED`, `HANDOVER_GENERATED`, `ATTENDANCE_CHECKED_IN`, `OFFER_CANCELLED_NOT_NEEDED` **[รอบ 5 · PR N2]**, `UNAVAILABILITY_CREATED`, `UNAVAILABILITY_UPDATED`, `ASSIGNMENT_CANCELLED`, `PATIENT_COUNT_UPDATED`, `REQUIREMENT_UPDATED` และค่าที่เพิ่มในรอบ 2: `MANUAL_ASSIGNMENT_CREATED`, `CASE_CLOSED_UNRESOLVED`, `OFFER_CANCELLED_BY_ASSIGNMENT` และค่าที่เพิ่มในรอบ 3: `OFFER_DELIVERY_FAILED`, `LINE_ACCOUNT_LINKED`, `LINE_ACCOUNT_UNLINKED` และค่าที่เพิ่มในรอบ 4 ที่ยังไม่มีโค้ดเขียน: `APPROVAL_WARD_APPROVED`, `ASSIGNMENT_TRANSFERRED`, `TRANSFER_CHECK_FAILED` |
| `CheckInSource` | AUDIT_LOG.payload.source ของ `ATTENDANCE_CHECKED_IN` | `SELF`, `SIMULATED` |
| `HandoverReason` | STRUCTURED_HANDOVER.content.reason | `UNPLANNED_LEAVE`, `NO_SHOW`, `ASSIGNMENT_CANCELLED`, `PATIENT_SURGE`, `REQUIREMENT_CHANGED` **[รอบ 5 · PR H1]** |


**กลุ่มของ EventType**


* กลุ่มบุคลากร (ต้องมี `staff_id`): `STAFF_UNAVAILABLE`, `ASSIGNMENT_CANCELLED`
* กลุ่มภาระงาน (`staff_id` เป็น NULL): `PATIENT_SURGE`, `REQUIREMENT_CHANGED`


**กลุ่มของ CaseStatus**


* จุดรอ: `WAITING_RESPONSE`, `WAITING_APPROVAL`
* สิ้นสุด: `RESOLVED`, `UNRESOLVED`, `FAILED`
* หยุดอัตโนมัติแต่ยังเปิดให้คนจัดการ: `MANUAL_HANDOFF` ตั้งแต่รอบ 2 ออกได้ไป `RESOLVED` (T8) หรือ `UNRESOLVED` (T9) จากการกระทำของ Head Nurse หรือจากขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด ไม่ใช่จาก Handler หรือ `recompute()` (`docs/workflow.md` ข้อ 6.12)


---


## Schema รอบ 4

Schema ที่มี Migration ของรอบ 4 ทำครบถึง S แล้วตามรายการบนสุด: T1 → T2 → C1 → T3 → S (`f2a7c9d4e6b8`) Migration ที่เพิ่มภายหลังต้องต่อจาก head ของ staging จริงและรักษา head เดียว

Role `SUPERVISOR` เป็นแถวข้อมูลใน `ROLE` ไม่มี Migration PR S เพิ่ม Role (id 3) ใน Seed แล้ว PR W4 ใช้ Role นี้เพิ่มผู้ใช้งาน Supervisor และข้อมูลหลายหอ

## Constraint ที่ควรใส่ใน Migration แรก


| ตาราง | Constraint | เหตุผล |
|---|---|---|
| `STAFFING_EVENTS` | CHECK: Event กลุ่มบุคลากรต้องมี `staff_id`, กลุ่มภาระงานต้องเป็น NULL | กันข้อมูลผิดประเภท |
| `ACTORS` | CHECK: `actor_type = 'user'` ↔ `staff_id IS NOT NULL` | ผู้กระทำที่เป็นคนต้องผูกพนักงาน |
| `ACTORS` | UNIQUE (`staff_id`) | พนักงานหนึ่งคนมี Actor เดียว |
| `ACTORS` | UNIQUE (`name`) WHERE `actor_type <> 'user'` | Component แต่ละตัวมีแถวเดียว |


CHECK ทั้งสองข้อนี้ไม่ได้ล็อกค่าของ Enum แค่บังคับความสัมพันธ์ระหว่างคอลัมน์ จึงไม่ขัดกับการตัดสินใจเรื่องไม่ใส่ CHECK ให้ Enum

**ประกาศที่ไหน:** ทั้ง 4 ข้อประกาศใน `__table_args__` ของ Model (`backend/app/db/models/actor.py` และ `staffing_event.py`) ไม่ได้เขียนเพิ่มด้วยมือในไฟล์ Migration `alembic revision --autogenerate` จึงสร้างให้เอง และไม่เสนอลบ UNIQUE ทิ้งในรอบถัดไป ถ้าจะแก้ Constraint ให้แก้ที่ Model แล้วสร้าง Migration ใหม่

ข้อยกเว้น: Alembic ไม่เทียบ CHECK constraint ถ้าแก้ CHECK ใน Model (รวมถึงเมื่อกลุ่มของ `EventType` เปลี่ยน) ต้องเขียน Migration เองให้ลบแล้วสร้าง CHECK ใหม่ `tests/integration/test_migrations.py` ตรวจว่า Constraint ทั้ง 4 ข้อมีอยู่ใน DB จริง


## ยังไม่ตัดสิน (ไม่กระทบ Skeleton)


| เรื่อง | หมายเหตุ |
|---|---|
| ON DELETE / ON UPDATE / Index | ค่อยกำหนดหลัง Skeleton |




# Candidate Skip Reasons

## Purpose

The `skipped` field records why candidates were skipped while Outreach selected the people of a wave.

Reasons come from checks against the candidate's current data at selection time. They must not be guessed from candidate rank or copied from an outdated Solver result.

This section follows the round 1 contract: wave selection is `docs/workflow.md` sections 6.6 and 6.7, and the Hard Rules are `docs/round1/round1-contract-draft.md` section 7.2.

## Selection Process

1. Read candidates from the plan of the case in rank order. The plan holds every candidate that passed the Hard Rules when the Solver ran, not only the first wave.
2. Leave out candidates this case has already contacted (any outreach row of the case, whatever its status).
3. Recheck each remaining candidate with the shared Hard Rules evaluator. A failed rule skips the candidate with the code of that rule.
4. Check the offer limit. A candidate who already holds `OUTREACH_POLICY.maximum_concurrent_offers_per_staff` offers is skipped with `OFFER_LIMIT_REACHED`.
5. Fill the wave targets from the candidates that are left and send an offer to every selected candidate at the same time.
6. If nobody can be selected: the case waits in `WAITING_APPROVAL` when a pending approval can still fill the gap, waits in `WAITING_RESPONSE` when a paused offer has not expired, and otherwise moves to `MANUAL_HANDOFF`.

Only candidates examined and skipped in steps 3 and 4 belong in `skipped`. A candidate who passed the checks but was not needed because every target was already full is not skipped; that candidate stays in the plan for a later wave.

## Skip Reasons

| Code | Criteria | Policy or Rule |
|---|---|---|
| `STAFF_NOT_ACTIVE` | Candidate is not `ACTIVE`. | `require_active_staff` |
| `ALREADY_ON_SHIFT` | Candidate already has a committed roster assignment on the target shift. | Always checked |
| `UNAVAILABLE` | A recorded unavailability period overlaps the proposed shift, or the candidate has a `CANCELLED` roster row on the proposed shift (they left it or were taken off it). | Always checked |
| `SHIFT_CONFLICT` | Candidate has a committed assignment on another shift whose time overlaps the proposed shift. | `prevent_shift_conflict` |
| `ROLE_MISMATCH` | Candidate does not have the role of the target they are selected to fill. | `require_matching_role` |
| `SKILL_MISMATCH` | Candidate does not have the skill of the target they are selected to fill. | `require_matching_skill` |
| `INSUFFICIENT_REST` | Adding the shift would leave less rest than the minimum before or after it. | `minimum_rest_hours` |
| `DAILY_HOURS_EXCEEDED` | Total hours of the day, including the proposed shift, would exceed the limit. | `maximum_daily_hours` |
| `WEEKLY_HOURS_EXCEEDED` | Total hours of the week, including the proposed shift, would exceed the limit. | `maximum_weekly_hours` |
| `CONSECUTIVE_SHIFTS_EXCEEDED` | Consecutive shifts, counted after inserting the proposed shift, would exceed the limit. A rest of 24 hours or less keeps two shifts in the same run. | `maximum_consecutive_shifts` |
| `SOURCE_WARD_MINIMUM_VIOLATION` | Moving the candidate out of an existing assignment would leave the source shift below its target. Round 4 PR C2: `SourceShift(shift_id, leaves_gap)` is set when the cover is a move, and `leaves_gap` comes from `gap_service.gap_without()`, the same gap calculator as cases, over headcount, role and skill from `max(cover start, Backend Clock)` to the source shift end (`docs/workflow.md` 6.19). Checked at planning, Safety, wave selection and at the final transfer. | `preserve_source_ward_minimum` |
| `OFFER_LIMIT_REACHED` | Candidate already holds the maximum number of open offers: `SENT`, or `ACCEPTED` on a case that is still running. | `OUTREACH_POLICY.maximum_concurrent_offers_per_staff` |
| `GAP_TIME_MISMATCH` | Round 4 PR T4. The candidate's cover window (`cover_start_at` to `cover_end_at`, the whole shift when empty) overlaps no time slice of the gap that is still short, so they could only work while the ward is already full. Checked in `optimization_service` before the Solver runs. Can happen since PR C3, which gives candidates partial cover windows (for example a gap that is short only in the first half of the shift, and a mover whose cover starts in the second half); C2 moved only whole shifts. | Solver planning only; not a Hard Rule |
| `SOURCE_SHIFT_TAKEN` | Round 4 PR C2: another candidate from the same source shift already gives this case a live offer, a pending request or a move (`docs/workflow.md` 6.19). | Wave selection only |

The first eleven codes are Hard Rules. The Solver, wave selection and Safety must return the same result from the same data. `GAP_TIME_MISMATCH` is not a Hard Rule either: the Solver step judges it from the gap slices and the cover window, so it is written to the plan snapshot's `skipped` only, never by wave selection or Safety. `OFFER_LIMIT_REACHED` is not a Hard Rule: it is checked by the Solver and by wave selection, never by Safety, because the candidate being validated always holds the accepted offer of their own case.

The old codes `OPEN_OFFER`, `HAS_OPEN_OFFER` and `SOURCE_WARD_MINIMUM` are not used.

The Solver also leaves out a candidate who can fill nothing: the case is short of a role or a skill only (`headcount_gap = 0`) and the candidate has none of them. The code is `SKILL_MISMATCH` when a skill is short, otherwise `ROLE_MISMATCH`.

### Policy Flags

A disabled policy flag must not produce a skip reason. Numeric limits have no flag and are always checked. For the maximum limits (daily hours, weekly hours, consecutive shifts), being equal to the limit passes and only exceeding it fails. For `minimum_rest_hours`, rest equal to the minimum passes and less rest fails.

For example, when `require_matching_skill = false`, a skill mismatch alone does not reject the candidate.

### Role and Skill

A candidate does not have to close every gap of the case alone. Role and skill are evaluated against the targets the candidate is selected to fill, stored in `CANDIDATE_ITEM_TARGET`. A candidate selected only for headcount passes without the missing skill.

A candidate who fills no role target (selected for headcount or a skill only) must still have a role that the requirement of the shift lists. The caller of the evaluator passes those role IDs as the candidate's role set, so any other role fails with `ROLE_MISMATCH`. Any role passes only when the requirement lists no role at all.

### Time Overlap

Two intervals overlap when:

    existing.start_at < proposed.end_at
    AND existing.end_at > proposed.start_at

Intervals that only touch at their boundaries do not overlap. Rest requirements are checked separately.

For unavailability without an end time, treat it as continuing from its start time onward.

### Source-Ward Minimum

`SOURCE_WARD_MINIMUM_VIOLATION` applies only when the proposed action removes an existing source assignment. A candidate with no source assignment passes.

The source shift must keep at least its target headcount after the candidate leaves. The target uses the same formula as the gap calculation: `max(minimum_staff, required_staff)` when `preserve_minimum_staffing` is on, and `required_staff` when it is off.

Round 1 only adds assignments, so this rule cannot fail in the actual selection flow yet. It is covered by unit tests.

### Work-Hour Rules

- Hours of a shift are `end_at - start_at`, counted whole and not split across midnight.
- A shift belongs to the day of its `start_at` in Asia/Bangkok time.
- A week runs from Monday 00:00 to the next Monday 00:00 in Asia/Bangkok time, by `start_at`.
- Counted assignments are those in `COMMITTED_ROSTER_STATUSES`, plus the proposed shift.
- Consecutive shifts use real time and do not reset at a day or week boundary.
- Weekly overtime is not a hard limit. It only affects ranking.

## Candidates Already Contacted

A candidate the case has already contacted does not receive another offer from the same case.

Their previous outcome is recorded by the outreach status and the matching audit event, such as `OFFER_REJECTED` or `OFFER_TIMEOUT`. This is different from failing a current eligibility check, so these candidates are left out before the `skipped` list is built.

## Multiple Failed Rules

`skipped` is a list of `{staff_id, reason}` with one fixed code per skipped candidate.

A candidate may fail more than one rule. One code is kept: the first failed Hard Rule in the order of the Skip Reasons table above, which is also the order Safety uses for `failure_reason`. The Solver step checks the time slices after the Hard Rules and before the offer limit, so `GAP_TIME_MISMATCH` appears only for a candidate who passed the Hard Rules, in the plan snapshot's `skipped`. The offer limit is checked after the Hard Rules, so `OFFER_LIMIT_REACHED` appears only for a candidate who passed them. PR 2b removes the interim rule that excluded anyone holding another offer. Both the Solver and Wave selection now use the cap alone after the Hard Rules. Do not rely on database query order.

## OFFER_SENT Payload Example

One `OFFER_SENT` row is written per candidate of the wave, in rank order. Only the first row of a wave carries `skipped`.

    {
      "outreach_id": 12,
      "staff_id": 203,
      "channel": "LINE",
      "wave": 2,
      "skipped": [
        {
          "staff_id": 204,
          "reason": "UNAVAILABLE"
        },
        {
          "staff_id": 205,
          "reason": "OFFER_LIMIT_REACHED"
        }
      ]
    }

Meaning:

- 204 was examined and skipped because of overlapping unavailability.
- 205 was examined and skipped because they already hold the maximum number of open offers.
- 203 passed the checks and received an offer in wave 2.

## MANUAL_HANDOFF Payload

If no candidate can be selected and the case stops, the `MANUAL_HANDOFF` payload carries `reason` (`NO_CANDIDATE_LEFT`, `NO_FEASIBLE_PLAN` or `SOLVER_TIMEOUT`), `stopped_at`, `cancelled_outreach_ids` and the collected `skipped` list.

Previously contacted candidates may also explain why no candidate remains, but their outcomes come from outreach history and must not be labelled as new Hard Rule failures.

## Storage and Display

- Use fixed codes rather than free-text skip reasons.
- Record `skipped` in the relevant `OFFER_SENT` or `MANUAL_HANDOFF` audit payload. No column is added.
- A skipped candidate receives no new `CANDIDATE_OUTREACH` row.
- A candidate with no outreach history can still appear as "Not contacted."
- The case page reads the reasons from the audit payload and translates the codes into readable explanations.

### Migration ของ PR T

`b7d2f8a1c6e4` ต่อจาก `a4b8c2d6e9f1`: เติมเส้นตายทุกคำขอเดิมเป็น requested_at + 900 วินาที และจับคู่ Safety/Approval กับ Offer ของ case/item เดียวกัน ถ้าจับคู่ไม่ได้หรือพบหลาย Offer ให้หยุดก่อน DDL เพื่อให้ซ่อมข้อมูล ไม่เลือกแถวเอง ไม่มีการ Reset ข้อมูล Job ข้ามคำขอประวัติที่ Offer ไม่ ACCEPTED และเคสที่หยุดแล้ว

มี partial index `ix_approval_request_pending_expiry` บน expires_at ของแถว is_pending=true; ค่า policy ต้อง > 0 และไม่มี server default ของระยะเวลา
