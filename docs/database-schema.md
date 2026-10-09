
# Database Schema & Enum (แผนที่จะ Implement)


> สรุปจากคู่มือ Schema v5 + การตัดสินใจล่าสุดของทีม ใช้คู่กับ `docs/workflow.md` และ `backend/app/domain/enums.py`
> สถานะ: สร้างแล้วใน Migration แรก (`backend/alembic/versions/2026_10_09_0646-63c7709cfe6c_initial_schema.py`)
> เพิ่ม `HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse` ใน Migration `a73d9e2c4b10` (Backfill Policy เดิม = 2 สำหรับ Demo)


## สรุปการตัดสินใจ


| เรื่อง | ตัดสินว่า |
|---|---|
| จำนวนตาราง | 30 ตาราง (29 เดิม + `ACTORS`) |
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


### 9. STAFFING_REQUIREMENTS


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `shift_id` | bigint | NOT NULL | FK SHIFT.id |  |
| `required_staff` | integer | NOT NULL |  | จำนวนเป้าหมายที่บันทึกใน Requirement; Skeleton ยังไม่ใช้เป็นเป้าหมาย Headcount Gap (ใช้สูตร Patient Count / Ratio แทน) |
| `minimum_staff` | integer | NOT NULL |  | จำนวนขั้นต่ำที่เก็บไว้สำหรับกฎความปลอดภัยในอนาคต เช่น เวรต้นทาง; ยังไม่ใช้ใน Gap Calculator ของ Skeleton |
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
| `event_id` | bigint | NOT NULL | FK STAFFING_EVENTS.id |  |
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
| `created_at` | timestamptz | NOT NULL |  |  |
| `updated_at` | timestamptz | NOT NULL |  |  |


### 15. CANDIDATE_PLANS


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `solver_status` | text | NOT NULL |  | `SolverStatus` |
| `generated_at` | timestamptz | NOT NULL |  |  |
| `execution_time_ms` | integer | NOT NULL |  |  |
| `objective_score` | numeric | NULL |  |  |
| `solver_version` | text | NOT NULL |  | Skeleton = `"stub"` |
| `hard_constraint_policy_id` | bigint | NOT NULL | FK HARD_CONSTRAINT_POLICY.id |  |
| `soft_constraint_policy_id` | bigint | NOT NULL | FK SOFT_CONSTRAINT_POLICY.id |  |
| `input_snapshot` | jsonb | NOT NULL |  |  |


### 16. CANDIDATE_ITEMS


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `plan_id` | bigint | NOT NULL | FK CANDIDATE_PLANS.id |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `rank` | integer | NOT NULL |  |  |
| `source` | text | NOT NULL |  | `CandidateSource` |
| `proposed_shift_id` | bigint | NOT NULL | FK SHIFT.id |  |


### 17. CONTACTS


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `line_id` | text | NULL |  |  |
| `line_uid` | text | NULL |  |  |
| `is_active` | boolean | NOT NULL |  |  |


### 18. CANDIDATE_OUTREACH


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `candidate_item_id` | bigint | NOT NULL | FK CANDIDATE_ITEMS.id |  |
| `channel` | text | NOT NULL |  | `Channel` |
| `sent_at` | timestamptz | NULL |  |  |
| `response_at` | timestamptz | NULL |  |  |
| `status` | text | NOT NULL |  | `OutreachStatus` |


### 19. ATTENDANCE


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `check_in_at` | timestamptz | NOT NULL |  |  |
| `check_out_at` | timestamptz | NULL |  |  |
| `work_minutes` | integer | NULL |  |  |
| `overtime_minutes` | integer | NULL |  |  |
| `synced_at` | timestamptz | NOT NULL |  |  |


### 20. STAFF_WORKING_TIME_SNAPSHOT


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `hours_today` | numeric | NOT NULL |  |  |
| `hours_this_week` | numeric | NOT NULL |  |  |
| `rest_hours` | numeric | NOT NULL |  |  |
| `overtime_hours` | numeric | NOT NULL |  |  |
| `consecutive_shifts` | integer | NOT NULL |  |  |
| `consecutive_night_shifts` | integer | NOT NULL |  |  |
| `captured_at` | timestamptz | NOT NULL |  |  |


### 21. APPROVAL_POLICY


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `ratio` | numeric | NOT NULL |  | Auto-approval threshold multiplier: activate when the nurse-to-patient ratio exceeds this value times the ward's required ratio. Team value = 2. |
| `incoming_count` | integer | NOT NULL |  | Policy value for the number of staff awaiting approval by the head nurse or nurse supervisor. Team value = 10; its comparison rule remains to be defined. |
| `version` | text | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |


### 22. HARD_CONSTRAINT_POLICY


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `version` | text | NOT NULL |  |  |
| `minimum_rest_hours` | numeric | NOT NULL |  |  |
| `maximum_daily_hours` | numeric | NOT NULL |  |  |
| `maximum_weekly_hours` | numeric | NOT NULL |  |  |
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
| `candidate_source_priority` | jsonb | NOT NULL |  |  |
| `optimization_priority` | jsonb | NOT NULL |  |  |
| `effective_from` | timestamptz | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |


### 24. STAFFING_GAP


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `staffing_requirement_id` | bigint | NOT NULL | FK STAFFING_REQUIREMENTS.id |  |
| `headcount_gap` | integer | NOT NULL |  |  |
| `computed_at` | timestamptz | NOT NULL |  |  |


