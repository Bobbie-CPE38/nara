# Workflow Contract

> ข้อตกลงร่วมของทีม ใช้คู่กับ `backend/app/domain/enums.py` และ `docs/database-schema.md`
> ถ้าจะเปลี่ยนอะไรในไฟล์นี้ แจ้งทั้งทีมก่อน และแก้ใน PR เดียวกับโค้ดที่เกี่ยวข้อง
>
> ขอบเขต: Walking Skeleton, รอบ 1 (Merge Gap, เคสรับหลายคน, Wave) และ Contract ของรอบ 2 (เส้นออกจาก `MANUAL_HANDOFF`, Timeout ของการอนุมัติ, OR-Tools) ซึ่งโค้ดยังเข้าไม่ครบ ดู "สถานะของรอบ 2"
> อัปเดตล่าสุด: 2026-10-13

## สถานะของรอบ 1

รอบ 1 เสร็จแล้ว PR ทุกตัวของร่างรอบ 1 ข้อ 10 เข้า `staging` ครบ โค้ดตรงกับข้อ 3 ถึง 7 และข้อ 9 ของไฟล์นี้ กติกาเหล่านี้ย้ายมาจาก `docs/round1/round1-contract-draft.md` (ในไฟล์นี้เรียกว่า "ร่างรอบ 1") ใน PR 0

| PR ของรอบ 1 | เรื่อง | ข้อของไฟล์นี้ | PR บน GitHub |
|---|---|---|---|
| 0 | ย้าย Contract เข้าไฟล์นี้, Transition T1 ถึง T7 | 3 ถึง 7, 9 | #33 |
| 1a | ตัวตรวจ Hard Rules | ร่างรอบ 1 ข้อ 7 | #36 |
| 1b | เป้าหมายจำนวนคนและ Gap (`effective_minimum`) | 3.6 | #34 |
| 1c | เพดาน Offer ต่อคน | 6.7 | #35 |
| M | Window, Threshold, Event สี่ชนิด, Job | 3 | #38 |
| S | ฟังก์ชันคำนวณสถานะเคส | 5.3 | #37 |
| 2a | Solver ใช้ Gap, Hard Rules และน้ำหนัก | 8 แถว Solver | #39 |
| 2b | Wave และการตอบ Offer รายคน | 6.6, 6.8, 6.10 | #40 |
| 3 | Safety รายคน | 8 แถว Safety | #41 |
| 4 | อนุมัติและจัดเวรรายคน | 6.10, 9.2 | #42 |
| (รวม 2b, 3, 4) | Branch รวมเข้า `staging` ครั้งเดียว | | #43 |
| O | Timeout ของ Offer และรอบเก็บตกของ Job | 6.9, 3.8 | #44 |
| 5 | หน้า `approvals` | 9.3 | #45 |
| 6 | หน้า `cases/[id]` | 9.3 | #46 |
| (เพิ่ม) | หน้า `demo/control` แสดง Offer ที่หมดเวลาหลังเลื่อน Clock | 9.3 | #47 |

สิ่งที่รอบ 1 ตั้งใจไม่ทำอยู่ในร่างรอบ 1 ข้อ 1.2 และข้อ 12 ของไฟล์นี้

เรื่องที่ยังอยู่ในร่างรอบ 1 ไม่ได้ย้ายเข้าไฟล์นี้ เลข Q ที่อ้างในไฟล์นี้คือคำถามในร่างรอบ 1 ข้อ 12

| ร่างรอบ 1 | เรื่อง |
|---|---|
| ข้อ 6.2 | หน้าเว็บที่ต้องแก้ตาม และเจ้าของแต่ละหน้า |
| ข้อ 7 | Hard Rules: รหัส, Interface, สิ่งที่ Safety บันทึก ตัวตรวจอยู่ใน `domain/constraints/` ตั้งแต่ PR 1a Solver เรียกผ่าน `hard_rule_service` แล้วตั้งแต่ PR 2a การเลือกคนของ Wave เปลี่ยนใน PR 2b และ Safety เรียกตัวเดียวกันตั้งแต่ PR 3 ซึ่งลบ `assert_available()` กับ `unavailable_staff()` ออกจาก `availability_service` แล้ว Execute ไม่ตรวจซ้ำ (Q38) |
| ข้อ 8.3, 8.4 | Seam จาก Gap ไป Solver, สูตรจัดอันดับ, Target ของ Wave, `CANDIDATE_ITEM_TARGET` |
| ข้อ 9 | Scenario และกติกาของ Test รวม Test สอง Connection และ Test หลังระบบล่ม ที่ PR ของแต่ละเส้นทางต้องมี |
| ข้อ 10, 11 | ลำดับ PR และไฟล์กลางที่ต้องแก้ |
| ข้อ 12 | คำถาม Q1 ถึง Q56 พร้อมคำตอบ |

ส่วนที่ย้ายเข้าไฟล์นี้แล้วคือร่างรอบ 1 ข้อ 2, 3, 4, 5, 6.1 และ 8.2 (ข้อ 8.2 อยู่ที่ข้อ 3.6 ของไฟล์นี้) ถ้าเรื่องพวกนั้นในไฟล์นี้ไม่ตรงกับร่างรอบ 1 ให้ยึดไฟล์นี้

---

## สถานะของรอบ 2

