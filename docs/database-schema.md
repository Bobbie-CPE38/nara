
# Database Schema & Enum (แผนที่จะ Implement)


> สรุปจากคู่มือ Schema v5 + การตัดสินใจล่าสุดของทีม ใช้คู่กับ `docs/workflow.md` และ `backend/app/domain/enums.py`
> สถานะ: สร้างแล้วใน Migration แรก (`backend/alembic/versions/2026_10_09_0646-63c7709cfe6c_initial_schema.py`)
> Migration ถัดจากนั้น เรียงตามลำดับ:
> * `a73d9e2c4b10` เพิ่ม `HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse` (Backfill Policy เดิม = 2 สำหรับ Demo)
> * `b82e4f6a901c` ย่อชื่อ CHECK ของคอลัมน์นั้นเป็น `ck_hard_constraint_policy_patients_per_nurse_valid` (กติกาเดิม)
> * `c4d7e19a52f3` เพิ่ม Snapshot `patient_count` และ `patients_per_nurse` ใน `STAFFING_GAP` พร้อม CHECK (ไม่ Backfill, ดูข้อ 24)


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
| `merge_window_seconds` | integer | NOT NULL |  | CHECK `>= 0` ความยาว Merge Window ของเวรนี้เป็นวินาที 0 = ไม่รอ **(รอบ 1 ยังไม่มีใน DB)** |


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
| `processed_at` | timestamptz | NULL |  | เวลาที่ Merge Window ของ Event นี้ปิด ว่างเมื่อ `status = RECEIVED` ตั้งเมื่อเป็น `PROCESSED` หรือ `IGNORED` Event ที่ปิดพร้อมกันได้ค่าเดียวกัน CHECK: ว่างก็ต่อเมื่อ `status = RECEIVED` **(รอบ 1 ยังไม่มีใน DB)** |
| `case_id` | bigint | NULL | FK STAFFING_CASES.id | เคสที่ Event นี้เป็นส่วนหนึ่ง ตั้งตอน Merge Window ปิดเมื่อเป็น `PROCESSED` ว่างเมื่อเป็น `RECEIVED` หรือ `IGNORED` เคสหนึ่งมีได้หลาย Event **(รอบ 1 ยังไม่มีใน DB)** |


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
| `event_id` | bigint | NOT NULL | FK STAFFING_EVENTS.id | **(รอบ 1 จะลบ ใช้ `STAFFING_EVENTS.case_id` แทน เพราะเคสหนึ่งมีได้หลาย Event)** |
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
| `working_time_snapshot_id` | bigint | NULL | FK STAFF_WORKING_TIME_SNAPSHOT.id | Snapshot ที่ Solver ใช้ตอนจัดอันดับผู้สมัครคนนี้ **(รอบ 1 ยังไม่มีใน DB)** |


### 16.1 CANDIDATE_ITEM_TARGET **(รอบ 1 ยังไม่มีใน DB)**


ตารางลูกของ `CANDIDATE_ITEMS` เก็บว่าผู้สมัครถูกเลือกมาเติม Target ไหน คนหนึ่งคนมีได้หลายแถว

| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `candidate_item_id` | bigint | NOT NULL | FK CANDIDATE_ITEMS.id |  |
| `target_type` | text | NOT NULL |  | `HEADCOUNT`, `ROLE`, `SKILL` |
| `role_id` | bigint | NULL | FK ROLE.id | ใช้เมื่อ Target เป็น `ROLE` |
| `skill_id` | bigint | NULL | FK SKILL.id | ใช้เมื่อ Target เป็น `SKILL` |
| `selection_type` | text | NOT NULL |  | `PRIMARY` หรือ `RESERVE` |


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
| `expires_at` | timestamptz | NULL |  | เวลาหมดอายุของ Offer ตั้งตอนส่ง = `sent_at` + `OUTREACH_POLICY.offer_timeout_seconds` เลยเวลานี้แล้วยัง `SENT` จะเป็น `TIMEOUT` **(รอบ 1 ยังไม่มีใน DB)** |
| `status` | text | NOT NULL |  | `OutreachStatus` |


### 19. ATTENDANCE