งานต่อใน Wiring PR ก่อนเริ่มเขียน Gap ลง DB: เพิ่ม `patient_count` และ `patients_per_nurse`
(หรือ Policy ID ที่อ้างเวอร์ชันซึ่งไม่แก้ย้อนหลัง) เพื่อย้อนตรวจ Input ของการคำนวณแต่ละครั้ง
คอลัมน์เหล่านี้ยังไม่ได้เพิ่มใน Schema ปัจจุบัน

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


### 27. SAFETY_VALIDATION


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `candidate_item_id` | bigint | NOT NULL | FK CANDIDATE_ITEMS.id |  |
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
| `required_approver_role` | bigint | NULL | FK ROLE.id | Skeleton เก็บ ROLE.id ของ HEAD_NURSE |
| `approval_mode` | text | NOT NULL |  | `ApprovalMode` |
| `is_pending` | boolean | NOT NULL |  | สถานะอ่านจาก `is_pending` / `is_approved` / `decided_at` |
| `approver_id` | bigint | NULL | FK STAFF.id |  |
| `is_approved` | boolean | NULL |  |  |
| `reason` | text | NULL |  |  |
| `decided_at` | timestamptz | NULL |  |  |
| `requested_at` | timestamptz | NOT NULL |  |  |


### 29. STRUCTURED_HANDOVER


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NOT NULL | FK STAFFING_CASES.id |  |
| `shift_id` | bigint | NOT NULL | FK SHIFT.id |  |
| `incoming_staff_id` | bigint | NULL | FK STAFF.id |  |
| `content` | jsonb | NOT NULL |  |  |
| `generated_at` | timestamptz | NOT NULL |  |  |


### 30. AUDIT_LOG


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `case_id` | bigint | NULL | FK STAFFING_CASES.id |  |
| `actor_id` | bigint | NOT NULL | FK ACTORS.id |  |
| `entity_type` | text | NOT NULL |  | `EntityType` |
| `entity_id` | bigint | NULL |  | NULL ได้สำหรับ composite key (ยังไม่ Audit ใน Skeleton) |
| `action` | text | NOT NULL |  | `AuditAction` |
| `payload` | jsonb | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |


`actor_type` ถูกย้ายไปอยู่ที่ `ACTORS` ไม่มีในตารางนี้แล้ว


---


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
| `OutreachStatus` | CANDIDATE_OUTREACH.status | `PENDING`, `SENT`, `ACCEPTED`, `REJECTED`, `TIMEOUT`, `FAILED`, `CANCELLED` |
| `CandidateResponse` | API ของ LINE / LINE Sim (ไม่เก็บใน DB) | `ACCEPT`, `REJECT` |
| `Channel` | CANDIDATE_OUTREACH.channel | `LINE` |
| `ValidationResult` | ผลตรวจรายข้อใน validation_snapshot | `PASS`, `FAIL` |
| `ApprovalMode` | APPROVAL_REQUEST.approval_mode | `MANUAL`, `AUTO` |
| `ActorType` | ACTORS.actor_type | `user`, `system`, `component` |
| `ActorName` | ACTORS.name (ที่ไม่ใช่ user) | `system`, `workflow_orchestrator`, `staffing_gap_assessment_agent`, `constraint_fair_scheduling_agent`, `outreach_agent`, `safety_rule_engine` |
| `EntityType` | AUDIT_LOG.entity_type | `STAFFING_EVENTS`, `STAFFING_CASES`, `STAFFING_GAP`, `CANDIDATE_PLANS`, `CANDIDATE_OUTREACH`, `SAFETY_VALIDATION`, `APPROVAL_REQUEST`, `ROSTER_ASSIGNMENT`, `STRUCTURED_HANDOVER`, `STAFF_UNAVAILABILITY` |
| `AuditAction` | AUDIT_LOG.action | `EVENT_RECEIVED`, `EVENT_IGNORED`, `CASE_OPENED`, `CASE_STATUS_CHANGED`, `CASE_RESOLVED`, `MANUAL_HANDOFF`, `WORKFLOW_FAILED`, `GAP_ASSESSED`, `SOLVER_EXECUTED`, `OFFER_SENT`, `OFFER_ACCEPTED`, `OFFER_REJECTED`, `OFFER_TIMEOUT`, `SAFETY_PASSED`, `SAFETY_FAILED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `APPROVAL_REJECTED`, `ASSIGNMENT_CREATED`, `HANDOVER_GENERATED`, `UNAVAILABILITY_CREATED`, `UNAVAILABILITY_UPDATED` |


**กลุ่มของ EventType**


* กลุ่มบุคลากร (ต้องมี `staff_id`): `STAFF_UNAVAILABLE`, `ASSIGNMENT_CANCELLED`
* กลุ่มภาระงาน (`staff_id` เป็น NULL): `PATIENT_SURGE`, `REQUIREMENT_CHANGED`


**กลุ่มของ CaseStatus**


* จุดรอ: `WAITING_RESPONSE`, `WAITING_APPROVAL`
* สิ้นสุด: `RESOLVED`, `UNRESOLVED`, `FAILED`
* หยุดอัตโนมัติแต่ยังเปิดให้คนจัดการ: `MANUAL_HANDOFF`


---


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