Contract ของรอบ 2 ตกลงแล้ว (PR #50) ไฟล์นี้รับเฉพาะกติกาที่ข้ามคน ส่วน Spec เต็มของรอบ รวมการออกแบบข้างในของ OR-Tools อยู่ที่ `docs/round2/round2-contract-draft.md` (ในไฟล์นี้เรียกว่า "ร่างรอบ 2") รอบ 2 ไม่มีไฟล์ Spec แยกรายคน (R2-Q38) เลข R2-Q ที่อ้างในไฟล์นี้คือคำถามในร่างรอบ 2 ข้อ 7

**โค้ดของรอบ 2 ยังเข้าไม่ครบ** PR 0 ของรอบ 2 เพิ่มแค่เส้น T8 กับ T9 ใน `transitions.py` และค่าใหม่ใน `enums.py` ไม่เปลี่ยนพฤติกรรมของระบบ ข้อความในไฟล์นี้ที่ขึ้นต้นด้วย **[รอบ 2]** คือกติกาที่ตกลงแล้วแต่โค้ดยังไม่ทำตาม จนกว่า PR ที่ระบุจะ merge ข้อความที่ไม่มีป้ายนี้ยังตรงกับโค้ดปัจจุบัน

| PR ของรอบ 2 | ใคร | เรื่อง | ข้อของไฟล์นี้ | PR บน GitHub |
|---|---|---|---|---|
| เอกสาร | คน 1 | ร่างรอบ 2 และไฟล์คำถามสามชุด | | #50 |
| A | คน 2 | Test ที่ตรึงผลของ Solver รอบ 1 | 6.14 | #51 |
| 0 | คน 1 | ย้าย Contract เข้าไฟล์นี้, Transition T8 และ T9, ค่าใหม่ใน Enum | 4, 5.1, 6.12 ถึง 6.14, 7.1, 9.4 | #52 |
| W | คน 1 | การอนุมัติจำกัดหอ | 6.12 | |
| T | คน 3 | Approval Timeout (Migration ตัวที่ 1) | 6.13 | |
| T2 | คน 1 | หน้า `approvals` แสดงเส้นตาย | 9.4 | |
| B | คน 2 | OR-Tools (Migration ตัวที่ 2) | 6.14 | |
| H | คน 1 | เส้นออกจาก `MANUAL_HANDOFF` (Migration ตัวที่ 3) | 6.12 | |

ลำดับ merge: 0 ก่อนทุกตัว, W ก่อน H, T ก่อน B ก่อน H ตามสาย Migration (`a4b8c2d6e9f1` → T → B → H), T2 หลัง T รายละเอียดอยู่ร่างรอบ 2 ข้อ 6 รอบ 2 ไม่ใช้ Branch รวม ทุก PR เข้า `staging` ตรง (R2-Q10)

เรื่องที่ยังอยู่ในร่างรอบ 2 ไม่ได้ย้ายเข้าไฟล์นี้

| ร่างรอบ 2 | เรื่อง |
|---|---|
| ข้อ 3.2 | Test ที่เป็นเกณฑ์เสร็จของ PR H และ PR T ทีละข้อ และเหตุผลของแต่ละกติกา |
| ข้อ 4.5 | เกณฑ์เสร็จของ PR B |
| ข้อ 4.6 | ผลวัดเวลาของโมเดลต้นแบบ |
| ข้อ 4.7 | การออกแบบข้างในของโมเดล OR-Tools: การคูณสเกล และการเลือกกลุ่มสามขั้น |
| ข้อ 5 | จุดที่เสี่ยงพังเงียบ |
| ข้อ 6 | ลำดับ PR |
| ข้อ 7 | คำถาม R2-Q1 ถึง R2-Q56 พร้อมคำตอบ |

ถ้ากติกาที่ย้ายเข้าไฟล์นี้แล้วไม่ตรงกับร่างรอบ 2 ให้ยึดไฟล์นี้

**ข้อกำหนดที่ยังไม่มี Test** PR 0 เป็น PR ของ Contract Test ที่มากับ PR นี้ครอบคลุมแค่เส้น T8 กับ T9 ใน `transitions.py` กติกาที่มีป้าย **[รอบ 2]** ทุกข้อจึงยังไม่มีอะไรพิสูจน์ PR ที่ทำกติกานั้นต้องมี Test ของกติกานั้นใน PR เดียวกัน รายการเต็มอยู่ร่างรอบ 2 ข้อ 3.2 และ 4.5 ข้อที่พังเงียบได้ถ้าไม่มี Test คือ

| ข้อกำหนด | PR ที่ต้องมี Test | ข้อ |
|---|---|---|
| ตัวอ่านสี่จุดจับคู่ด้วย `outreach_id` แทน `candidate_item_id` และแถวของรอบแรกไม่มีผลกับรอบที่สอง | T | 6.13 |
| Migration หยุดเมื่อเคสกับ Item หนึ่งคู่มี Offer มากกว่าหนึ่งแถว และ Job เขียนผลหมดเวลาเฉพาะคำขอที่ยังกดตัดสินได้ | T | 6.13 |
| `cancellation_reason` เป็น `APPROVAL_TIMEOUT` เมื่อคำขอหมดเวลา | T | 6.13, 7.1 |
| ช่องของ `OFFER_CANCELLED_BY_ASSIGNMENT` ชื่อ `cancelled_outreach_id` และ `cancellation_reason` ยังเป็น `CONFLICTING_ASSIGNMENT` ทั้งสองเส้นทาง | H | 6.12, 7.1 |
| ตัวยกเลิก Offer ไม่แตะ Offer `SENT` ที่เลยเส้นตาย ทั้งเส้นทางจัดคนเองและเส้นทางอนุมัติ | H | 6.12 |
| การจัดคนเองถูกปฏิเสธเมื่อไม่ผ่าน Hard Rules ข้อใดข้อหนึ่ง และเวรที่จัดเองถูกนับว่าปิด Gap | H | 6.12 |
| ผู้กดที่ไม่ใช่ Head Nurse ของหอเดียวกับเวรได้ `403` | W สำหรับการอนุมัติ (มี Test แล้ว) และ H สำหรับการจัดคนเองกับการปิดเคส | 6.12 |
| สถานะของ Solver แต่ละค่าพาเคสไปสถานะที่ถูก และผล `OPTIMAL` เท่ากับ Solver รอบ 1 | B | 6.14 |

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

Event ของเวรเดียวกันถูกเก็บเป็น `RECEIVED` รอไว้ใน Window ก่อน ยังไม่เปิดเคส พอ Window ปิดจึงคิด Gap ครั้งเดียวจาก Event ทั้งชุด แล้วค่อยเปิดเคส หนึ่ง Window เปิดได้หนึ่งเคส Event ไม่ถูกเอาไปรวมกับเคสที่มีอยู่แล้ว (Q43) และเวรหนึ่งมีเคสที่เดินอยู่ได้เคสเดียว

### 3.1 สองช่วงของการรับ Event

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

* `required_replacement_time` ของเคส = `SHIFT.start_at`
* `STAFF.status` ของคนที่ลาไม่เปลี่ยน (ยังเป็น `ACTIVE`)
* `PLANNED_LEAVE` (ลาที่ไม่ชนเวรที่มี Roster) ไม่สร้าง Event และ `NO_SHOW` (ระบบสร้างเองจาก `ATTENDANCE`) อยู่นอกรอบ 1 ดูข้อ 12

### 3.2 Window

ไม่มีตารางใหม่ และไม่มีคอลัมน์ใน `STAFFING_CASES` (ตอน Window เปิดยังไม่มีเคส) อ่านจาก `STAFFING_EVENTS` กับความยาว Window ที่เก็บใน `SHIFT`

| ต้องรู้อะไร | อ่านจาก |
|---|---|
| เวรนี้มี Window เปิดอยู่ไหม | มี Event ที่ `shift_id` นี้ และ `status = RECEIVED` อย่างน้อย 1 แถว |
| Window เปิดตอนไหน | `min(occurred_at)` ของ Event กลุ่มนั้น (`occurred_at` ตั้งจาก `clock.now()` ตอนรับ Event) |
| Window ปิดตอนไหน | เวลาที่ช้ากว่าระหว่าง `min(occurred_at)` + `SHIFT.merge_window_seconds` กับเวลาที่เคสก่อนหน้าของเวรนั้นจบ ถ้าเวรไม่มีเคสเดินอยู่ ใช้ค่าแรกอย่างเดียว (Q43) |
| Event ไหนอยู่ใน Window นี้ | Event ที่ `RECEIVED` ทุกแถวของเวรนั้น |
| Event ไหนเคยอยู่ Window เดียวกัน (ดูย้อนหลัง) | `shift_id` เดียวกัน และ `processed_at` เท่ากัน |
| Event ไหนเป็นของเคสไหน | `STAFFING_EVENTS.case_id` |

คอลัมน์ที่ใช้: `SHIFT.merge_window_seconds`, `STAFFING_EVENTS.processed_at`, `STAFFING_EVENTS.case_id` และ `AUDIT_LOG.event_id` ส่วน `STAFFING_CASES.event_id` ถูกลบ รายละเอียดของคอลัมน์อยู่ใน `docs/database-schema.md`

`EventStatus` ใช้ 3 ค่าเดิม ไม่เพิ่ม `PROCESSING` เพราะ PART B อยู่ใน Transaction เดียว ไม่มีใครเห็นสถานะระหว่างทาง

**ทำไม Window ใหม่ไม่ปนกับของเก่า**

ต้องจริงทั้งสามข้อ และต้องมี Test ยืนยัน

1. PART B เปลี่ยนสถานะ Event ทั้งชุดใน Transaction เดียว ถ้าพังกลางทาง Rollback ทั้งชุด ทุกตัวยัง `RECEIVED` Window เดิมยังไม่ปิด
2. PART A และ PART B ล็อก shift ตัวเดียวกัน Event ที่มาช้าจึงเข้าได้แค่สองแบบ: Commit ก่อน PART B ล็อก (อยู่ Window เก่า) หรือหลัง PART B เสร็จ (เป็นตัวแรกของ Window ใหม่)
3. สถานะไม่ย้อนกลับ ไม่มีโค้ดไหนเปลี่ยน `PROCESSED` / `IGNORED` กลับเป็น `RECEIVED`

Event หนึ่งตัวจึงอยู่ได้ Window เดียว ส่วน**ตัวเลข Gap** ของ Window ใหม่คิดจากสภาพเวรทั้งหมดตอนนั้น ไม่ใช่เฉพาะ Event ใหม่ (ตั้งใจ ตรงกับ Q26)

**กติกาของ Window**

| หัวข้อ | กติกา |
|---|---|
| ตำแหน่งของ Window | ก่อนเคส เคสเกิดหลัง Window ปิดและเวรขาดคนจริง |
| สถานะเคส | ไม่เพิ่ม `WAITING_MERGE_WINDOW` Merge Gap ไม่เพิ่ม Transition เคสใหม่เดิน `OPEN → ASSESSING` เหมือนเดิม จุดรอของเคสยังมีสองจุด |
| เก็บ Window | อ่านจาก `STAFFING_EVENTS` ตามตารางข้างบน เพิ่ม `processed_at` และ `case_id` |
| Event กับเคส | `STAFFING_EVENTS.case_id` ชี้ไปที่เคส ลบ `STAFFING_CASES.event_id` |
| `EventStatus` | 3 ค่าเดิม ไม่เพิ่ม `PROCESSING` |
| ความยาว Window | `SHIFT.merge_window_seconds` ตั้งได้ต่อเวร ค่าที่ใช้กับการ Merge เริ่มที่ 600 (10 นาที) แล้วปรับ |
| Window = 0 | เวรใน Golden Case ตั้ง `merge_window_seconds = 0` Demo ปกติและ Test เดิมจึงได้ผลเหมือน Skeleton: PART A เรียก PART B ต่อใน Transaction เดียวกัน `POST /events` ยังเดินรวดเดียวถึง `WAITING_RESPONSE` และตอบ `case_id` เหมือนเดิม (ยกเว้นตอนเวรมีเคสเดินอยู่ Event จะรอเป็น `RECEIVED` ดูข้อจำกัดที่รู้) ตั้งเป็น 600 เฉพาะเวรใน Scenario ของการ Merge |
| ปิด Window ใน Demo | เลื่อน Clock ต้องมี Route เลื่อนนาฬิกาและปุ่มในหน้า `demo/control` Route นี้เรียกฟังก์ชันปิด Window ตัวเดียวกับ Job เพราะเลื่อนนาฬิกาอย่างเดียว Job ไม่รันเอง |
| หาเวรที่ถึงเวลาปิด | เวรที่มี Event `RECEIVED`, `min(occurred_at) + merge_window_seconds <= clock.now()` และไม่มีเคสที่ยังเดินอยู่ของเวรนั้น |
| หนึ่ง Window หนึ่งเคส (Q43) | Window หนึ่งสร้างเคสได้มากสุดหนึ่งเคส เคสถูกสร้างหลังวนครบทุก Event เมื่อมี Event ที่ผ่าน Threshold และ Gap สุดท้ายไม่เป็น 0 Event ทุกตัวใน Window Link เข้าเคสนั้น ไม่มีการเอา Event ไปรวมกับเคสของ Window ก่อน |
| Threshold (Q32) | ตรวจตอน Window ปิด **ทีละ Event ตามลำดับ** กับ Event ทุกชนิด ไม่มีชนิดไหนผ่านเสมอ ดู 3 อย่างจากข้อมูลของเวรหลัง Event ตัวนั้น: Ratio, Role Gap, Skill Gap ผ่านเมื่อมีอย่างน้อยหนึ่งอย่างเกิน ข้อมูลสะสม Event ตัวหลังจึงเห็นผลของตัวก่อน รายละเอียดอยู่ข้อ 3.3 |
| Event ที่ผ่าน Threshold | ระบบจดไว้ว่าผ่าน ยังไม่สร้างเคสและยังไม่เขียน `required_staff` ทั้งสองอย่างทำหลังวนครบทุก Event จากข้อมูลสุดท้ายของเวร |
| มี Event ผ่าน แต่ Gap สุดท้ายเป็น 0 ทุกตัว | ไม่สร้างเคส Event ทุกตัวใน Window เป็น `IGNORED` เหตุผลอยู่ใน payload ของ `EVENT_IGNORED` เกิดเมื่อ Event ตัวหลังทำให้เวรกลับมาพอ เช่น จำนวนผู้ป่วยลดลง `required_staff` ยังถูกเขียนตามค่าสุดท้าย |
| Update table ที่เกี่ยวข้อง (Q41) | ทำตอน Window ปิด ทีละ Event ไม่ทำตอนรับ Event ตอนรับ Event เขียนแค่แถว Event กับ `EVENT_RECEIVED` |
| Event ที่ไม่ผ่านใน Window ที่มีตัวผ่าน (Q42) | เป็น `PROCESSED` และ Link เข้าเคสเดียวกัน Window ที่มีเคสจึงจบแบบนี้: ทุกตัว `PROCESSED` + Link ยกเว้นตัวที่ Update table ไม่ได้ ซึ่งเป็น `IGNORED` เฉพาะตัวนั้น (Q44) ส่วน Window ที่ไม่มีเคส ทุกตัวเป็น `IGNORED` |
| ผู้แจ้งหาเคสของ Event (Q36) | อ่านจาก `STAFFING_EVENTS.case_id` ผ่าน Route อ่าน Event (ข้อ 9.2) |
| ไม่มี Event ไหนผ่าน | Event ทุกตัวใน Window เป็น `IGNORED` ไม่มีเคส ไม่เขียน `required_staff` ใหม่ ส่วนสิ่งที่ Event แก้ไปแล้วในขั้น Update table ยังอยู่ เช่น การลา, Roster ที่ยกเลิก, `patient_count`, จำนวนของ Role / Skill จาก `REQUIREMENT_CHANGED` |
| Gap | คิดครั้งเดียวหลังวนครบทุก Event ถ้าไม่เป็น 0 จึงสร้างเคสและบันทึก Gap หนึ่งแถว ไม่สร้างต่อ Event |
| Event ที่รับในรอบ 1 (Q32) | ครบทั้งสี่ชนิด: `STAFF_UNAVAILABLE`, `ASSIGNMENT_CANCELLED`, `PATIENT_SURGE`, `REQUIREMENT_CHANGED` |
| Audit ของ Event (Q33) | เพิ่ม `AUDIT_LOG.event_id` แถว Audit ที่เป็นเรื่องของ Event ใส่ `event_id` อย่างเดียว ไม่ใส่ `case_id` ทุกกรณี รวมถึง Window = 0 ใส่ตั้งแต่ตอนเขียน ไม่มีการแก้แถว Audit ทีหลัง |
| Migration (Q34) | ทำเป็น Migration ใหม่ ไม่แก้ไฟล์ Migration เดิม ไม่เติมค่าให้ข้อมูลที่มีอยู่ ทุกคนรัน `make reset` ก่อน |
| Job ปิด Window (Q35) | Service แยกใน `docker-compose.yml` เป็นตัวจับรอบ ทุก 30 วินาทีเรียก Route ภายในของ Backend ให้ Backend ปิด Window ที่ถึงเวลาด้วยนาฬิกาของ Backend เอง |
| Event ของเคสใน Case API (Q36) | ตอบเป็น List `event_ids` แทน `event_id` ตัวเดียว |
| Event ของเวรที่มีเคสเดินอยู่ (Q43) | ไม่เข้าเคสนั้น เก็บเป็น `RECEIVED` รอจนเคสนั้นจบ แล้ว Window ของมันจึงปิดและเปิดเคสใหม่ของตัวเอง แทนคำตอบเดิมของ Q26 |
| เคสก่อนหน้า "จบ" (Q49) | นับ 4 สถานะ: `RESOLVED`, `UNRESOLVED`, `FAILED`, `MANUAL_HANDOFF` |

### 3.3 Threshold

| ตัวที่ดู | ผ่านเมื่อ | ข้อมูลที่ใช้ |
|---|---|---|
| Ratio | ผู้ป่วยต่อพยาบาลของเวรเกินค่าที่กำหนด: `patient_count > maximum_patients_per_nurse * จำนวนคนในเวร` | `SHIFT.patient_count`, Roster ที่ `ASSIGNED`, `HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse` |
| Role Gap | มี Role อย่างน้อยหนึ่งตัวที่คนในเวรน้อยกว่าจำนวนที่ต้องการ | Requirement ของ Role, Roster |
| Skill Gap | มี Skill อย่างน้อยหนึ่งตัวที่คนในเวรน้อยกว่าจำนวนที่ต้องการ | Requirement ของ Skill, Roster |

* ผ่านเมื่อข้อใดข้อหนึ่งเป็นจริง ใช้กติกาเดียวกับ Event ทุกชนิด
* เขียน Ratio เป็นการคูณ ไม่ใช่การหาร เพราะเวรที่ไม่เหลือคนจะหารด้วยศูนย์
* ข้อ Ratio ให้ผลเท่ากับ "จำนวนคนในเวร < `ceil(patient_count / maximum_patients_per_nurse)`" คือเทียบกับ `required_staff` ค่าใหม่ ก่อนเขียนลง Requirement (ตรวจด้วยโค้ดแล้ว ตรงกันทุกค่าที่ลอง)
* ไม่ต้องมีคอลัมน์เก็บค่า Threshold เพิ่ม ใช้ค่าที่มีอยู่แล้วทั้งหมด
* **Threshold ไม่ดู `minimum_staff`:** เวรที่คนต่ำกว่า `minimum_staff` แต่ Ratio ยังไม่เกินและไม่ขาด Role / Skill เป็น `IGNORED` ตัวอย่าง: ผู้ป่วย 2 คน, `minimum_staff = 2`, เหลือคน 1 คน Ratio = 2 ต่อ 1 ไม่เกิน จึงไม่เปิดเคส `minimum_staff` มีผลหลังผ่าน Threshold แล้วเท่านั้น คือทำให้ `headcount_gap` ที่คิดจาก `effective_minimum` (ข้อ 3.6) มากขึ้นได้

### 3.4 Event สี่ชนิด

รับผ่าน `POST /events` ตัวเดียว เพิ่ม Field ใน Body ตามชนิด ตารางแรกคือสิ่งที่ PART B แก้ในขั้น "Update table ที่เกี่ยวข้อง"

| ชนิด | กลุ่ม | Table ที่ PART B แก้ |
|---|---|---|
| `STAFF_UNAVAILABLE` | บุคลากร (มี `staff_id`) | สร้างแถว `STAFF_UNAVAILABILITY` (`reason = UNPLANNED_LEAVE`, `start_at = SHIFT.start_at`, `end_at` = เวลากลับที่แจ้ง หรือ `SHIFT.end_at` ถ้าไม่ได้แจ้ง) และยกเลิก Roster ของคนนั้นในเวร |
| `ASSIGNMENT_CANCELLED` | บุคลากร (มี `staff_id`) | Roster ของคนนั้นในเวรเป็น `CANCELLED` ไม่มีแถวการลา |
| `PATIENT_SURGE` | ภาระงาน (`staff_id` ว่าง) | `SHIFT.patient_count` = ค่าใหม่ |
| `REQUIREMENT_CHANGED` | ภาระงาน (`staff_id` ว่าง) | UPDATE แถวใน `STAFFING_REQUIREMENT_ROLE` / `STAFFING_REQUIREMENT_SKILL` ของเวร ในแถวเดิม |

Body ที่เพิ่ม การตรวจตอนรับ และ Audit ของแต่ละชนิด

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
* แถว Audit ทั้งสามใส่ `event_id` แบบเดียวกับ `UNAVAILABILITY_CREATED` (Q33)
* `reason` ของ `ASSIGNMENT_CANCELLED` เป็นข้อความที่ Head Nurse พิมพ์ ยาวได้ไม่เกิน 500 ตัวอักษร (`MAX_EVENT_REASON_LENGTH`) เกินตอบ `422` ข้อความนี้ถูกเก็บใน payload ของ Event และของ Audit ข้อห้ามในข้อ 6.3 คือเหตุผลการลาของพนักงาน ซึ่งเป็นข้อมูลส่วนตัว ส่วนข้อความนี้เป็นเหตุผลของการตัดสินใจด้านการจัดเวร แบบเดียวกับ `reason` ของการอนุมัติ (ข้อ 7.2) จึงเก็บได้ ผู้กรอกต้องไม่ใส่เหตุผลการลาหรือข้อมูลผู้ป่วยลงไป
* Body รับเฉพาะ Field ของชนิดนั้น ส่ง Field ของชนิดอื่นมาด้วยตอบ `422` เช่น `patient_count` กับ `STAFF_UNAVAILABLE` และ Role / Skill ตัวเดียวกันซ้ำสองรายการใน `REQUIREMENT_CHANGED` ก็ตอบ `422`
* `STAFFING_EVENTS.staff_id` คือคนที่ Event พูดถึง: คนที่ลา (`STAFF_UNAVAILABLE`) หรือคนที่ถูกยกเลิก (`ASSIGNMENT_CANCELLED`) อีกสองชนิดเป็น NULL ตาม CHECK ของตาราง ผู้แจ้งของสามชนิดที่ Head Nurse แจ้งจึงเก็บใน payload ที่ Key `reported_by` (Staff ID) PART B ใช้ค่านี้เป็น Actor ของแถว Audit เพราะตอน Window ปิดไม่มี Request ของผู้แจ้งแล้ว
* รูปของ payload ที่ PART A เก็บ

  | ชนิด | payload |
  |---|---|
  | `STAFF_UNAVAILABLE` | `{}` หรือ `{end_at}` เมื่อแจ้งเวลากลับ (ข้อความ ISO ที่มี `+07:00`) |
  | `ASSIGNMENT_CANCELLED` | `{reason, reported_by}` `reason` ตัดช่องว่างหัวท้ายแล้ว |
  | `PATIENT_SURGE` | `{patient_count, reported_by}` |
  | `REQUIREMENT_CHANGED` | `{roles: [{role_id, required_count}], skills: [{skill_id, required_count}], reported_by}` เรียงตาม ID รายการที่ไม่ได้ส่งเป็น List ว่าง |

### 3.5 Request และการตรวจตอนรับ Event

* Request: `POST /events` พร้อม `X-Demo-User` และ Body `{event_type, shift_id, ...}` ตาม Field ของแต่ละชนิดในข้อ 3.4 ผู้แจ้งคือ `user.staff.id`
* `end_at` ของ `STAFF_UNAVAILABLE` คือเวลากลับที่แจ้ง ต้องมี Timezone และอยู่หลัง `SHIFT.start_at` ไม่ส่งมา = ถึง `SHIFT.end_at`
* ตรวจทุกข้อ**ก่อนเขียนแถวแรก** คำขอที่ถูกปฏิเสธจึงไม่ทิ้งอะไรไว้ใน DB ตามลำดับนี้

  | ตรวจ | ไม่ผ่านตอบ |
  |---|---|
  | `event_type` เป็นหนึ่งในสี่ชนิด | `422` |
  | `shift_id` อยู่ในช่วง `bigint` (1 ถึง 9223372036854775807) | `422` |
  | Field ของชนิดนั้นครบและถูกรูปแบบ ไม่มี Field ของชนิดอื่น (ตรวจจาก Body อย่างเดียว) | `422` |
  | มี Shift ID นั้น | `404` |
  | เวรมีแถว `STAFFING_REQUIREMENTS` (ทุกชนิด) | `409` |
  | ผู้แจ้งเป็น Head Nurse (เฉพาะสามชนิดที่ Head Nurse แจ้ง) | `403` |
  | การตรวจที่ต้องอ่าน DB ของชนิดนั้น | ตามคอลัมน์ "ตรวจตอนรับ" ของตารางในข้อ 3.4: `422` (`end_at` ไม่หลังเวลาเริ่มเวร, id ไม่อยู่ใน Requirement ของเวร) และ `409` (ไม่มี Roster `ASSIGNED`) |

  `404` มาก่อน `403`: คนที่ไม่ใช่ Head Nurse ส่งเวรที่ไม่มีอยู่ได้ `404`

  เหตุผลของ `409`: PART B ต้องใช้ Requirement ตรวจ Threshold และคิด Gap ถ้าเวรไม่มี Requirement การปิด Window จะพังทุกรอบ Event ค้าง `RECEIVED` และ Event ตัวถัดไปของเวรนั้นต่อคิวตามไม่มีวันถูกปิด จึงปฏิเสธตั้งแต่ตอนรับ Seed ให้ทุกเวรมี Requirement กรณีนี้จึงเกิดกับข้อมูลที่ตั้งค่าไม่ครบเท่านั้น

* การตรวจว่าผู้แจ้งมี Roster `ASSIGNED` ในเวรนั้นทำตอนรับ Event แต่ไม่กันการแจ้งซ้ำใน Window เดียวกัน เพราะ Roster ยังไม่ถูกยกเลิกจนกว่า Window ปิด (Q41) Event ที่ซ้ำถูกจับใน PART B: ตัวที่สองไม่มี Roster ให้ยกเลิก จึงเป็น `IGNORED` เฉพาะตัวนั้น (Q44)
* PART A และ PART B ล็อกแถว `SHIFT` ตัวเดียวกันด้วย `SELECT ... FOR NO KEY UPDATE` และถือ Lock จน Commit PART B ล็อก `SHIFT` ก่อนแล้วจึงแก้ Roster (ข้อ 6.11)
* รายละเอียดของ Event ต้องอยู่ใน `STAFFING_EVENTS.payload` ตั้งแต่ตอนรับ เช่น `end_at` ของคนลา เพราะ PART B เป็นคนเขียน `STAFF_UNAVAILABILITY`
* ระหว่างรอ Window คนที่แจ้งลายังเป็น `ASSIGNED` ใน Roster หน้า `roster` และ Solver ของเคสอื่นยังเห็นเขาอยู่ในเวร
* PART A เป็นหนึ่ง Transaction ต่อ Event และ Commit เอง ยกเว้นเวรที่ `merge_window_seconds = 0` ซึ่ง PART A เรียก PART B ต่อใน Transaction เดียวกัน PART B เป็นหนึ่ง Transaction ต่อเวร ถ้าพังกลางทาง Event ทุกตัวของเวรนั้นยัง `RECEIVED`
* Event ที่เปิดเคส Orchestrator Commit ให้ (ข้อ 6.2)

### 3.6 เป้าหมายจำนวนคนและ Gap

ไม่มีการบวกแถว คิดครั้งเดียวตอน Window ปิดจากข้อมูลปัจจุบันของเวร

| ส่วน | รวมยังไง |
|---|---|
| ความต้องการ (`required_staff`) | UPDATE ในแถว Requirement เดิม ครั้งเดียวหลังวนครบทุก Event เมื่อมี Event ที่ผ่าน Threshold อย่างน้อยหนึ่งตัว ใช้ `patient_count` ค่าสุดท้ายของเวร |
| จำนวนคนในเวร | นับใหม่จาก Roster ที่ `ASSIGNED` หลังวนครบทุก Event การลาของทุก Event ใน Window ถูกหักแล้ว |
| `headcount_gap` | `max(effective_minimum - current_valid_staff, 0)` คิดครั้งเดียวจากสองบรรทัดบน |
| Gap ของ Role / Skill | คิดใหม่ทุกตัว: จำนวนที่ต้องการ ลบ คนในเวรที่มี Role / Skill นั้น |

| ค่า | กติกา |
|---|---|
| `required_staff` | จำนวนคนที่ต้องการตามภาระงาน = `ceil(patient_count / patients_per_nurse)` เก็บใน `STAFFING_REQUIREMENTS` PART B เขียนใหม่ครั้งเดียวหลังวนครบทุก Event เมื่อมี Event ที่ผ่าน Threshold จาก `patient_count` ค่าสุดท้าย โดย UPDATE ในแถว Requirement เดิม ไม่สร้างแถวใหม่ |
| `minimum_staff` | ค่าคงที่ของแต่ละเวร คือจำนวนคนขั้นต่ำที่เวรต้องมีเสมอ |
| `effective_minimum` | เป้าหมายจำนวนคน = `max(required_staff, minimum_staff)` เมื่อ `preserve_minimum_staffing` เปิด และ `required_staff` เมื่อปิด |
| `headcount_gap` | `max(effective_minimum - current_valid_staff, 0)` |
| `calculate_gap()` | รับ `required_staff` และ `minimum_staff` แทน `patient_count` และ `patients_per_nurse` |
| สูตร `ceil` | `gap_calculator.required_staff_for()` ใช้ตอนเขียน `required_staff` (PART B) ค่า Seed เขียนเป็นตัวเลขตรง ๆ และมี Test ตรวจว่าตรงกับสูตร |
| Snapshot ใน `STAFFING_GAP` | เก็บ `effective_minimum` คอลัมน์เดียว ลบ `patient_count` กับ `patients_per_nurse` `required_staff` และ `minimum_staff` อ่านผ่าน `staffing_requirement_id` ไม่เก็บซ้ำ |

```text
if preserve_minimum_staffing:
    effective_minimum = max(minimum_staff, required_staff)
else:
    effective_minimum = required_staff

headcount_gap = max(effective_minimum - current_valid_staff, 0)
```

* `preserve_minimum_staffing` คือธงใน `HARD_CONSTRAINT_POLICY` (Seed เป็น `true`) ธงนี้เป็น `false` = ไม่ใช้ `minimum_staff` เป็นพื้น
* ธงนี้ใช้ที่การคิด Gap ที่เดียว การกันไม่ให้ต้นทางขาดคนเป็นของอีกธงคือ `preserve_source_ward_minimum` (ร่างรอบ 1 ข้อ 7.2 Q15) ทั้งสองอย่างทำในรอบ 1
* `current_valid_staff` = จำนวนคนในเวรที่นับตอนนี้ (Roster ที่ `ASSIGNED`) ไม่เปลี่ยนวิธีนับ
* Golden Case ไม่เปลี่ยนผล: เวร 1 มี `required_staff = 5`, `minimum_staff = 4` เป้าหมายยังเป็น 5 และค่า Seed ตรงกับสูตรอยู่แล้ว (ผู้ป่วย 10 คน หาร 2 = 5, เวร 2 ผู้ป่วย 2 คน หาร 2 = 1)
* Ratio ที่ใช้คือ `HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse` ค่าเดียวทั้งโรงพยาบาล โหลดด้วย `policy_service.get_hard_constraint_policy(db)` ซึ่งเลือก Policy `id=1` ตาม Seed ไม่มีค่า Default / Fallback ใน Calculator และไม่มีคอลัมน์ Ratio ใน WARD ค่านี้ไม่ใช่ `APPROVAL_POLICY.ratio` (ตัวคูณสำหรับ Auto-approval)
* ตรวจ Role / Skill ตาม Requirement แยกจาก Headcount ขาดอย่างใดอย่างหนึ่งก็ถือว่ามี Gap แม้จำนวนคนจะเพียงพอแล้วก็ตาม
* โค้ดที่เขียน `required_staff` ใหม่มีที่เดียวคือ PART B (`merge_window_service`) และเขียนเฉพาะ Window ที่มี Event ผ่าน Threshold การแก้ `SHIFT.patient_count` อย่างเดียวจึงไม่เปลี่ยน Gap
* ตรวจ Gap ด้วย `gap_service.assess_shift(db, shift)` ซึ่งโหลด Requirement ผ่าน `requirement_service.get_current_requirement()` (Seam 10) การปิด Window และขั้น `ASSESSING` ต้องเรียกฟังก์ชันเดียวกันนี้
* `effective_minimum` คือค่าที่ส่งเข้าสูตร `headcount_gap` จริง `record_gap()` เขียนค่าที่ใช้คิด ไม่คิดใหม่ตอนบันทึก
* `required_staff` ถูก UPDATE ในแถวเดิม ค่าที่อ่านผ่าน `staffing_requirement_id` จึงเป็นค่าปัจจุบัน ไม่ใช่ค่าตอนคิด Gap ค่าเดียวในแถว Gap ที่บอกเป้าหมายตอนคิดคือ `effective_minimum` ห้ามเอา `required_staff` / `minimum_staff` ของ Requirement มาแสดงคู่กับ Gap เก่าว่าเป็นค่าที่ใช้คิด (Q20)

* **ข้อมูลไม่ตรงกันได้:** `PATIENT_SURGE` เปลี่ยน `patient_count` ใน PART B ตอนถึงคิวของ Event ตัวนั้น (Q41) แต่ `required_staff` ถูกเขียนใหม่เฉพาะเมื่อ Window นั้นมี Event ที่ผ่าน Threshold ถ้าไม่มี สองค่านี้จะไม่ตรงกันจนกว่าจะมี Window ที่มี Event ผ่าน เป็นไปตามที่ออกแบบ (ไม่ผ่าน Threshold = ไม่เขียน `required_staff`)
* Policy `id=1` ถูกตรึงตลอด Demo ไม่แก้ค่าระหว่างที่มีเคสทำงาน การเลือกเวอร์ชันตาม `effective_from` และ Ratio แยก Ward เป็นงานภายหลัง `STAFFING_GAP` ยังไม่มี FK ไป Hard Policy

### 3.7 Audit ของ Event

* แถว Audit ที่เป็นเรื่องของ Event ใส่ `AUDIT_LOG.event_id` อย่างเดียว ไม่ใส่ `case_id` ทุกกรณี รวมถึงเวรที่ Window = 0 ใส่ตั้งแต่ตอนเขียน ไม่มีการแก้แถว Audit ทีหลัง (Q33) แถวกลุ่มนี้คือ `EVENT_RECEIVED`, `EVENT_IGNORED` และ Action ของขั้น Update table (`UNAVAILABILITY_CREATED`, `ASSIGNMENT_CANCELLED`, `PATIENT_COUNT_UPDATED`, `REQUIREMENT_UPDATED`)
* Timeline ของเคส = แถวที่ `case_id` เป็นเคสนี้ รวมกับแถวที่ `event_id` เป็น Event ของเคสนี้ (หาจาก `STAFFING_EVENTS.case_id`) เรียงตาม `id` แถวของ Event ทุกแถวขึ้นก่อน `CASE_OPENED` เพราะเคสถูกสร้างหลังวนครบทุก Event
* Event ที่ `IGNORED` ไม่มีเคส แต่ยังค้น Audit ของมันได้จาก `event_id`
* `EVENT_IGNORED` ใช้ Actor `workflow_orchestrator` เหมือน `CASE_OPENED` (เป็นการตัดสินของระบบ) `entity_type = STAFFING_EVENTS` payload มี `event_id`, `shift_id` และ `reason` ซึ่งเป็นรหัสจาก `EventIgnoredReason` (`domain/enums.py`)

  | `reason` | ความหมาย | ใครได้ |
  |---|---|---|
  | `THRESHOLD_NOT_PASSED` | ไม่มี Event ไหนใน Window ผ่าน Threshold (กรณี ต4) | ทุก Event ของ Window |
  | `NO_GAP` | มี Event ที่ผ่าน แต่ Gap จากข้อมูลสุดท้ายเป็น 0 ทุกตัว (กรณี ต5) | ทุก Event ของ Window |
  | `NO_ASSIGNED_ROSTER` | คนของ Event นี้ไม่มี Roster `ASSIGNED` ให้ยกเลิกแล้ว เช่น แจ้งซ้ำใน Window เดียว (Q44) | เฉพาะ Event ตัวนั้น |
  | `REQUIREMENT_ITEM_NOT_FOUND` | Role / Skill ที่ Event นี้แก้ไม่อยู่ใน Requirement ปัจจุบันของเวร (Q44) | เฉพาะ Event ตัวนั้น |

* แถว `EVENT_IGNORED` ของ Event ที่ Update table ไม่ได้ (สองรหัสหลัง) ถูกเขียนตอนถึงคิวของ Event ตัวนั้น แทนที่แถว Action ของมัน ส่วนสองรหัสแรกเขียนหลังวนครบทุก Event
* `audit_service.log()` ไม่รับแถวที่มีทั้ง `case_id` และ `event_id` (โยน `ValueError`)
* ลำดับของแต่ละกรณีอยู่ข้อ 7.3

### 3.8 Job ปิด Window และการเลื่อน Clock

* Job เป็น Service แยกใน `docker-compose.yml` ทำหน้าที่จับรอบอย่างเดียว ทุก 30 วินาทีเรียก Route ภายใน `POST /internal/merge-windows/close-due` ของ Backend Route นี้กันด้วย Secret ใน Header `X-Internal-Secret` ค่าอ่านจาก env `INTERNAL_JOB_SECRET` ไม่ Commit ลง Repo (Q35)
  * Header ไม่มีหรือไม่ตรง ตอบ `401` ถ้า Backend ไม่ได้ตั้ง `INTERNAL_JOB_SECRET` Route ตอบ `503` ทุกคำขอ ไม่มีค่าไหนเปิดได้ (ไม่ตั้ง = ปิด ไม่ใช่เปิด)
  * ค่าต้องยาวอย่างน้อย 8 ตัวอักษร `docker-compose.yml` และ `.env.example` ใส่ค่า `local-dev-only` ไว้สำหรับเครื่องพัฒนาเท่านั้น แบบเดียวกับรหัสผ่านของ PostgreSQL ที่อื่นต้องตั้งค่าเอง
  * Service ชื่อ `job` รัน `python -m app.jobs.ticker` ใช้แค่ Standard Library ไม่ติดตั้งอะไรและไม่ต่อ DB ปรับรอบได้ด้วย env `JOB_INTERVAL_SECONDS` ซึ่งต้องเป็นตัวเลขตั้งแต่ 1 ขึ้นไป ค่าอื่นทำให้ Service หยุดพร้อมข้อความ การเรียกที่ล้มเหลวทุกแบบ รวม Backend รีสตาร์ตกลางคำขอ ไม่ทำให้ Service ล้ม รอบถัดไปเรียกใหม่
* Backend เป็นคนตัดสินว่าเวรไหนถึงเวลาปิด ด้วยนาฬิกาของ Backend เอง เพราะเวลาของ Demo ที่ถูกหยุดไว้อยู่ในหน่วยความจำของ Process ของ Backend (`core/clock.py`) Service แยกเห็นแต่เวลาจริง
* `POST /demo/clock/advance` เลื่อน Clock ของ Demo แล้วเรียกฟังก์ชันปิด Window ตัวเดียวกับ Job เพราะเลื่อนนาฬิกาอย่างเดียว Job ไม่รันเอง
* ทั้ง Route ของ Job และ Route เลื่อน Clock เรียก `job_service.run_due_work(db)` ตัวเดียวกัน ซึ่งปิด Window ที่ถึงเวลาทีละเวร หนึ่ง Transaction ต่อเวร เวรที่ปิดไม่สำเร็จถูก Rollback และข้ามไป เวรอื่นไม่ได้รับผล
* PR O ให้ `run_due_work()` ปิด Offer ที่หมดเวลา → recovery sweep → ปิด Window ที่ถึงเวลา ตามลำดับนี้ เพื่อให้เคสที่หยุดจาก timeout ปล่อย Window ที่รออยู่ได้ใน tick เดียวกัน ปิด Offer / recovery เคสละ Transaction และ Window เวรละ Transaction หนึ่งเคสที่ผิดพลาดไม่หยุดเคสอื่น แต่ลองใหม่รอบถัดไป

### 3.9 ข้อจำกัดที่รู้

* แก้ `merge_window_seconds` ของเวรขณะ Window เปิดอยู่ เวลาปิดเลื่อนตาม เพราะไม่ได้เก็บเวลาปิดไว้
* ถ้า PART B พังกับเวรไหน Event ของเวรนั้นค้าง `RECEIVED` และ Job ลองใหม่ทุกรอบ รอบ 1 ไม่มีการเลิกลองเอง: Window นั้นยังเปิดอยู่ Event ใหม่ของเวรนั้นเข้าคิวต่อ และ Backend เขียน Log ระดับ Error ทุกรอบจนกว่าจะมีคนแก้ต้นเหตุ เหตุผลที่ไม่ตั้ง Event เป็น `IGNORED` เอง: การลาหรือการเพิ่มผู้ป่วยที่แจ้งมาจะหายไปเงียบ ๆ ทั้งที่เวรอาจขาดคนจริง ต้นเหตุที่รู้ตอนนี้คือเวรไม่มี Requirement ซึ่งถูกปฏิเสธตั้งแต่ตอนรับแล้ว (ข้อ 3.5)
* ระหว่างที่เคสของเวรยังเดินอยู่ Event ใหม่ของเวรนั้นไม่ถูกทำอะไร Offer มี Timeout (ข้อ 6.9) แต่การอนุมัติไม่มี เคสที่ค้างรออนุมัติจึงเดินได้นาน คนที่แจ้งลาช่วงนั้นยังเป็น `ASSIGNED` ใน Roster (Q41) และการขาดคนเพิ่มยังไม่ถูกหาคนแทนจนกว่าเคสแรกจบ
* ตอน Window = 0 ถ้าเวรมีเคสเดินอยู่ `POST /events` ตอบ `RECEIVED` ไม่ได้เคสทันที Test ที่ให้สองคนลาเวรเดียวกันแล้วคาดสองเคสทันทีต้องแก้
* ตอน Window = 0 กับ Clock ที่หยุดนิ่งของ Demo Event คนละชุดของเวรเดียวกันได้ `processed_at` เท่ากันได้ ยอมรับ เพราะตอน Window = 0 หนึ่ง Event คือหนึ่งชุดอยู่แล้ว
* Event ที่รอเคสก่อนหน้าจบ ถูกปิดพร้อมกับการปิด Window ครั้งถัดไปของเวรนั้น ไม่ว่าใครเป็นคนเรียก: Job, การเลื่อน Clock หรือ `POST /events` ตัวถัดไปของเวรที่ Window = 0 Event ที่รออยู่กับ Event ใหม่จึงอยู่ Window เดียวกันและได้เคสเดียวกัน
* `required_staff` ที่ PART B เขียนไม่มีแถว Audit ของตัวเอง ค่าใหม่ดูได้จาก `effective_minimum` ของ Gap และจาก `PATIENT_COUNT_UPDATED` ของ Event ที่เปลี่ยนจำนวนผู้ป่วย
* `ASSIGNMENT_CANCELLED` ไม่ตรวจว่า `staff_id` เป็นพนักงานที่มีอยู่แยกจากการตรวจ Roster: คนที่ไม่มีอยู่ไม่มี Roster `ASSIGNED` จึงได้ `409` เหมือนคนที่ไม่ได้อยู่เวรนั้น

### 3.10 โค้ดอยู่ที่ไหน

| ส่วน | ไฟล์ |
|---|---|
| PART A รับ Event และอ่านสถานะ Event | `services/event_service.py` (`receive_event()`, `get_event()`) |
| PART B ปิด Window | `services/merge_window_service.py` (`lock_shift()`, `find_due_shift_ids()`, `close_window()`, `close_locked_window()`, `close_due_windows()`) |
| Threshold | `domain/staffing/threshold.py` (`check_threshold()` เป็น Pure Function คืนว่าผ่านเพราะ Ratio, Role ไหน หรือ Skill ไหน) |
| งานที่ถึงเวลา | `services/job_service.py` (`run_due_work()`) |
| ตัวจับรอบ | `jobs/ticker.py` |
| Scenario สำหรับ Test | `seed/scenarios/merge_gap.py` (เวร 1 ตั้ง Window 600 วินาที), `seed/scenarios/threshold.py` (เวร 3 ที่คนเกินความต้องการ) |

* `close_locked_window()` คือ PART B ของเวรที่ผู้เรียกล็อกไว้แล้ว Commit เองเมื่อปิด Window ได้ และคืน `None` โดยไม่เขียนอะไรเมื่อยังไม่ถึงเวลา PART A ของเวรที่ Window = 0 เรียกตัวนี้ต่อใน Transaction เดียวกัน
* `SHIFT.merge_window_seconds` ไม่มีค่า Default ใน DB ส่วน Model ใส่ `0` ให้เมื่อโค้ดสร้าง `Shift` โดยไม่ระบุ (0 = ไม่รอ เหมือน Skeleton) Seed ระบุค่าเองทุกเวร

---

## 4. Case Status

| Status | ความหมาย | ประเภท | ใช้ในรอบ 1 |
|---|---|---|---|
| `OPEN` | เปิดเคสแล้ว พบว่ามี Gap | อัตโนมัติ | ✅ |
| `ASSESSING` | ประเมินและบันทึก `STAFFING_GAP` | อัตโนมัติ | ✅ |
| `OPTIMIZING` | สร้างรายชื่อผู้สมัคร (Solver) | อัตโนมัติ | ✅ |
| `OUTREACH` | กำลังเลือกคนและส่ง Offer ของ Wave | อัตโนมัติ (ชั่วคราว) | ✅ |
| `WAITING_RESPONSE` | รอผู้สมัครตอบ | **จุดรอ** | ✅ |
| `SAFETY_VALIDATION` | ค่าคงไว้ใน Enum เคสไม่หยุดที่สถานะนี้แล้ว Safety ตรวจรายคนทันทีที่ผู้สมัครตอบรับ (Q31) ไม่มี Handler และไม่มีเส้นเข้าสถานะนี้ตั้งแต่ PR 3 | อัตโนมัติ | เลิกใช้เป็นขั้นของเคส |
| `WAITING_APPROVAL` | รอผู้อนุมัติ | **จุดรอ** | ✅ |
| `EXECUTING` | ปิดงานของเคสเมื่อ Gap ถูกปิด: ยกเลิก Offer ที่เหลือและเขียน `CASE_RESOLVED` การจัดเวรรายคนเกิดไปแล้วตอนอนุมัติ (Q45) | อัตโนมัติ | ✅ |
| `RESOLVED` | คนที่ได้เข้าเวรจากเคสนี้ปิด Gap ของเคสครบ | สิ้นสุด | ✅ |
| `MANUAL_HANDOFF` | ไม่เหลือผู้สมัคร ส่งต่อให้คนจัดการ Workflow อัตโนมัติหยุด | หยุดอัตโนมัติ | ✅ (หยุดที่สถานะนี้) **[รอบ 2 · PR H]** เคสออกได้สองทาง คือ T8 และ T9 จากการกระทำของ Head Nurse หรือจากขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด (ข้อ 6.12) |
| `UNRESOLVED` | คนจัดการแล้วแต่แก้ไม่ได้ | สิ้นสุด | ยังไม่มีโค้ดใดเขียนค่านี้ **[รอบ 2 · PR H]** เป็นปลายทางของ T9 |
| `FAILED` | ระบบหรือบริการขัดข้อง | สิ้นสุด | ✅ (ตาม D11) |

**จุดรอ** คือ State ที่ Orchestrator หยุด เคสออกจากจุดรอเมื่อ Service ของ API ภายนอกหรือ Job เรียก `orchestrator.recompute(db, case_id)` ซึ่งคำนวณสถานะใหม่จาก Gap ที่เหลือและ Offer ที่ค้าง (ข้อ 5.3) Service ไม่แก้ `case.status` เอง (D3) `orchestrator.resume(db, case_id, next_status)` ของ Skeleton ยังอยู่จนกว่าผู้เรียกทุกตัวเปลี่ยนไปใช้ `recompute()`

### 4.1 สถานะรายคน

เคสหนึ่งมีผู้สมัครหลายคนพร้อมกัน แต่ละคนอยู่คนละขั้น สถานะรายคนไม่มีคอลัมน์เดียวที่เก็บ อ่านจากแถวของผู้สมัคร (ผูกด้วย `candidate_item_id`)

| ผู้สมัครอยู่ขั้นไหน | ดูจาก | `stage` |
|---|---|---|
| ยังไม่ถูกติดต่อ | ไม่มีแถว `CANDIDATE_OUTREACH` | `NOT_CONTACTED` |
| ส่ง Offer แล้ว รอคำตอบ | `CANDIDATE_OUTREACH.status = SENT` | `OFFER_SENT` |
| ปฏิเสธ | `status = REJECTED` | `OFFER_REJECTED` |
| ตอบรับ รอตรวจ Safety | `status = ACCEPTED` และยังไม่มีแถว `SAFETY_VALIDATION` | `ACCEPTED` |
| ตอบรับ แต่ Safety ไม่ผ่าน | `SAFETY_VALIDATION.is_passed = false` และ Offer เป็น `CANCELLED` | `SAFETY_FAILED` |
| รออนุมัติ | `APPROVAL_REQUEST.is_pending = true` และมี Offer `ACCEPTED` ของเคส / Item เดียวกัน | `WAITING_APPROVAL` |
| ไม่ได้รับอนุมัติ | `APPROVAL_REQUEST.is_approved = false` และ Offer เป็น `CANCELLED` | `APPROVAL_REJECTED` |
| ได้รับอนุมัติ | `APPROVAL_REQUEST.is_approved = true` | `APPROVED` |
| ได้เข้าเวรแล้ว | มีแถว `ROSTER_ASSIGNMENT` แบบ `REPLACEMENT` | `ASSIGNED` |

`GET /cases/{id}` คืนขั้นนี้เป็น `candidates[].stage` (ข้อ 9.3) Offer ที่จบแบบอื่นใช้ `OFFER_TIMEOUT`, `OFFER_CANCELLED`, `OFFER_PENDING` และ `OFFER_FAILED`

**[รอบ 2 · PR T]** เพิ่ม `stage` ค่าใหม่ `APPROVAL_TIMEOUT` สำหรับผู้สมัครที่คำขออนุมัติหมดเวลา แยกจาก `APPROVAL_REJECTED` และเมื่อผู้สมัครถูกติดต่อรอบที่สองได้ `stage` อ่านจาก Offer ที่ `id` มากสุดของผู้สมัครคนนั้น (ข้อ 6.13)

### 4.2 สถานะเคส

สถานะเคสคำนวณจาก Gap ที่เหลือ ไม่ตามผู้สมัครคนใดคนหนึ่ง คำว่า "Gap ถูกปิด", "Offer ค้าง" และ "Offer ที่ถูกพัก" นิยามในข้อ 5.1

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
* อนุมัติกดต่อคน หนึ่ง `APPROVAL_REQUEST` ต่อผู้สมัคร และจัดเวรทีละคนทันทีที่ได้รับอนุมัติ ไม่รอครบ (Q27)
* ได้คนไม่ครบและไม่เหลือผู้สมัคร: คนที่จัดเวรแล้วอยู่ต่อ เคสไป `MANUAL_HANDOFF`
* คนที่ตอบรับหลังจาก Gap ถูกปิดครบแล้วด้วยคนที่ตอบรับก่อนหน้าเป็น**สำรอง**: Offer เป็น `ACCEPTED` ยังไม่ตรวจ Safety ยังไม่ขออนุมัติ ถ้าคนก่อนหน้าหลุด สำรองคนแรกตามเวลาที่ตอบรับเข้า Safety ต่อ เมื่อเคส `RESOLVED` ยกเลิกทั้ง Offer ที่ยัง `SENT` และของสำรอง (Q28)

---

## 5. Transition

### 5.1 ตาราง Transition

เส้นของ Skeleton ที่ยังใช้

| จาก | ไป | ใครสั่ง | เกิดเมื่อ |
|---|---|---|---|
| (ไม่มีเคส) | `OPEN` | ฟังก์ชันปิด Window ใน `event_service` | Window ปิดแล้ว Gap สุดท้ายไม่เป็น 0 (ข้อ 3.1) |
| `OPEN` | `ASSESSING` | handler `intake_event` | ทันที |
| `ASSESSING` | `OPTIMIZING` | handler `assess_staffing` | บันทึก Gap แล้ว `result.has_gap` เป็น True (Headcount หรือ Role หรือ Skill ขาด) |
| `OPTIMIZING` | `OUTREACH` | handler `optimize` | ได้รายชื่อผู้สมัครอย่างน้อย 1 คน |
| `OUTREACH` | `WAITING_RESPONSE` | handler `contact_candidate` | ส่ง Offer ของ Wave แล้ว หรือไม่เหลือผู้สมัครแต่มี Offer ที่ถูกพักซึ่งยังไม่หมดเวลา (`wait=True`) |
| `WAITING_APPROVAL` | `EXECUTING` | `orchestrator.recompute()` | คนที่ได้เข้าเวรแล้วปิด Gap ครบ |
| `EXECUTING` | `RESOLVED` | handler ของ `EXECUTING` | ยกเลิก Offer ที่เหลือและเขียน `CASE_RESOLVED` แล้ว |

เส้นใหม่ของรอบ 1

เคสไม่ได้เดินตามผู้สมัครคนใดคนหนึ่งแล้ว สถานะเคสคำนวณจาก Gap ที่เหลือและ Offer ที่ค้าง (ข้อ 4) เพิ่ม 7 เส้น และเลิกใช้ 2 เส้น

| # | จาก | ไป | เกิดเมื่อ |
|---|---|---|---|
| T1 | `WAITING_RESPONSE` | `OUTREACH` | Gap ยังไม่ถูกปิด และเคสไม่มี Offer ค้าง |
| T2 | `WAITING_RESPONSE` | `WAITING_APPROVAL` | คนที่เข้าเวรแล้วรวมกับคนที่รออนุมัติ ปิด Gap ได้ครบ |
| T3 | `WAITING_APPROVAL` | `WAITING_RESPONSE` | Gap ยังไม่ถูกปิดแม้รวมคนที่รออนุมัติ และเคสมี Offer ค้าง เกิดได้หลังมีคนหลุด หรือเมื่อ Offer ที่ถูกพักกลับมากดรับได้ |
| T4 | `WAITING_APPROVAL` | `OUTREACH` | Gap ยังไม่ถูกปิดแม้รวมคนที่รออนุมัติ และเคสไม่มี Offer ค้าง เกิดได้หลังผู้อนุมัติตัดสิน (อนุมัติหรือไม่อนุมัติก็ได้) |
| T5 | `OUTREACH` | `MANUAL_HANDOFF` | `contact_candidate` ไม่เหลือผู้สมัครที่ส่ง Offer ได้ ไม่มีคนรออนุมัติที่เติม Gap ได้ และไม่มี Offer ที่ถูกพักซึ่งยังไม่หมดเวลา |
| T6 | `OPTIMIZING` | `MANUAL_HANDOFF` | Solver ไม่ได้ผู้สมัครเลย Handler `optimize` บันทึก Plan `INFEASIBLE` เขียน `SOLVER_EXECUTED` และ `MANUAL_HANDOFF` (`NO_FEASIBLE_PLAN`) แล้วคืน `MANUAL_HANDOFF` (ตั้งแต่ PR 2a) |
| T7 | `OUTREACH` | `WAITING_APPROVAL` | `contact_candidate` ไม่เหลือผู้สมัครที่ส่ง Offer ได้ แต่ยังมีคนรออนุมัติที่เติม Gap ได้ |

เส้นของ T2 และ T3 ยังถูกใช้อีกแบบโดย `recompute()` ตอนเคสไม่เหลือใครให้ติดต่อ: ไป `WAITING_APPROVAL` เมื่อยังมีคนรออนุมัติ และไป `WAITING_RESPONSE` เมื่อเหลือแต่ Offer ที่ถูกพัก (ข้อ 5.3 กฎข้อ 5 และ 6) และเคสที่ได้คนครบตอนอยู่ `WAITING_RESPONSE` ผ่านเส้นของ T2 ไป `EXECUTING`

เส้นเดิมที่เลิกใช้: `WAITING_RESPONSE → SAFETY_VALIDATION` และ `SAFETY_VALIDATION → WAITING_APPROVAL` เพราะ Safety ตรวจรายคนตอนตอบรับ เคสไม่หยุดที่สถานะนี้ (Q31) สองเส้นนี้ลบออกจาก `transitions.py` แล้วใน PR 3 พร้อม Handler ของสถานะนี้ ค่า `SAFETY_VALIDATION` ยังอยู่ใน Enum และเหลือเส้นไป `FAILED` เส้นเดียวเหมือนทุกสถานะที่ไม่ใช่สิ้นสุด

เส้นใหม่ของรอบ 2

รอบ 1 หยุดเคสไว้ที่ `MANUAL_HANDOFF` โดยไม่มีทางไปต่อ รอบ 2 เพิ่มสองเส้นออก ไม่มี Handler และ `recompute()` ไม่เดินเส้นนี้ ผู้เดินมีสองแบบเท่านั้น คือ Route ของ PR H ที่ Head Nurse กด และขั้นปิด Window เมื่อเคสใหม่ของเวรเดียวกันเปิด (เฉพาะ T9) เส้นทั้งสองอยู่ใน `transitions.py` แล้วตั้งแต่ PR 0 ของรอบ 2 แต่ยังไม่มีโค้ดใดเรียกจนกว่า PR H จะเข้า

| # | จาก | ไป | เกิดเมื่อ |
|---|---|---|---|
| T8 | `MANUAL_HANDOFF` | `RESOLVED` | **[รอบ 2 · PR H]** Head Nurse จัดคนเข้าเวรเองจนคนที่ได้เข้าเวรปิด Gap ของเคสครบทั้งจำนวนคน, Role และ Skill (ข้อ 6.12) Head Nurse ไม่ต้องกดปิดเคส Route จัดคนเองของ PR H เรียก Orchestrator ให้เดินเส้นนี้ใน Transaction เดียวกับการจัดคนที่ทำให้ Gap ถูกปิด ไม่ใช่ `recompute()` |
| T9 | `MANUAL_HANDOFF` | `UNRESOLVED` | **[รอบ 2 · PR H]** มีสองทาง ทางแรก Head Nurse ปิดเคสโดยไม่มีคนแทนพร้อมเหตุผล ทางที่สอง**ระบบปิดเอง**: เมื่อเคสใหม่ของเวรเดียวกันเปิด ขั้นปิด Window ปิดเคสเดิมที่ยัง `MANUAL_HANDOFF` ด้วย Actor `workflow_orchestrator` (ข้อ 6.12) ทั้งสองทางเรียก Orchestrator ไม่ใช่ `recompute()` |

* ไม่มีเส้นจาก `MANUAL_HANDOFF` กลับเข้าเส้นทางอัตโนมัติ เช่น กลับไป `OPTIMIZING` หรือ `OUTREACH` Solver ยังรันครั้งเดียวต่อเคส (Q37, R2-Q8)
* `FAILED` ยังเป็นจุดจบ ไม่มีเส้นออก เคส `FAILED` แสดงในรายการของ Head Nurse แต่กดจัดการไม่ได้ (R2-Q22)
* **[รอบ 2 · PR B]** เคสเข้า `MANUAL_HANDOFF` ทาง T6 ได้อีกเหตุหนึ่ง คือ Solver หมดเวลาโดยยังไม่มีแผน (สถานะ `UNKNOWN`) เหตุผลใน Audit คือ `SOLVER_TIMEOUT` (ข้อ 6.14)

คำที่ใช้ในตาราง

* **Gap ถูกปิด** = Gap ของจำนวนคน, Role และ Skill เป็น 0 ทุกตัว เมื่อนับคนกลุ่มที่ระบุ (Q46)
* **Offer ค้าง** = Offer ของเคสที่ยัง `SENT` ไม่นับ Offer ที่ผู้สมัครกดรับไม่ได้เพราะรับของเคสอื่นค้างอยู่ (Q29)
* **Offer ที่ถูกพัก** = Offer ของเคสที่ยัง `SENT` แต่ผู้สมัครกดรับไม่ได้ชั่วคราว เพราะเขากดรับ Offer ของเคสอื่นไปแล้วและยังรอผล (ข้อ 6.8) ไม่นับเป็น Offer ค้าง เคสจึงส่ง Wave ให้คนอื่นต่อได้ แต่ตราบที่ Offer นี้ยังไม่หมดเวลา เคสต้องไม่ไป `MANUAL_HANDOFF` เพราะผู้สมัครอาจกลับมากดรับได้
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

* เคสไม่ไป `MANUAL_HANDOFF` ตอนที่ยังมีคนรออนุมัติที่เติม Gap ได้ เพราะยังมีทางแก้ผ่าน Workflow ปกติ รอจนผู้อนุมัติตัดสิน การอนุมัติไม่มี Timeout (ข้อ 6.9) **[รอบ 2 · PR T]** การรอนี้จะมีเส้นตาย (ข้อ 6.13)
* ระหว่างรอ ถ้ายังมีผู้สมัครที่ติดต่อได้ เคสส่ง Wave ต่อได้ตามปกติ การรออนุมัติไม่หยุดการหาคน
* หลังตัดสินครบแล้ว Gap ยังเหลือ และไม่มีอะไรให้ทำต่อ เคสจึงไป `MANUAL_HANDOFF` ผ่าน T4 แล้ว T5
* เคสที่รอ Offer ที่ถูกพักจะถูกปลุกสามทาง ทุกทางเรียก `recompute()` ของเคสนี้ (ข้อ 5.3): เคสที่ผู้สมัครไปรับไม่อนุมัติเขาหรือ Safety ไม่ผ่าน (Offer กลับมากดรับได้), เคสนั้นอนุมัติเขา (Offer ที่ขัดกับเวรใหม่ถูกยกเลิก) หรือ Offer หมดเวลา การรอนี้จึงนานสุดไม่เกินอายุของ Offer (ข้อ 6.9)
* ตัวอย่างที่กติกานี้กัน: A มี Offer ของเคส X และเคส Y โดยเคส Y เหลือ A เป็นคนสุดท้าย A กดรับเคส X ถ้าเคส Y ไป `MANUAL_HANDOFF` ทันที Offer ของ A จะถูกยกเลิก พอเคส X ไม่อนุมัติ A เขาจะกลับไปรับเคส Y ไม่ได้ ซึ่งขัดกับข้อ 6.8

เส้นที่ไม่ต้องมี

* ไม่มีเส้นออกจาก `EXECUTING` นอกจาก `RESOLVED` และ `FAILED`: การจัดเวรรายคนเกิดตอนอนุมัติ เคสผ่าน `EXECUTING` ครั้งเดียวตอน Gap ถูกปิดเพื่อปิดงาน (Q45) และไม่มีการตรวจซ้ำตอนจัดเวร (Q38)
* ไม่มีสถานะ `WAITING_MERGE_WINDOW`: Window อยู่ก่อนเคส (ข้อ 3)

### 5.2 `FAILED` และสิ่งที่ไม่เปลี่ยน

| จาก | ไป | เกิดเมื่อ |
|---|---|---|
| ทุก State ที่ไม่ใช่สิ้นสุด | `FAILED` | Exception ระหว่าง Workflow (D11) |

* `FAILED` ยังตั้งได้จากเส้นทาง D11 เท่านั้น (Exception) Handler ห้ามคืน `FAILED`
* `MANUAL_HANDOFF` → `FAILED` มีอยู่แล้ว รอบ 2 เพิ่มเส้นออกอีกสองเส้น คือ T8 และ T9 (ข้อ 5.1) ผู้เดินคือ Route ที่ Head Nurse กด หรือขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด (เฉพาะ T9) Handler และ `recompute()` ไม่เดินสองเส้นนี้
* จุดรอของเคสยังมีสองจุด: `WAITING_RESPONSE`, `WAITING_APPROVAL`
* `CASE_STATUS_CHANGED` ยังเขียนโดย Orchestrator เท่านั้น

### 5.3 ฟังก์ชันคำนวณสถานะเคส

* **ฟังก์ชันคำนวณสถานะเคส** ตัวใหม่ แยกเป็นสองชั้นแบบเดียวกับ `gap_calculator`
  * ชั้นตัดสิน (Pure Function ไม่อ่าน DB): `domain/workflow/case_status.py` มี `decide_status(facts: CaseFacts) -> CaseStatus` โดย `CaseFacts` เป็น Dataclass แบบ Frozen มี 6 ค่า: `gap_closed_by_assigned`, `gap_closed_with_pending`, `has_open_offer`, `has_uncontacted_candidate`, `has_pending_approval`, `has_paused_offer` คืนได้ 4 สถานะ ตรวจตามลำดับนี้ ข้อแรกที่จริงคือคำตอบ
    1. `gap_closed_by_assigned` จริง (คนที่ได้เข้าเวรแล้วปิด Gap ครบ) → `EXECUTING`
    2. `gap_closed_with_pending` จริง (รวมคนที่รออนุมัติแล้วปิด Gap ครบ) → `WAITING_APPROVAL`
    3. `has_open_offer` จริง (เคสมี Offer ค้าง) → `WAITING_RESPONSE`
    4. `has_uncontacted_candidate` จริง (Plan ล่าสุดของเคสยังมีผู้สมัครที่เคสนี้ไม่เคยส่ง Offer ให้) → `OUTREACH` ส่ง Wave ถัดไป
    5. `has_pending_approval` จริง (มีคนรออนุมัติ) → `WAITING_APPROVAL` รอต่อ
    6. `has_paused_offer` จริง (มี Offer ที่ถูกพัก) → `WAITING_RESPONSE` รอต่อ
    7. นอกนั้น → `OUTREACH` ให้ `contact_candidate` เป็นคนส่งเคสไป `MANUAL_HANDOFF` (T5)
  * ข้อ 5 ถึง 7 เพิ่มตามรีวิวของ PR S แทนกฎเดิมที่มี 3 ค่าและ 4 ข้อ เหตุผล: กฎเดิมไม่มีคำตอบว่า "รอต่อ" เคสที่ไม่เหลือใครให้ติดต่อแต่ยังมีสิ่งที่ต้องรอ (จอดที่ `WAITING_APPROVAL` ผ่าน T7 หรือจอดที่ `WAITING_RESPONSE` เพราะ Offer ที่ถูกพัก) จะคำนวณได้ `OUTREACH` ทุกครั้งที่ถูกเรียก วิ่งเข้า `contact_candidate` แล้วกลับมาที่เดิม เขียน `CASE_STATUS_CHANGED` สองแถวต่อครั้งโดยไม่มีอะไรเปลี่ยน ตอนนี้เคสแบบนั้นได้สถานะเดิม จึงไม่เขียนอะไร
  * ข้อ 4 มาก่อนข้อ 5 และ 6 เสมอ การรออนุมัติหรือรอ Offer ที่ถูกพักจึงไม่หยุดการส่ง Wave ตามข้อ 5.1 ส่วนลำดับของข้อ 5 กับ 6 เป็นลำดับเดียวกับที่ `contact_candidate` ใช้ตอนไม่เหลือผู้สมัคร (T7 ก่อน แล้วจึง Offer ที่ถูกพัก)
  * `has_pending_approval` ไม่ได้ตรวจว่าคนที่รออนุมัติ "เติม Gap ได้" หรือไม่ ใช้แค่ว่ามีคนรออนุมัติ เพราะผู้สมัครทุกคนที่ผ่าน Safety ถูกเลือกมาเติม Target อย่างน้อยหนึ่งตัวอยู่แล้ว การตรวจแบบละเอียดยังเป็นของ `contact_candidate` (T7)
  * ข้อที่ยังวนได้: Plan ยังมีผู้สมัครที่ไม่เคยติดต่อ (ข้อ 4) แต่ทุกคนถูกข้ามเพราะ Hard Rules หรือเต็มเพดาน Offer เคสจะเข้า `OUTREACH` แล้วกลับมาจุดรอทุกครั้งที่ถูกเรียก จนกว่าจะส่งได้หรือสิ่งที่รอจบลง ตรงกับที่ Job เก็บตกลองใหม่ทุกรอบ
  * เส้นที่ข้อ 5 และ 6 ใช้: จาก `WAITING_RESPONSE` ไป `WAITING_APPROVAL` ใช้เส้นของ T2 และจาก `WAITING_APPROVAL` ไป `WAITING_RESPONSE` ใช้เส้นของ T3 ไม่มีเส้นใหม่ใน `transitions.py`
  * **เคสที่ได้คนครบตอนอยู่ `WAITING_RESPONSE`:** ไม่มีเส้น `WAITING_RESPONSE → EXECUTING` `recompute()` จึงพาเคสผ่าน `WAITING_APPROVAL` (T2) แล้วไป `EXECUTING` เขียน `CASE_STATUS_CHANGED` ทั้งสองช่วง เคสที่มีคนเข้าเวรครบแล้วต้องไม่เป็น `FAILED` เกิดได้เมื่อ Gap ถูกปิดโดยไม่มี `recompute()` คั่นที่ `WAITING_APPROVAL` เช่น การอนุมัติที่ตัดสินใน Transaction เดียวกับการตอบรับ
  * ชั้นลงมือ: `orchestrator.recompute(db: Session, case_id: int) -> CaseStatus` ล็อกเคสแบบเดียวกับ `resume()` ถ้าเคสอยู่ใน `AUTOMATION_STOPPED_STATUSES` (`RESOLVED`, `UNRESOLVED`, `FAILED`, `MANUAL_HANDOFF`) ไม่ทำอะไร คืนสถานะเดิม เพราะ `recompute()` ไม่เดินเส้นออกของเคสที่หยุดแล้ว (T8 และ T9 เดินโดย Route ที่ Head Nurse กด หรือโดยขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด ข้อ 6.12) นอกนั้นโหลดข้อมูลมาสร้าง `CaseFacts` ถ้าสถานะที่ได้เท่าเดิมไม่เขียนอะไร ถ้าต่างจึงเปลี่ยนสถานะผ่าน `assert_transition()` เขียน `CASE_STATUS_CHANGED` แล้วเดินต่อถ้าสถานะใหม่ไม่ใช่จุดรอ Commit เหมือน `resume()`
  * **ที่อยู่ของโค้ด (PR S):** ชั้นตัดสินอยู่ใน `domain/workflow/case_status.py` พร้อม `gap_closed(*, headcount_gap, role_gaps, skill_gaps, fillers)` ซึ่งตัดสินว่า "Gap ถูกปิด" โดยคนหนึ่งคนนับให้จำนวนคน, Role ของเขา และทุก Skill ที่เขามี ส่วนการอ่าน DB มาสร้าง `CaseFacts` อยู่ใน `services/case_facts_service.py` (`load_case_facts()`) อ่านอย่างเดียว ไม่ Flush ไม่ Commit ไม่ล็อก และปิด Autoflush ระหว่างอ่านเอง จึงไม่ส่งงานค้างของผู้เรียกลง DB ไม่ว่า Session ตั้งค่าแบบไหน Offer และ Plan ถูกอ่านเฉพาะตอน Gap ยังไม่ถูกปิด
  * **ใครนับเป็นอะไร:** "ได้เข้าเวรแล้ว" = คำขออนุมัติของเคสนี้ที่อนุมัติแล้ว และผู้สมัครมีแถว Roster แบบ `REPLACEMENT` ในเวรที่เสนอ ที่สถานะเป็น `ASSIGNED` หรือ `COMPLETED` (อนุมัติแล้วแต่ไม่มีแถว Roster ไม่นับ แถวที่ `CANCELLED` ไม่นับ) "รออนุมัติ" = คำขอของเคสนี้ที่ `is_pending = true` และมี Offer ACCEPTED ของเคส / Item เดียวกัน สำรองที่ตอบรับแล้วแต่ยังไม่มีคำขออนุมัติไม่นับทั้งสองกลุ่ม Gap ที่เทียบคือแถว `STAFFING_GAP` ของเคสเอง ผ่าน `gap_service.get_case_gap()` (Q19)
  * **ข้อจำกัดที่รู้ของการนับ:** (1) `ROSTER_ASSIGNMENT` ไม่มีคอลัมน์ที่ชี้ไปเคส แถว `REPLACEMENT` ของคนเดียวกันในเวรเดียวกันที่เส้นทางอื่นสร้าง จึงถูกนับให้เคสนี้ด้วย ตราบที่เคสนี้อนุมัติคนนั้น (2) Role และ Skill ของผู้สมัครอ่านค่าปัจจุบัน แต่ Gap เป็นค่าที่จดไว้ตอนเปิดเคส ถ้ามีคนแก้ Role หรือ Skill ของคนที่เข้าเวรแล้วกลางเคส Gap ของเคสเปิดใหม่ได้และเคสจะส่ง Wave เพิ่ม ไม่ทำให้เคส `FAILED` รอบ 1 ไม่มี Route แก้ Role หรือ Skill ของพนักงาน
  * **Offer ที่ถูกพักในโค้ด:** `case_facts_service.staff_waiting_on_another_case(db, case_id, staff_ids)` คืนผู้สมัครที่มี Offer `ACCEPTED` บนเคสอื่นที่ยังไม่อยู่ใน `AUTOMATION_STOPPED_STATUSES` โดย Offer นั้นยังไม่มีคำขออนุมัติที่ตัดสินแล้ว (ไม่ว่าอนุมัติหรือไม่อนุมัติ) และยังไม่มีผล Safety ที่ไม่ผ่าน (ครอบคลุมคนที่กำลังตรวจ Safety, รออนุมัติ และสำรอง) Offer `SENT` ของคนกลุ่มนี้ไม่นับเป็น Offer ค้าง ฟังก์ชันนี้ไม่พึ่งว่าเคสอื่นตั้ง Offer เป็น `CANCELLED` แล้วหรือยัง ถ้าการเขียนนั้นหลุด ผู้สมัครที่ถูกปัดตกก็ยังกลับมากดรับ Offer นี้ได้ PR 2b ใช้ฟังก์ชันเดียวกันนี้ตอบ `409` เมื่อผู้สมัครกดรับ Offer ที่ถูกพัก และ PR O ใช้ใน Job เก็บตก Offer SENT ที่เลย deadline ไม่ถูกนับเป็น Offer ค้างหรือ Offer ที่ถูกพักตั้งแต่ PR O ส่วน ACCEPTED ไม่ถูกตรวจ deadline เพราะตอบแล้ว
  * **ความล้มเหลวใน `recompute()`:** ต่างจาก `resume()` ตรงที่ไม่มีสถานะที่ผู้เรียกขอมา สถานะคำนวณภายใต้ Lock ของเคส จึงไม่มีกรณีแพ้ Race ถ้าการอ่านข้อมูลล้มเหลว (เช่น เคสไม่มีแถว Gap) ถือเป็นระบบผิด เคสเป็น `FAILED` ตาม D11 เหมือน Handler ที่พัง งานของผู้เรียกใน Transaction เดียวกันยังอยู่ เคสที่ไม่ได้อยู่ที่จุดรอและไม่ได้หยุด `recompute()` โยน `InvalidTransitionError` โดยไม่แตะเคส เคสที่หยุดแล้ว `recompute()` ไม่อ่านอะไรและไม่เขียนอะไรกับเคส แต่ยัง Commit งานของผู้เรียก (เช่น Job ที่เพิ่งตั้ง Offer เป็น `TIMEOUT`)
  * **PR 2b เรียก `recompute()` กับ Handler จริงแล้ว:** `contact_candidate` ส่ง Wave โดยไม่ติดต่อคนเดิมซ้ำ และเส้นตอบ Offer ตรวจ Safety รายคนด้วย Hard Rules เต็มตั้งแต่ PR 3 PR 4 จัดเวรรายคนใน Transaction ของการอนุมัติและให้ `execute_assignment` ปิดเคสเฉพาะเมื่อคนที่ได้เข้าเวรปิด Gap ครบ Branch รวมต้องผ่าน Test ร่วมกันก่อน merge เข้า staging
  * ผู้เรียก: `outreach_service` (หลังตอบรับ, ปฏิเสธ, Offer หมดเวลา) และ `approval_service` (หลังตัดสิน) เรียก `recompute()` แทนการส่ง `next_status` เอง
  * **เคสอื่นที่ได้รับผลกระทบ:** เมื่อสถานะของผู้สมัครคนหนึ่งเปลี่ยนในเคส X (เขาตอบรับ, เขาหลุดเพราะ Safety ไม่ผ่านหรือไม่ได้รับอนุมัติ, หรือเขาได้เวร) Offer ของเขาในเคสอื่นเปลี่ยนตามไปด้วย คือถูกยกเลิก, เลิกนับเป็น Offer ค้าง หรือกลับมากดรับได้ (ข้อ 6.8) แต่เคสอื่นนั้นไม่มีเหตุการณ์ของตัวเองมาสั่งให้คำนวณสถานะใหม่ ตัวอย่าง: เคส Y รอ A คนเดียว เคส X อนุมัติ A แล้วยกเลิก Offer ของ A ในเคส Y เคส Y จะค้างที่ `WAITING_RESPONSE` โดยไม่มี Offer ค้าง กติกา: หลัง Transaction ของเคส X Commit แล้ว ผู้เรียกเรียก `recompute()` ให้เคสอื่นทุกเคสที่ผู้สมัครคนนั้นมี Offer ที่ยัง `SENT` หรือเพิ่งถูกยกเลิกใน Transaction นั้น ทีละเคส เคสละ Transaction เรียงตาม `case_id`
  * **Job เก็บตก:** การเรียก `recompute()` ให้เคสอื่นเกิดหลัง Commit ถ้าระบบล่มตรงช่วงนั้น การเรียกจะหายไป ทุกรอบของ Job (ข้อ 3.8) จึงเรียก `recompute()` ให้เคสที่อยู่ `WAITING_RESPONSE`, ไม่มี Offer ค้าง (ไม่มี Offer ที่กดรับได้ตอนนี้) และเข้าเงื่อนไขข้อใดข้อหนึ่ง
    * เคสไม่มี Offer ที่เป็น `SENT` เหลือเลย
    * เคสมีแต่ Offer ที่ถูกพัก และใน Plan ยังมีผู้สมัครที่เคสนี้ยังไม่เคยส่ง Offer ให้
  * ตัวอย่างของเงื่อนไขข้อสอง: เคส Y ส่ง Offer ให้ A และยังมี B ที่ติดต่อได้ A กดรับเคส X ทำให้ Offer ของเคส Y ถูกพัก เคส X Commit แล้วระบบล่มก่อนเรียก `recompute()` ของเคส Y พอระบบกลับมา Job เจอเคส Y ตามเงื่อนไขข้อสอง เคส Y จึงส่ง Wave ให้ B ได้โดยไม่ต้องรอ Offer ของ A หมดเวลา
  * Job ไม่ยกเลิก Offer ที่ถูกพัก และไม่ทำให้เคสไป `MANUAL_HANDOFF` ก่อนเวลา เพราะ `contact_candidate` ยังตรวจตามลำดับเดิม (ข้อ 6.6 ขั้นที่ 6) เคสที่มีแต่ Offer ที่ถูกพักและไม่เหลือผู้สมัครที่ยังไม่เคยติดต่อ ไม่เข้าเงื่อนไขของ Job เพราะกำลังรออย่างถูกต้อง
  * ถ้าผู้สมัครที่เหลือถูกข้ามทั้งหมดในรอบนั้น (ไม่ผ่าน Hard Rules หรือเต็มเพดาน Offer) เคสกลับมารอที่ `WAITING_RESPONSE` และ Job ลองใหม่รอบถัดไป จนกว่าจะส่งได้หรือ Offer ที่ถูกพักหมดเวลา (ไม่เกินอายุของ Offer ข้อ 6.9)
  * `MANUAL_HANDOFF` กับ T7 ไม่ได้มาจาก `decide_status()` Handler `contact_candidate` เป็นคนตัดสินตอนเคสอยู่ `OUTREACH` เพราะต้องตรวจ Hard Rules ของผู้สมัครก่อนจึงรู้ว่าเหลือใคร ตอนไม่เหลือผู้สมัคร Handler ตรวจตามลำดับ: มีคนรออนุมัติที่เติม Gap ได้ → `WAITING_APPROVAL` (T7), มี Offer ที่ถูกพักและยังไม่หมดเวลา → `WAITING_RESPONSE`, ไม่มีทั้งสองอย่าง → `MANUAL_HANDOFF` (T5)
* **Safety ไม่เป็นขั้นของเคสแล้ว** `safety_service.validate_accepted_candidate(db, case, outreach_id=)` ถูกเรียกจาก `outreach_service.promote_reserves()` ใน Transaction ของการตอบรับ ไม่มี Handler ที่ Orchestrator เรียกตามสถานะ (`handlers/validate_safety.py` ลบแล้วใน PR 3)
* **การจัดเวรรายคน** อยู่ใน Transaction ของการอนุมัติ Handler ของ `EXECUTING` เหลืองานปิดเคส: ยกเลิก Offer ที่เหลือ แล้วเขียน `CASE_RESOLVED` (Q45)
* T5 กับ T6: Handler คืน `MANUAL_HANDOFF` พร้อม `wait = False` รอบถัดไปของลูปเห็นว่าอยู่ใน `AUTOMATION_STOPPED_STATUSES` แล้วหยุดเอง ต้องเพิ่ม Test ยืนยัน
* `_MAX_STEPS`: เส้น T1 กับ T4 เข้า `OUTREACH` ซึ่งจบได้สามทาง คือ `WAITING_RESPONSE`, `WAITING_APPROVAL` (T7) หรือ `MANUAL_HANDOFF` ทั้งสามเป็นจุดรอหรือจุดหยุด จึงไม่วนไม่จบ ต้องเพิ่ม Test
* คำขออนุมัติที่ค้างกัน `MANUAL_HANDOFF` ไว้ (ข้อ 5.1 ลำดับการตัดสิน และ T7) `contact_candidate` ต้องเช็กคนรออนุมัติก่อนคืน `MANUAL_HANDOFF`

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
def recompute(db: Session, case_id: int) -> CaseStatus       # รอบ 1 (PR S)

HANDLERS: dict[CaseStatus, Handler]      # State อัตโนมัติ → Handler ที่รันใน State นั้น
```

* `advance()` ใช้หลังสร้างเคส (`merge_window_service` ตอน Window ปิด) เดินจาก State ปัจจุบัน ถ้าเคสอยู่ที่จุดรอหรือ State ที่หยุดแล้วจะไม่ทำอะไร
* `resume()` ใช้ออกจากจุดรอ: ตรวจ Transition, เปลี่ยน State, บันทึก `CASE_STATUS_CHANGED` แล้วเดินต่อเหมือน `advance()`
  ถ้าเคสไม่ได้อยู่ที่จุดรอหรือ Transition ไม่ถูกต้อง จะโยน `InvalidTransitionError` โดยไม่แตะเคสและ**ไม่**ทำให้เคสเป็น `FAILED`
  (เกิดเมื่อสองคำขอของเคสเดียวกันมาพร้อมกัน เช่น กด `ACCEPT` หรือกดอนุมัติสองครั้งติดกัน) Route ควรตอบ `409`
  `resume()` ไม่รับ `next_status = FAILED` เช่นกัน เพราะ `FAILED` ตั้งได้จากเส้นทาง D11 ของ Orchestrator เท่านั้น
  ก่อนตรวจ `resume()` จะ Flush งานที่ผู้เรียกค้างไว้ (เช่น แถว Outreach และ Audit `OFFER_ACCEPTED`) ดังนั้นเมื่อได้ `InvalidTransitionError`
  ผู้เรียก**ห้าม Commit** ให้ตอบ `409` แล้วปล่อยให้ Session Rollback (`get_db` ปิด Session ซึ่ง Rollback ให้อยู่แล้ว)
* ล็อกแถวของเคสด้วย `SELECT ... FOR NO KEY UPDATE` คำขอที่สองของเคสเดียวกันจะรอจนรอบแรกจบ
  (ไม่ใช้ `FOR UPDATE` เพราะแถว Audit ที่ผู้เรียก Insert ไว้ก่อนถือ Lock `KEY SHARE` บนเคสผ่าน FK สองคำขอแบบนี้จะ Deadlock กัน)
* ลำดับ Lock ทั้งระบบอยู่ข้อ 6.11 แถว `STAFF` มาท้ายสุดเสมอและล็อกเรียงตาม `id` ห้ามโค้ดใหม่ล็อก `STAFF` ก่อนแล้วค่อยล็อกเคสหรือเวร ไม่งั้นจะ Deadlock
* PR 2b เรียก `recompute(..., prepare=promote_reserves)` preparation callback รันใน Savepoint ของ D11 ก่อนคำนวณสถานะ เพื่อให้ Safety รายคนล้มเหลวแล้วคงคำตอบของผู้สมัครไว้และบันทึกเคสเป็น `FAILED` ได้ callback ห้าม Commit หรือเปลี่ยนสถานะเคสเอง
* `recompute()` (มีแล้วตั้งแต่ PR S เส้นทางตอบ Offer และการแจ้งเคสอื่นเรียกแล้วใน PR 2b) ใช้ออกจากจุดรอในรอบ 1 แทนการที่ผู้เรียกส่ง `next_status` เอง: ล็อกเคสแบบเดียวกับ `resume()` คำนวณสถานะจาก Gap ที่เหลือและ Offer ที่ค้าง แล้วเปลี่ยนสถานะผ่านตารางของข้อ 5 เคสที่อยู่ใน `AUTOMATION_STOPPED_STATUSES` ไม่ถูกแตะ กติกาเต็มอยู่ข้อ 5.3
* ไม่มีเคส ID นั้น โยน `CaseNotFoundError`
* D11 ทำด้วย Savepoint: รอบที่พังถูก Rollback กลับไปที่จุดเริ่มรอบ งานที่ผู้เรียกทำไว้ก่อนใน Transaction เดียวกัน
  (Event, เคส, คำตอบของผู้สมัคร) ยังอยู่ จากนั้นเคสเป็น `FAILED` พร้อม `CASE_STATUS_CHANGED` และ `WORKFLOW_FAILED`
  (payload: `from`, `failed_at`, `error_type` ไม่เก็บข้อความ Error เพราะอาจมีข้อมูลต้องห้าม) แล้ว Commit
* `advance()`, `resume()` และ `recompute()` **ไม่โยน** Exception ของ Handler ต่อ ผู้เรียกดูผลจาก `case.status` รายละเอียดอยู่ใน Log ของ Server
  ยกเว้นกรณีเดียว: ถ้าการบันทึก `FAILED` เองล้มเหลว (เช่น ไม่มี Actor `workflow_orchestrator`) Exception นั้นจะหลุดออกมาและไม่มีอะไรถูก Commit
* ผู้เรียกไม่ต้อง Commit ก่อนเรียก และไม่ต้อง Commit หลังเรียก Orchestrator Commit ให้ทั้ง Transaction

* เดินต่อจนเจอจุดรอหรือ State สิ้นสุด แล้ว Commit
* ตรวจ `next_status` ของ Handler กับ `domain/workflow/transitions.py` ก่อนเปลี่ยน State (ตารางเดียวของข้อ 5)
* ทุกการเปลี่ยน State: บันทึก `CASE_STATUS_CHANGED` ด้วย Actor `workflow_orchestrator`
* ห่อทั้งรอบด้วย try/except ตาม D11

### 6.3 Audit Service

```python
# services/audit_service.py
def log(db: Session, *, case_id: int | None, event_id: int | None = None,
        actor_id: int, action: AuditAction, entity_type: EntityType,
        entity_id: int | None, payload: dict) -> None
```

```python
# services/actor_service.py
def component_id(db: Session, name: ActorName) -> int        # Actor ที่ไม่ใช่คน
def user_id(db: Session, staff_id: int) -> int               # Actor ของพนักงาน
```

* `component_id()` รับเฉพาะ `ActorName` และทั้งสองฟังก์ชันโยน `ActorNotFoundError` เมื่อไม่มี Actor (Seed ไม่ครบ) ไม่คืน `None`
* `actor_service` และ `get_demo_user` อ่านด้วย SELECT และ `SessionLocal` ปิด autoflush แถว `ACTORS` / `STAFF` ที่เพิ่งเพิ่มใน Session เดียวกันต้อง `db.flush()` ก่อนจึงจะหาเจอ
* `log()` **ห้าม Commit เอง**
* `log()` รับ `event_id` สำหรับแถว Audit ที่เป็นเรื่องของ Event (ข้อ 3.7) ไม่ส่งมา = `NULL` ผู้เรียกเดิมจึงไม่ต้องแก้ แถวหนึ่งมีได้แค่ `case_id` หรือ `event_id` อย่างใดอย่างหนึ่ง ส่งทั้งสองโยน `ValueError`
* `action` และ `entity_type` ต้องเป็น Enum ห้ามพิมพ์ข้อความเอง
* `payload` ห้ามมีข้อมูลผู้ป่วยรายบุคคล เหตุผลการลาแบบข้อความอิสระ หรือ `password_hash`
* Composite Key (เช่น `STAFF_SKILL`) ยังไม่ต้อง Audit ใน Skeleton จึงยังไม่ต้องตัดสินรูปแบบ `entity_id`

### 6.4 จุดส่งต่อระหว่างขั้น (Seam)

แต่ละขั้นหาแถวที่ขั้นก่อนหน้าเขียนไว้ตามกติกานี้ เพื่อให้ทำขนานกันได้โดยไม่ต้องรอโค้ดของกัน

* ที่เขียนว่า **หนึ่งแถวพอดี** ถ้าเจอ 0 แถวหรือหลายแถวถือเป็น Error ห้ามหยิบแถวแรกมาใช้เงียบ ๆ
  ใน Handler ให้โยน Exception (D11 เปลี่ยนเป็น `FAILED`) ใน Route ให้ตอบเป็น HTTP Error
* Model ยังไม่มี ORM `relationship()` สักตัว ให้โหลดหรือ Join ผ่านคอลัมน์ FK เช่น โหลด `CANDIDATE_PLANS` จาก `item.plan_id`
* "ล่าสุด" หมายถึง `id` มากสุดเสมอ ห้ามเรียงด้วยคอลัมน์เวลา เพราะ Clock ของ Demo หยุดนิ่งหลัง Reset ทุกแถวจึงมีเวลาเท่ากัน

| # | Seam | เจ้าของ | กติกา |
|---|---|---|---|
| 1 | Plan ล่าสุด | คน 2 → คน 3 | `CANDIDATE_PLANS` ที่ `case_id = case.id` เรียง `id` จากมากไปน้อย เอาแถวแรก ไม่เจอ → Error Plan เก็บผู้สมัครทุกคนที่ผ่าน Hard Rules ตอน Solver รัน ไม่ใช่เฉพาะกลุ่มของ Wave แรก และ Solver รันครั้งเดียวต่อเคส (Q37) |
| 2 | Plan → Outreach | คน 3 | `contact_candidate` เลือกคนของ Wave ตามข้อ 6.6 แล้วส่ง Offer ทุกคนพร้อมกัน แทนกติกาเดิมที่ส่งให้ `rank = 1` คนเดียว |
| 3 | Respond | คน 3 | ผู้ตอบคือ `user.staff.id` จาก `X-Demo-User` Body ส่ง `outreach_id` ของ Offer ที่เห็น ตอบได้ทั้ง `ACCEPT` และ `REJECT` การตรวจและคำตอบอยู่ข้อ 9.2 แถวที่เขียนอยู่ข้อ 6.10 ลำดับ Lock อยู่ข้อ 6.11 จบด้วยการเรียก `orchestrator.recompute()` |
| 4 | Outreach → Safety | คน 3 → คน 2 | Safety รับ `outreach_id` ของคนที่เพิ่งตอบรับ และตรวจใน Transaction ของการตอบรับ ไม่ค้นจากเคส เพราะเคสมี Offer `ACCEPTED` ได้หลายแถว `get_accepted_outreach()` ที่ต้องการหนึ่งแถวพอดีจึงลบแล้วใน PR 3 ตัวตรวจและสิ่งที่ Safety บันทึกอยู่ร่างรอบ 1 ข้อ 7.3 และ 7.4 |
| 5 | Safety → Approval Request | คน 2 (PR 3) | Safety ผ่าน: `safety_service` เรียกฟังก์ชันสร้างคำขอใน `approval_service` (`create_request(db, *, case, item)`) ซึ่งสร้าง `APPROVAL_REQUEST` หนึ่งแถวของผู้สมัครคนนั้น และเขียน `APPROVAL_REQUESTED` ใน Transaction ของการตอบรับ PR 3 เป็นคนย้ายโค้ดนี้ออกจาก `safety_service` และ Handler `validate_safety` (ไฟล์ `approval_service` เป็นของคน 3 แจ้งก่อนแก้) PR 4 ไม่ต้องทำส่วนนี้ `case_id` = เคสนั้น `candidate_item_id` = Item ของ Outreach ที่ตอบรับ โหลด Plan จาก `item.plan_id` แล้วตรวจ `plan.case_id == case.id` (FK สองตัวไม่ได้รับประกันข้อนี้) ตั้ง `approval_mode = MANUAL`, `required_approver_role` = `id` ของ Role ชื่อ `HEAD_NURSE` (ค้นด้วยชื่อ), `is_pending = true`, `requested_at = clock.now()` Safety ไม่ผ่าน: ไม่สร้าง Request และ Offer ของคนนั้นเป็น `CANCELLED` ผ่านฟังก์ชันเดียวใน `outreach_service` (Q8) |
| 6 | รายการรออนุมัติ | คน 3 | `GET /approvals?pending=true` คืนแถวที่ `is_pending = true` เฉพาะเคสที่ไม่อยู่ใน `AUTOMATION_STOPPED_STATUSES` เรียงด้วย `id` จากน้อยไปมาก เคสหนึ่งมีได้หลายแถว หนึ่งแถวต่อผู้สมัคร |
| 7 | Decide | คน 3 | ตรวจตามลำดับเดิม: ไม่มี Request ID นั้น → `404`; `user.staff.role_id != required_approver_role` → `403` (`get_demo_user` ไม่ตรวจ Role ดูข้อ 9); ไม่ได้ Pending → `409` กติกาเพิ่มของรอบ 1 อยู่ข้อ 9.2: เคสที่หยุดแล้วตอบ `409` และไม่อนุมัติต้องมี `reason` ตัดสินทีละคน บันทึกผลตามข้อ 6.10 แล้วเรียก `orchestrator.recompute()` |
| 8 | Approval → Roster | คน 3 | อนุมัติแล้วสร้าง Roster ของคนนั้นใน Transaction เดียวกับการอนุมัติ จาก Item ของ Request: `staff_id = item.staff_id`, `shift_id = item.proposed_shift_id`, `status = ASSIGNED`, `assignment_type = REPLACEMENT`, `candidate_source = item.source` ไม่ตรวจ Hard Rules ซ้ำ (Q38) จากนั้นยกเลิก Offer ของคนนั้นในเคสอื่นที่ขัดกับเวรใหม่ (ข้อ 6.8) Handler ของ `EXECUTING` เหลืองานปิดเคส |
| 9 | Timeline | คน 1 | `GET /cases/{id}/audit` แถวที่ `case_id` เป็นเคสนี้ รวมกับแถวที่ `event_id` เป็น Event ของเคสนี้ เรียงด้วย `id` (ข้อ 3.7) |
| 10 | Requirement ของเวร | คน 1 (รับ Event + Gap) | `STAFFING_REQUIREMENTS` ที่ `shift_id` ของเวรนั้น เรียง `id` จากมากไปน้อย เอาแถวแรก ไม่เจอ → Error ตารางนี้ไม่มี Unique ที่ `shift_id` จึงมีหลายเวอร์ชันได้ (Seed มีเวรละแถว) การปิด Window และ `assess_staffing` ต้องโหลดผ่าน**ฟังก์ชันเดียวกัน** เพื่อให้เห็น Requirement ตัวเดียวกันเสมอ แถว Gap เก็บ `id` นี้ใน `staffing_requirement_id` |
| 11 | Gap → Solver | คน 1 → คน 2 | `gap_service.get_case_gap(db, case_id)` คืน `CaseGap` (`gap`, `headcount_gap`, `role_gaps`, `skill_gaps` เป็น Dict จาก ID ไป `gap_count` เฉพาะตัวที่ขาด) ไม่เจอแถว → `GapNotFoundError` ฟังก์ชันนี้อ่าน `STAFFING_GAP` ของเคสที่ `id` มากสุด พร้อมแถว Role / Skill ที่ `gap_count > 0` ให้ Solver และ Safety เรียก ไม่เขียน Query เอง รายละเอียดอยู่ร่างรอบ 1 ข้อ 8.3 |
| 12 | Hard Rules ของผู้สมัคร | คน 2 → คน 3, คน 2 | Loader ตัวเดียวของตัวตรวจ (ร่างรอบ 1 ข้อ 7.2 Q55) อยู่ที่ `services/hard_rule_service.py` Solver เรียก `check_staff(db, shift=, staff_ids=)` การเลือกคนของ Wave และ Safety เรียก `check_items(db, shift=, items=)` ทั้งสองคืน `CandidateCheck` (`context`, `result`) ต่อคน โดย `result.failed_rules` ว่าง = ผ่าน `check_items` อ่าน `CANDIDATE_ITEM_TARGET` ของ Item เอง: `target_skill_ids` = Skill ของแถว `SKILL`, `target_role_ids` = Role ของแถว `ROLE` ถ้าไม่มีแถว `ROLE` ใช้ Role ของ Requirement ปัจจุบันของเวร (Seam 10) ฟังก์ชันอ่านอย่างเดียว ไม่ Flush / Commit ผู้เรียกต้อง Flush ก่อน และไม่ตรวจเพดาน Offer (ข้อ 6.7) การล็อกแถว `STAFF` ใช้ `hard_rule_service.lock_staff(db, staff_ids)` |
| 13 | Target ของผู้สมัคร | คน 2 → คน 3 | `domain/staffing/wave_targets.py`: `wave_target(gap)` = `ceil(gap * 11 / 10)` และ `fill_targets(headcount_gap=, role_gaps=, skill_gaps=, candidates=)` เลือกคนตามลำดับการเติมในร่างรอบ 1 ข้อ 8.3 โดย `candidates` เรียงตามลำดับที่ผู้เรียกต้องการ (Solver ใช้ `ranking_key`, `contact_candidate` ใช้ `rank`) คืน `staff_id` → รายการ `TargetCredit` ผู้เขียนแถวเรียก `optimization_service.record_item_targets(db, item, credits)` ซึ่ง Flush แต่ไม่ Commit Solver เขียนให้กลุ่มของ Wave แรก `contact_candidate` เขียนให้ทุกคนที่มันเลือกเอง แถวไม่เปลี่ยนหลังส่ง Offer ครั้งแรก ถ้าสมาชิก Solver ถูกข้ามใน Wave แรกแล้วถูกเลือกใน Wave ถัดไป ให้แทนที่ Target ชั่วคราวด้วย Target ของ Wave ที่เลือกเขาก่อนส่ง |
| 14 | Working Time Snapshot | คน 2 | `working_time_service.capture(db, staff_ids, captured_at=)` เป็นผู้เขียน `STAFF_WORKING_TIME_SNAPSHOT` จุดเดียว เขียนแถวใหม่ทุกครั้งที่ Solver รัน หนึ่งแถวต่อคนใน Plan ใช้ `captured_at = clock.now()` ค่าเดียวทั้งรอบ `CANDIDATE_ITEMS.working_time_snapshot_id` ชี้แถวที่ใช้จัดอันดับ ความหมายของแต่ละคอลัมน์อยู่ `docs/database-schema.md` ข้อ 20 |

### 6.5 คอลัมน์เวลา

คอลัมน์ที่บันทึกว่าขั้นนั้นทำงานเมื่อไร ต้องใส่ค่า `clock.now()` เองโดยขั้นที่เขียนแถว ห้ามใช้ `datetime.now()` (D10)

| คอลัมน์ | Null | ใครใส่ | ถ้าลืม |
|---|---|---|---|
| `STAFFING_GAP.computed_at` | NOT NULL | Gap | `IntegrityError` → เคส `FAILED` |
| `CANDIDATE_PLANS.generated_at` | NOT NULL | Solver | `IntegrityError` → เคส `FAILED` |
| `STAFF_WORKING_TIME_SNAPSHOT.captured_at` | NOT NULL | `working_time_service` (ค่าเดียวกับ `generated_at` ของ Plan) | `IntegrityError` → เคส `FAILED` |
| `SAFETY_VALIDATION.validated_at` | NOT NULL | Safety | `IntegrityError` → เคส `FAILED` |
| `APPROVAL_REQUEST.requested_at` | NOT NULL | `approval_service.create_request()` | `IntegrityError` → เคส `FAILED` |
| `CANDIDATE_OUTREACH.sent_at` | NULL | Outreach | ไม่ Error แต่ข้อมูลหาย |
| `CANDIDATE_OUTREACH.response_at` | NULL | Respond | ไม่ Error แต่ข้อมูลหาย |
| `CANDIDATE_OUTREACH.expires_at` | NULL | Outreach (PR O) | NULL ได้ในแถวที่ยังไม่ส่งหรือประวัติที่ไม่มี sent_at; ประวัติที่มี sent_at backfill เป็น sent_at + 300 วินาทีด้วย; SENT ต้องมี deadline (CHECK) ส่วน ACCEPTED ไม่หมดเวลาแม้พ้น deadline |
| `APPROVAL_REQUEST.decided_at` | NULL | Decide | ไม่ Error แต่ข้อมูลหาย |

คอลัมน์เวลาอีกสองชนิดไม่ต้องใส่ตามตารางนี้

* `created_at` ใส่ให้เองด้วย `default` และ `updated_at` ด้วย `default` กับ `onupdate`
* คอลัมน์เวลาที่มีความหมายของตัวเองทำตามสเปกของมัน เช่น `STAFFING_CASES.required_replacement_time = SHIFT.start_at`,
  `STAFFING_EVENTS.occurred_at` และเวลาของ `STAFF_UNAVAILABILITY` ตามข้อ 3

### 6.6 การเลือกผู้สมัครของ Wave

เคสเข้า `OUTREACH` เมื่อ Gap ยังไม่ถูกปิดและเคสไม่มี Offer ค้าง (T1, T4 และครั้งแรกหลัง Solver) Handler `contact_candidate` เป็นที่เดียวที่เลือกคนและส่ง Offer

1. **หา Gap ที่ยังเหลือ** = Gap ของเคส (แถว `STAFFING_GAP` ของเคส) หักด้วยคนที่เข้าเวรแล้ว, คนที่รออนุมัติ และสำรองที่ตอบรับไว้
2. **คิด Target** ของ Skill, Role และจำนวนคนจาก Gap ที่เหลือ: `ceil(gap * 11 / 10)` (ร่างรอบ 1 ข้อ 8.3)
3. **อ่านผู้สมัคร** จาก Plan ของเคส เรียงตาม `rank` Plan เก็บผู้สมัครทุกคนที่ผ่าน Hard Rules ตอน Solver รัน ไม่ใช่เฉพาะกลุ่มของ Wave แรก (ร่างรอบ 1 ข้อ 8.3) จึงมีคนเหลือให้ Wave ถัดไป ไม่รัน Solver ใหม่ (Q3, Q37)
4. **ข้ามคนที่ใช้ไม่ได้** และจดเหตุผล
   * เคสนี้ติดต่อไปแล้ว: Offer เป็น `REJECTED`, `CANCELLED`, `TIMEOUT` หรือยัง `SENT` / `ACCEPTED` อยู่ คนกลุ่มนี้ไม่อยู่ใน `skipped` เพราะผลของเขาอยู่ในประวัติ Offer แล้ว
   * ไม่ผ่าน Hard Rules ณ ตอนนี้ (ตัวตรวจเดียวกับ Solver และ Safety ร่างรอบ 1 ข้อ 7) รหัสเหตุผล = รหัสของกฎ
   * ถือ Offer ครบเพดานแล้ว รหัส `OFFER_LIMIT_REACHED` (ข้อ 6.7)
5. **เลือกคนของ Wave**
   * Wave แรก: ใช้กลุ่มที่ Solver เลือก คือคนใน Plan ที่มีแถว `CANDIDATE_ITEM_TARGET` อยู่แล้ว ไม่เลือกใหม่จากทั้ง Plan ถ้าคนในกลุ่มถูกข้ามในขั้นที่ 4 Target ที่เขาถืออยู่จะว่าง ให้เติมเฉพาะ Target ที่ว่างนั้นจากคนที่เหลือใน Plan ตามลำดับในร่างรอบ 1 ข้อ 8.3
   * Wave ถัดไป: เติม Target จากคนที่เหลือใน Plan ตามลำดับในร่างรอบ 1 ข้อ 8.3 จนทุก Target เป็น 0 หรือไม่เหลือผู้สมัคร
   * คนที่ถูกเลือกโดยขั้นนี้ (ไม่ใช่โดย Solver) ต้องได้แถว `CANDIDATE_ITEM_TARGET` ก่อนส่ง Offer Safety จึงมีแถวอ่านทุกคน ไม่ว่าอยู่ Wave ไหน
6. เลือกได้อย่างน้อยหนึ่งคน → ส่ง Offer ทุกคนพร้อมกัน เคสไป `WAITING_RESPONSE` เลือกไม่ได้เลย ตรวจตามลำดับนี้
   * มีคนรออนุมัติที่เติม Gap ได้ → เคสไป `WAITING_APPROVAL` (T7)
   * มี Offer ที่ถูกพักและ`clock.now() < expires_at` → เคสไป `WAITING_RESPONSE` รอผลของเคสที่ผู้สมัครไปรับ หรือรอ Offer หมดเวลา (ข้อ 5.1)
   * ไม่มีทั้งสองอย่าง → `MANUAL_HANDOFF` (T5)

Target ของ Wave, สูตรจัดอันดับ และลำดับการเติม Target อยู่ร่างรอบ 1 ข้อ 8.3

PR 2b เพิ่ม `wave_service.select_wave()` แล้ว: Wave แรกเก็บกลุ่มของ Solver และเติมเฉพาะ Target ที่ว่าง โดย `fill_targets(..., already_selected=...)` ไม่คูณ 1.1 ซ้ำ Wave ถัดไปใช้ Plan เดิม เลข Wave อ่านจาก payload ของ `OFFER_SENT` และผู้ที่เคยติดต่อแล้วไม่อยู่ใน `skipped` เมื่อไม่ผ่านหลายกฎเก็บรหัสแรกตามลำดับของตัวตรวจ แล้วจึงตรวจ `OFFER_LIMIT_REACHED`


### 6.7 เพดาน Offer ต่อคน

PR 2b ลบกฎเดิมที่ตัดคนทันทีเมื่อมี Offer ค้างออกจาก Solver แล้ว ผู้สมัครมีหลาย Offer ได้จนเต็มเพดานด้านล่าง ไม่ใช้รหัส `HAS_OPEN_OFFER`

| หัวข้อ | กติกา |
|---|---|
| กติกาใหม่ | ผู้สมัครถือ Offer ได้พร้อมกันไม่เกิน `OUTREACH_POLICY.maximum_concurrent_offers_per_staff` (Seed = 3) |
| นับอะไร | Offer ของผู้สมัครที่เป็น `SENT` หรือ `ACCEPTED` บนเคสที่ยังเดินอยู่ |
| รหัสตอนข้ามคน | `OFFER_LIMIT_REACHED` |
| อยู่ที่ไหน | `availability_service.staff_at_offer_limit(db, staff_ids) -> set[int]` คืน Set ของคนที่เต็มเพดาน ไม่อยู่ใน `domain/constraints/` เพราะต้อง Query `CANDIDATE_OUTREACH` อ่านอย่างเดียว ไม่ Flush / Commit ผู้เรียกต้อง Flush ข้อมูลที่ต้องการนับก่อนเรียก |
| ใครทำ | คน 3 ใน PR 1c (งาน Outreach เป็นของคน 3): ตาราง `OUTREACH_POLICY`, Seed และฟังก์ชันนี้ Solver เรียกฟังก์ชันนี้ตั้งแต่ PR 2a และ PR 2b ลบ `_staff_with_open_offers()` ออกจาก `optimization_service` แล้ว |
| ใครเรียก | Solver (ตอนสร้าง Plan) และ `contact_candidate` (ขั้นที่ 4 ของข้อ 6.6) |
| Safety ไม่เรียก | ผู้สมัครที่กำลังถูกตรวจมี Offer `ACCEPTED` ของเคสตัวเองอยู่ กติกานี้จึงไม่อยู่ในรายการรหัสของร่างรอบ 1 ข้อ 7.2 |

PR 1c เพิ่ม Model, Migration, Seed และฟังก์ชันนี้ Solver เรียกแล้วตั้งแต่ PR 2a และ `contact_candidate` เรียกแล้วใน PR 2b โดยไม่มีการตัดคนเพียงเพราะมี Offer ค้าง โหลด Policy ด้วย `policy_service.get_outreach_policy(db)` เลือก `id=1` ตาม Seed ไม่ใช้ `effective_from` เลือกเวอร์ชัน และไม่ใช้ค่า Default เมื่อไม่มี Policy การเลือกเวอร์ชันเป็นงานภายหลัง

Migration สร้างตารางว่าง ไม่สร้าง Policy ให้ฐานข้อมูลเดิม หลัง merge PR 1c ให้ `make reset` เพื่อโหลด Policy `id=1` ก่อนใช้งาน

ฟังก์ชันนับแถว Offer ข้ามทุกเคสและทุก Plan ของผู้สมัคร แต่ไม่รวมเคสที่อยู่ใน `AUTOMATION_STOPPED_STATUSES` รวมสำรองที่ `ACCEPTED` ด้วย ผู้เรียกที่กำลังเลือกคนต้องล็อก Staff ตามข้อ 6.11 แล้วตรวจเพดานอีกครั้งใน Transaction เดียวกัน ฟังก์ชันอ่านนี้ไม่ได้จองสิทธิ์ส่ง Offer เอง

กติกาอื่นของการส่ง Wave

* **Lock:** ตอนเลือกคนของ Wave ล็อกแถว `STAFF` ของผู้สมัครทั้ง Plan แบบเดียวกับ Solver (`FOR NO KEY UPDATE` เรียงตาม `id`) ไม่งั้นสองเคสที่เลือกคนพร้อมกันจะนับเพดานของคนเดียวกันผิด
* **คนที่ถูกข้ามต้องไม่หายเงียบ:** ใส่ `skipped` ใน payload ของ `OFFER_SENT` แถวแรกของ Wave หรือของ `MANUAL_HANDOFF` เมื่อไม่เหลือใคร เป็น List ของ `{staff_id, reason}` โดย `reason` เป็นรหัส (Q5) หน้าเคสอ่านเหตุผลจาก payload นี้ (Q6)
* **ผู้สมัครที่รับของเคสอื่นอยู่:** Offer ของเคสนี้ยัง `SENT` แต่กดรับไม่ได้ และไม่นับเป็น Offer ค้างของเคสนี้ (Q29) เคสจึงส่ง Wave ถัดไปได้โดยไม่รอเขา ถ้าเคสไม่เหลือผู้สมัครให้ส่งแล้ว เคสรอ Offer นี้ที่ `WAITING_RESPONSE` ไม่ไป `MANUAL_HANDOFF` จนกว่า Offer จะหมดเวลาหรือถูกยกเลิก (ข้อ 5.1)

### 6.8 ผู้สมัครถือหลาย Offer พร้อมกัน

ผู้สมัครได้รับ Offer จากหลายเคสพร้อมกัน แล้วเลือกเองว่าจะรับอันไหน จำกัดจำนวนด้วย Policy

| เหตุการณ์ | Offer หอ 1 | Offer หอ 2 |
|---|---|---|
| A ได้รับทั้งสอง Offer | รอตอบ กด Accept ได้ | รอตอบ กด Accept ได้ |
| A รับหอ 2 กำลังตรวจหรือรออนุมัติ | ยัง `SENT` แต่กด Accept ไม่ได้ | `ACCEPTED` |
| หอ 2 ไม่อนุมัติ A | กลับมากด Accept ได้ ถ้า Offer ยังใช้ได้ | `CANCELLED` |
| หอ 2 อนุมัติและสร้าง Assignment สำเร็จ | ยกเลิกถ้าขัดกับ Assignment ใหม่ | `ACCEPTED` และมี Assignment |

| เรื่อง | กติกา |
|---|---|
| ตอบรับพร้อมกันสองแท็บ | ล็อกแถว `STAFF` ของผู้สมัครทั้ง Plan ตามลำดับในข้อ 6.11 แล้วตรวจซ้ำก่อนรับ |
| รับหอ 2 แล้วหอ 2 ไม่อนุมัติ | หอ 1 ไม่ต้องส่ง Offer ใหม่ Offer เดิมของหอ 1 กลับมากดได้ |
| เมื่อไหร่ยกเลิก Offer ของหอ 1 | ไม่ยกเลิกตอน A กดรับหอ 2 ยกเลิกหลังหอ 2 จัดเวรให้ A สำเร็จ และเฉพาะ Offer ที่ขัดกับ Assignment ใหม่ |
| "ขัดกัน" | ใช้ Hard Rules ชุดเดียวกัน: เวลาทับ, พักไม่พอ, ชั่วโมงรวมเกิน ไม่ใช่แค่เวลาทับ |
| สิ่งที่ผู้สมัครเห็น | หอ, เวร, เส้นตาย และเหตุผลที่ยกเลิก เส้นตายแสดงด้วย `expires_at` แล้วตั้งแต่ PR O |
| จำกัดจำนวน | ตารางใหม่ `OUTREACH_POLICY` |

คอลัมน์ของ `OUTREACH_POLICY` อยู่ใน `docs/database-schema.md`

### 6.9 Timeout ของ Offer

PR O ตามรีวิว: recovery อ่าน facts โดยไม่ล็อกก่อน แล้วล็อกและตรวจซ้ำเฉพาะเคสที่ดูค้าง; healthy waits ไม่ล็อก Offer/Case/Staff ทุก tick. Lock retry ครบ 5 รอบตอบ `503` พร้อม `Retry-After: 1` แยกจาก Offer conflict `409`; ผู้เรียก lock helper ต้องไม่มี uncommitted writes เพราะ retry rollback. เคสสถานะเก่าที่ไม่ใช่ wait/stopped ยังปิด Offer เป็น TIMEOUT พร้อม audit ได้ แต่ไม่เรียก recompute หรือเปลี่ยนสถานะเคส และ log ให้ซ่อมด้วยมือ. ความล้มเหลวซ้ำ log stack trace ครั้งแรกและทุก 120 ครั้งต่อ operation/case/exception type (counter ใน process จำกัด 1,024 entries; ล้างเมื่อสำเร็จ).



Offer มี Timeout ส่วนการอนุมัติ**ไม่มี** Timeout หรือ Deadline เคสที่รออนุมัติรอจนผู้อนุมัติตัดสิน (Q56) **[รอบ 2 · PR T]** การอนุมัติจะมีเส้นตาย กติกาอยู่ข้อ 6.13 ประโยคนี้ยังตรงกับโค้ดจนกว่า PR T จะเข้า

| หัวข้อ | กติกา |
|---|---|
| ค่าระยะเวลา | คอลัมน์ `OUTREACH_POLICY.offer_timeout_seconds` (integer, NOT NULL, CHECK > 0) Seed = 300 วินาที |
| เวลาหมดอายุของแต่ละ Offer | คอลัมน์ใหม่ `CANDIDATE_OUTREACH.expires_at` ตั้งตอนส่ง = `sent_at` + ค่าใน Policy ไม่เปลี่ยนทีหลัง Offer ใน Wave เดียวกันจึงหมดพร้อมกัน |
| หมดเวลาแล้วยังไม่ตอบ | Offer ที่ยัง `SENT` เป็น `TIMEOUT` เขียน `OFFER_TIMEOUT` หนึ่งแถวต่อ Offer แล้วคำนวณสถานะเคสใหม่ (ไม่มี Offer ค้างแล้ว เคสจึงไป `OUTREACH` ส่ง Wave ถัดไป หรือจบตามข้อ 5.1) |
| ผู้สมัครที่ Timeout | นับว่าเคสนี้ติดต่อไปแล้ว ไม่ส่งซ้ำในเคสเดียวกัน (ข้อ 6.6 ขั้นที่ 4) และ SENT ที่พ้น deadline เลิกนับในเพดานทันทีแม้ Job ยังไม่ได้ตั้ง TIMEOUT; ACCEPTED ยังนับตามปกติ |
| Offer ที่กดรับไม่ได้เพราะรับของเคสอื่นค้างอยู่ (Q29) | หมดเวลาตามปกติ ไม่หยุดนาฬิกา |
| Offer ที่ตอบรับแล้ว (รวมสำรอง) | ไม่มี Timeout เพราะตอบแล้ว |
| กดตอบหลังหมดเวลา | ช่วงที่ตอบได้คือ `clock.now() < expires_at`; เท่ากับ deadline ถือว่าหมดเวลาและตอบ `409` ไม่เขียน DB `respond` เทียบ `expires_at` กับ `clock.now()` เอง ไม่รอ Job เพราะ Job รันทุก 30 วินาที ช่วงนั้น Offer ที่เลยเวลาแล้วยังเป็น `SENT` การเปลี่ยนเป็น `TIMEOUT` ยังเป็นหน้าที่ของ Job ที่เดียว |
| ใครสั่ง | Service ของ Job ตัวเดียวกับ Merge Gap (ข้อ 3) ทุกรอบให้ Backend ปิด Offer ที่หมดเวลา ปุ่มเลื่อน Clock ของ Demo ทำงานเดียวกัน |

* ผลต่อ Demo: Clock ของ Demo เป็นตัวเดียวทั้งระบบ เลื่อน Clock ตั้งแต่ 300 วินาที Offer ที่ยัง `SENT` และส่งไว้ก่อนหน้านั้นจะ `TIMEOUT` ทุกแถว ไม่ว่าเป็นของเคสไหน เรื่องนี้เป็นคนละส่วนกับการปิด Window ซึ่งยังเป็นไปตาม Q43 (Window ปิดเมื่อครบ `merge_window_seconds` และเคสก่อนหน้าของเวรจบแล้ว) Scenario และการสาธิตที่เลื่อน Clock เพื่อปิด Window จึงต้องรู้ว่า Offer ที่ค้างอยู่จะหมดเวลาไปพร้อมกัน

### 6.10 แถวที่แต่ละเส้นทางเขียน

* Seam 4 เดิม (`get_accepted_outreach`) ต้องการ Offer `ACCEPTED` ของเคส **หนึ่งแถวพอดี** ใช้ไม่ได้แล้ว และลบแล้วใน PR 3 เพราะเคสมีคนตอบรับได้หลายคน Safety รับ `outreach_id` ของคนที่เพิ่งตอบรับแทนการค้นจากเคส
* เคสหนึ่งมี `APPROVAL_REQUEST` ที่ค้างได้หลายแถว หนึ่งแถวต่อผู้สมัคร (Q24)
* คนที่ตอบรับแล้วหลุด Offer เป็น `CANCELLED` (Q7) ฟังก์ชันเดียวใน `outreach_service` เป็นคนตั้ง Safety กับ Approval เรียกใช้ (Q8)

| เหตุการณ์ | ตาราง | ค่าที่เขียน | ใครเขียน |
|---|---|---|---|
| ส่ง Wave | `CANDIDATE_OUTREACH` (แถวใหม่ หนึ่งแถวต่อคน) | `status = SENT`, `sent_at = clock.now()` ค่าเดียวกันทั้ง Wave | `outreach_service.send_offer()` (Skeleton รับอันดับ 1 คนเดียว PR 2b แก้ให้รับหลาย Item) |
| ปฏิเสธ | `CANDIDATE_OUTREACH` | `status = REJECTED`, `response_at = clock.now()` | `outreach_service.record_response()` |
| ตอบรับ ตอน Gap ยังไม่ถูกปิดด้วยคนที่ตอบรับก่อนหน้า | `CANDIDATE_OUTREACH` | `status = ACCEPTED`, `response_at` | `record_response()` |
| | `SAFETY_VALIDATION` | หนึ่งแถวของคนนี้ ใน Transaction เดียวกับการตอบรับ (ร่างรอบ 1 ข้อ 7.4) | `safety_service` |
| | `APPROVAL_REQUEST` | แถวใหม่ที่ค้าง เมื่อ Safety ผ่าน | `approval_service` เรียกจาก `safety_service` (Seam 5, PR 3) |
| | `CANDIDATE_OUTREACH` | `status = CANCELLED` เมื่อ Safety ไม่ผ่าน ไม่สร้าง `APPROVAL_REQUEST` | `outreach_service` (Q8) |
| ตอบรับ ตอน Gap ถูกปิดครบแล้ว (สำรอง) | `CANDIDATE_OUTREACH` | `status = ACCEPTED`, `response_at` อย่างเดียว ยังไม่ตรวจ Safety (Q28) | `record_response()` |
| ตอบรับ แต่ผู้ตอบรับของเคสอื่นค้างอยู่ | ไม่เขียน | ตอบ `409` (Q39) | |
| อนุมัติ | `APPROVAL_REQUEST` | `approver_id`, `is_approved = true`, `is_pending = false`, `decided_at` | `approval_service.decide()` |
| | `ROSTER_ASSIGNMENT` | แถว `REPLACEMENT` ของคนนั้น ใน Transaction เดียวกัน ไม่ตรวจซ้ำ (Q27, Q38) | `roster_service` |
| | `CANDIDATE_OUTREACH` ของคนนั้นในเคสอื่น | `status = CANCELLED` เฉพาะ Offer ที่ขัดกับเวรใหม่ตาม Hard Rules (ข้อ 6.8) | `outreach_service` |
| ไม่อนุมัติ | `APPROVAL_REQUEST` | `approver_id`, `is_approved = false`, `is_pending = false`, `reason`, `decided_at` | `approval_service.decide()` |
| | `CANDIDATE_OUTREACH` (ของคนที่ไม่ได้รับอนุมัติ) | `status = CANCELLED` | `outreach_service` (Q8) |
| | สำรองคนแรก (ถ้ามี) | เข้า Safety ต่อ เขียนแบบเดียวกับแถว "ตอบรับ" | `safety_service` |
| Gap ถูกปิด (เคสผ่าน `EXECUTING`) | `CANDIDATE_OUTREACH` ของเคสที่ยัง `SENT` และ `clock.now() < expires_at` และของสำรอง; SENT ที่หมดเวลาคงไว้ให้ Job | `status = CANCELLED` | Handler ของ `EXECUTING` ผ่าน `outreach_service` |
| Offer หมดเวลา | `CANDIDATE_OUTREACH` ที่ยัง `SENT` และ `clock.now() >= expires_at` | `status = TIMEOUT`, `response_at` คงเป็น NULL (ข้อ 6.9) | `offer_timeout_service` เรียกจาก Job |
| เคสเข้า `MANUAL_HANDOFF` (T5) | `CANDIDATE_OUTREACH` ของเคสที่ยัง `SENT` เฉพาะแถวที่ยังไม่หมดเวลา; แถวที่ถึงหรือเลย deadline คงไว้ให้ Job ตั้ง `TIMEOUT` พร้อม audit (ข้อ 5.1) | `status = CANCELLED` เพราะระบบอัตโนมัติไม่เดินเคสต่อจาก `MANUAL_HANDOFF` | `contact_candidate` ผ่าน `outreach_service` |
| Solver ไม่ได้ใครเลย (T6) | ไม่มีแถวใหม่นอกจาก Audit | | Handler |

### 6.11 ลำดับ Lock

ลำดับเดิมทั้งระบบ: `SHIFT` / `ROSTER_ASSIGNMENT` → `APPROVAL_REQUEST` หรือ `CANDIDATE_OUTREACH` → เคส → `STAFF`

* **ตอบ Offer:** ล็อก Offer ที่ยังไม่จบของเคสทุกแถว เรียงตาม `id` (รวมของผู้ตอบเอง) → เคส → แถว `STAFF` ของผู้สมัครทั้ง Plan ของเคส ใน Query เดียวที่เรียงตาม `id` แล้วตรวจซ้ำว่าผู้ตอบไม่ได้รับของเคสอื่นค้างอยู่ (ข้อ 6.8) ผู้สมัครที่ตอบรับสองเคสพร้อมกันจึงได้ผลสำเร็จเคสเดียว
  * เหตุผลที่ล็อก Offer ทุกแถวของเคส: คำตอบนี้อาจทำให้เคสเข้า `MANUAL_HANDOFF` ซึ่งยกเลิก Offer ที่ยัง `SENT` ของคนอื่น
  * เหตุผลที่ล็อก `STAFF` ทั้ง Plan ไม่ใช่แค่ของผู้ตอบ: คำตอบนี้อาจทำให้เคสส่ง Wave ถัดไปใน Transaction เดียวกัน ซึ่งต้องล็อก `STAFF` ทั้ง Plan ถ้าถือแถวของผู้ตอบไว้ก่อนแล้วค่อยล็อกที่เหลือ สองเคสที่ใช้ผู้สมัครชุดเดียวกันจะค้างกันได้ เช่น เคส A ถือแถวของ 202 แล้วรอ 201 ส่วนเคส B ถือแถวของ 201 แล้วรอ 202
* **ตัดสินอนุมัติ:** การอนุมัติสร้าง Roster อาจเป็นคนสุดท้ายที่ทำให้ Gap ถูกปิด และต้องยกเลิก Offer ของผู้สมัครคนนั้นในเคสอื่นที่ขัดกับเวรใหม่ จึงล็อกตามลำดับ: `SHIFT` → `APPROVAL_REQUEST` → Offer ที่ยังไม่จบของเคสนี้ทุกแถว **รวมกับ** Offer ที่ยังไม่จบของผู้สมัครคนนั้นในเคสอื่น ล็อกใน Query เดียว เรียงตาม `id` → เคส → `STAFF` ของผู้สมัครทั้ง Plan ของเคส ใน Query เดียวที่เรียงตาม `id` เหตุผลที่ต้องล็อก Offer ก่อนเคสและก่อน `STAFF`: การตอบ Offer ล็อก Offer ก่อนแล้วจึงล็อก `STAFF` ถ้าการอนุมัติถือ `STAFF` ก่อนแล้วไปรอ Offer จะค้างกับผู้สมัครที่กดตอบ Offer นั้นพอดี หลังล็อกครบจึงตรวจว่า Offer ไหนขัดกับเวรใหม่ แล้วยกเลิกเฉพาะแถวนั้น
* **ลำดับย่อยในชั้นเดียวกัน:** `APPROVAL_REQUEST` ก่อน `CANDIDATE_OUTREACH` การตอบ Offer สร้าง `APPROVAL_REQUEST` แถวใหม่ได้ แต่ไม่ล็อกแถวที่มีอยู่ จึงไม่สวนกัน
* **Offer หมดเวลา (Job):** ล็อก Offer ที่ยังไม่จบของเคสทุกแถว เรียงตาม `id` → เคส → `STAFF` ของผู้สมัครทั้ง Plan ของเคส แบบเดียวกับการตอบ Offer เพราะเคสอาจส่ง Wave ถัดไปหรือเข้า `MANUAL_HANDOFF` ได้เหมือนกัน
* **กติการวม:** ทุกเส้นทางที่เรียก `recompute()` ล็อกตามลำดับเดียวกัน: Offer ที่ยังไม่จบของเคสทุกแถว → เคส → `STAFF` ของผู้สมัครทั้ง Plan แถวของตารางเดียวกันที่ Transaction หนึ่งจะล็อก ต้องล็อกใน Query เดียวที่เรียงตาม `id` ห้ามล็อกบางแถวก่อนแล้วมาล็อกเพิ่มทีหลัง
* **เคสอื่นที่ได้รับผลกระทบ (ข้อ 5.3):** `recompute()` ของเคสอื่นทำหลัง Commit ใน Transaction ของตัวเอง จึงเริ่มล็อกจาก Offer ของเคสนั้นตามลำดับปกติ ไม่ถือ Lock ของเคสแรกค้างไว้
* **Safety ไม่ผ่าน:** ตั้ง Offer ของผู้ตอบเป็น `CANCELLED` ใน Transaction ของการตอบรับ ซึ่งถือ Lock ของแถวนั้นอยู่แล้ว
* **เลือกคนของ Wave:** `contact_candidate` ล็อกแถว `STAFF` ของทั้ง Plan เรียงตาม `id` (ข้อ 6.7) ถ้าถูกเรียกต่อจากการตอบ Offer, การอนุมัติ หรือ Job แถวพวกนี้ถูกล็อกไว้แล้วตั้งแต่ต้น Transaction จึงไม่มีการรอเพิ่ม
* **ปิด Window (ข้อ 3):** ล็อก `SHIFT` ก่อน แล้วจึงแก้ Roster ตรงลำดับเดิม
* **[รอบ 2 · PR H] จัดคนเองจาก `MANUAL_HANDOFF`:** สร้าง Roster และอาจยกเลิก Offer ของคนที่ถูกเลือกในเคสอื่น จึงใช้ลำดับเดียวกับการตัดสินอนุมัติ: `SHIFT` → Offer ที่ยังไม่จบของคนนั้นในเคสอื่น → เคส → แถว `STAFF` ของคนที่ถูกเลือก ซึ่งต้องล็อกแม้เขาไม่อยู่ใน Plan แล้วตรวจ Hard Rules ซ้ำหลังได้ Lock (ข้อ 6.12)
* **[รอบ 2 · PR T] คำขออนุมัติหมดเวลา (Job):** ยกเลิก Offer และอาจทำให้เคสส่ง Wave ถัดไป จึงใช้ลำดับของการตัดสินอนุมัติ
* **[รอบ 2 · PR B] Solver:** `create_plan()` ยังล็อก `STAFF` ของทั้ง Pool ก่อนตรวจกติกาและถือจน Commit เพดานเวลาของ Solver จำกัดเวลาค้น ไม่ได้จำกัดเวลาที่ถือ Lock นี้ (ข้อ 6.14)
* ลำดับ Lock ในข้อนี้ยังเป็นการวิเคราะห์ ไม่มี Test พิสูจน์ PR ที่ลงมือเส้นทางนั้นต้องมี Test สอง Connection อย่างน้อยสี่กรณี: สองคนตอบรับเคสเดียวกันพร้อมกัน, คนเดียวตอบรับสองเคสพร้อมกัน, ตอบรับกับอนุมัติคนสุดท้ายพร้อมกัน, สองเคสที่ใช้ผู้สมัครชุดเดียวกันตอบ Offer แล้วส่ง Wave ถัดไปพร้อมกัน (รายการ Test อยู่ร่างรอบ 1 ข้อ 9.2)

### 6.12 เส้นออกจาก `MANUAL_HANDOFF`

**[รอบ 2 · PR H]** ทั้งข้อนี้เป็นกติกาที่ตกลงแล้ว โค้ดที่มีแล้วคือเส้น T8 กับ T9 ใน `transitions.py`, ค่าใน `enums.py` และการตรวจหอของการอนุมัติ (PR W) ส่วนที่เหลือยังไม่มีโค้ด Test ที่เป็นเกณฑ์เสร็จอยู่ร่างรอบ 2 ข้อ 3.2

**ใครกดได้**

* ผู้กดต้องเป็น Head Nurse ของหอเดียวกับเวร เทียบ `STAFF.home_ward_id` ของผู้กดกับ `SHIFT.ward_id` (R2-Q21)
* การอนุมัติใช้กติกาเดียวกัน และ**ทำแล้วใน PR W** (R2-Q53) ตัวตรวจคือ `domain/staffing/ward_authority.py` ฟังก์ชัน `manages_ward(*, home_ward_id, ward_id)` ตัวเดียว ซึ่งเส้นทางจัดคนเองและปิดเคสของ PR H ต้องเรียกตัวเดียวกันนี้ ไม่เขียนการเทียบหอเอง ผู้เรียกตรวจ Role เอง ตัวตรวจนี้ตรวจแค่หอ
  * `approval_service.decide()` รับ `home_ward_id` ของผู้กดเพิ่ม เทียบกับ `ward_id` ของเวรของเคสหลังล็อก `SHIFT` ถ้าไม่ตรงโยน `ApproverWardError` และ Route ตอบ `403` ไม่เขียน DB
  * ลำดับการตรวจของ `decision` คือ `404` → `403` (Role) → `403` (หอ) → `409` → `422` การตรวจหอมาก่อนการตรวจว่าคำขอยังค้างอยู่ เหมือนการตรวจ Role
  * ข้อนี้เปลี่ยนพฤติกรรมที่ merge แล้วในรอบ 1 ข้อมูล Seed มีหอเดียวและ Head Nurse 900 อยู่หอเดียวกับทุกเวร ผลของ Test เดิมและ Golden Path จึงไม่เปลี่ยน
  * `GET /approvals` ยังคืนคำขอของทุกหอให้ผู้ใช้ Demo ทุกคนเหมือนเดิม PR W ไม่ได้กรองรายการตามหอ เพราะ Contract กำหนดแค่การกดตัดสิน Head Nurse ต่างหอจึงเห็นคำขอแต่กดแล้วได้ `403`

**หาเคสที่ไหน**

* หน้า `/handoff` และ API `GET /cases?status=MANUAL_HANDOFF,FAILED` คืนเฉพาะเคสของหอที่ผู้เรียกเป็น Head Nurse (R2-Q12, R2-Q55) รูปของคำตอบอยู่ข้อ 9.4
* เคส `FAILED` แสดงในรายการเพื่อให้เห็นเวรที่ระบบจัดไม่สำเร็จ แต่กดจัดการไม่ได้ (R2-Q22)

**จัดคนเอง (T8)**

| หัวข้อ | กติกา |
|---|---|
| เลือกใครได้ | พนักงานที่ Active ของหอเดียวกับเวรทุกคน ไม่จำกัดเฉพาะคนใน Plan (R2-Q13) |
| Hard Rules | **ต้องผ่านทุกข้อ ไม่มีการข้าม** รวมกฎความล้าสี่ข้อ (`INSUFFICIENT_REST`, `DAILY_HOURS_EXCEEDED`, `WEEKLY_HOURS_EXCEEDED`, `CONSECUTIVE_SHIFTS_EXCEEDED`) เหตุผลที่ Head Nurse พิมพ์ไม่ทำให้คนที่ไม่ผ่านกลายเป็นจัดได้ (R2-Q14) |
| ตรวจเมื่อไหร่ | ด้วยตัวตรวจกลางใน `hard_rule_service` กับ Roster ล่าสุดรวมเวรที่จะจัด **หลัง**ได้ Lock ครบ ไม่ผ่านข้อใด ระบบปฏิเสธ ไม่สร้างแถว Roster ไม่สร้างแถว `manual_assignment` และบอกรหัสกฎที่ติด |
| หน้าเว็บ | รายการให้เลือกแสดงรหัสกฎที่ทำให้จัดไม่ได้ของแต่ละคน ผลในรายการคำนวณตอนอ่าน การตรวจตอนกดเป็นตัวตัดสิน |
| การตอบรับและการอนุมัติ | คนที่ถูกเลือกไม่ต้องกดตอบรับ ไม่สร้าง `APPROVAL_REQUEST` (R2-Q15, R2-Q16) |
| แถวที่เขียน | `ROSTER_ASSIGNMENT` แบบ `REPLACEMENT` สถานะ `ASSIGNED`, แถว `manual_assignment` ที่ผูกเวรนั้นกับเคส (R2-Q40 คอลัมน์อยู่ `database-schema.md`) และ Audit `MANUAL_ASSIGNMENT_CREATED` |
| การนับว่าปิด Gap | `case_facts_service._assigned_staff_ids()` รวมคนจาก `manual_assignment` ที่แถว Roster ยังเป็น `ASSIGNED` หรือ `COMPLETED` ตัวอ่านยังมีจุดเดียว เวรที่จัดเองแล้วถูกยกเลิกจึงไม่ถูกนับ |
| เคสที่ขาดหลายคน | จัดทีละคนได้ เคสอยู่ที่ `MANUAL_HANDOFF` จนคนที่ได้เข้าเวรปิด Gap ครบทั้งจำนวนคน, Role และ Skill ตามกติกา "Gap ถูกปิด" ของข้อ 5.1 แล้วเคสเป็น `RESOLVED` โดย Head Nurse ไม่ต้องกดปิด: Route จัดคนเองตรวจ Gap หลังสร้างเวร ถ้าปิดครบจึงเรียก Orchestrator ให้เดิน T8 ใน Transaction เดียวกัน (R2-Q17, R2-Q18) เคสเป็น `RESOLVED` ไม่ได้เพียงเพราะ Head Nurse เห็นว่าคนพอ |

**คนที่ถูกเลือกมี Offer ค้างในเคสอื่น (R2-Q46)**

* ตัวตรวจ Hard Rules ดูเวรใน Roster จึงไม่เห็นคนที่ตอบรับ Offer ของเคสอื่นแล้วแต่ยังรออนุมัติ ระบบแสดงคำเตือนว่าคนนี้มี Offer ในเคสอื่นที่ขัดกับเวรนี้ และ Head Nurse ต้องยืนยันก่อน การยืนยันเป็นการรับรู้ว่าจะดึงคนออกจากเคสอื่น ไม่ใช่การข้ามกฎ
* หลังสร้างเวร ระบบยกเลิก Offer ของคนเดียวกันในเคสอื่นที่ขัดกับ Roster ใหม่ ด้วยตัวยกเลิกตัวเดียวกับที่การอนุมัติใช้ (`approval_service._cancel_conflicting_offers()`) การตัดสินว่าใบไหนขัดทำตอนยืนยันด้วยข้อมูลปัจจุบันขณะถือ Lock ไม่ใช้รายการในคำเตือน
* ตัวยกเลิกที่ใช้ร่วมกันทำตามนี้ และแก้เส้นทางอนุมัติของรอบ 1 ไปพร้อมกัน

| Offer ของคนนั้นในเคสอื่น | สิ่งที่ทำ |
|---|---|
| `SENT` ยังไม่เลยเส้นตาย (`clock.now() < expires_at`) และขัดกับเวรใหม่ | ยกเลิก |
| `SENT` เลยเส้นตายแล้ว | ไม่แตะ ปล่อยให้ Job เขียน `TIMEOUT` พร้อม Audit `OFFER_TIMEOUT` (แบบเดียวกับข้อ 6.10 แถว "Gap ถูกปิด") ตอนนี้ตัวยกเลิกไม่ดูเส้นตาย เป็นบั๊กที่มีอยู่บน `main` |
| `ACCEPTED` และขัด | ยกเลิก คำขออนุมัติที่ผูกอยู่จึงกดตัดสินไม่ได้อีก |

* ทุก Offer ที่ถูกยกเลิก เขียน Audit `OFFER_CANCELLED_BY_ASSIGNMENT` ในเคสที่เสีย Offer ทั้งเมื่อเสียให้การจัดคนเองและเมื่อเสียให้การอนุมัติ (R2-Q56) แล้วเรียก `recompute()` ให้เคสเหล่านั้นหลัง Commit ตามข้อ 5.3
* `outreach_service._cancellation_reasons()` ซึ่งเติม `cancellation_reason` ในรายการ Offer ต้องยังคืน `CONFLICTING_ASSIGNMENT` ทั้งสองเส้นทาง ชื่อช่องใน payload ของ Audit สองตัวใหม่กำหนดในข้อ 7.1 เพื่อการนี้

**ปิดเคสโดยไม่มีคนแทน (T9)**

* Head Nurse ปิดเคสเป็น `UNRESOLVED` ต้องใส่เหตุผล ไม่ว่าง ไม่เกิน 500 ตัวอักษร ตัดช่องว่างหัวท้าย กติกาเดียวกับเหตุผลของการไม่อนุมัติ (R2-Q20) เขียน Audit `CASE_CLOSED_UNRESOLVED`
* ถ้าไม่มีใครผ่าน Hard Rules เคสอยู่ที่ `MANUAL_HANDOFF` ต่อ หรือถูกปิดด้วยเส้นนี้
* เวรที่จัดเองไปแล้วในเคสที่ถูกปิดยังอยู่ใน Roster
* **เคสใหม่ของเวรเดียวกัน (R2-Q19):** `MANUAL_HANDOFF` นับว่าเคสก่อนหน้าจบแล้ว เคสใหม่ของเวรจึงเปิดได้ (Q49) และ Gap ของเคสใหม่คำนวณจาก Roster ของทั้งเวร ช่องว่างของเคสเดิมจึงอยู่ในเคสใหม่ด้วย เมื่อเคสใหม่เปิด ระบบปิดเคสเดิมที่ยัง `MANUAL_HANDOFF` เป็น `UNRESOLVED` พร้อมเหตุผลตายตัวและเลขเคสใหม่ งานนี้อยู่ในขั้นปิด Window

**การเปลี่ยนสถานะและ Lock**

* T8 และ T9 เปลี่ยนสถานะผ่าน Orchestrator เท่านั้น เพื่อให้ `assert_transition()` ตรวจ และ `CASE_STATUS_CHANGED` ยังมีผู้เขียนคนเดียว (ข้อ 7.2) `recompute()` ยังไม่แตะเคสที่ `MANUAL_HANDOFF` PR H เพิ่มทางเข้าใหม่ใน Orchestrator สำหรับสองเส้นนี้ และเขียน Signature ลงข้อ 6.2
* ผู้เรียกทางเข้านี้มีสามจุด: Route จัดคนเอง (T8 เมื่อ Gap ถูกปิด), Route ปิดเคสโดยไม่มีคนแทน (T9) และขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด (T9 โดยระบบ) ทุกจุดเรียกใน Transaction เดียวกับงานของตัวเอง ไม่มี Handler และไม่มีจุดอื่นเดินสองเส้นนี้
* เส้นทางจัดคนเองล็อกแถว `STAFF` ของคนที่ถูกเลือกแม้เขาไม่อยู่ใน Plan ตรวจซ้ำหลังได้ Lock และใช้ลำดับ Lock ของข้อ 6.11

### 6.13 Timeout ของการอนุมัติ

**[รอบ 2 · PR T]** ทั้งข้อนี้เป็นกติกาที่ตกลงแล้ว โค้ดยังไม่มี จนกว่า PR T จะเข้า การอนุมัติยังไม่มีเส้นตายตามข้อ 6.9 Test ที่เป็นเกณฑ์เสร็จอยู่ร่างรอบ 2 ข้อ 3.2

| หัวข้อ | กติกา |
|---|---|
| ค่าระยะเวลา | คอลัมน์ใหม่ `APPROVAL_POLICY.approval_timeout_seconds` Seed = 900 วินาที ยาวกว่า Timeout ของ Offer (300) และ Window ของ Scenario การ Merge (600) (R2-Q9, R2-Q23) |
| เส้นตายของแต่ละคำขอ | คอลัมน์ใหม่ `APPROVAL_REQUEST.expires_at` ตั้งตอนสร้างคำขอ = `requested_at` + ค่าใน Policy ไม่เปลี่ยนทีหลัง |
| ขอบเขตเวลา | คำขอหมดเวลาเมื่อ `clock.now() >= expires_at` และกดตัดสินได้ขณะ `clock.now() < expires_at` สูตรเดียวกับ Offer (R2-Q50) |
| กดตัดสินหลังเส้นตาย | ตอบ `409` ไม่เขียน DB แม้ Job ยังไม่มา (R2-Q26) |
| ใครเขียนผลหมดเวลา | Job เท่านั้น เลือกคำขอที่ `is_pending = true` และผ่าน `case_facts_service.accepted_offer_for_request()` และ `clock.now() >= expires_at` ไม่ใช้ `is_pending` อย่างเดียว คำขอของเคสที่หยุดแล้วไม่ถูกเลือก |
| ค่าที่เขียน | `is_pending = false`, `is_approved = false`, `approver_id` ว่าง, `is_timed_out = true`, `reason` เป็นข้อความตายตัว, `decided_at` แล้วยกเลิก Offer ของคำขอนั้น และเขียน Audit `APPROVAL_TIMEOUT` (R2-Q24) |
| สถานะรายคน | `stage` ค่าใหม่ `APPROVAL_TIMEOUT` แยก "Head Nurse ไม่ได้ตอบ" ออกจาก `APPROVAL_REJECTED` (R2-Q25) |
| ลำดับใน `run_due_work()` | ปิด Offer ที่หมดเวลา → ปิดคำขออนุมัติที่หมดเวลา → เก็บตก → ปิด Window (R2-Q27) แทนลำดับสามขั้นของข้อ 3.8 |
| คำตอบของ `POST /demo/clock/advance` | เพิ่ม `timed_out_approval_request_ids` และหน้า `demo/control` แสดงตาม |
| Auto-Approval | ไม่ทำในรอบ 2 |

**ผู้สมัครกลับไปต่อท้ายคิวได้หนึ่งครั้ง (R2-Q29)**

* หมดเวลาครั้งแรก คำขอนั้นจบแบบไม่อนุมัติและเคสไปหาคนถัดไป แต่ผู้สมัครไม่หลุดถาวร หมดเวลาครั้งที่สองจึงหลุดถาวรในเคสนั้น
* เขาถูกติดต่อใหม่เมื่อการเลือก Wave ครั้งนั้นไม่เหลือคนที่ไม่เคยถูกติดต่อและส่ง Offer ได้ คนที่ถูกข้ามเพราะ Hard Rules หรือเพดาน Offer ไม่ทำให้คิวนี้รอ (R2-Q48) ข้อนี้เปลี่ยนข้อ 6.6 ขั้นที่ 4 ซึ่งตอนนี้ไม่ติดต่อคนเดิมซ้ำ และเปลี่ยนเงื่อนไขของ T5
* รอบที่สองคือ Offer ใบใหม่ ผ่านการตรวจ Hard Rules และเพดาน Offer แบบเดียวกับใบแรกขณะถือ Lock ตอบรับแล้วเข้า Safety ใหม่ และได้คำขออนุมัติใหม่พร้อมเส้นตายใหม่
* ถึงคิวแล้วแต่ติดเพดานหรือไม่ผ่าน Hard Rules ยังไม่นับว่าใช้สิทธิ์ สิทธิ์หมดเมื่อ Offer ใบที่สองถูกส่งจริง (R2-Q47)

**หนึ่งรอบคือหนึ่ง Offer (R2-Q41)**

* โค้ดรอบ 1 ผูก Offer, ผล Safety และคำขออนุมัติด้วย `candidate_item_id` อย่างเดียว ซึ่งถูกเมื่อหนึ่งคนมีหนึ่งรอบต่อเคส PR T เพิ่มคอลัมน์ `outreach_id` ใน `SAFETY_VALIDATION` และ `APPROVAL_REQUEST` และให้ตัวอ่านจับคู่ด้วย Offer
* ตัวอ่านที่ต้องแก้มีอย่างน้อยสี่จุด: `case_facts_service._waiting_acceptances()`, `outreach_service.promote_reserves()`, `case_facts_service.accepted_offer_for_request()` และ `case_facts_service._has_uncontacted_candidate()` คนทำ PR T ต้องค้นทุกที่ที่จับคู่ด้วย `candidate_item_id`
* สิทธิ์รอบที่สองคำนวณตอนอ่าน ไม่เก็บตัวนับ: Item มีสิทธิ์เมื่อมี Offer ของเคสนี้แถวเดียว และคำขอของ Offer นั้นมี `is_timed_out = true` Item หนึ่งมี Offer ของเคสได้ไม่เกินสองแถว
* สถานะรายคนอ่านจาก Offer ที่ `id` มากสุดของ Item แถวของรอบแรกเป็นประวัติ ต้องไม่ทำให้เคสหยุดรอ ไม่นับว่าปิด Gap ไม่นับว่าถูกปฏิเสธ และไม่กันรอบที่สอง

**Migration**

* เติมเส้นตายให้**ทุกแถว**ที่มีอยู่ด้วย `requested_at` + ค่าใน Policy คอลัมน์เป็น NOT NULL (R2-Q28) เส้นตายของแถวที่ไม่ได้รออยู่จริงเป็นแค่ประวัติ
* เติม `outreach_id` ให้แถวเดิมจาก Offer ของเคสกับ Item เดียวกัน ตาราง `candidate_outreach` ไม่มี Unique Constraint Migration จึงตรวจก่อน ถ้าคู่ไหนมี Offer มากกว่าหนึ่งแถวให้หยุดพร้อมข้อความบอกสาเหตุ (R2-Q52)
* รันได้กับฐานข้อมูลที่มีข้อมูลอยู่โดยไม่ต้อง Reset คำขอที่ค้างมานานกว่า 900 วินาทีจะหมดเวลาในรอบแรกที่ Job ทำงานหลัง Migration

**เหตุที่ยกเลิกในรายการ Offer:** `outreach_service._cancellation_reasons()` คืน `APPROVAL_TIMEOUT` สำหรับ Offer ที่ถูกยกเลิกเพราะคำขอหมดเวลา ไม่ใช่ค่ากลาง `CANCELLED`

### 6.14 Solver แบบ OR-Tools

**[รอบ 2 · PR B]** ทั้งข้อนี้เป็นกติกาที่ตกลงแล้ว โค้ดยังเป็นการค้นของรอบ 1 จนกว่า PR B จะเข้า PR A (#51) ตรึงผลของ Solver รอบ 1 ไว้เป็นตัวเทียบแล้ว การออกแบบข้างในของโมเดลอยู่ร่างรอบ 2 ข้อ 4.7 และเกณฑ์เสร็จอยู่ข้อ 4.5

**สิ่งที่ไม่เปลี่ยน**

* Hard Rules ยังคัดรายคนใน `hard_rule_service` ก่อนเรียก `solve()` OR-Tools ทำแค่ Soft (R2-Q2) ตัวตรวจ Hard Rules ยังมีตัวเดียวทั้ง Solver, Wave และ Safety
* Argument ห้าตัวเดิมของ `solve()` และสามค่าเดิมของ `SolverResult` ความหมายไม่เปลี่ยน `rank` เรียง 1 ถึง n, `first_wave` มาจาก `fill_targets()` ตัวเดิม และ Target ที่ผู้สมัครมีไม่พอถูกลดเท่าจำนวนคนที่ตรง
* `objective_score` ที่เก็บเป็นค่า `plan_penalty` จริง คำนวณใหม่จากกลุ่มที่ได้ด้วย `penalties.plan_penalty()` ไม่ใช่ค่าที่คูณสเกลแล้ว
* `solver.py` ไม่อ่าน DB ไม่เขียน และไม่อ่าน Clock ของระบบ
* ผลต้องเท่ากับ Solver รอบ 1 ทุกกรณี รวมกรณีคะแนนเท่ากัน เมื่อสถานะเป็น `OPTIMAL` (R2-Q3) Golden Path ยังได้ Wave แรกเป็น 201 กับ 202 (R2-Q7)
* การค้นแบบเดิมเก็บไว้เป็นตัวเทียบใน Test เท่านั้น ไม่ใช่ตัวสำรองในระบบจริง (R2-Q6)

**สิ่งที่เพิ่มใน Interface (R2-Q42)**

* `solve()` รับเพดานเวลาเป็น Argument แบบ keyword ตัวใหม่ `create_plan()` อ่านค่าจากคอลัมน์ใหม่ `SOFT_CONSTRAINT_POLICY.solver_time_limit_seconds` (Seed = 3) แล้วส่งเข้ามา
* `SolverResult` มีช่องสถานะเพิ่มหนึ่งช่อง เป็นค่าของ `SolverStatus` `create_plan()` เขียน `CANDIDATE_PLANS.solver_status` จากช่องนี้ แทนการเดาจากว่ามีผู้สมัครหรือไม่
* `SOLVER_VERSION` เปลี่ยนจาก `"weighted-v1"` เป็นค่าใหม่

**สถานะและผลต่อเคส (R2-Q4, R2-Q43)**

| `solver_status` | ความหมาย | เคสเป็น |
|---|---|---|
| `OPTIMAL` | พิสูจน์ครบทั้งคะแนน จำนวนคน และชุด `staff_id` | `OUTREACH` ตามปกติ |
| `FEASIBLE` | มีแผนที่ผ่านข้อบังคับ แต่หมดเวลาก่อนพิสูจน์ครบ ผลอาจไม่ซ้ำเดิมและอาจต่างจากรอบ 1 | `OUTREACH` ตามปกติ บันทึกใน Audit `SOLVER_EXECUTED` อย่างเดียว (R2-Q32) |
| `INFEASIBLE` | ไม่มีผู้สมัครผ่าน Hard Rules เลย `solve()` คืนค่านี้โดยไม่สร้างโมเดล เหมือนรอบ 1 | `MANUAL_HANDOFF` ด้วยเหตุผล `NO_FEASIBLE_PLAN` (T6) |
| `UNKNOWN` | หมดเวลาโดยยังไม่มีแผนเลย เป็นผลที่เกิดได้ตามปกติ ไม่ใช่ระบบทำงานผิด Handler ไม่โยน Exception และแถว Plan ถูกเก็บ | `MANUAL_HANDOFF` ด้วยเหตุผล `SOLVER_TIMEOUT` (T6) |
| `MODEL_INVALID` | โมเดลผิดรูป หรือ OR-Tools รายงาน `INFEASIBLE` ทั้งที่มีผู้สมัคร ซึ่งเกิดไม่ได้ถ้าโมเดลถูก เพราะการเลือกทุกคนผ่านข้อบังคับเสมอ Handler โยน Exception | `FAILED` ผ่าน D11 |

* Audit `SOLVER_EXECUTED` ของ Golden Path เปลี่ยนจาก `FEASIBLE` เป็น `OPTIMAL` ไฟล์ Test ที่ต้องแก้ใน PR B อยู่ร่างรอบ 2 ข้อ 5
* แผนที่เก็บไว้จากขั้นก่อนหน้าคืนเป็น `FEASIBLE` ได้เฉพาะเมื่อขั้นหลังหมดเวลา ไม่ใช้กลบข้อผิดพลาดของโมเดล

**เพดานเวลาและการตั้งค่า**

* 3 วินาทีเป็นงบรวมของการเรียก `solve()` หนึ่งครั้ง ทุกรอบของการ Solve ใช้งบก้อนเดียวกัน (R2-Q5, R2-Q44) ค่านี้อาจเปลี่ยนหลังผลวัดของโมเดลจริงใน PR B
* เพดานนี้จำกัดเวลาค้นอย่างเดียว ไม่ได้จำกัดเวลาที่ถือ Lock ของ `STAFF` ทั้ง Pool (ข้อ 6.11) ซึ่งรวมการโหลดข้อมูล การสร้างโมเดล และการเขียน Plan
* ใช้ `num_workers = 1` และ `random_seed = 0` เป็นข้อตกลงกลาง ไม่ใช่ทางเลือกของผู้ทำ (R2-Q33)
* PR B เพิ่ม Dependency `ortools` หลัง merge ทุกคนต้องสร้าง container ของ Backend ใหม่ (R2-Q11)

---

## 7. Audit

PR 4 ตรวจชุด Offer ซ้ำหลังล็อก Staff ถ้ามี Offer ใหม่ Commit ระหว่างรอ Lock ให้ Rollback ก่อนเขียนคำตัดสิน แล้วเริ่มล็อกใหม่ตามลำดับเดิม (สูงสุด 5 ครั้ง ถ้ายังเปลี่ยนตอบ 409 ให้ลองใหม่) ไม่ล็อก Offer เพิ่มภายหลังเคส/Staff เพื่อกัน Deadlock

### 7.1 Action ที่ใช้

| Action | ใครเขียน | Actor | entity_type | payload ขั้นต่ำ |
|---|---|---|---|---|
| `EVENT_RECEIVED` | `event_service` ตอนรับ Event (PART A) | user (ผู้แจ้ง) | STAFFING_EVENTS | `event_type`, `shift_id`, `staff_id` |
| `UNAVAILABILITY_CREATED` | `merge_window_service` ตอน Window ปิด (PART B) | user (คนที่ลา) | STAFF_UNAVAILABILITY | `unavailability_id`, `staff_id`, `reason`, `start_at`, `end_at` |
| `ASSIGNMENT_CANCELLED` | `merge_window_service` ตอน Window ปิด (PART B) | user (ผู้แจ้ง จาก `reported_by` ใน payload ของ Event) | ROSTER_ASSIGNMENT | `assignment_id` (Roster ที่ถูกยกเลิก), `staff_id`, `reason` |
| `PATIENT_COUNT_UPDATED` | `merge_window_service` ตอน Window ปิด (PART B) | user (ผู้แจ้ง) | SHIFT | `shift_id`, `old_patient_count`, `new_patient_count` |
| `REQUIREMENT_UPDATED` | `merge_window_service` ตอน Window ปิด (PART B) | user (ผู้แจ้ง) | STAFFING_REQUIREMENTS | `requirement_id`, `roles`: List ของ `{role_id, old_required_count, new_required_count}`, `skills`: List ของ `{skill_id, old_required_count, new_required_count}` เรียงตาม ID |
| `EVENT_IGNORED` | `merge_window_service` ตอน Window ปิด (PART B) | `workflow_orchestrator` | STAFFING_EVENTS | `event_id`, `shift_id`, `reason` (รหัสในข้อ 3.7) |
| `CASE_OPENED` | `merge_window_service` ตอน Window ปิด (PART B) | `workflow_orchestrator` | STAFFING_CASES | `event_id` (Event ตัวแรกที่ผ่าน Threshold), `shift_id`, `headcount_gap` |
| `CASE_STATUS_CHANGED` | Orchestrator | `workflow_orchestrator` | STAFFING_CASES | `from`, `to` |
| `GAP_ASSESSED` | `assess_staffing` | `staffing_gap_assessment_agent` | STAFFING_GAP | `gap_id`, `headcount_gap`, `role_gaps`, `skill_gaps` |
| `SOLVER_EXECUTED` | `optimize` | `constraint_fair_scheduling_agent` | CANDIDATE_PLANS | `plan_id`, `solver_status`, `candidate_count` |
| `OFFER_SENT` | `contact_candidate` | `outreach_agent` | CANDIDATE_OUTREACH | `outreach_id`, `staff_id`, `channel`, `wave` แถวแรกของ Wave มี `skipped` |
| `OFFER_ACCEPTED` | `outreach_service` | user (ผู้สมัคร) | CANDIDATE_OUTREACH | `outreach_id`, `staff_id` |
| `OFFER_REJECTED` | `outreach_service` | user (ผู้สมัคร) | CANDIDATE_OUTREACH | `outreach_id`, `staff_id` |
| `OFFER_TIMEOUT` | `offer_timeout_service` เรียกจาก Job | `outreach_agent` | CANDIDATE_OUTREACH | `outreach_id`, `staff_id` |
| `SAFETY_PASSED` | `safety_service` | `safety_rule_engine` | SAFETY_VALIDATION | `validation_id`, `staff_id` |
| `SAFETY_FAILED` | `safety_service` | `safety_rule_engine` | SAFETY_VALIDATION | `validation_id`, `staff_id`, `outreach_id`, `failed_rules` (List ของรหัส) |
| `APPROVAL_REQUESTED` | `approval_service` ตอนสร้างคำขอ หลัง Safety ผ่าน (Seam 5) | `workflow_orchestrator` | APPROVAL_REQUEST | `approval_id`, `approval_mode` |
| `APPROVAL_APPROVED` | `approval_service` | user (ผู้อนุมัติ) | APPROVAL_REQUEST | `approval_id`, `reason` |
| `APPROVAL_REJECTED` | `approval_service` | user (ผู้อนุมัติ) | APPROVAL_REQUEST | `approval_id`, `staff_id` (ผู้สมัคร), `outreach_id`, `reason` |
| `ASSIGNMENT_CREATED` | เส้นทางอนุมัติ ใน Transaction ของ `approval_service.decide()` | `workflow_orchestrator` | ROSTER_ASSIGNMENT | `assignment_id`, `staff_id`, `assignment_type`, `cancelled_outreach_ids` |
| `CASE_RESOLVED` | Handler ของ `EXECUTING` | `workflow_orchestrator` | STAFFING_CASES | `assignment_ids`, `cancelled_outreach_ids` |
| `MANUAL_HANDOFF` | Handler ที่หยุดเคส (`contact_candidate` หรือ `optimize`) | Actor ของ Handler นั้น | STAFFING_CASES | `reason` (รหัส), `stopped_at` (State ที่หยุด), `cancelled_outreach_ids` (Offer ที่ยัง `SENT` ซึ่งถูกยกเลิกตอนเคสหยุด ว่างได้), `skipped` (List ของ `{staff_id, reason}` ของคนที่ถูกข้ามในการเลือกครั้งสุดท้าย ข้อ 6.7 ว่างได้) |
| `WORKFLOW_FAILED` | Orchestrator (D11) | `workflow_orchestrator` | STAFFING_CASES | `from`, `failed_at`, `error_type` |
| `APPROVAL_TIMEOUT` **[รอบ 2 · PR T]** | Service ของคำขอที่หมดเวลา เรียกจาก Job | `workflow_orchestrator` | APPROVAL_REQUEST | `approval_id`, `staff_id` (ผู้สมัคร), `outreach_id` (Offer ที่ถูกยกเลิก), `reason` (ข้อความตายตัว) |
| `MANUAL_ASSIGNMENT_CREATED` **[รอบ 2 · PR H]** | เส้นทางจัดคนเอง | user (Head Nurse) | ROSTER_ASSIGNMENT | `assignment_id`, `manual_assignment_id`, `staff_id`, `assignment_type`, `reason` (ว่างได้), `cancelled_outreach_ids` (Offer ของเคสอื่นที่ขัดกับเวรใหม่ ว่างได้) |
| `CASE_CLOSED_UNRESOLVED` **[รอบ 2 · PR H]** | เส้นทางปิดเคสโดยไม่มีคนแทน หรือขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด | user (Head Nurse) หรือ `workflow_orchestrator` เมื่อระบบปิด | STAFFING_CASES | `reason`, `closed_by` (`HEAD_NURSE` หรือ `SUCCESSOR_CASE`), `successor_case_id` (มีเมื่อระบบปิด) |
| `OFFER_CANCELLED_BY_ASSIGNMENT` **[รอบ 2 · PR H]** | ตัวยกเลิก Offer ที่ขัดกับเวรใหม่ เขียนใน**เคสที่เสีย Offer** หนึ่งแถวต่อ Offer | ผู้กระทำของการจัดนั้น | CANDIDATE_OUTREACH | `cancelled_outreach_id` (เอกพจน์), `staff_id`, `by_case_id` (เคสที่เอาคนไป), `assignment_id` (Roster ที่ทำให้ขัด), `source` (`MANUAL_ASSIGNMENT` หรือ `APPROVAL`) |

* `ASSIGNMENT_CANCELLED`, `PATIENT_COUNT_UPDATED`, `REQUIREMENT_UPDATED` เพิ่มใน `AuditAction` แล้ว และ `SHIFT`, `STAFFING_REQUIREMENTS` เพิ่มใน `EntityType` แล้ว (PR 0) และ PART B เขียนแถวพวกนี้ตั้งแต่ PR M
* Actor ของ `OFFER_TIMEOUT` คือ `outreach_agent` และผู้เขียนคือ `offer_timeout_service` (PR O); Actor และชื่อ Key ใน payload ของ Action สามตัวของ Event ชนิดใหม่ และ Key `reason` ของ `EVENT_IGNORED` กำหนดแล้วใน PR M ตามตารางข้างบน
* `EVENT_RECEIVED`: `staff_id` ใน payload คือคนที่ Event พูดถึง (`STAFFING_EVENTS.staff_id`) จึงเป็น `null` สำหรับ `PATIENT_SURGE` และ `REQUIREMENT_CHANGED` ผู้แจ้งดูจาก Actor ของแถว
* หกแถวแรกของตารางเป็นแถวของ Event: มี `event_id` และ `case_id = NULL` เสมอ ส่วน `CASE_OPENED` เป็นแถวของเคส: มี `case_id` และ `event_id = NULL` โดยบอก Event ไว้ใน payload

รหัส `reason` ของ `MANUAL_HANDOFF`: `NO_CANDIDATE_LEFT` (T5), `NO_FEASIBLE_PLAN` (T6) และ **[รอบ 2 · PR B]** `SOLVER_TIMEOUT` (T6 เมื่อ Solver หมดเวลาโดยยังไม่มีแผน ข้อ 6.14)

* แถวที่มีป้าย **[รอบ 2]** ในตารางข้างบน: ค่าอยู่ใน `AuditAction` แล้วตั้งแต่ PR 0 ของรอบ 2 แต่ยังไม่มีโค้ดใดเขียน
* ชื่อช่องของ `OFFER_CANCELLED_BY_ASSIGNMENT` ต้องเป็น `cancelled_outreach_id` ห้ามใช้ `cancelled_outreach_ids` หรือ `outreach_id` เพราะ `outreach_service._cancellation_reasons()` ใช้สองชื่อนั้นหาเหตุที่ยกเลิก และแถว Audit ล่าสุดชนะ ถ้าใช้ชื่อซ้ำ `cancellation_reason` ของรายการ Offer จะเปลี่ยนจาก `CONFLICTING_ASSIGNMENT` เป็น `CANCELLED` โดยไม่มี Error
* `MANUAL_ASSIGNMENT_CREATED` ใช้ `cancelled_outreach_ids` เหมือน `ASSIGNMENT_CREATED` และ PR H ต้องเพิ่ม Action นี้ในตารางของ `_cancellation_reasons()` ให้ได้ `CONFLICTING_ASSIGNMENT`
* `APPROVAL_TIMEOUT` มี `outreach_id` และ PR T ต้องให้ `_cancellation_reasons()` คืน `APPROVAL_TIMEOUT` สำหรับ Offer นั้น

* `MANUAL_HANDOFF` ของ T6 เขียนโดย Handler `optimize` ด้วย Actor `constraint_fair_scheduling_agent` ต่อจาก `SOLVER_EXECUTED` ในรอบเดียวกัน `cancelled_outreach_ids` ว่างเสมอ และ `skipped` คือทุกคนใน Pool ที่ Solver ตัดออก เรียงตาม `staff_id` รหัสของแต่ละคนคือเหตุผลแรกตามลำดับ: Hard Rules (ลำดับตารางในร่างรอบ 1 ข้อ 7.2), ปิด Gap ไม่ได้สักอย่าง, เพดาน Offer ค่าของ `reason` อยู่ใน `ManualHandoffReason` ของ `domain/enums.py`

payload ที่เปลี่ยนจาก Skeleton เพราะ Wave

* `OFFER_SENT`: ยังเป็นหนึ่งแถวต่อคน เรียงตาม `rank` payload เดิม (`outreach_id`, `staff_id`, `channel`) เพิ่ม `wave` (เลข Wave ของเคส เริ่มที่ 1) แถวแรกของ Wave มี `skipped` (Q5)
* `OFFER_ACCEPTED`: ไม่เพิ่ม `cancelled_outreach_ids` เพราะการตอบรับไม่ยกเลิก Offer ของคนอื่นทันที (ข้อ 6.8)
* `CASE_RESOLVED`: เพิ่ม `cancelled_outreach_ids` = Offer ของเคสที่ถูกยกเลิกตอนได้คนครบ ทั้งที่ยัง `SENT` และของสำรอง (Q28)
* `ASSIGNMENT_CREATED`: เพิ่ม `cancelled_outreach_ids` = Offer ของเคสอื่นที่ขัดกับเวรใหม่ของผู้สมัคร (ข้อ 6.8) ว่างได้
* `WORKFLOW_FAILED`: ไม่เปลี่ยนความหมาย ยังแปลว่าเคส `FAILED` ตาม D11 เท่านั้น ไม่มีกรณีจัดเวรรายคนไม่ผ่าน เพราะไม่มีการตรวจซ้ำตอนจัดเวร (Q38)

### 7.2 กติกา

* `CASE_STATUS_CHANGED` ยังเขียนโดย Orchestrator เท่านั้น ทุกเส้นใหม่จะมีแถวนี้เอง
* ไม่เพิ่ม Action สำหรับการตั้ง Offer เป็น `CANCELLED` ให้ `outreach_id` ใน payload ของ `SAFETY_FAILED` / `APPROVAL_REJECTED` บอกแทน ส่วน Offer ที่ถูกยกเลิกเพราะเคสได้คนครบ, เพราะเคสเข้า `MANUAL_HANDOFF` หรือเพราะขัดกับเวรใหม่ของผู้สมัคร ให้ `cancelled_outreach_ids` ของ Action ในจังหวะนั้นบอก (ข้อ 7.1, Q28)
  * **[รอบ 2 · PR H]** ข้อยกเว้นหนึ่งข้อ: Offer ที่ถูกยกเลิกเพราะเคสอื่นเอาคนไป ได้แถว `OFFER_CANCELLED_BY_ASSIGNMENT` ในเคสของ Offer นั้นด้วย เพราะ `cancelled_outreach_ids` อยู่ในเคสที่ได้คนไป คนที่เปิดเคสที่เสีย Offer จึงไม่เห็นเหตุ (R2-Q56) ช่อง `cancelled_outreach_ids` ในเคสที่ได้คนไปคงไว้ตามเดิม
* `payload` ยังห้ามมีข้อมูลผู้ป่วยรายบุคคลและ `password_hash` `reason` ของการไม่อนุมัติเป็นข้อความที่ผู้อนุมัติพิมพ์ ตอนนี้ `APPROVAL_APPROVED` ก็เก็บ `reason` อยู่แล้ว คงแบบเดียวกัน
* `GOLDEN_PATH_AUDIT_ACTIONS` **เปลี่ยน**: Golden Case ขาดจำนวนคน 1 และขาด Role RN 1 Target = จำนวนคน 2, RN 2 ผู้สมัครทุกคนเป็น RN คนหนึ่งคนจึงนับให้ทั้งสอง Target Wave แรก = 201, 202 มี `OFFER_SENT` สองแถว (จำลองกติกาเติม Target ด้วยโค้ดแล้ว) E2E เทียบลำดับแบบตรงตัวทุกแถว จึงต้องแก้ค่าคงที่และ E2E ใน PR เดียวกับที่เปิด Wave (PR 2b) Merge Gap ไม่เปลี่ยนค่าคงที่นี้ เพราะเวรใน Golden Case ใช้ Window = 0

### 7.3 ลำดับ Audit ที่คาดหวังของแต่ละกรณี (ไม่นับ `CASE_STATUS_CHANGED`)

ใช้เป็นเกณฑ์ของ Integration Test

วิธีอ่าน

* ลำดับแบ่งเป็นสองช่วง **ช่วงต้น** ตั้งแต่รับ Event ถึงได้ Gap และ **ช่วงหาคน** ตั้งแต่ Solver ถึงเคสจบ เคสหนึ่งเคส = ช่วงต้นหนึ่งกรณี ต่อด้วยช่วงหาคนหนึ่งกรณี
* ลำดับของผู้สมัครคนเดียวกันตายตัว: `OFFER_SENT` → `OFFER_ACCEPTED` → `SAFETY_PASSED` → `APPROVAL_REQUESTED` → `APPROVAL_APPROVED` → `ASSIGNMENT_CREATED`
* ลำดับข้ามคนขึ้นกับว่าใครกดก่อน ลำดับข้างล่างคือลำดับเมื่อ Test กดตามที่เขียน
* ขนาด Wave ตามกติกาเติม Target ร่างรอบ 1 ข้อ 8.3 Golden Case: Target = จำนวนคน 2, RN 2 ได้ Wave แรก 2 คน คือ 201 กับ 202
* การตอบรับของคนหนึ่ง**ไม่**ยกเลิก Offer ของคนอื่นทันที (ข้อ 6.8) Offer ที่เหลือถูกยกเลิกตอนเคส `RESOLVED` และรายการอยู่ใน `cancelled_outreach_ids` ของ `CASE_RESOLVED` (Q28)
* จัดเวรรายคน: `ASSIGNMENT_CREATED` ของแต่ละคนตามหลัง `APPROVAL_APPROVED` ของคนนั้นทันที (Q27)

#### ช่วงต้น: รับ Event ถึงได้ Gap

| กรณี | เขียนตอนรับ Event (PART A) | เขียนตอน Window ปิด (PART B) |
|---|---|---|
| ต1. Window = 0 เวรขาดคน | `EVENT_RECEIVED` | `UNAVAILABILITY_CREATED`, `CASE_OPENED`, `GAP_ASSESSED` อยู่ใน Request เดียวกับ PART A ลำดับที่เห็นเหมือน Skeleton |
| ต2. Window = 0 ไม่ผ่าน Threshold | `EVENT_RECEIVED` | `UNAVAILABILITY_CREATED`, `EVENT_IGNORED` ไม่มีเคส เหมือน Skeleton |
| ต3. Window > 0 มี 2 Event มีตัวที่ผ่าน Threshold และ Gap สุดท้ายไม่เป็น 0 | `EVENT_RECEIVED` หนึ่งแถวต่อ Event (คนละ Request) | `UNAVAILABILITY_CREATED` หนึ่งแถวต่อ Event ตามลำดับ Event แล้ว `CASE_OPENED` หนึ่งแถว และ `GAP_ASSESSED` หนึ่งแถวท้ายสุด |
| ต4. Window > 0 ไม่มี Event ไหนผ่าน Threshold | `EVENT_RECEIVED` หนึ่งแถวต่อ Event | `UNAVAILABILITY_CREATED` หนึ่งแถวต่อ Event แล้ว `EVENT_IGNORED` หนึ่งแถวต่อ Event ไม่มีเคส |
| ต5. Window > 0 มี Event ที่ผ่าน Threshold แต่ Gap สุดท้ายเป็น 0 | `EVENT_RECEIVED` หนึ่งแถวต่อ Event | Action ของแต่ละ Event ตามลำดับ (เช่น `PATIENT_COUNT_UPDATED` สองแถว) แล้ว `EVENT_IGNORED` หนึ่งแถวต่อ Event ไม่มีเคส |

* ต3: `EVENT_RECEIVED` และ `UNAVAILABILITY_CREATED` ถูกเขียนตอนยังไม่มีเคส แต่มี `event_id` จึงขึ้น Timeline ของเคสหลัง Window ปิด และอยู่ก่อน `CASE_OPENED` ทุกแถว (Q33) ไม่มี Action เพิ่ม
* ต4 กับ ต5: `EVENT_IGNORED` เกิดได้สองทาง คือไม่มี Event ไหนผ่าน Threshold (ต4, Q32) หรือมีตัวที่ผ่านแต่ Gap ที่คิดจากข้อมูลสุดท้ายเป็น 0 ทุกตัว (ต5) payload ของ `EVENT_IGNORED` บอกว่าเป็นทางไหน
* payload ของ `CASE_OPENED` ยังมี `event_id` ตัวเดียว คือ Event ตัวแรกที่ผ่าน Threshold ไม่เปลี่ยนเป็น List รายการ Event ครบทุกตัวของเคสอ่านจาก `STAFFING_EVENTS.case_id` และ Case API ตอบเป็น `event_ids` (Q36)
* ทุกกรณี: `EVENT_RECEIVED` กับ `UNAVAILABILITY_CREATED` มี `event_id` ไม่มี `case_id` (Q33) ขึ้น Timeline ของเคสผ่าน `event_id` เรียงตาม `id` ของ Audit
* ตารางนี้เขียนด้วย `STAFF_UNAVAILABLE` Event อีกสามชนิดเขียน Action ของตัวเองแทน `UNAVAILABILITY_CREATED` ในตำแหน่งเดียวกัน: `ASSIGNMENT_CANCELLED`, `PATIENT_COUNT_UPDATED`, `REQUIREMENT_UPDATED` (ข้อ 3 Q40)
* `UNAVAILABILITY_CREATED` อยู่คอลัมน์ขวาทุกกรณี เพราะ Update table ทำตอน Window ปิด (Q41) ผลคือใน ต3 ลำดับตาม `id` เป็น `EVENT_RECEIVED` ทุกตัวก่อน แล้วจึงเป็นแถวของ PART B ตามลำดับในตาราง ไม่สลับเป็นคู่กับ `EVENT_RECEIVED`
* ต3: Event ที่ไม่ผ่าน Threshold แต่อยู่ Window เดียวกับตัวที่ผ่าน เป็น `PROCESSED` และ Link เข้าเคส ไม่มี `EVENT_IGNORED` (Q42)
* ไม่มีกรณี Event เข้าเคสเดิม: Event ของเวรที่มีเคสเดินอยู่รอเป็น `RECEIVED` จนเคสนั้นจบ แล้วเดินตาม ต3, ต4 หรือ ต5 (Q43)
* Event ที่ Update table ไม่ได้ (Q44): Event ตัวนั้นได้ `EVENT_IGNORED` พร้อมเหตุผลใน payload ไม่มี `UNAVAILABILITY_CREATED`

#### ช่วงหาคน: เคสขาด 1 คน (Golden Case)

Wave แรก = 201, 202 ผู้สมัครทั้งหมดมี 201, 202, 203

**Golden Path. 201 รับ, อนุมัติ**
`SOLVER_EXECUTED`, `OFFER_SENT` (201), `OFFER_SENT` (202), `OFFER_ACCEPTED` (201), `SAFETY_PASSED` (201), `APPROVAL_REQUESTED` (201), `APPROVAL_APPROVED` (201), `ASSIGNMENT_CREATED` (201), `CASE_RESOLVED`
Offer ของ 202 ยัง `SENT` จนเคส `RESOLVED` แล้วเป็น `CANCELLED` (อยู่ใน `cancelled_outreach_ids` ของ `CASE_RESOLVED`)
ลำดับเต็มของ Golden Path = ต1 ต่อด้วยบรรทัดนี้ รวม 13 แถว ต่างจาก Skeleton ตรงที่ `OFFER_SENT` มีสองแถว

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
Offer ของ 201 กับ 202 เป็น `TIMEOUT` ตามข้อ 6.9 เคสไม่มี Offer ค้างจึงส่ง Wave 2

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
201 ได้เข้าเวรและอยู่ต่อ เคสจบที่ `MANUAL_HANDOFF` (Q24, Q27)

ไม่มีกรณี "จัดเวรไม่ผ่าน" เพราะไม่มีการตรวจซ้ำตอนจัดเวร (Q38)

---

## 8. สิ่งที่แต่ละขั้นทำ

ข้อนี้เคยชื่อ "Stub ของแต่ละขั้น" ตอนนี้ทุกขั้นเป็นของจริงแล้ว ส่วนเดียวที่ยังเป็นตัวจำลองคือการส่งข้อความ LINE (`integrations/line/mock.py`) ข้อนี้อธิบายสิ่งที่โค้ดของแต่ละขั้นทำตอนนี้ เจ้าของแต่ละแถวอัปเดตแถวของตัวเองใน PR ที่เปลี่ยนโค้ดส่วนนั้น กติกาของรอบ 1 อยู่ข้อ 3 ถึง 7 และร่างรอบ 1 ข้อ 7, 8

| ขั้น | ทำอะไร | ตารางที่เขียน |
|---|---|---|
| Event | ของจริง ตรงกับข้อ 3 ตั้งแต่ PR M: รับ Event สี่ชนิดเป็น `RECEIVED` (PART A) แล้วปิด Window ทีละเวร ตรวจ Threshold และเปิดได้หนึ่งเคสต่อ Window (PART B) เวรของ Golden Case ตั้ง Window = 0 จึงยังเดินรวดเดียวใน Request เดียวเหมือน Skeleton | STAFFING_EVENTS, STAFF_UNAVAILABILITY, ROSTER_ASSIGNMENT, SHIFT, STAFFING_REQUIREMENTS (+ ROLE, SKILL), STAFFING_CASES |
| Gap | ของจริงตั้งแต่ PR 1b: `gap_service.assess_shift()` โหลด Requirement ปัจจุบันของเวร (Seam 10) และ Hard Policy `id=1` แล้วส่ง `required_staff`, `minimum_staff` และธง `preserve_minimum_staffing` ให้ `gap_calculator.calculate_gap()` ซึ่งคิด `effective_minimum` และ `headcount_gap` ตามข้อ 3.6 และเทียบ Role / Skill กับ Requirement ใช้ `result.has_gap` Handler `assess_staffing` เรียก `assess_shift()` ตัวเดียวกับการรับ Event แล้วบันทึกด้วย `gap_service.record_gap()`: `STAFFING_GAP` หนึ่งแถว (`effective_minimum` = ค่าที่ใช้คิดจริง, `computed_at = clock.now()`) และแถว Role / Skill ของทุกรายการใน Requirement รวมรายการที่ไม่ขาด จากนั้นเขียน `GAP_ASSESSED` โดย `role_gaps` / `skill_gaps` ใน payload เป็น List เรียงตาม ID ของ `{role_id หรือ skill_id, required_count, current_count, gap_count}` (ไม่ใช้ ID เป็น Key เพราะ JSON จะเปลี่ยนเป็นข้อความ) ถ้า `result.has_gap` เป็น False โยน `NoGapError` โดยไม่เขียนแถว เคสเป็น `FAILED` ตาม D11 (ข้อ 5 ไม่มี Transition ของกรณีนี้ และการรับ Event เปิดเคสเฉพาะเมื่อมี Gap ภายใต้ Lock ของเวรเดียวกัน จึงไม่เกิดใน Golden Path) | STAFFING_GAP (+ ROLE, SKILL) |
| Solver | ของจริงตั้งแต่ PR 2a: `optimization_service.create_plan()` ทำตามร่างรอบ 1 ข้อ 8.3 (1) Pool = พนักงานทุกคนที่ `home_ward_id` ตรงกับหอของเวรของเคส รอบ 1 จึงเป็น `SAME_WARD` ทุกคน (2) ล็อกแถว `STAFF` ของทั้ง Pool (`FOR NO KEY UPDATE` เรียงตาม `id`) จนรอบนั้น Commit (3) ตัดคนออกพร้อมรหัสเหตุผลหนึ่งรหัสต่อคน ใช้เหตุผลแรกตามลำดับนี้: ไม่ผ่าน Hard Rules (`hard_rule_service.check_staff()` รหัส = ข้อแรกที่ไม่ผ่านตามลำดับตารางในร่างรอบ 1 ข้อ 7.2), ปิด Gap ไม่ได้สักอย่าง (เกิดเมื่อ `headcount_gap = 0`: รหัส `SKILL_MISMATCH` ถ้าเคสขาด Skill ไม่งั้น `ROLE_MISMATCH`), เต็มเพดาน Offer (`availability_service.staff_at_offer_limit()` รหัส `OFFER_LIMIT_REACHED` ข้อ 6.7) (4) `working_time_service.capture()` เขียน `STAFF_WORKING_TIME_SNAPSHOT` ของคนที่เหลือ (Seam 14) (5) `optimization/solver.py` คิด Target = `ceil(gap * 11 / 10)` แล้วเลือกกลุ่มของ Wave แรกที่ปิด Target ครบและ `plan_penalty` ต่ำสุด คะแนนเท่ากันเลือกกลุ่มที่คนน้อยกว่า แล้ว `staff_id` น้อยกว่า Target ที่ผู้สมัครมีไม่พอถูกลดลงเท่าจำนวนคนที่ตรง (6) บันทึก Plan ที่มีทุกคนที่เหลือ ไม่ใช่เฉพาะกลุ่มของ Wave แรก `rank` = กลุ่มของ Wave แรกเรียงตาม `ranking_key` แล้วตามด้วยคนที่เหลือเรียงตาม `ranking_key` ไม่ข้ามเลข พร้อม `working_time_snapshot_id` ของแต่ละคน และแถว `CANDIDATE_ITEM_TARGET` ของกลุ่ม Wave แรก (Seam 13) `solver_status = FEASIBLE`, `solver_version = "weighted-v1"`, `objective_score` = `plan_penalty` ของกลุ่ม `input_snapshot` เก็บ `captured_at`, วันและต้นสัปดาห์ที่ใช้, Target, ค่าที่ใช้คิดของแต่ละคน และคนที่ถูกตัดพร้อมรหัส ถ้าไม่เหลือใครเลย: บันทึก Plan `INFEASIBLE` ไม่มี Item, Handler เขียน `SOLVER_EXECUTED` และ `MANUAL_HANDOFF` (`NO_FEASIBLE_PLAN`) แล้วเคสไป `MANUAL_HANDOFF` (T6) ไม่เป็น `FAILED` เคสที่ไม่มีแถว Gap ยังเป็น `FAILED` ตาม D11 (`GapNotFoundError`) PR 2b ลบกฎ Offer ค้างเดิมแล้ว Solver ตัดด้วย `OFFER_LIMIT_REACHED` เฉพาะคนที่เต็มเพดาน Offer ตามข้อ 6.7 คนที่มีแถว Roster `CANCELLED` บนเวรของเคสไม่ผ่าน `UNAVAILABLE` จึงไม่ถูกเสนอเวรเดิมอีก การค้นหากลุ่มข้ามผู้สมัครที่ปิด Target ชุดเดียวกับคนที่ถูกข้ามไปแล้ว และตัดกิ่งที่ต้นทุนขั้นต่ำสู้กลุ่มที่ดีที่สุดไม่ได้ ผลลัพธ์เท่ากับการลองทุกกลุ่ม | CANDIDATE_PLANS, CANDIDATE_ITEMS, CANDIDATE_ITEM_TARGET, STAFF_WORKING_TIME_SNAPSHOT |
| Outreach | PR 2b เลือกและส่ง Wave ตามข้อ 6.6 ผ่าน `wave_service.select_wave()` และ `outreach_service.send_offer()` หนึ่งแถวต่อคน ใช้ LINE Mock และไม่ Commit เอง | CANDIDATE_OUTREACH |
| Response | PR 2b ตอบ Accept / Reject ของ Offer ID ที่ระบุ ล็อก Offer → เคส → Staff ทั้ง Plan; ตอบรับเกินเป็นสำรอง ตรวจ Safety รายคนผ่าน bridge และเรียก `recompute()` แทน `resume()` กติกาเต็มอยู่ข้อ 6.10 และ 9.2 | CANDIDATE_OUTREACH, AUDIT_LOG |
| Safety | ของจริงตั้งแต่ PR 3: `safety_service.validate_accepted_candidate(db, case, outreach_id=)` ถูกเรียกรายคนใน Transaction ของการตอบรับ ผ่าน `outreach_service.promote_reserves()` ตรวจด้วย `hard_rule_service.check_items()` ตัวเดียวกับการเลือกคนของ Wave แล้วเขียน `SAFETY_VALIDATION` หนึ่งแถวตามร่างรอบ 1 ข้อ 7.4 ผ่าน: เขียน `SAFETY_PASSED` แล้ว `approval_service.create_request()` สร้างคำขออนุมัติและเขียน `APPROVAL_REQUESTED` ไม่ผ่าน: เขียน `SAFETY_FAILED` พร้อมรหัสทุกข้อ ตั้ง Offer เป็น `CANCELLED` ผ่าน `outreach_service.cancel_offer()` ไม่สร้างคำขอ และเคสเดินต่อตามข้อ 5.3 ข้อมูลผิดรูป (Offer ไม่ใช่ของเคส, Offer ไม่ใช่ `ACCEPTED`, Item ของเคสอื่นหรือเวรอื่น) ยังเป็น `FAILED` ตาม D11 ไม่ตรวจเพดาน Offer | SAFETY_VALIDATION, APPROVAL_REQUEST |
| Approval | PR 4 ตัดสินรายคน ตรวจ `404 → 403 → 409 → 422` เคสที่หยุดแล้วตอบ `409` ไม่อนุมัติต้องมีเหตุผลไม่ว่าง ยกเลิก Offer ของคนนั้นและเลื่อนสำรอง; อนุมัติสร้าง Roster ทันทีผ่าน `recompute(..., prepare=...)` ใน Savepoint ของ D11 แล้วแจ้งเคสอื่นหลัง Commit | APPROVAL_REQUEST |
| Roster | PR 4 ใช้ `roster_service.create_replacement(db, case, approval=request)` สร้างแถวของ Request ที่กำลังตัดสินโดยตรง ไม่ค้นหนึ่งแถวจากเคส ไม่ตรวจ Hard Rules ซ้ำ (Q38) การอนุมัติเขียน `ASSIGNMENT_CREATED` และยกเลิก Offer ของเคสอื่นที่ขัดกับเวรใหม่ด้วยกฎเวลา/ชั่วโมงชุดเดียวกับ Safety; `EXECUTING` ตรวจ Assigned Coverage ไม่สร้าง Roster เพิ่ม ยกเลิก Offer SENT ที่ยังไม่หมดเวลาและสำรอง (SENT ที่หมดเวลาคงไว้ให้ Job ตั้ง TIMEOUT) แล้วเขียน `CASE_RESOLVED` พร้อม `assignment_ids` / `cancelled_outreach_ids` | ROSTER_ASSIGNMENT |

`CANDIDATE_PLANS` และ `SAFETY_VALIDATION` อ้าง Policy แบบ NOT NULL จึงต้อง Seed `HARD_CONSTRAINT_POLICY` และ `SOFT_CONSTRAINT_POLICY` อย่างละ 1 แถว Solver ใช้ค่าของทั้งสอง Policy แล้วตั้งแต่ PR 2a

---

## 9. API

| Method | Path | ใช้ทำอะไร | เจ้าของ |
|---|---|---|---|
| POST | `/events` | รับ Event ตามข้อ 3 | คน 1 |
| GET | `/events/{event_id}` | สถานะของ Event และเคสของมัน | คน 1 |
| GET | `/cases/{id}` | สถานะเคส + Gap + Candidate | คน 1 |
| GET | `/cases/{id}/audit` | Timeline ของเคส | คน 1 |
| GET | `/demo/line-sim/offers?staff_id=` | Offer ที่ผู้สมัครได้รับ | คน 3 |
| POST | `/demo/line-sim/respond` | ผู้สมัครตอบ `ACCEPT` / `REJECT` | คน 3 |
| GET | `/approvals?pending=true` | รายการรออนุมัติ | คน 3 |
| POST | `/approvals/{id}/decision` | อนุมัติ / ไม่อนุมัติ | คน 3 |
| GET | `/roster?shift_id=` | ตารางเวรของเวรนั้น | คน 3 |
| POST | `/demo/reset` | ล้าง DB โหลด Golden Case ตั้ง Clock ใหม่ | คน 1 |
| POST | `/demo/clock/advance` | เลื่อน Clock ของ Demo แล้วปิด Offer ที่หมดเวลา เก็บตกเคสที่ค้าง และปิด Window ที่ถึงเวลา | คน 1 |
| POST | `/internal/merge-windows/close-due` | Route ภายในที่ Service ของ Job เรียก กันด้วย `X-Internal-Secret` ไม่ใช้ `X-Demo-User` | คน 1 |

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
| `api/routes/demo.py` | `/demo` (`/demo/reset` และ `/demo/clock/advance`) |
| `api/routes/internal.py` | `/internal` (เพิ่มและลงทะเบียนใน PR M สำหรับ Route ที่ Service ของ Job เรียก) |

Error สองตัวนี้ถูกแปลงเป็น HTTP ให้ที่เดียวใน `api/exception_handlers.py` Route ไม่ต้อง `try/except` เอง

| Exception | ตอบ | เกิดเมื่อ |
|---|---|---|
| `InvalidTransitionError` | `409` | `orchestrator.resume()` ปฏิเสธ เมื่อสองคำขอของเคสเดียวกันมาพร้อมกัน (Race): ทั้งคู่ผ่านการค้นแถวก่อนที่ตัวใดจะ Commit แล้วตัวที่สองถูกปฏิเสธ |
| `CaseNotFoundError` | `404` | ไม่มีเคส ID นั้น |

Handler นี้เป็นตาข่ายชั้นสุดท้าย ไม่ได้แทนการตรวจใน Route: คำขอซ้ำที่มา**หลัง**คำขอแรกเสร็จแล้ว ต้องถูกจับด้วยการค้นแถวของ Seam 3 และ 7 (ไม่เจอ Offer ที่ `SENT` หรือ Request ไม่ได้ Pending → `409`) ก่อนถึง `resume()`

ทั้งสองกรณี Route **ห้าม Commit** `get_db` ปิด Session ซึ่ง Rollback งานที่ Flush ไปแล้วให้เอง Exception อื่นตอบ `500` ตามปกติ

### 9.2 คำตอบที่เปลี่ยนในรอบ 1

คอลัมน์ "ตอนนี้" คือพฤติกรรมของ Skeleton แถวของ `/events`, `/demo/clock/advance`, `/internal/...` และ `/cases/{id}` เป็นไปตามคอลัมน์ "รอบ 1" แล้วตั้งแต่ PR M

| Route | ตอนนี้ | รอบ 1 |
|---|---|---|
| `POST /events` เวรที่ `merge_window_seconds = 0` | `201` `{event_id, event_status, case_id, case_status}` | เหมือนเดิมเมื่อเวรไม่มีเคสเดินอยู่: `PROCESSED` พร้อมเคส หรือ `IGNORED` ไม่มีเคส ถ้าเวรมีเคสเดินอยู่ ตอบ `RECEIVED`, `case_id = null` เพราะ Event ต้องรอเคสนั้นจบ (Q43) |
| `POST /events` กับ `event_type` อีกสามชนิด | `422` (`EventNotSupportedError`) | รับได้ Body และการตรวจของแต่ละชนิดอยู่ในข้อ 3 (Q40) |
| `POST /events` เวรที่ `merge_window_seconds > 0` | (ไม่มี) | `201` `{event_id, event_status: "RECEIVED", case_id: null, case_status: null}` เคสยังไม่เกิดจนกว่า Window ปิด |
| `POST /demo/clock/advance` (ใหม่) | (ไม่มี) | รับ `{seconds}` เลื่อน Clock ของ Demo แล้วปิด Window ที่ถึงเวลา และปิด Offer ที่หมดเวลา (ข้อ 6.9) ตอบเวลาใหม่ รายการเวรที่ปิด Window, Offer ที่หมดเวลา และเคสที่ถูกเก็บตก |
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
* `case_status` ในคำตอบเป็นค่าที่คำนวณจากตารางสถานะเคส (ข้อ 4): `WAITING_RESPONSE`, `WAITING_APPROVAL`, `RESOLVED`, `MANUAL_HANDOFF` หรือ `FAILED` (D11)
* `respond` รับคำตอบได้เมื่อ Offer ยัง `SENT` และ`clock.now() < expires_at` (Q24, ข้อ 6.9) แทนกติกาเดิมที่เคสต้องอยู่ `WAITING_RESPONSE` เคสที่จบที่ `RESOLVED` หรือ `MANUAL_HANDOFF` ยกเลิกเฉพาะ Offer `SENT` ที่ยังไม่หมดเวลา ส่วน `SENT` ที่ถึงหรือเลย deadline คงไว้ให้ Job ตั้ง `TIMEOUT` พร้อม audit (ข้อ 6.10)
* Offer ที่ถูก `CANCELLED` หรือ `TIMEOUT` แล้ว กดตอบได้ `409` ตามการตรวจเดิม
* เคสที่หยุดแล้ว: ถ้าเคสอยู่ใน `AUTOMATION_STOPPED_STATUSES` (`RESOLVED`, `UNRESOLVED`, `FAILED`, `MANUAL_HANDOFF`) ทั้ง `respond` และ `decision` ตอบ `409` ไม่เขียน DB กรณีที่เกิดจริงคือเคส `FAILED`: เคสล้มจาก Exception (D11) จึงไม่มีขั้นยกเลิก Offer และคำขออนุมัติที่เหลือ ถ้าไม่กันไว้ ผู้สมัครกดรับได้ และผู้อนุมัติกดอนุมัติแล้วได้ Roster ของเคสที่ล้มไปแล้ว Offer ของเคสแบบนี้ค้างเป็น `SENT` จนหมดเวลาตามข้อ 6.9 (ตอนหมดเวลา `recompute()` ไม่ทำอะไรกับเคสที่หยุดแล้ว ข้อ 5.3)
* Offer ที่ยัง `SENT` แต่กดรับไม่ได้ เพราะผู้ตอบรับ Offer ของเคสอื่นค้างอยู่ (ข้อ 6.8): ตอบ `409` (Q39) ข้อความต้องต่างจาก `409` ของ Offer ที่ถูกยกเลิก เพื่อให้หน้า `line-sim` บอกเหตุผลได้
* `decision` ตัดสินทีละคน เคสหนึ่งมีคำขออนุมัติค้างได้หลายแถวพร้อมกัน (Q24)
* การตรวจที่มาก่อนยังเหมือนเดิม: respond ตรวจ `outreach_id` (PR #30), decision ตรวจ `404 → 403 → 409` ตั้งแต่รอบ 2 PR W `403` มีสองเหตุ คือ Role ไม่ตรง แล้วจึงหอไม่ตรง (ข้อ 6.12)
* `reason` ตอนไม่อนุมัติ: บังคับและไม่ว่าง ไม่ส่งเหตุผลให้ตอบ `422` (Q13) เหตุผลที่เก็บของทั้งอนุมัติและไม่อนุมัติยาวได้ไม่เกิน 500 ตัวอักษร เหตุผลปฏิเสธตัดช่องว่างหัวท้ายก่อนตรวจและเก็บ ส่วนเหตุผลอนุมัติเก็บตามที่ส่งมา ตรวจความยาวใน Service หลัง `404 → 403 → 409` เกินเพดานตอบ `422` ก่อนเขียนคำตัดสิน
* Body ของ `respond`: `{"outreach_id": <id>, "response": "ACCEPT"}` หรือ `REJECT` `outreach_id` ต้องเป็น JSON Integer บวกในช่วง PostgreSQL bigint ไม่รับ Boolean, Float, String หรือฟิลด์อื่น เช่น `staff_id` ไม่ส่ง ID หรือส่งค่าผิดรูปแบบตอบ `422` ID ใน Body ไม่ใช่สิทธิ์ในการตอบ ผู้ตอบยังต้องเป็น Staff เจ้าของ Offer ตาม Header เสมอ
* Body ของ `decision`: `approved` เป็น JSON Boolean และ `reason` เป็น String หรือ `null` (ไม่ส่งเท่ากับ `null`) ไม่รับฟิลด์อื่น ตัวตนและ Role มาจาก `X-Demo-User` เท่านั้น ID ต้องเป็นจำนวนเต็มบวกในช่วง PostgreSQL bigint
* Service และ Route ไม่ Commit เองและไม่แก้ `case.status` Error จาก Orchestrator ต้องปล่อยให้ Request Rollback
* ถ้า Workflow ล้มเหลวหลังบันทึกคำตอบแล้วและ Orchestrator บันทึก `FAILED` ได้ ให้ตอบ `200` พร้อมสถานะ `FAILED` และเก็บคำตอบหรือผลอนุมัติไว้

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
| `POST /events` | `201` | `{event_id, event_status, case_id, case_status}` เมื่อ Event เป็น `IGNORED` หรือ `RECEIVED` ทั้ง `case_id` และ `case_status` เป็น `null` (ข้อ 9.2) คำขอที่ถูกปฏิเสธตอบ `401` / `403` / `404` / `409` / `422` ตามข้อ 3 |
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

**`GET /events/{event_id}`** (คน 1) ไม่ต้องมี `X-Demo-User` ไม่มี Event ID นั้น → `404` ID นอกช่วง `bigint` (1 ถึง 9223372036854775807) → `422`

```json
{"event_id": 2, "event_status": "RECEIVED", "case_id": null, "case_status": null}
```

* รูปเดียวกับคำตอบของ `POST /events` จึงใช้ชื่อ Field แบบมี Prefix ทั้งที่เป็น `GET`
* `case_status` คือสถานะปัจจุบันของเคส ไม่ใช่สถานะตอน Window ปิด

**`POST /demo/clock/advance`** (คน 1) ไม่ต้องมี `X-Demo-User` Body `{"seconds": 600}` เป็นจำนวนเต็ม 1 ถึง 604800 (หนึ่งสัปดาห์) ค่าอื่น → `422` และ Clock ไม่ขยับ Clock ยังไม่ถูกหยุด (ยังไม่เคย Reset ตั้งแต่ Backend เริ่ม) → `409`

```json
{
  "clock": "2026-10-09T21:10:00+07:00",
  "closed_windows": [
    {"shift_id": 1, "event_ids": [1, 2], "case_id": 1, "case_status": "WAITING_RESPONSE"}
  ],
  "timed_out_outreach_ids": [],
  "recovered_case_ids": []
}
```

* `timed_out_outreach_ids` คือ Offer ที่คำขอนี้ตั้งเป็น `TIMEOUT` (ข้อ 6.9) และ `recovered_case_ids` คือเคสที่รออยู่ซึ่งรอบเก็บตกคำนวณสถานะใหม่ให้ (ข้อ 5.3) ทั้งสองเรียงตาม ID และเป็น `[]` เมื่อไม่มี หน้า `demo/control` ใช้แสดงว่าการเลื่อน Clock ทำให้ Offer ไหนหมดเวลา Route ของ Job ไม่คืนสองค่านี้
* `closed_windows` มีหนึ่งรายการต่อเวรที่ปิด Window ในคำขอนี้ เรียงตาม `shift_id` Window ที่ไม่เปิดเคสมี `case_id` และ `case_status` เป็น `null` (Event ของมันเป็น `IGNORED`)
* `event_ids` คือ Event ทุกตัวของ Window นั้น รวมตัวที่ `IGNORED` ตาม Q44 ซึ่งไม่ได้ Link เข้าเคส

**`POST /internal/merge-windows/close-due`** (คน 1) Header `X-Internal-Secret` ไม่มี Body ตอบ `{"closed_windows": [...]}` รูปเดียวกับข้างบน `401` เมื่อ Secret ไม่มีหรือไม่ตรง `503` เมื่อ Backend ไม่ได้ตั้ง `INTERNAL_JOB_SECRET` (ข้อ 3.8)

**`GET /cases/{id}`** (คน 1) ไม่ต้องมี `X-Demo-User` ไม่มีเคส ID นั้น → `404` ID นอกช่วง `bigint` (1 ถึง 9223372036854775807) → `422`

```json
{
  "id": 1,
  "status": "WAITING_RESPONSE",
  "event_ids": [1],
  "shift_id": 1,
  "required_replacement_time": "2026-10-09T23:00:00+07:00",
  "created_at": "2026-10-09T21:00:00+07:00",
  "updated_at": "2026-10-09T21:00:00+07:00",
  "gap": {
    "id": 1,
    "effective_minimum": 5,
    "headcount_gap": 1,
    "computed_at": "2026-10-09T21:00:00+07:00",
    "roles": [{"id": 1, "name": "RN", "required_count": 5, "current_count": 4, "gap_count": 1}],
    "skills": [{"id": 1, "name": "ICU", "required_count": 2, "current_count": 2, "gap_count": 0}]
  },
  "assigned_count": 0,
  "candidates": [
    {"candidate_item_id": 1, "rank": 1, "staff_id": 201, "first_name": "Arunee", "last_name": "Demo",
     "source": "SAME_WARD", "outreach_status": "SENT", "stage": "OFFER_SENT"}
  ]
}
```

* `event_ids` คือ Event ทุกตัวของเคส อ่านจาก `STAFFING_EVENTS.case_id` เรียงตาม `id` แทน `event_id` ตัวเดียวของ Skeleton (Q36, PR M)
* `gap.effective_minimum` คือเป้าหมายจำนวนคนที่ใช้คิด Gap แถวนั้น (ข้อ 3.6) ไม่คืน `required_staff` กับ `minimum_staff`
  เพราะ Requirement ถูก UPDATE ในแถวเดิม ค่าที่อ่านได้อาจไม่ใช่ค่าตอนคิด (Q20)
* `gap` เป็น `null` จนกว่าขั้น `ASSESSING` จะบันทึก `STAFFING_GAP` ถ้ามีหลายแถวใช้แถวที่ `id` มากสุด
  ใน `roles` / `skills` ฟิลด์ `id` คือ Role ID / Skill ID
* `assigned_count` คือจำนวนคนที่เคสนี้จัดเข้าเวรแล้ว นับแบบเดียวกับ "ได้เข้าเวรแล้ว" ของข้อ 5.3 (`case_facts_service.assigned_staff_ids()`) เคสยังขาดคนอีก `max(gap.headcount_gap - assigned_count, 0)` หน้า `approvals` ใช้ค่านี้บอกว่าเคสของแต่ละคำขอยังขาดกี่คน (PR 5) ค่านี้นับเฉพาะจำนวนคน เคสที่ได้ 0 ยังรออนุมัติอยู่ได้เมื่อยังขาด Role หรือ Skill
* `candidates` เป็น `[]` จนกว่า Solver จะบันทึก Plan ใช้ Plan ที่ `id` มากสุดของเคส (Seam 1) เรียงตาม `rank`
* `outreach_status` เป็น `null` จนกว่าจะมี Outreach ของผู้สมัครคนนั้น ถ้ามีหลายแถวใช้แถวที่ `id` มากสุด
* `stage` คือขั้นของผู้สมัครในเคสนี้ตามข้อ 4.1 คำนวณตอนอ่าน ไม่มีคอลัมน์เก็บ ใช้ข้อแรกที่ตรงตามลำดับ: ได้เข้าเวรแล้ว (`ASSIGNED`), อนุมัติแล้ว (`APPROVED`), ไม่อนุมัติ (`APPROVAL_REJECTED`), Safety ไม่ผ่าน (`SAFETY_FAILED`), ไม่มี Offer (`NOT_CONTACTED`), Offer `ACCEPTED` และรออนุมัติ (`WAITING_APPROVAL`), Offer `ACCEPTED` อย่างเดียว (`ACCEPTED` คือสำรองตาม Q28), นอกนั้น `OFFER_` ตามด้วยสถานะของ Offer "ได้เข้าเวรแล้ว" กับ "รออนุมัติ" ใช้เงื่อนไขเดียวกับ `case_facts_service` คำขอที่ยัง Pending แต่ Offer ถูกยกเลิกจึงเป็น `OFFER_CANCELLED` Offer ที่ยัง `SENT` เลย `expires_at` แล้วแต่ Job ยังไม่ตั้ง `TIMEOUT` ยังเป็น `OFFER_SENT` ทั้งที่เคสไม่รอ Offer นั้นแล้ว (ข้อ 6.9) `stage` อ่านสถานะที่เก็บ ไม่ได้เทียบ `clock.now()`

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

* เป็น List ที่ชั้นบนสุด มีแถวที่ `case_id` ตรงกับเคส รวมกับแถวที่ `event_id` เป็น Event ของเคส เรียงด้วย `id` จากน้อยไปมาก (Seam 9, ข้อ 3.7) เคสที่ยังไม่มี Audit คืน `[]`
* `actor_name` ของ Actor ที่เป็นพนักงานคือ `str(staff.id)` เช่น `"105"`

**LINE Sim — `GET /demo/line-sim/offers?staff_id=201`**

PR 2b เพิ่ม `ward_id`, `ward_name`, `shift_start_at`, `shift_end_at`, `can_accept`, `can_reject`, `blocked_reason`, `cancellation_reason` และ `is_reserve` สถานะ `SENT` ของเคสที่ยังเดินอยู่กด Reject ได้ แม้ Accept ถูกพัก (`AWAITING_OTHER_CASE`) ส่วนเคสที่หยุดแล้วกดทั้งสองอย่างไม่ได้ ไม่ได้ใช้ `case_status == WAITING_RESPONSE` เป็นเงื่อนไขอีกต่อไป

PR O เพิ่ม `expires_at` ในคำตอบและคอลัมน์ Deadline ใน LINE simulator; Offer ที่ยัง SENT แต่หมดเวลาแสดง `blocked_reason = OFFER_EXPIRED`, `can_accept = false`, `can_reject = false` โดยอ่านอย่างเดียว ไม่รอ Job และไม่เทียบเวลาของ Browser ซึ่งต่างจาก Clock ของ Demo

PR 4 เพิ่ม `is_assigned`: Request ของ Item นี้อนุมัติแล้วและมี Roster `REPLACEMENT` ที่ `ASSIGNED` หรือ `COMPLETED` ของคน/เวรนี้ LINE simulator จึงแสดงข้อความยืนยันเวรได้แม้เคสยังรอผู้สมัครคนอื่น ไม่ใช่อ่านจาก `case_status` อย่างเดียว

* ต้องมี `X-Demo-User` ของ Staff ที่ Active และมี Actor (ไม่ผ่าน → `401`)
* `staff_id` เป็น Query ที่ต้องส่ง เป็นจำนวนเต็มบวกไม่เกิน PostgreSQL bigint; ไม่ส่งหรือไม่ถูกต้อง → `422`
* เป็นการอ่านของ Demo: เลือก Staff คนอื่นได้ผ่าน Query; `POST /respond` ยังใช้ตัวตนจาก Header เท่านั้น
* คืน JSON List ของ Outreach ที่ Item อ้าง Staff คนนั้น เรียง `id` จากน้อยไปมาก; ไม่มี Offer หรือไม่มี Staff ID นั้นคืน `[]`
* คืนทุก Status รวมประวัติ: `id`, `case_id`, `candidate_item_id`, `staff_id`, `proposed_shift_id`,
  `status`, `case_status`, `channel`, `sent_at`, `response_at`; เวลาที่มีค่าใช้ `+07:00`, เวลาที่ยังไม่มีเป็น `null`
* Offer ที่ตอบได้ต้องเป็น `SENT`, `clock.now() < expires_at` และเคสไม่อยู่ใน `AUTOMATION_STOPPED_STATUSES` (ข้อ 9.2)
  การอ่านไม่เปลี่ยน Status ของ Offer หรือเคส ผู้สมัครคนเดียวมี Offer ที่ตอบได้จากหลายเคสพร้อมกันได้ (ข้อ 6.8)
  `PENDING` ยังไม่ถูกใช้ Wave ของรอบ 1 เขียนแถวเป็น `SENT` ตอนส่งเลย
* Route / `outreach_service.list_offers()` ไม่เขียน DB, Audit, Commit, Explicit Flush หรือ Row Lock

**Seam 6 — `GET /approvals?pending=true`**

* ต้องมี `X-Demo-User` ของ Staff ที่ Active และมี Actor (ไม่ผ่าน → `401`)
* การอ่านไม่ตรวจ Role; การอนุมัติตรวจ Role ใน Seam 7
* คืน JSON List ที่ชั้นบนสุด เรียง `id` จากน้อยไปมาก ไม่ห่อด้วย `items` และไม่ใช้ `approval_id` แทน `id`
* แต่ละรายการมี `id`, `case_id`, `candidate_item_id`, `staff_id`, `proposed_shift_id`,
  `required_approver_role` (อาจเป็น `null`), `approval_mode`, `is_pending` และ `requested_at` (ISO 8601, `+07:00`)
  `staff_id` และ `proposed_shift_id` โหลดจาก Item ของ Request นั้นเพื่อให้ Frontend ระบุผู้สมัครและเวรได้
* ไม่ส่ง `pending` เท่ากับ `pending=true`; `pending=false` หรือค่า Boolean ไม่ถูกต้องตอบ `422`
* คืนทุก Pending Request ของเคสที่ยังเดินอยู่และยังมี Offer `ACCEPTED` ของเคส / Item เดียวกัน เคสเดียวมีได้หลายแถว หนึ่งแถวต่อผู้สมัครที่รออนุมัติ (ข้อ 4.2)
* Route / `approval_service.list_pending()` ไม่เขียน DB, Audit, Commit หรือ Explicit Flush และปิด Autoflush ระหว่างอ่าน คำขอของเคสที่หยุดแล้ว (`RESOLVED`, `FAILED`, `UNRESOLVED`, `MANUAL_HANDOFF`) ไม่อยู่ในรายการ แม้ยัง `is_pending = true`; เก็บแถวดังกล่าวไว้เป็นประวัติ ไม่สร้างผลอนุมัติ/ปฏิเสธขึ้นเอง คำขอที่ Offer ถูกยกเลิกก็ไม่อยู่ในรายการและไม่ถูกนับเป็น Pending Coverage แม้เคสยังเดินอยู่ (`case_facts_service.accepted_offer_for_request()` ใช้เงื่อนไขร่วมกัน)

**`GET /roster?shift_id=`** (คน 3)

```json
{
  "shift": {
    "id": 1,
    "ward_id": 1,
    "ward_name": "ICU",
    "shift_type": "NIGHT",
    "start_at": "2026-10-09T23:00:00+07:00",
    "end_at": "2026-10-10T07:00:00+07:00",
    "is_active": true
  },
  "assignments": [
    {
      "id": 5,
      "status": "CANCELLED",
      "assignment_type": "REGULAR",
      "candidate_source": null,
      "staff_id": 105,
      "first_name": "Sudarat",
      "last_name": "Demo",
      "staff_status": "ACTIVE",
      "role_id": 1,
      "role_name": "RN",
      "home_ward_id": 1,
      "home_ward_name": "ICU",
      "created_at": "2026-10-09T21:00:00+07:00",
      "updated_at": "2026-10-09T21:00:00+07:00"
    }
  ]
}
```

* ต้องมี `X-Demo-User` ของ Staff ที่ Active และมี Actor (ไม่ผ่าน → `401`) การอ่านไม่ตรวจ Role หรือ Ward:
  พนักงานคนใดก็อ่านเวรใดก็ได้ (ข้อ 12)
* `shift_id` ต้องส่งมาเสมอ และเป็นจำนวนเต็มในช่วง `bigint` (1 ถึง 9223372036854775807) ไม่ส่งหรือค่าไม่ถูกต้อง → `422`
* ไม่มี Shift ID นั้น → `404` เวรที่มีอยู่แต่ไม่มีแถว Roster ตอบ `200` พร้อม `assignments: []`
  ตรวจตามลำดับ `401` → `422` → `404`
* เวรที่ `is_active = false` ยังตอบ `200` พร้อมแถวของมัน ดูจาก `shift.is_active`
* `assignments` คือ**แถว** `ROSTER_ASSIGNMENT` ไม่ใช่รายชื่อคน คืนทุกสถานะตามที่เก็บ (`CANCELLED`, `PENDING_APPROVAL`,
  `COMPLETED` ด้วย) ไม่กรองและไม่รวมแถวซ้ำ คนเดียวกันมีได้หลายแถวในเวรเดียว เพราะตารางไม่มี UNIQUE ที่
  (`staff_id`, `shift_id`) เรียงด้วย `id` จากน้อยไปมาก
* Route ไม่นับ Coverage: คนที่นับได้คือคนไม่ซ้ำที่มีแถว `ASSIGNED` เท่านั้น (ข้อ 3) `PENDING_APPROVAL` ไม่นับ
  ตัวเลข Gap ดูจาก `GET /cases/{id}`
* `status` คือค่าที่เก็บใน DB ไม่คำนวณจากเวลา เวรที่จบไปแล้วจึงยังเป็น `ASSIGNED` ได้ (ยังไม่มีขั้นใดตั้ง `COMPLETED`
  ดูข้อ 12) ใช้ `shift.end_at` ดูว่าเวรจบแล้วหรือยัง
* `candidate_source` เป็น `null` สำหรับแถว `REGULAR`
* `staff_status` คือ `STAFF.status` คนที่ `INACTIVE` ยังอยู่ในรายการถ้ายังมีแถว Roster
  (Coverage ไม่กรอง `STAFF.status` ซ้ำ ตาม `database-schema.md`)
* `home_ward_id` / `home_ward_name` คือหอประจำของพนักงาน เทียบกับ `shift.ward_id` เพื่อดูว่ามาจากหออื่น
* ไม่ส่ง `email` / `password_hash` และยังไม่บอกว่าคนที่ `ASSIGNED` มี `STAFF_UNAVAILABILITY` ชนเวรหรือไม่ (ข้อ 12)
* ค่า `status` ที่ไม่อยู่ใน `RosterStatus` (คอลัมน์ไม่มี CHECK ตาม D8) ทำให้ตอบ `500` ไม่ซ่อนแถวนั้นเงียบ ๆ
* Route / `roster_service.get_shift_roster()` ไม่เขียน DB, Audit, Commit, Explicit Flush และไม่ล็อกแถว จึงไม่ขวางการรับ Event
  อ่านได้เฉพาะข้อมูลที่ Commit แล้ว แถวของผู้มาแทนจึงปรากฏพร้อมกับเคสเป็น `RESOLVED`

### 9.4 API และหน้าเว็บที่รอบ 2 จะเปลี่ยน

**[รอบ 2]** ทุกแถวเป็นกติกาที่ตกลงแล้ว ยังไม่มีโค้ด PR ที่ทำแถวไหนต้องเติมรูปของคำตอบลงข้อ 9.3 ใน PR เดียวกัน

| Route หรือหน้า | สิ่งที่เปลี่ยน | PR |
|---|---|---|
| `GET /cases?status=MANUAL_HANDOFF,FAILED` (ใหม่) | รายการเคสที่รอรับช่วง คืนเฉพาะเคสของหอที่ผู้เรียกเป็น Head Nurse เคส `FAILED` อยู่ในรายการแต่กดจัดการไม่ได้ ผลเมื่อไม่ส่ง `status` กำหนดใน PR H | H |
| Route จัดคนเอง และ Route ปิดเคสโดยไม่มีคนแทน (ใหม่) | Path และรูปของคำขอยังไม่ได้ตั้ง PR H ตั้งแล้วเขียนลงข้อนี้ ผู้เรียกที่ไม่ใช่ Head Nurse ของหอเดียวกับเวรได้ `403` การจัดที่ไม่ผ่าน Hard Rules ถูกปฏิเสธพร้อมรหัสกฎ | H |
| หน้า `/handoff` (ใหม่) | รายการเคส, รายการคนให้เลือกพร้อมรหัสกฎที่ทำให้จัดไม่ได้ของแต่ละคน, คำเตือนเมื่อคนที่เลือกมี Offer ค้างในเคสอื่น, ช่องเหตุผลของการปิดเคส เจ้าของหน้าคือคน 1 | H |
| `POST /approvals/{id}/decision` | ผู้กดที่ไม่ใช่ Head Nurse ของหอเดียวกับเวรได้ `403` พร้อม `detail` บอกเหตุ | W (ทำแล้ว) |
| `POST /approvals/{id}/decision` | กดเมื่อ `clock.now() >= expires_at` ได้ `409` | T |
| `GET /approvals` | เพิ่มเส้นตายของคำขอ (`expires_at`) | T |
| หน้า `approvals` | แสดงเส้นตาย | T2 |
| `POST /demo/clock/advance` และหน้า `demo/control` | เพิ่ม `timed_out_approval_request_ids` | T |
| `GET /cases/{id}` และหน้า `cases/[id]` | `candidates[].stage` มีค่าใหม่ `APPROVAL_TIMEOUT` และอ่านจากรอบล่าสุดของผู้สมัคร คนที่ได้เข้าเวรจากการจัดเองถูกนับใน `assigned_count` | T และ H |
| รายการ Offer ของหน้า `line-sim` | `cancellation_reason` มีค่าใหม่ `APPROVAL_TIMEOUT` และยังเป็น `CONFLICTING_ASSIGNMENT` เมื่อเสียให้การจัดคนเอง | T และ H |

---

## 10. Golden Case

### 10.1 สถานการณ์

พยาบาล RN ในหอ ICU แจ้งลาป่วยกะทันหันก่อนเวรดึก 2 ชั่วโมง ทำให้กำลังคนต่ำกว่าที่ต้องการ 1 คน ทักษะ ICU ยังครบ ระบบส่ง Offer ให้ผู้สมัครจากหอเดียวกันสองคนใน Wave แรก และได้คนแทนจากคนแรกที่ตอบรับ

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
* ทั้งสองเวรตั้ง `merge_window_seconds = 0` Event จึงถูกตัดสินใน Request ที่แจ้ง (ข้อ 3.2) เวรที่มี Window อยู่ใน Scenario ของ Test เท่านั้น (ข้อ 3.10)

**STAFFING_REQUIREMENTS**
* 1 = shift 1, `required_staff = 5`, `minimum_staff = 4`, ROLE: RN = 5, SKILL: ICU = 2
* 2 = shift 2, `required_staff = 1`, `minimum_staff = 1`, ROLE: RN = 1, ไม่มี SKILL

Golden Case ใช้ `HARD_CONSTRAINT_POLICY(id=1).maximum_patients_per_nurse = 2` จาก Seed
เพื่อให้ผู้ป่วย 10 คนต้องการพยาบาล 5 คน และผู้ป่วย 2 คนต้องการ 1 คน
ค่านี้เป็น Ratio เดียวทั้งโรงพยาบาลสำหรับ Skeleton ไม่ใช่ค่า Auto-approval
`required_staff` เป็นจำนวนคนที่ต้องการตามภาระงาน ค่า Seed ตรงกับสูตร `ceil(patient_count / patients_per_nurse)`
และ `minimum_staff` เป็นจำนวนขั้นต่ำคงที่ของเวร รอบ 1 ใช้ทั้งสองค่าตัดสิน Headcount Gap ผ่าน `effective_minimum` (ข้อ 3.6)
เวร 1: `max(5, 4) = 5` ผลของ Golden Case จึงเท่าเดิม
ส่วน `STAFFING_REQUIREMENT_ROLE` / `STAFFING_REQUIREMENT_SKILL` ใช้คำนวณ Role / Skill Gap

**ROSTER_ASSIGNMENT**
* 101–105 ในเวร 1: `ASSIGNED`, `REGULAR`
* 202, 203 ในเวร 2: `ASSIGNED`, `REGULAR` (เกิน Requirement 1 คน)

**ACTORS** 6 ตัวตาม `ActorName` + 1 ตัวต่อพนักงานแต่ละคน

**Policy** อย่างละ 1 แถว แต่ละตารางใช้ `id = 1`, `version = "demo-stub-v1"`

* `HARD_CONSTRAINT_POLICY`: พัก 11 ชม., วันละไม่เกิน 12 ชม., สัปดาห์ละไม่เกิน 52 ชม., `maximum_patients_per_nurse = 2`
* `SOFT_CONSTRAINT_POLICY`: ค่า Seed ของรอบ 1 ตามร่างรอบ 1 ข้อ 8.3: `candidate_count_weight = 1000`, `candidate_source_weight = 200`, `workload_imbalance_weight = 1`, `consecutive_shift_weight = 5`, `projected_overtime_weight = 2`, `roster_change_weight = 300`, `candidate_source_priority = ["SAME_WARD", "FLOAT_POOL", "CROSS_WARD"]` และ `optimization_priority = ["MIN_CANDIDATE_COUNT", "CANDIDATE_SOURCE", "WEEKLY_WORKLOAD_FAIRNESS", "MIN_CONSECUTIVE_SHIFT", "MIN_PROJECTED_OVERTIME"]` (ป้ายลำดับ ไม่เข้าสูตร)
* `APPROVAL_POLICY`: `ratio = 2`, `incoming_count = 10` ตามข้อตกลงทีม แต่ Golden Path ใช้ MANUAL approval จึงยังไม่ใช้ค่าเหล่านี้ตัดสินอัตโนมัติ

### 10.3 ผลที่คาดหวัง

| ขั้น | ผล |
|---|---|
| ก่อนลา | RN 5/5, ICU 2/2 (101, 102) ไม่มี Gap |
| 105 แจ้งลา | Event `PROCESSED`, `STAFF_UNAVAILABILITY` ของ 105 (`UNPLANNED_LEAVE`, `D 23:00` – `D+1 07:00`), Roster ของ 105 → `CANCELLED`, เปิดเคส |
| Gap | `headcount_gap = 1`, RN ขาด 1, ICU ไม่ขาด |
| Solver | Plan มี 201, 202, 203 ตามลำดับ กลุ่มของ Wave แรกคือ 201 กับ 202 (`plan_penalty` = 2023 เท่ากับกลุ่ม 201 กับ 203 จึงเลือก `staff_id` น้อยกว่า) 201 ได้แถว `ROLE` กับ `HEADCOUNT` แบบ `PRIMARY` และ 202 แบบ `RESERVE` |
| Outreach | Wave แรกคือ 201 กับ 202 (Target = จำนวนคน 2, RN 2) Offer ทั้งสองแถวเป็น `SENT` |
| 201 ตอบรับ | ผ่าน Safety ของ 201 ทันที เคสรออนุมัติ Offer ของ 202 ยัง `SENT` |
| 900 อนุมัติ | Roster ของ 201 `ASSIGNED` + `REPLACEMENT` สร้างตอนอนุมัติ เคส `RESOLVED` Offer ของ 202 เป็น `CANCELLED` RN 5/5 อีกครั้ง |

ตารางนี้เป็นผลของรอบ 1 แถว Outreach ลงไปเป็นแบบนี้ตั้งแต่ PR 2b, 3 และ 4 เข้า (PR #43) ใน Skeleton ระบบส่ง Offer ให้ 201 คนเดียว

### 10.4 ข้อมูลเผื่อ Test อื่น (ใช้ Seed เดียวกัน)

* **Event ที่ไม่มี Gap:** 203 ส่ง `STAFF_UNAVAILABLE` ของเวร 2 → สร้าง `STAFF_UNAVAILABILITY` (`UNPLANNED_LEAVE`), Roster ของ 203 → `CANCELLED`, 202 ยังครบ RN 1/1 → Event `IGNORED` ไม่มีเคส
* **กรณีอื่นของรอบ 1** (ปฏิเสธ, Safety ไม่ผ่าน, ไม่อนุมัติ, Offer หมดเวลา, Merge Gap) ใช้ไฟล์ Scenario แยก รายการอยู่ร่างรอบ 1 ข้อ 9.1 และลำดับ Audit ที่คาดหวังอยู่ข้อ 7.3

---

## 11. ลำดับเหตุการณ์ของ Golden Path

```
[Demo Control]  POST /events   (X-Demo-User: 105, STAFF_UNAVAILABLE, shift 1)
   Event PROCESSED → OPEN → ASSESSING → OPTIMIZING → OUTREACH → WAITING_RESPONSE   (หยุด)

[LINE Sim]      POST /demo/line-sim/respond   (X-Demo-User: 201, outreach_id จาก GET offers, ACCEPT)
   → WAITING_APPROVAL   (Safety ของ 201 ตรวจใน Request นี้ เคสไม่ผ่าน SAFETY_VALIDATION)   (หยุด)

[Approvals]     POST /approvals/{id}/decision   (X-Demo-User: 900, approved = true)
   → EXECUTING → RESOLVED                                                          (จบ)
```

Test ที่ยืนยัน Flow นี้: `backend/tests/e2e/test_workforce_recovery.py` ต้องผ่านทุก PR ที่เข้า `staging`

---
## 12. เรื่องที่ทำภายหลัง

ข้อนี้เก็บเฉพาะเรื่องที่ยังไม่ได้ทำ เรื่องที่รอบ 1 ทำแล้วถูกย้ายออก ดูรายการท้ายตาราง เรื่องที่รอบ 1 ตั้งใจเลื่อนออกไปพร้อมรอบที่วางไว้อยู่ร่างรอบ 1 ข้อ 1.2

| เรื่อง | หมายเหตุ |
|---|---|
| การใช้ `PENDING_APPROVAL` ใน Roster | ค่ามีใน Enum แล้ว แต่ยังไม่ใช้ รอบ 1 รองรับ Gap > 1 และหลายเคสพร้อมกันด้วยการสร้าง Roster เป็น `ASSIGNED` ตอนอนุมัติ ยังไม่มีงานที่กำหนดให้ใช้ค่านี้ |
| การตั้ง Roster เป็น `COMPLETED` | ยังไม่มีขั้นใดเขียน เวรที่จบแล้วจึงยังเป็น `ASSIGNED` ใน `GET /roster` |
| สิทธิ์อ่าน Roster ตาม Ward | Skeleton ให้ Staff ที่ Active ทุกคนอ่าน `GET /roster` ได้ทุกเวร การจำกัด เช่น Head Nurse อ่านได้เฉพาะหอของตัวเอง รอ Login จริง แล้วตอบ `403` |
| ธง "อยู่เวรแต่ไม่พร้อม" ใน `GET /roster` | คนที่ `ASSIGNED` แต่มี `STAFF_UNAVAILABILITY` ชนเวร (รวม `end_at = NULL`) ใช้กติกาของรหัส `UNAVAILABLE` ใน `domain/constraints/` ร่วมกัน (กติกาข้อ 3 เดิมของ `availability_service` ลบแล้วใน PR 3) Golden Case สร้างสถานะนี้ไม่ได้ เพราะการรับ Event ยกเลิก Roster ใน Transaction เดียวกับการลา |
| `GET /roster?staff_id=` | ตารางเวรของพนักงานหนึ่งคน เพิ่มเป็น Filter ของ Route เดิม ไม่ใช่ Path ใหม่ |
| `NO_SHOW` | ตรวจ check-in ใน `ATTENDANCE` หลัง `SHIFT.start_at` + เวลาผ่อนผัน (สมมติ 15 นาที) แล้วสร้าง `STAFF_UNAVAILABILITY` + Event `STAFF_UNAVAILABLE` ทีละเวร |
| แก้ `end_at` ของ `STAFF_UNAVAILABILITY` | กลับเร็ว / หยุดนานกว่าที่บันทึก / ใส่วันกลับเมื่อเคยเป็น NULL → Audit `UNAVAILABILITY_UPDATED` |
| Auto-Approval | Future feature: activate when the nurse-to-patient ratio exceeds twice the ward's required ratio (`ratio = 2`). `incoming_count` refers to staff awaiting approval by the head nurse or nurse supervisor (policy value = 10); its comparison rule remains to be defined. Skeleton uses MANUAL approval. |
| รูปแบบ `required_approver_role` | Skeleton เก็บ `ROLE.id` ของ HEAD_NURSE ไปก่อน |
| LangGraph | ดูทางเลือกในเอกสารแยก |

เรื่องที่ย้ายออกเพราะรอบ 2 ตกลง Contract แล้ว (โค้ดเข้าตาม PR ที่ระบุ)

| เรื่อง | ทำใน | ตอนนี้อยู่ข้อ |
|---|---|---|
| Timeout ของการอนุมัติ | รอบ 2 PR T | 6.13 |
| การจัดการเคสหลัง `MANUAL_HANDOFF` | รอบ 2 PR H | 6.12 |
| Solver แบบ OR-Tools | รอบ 2 PR B | 6.14 |

Escalation ไม่มีเป็นฟีเจอร์แยก การส่งเคสไป `MANUAL_HANDOFF` ให้ Head Nurse รับช่วงคือ Escalation ของระบบนี้ (R2-Q8) ส่วน Auto-Approval ยังอยู่ในตารางข้างบน ไม่ทำในรอบ 2

เรื่องที่ย้ายออกเพราะรอบ 1 ทำแล้ว

| เรื่อง | ทำใน | ตอนนี้อยู่ข้อ |
|---|---|---|
| การรวม Event และ `case_id` ใน `STAFFING_EVENTS` | PR M | 3.2 |
| Event กลุ่มภาระงาน (`PATIENT_SURGE`, `REQUIREMENT_CHANGED`) | PR M | 3.4 |
| Timeout ของ Offer ใช้ Service ของ Job ตัวเดียวกับ Merge Gap ไม่ใช้ Celery | PR O | 6.9 |

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
| 2026-10-10 | ขั้นที่ 4 Seam 6: เพิ่ม `GET /approvals?pending=true` และ `approval_service.list_pending()`; คืน Pending List เรียง ID, ใช้ Demo Auth, ระบุ Response Fields และเพิ่ม Integration Tests | คน 3 |
| 2026-10-10 | ตามรีวิว Seam 6: ไม่ปิด Pending List เมื่อเคสมี Request ซ้ำ เพิ่ม `staff_id` / `proposed_shift_id` จาก Item และเวลา `+07:00`; จัดเอกสารเป็น Bullet List และ Test ผ่าน Main App | คน 3 |
| 2026-10-10 | ขั้นที่ 4 Seam 7: เพิ่ม Route / Schema / `approval_service.decide()` ตรวจ `404 → 403 → 409 → 422`, ล็อก Request กันอนุมัติซ้ำ, เขียน Audit และ `resume(EXECUTING)` | คน 3 |
| 2026-10-10 | ตามรีวิว Seam 7: รวม staging คืนเจ้าของ Seam 8 ใช้ `MAX_BIGINT` และล็อก Request แบบ `FOR NO KEY UPDATE`; Test ใช้ Main App และ Error Handler ตัวจริง | คน 3 |
| 2026-10-10 | ตามรีวิว Seam 7 รอบล่าสุด: ย้าย Schema การตัดสินใจมา `schemas/approval.py`, เพิ่มลำดับ Lock Request ก่อน Case ในข้อ 6.2 และ Test อนุมัติแล้วหายจาก Pending List; ระบุว่า Seam 8 เป็นงานคน 3 ใน PR #18 และวางรูปแบบ GET Seam 6 ในข้อ 9.3 | คน 3 |
| 2026-10-10 | ขั้นที่ 4 Seam 8 (คน 3 รับงานกลับ): สร้าง Roster จาก Request ที่อนุมัติหนึ่งแถวพอดี ตรวจ Plan / Shift ของ Item; Handler เขียน `ASSIGNMENT_CREATED`, `CASE_RESOLVED` และให้ Orchestrator เปลี่ยนสถานะ / Commit; เพิ่ม Test Contract และ D11 Rollback | คน 3 |
| 2026-10-10 | ตามรีวิว Seam 8: เช็ก Availability ซ้ำก่อนสร้าง Roster ด้วยกติกาเดียวกับ Safety; เปลี่ยนเป็น `FAILED` เมื่อผู้สมัครไม่พร้อมโดยไม่สร้าง Roster ใหม่และเก็บผลอนุมัติไว้ เพิ่ม Regression Tests | คน 3 |
| 2026-10-10 | Gap Snapshot: `STAFFING_GAP` เพิ่ม `patient_count` และ `patients_per_nurse` (NOT NULL) พร้อม CHECK `ck_staffing_gap_patients_per_nurse_valid` กติกาเดียวกับ Policy; Migration `c4d7e19a52f3` ไม่ Backfill และหยุดถ้ามีแถวเก่า; ข้อ 3 และข้อ 8 ระบุว่าผู้เขียนแถว Gap ต้องใส่ค่าที่ใช้คำนวณจริง; Guard ของ Migration รันใน SQL จึงใช้กับ `alembic upgrade --sql` ได้ | คน 1 |
| 2026-10-10 | ขั้นที่ 4 Gap: Handler `assess_staffing` ตัวจริงแทน Stub บันทึก `STAFFING_GAP` (+ Role, Skill) พร้อม Snapshot ผ่าน `gap_service.record_gap()` และเขียน `GAP_ASSESSED`; ข้อ 8 ระบุรูปแบบ `role_gaps` / `skill_gaps` ใน payload และ `NoGapError` เมื่อเวรไม่ขาดคน | คน 1 |
| 2026-10-10 | ขั้นที่ 4 LINE Sim Read: เพิ่ม `GET /demo/line-sim/offers?staff_id=` และ `outreach_service.list_offers()` คืนประวัติ Offer ของ Staff ที่เลือกพร้อม Case Status และเวลา `+07:00`; ใช้ Demo Auth และไม่เขียนข้อมูล เพิ่ม Integration Tests | คน 3 |
| 2026-10-10 | ขั้นที่ 4 อ่าน Roster: เพิ่ม `GET /roster?shift_id=` และ `roster_service.get_shift_roster()`; ข้อ 9.3 ระบุรูปแบบคำตอบ `{shift, assignments}` ลำดับ `401` → `422` → `404` คืนทุกสถานะเรียงด้วย `id` และไม่นับ Coverage; `ShiftNotFoundError` ย้ายไป `app/domain/errors.py`; ข้อ 12 เพิ่มการตั้ง `COMPLETED`, สิทธิ์อ่านตาม Ward, ธงไม่พร้อม และ `?staff_id=` | คน 3 |
| 2026-10-10 | Issue #26: LINE Sim ต้องส่ง `outreach_id` ของ Offer ที่เห็น; Service เทียบ ID หลังล็อกและก่อนเขียนข้อมูล ตอบ `409` เมื่อ Offer เปลี่ยน Frontend ส่ง ID และ Refresh หลัง Conflict; เพิ่ม Test Stale Offer, สิทธิ์ผู้ตอบ, Validation และคง Race / E2E | คน 3 |
| 2026-10-12 | รอบ 1 PR 0: ย้ายกติกาจาก `docs/round1/round1-contract-draft.md` เข้าข้อ 3 (Window, Threshold, Event สี่ชนิด, `effective_minimum`), ข้อ 4 และ 5 (สถานะรายคน, T1 ถึง T7, `decide_status()` / `recompute()`), ข้อ 6.4 ถึง 6.11 (Seam, Wave, เพดาน Offer, หลาย Offer ต่อคน, Timeout ของ Offer, ลำดับ Lock), ข้อ 7 (Audit ทุก Action และลำดับของแต่ละกรณี) และข้อ 9.2 (คำตอบของ API ที่เปลี่ยน แทนส่วน `422` เดิม); `transitions.py` เพิ่ม T1 ถึง T7 โดยสองเส้นของ `SAFETY_VALIDATION` ยังอยู่; `enums.py` เพิ่ม `AuditAction` 3 ค่า และ `EntityType` 2 ค่า; ยังไม่เปลี่ยนพฤติกรรม | คน 1 |
| 2026-10-12 | รอบ 1 PR 0 ตามรีวิว: ข้อ 8 เขียนใหม่ให้ตรงกับโค้ดปัจจุบัน ทุกแถวบอกพฤติกรรมของ Skeleton และ PR ที่จะมาเปลี่ยน; เพิ่มข้อ 8.1 เก็บการรับ Event ของ Skeleton จนกว่า PR M เข้า; Seam 5 กำหนดให้ PR 3 เป็นเจ้าของการสร้าง `APPROVAL_REQUEST` และการเขียน `APPROVAL_REQUESTED` ผ่านฟังก์ชันใน `approval_service`; PR 3 ลบการเรียก `assert_available()` ใน `roster_service` ด้วย; ตารางสถานะของรอบ 1 เพิ่ม PR 1b, 2a, O; `MANUAL_HANDOFF` มี `skipped` ใน payload | คน 1 |
| 2026-10-12 | รอบ 1 PR 1b: `calculate_gap()` รับ `required_staff`, `minimum_staff` และธง `preserve_minimum_staffing` แทน `patient_count` และ `patients_per_nurse`; เพิ่ม `required_staff_for()` (สูตร `ceil`) และ `effective_minimum_for()`; `STAFFING_GAP` เพิ่ม `effective_minimum` และลบ `patient_count`, `patients_per_nurse` พร้อม CHECK (Migration `d5e8f20b63a4` ไม่ Backfill ทั้งขาขึ้นและขาลง หยุดถ้ามีแถวเก่า ให้ `make reset`); เพิ่ม `gap_service.get_case_gap()` สำหรับ Solver และ Safety (Seam 11); `GET /cases/{id}` คืน `gap.effective_minimum`; ข้อ 8 แถว Gap และข้อ 8.1 ปรับตาม | คน 1 |
| 2026-10-12 | รอบ 1 PR 1a: ตัวตรวจ Hard Rules 11 รหัสใน `domain/constraints/` (`codes.py`, `context.py`, `hard_rules.py`, `evaluator.py`) เป็น Pure Function คืนรหัสที่ไม่ผ่านทุกข้อเรียงตามตารางในร่างรอบ 1 ข้อ 7.2 พร้อม `checked_rules` และ `details` ตามข้อ 7.4 ยังไม่มีใครเรียก Solver, Safety และ `availability_service` ยังทำงานตามข้อ 8 จนกว่า PR 2a และ 3 เข้า; Migration `e1f5a8b3c6d2` เพิ่ม `HARD_CONSTRAINT_POLICY.maximum_consecutive_shifts` (Seed และ Backfill = 7) และ CHECK ของ `ATTENDANCE.overtime_minutes` ทุกคน `make reset` หลัง merge | คน 2 |
| 2026-10-12 | รอบ 1 PR 1a ตามรีวิว: ผู้สมัครที่ไม่ได้ถูกเลือกมาเติม Role ใด (เติมจำนวนคนหรือ Skill อย่างเดียว) ต้องมี Role ที่ Requirement ของเวรมี ผู้เรียกตัวตรวจส่ง Role ของ Requirement เป็น `target_role_ids` ไม่ส่ง Set ว่าง (ร่างรอบ 1 ข้อ 7.2 Q55 และ 8.3) Logic ของตัวตรวจไม่เปลี่ยน เพิ่ม Test ของกรณีนี้; ตารางสถานะของรอบ 1 ระบุว่าตัวตรวจมีแล้วแต่ยังไม่มีผู้เรียก | คน 2 |
| 2026-10-12 | รอบ 1 PR 1a ตามรีวิวรอบสอง: รวม `staging` หลัง PR 1b เข้า; Migration `e1f5a8b3c6d2` เปลี่ยนไปต่อจาก `d5e8f20b63a4` จึงเหลือ Head เดียว; `SOURCE_WARD_MINIMUM_VIOLATION` คิดเป้าหมายของเวรต้นทางด้วย `gap_calculator.effective_minimum_for()` ตัวเดียวกับการคิด Gap แทนสูตรที่เขียนซ้ำ | คน 2 |
| 2026-10-12 | รอบ 1 PR 1c: เพิ่ม `OUTREACH_POLICY`, Migration และ Seed เพดาน 3 Offer; เพิ่ม `get_outreach_policy()` กับ `staff_at_offer_limit()` นับ `SENT` / `ACCEPTED` บนเคสที่ยังเดินอยู่ข้ามทุก Plan; ยังไม่ต่อกับ Solver / Wave และยังไม่มี Timeout | คน 3 |
| 2026-10-12 | รอบ 1 PR 1c ตามรีวิว: รวม `staging` หลัง PR 1b และ 1a; Migration `d91a6c8e203f` ต่อจาก `e1f5a8b3c6d2` ตามลำดับ 1b → 1a → 1c เหลือ Head เดียว; ตารางสถานะระบุว่า Policy และฟังก์ชันเพดานมีแล้ว; Schema ระบุ 31 ตารางและ Migration ครบ; ให้ `make reset` หลัง merge เพื่อโหลด Policy ของ Demo | คน 3 |
| 2026-10-12 | รอบ 1 PR S: เพิ่ม `domain/workflow/case_status.py` (`CaseFacts`, `decide_status()`, `GapNeeds`, `GapFiller`, `gap_closed()`), `services/case_facts_service.py` (`load_case_facts()`, `has_open_offer()`, `staff_waiting_on_another_case()`) และ `orchestrator.recompute()`; ข้อ 5.3 ระบุว่าใครนับเป็นได้เข้าเวรแล้ว / รออนุมัติ, นิยามของ Offer ที่ถูกพักในโค้ด และความล้มเหลวใน `recompute()` เป็น `FAILED` ตาม D11; Test ว่า `MANUAL_HANDOFF` จาก Handler หยุดรอบเอง และ T1 / T4 เข้า `OUTREACH` แล้วไม่วน; ยังไม่มีผู้เรียก จึงยังไม่เปลี่ยนพฤติกรรม; Fixture `stub_handlers` ยังมี Stub ของ `SAFETY_VALIDATION` จนกว่า PR 3 ลบ Handler นั้น | คน 1 |
| 2026-10-12 | รอบ 1 PR S ตามรีวิว: `CaseFacts` เพิ่ม `has_uncontacted_candidate`, `has_pending_approval`, `has_paused_offer` และ `decide_status()` เพิ่มกฎข้อ 5 ถึง 7 ให้เคสที่ไม่เหลือใครให้ติดต่อแต่ยังมีสิ่งที่ต้องรออยู่ที่จุดรอเดิมโดยไม่เขียนอะไร; เคสที่ได้คนครบตอนอยู่ `WAITING_RESPONSE` ผ่าน `WAITING_APPROVAL` ไป `EXECUTING` ไม่เป็น `FAILED`; "ได้เข้าเวรแล้ว" นับแถว Roster ที่ `COMPLETED` ด้วย; Offer ที่ถูกพักไม่นับ Offer ที่คำขออนุมัติตัดสินแล้วหรือ Safety ไม่ผ่าน โดยไม่พึ่งว่า Offer ถูกตั้งเป็น `CANCELLED`; ตัวอ่านปิด Autoflush เอง; ลบ `GapNeeds` และใช้ `gap_service.load_skill_sets()` ร่วมกัน; ข้อ 5.3 ระบุข้อจำกัดของการนับและเหตุที่ `recompute()` ยังรันกับ Handler ของ Skeleton ไม่ได้ | คน 1 |
| 2026-10-12 | รอบ 1 PR M: Migration `f2a6b9c4d7e1` (`SHIFT.merge_window_seconds`, `STAFFING_EVENTS.processed_at` + `case_id`, `AUDIT_LOG.event_id`, ลบ `STAFFING_CASES.event_id`) ทุกคนต้อง `make reset`; `event_service.receive_event()` เหลือ PART A และรับ Event สี่ชนิด; เพิ่ม `merge_window_service` (PART B), `domain/staffing/threshold.py`, `job_service`, `jobs/ticker.py` และ Service `job` ใน `docker-compose.yml`; Route ใหม่ `GET /events/{event_id}`, `POST /demo/clock/advance`, `POST /internal/merge-windows/close-due`; `audit_service.log()` รับ `event_id`; Case API ตอบ `event_ids` และ Timeline รวมแถวของ Event; ข้อ 3.4, 3.5, 3.7, 3.8 เพิ่มสิ่งที่กำหนดใน PR นี้ (`reported_by`, ลำดับการตรวจ, รหัส `reason` ของ `EVENT_IGNORED`, ชื่อ Header และ env ของ Secret); เพิ่มข้อ 3.10; ข้อ 7.1 กำหนด Key ของ payload; ลบข้อ 8.1; ข้อ 9.3 เพิ่มรูปแบบคำตอบของ Route ใหม่ | คน 1 |
| 2026-10-12 | รอบ 1 PR M ตามรีวิว: เพิ่ม CHECK `ck_staffing_events_processed_at_matches_status` ใน Migration `f2a6b9c4d7e1` และ Model; `POST /events` ตอบ `409` เมื่อเวรไม่มี `STAFFING_REQUIREMENTS` (ข้อ 3.5) เพราะ Window ของเวรนั้นปิดไม่ได้; `reason` ของ `ASSIGNMENT_CANCELLED` ยาวได้ไม่เกิน 500 ตัวอักษรและข้อ 3.4 ระบุว่าเป็นข้อความอิสระที่เก็บได้; ข้อ 3.9 ระบุว่า Window ที่ปิดไม่สำเร็จถูกลองใหม่ทุกรอบโดยไม่เลิกเอง; `jobs/ticker.py` ไม่ล้มเมื่อ Connection ถูกปิดกลางคำขอ และตรวจ `JOB_INTERVAL_SECONDS`; ชื่อ Role `HEAD_NURSE` ย้ายไป `core/constants.py` ที่เดียว | คน 1 |
| 2026-10-12 | รอบ 1 PR 2a: Solver ตัวจริงแทน Stub Pool = พนักงานของหอของเวร คัดด้วย Hard Rules ผ่าน `hard_rule_service` (Seam 12), อ่าน Gap ของเคส (Seam 11), เลือกกลุ่มของ Wave แรกด้วย `plan_penalty` และเรียง `rank` ด้วย `ranking_key`; เพิ่มตาราง `CANDIDATE_ITEM_TARGET`, `CANDIDATE_ITEMS.working_time_snapshot_id` และ `SOFT_CONSTRAINT_POLICY.candidate_source_weight` (Migration `f3a7c1d9e5b2` Backfill = 200); `working_time_service` เขียน `STAFF_WORKING_TIME_SNAPSHOT` (Seam 14); `fill_targets()` กับ `record_item_targets()` ให้ PR 2b ใช้ (Seam 13); Solver เรียกเพดาน Offer และเก็บกฎ Offer ค้างเดิมไว้ชั่วคราวจนถึง PR 2b (ข้อ 8 แถว Response); แถว Roster `CANCELLED` บนเวรที่เสนอทำให้ไม่ผ่าน `UNAVAILABLE`; Solver ไม่ได้ใครเลยเป็น `MANUAL_HANDOFF` ผ่าน T6 แทน `FAILED`; Seed ของ Weight เป็นค่าของรอบ 1; เพิ่ม Scenario `no_feasible_solution` และ `soft_constraint`; ทุกคน `make reset` หลัง merge | คน 2 |
| 2026-10-12 | รอบ 1 PR 2a: รวม `staging` หลัง PR M; Migration `f3a7c1d9e5b2` ต่อจาก `f2a6b9c4d7e1` เหลือ Head เดียว | คน 2 |
| 2026-10-13 | รอบ 1 PR 2b: ส่ง Offer เป็น Wave ตาม Target ของ Solver, เติมเฉพาะตำแหน่งที่ว่าง, Accept / Reject ระบุ Offer ID, สำรองและการเลื่อนสำรอง, หลาย Offer ต่อคนและการพัก Accept ข้ามเคส, เรียก `recompute()` หลังตอบและแจ้งเคสอื่นหลัง Commit; LINE simulator แสดงหอ เวลาเวร เหตุผล และสถานะสำรอง; เตรียม Safety bridge รายคนสำหรับ PR 3 และ preparation callback ภายใต้ D11; PR 3/4 ยังต้องเข้า branch รวมก่อน staging รายละเอียดที่ `docs/round1/pr-2b-handoff.md` | คน 3 |
| 2026-10-13 | ตามรีวิว PR 2b: เอกสารตรงกับเพดาน Offer และผู้เรียก recompute ปัจจุบัน; Target ของสมาชิก Solver ที่ยังไม่เคยติดต่อถูกแทนที่ก่อนส่งใน Wave ถัดไป; อ่าน Offer เป็นชุดพร้อมเหตุผลยกเลิก และซ่อนข้อความรออนุมัติเมื่อเคสหยุด | คน 3 |
| 2026-10-13 | รอบ 1 PR 3: Safety ตรวจรายคนตอนตอบรับด้วย `hard_rule_service.check_items()` บันทึกผลตามร่างรอบ 1 ข้อ 7.4; Safety ไม่ผ่านเขียน `SAFETY_FAILED` ตั้ง Offer เป็น `CANCELLED` และเคสเดินต่อ ไม่เป็น `FAILED`; ย้ายการสร้าง `APPROVAL_REQUEST` และ `APPROVAL_REQUESTED` ไป `approval_service.create_request()`; ลบสองเส้นของ `SAFETY_VALIDATION`, Handler `validate_safety`, `get_accepted_outreach()`, `assert_available()`, `unavailable_staff()` และ Exception สี่ตัว; เพิ่ม Scenario `safety_failure` | คน 2 |
| 2026-10-13 | รอบ 1 PR 4: อนุมัติ/ไม่อนุมัติรายคนพร้อมเหตุผล สร้าง Roster ทันทีใน Savepoint ของการตัดสิน เลื่อนสำรองและแจ้งเคสอื่นหลัง Commit; ปิดเคสเฉพาะเมื่อ Assigned ปิด Gap ครบ ยกเลิก Offer ของสำรอง/ที่ยัง SENT และ Offer ต่างเคสที่ขัดกับเวรใหม่; LINE simulator ใช้ is_assigned แสดงยืนยันเวรของคนที่อนุมัติแล้ว แม้เคสยังไม่จบ; Scenario head_nurse_reject และ Test สอง Connection สำหรับ Accept แข่งกับอนุมัติสุดท้าย | คน 3 |
| 2026-10-13 | ตามรีวิว PR 4: Pending List ไม่แสดงคำขอของเคสที่หยุดแล้ว รวมกรณีอนุมัติคนเดียวปิดทั้ง Headcount/Skill แต่คำขอคนอื่นยังค้างและกรณี D11; เหตุผลการตัดสินยาวได้ไม่เกิน 500 ตัวอักษร (`MAX_APPROVAL_REASON_LENGTH`) ตรวจทั้ง API และ Service ก่อนเขียน พร้อม Test ขอบเขต 500/501 | คน 3 |
| 2026-10-13 | ตามรีวิว PR 4 รอบเพิ่มเติม: คำขอใช้งานได้และนับ Pending Coverage เฉพาะเมื่อ Offer ของเคส / Item เดียวกันยัง ACCEPTED; ยกเลิก Offer แล้วเก็บคำขอเป็นประวัติ แต่กดตัดสินได้ 409 และเคสต่างหอเดินต่อได้; แยก Offer Conflict / Lock Retry Error, ใช้ query lock ร่วมกับ phantom check, ย้าย scheduling codes ขึ้น module และแจ้งเฉพาะผู้สมัครที่ยกเลิกในรอบนี้ | คน 3 |
| 2026-10-13 | ตามรีวิว PR 4 รอบ Minor: ตรวจความยาวเหตุผลใน Service แทน Schema เพื่อคง 404 → 403 → 409 → 422; เหตุผลปฏิเสธตัดช่องว่างก่อนตรวจ 500 ตัวอักษร; รายงานหรือผู้ใช้อื่นที่นับคำขอค้างต้องใช้ accepted_offer_for_request ไม่ใช่ is_pending อย่างเดียว; เพิ่ม Test ลำดับ error และเหตุผล 500 ตัวอักษรพร้อม whitespace | คน 3 |
| 2026-10-13 | รอบ 1 PR O: Migration a4b8c2d6e9f1 เพิ่ม offer_timeout_seconds (Seed 300) และ expires_at; backfill จาก sent_at + 300 วินาที ตรวจ SENT ต้องมี expiry; ส่ง Wave snapshot deadline เดียวกัน, ตอบหลัง deadline ได้ 409 ไม่เขียน, SENT ที่หมดเวลาไม่เติม open/paused offer และไม่นับ cap; Job ปิด TIMEOUT/Audit ราย Offer แล้ว recompute, recovery sweep และปล่อย Window ต่อใน tick เดียวกัน; LINE simulator แสดง deadline; tests ครอบคลุมขอบเขตเวลา migration failure-isolation และ race กับ Job | คน 3 |
| 2026-10-13 | รอบ 1 PR 5: หน้า `approvals` มีช่องกรอกเหตุผลตอนไม่อนุมัติ (ไม่ว่าง ไม่เกิน 500 ตัวอักษร ส่งค่าที่ตัดช่องว่างหัวท้ายแล้ว) และคอลัมน์บอกว่าเคสของคำขอยังขาดกี่คน; `GET /cases/{id}` เพิ่ม `assigned_count` จาก `case_facts_service.assigned_staff_ids()` | คน 1 |
| 2026-10-13 | `POST /demo/clock/advance` คืน `timed_out_outreach_ids` และ `recovered_case_ids` เพิ่มจาก `closed_windows` และหน้า `demo/control` แสดงสองรายการนี้หลังเลื่อน Clock เพราะตั้งแต่ PR O การเลื่อน Clock ทำให้ Offer หมดเวลาได้ แต่หน้าเดิมบอกแค่เรื่อง Window; Route ของ Job ไม่เปลี่ยน | คน 1 |
| 2026-10-13 | รอบ 1 PR 6: `GET /cases/{id}` เพิ่ม `candidates[].stage` (ข้อ 4.1, 9.3) คำนวณตอนอ่านด้วยเงื่อนไขเดียวกับ `case_facts_service`; หน้า `cases/[id]` แสดงสถานะรายคน, ตารางผู้สมัครที่ถูกข้ามจาก `skipped` ใน Audit และ `effective_minimum` ของ Gap ไม่มี Migration | คน 2 |
| 2026-10-13 | ปิดรอบ 1: ส่วน "สถานะของรอบ 1" เปลี่ยนเป็นตาราง PR ที่เข้าครบแล้วพร้อมเลข PR; ข้อ 8 เปลี่ยนชื่อจาก "Stub ของแต่ละขั้น" เป็น "สิ่งที่แต่ละขั้นทำ" เพราะไม่เหลือ Stub นอกจาก LINE Mock; ข้อ 12 ย้ายเรื่องที่รอบ 1 ทำแล้วออก (รวม Event, Event กลุ่มภาระงาน, Timeout ของ Offer) เหลือ Approval Timeout; ตามรีวิว: เอาคำว่า "ไม่ใช่ Stub" ออกจากแถวของข้อ 8 และเขียนแถว Timeout ของการอนุมัติในข้อ 12 ให้ชัดว่ายังไม่มีการออกแบบ; ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-13 | รอบ 2 PR 0: ย้าย Contract ของรอบ 2 เข้าไฟล์นี้ตามร่างรอบ 2 (PR #50): เพิ่มส่วน "สถานะของรอบ 2", เส้น T8 (`MANUAL_HANDOFF` → `RESOLVED`) และ T9 (`MANUAL_HANDOFF` → `UNRESOLVED`) ในข้อ 5.1 และใน `transitions.py` พร้อม Test, ข้อ 6.12 เส้นออกจาก `MANUAL_HANDOFF`, ข้อ 6.13 Timeout ของการอนุมัติ, ข้อ 6.14 Solver แบบ OR-Tools, ข้อ 9.4 API ที่จะเปลี่ยน, Audit Action ใหม่สี่ตัว (`APPROVAL_TIMEOUT`, `MANUAL_ASSIGNMENT_CREATED`, `CASE_CLOSED_UNRESOLVED`, `OFFER_CANCELLED_BY_ASSIGNMENT`) และเหตุผล `SOLVER_TIMEOUT` ใน `enums.py`; ข้อ 12 ย้ายสามเรื่องออก; กติกาที่มีป้าย **[รอบ 2]** ยังไม่มีโค้ด; ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-13 | ตามรีวิว PR 0 ของรอบ 2: แก้ข้อ 4, 5.1, 5.2, 5.3 และ 6.12 ที่เขียนว่า T8 กับ T9 เป็นของ Head Nurse อย่างเดียว ให้ตรงกับข้อ 6.12 และแถว `CASE_CLOSED_UNRESOLVED` ของข้อ 7.1: T9 เดินได้โดยขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด และ T8 เดินโดย Route จัดคนเองที่เรียก Orchestrator ใน Transaction เดียวกัน Handler กับ `recompute()` ยังไม่เดินสองเส้นนี้; เพิ่มตารางข้อกำหนดที่ยังไม่มี Test พร้อม PR ที่ต้องมี Test ในส่วน "สถานะของรอบ 2"; ใส่เลข PR #52; เอาเส้นคั่นระหว่างข้อ 9.3 กับ 9.4 ออก; ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-13 | รอบ 2 PR W: การอนุมัติจำกัดหอ (R2-Q21, R2-Q53) `approval_service.decide()` รับ `home_ward_id` ของผู้กด เทียบกับ `ward_id` ของเวรด้วย `domain/staffing/ward_authority.manages_ward()` ถ้าไม่ตรงตอบ `403` ก่อนการตรวจ `409`; ข้อ 6.12, 9.2 และ 9.4 แก้ตาม; `GET /approvals` ไม่เปลี่ยน; ข้อมูล Seed มีหอเดียว ผลของ Test เดิมจึงไม่เปลี่ยน | คน 1 |