| Field | Type | Null | Key | Enum / หมายเหตุ |
| :-- | :-- | :-- | :-- | :-- |
| `id` | bigint | NOT NULL | PK |  |
| `staff_id` | bigint | NOT NULL | FK STAFF.id |  |
| `check_in_at` | timestamptz | NOT NULL |  |  |
| `check_out_at` | timestamptz | NULL |  |  |
| `work_minutes` | integer | NULL |  | เวลาทำงานจริงทั้งหมด รวม OT |
| `overtime_minutes` | integer | NULL | CHECK | ส่วนของ `work_minutes` ที่เป็น OT CHECK `0 <= overtime_minutes <= work_minutes` NULL = ข้อมูลยังไม่ครบ ไม่ใช่ 0 |
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
| `minimum_rest_hours` | numeric | NOT NULL |  | gap ขั้นต่ำของการจบ shift หนึ่งไปอีก shift หนึ่ง ใช้ปฏิเสธการจัดเวรที่พักไม่พอ |
| `maximum_daily_hours` | numeric | NOT NULL |  |  |
| `maximum_weekly_hours` | numeric | NOT NULL |  |  |
| `maximum_consecutive_shifts` | integer | NOT NULL | CHECK | เพิ่มในรอบ 1: จำนวนเวรต่อเนื่องสูงสุดหลังรวมเวรที่เสนอ CHECK `>= 0` Seed = 7 พักไม่เกิน 24 ชั่วโมงนับว่าต่อเนื่อง |
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
| `candidate_source_weight` | numeric | NOT NULL |  | Weight ของพจน์แหล่งที่มาใน `plan_penalty` Seed = 200 ลำดับของแหล่งที่มายังอ่านจาก `candidate_source_priority` **(รอบ 1 ยังไม่มีใน DB เพิ่มใน PR 2a)** |
| `candidate_source_priority` | jsonb | NOT NULL |  |  |
| `optimization_priority` | jsonb | NOT NULL |  |  |
| `effective_from` | timestamptz | NOT NULL |  |  |
| `created_at` | timestamptz | NOT NULL |  |  |


### 23.1 OUTREACH_POLICY **(รอบ 1 ยังไม่มีใน DB)**


กติกาของ Offer ต่อผู้สมัคร ตารางและ `maximum_concurrent_offers_per_staff` เพิ่มใน PR 1c ส่วน `offer_timeout_seconds` เพิ่มใน PR O

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
| `effective_minimum` | integer | NOT NULL |  | เป้าหมายจำนวนคนที่ใช้คิด Gap แถวนี้: `max(required_staff, minimum_staff)` เมื่อ `preserve_minimum_staffing` เปิด และ `required_staff` เมื่อปิด **(รอบ 1 ยังไม่มีใน DB เพิ่มใน PR 1b)** |
| `patient_count` | integer | NOT NULL |  | Snapshot ของ `SHIFT.patient_count` ตอนคำนวณ **(ลบใน PR 1b)** |
| `patients_per_nurse` | numeric | NOT NULL | CHECK | Snapshot ของ `HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse` ตอนคำนวณ **(ลบใน PR 1b)** |
| `computed_at` | timestamptz | NOT NULL |  |  |


`patient_count` และ `patients_per_nurse` เป็น Snapshot ของ Input ที่ใช้คำนวณ Gap แถวนั้น
ค่าใน `SHIFT` และ Policy เปลี่ยนภายหลังได้ จึงเก็บไว้กับแถวเพื่อย้อนตรวจการคำนวณแต่ละครั้ง
CHECK `ck_staffing_gap_patients_per_nurse_valid`: `patients_per_nurse > 0` และไม่เป็น Infinity / NaN (กติกาเดียวกับ Policy)
Migration `c4d7e19a52f3` ไม่ Backfill และหยุดถ้ามีแถวเก่าใน `STAFFING_GAP` (ให้ `make reset` ก่อน)

รอบ 1 (PR 1b) เปลี่ยน Snapshot ของแถวนี้: เพิ่ม `effective_minimum` และลบ `patient_count`, `patients_per_nurse` พร้อม CHECK `ck_staffing_gap_patients_per_nurse_valid`
เพราะ Gap คิดจาก `required_staff` และ `minimum_staff` ของ Requirement แล้ว สองค่านั้นอ่านผ่าน `staffing_requirement_id` ไม่เก็บซ้ำ
แต่ `required_staff` ถูก UPDATE ในแถวเดิม ค่าที่อ่านได้จึงเป็นค่าปัจจุบัน ค่าเดียวที่บอกเป้าหมายตอนคิดคือ `effective_minimum`
Migration ของ PR 1b ไม่เติมค่าย้อนหลัง ทุกคน `make reset` หลัง merge

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
| `event_id` | bigint | NULL | FK STAFFING_EVENTS.id | ตั้งในแถวที่เป็นเรื่องของ Event ตัวนั้น (`EVENT_RECEIVED`, `UNAVAILABILITY_CREATED`, `EVENT_IGNORED`) Timeline ของเคสรวมแถวของ Event ที่เป็นของเคสด้วย **(รอบ 1 ยังไม่มีใน DB)** |
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
| `EntityType` | AUDIT_LOG.entity_type | `STAFFING_EVENTS`, `STAFFING_CASES`, `STAFFING_GAP`, `CANDIDATE_PLANS`, `CANDIDATE_OUTREACH`, `SAFETY_VALIDATION`, `APPROVAL_REQUEST`, `ROSTER_ASSIGNMENT`, `STRUCTURED_HANDOVER`, `STAFF_UNAVAILABILITY`, `SHIFT`, `STAFFING_REQUIREMENTS` |
| `AuditAction` | AUDIT_LOG.action | `EVENT_RECEIVED`, `EVENT_IGNORED`, `CASE_OPENED`, `CASE_STATUS_CHANGED`, `CASE_RESOLVED`, `MANUAL_HANDOFF`, `WORKFLOW_FAILED`, `GAP_ASSESSED`, `SOLVER_EXECUTED`, `OFFER_SENT`, `OFFER_ACCEPTED`, `OFFER_REJECTED`, `OFFER_TIMEOUT`, `SAFETY_PASSED`, `SAFETY_FAILED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `APPROVAL_REJECTED`, `ASSIGNMENT_CREATED`, `HANDOVER_GENERATED`, `UNAVAILABILITY_CREATED`, `UNAVAILABILITY_UPDATED`, `ASSIGNMENT_CANCELLED`, `PATIENT_COUNT_UPDATED`, `REQUIREMENT_UPDATED` |


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
| `UNAVAILABLE` | A recorded unavailability period overlaps the proposed shift. | Always checked |
| `SHIFT_CONFLICT` | Candidate has a committed assignment on another shift whose time overlaps the proposed shift. | `prevent_shift_conflict` |
| `ROLE_MISMATCH` | Candidate does not have the role of the target they are selected to fill. | `require_matching_role` |
| `SKILL_MISMATCH` | Candidate does not have the skill of the target they are selected to fill. | `require_matching_skill` |
| `INSUFFICIENT_REST` | Adding the shift would leave less rest than the minimum before or after it. | `minimum_rest_hours` |
| `DAILY_HOURS_EXCEEDED` | Total hours of the day, including the proposed shift, would exceed the limit. | `maximum_daily_hours` |
| `WEEKLY_HOURS_EXCEEDED` | Total hours of the week, including the proposed shift, would exceed the limit. | `maximum_weekly_hours` |
| `CONSECUTIVE_SHIFTS_EXCEEDED` | Consecutive shifts, counted after inserting the proposed shift, would exceed the limit. A rest of 24 hours or less keeps two shifts in the same run. | `maximum_consecutive_shifts` |
| `SOURCE_WARD_MINIMUM_VIOLATION` | Moving the candidate out of an existing assignment would leave the source shift below its target headcount. | `preserve_source_ward_minimum` |
| `OFFER_LIMIT_REACHED` | Candidate already holds the maximum number of open offers: `SENT`, or `ACCEPTED` on a case that is still running. | `OUTREACH_POLICY.maximum_concurrent_offers_per_staff` |

The first eleven codes are Hard Rules. The Solver, wave selection and Safety must return the same result from the same data. `OFFER_LIMIT_REACHED` is not a Hard Rule: it is checked by the Solver and by wave selection, never by Safety, because the candidate being validated always holds the accepted offer of their own case.

The old codes `OPEN_OFFER`, `HAS_OPEN_OFFER` and `SOURCE_WARD_MINIMUM` are not used.

### Policy Flags

A disabled policy flag must not produce a skip reason. Numeric limits have no flag and are always checked. Being equal to a limit passes; only exceeding it fails.

For example, when `require_matching_skill = false`, a skill mismatch alone does not reject the candidate.

### Role and Skill

A candidate does not have to close every gap of the case alone. Role and skill are evaluated against the targets the candidate is selected to fill, stored in `CANDIDATE_ITEM_TARGET`. A candidate selected only for headcount passes without the missing skill.

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

A candidate may fail more than one rule. The contract fixes the shape but not which code is kept in that case. The PR that implements wave selection must pick a stable rule and write it here; the order of the Skip Reasons table above, which Safety also uses for `failure_reason`, is the natural choice. Do not rely on database query order.

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

If no candidate can be selected and the case stops, the `MANUAL_HANDOFF` payload carries `reason` (`NO_CANDIDATE_LEFT` or `NO_FEASIBLE_PLAN`), `stopped_at`, `cancelled_outreach_ids` and the collected `skipped` list.

Previously contacted candidates may also explain why no candidate remains, but their outcomes come from outreach history and must not be labelled as new Hard Rule failures.

## Storage and Display

- Use fixed codes rather than free-text skip reasons.
- Record `skipped` in the relevant `OFFER_SENT` or `MANUAL_HANDOFF` audit payload. No column is added.
- A skipped candidate receives no new `CANDIDATE_OUTREACH` row.
- A candidate with no outreach history can still appear as "Not contacted."
- The case page reads the reasons from the audit payload and translates the codes into readable explanations.
