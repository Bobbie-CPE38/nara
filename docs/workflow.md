# Workflow Contract

> ข้อตกลงร่วมของทีม ใช้คู่กับ `backend/app/domain/enums.py` และ `docs/database-schema.md`
> ถ้าจะเปลี่ยนอะไรในไฟล์นี้ แจ้งทั้งทีมก่อน และแก้ใน PR เดียวกับโค้ดที่เกี่ยวข้อง
>
> ขอบเขต: Walking Skeleton, รอบ 1 (Merge Gap, เคสรับหลายคน, Wave) และรอบ 2 (เส้นออกจาก `MANUAL_HANDOFF`, Timeout ของการอนุมัติ, OR-Tools) ทั้งสามช่วงเสร็จแล้ว
> รอบ 3 (คำอธิบายอันดับ, LINE จริง, หน้าเว็บพยาบาล, งานค้างของ Roster) เสร็จแล้วทางโค้ด LINE และ LLM ทดสอบกับตัวแทน (fake) ยังไม่ได้ลองกับบริการจริง ดู "สถานะของรอบ 3" กติกาที่มีป้าย **[รอบ 6 · PR D]** เป็นของที่เลื่อนไปรอบ 6
> รอบ 4 (Cross-Ward, การย้ายคนข้ามหอ, เวลาจริงของ Roster และ Gap รายช่วง, ผู้อนุมัติสองหอและ Supervisor, Auto-Approval) เสร็จแล้ว ดู "สถานะของรอบ 4"
> รอบ 5 (LangGraph, check-in และ `NO_SHOW`, Handover) เสร็จแล้ว ดู "สถานะของรอบ 5"
> รอบ 6 (Bedrock จริง, เครื่อง AWS และ Webhook บนเครื่อง, ผู้ใช้กดขอคำอธิบายจาก AI, Dashboard และเช็ค Gap) กำลังทำ กติกาที่มีป้าย **[รอบ 6 · PR X]** คือข้อตกลงที่ PR นั้นยังไม่ได้ทำ ดู "สถานะของรอบ 6"
> อัปเดตล่าสุด: 2026-10-17

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

**รอบ 2 เสร็จแล้ว** PR ทุกตัวในตารางข้างล่างเข้า `staging` ครบ โค้ดตรงกับกติกาของรอบ 2 ในไฟล์นี้ (ส่วนนี้, ข้อ 4, 5.1, 6.12 ถึง 6.14, 7.1 และ 9.4) กติกาข้อไหนมาจาก PR ไหนดูได้จากคอลัมน์ "ข้อของไฟล์นี้" ของตารางข้างล่าง

| PR ของรอบ 2 | ใคร | เรื่อง | ข้อของไฟล์นี้ | PR บน GitHub |
|---|---|---|---|---|
| เอกสาร | คน 1 | ร่างรอบ 2 และไฟล์คำถามสามชุด | | #50 |
| A | คน 2 | Test ที่ตรึงผลของ Solver รอบ 1 | 6.14 | #51 |
| 0 | คน 1 | ย้าย Contract เข้าไฟล์นี้, Transition T8 และ T9, ค่าใหม่ใน Enum | 4, 5.1, 6.12 ถึง 6.14, 7.1, 9.4 | #52 |
| W | คน 1 | การอนุมัติจำกัดหอ | 6.12 | #53 |
| T | คน 3 | Approval Timeout (Migration ตัวที่ 1) | 6.13 | #54 |
| T2 | คน 1 | หน้า `approvals` แสดงเส้นตาย | 9.4 | #55 |
| B | คน 2 | OR-Tools (Migration ตัวที่ 2) | 6.14 | #56 |
| H | คน 1 | เส้นออกจาก `MANUAL_HANDOFF` (Migration ตัวที่ 3) | 6.12 | #57 |

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

**Test ของข้อกำหนดที่พังเงียบได้** PR 0 เคยระบุว่าข้อกำหนดข้างล่างต้องมี Test ใน PR ที่ทำ ตอนปิดรอบตรวจแล้วว่ามีครบ

| ข้อกำหนด | PR | Test อยู่ที่ |
|---|---|---|
| ตัวอ่านจับคู่ด้วย `outreach_id` และแถวของรอบแรกไม่มีผลกับรอบที่สอง | T | `test_approval_timeout.py` (`test_full_retry_gets_fresh_safety_and_request_and_can_be_approved`, `test_second_timeout_has_no_third_offer`) |
| Migration หยุดเมื่อเคสกับ Item หนึ่งคู่มี Offer มากกว่าหนึ่งแถว และ Job เขียนผลหมดเวลาเฉพาะคำขอที่ยังกดตัดสินได้ | T | `test_approval_timeout_migration.py`, `test_approval_timeout.py` (`test_inactive_history_is_not_expired`) |
| `cancellation_reason` เป็น `APPROVAL_TIMEOUT` เมื่อคำขอหมดเวลา | T | `test_approval_timeout.py` (`test_timeout_audit_stage_and_offer_reason_are_distinct_from_rejection`) |
| ช่องของ `OFFER_CANCELLED_BY_ASSIGNMENT` และ `cancellation_reason` ยังเป็น `CONFLICTING_ASSIGNMENT` ทั้งสองเส้นทาง | H | `test_manual_handoff.py` (`test_confirming_cancels_the_clashing_offer_and_says_why_in_its_case`, `test_an_approval_uses_the_same_rules_for_offers_elsewhere`) |
| ตัวยกเลิก Offer ไม่แตะ Offer `SENT` ที่เลยเส้นตาย ทั้งเส้นทางจัดคนเองและเส้นทางอนุมัติ | H | `test_manual_handoff.py` (`test_an_overdue_offer_is_left_for_the_timeout_job`, `test_an_approval_uses_the_same_rules_for_offers_elsewhere`) |
| การจัดคนเองถูกปฏิเสธเมื่อไม่ผ่าน Hard Rules ข้อใดข้อหนึ่ง และเวรที่จัดเองถูกนับว่าปิด Gap | H | `test_manual_handoff.py` (`test_a_person_already_on_the_shift_is_refused_whatever_the_reason`, `test_each_fatigue_rule_refuses_the_assignment`, `test_a_person_outside_the_plan_counts_toward_the_gap`, `test_an_approved_replacement_and_a_manual_one_close_the_gap_together`) |
| ผู้กดที่ไม่ใช่ Head Nurse ของหอเดียวกับเวรได้ `403` | W และ H | `test_approval_decision.py` (`test_head_nurse_of_another_ward_is_403_before_pending_and_answer`), `test_manual_handoff.py` (`test_only_a_head_nurse_of_the_shifts_ward_may_assign`) |
| สถานะของ Solver แต่ละค่าพาเคสไปสถานะที่ถูก และผล `OPTIMAL` เท่ากับ Solver รอบ 1 | B | `tests/unit/optimization/test_solver_stages.py`, `test_optimize.py` และ Test ที่ PR A ตรึงไว้ |

---

## สถานะของรอบ 3

Contract ของรอบ 3 ตกลงแล้ว (PR #60) ไฟล์นี้รับเฉพาะกติกาที่ข้ามคน ส่วน Spec เต็มของรอบอยู่ที่ `docs/round3/round3-contract-draft.md` (ในไฟล์นี้เรียกว่า "ร่างรอบ 3") เลข R3-Q ที่อ้างในไฟล์นี้คือคำถามใน `docs/round3/round3-questions.md` คำตอบเป็นการตัดสินใจร่วมกันของทั้งสามคน

**รอบ 3 เสร็จแล้ว** PR ทุกตัวในตารางข้างล่างยกเว้น D เข้า `staging` ครบ โค้ดตรงกับกติกาของรอบ 3 ในไฟล์นี้ (ส่วนนี้, ข้อ 6.15 ถึง 6.18, 7.1 และ 9.5) กติกาข้อไหนมาจาก PR ไหนดูได้จากคอลัมน์ "ข้อของไฟล์นี้" ของตารางข้างล่าง ส่วนของ PR D ที่ยังไม่มีโค้ดมีป้าย **[รอบ 6 · PR D]**

| PR ของรอบ 3 | ใคร | เรื่อง | ข้อของไฟล์นี้ | PR บน GitHub |
|---|---|---|---|---|
| เอกสาร | คน 1 | ร่างรอบ 3 และไฟล์คำถาม | | #60 |
| 0 | คน 1 | ย้าย Contract เข้าไฟล์นี้, ค่าใหม่ใน Enum, Path ของ API สำหรับผู้สมัคร | 6.15 ถึง 6.17, 7.1, 9.5 | #61 |
| E | คน 2 | คำอธิบายอันดับ (Backend): ช่องใหม่ใน Snapshot และช่อง `score` | 6.15 | #63 |
| E2 | คน 2 | คำอธิบายอันดับ (หน้า `cases/[id]`) | 6.15, 9.5 | #67 |
| L | คน 3 | LINE จริง: Webhook, กันซ้ำ, ส่ง Offer (Migration ตัวที่ 1) | 6.16 | #62 |
| K | คน 3 | ผูกบัญชี LINE (Migration ตัวที่ 2) | 6.16 | #68 |
| X | คน 2 | ประโยคอธิบายจาก LLM (Migration ตัวที่ 3 `e1a4c7f2b9d6`) | 6.15, 9.3, 9.5 | #70 |
| R | คน 1 | งานค้างของ Roster และการลา: `COMPLETED`, `GET /roster?staff_id=`, ธง `is_unavailable`, แก้ `end_at` ของการลา | 6.18, 9.5 | #64 |
| N | คน 1 | หน้าเว็บพยาบาล "ข้อเสนอเข้าเวรของฉัน" | 6.17, 9.5 | #69 |
| D | ทั้งสามคน (คน 1 รวบรวม PR) | สภาพแวดล้อมบน AWS **เลื่อนไปรอบ 6** (มติทีม 2026-10-14) งานที่ทำแล้วเก็บใน branch `feat/aws-test-environment` | 6.16, 6.17 | |

ลำดับ merge: 0 ก่อนทุกตัวยกเว้น D, E ก่อน E2 และ X, L ก่อน K, N หลัง L และ K, Migration ต่อกันเป็นเส้นเดียว `b7d3e5a1c9f2` → L → K → X (head ปัจจุบันหลัง X คือ `e1a4c7f2b9d6`; ลำดับนี้เป็นข้อเสนอในร่างรอบ 3 ข้อ 6 ถ้า X พร้อมก่อน ให้ตกลงสลับตอนนั้น) รอบ 3 ไม่ใช้ Branch รวม ทุก PR เข้า `staging` ตรง (R3-Q13)

**เลื่อน D และการลองของจริง (มติทีม 2026-10-14)** แทนเงื่อนไขเดิมที่ D ต้องเสร็จก่อนลอง LINE จริงและ Bedrock จริงในรอบ 3

* **LINE จริงในรอบ 3 ถึง 5:** คน 3 ลองผ่าน Cloudflare Quick Tunnel บนเครื่องของคน 3 ไม่ต้องมีบัญชี Cloudflare หรือโดเมน (ข้อ 6.16) ใช้ระหว่างพัฒนาเท่านั้น
* **Bedrock จริง:** เลื่อนไปรอบ 6 พร้อม Deploy รอบ 3 ถึง 5 ใช้ `fake` (ข้อ 6.15)
* **D:** เปิดเครื่อง AWS ในรอบ 6 ลำดับในรอบ 6 คือ เปิดเครื่องและผ่าน `check-gate.sh` ก่อน จากนั้นคน 2 ลอง Bedrock ด้วย IAM Role ของเครื่อง และคน 3 ย้าย Webhook จาก Tunnel มาที่เครื่องแล้วปิด Tunnel
* **การปิดรอบ 3:** ไม่รอ D และต้องระบุตามหลักฐานว่าอะไรทดสอบด้วย fake และอะไรผ่านบริการจริงแล้ว การทดสอบ Bedrock จริงและการทดสอบระบบบน AWS เป็นเกณฑ์ของรอบ 6

**อะไรทดสอบด้วย fake และอะไรผ่านบริการจริง (ตอนปิดรอบ 3)** หลักฐานคือ Description ของ PR และไฟล์ Handoff ใน `docs/round3/`

| เรื่อง | ทดสอบแล้วด้วย | บริการจริง |
|---|---|---|
| ส่ง Offer และรับคำตอบผ่าน LINE (L) | Test กับ PostgreSQL จริงและตัวแทน HTTP ของ LINE API รวม Test สอง Connection | **ผ่านแล้ว 2026-10-16 (Quick Tunnel)** ตามบันทึกใน `docs/round5/pr-H2-handoff.md` ที่คน 1 รายงาน: พยาบาล 201 รับ Offer ผ่าน LINE จริง และ Head Nurse 900 อนุมัติทางหน้าเว็บ ไม่ได้ลองผ่านเครื่อง AWS (รอบ 6 ขั้นที่ 6 และ W) |
| ผูกบัญชี LINE (K) | Test กับ PostgreSQL จริงและตัวแทน LINE API | **ใช้จริงแล้วโดยปริยาย 2026-10-16** บัญชีของ 201 ผูกกับ LINE จริงก่อนรับ Offer ในการทดสอบข้างบน แต่ไม่มีบันทึกขั้นตอนการผูกแยก คน 3 ยืนยันวันที่และขั้นตอนของ `LINK` ตอนทำ W |
| ด่าน HTTP หน้า Quick Tunnel (`dev/line-webhook-proxy`) | nginx config จริงกับ Backend จำลองใน CI | **ผ่านแล้ว 2026-10-16** `pr-H2-handoff.md` บันทึกว่าด่านผ่านทาง URL สาธารณะ (Quick Tunnel public gate passed) |
| ประโยคจาก LLM (X) | ตัวเชื่อม `fake` และตัวเชื่อม `bedrock` ทดสอบออฟไลน์ด้วย botocore `Stubber` | ไม่เรียก Bedrock จริงตามมติ เป็นงานของรอบ 6 |
| เครดิตและสิทธิ์โมเดลของ Bedrock (งานเตรียมของคน 2) | | ยังไม่มีบันทึกใน repo |
| หน้าเว็บ (E2, N) และงานของ Roster (R) | Test ของ Frontend และ Backend และลองบน Stack ในเครื่องผ่าน Browser | ไม่ใช้บริการภายนอก |
| สภาพแวดล้อมบน AWS (D) | `deploy/aws/test_gate.py` รัน `Caddyfile` จริงกับ Upstream ปลอมบน Docker แล้วรัน `check-gate.sh` (ใน CI ด้วย) PR D อยู่ใน `staging` แล้ว ไม่ได้เปิดเครื่อง | รอบ 6: ตรวจช่วง ข บนเครื่องที่ขั้นที่ 6 (ข้อ 6.30) ตารางนี้ต้องมีวันที่ครบทุกแถวก่อนปิดรอบ 6 (R6-Q3 ก) |

**ผลเพิ่มตอนเริ่มรอบ 5 (R5-Q2):** ทีมแจ้งเมื่อ 2026-10-16 ว่าลอง LINE จริงผ่าน Tunnel แล้วทำงานได้ปกติ ส่วนที่ลองผ่านแต่ละเรื่องของแถว L และ K คน 3 เติมพร้อมวันที่ ส่วนสิทธิ์ Bedrock คน 2 แจ้งภายในรอบ 6

ถ้าทีมได้ลอง LINE จริงผ่าน Tunnel แล้วแต่ยังไม่ได้บันทึก ให้เพิ่มผลพร้อมวันที่และสิ่งที่ผ่านจริงในตารางนี้ ห้ามอ้างว่าผ่านครบถ้า Tunnel ขาดกลางทาง (ข้อ 6.16)

เรื่องที่ยังอยู่ในร่างรอบ 3 ไม่ได้ย้ายเข้าไฟล์นี้

| ร่างรอบ 3 | เรื่อง |
|---|---|
| ข้อ 1 | ฐานจากรอบ 2 ที่ตรวจกับโค้ดแล้ว และจำนวน Test ตั้งต้น |
| ข้อ 2 | ขอบเขต งานของคน 1 การแบ่งงานใน PR D และเรื่องที่ไม่อยู่ในรอบ 3 |
| ข้อ 5 | จุดที่เสี่ยงพังเงียบ |
| ข้อ 6 | ลำดับ PR และเหตุผลของลำดับ Migration |
| ข้อ 8 | สิ่งที่ยังไม่ได้ตรวจ และลิงก์เอกสารของ LINE ที่ใช้ตรวจ |
| คำตอบ R3-Q15 | รายละเอียดเต็มของ LLM: ความลับ, ข้อจำกัด, การติดตามค่าใช้จ่าย |

ถ้ากติกาที่ย้ายเข้าไฟล์นี้แล้วไม่ตรงกับร่างรอบ 3 ให้ยึดไฟล์นี้

**Test ของข้อกำหนดที่พังเงียบได้** PR 0 เคยระบุว่าข้อกำหนดข้างล่างผิดแล้วไม่มี Error และ PR ที่ทำต้องมี Test ตอนปิดรอบตรวจแล้วว่ามีครบ ไฟล์อยู่ใต้ `backend/tests/integration/` ยกเว้นที่ระบุ

| ข้อกำหนด | PR | Test อยู่ที่ |
|---|---|---|
| แก้ Policy หลังวางแผนแล้ว คะแนนรายพจน์ของ Plan เดิมไม่เปลี่ยน และผลรวมยังเท่ากับ `penalty_exact` | E | `test_case_score.py` (`test_a_policy_edit_after_planning_does_not_change_the_score`) |
| ชั่วโมงไม่เต็มชั่วโมง (เช่น 20 นาที) กับค่าน้ำหนักที่เป็นเศษส่วน ผลรวมรายพจน์เท่ากับ `penalty_exact` พอดี | E | `test_case_score.py` (`test_fractional_weights_and_overtime_sum_exactly`), `tests/unit/domain/test_score_breakdown.py` |
| Plan ที่ไม่มีช่องใหม่ใน Snapshot ได้ `score = null` ไม่เดาจาก Policy ปัจจุบัน | E | `test_case_score.py` (`test_a_plan_without_stored_weights_has_no_score`) |
| ลายเซ็นไม่ผ่านหรือไม่มี Header ได้ `401` และไม่มีแถวใดถูกเขียน | L | `test_line_messaging.py` (`test_signature_is_checked_before_json_or_database`) |
| บังคับให้การล็อกใน `record_response()` เริ่มใหม่หนึ่งครั้ง แล้วแถวกันซ้ำกับผลของการตอบยังถูก Commit ด้วยกัน และ Event ที่ส่งซ้ำไม่ถูกประมวลอีก | L | `test_line_delivery_races.py` (`test_actual_lock_restart_keeps_the_webhook_id`), `test_line_messaging.py` (`test_dedup_callback_runs_after_the_lock_helper_returns`, `test_webhook_response_and_duplicate_have_one_effect`) |
| Event เดียวกันมาพร้อมกันสองครั้ง ได้ผลทางธุรกิจครั้งเดียว | L | `test_line_messaging.py` (`test_two_connections_process_same_webhook_once`) |
| การปฏิเสธทางธุรกิจได้ `200` พร้อมแถวกันซ้ำ ส่วน Error ที่ไม่คาดไว้ได้ `5xx` และไม่มีแถวกันซ้ำ | L | `test_line_messaging.py` (`test_unbound_wrong_owner_and_malformed_actions_are_acknowledged`, `test_unexpected_failure_rolls_back_event_and_response`, `test_lock_retry_has_no_dedup_row`) |
| ผู้ส่งที่ไม่ได้ผูกบัญชี หรือ `postback.data` ที่ชี้ Offer ของคนอื่น ไม่เปลี่ยน Offer | L | `test_line_messaging.py` (`test_unbound_wrong_owner_and_malformed_actions_are_acknowledged`) |
| เครื่องล่มหลัง Wave Commit แต่ก่อนส่งครั้งแรก แล้ว Job ส่งให้ | L | `test_line_messaging.py` (`test_intent_is_atomic_and_restart_recovers_it`, `test_claim_lease_prevents_duplicate_workers_and_recovers_crash`) |
| `409` ของ Retry key นับว่ารับแล้ว `429` ไม่นับในสามครั้ง `401` และ `403` ไม่ตั้ง Offer เป็น `FAILED` | L | `test_line_messaging.py` (`test_line_acceptance_stops_retries`, `test_configuration_and_rate_errors_do_not_consume_attempts`) |
| Offer ที่ถูกรับ ยกเลิก หมดเวลา หรือเคสหยุดแล้ว ไม่ถูกส่งซ้ำและไม่ถูกเขียนทับด้วย `FAILED` | L | `test_line_messaging.py` (`test_answer_or_cancellation_during_send_is_never_overwritten`, `test_expired_and_stopped_intents_do_not_send`) |
| รหัสผูกบัญชีเดียวกันถูกใช้พร้อมกันสองครั้ง สำเร็จได้ครั้งเดียว และถ้าการเขียนพัง รหัสยังใช้ได้ | K | `test_line_account_races.py` (`test_same_code_is_consumed_once_across_connections`), `test_line_account_linking.py` (`test_failed_link_rolls_back_contact_code_audit_and_dedup`) |
| เปิดหน้าซ้ำหรือ Polling `GET /cases/{id}` ไม่เรียก LLM (Gateway ถูกเรียก 0 ครั้ง) | X | `test_rank_explanation.py` (`test_polling_never_calls_the_llm`, `test_demo_clock_advance_does_not_call_the_gateway`) |
| Sweep พร้อมกันสองตัว (สอง Connection) เรียก LLM ครั้งเดียวต่อ Plan | X | `test_rank_explanation.py` (`test_two_concurrent_sweeps_make_one_call`) |
| ตั้ง `bedrock` แล้วเรียกไม่สำเร็จ ไม่สลับไปใช้ `fake` เงียบ ๆ และหน้าได้ `UNAVAILABLE` | X | `test_rank_explanation.py` และ `tests/unit/services/test_llm_service.py` (`test_bedrock_failure_never_falls_back_to_fake` ทั้งสองไฟล์) |
| LLM ล้มเหลวไม่เปลี่ยนสถานะเคสและไม่มี `WORKFLOW_FAILED` | X | `test_rank_explanation.py` (`test_llm_failure_does_not_touch_the_case`) |
| ข้อมูลที่ส่งให้ LLM ไม่มีชื่อพนักงานหรือ `staff_id` (ตรวจทั้ง Key และ Value) | X | `test_rank_explanation.py` (`test_payload_has_no_personal_data`) |
| Attempt ไม่เกิน `1 + LLM_MAX_RETRIES` แม้เครื่องล่มกลางการเรียก (Lease หมดแล้ว `attempts` เต็ม ได้ `FAILED` โดยไม่เรียก) | X | `test_rank_explanation.py` (`test_a_crash_cannot_exceed_the_attempt_bound`) |
| เลื่อน Demo Clock เกิน Lease ระหว่างที่การเรียกยังรันอยู่ Sweep ถัดไปไม่เรียกซ้ำใน Plan เดียว (Lease ใช้นาฬิกาฐานข้อมูล) | X | `test_rank_explanation.py` (`test_the_lease_follows_real_time_not_the_demo_clock`) |
| เคสถึงสถานะสุดท้ายขณะที่ประโยคยัง `PENDING` หน้ายัง Poll จนเป็น `READY` หรือ `UNAVAILABLE` | X | `frontend/tests/unit/components/case/CaseView.test.tsx` ("when the case is already final": "keeps polling while PENDING, then shows the sentence and stops", "stops when PENDING turns UNAVAILABLE") |
| Route ของหน้าเว็บพยาบาลไม่สนใจ `staff_id` ที่ส่งมาใน Query หรือ Body | N | `test_me_offers.py` (`test_staff_id_in_the_query_is_ignored`, `test_body_with_any_other_field_is_refused_without_writes`) |
| ตั้งเวรที่จบแล้วเป็น `COMPLETED` แล้ว Gap, Hard Rules (รวมเวลาพักหลังเวรนั้น) และชั่วโมงทำงานเท่าเดิม | R | `test_roster_completion.py` (`test_completing_a_shift_moves_no_gap_fatigue_check_or_working_time`) |
| การลาหรือการยกเลิกที่รับไว้ก่อนเวรจบยังถูกประมวลหลัง Job ตั้ง `COMPLETED` รวมกรณีที่ Window รอเคสที่ยังเดิน | R | `test_roster_completion_events.py` (`test_a_leave_reported_before_the_end_applies_after_the_job_runs`, `test_a_cancellation_reported_before_the_end_applies_after_the_job_runs`, `test_a_leave_held_back_by_a_running_case_applies_once_the_case_ends`) |
| เรียกเครื่องทดสอบบน AWS โดยไม่มีรหัส Basic Auth ถูกปฏิเสธ ส่วน Path ของ Webhook เรียกได้ และข้อยกเว้นไม่ครอบ Path อื่น | D (รอบ 6 ทำแล้ว) | `deploy/aws/test_gate.py` (รัน `Caddyfile` จริง ตรวจด้วย `check-gate.sh` และตรวจว่าคำขอที่ติดด่านไม่ถึง Upstream) ลองบนเครื่องจริงที่ขั้นที่ 6 ไม่ใช่เกณฑ์ปิดรอบ 3 |

---

## สถานะของรอบ 4

Contract ของรอบ 4 ตกลงแล้ว (PR #73) ไฟล์นี้รับเฉพาะกติกาที่ข้ามคน ส่วน Spec เต็มของรอบอยู่ที่ `docs/round4/round4-contract-draft.md` (ในไฟล์นี้เรียกว่า "ร่างรอบ 4") เลข R4-Q ที่อ้างในไฟล์นี้คือคำถามใน `docs/round4/round4-questions.md` คำตอบเป็นการตัดสินใจร่วมกันของทั้งสามคน

**รอบ 4 เสร็จแล้ว** PR ทุกตัวในตารางข้างล่างเข้า `staging` ครบ (#73, #74 และ #78 ถึง #88) โค้ดตรงกับกติกาของรอบ 4 ในไฟล์นี้ (ส่วนนี้, ข้อ 6.11 ลำดับ Lock ที่เพิ่ม, 6.19 ถึง 6.22, 7.1 และ 9.6) ไม่เหลือป้าย **[รอบ 4 · PR X]** กติกาข้อไหนมาจาก PR ไหนดูได้จากคอลัมน์ "ข้อของไฟล์นี้" ของตารางข้างล่าง

| PR ของรอบ 4 | ใคร | เรื่อง | ข้อของไฟล์นี้ | ต้องรอ | Migration | PR บน GitHub |
|---|---|---|---|---|---|---|
| เอกสาร | คน 1 | ร่างรอบ 4 และไฟล์คำถาม | | | ไม่มี | [#73](https://github.com/Bobbie-CPE38/nara/pull/73) |
| 0 | คน 1 | ย้าย Contract เข้าไฟล์นี้, ค่าใหม่ใน Enum | ทุกข้อของรอบ 4 | เอกสาร | ไม่มี | [#74](https://github.com/Bobbie-CPE38/nara/pull/74) |
| T1 | คน 2 | ช่วงที่มาทำได้และเวรต้นทางในรายชื่อผู้สมัคร, Safety และ Hard Rules ใช้ช่วงนี้, ช่วงทำงานต่อเนื่องตอนวางแผน | 6.20 | 0 | มี (`CANDIDATE_ITEMS`) | [#78](https://github.com/Bobbie-CPE38/nara/pull/78) |
| T2 | คน 3 | เวลาจริงและลิงก์การย้ายใน Roster, ตัวอ่านเวลาของ Roster | 6.20 | 0 | มี (`ROSTER_ASSIGNMENT`) | [#79](https://github.com/Bobbie-CPE38/nara/pull/79) |
| T3 | คน 1 | Gap รายช่วง | 6.20, 9.6 | 0, T2 | มี (`STAFFING_GAP` และตารางรายช่วง) | [#82](https://github.com/Bobbie-CPE38/nara/pull/82) |
| T4 | คน 2 | Solver และการเลือก Wave ตามช่วง, แผนบางส่วน, ข้อความอธิบายอันดับ | 6.20 | T1, T3 | ไม่มี | [#84](https://github.com/Bobbie-CPE38/nara/pull/84) |
| C1 | คน 2 | ดึงคนว่างข้ามหอ, Float Pool | 6.19 | T1 | มี (`WARD.is_float_pool`) | [#81](https://github.com/Bobbie-CPE38/nara/pull/81) |
| S | คน 3 | อนุมัติสองหอ, Supervisor, ตัวตรวจสิทธิ์ของคนกด | 6.21, 9.6 | C1 | มี (`APPROVAL_WARD_DECISION`, `APPROVAL_POLICY.supervisor_after_seconds`) | [#83](https://github.com/Bobbie-CPE38/nara/pull/83) |
| C2 | คน 2 | ย้ายทั้งเวร | 6.19, 9.6 | C1, S | ไม่มี | [#87](https://github.com/Bobbie-CPE38/nara/pull/87) |
| C3 | คน 2 | ย้ายกลางเวร | 6.19, 6.20 | C2, T2, T3, T4 | ไม่มี | [#88](https://github.com/Bobbie-CPE38/nara/pull/88) |
| A | คน 3 | Auto-Approval | 6.22, 9.6 | 0, T1 | ไม่มี | [#80](https://github.com/Bobbie-CPE38/nara/pull/80) |
| W4 | คน 1 | ข้อมูล Demo หลายหอ, หอ Float Pool, Role `SUPERVISOR` | 6.19, 6.21 | C1 | ไม่มี | [#85](https://github.com/Bobbie-CPE38/nara/pull/85) |
| U | คน 1 | หน้าเว็บของรอบ 4 | 9.6 | A, S | ไม่มี | [#86](https://github.com/Bobbie-CPE38/nara/pull/86) |

ลำดับ merge: 0 ก่อนทุกตัว, T3 หลัง T2, T4 หลัง T1 และ T3, C1 หลัง T1, S หลัง C1, C2 หลัง S (ห้ามมีการย้ายคนก่อนที่การอนุมัติสองหอจะมี), C3 หลัง C2 T2 T3 T4, A หลัง T1, U หลัง A และ S Migration ต่อจาก `e1a4c7f2b9d6` เป็นเส้นเดียวตามลำดับที่ merge จริง ลำดับจริงคือ T1 → T2 → C1 → T3 → S (head ของ S `f2a7c9d4e6b8` ต่อจาก `c6e2b9f4a1d7`) PR ที่เข้าหลัง S ไม่มี Migration head ตอนปิดรอบ 4 จึงเป็น `f2a7c9d4e6b8` ตัวที่ merge ทีหลังต้อง Rebase แก้ `down_revision` ให้ต่อจาก head ของ `staging` และรัน `alembic heads` ให้ได้ head เดียว รอบ 4 ไม่ใช้ Branch รวม ทุก PR เข้า `staging` ตรง (R4-Q2)

* **ทำไม A รอ T1:** Test ของ A สร้างข้อมูลเอง คนข้ามหอและคน Float Pool สร้างได้ด้วยค่า `source` = `CROSS_WARD` หรือ `FLOAT_POOL` ที่มีอยู่แล้ว จึงไม่ต้องรอ C1 แต่คำขอที่มีเวรต้นทางต้องใช้คอลัมน์ `CANDIDATE_ITEMS.source_assignment_id` ที่ T1 เพิ่ม ทั้งตอนกรองและตอนสร้างข้อมูลใน Test จึงต้องรอ T1 ไม่ต้องรอ C2
* **ถ้า C3 ไม่ทันในรอบนี้ (R4-Q38):** T2, T3 และ T4 ไปถึง `main` ตอนปิดรอบตามปกติเมื่อผ่านด่านครบ (Golden Case และ Seed Scenario เดิมได้ Gap เท่าเดิม และผลกับเวลาของ Solver กับข้อมูลแบบเดิมไม่เปลี่ยน) ไม่มีตัวเปิดปิด C2 ส่งได้เมื่อ S เข้าแล้ว ตอนปิดรอบ C3 เข้าแล้ว (#88) ทางนี้จึงไม่ได้ใช้
* **งานค้างจากรอบ 3 (R4-Q3):** ลอง LINE จริงผ่าน Tunnel (คน 3), ตรวจเครดิตและสิทธิ์โมเดลของ Bedrock (คน 2), ให้ Test บังคับ `LINE_MODE=simulation` เองไม่ขึ้นกับ `.env` บันทึกผลในตาราง "อะไรทดสอบด้วย fake และอะไรผ่านบริการจริง" ของส่วน "สถานะของรอบ 3" **ตอนปิดรอบ 4 ทั้งสามเรื่องยังไม่มีบันทึกใน repo** ตารางของรอบ 3 ยังเขียนว่ายังไม่ได้ลอง และ Test ยังไม่ตั้ง `LINE_MODE` เอง ทีมต้องตัดสินว่าจะทำในรอบไหน

เรื่องที่ยังอยู่ในร่างรอบ 4 ไม่ได้ย้ายเข้าไฟล์นี้

| ร่างรอบ 4 | เรื่อง |
|---|---|
| ข้อ 1 | ฐานจากรอบ 3 ที่ตรวจกับโค้ดแล้ว และจำนวน Test ตั้งต้น (Backend 2,262 ผ่าน 14 ข้าม, Frontend 304) |
| ข้อ 2 | ขอบเขต งานของคน 1 และเรื่องที่ไม่อยู่ในรอบ 4 |
| ข้อ 5.1 | ตัวอย่างและเหตุผลของแนวทาง Gap รายช่วง Solver และ Safety |
| ข้อ 7 | เหตุผลของการแบ่ง PR และเจ้าของ |
| ข้อ 9 | สิ่งที่ยังไม่ได้ตรวจ |

ถ้ากติกาที่ย้ายเข้าไฟล์นี้แล้วไม่ตรงกับร่างรอบ 4 ให้ยึดไฟล์นี้

**Test ของข้อกำหนดที่พังเงียบได้** PR 0 เคยระบุว่าข้อกำหนดข้างล่างผิดแล้วไม่มี Error และ PR ที่ทำต้องมี Test ตอนปิดรอบตรวจแล้วว่ามีครบ ไฟล์อยู่ใต้ `backend/tests/integration/` ยกเว้นที่ระบุ

| ข้อกำหนด | PR | Test อยู่ที่ |
|---|---|---|
| Pool ขยายแล้ว `source` ของคนข้ามหอไม่ใช่ `SAME_WARD` และคะแนนแหล่งที่มาไม่เป็น 0 | C1 | `test_cross_ward_pool.py` (`test_a_free_nurse_of_another_ward_is_a_cross_ward_candidate`, `test_a_free_nurse_of_the_float_pool_is_a_float_pool_candidate` ตรวจทั้ง `source` และคะแนน `candidate_source`) |
| คนที่อยู่เวรของหออื่นเข้า Pool ได้ก็ต่อเมื่อเวรต้นทางมีเวลาตรงกับเวรปลายทางและยังไม่เริ่ม มิฉะนั้นไม่เข้า (C3 แทนที่ด้วยกติกาของ C3: เข้า Pool เมื่อย้ายได้ คือ `max(เริ่มเวรปลายทาง, เริ่มเวรต้นทาง, Backend Clock) < min(จบเวรต้นทาง, จบเวรปลายทาง)` เวรที่เริ่มแล้วและเวรที่ทับบางส่วนเข้าได้ เวรที่จบแล้วไม่เข้า) | C1, C2, C3 | `test_cross_ward_pool.py` (`test_someone_on_another_wards_offset_overlapping_shift_is_in_the_pool_with_a_source`, `test_actual_times_decide_the_overlap`), `test_transfer_planning.py` (`test_a_person_whose_source_shift_has_started_enters_the_pool`, `test_a_source_row_that_is_over_by_now_keeps_the_person_out`) |
| สองเคสต่างหอใช้ผู้สมัครคนเดียวกันพร้อมกัน ไม่ได้เวรที่จัดแล้วทับกัน (สอง Connection) | C1 | `test_cross_ward_approval_race.py` (`test_concurrent_decisions_never_assign_overlapping_shifts`) |
| ตรวจคนที่ถูกย้ายด้วย Roster หลังย้าย ไม่ใช่แค่ข้าม `SHIFT_CONFLICT` | T1, C2 | `test_transfer_planning.py` (`test_planning_and_safety_give_the_same_answer`, `test_losing_the_only_holder_of_a_skill_fails_the_rule_with_headcount_fine`), `test_transfer_execution.py` (`test_a_conflicting_duty_added_after_safety_fails_the_hard_rule`) |
| ช่วงทำงานต่อเนื่องของการย้ายไม่ถูกกฎเวลาพักปฏิเสธ และเวรที่ต่อกันพอดีโดยไม่ได้ย้ายยังถูกปฏิเสธ | T1, C3 | `test_transfer_planning.py` (`test_the_linked_source_part_lets_a_mover_pass_the_rest_rule`), `test_roster_actual_times.py` (`test_unlinked_rows_still_fail_rest_at_zero_hours`) |
| ตรวจเวรต้นทางซ้ำหลังล็อกตอนย้ายจริง สองการอนุมัติพร้อมกันบนเวรต้นทางที่เกินแค่ 1 คน เหลือผู้ผ่านคนเดียว (สอง Connection) | C2 | `test_transfer_execution.py` (`test_two_final_approvals_race_for_the_last_surplus_of_one_source_shift`, `test_source_row_cancelled_after_the_request`, `test_source_gap_after_the_request`) |
| ตรวจไม่ผ่านตอนย้ายจริงไม่ทำให้เคส `FAILED` และตัวสำรองถูกเลื่อนขึ้นมา | C2 | `test_transfer_execution.py` (`test_a_reserve_is_promoted_after_a_refused_move`, `test_the_next_wave_is_sent_when_there_is_no_reserve`) |
| (C3 แทนที่แล้ว) อนุมัติครบหลังเวรต้นทางเริ่ม ก่อน C3 เข้าได้ `SOURCE_SHIFT_STARTED` ไม่ย้ายทั้งเวรแทน | C2, แทนที่โดย C3 | `test_transfer_execution.py` (`test_final_approval_after_the_source_shift_started_moves_mid_shift` แทน Test เดิมของ C2) |
| C3 ลบ `SOURCE_SHIFT_STARTED` และเอาเงื่อนไขของ C2 ที่ไม่ให้คนที่เวรต้นทางเริ่มแล้วเข้า Pool ออก (คนแบบนี้เข้า Pool ได้อีกครั้ง) เปลี่ยน Test ของ C2 ในกรณีนี้เป็นการย้ายกลางเวรที่สำเร็จ ตัวอ่าน `reason` ยังรับแถว Audit เก่าที่มีค่านี้ได้ | C3 | `test_transfer_planning.py` (`test_a_person_whose_source_shift_has_started_enters_the_pool`, `test_a_source_shift_that_starts_earlier_keeps_its_first_part_as_a_linked_duty`, `test_a_source_shift_that_starts_later_gives_a_cover_from_its_start`, `test_a_source_row_with_actual_times_is_covered_from_its_effective_times`, `test_a_mover_whose_cover_misses_every_short_slice_is_skipped`), `test_transfer_execution.py` (`test_final_approval_after_the_source_shift_started_moves_mid_shift`, `test_a_mid_shift_recheck_uses_the_real_move_time`, `test_an_old_source_shift_started_audit_stays_readable`) |
| การย้ายต้องได้อนุมัติครบสองหอ หอหนึ่งปฏิเสธคือปฏิเสธทั้งคำขอ | S, C2 | `test_approval_two_wards.py` (`test_both_wards_are_required_and_only_last_approval_executes`, `test_either_ward_rejection_finishes_request_without_execution`, `test_both_approvals_end_in_a_real_transfer`) |
| ตัดสินว่าต้องอนุมัติสองหอจากเวรต้นทาง ไม่ใช่จาก `source` | S, C2 | `test_approval_two_wards.py` (`test_single_ward_source_is_422_and_supervisor_can_decide_destination`), `test_transfer_planning.py` (`test_a_same_ward_nurse_on_another_wards_equal_time_shift_is_moved`, `test_a_float_pool_nurse_on_an_equal_time_shift_keeps_her_float_pool_source`) |
| `manages_ward()` ไม่เปลี่ยน การตรวจคนที่ถูกจัดเวรใน `MANUAL_HANDOFF` และสิทธิ์แก้การลาเหมือนเดิม | S | `tests/unit/domain/test_ward_authority.py` (`test_a_head_nurse_manages_their_own_ward`, `test_a_head_nurse_does_not_manage_another_ward`, `test_supervisor_authority_does_not_change_staff_membership`), `test_approval_two_wards.py` (`test_supervisor_does_not_gain_head_nurse_event_or_leave_permissions`) |
| Supervisor กดได้ก่อนเวลาที่กำหนดไม่ได้ รวมกรณีกดฝั่งที่ตัดสินแล้วก่อน `supervisor_from` ซึ่งต้องได้ `403` ไม่ใช่ `409` | S | `test_approval_two_wards.py` (`test_supervisor_wait_boundary_and_one_decision_per_click`, `test_supervisor_before_wait_gets_403_even_on_already_decided_side`) |
| แถว Roster ของเวรต้นทางที่ตัดหรือยกเลิกแล้วไม่ถูกนับว่าอยู่เวรหลังเวลาย้าย | T2, T3 | `test_gap_intervals.py` (`test_a_cut_source_row_stops_counting_at_its_actual_end`), `test_cross_ward_pool.py` (`test_a_cancelled_duty_keeps_the_person_in_the_pool`) |
| ตัวอ่านเวลาของ Roster ทุกตัวใช้เวลาจริง (แถวที่จบก่อนเวลาและเริ่มหลังเวลา) | T2 | `test_roster_actual_times.py` (`test_snapshot_uses_actual_segments_and_counts_a_linked_duty_once`, `test_completion_uses_actual_end_with_null_shift_fallback`, `test_roster_reads_expose_raw_endpoints_and_transfer_link`, `test_leave_flag_uses_the_actual_interval_not_the_whole_shift`, `test_leave_overlap_report_uses_actual_roster_interval`) |
| Gap รายช่วงของเวรที่ไม่มีการย้ายเท่ากับ Gap เดิม (Golden Case และ Seed Scenario เดิม) | T3 | `test_gap_intervals.py` (`test_shifts_without_moves_keep_the_old_gap`, `test_an_ended_shift_is_measured_whole_as_before_round_4`) |
| การตัดสิน `RESOLVED` และ Solver ใช้ข้อมูลรายช่วง ไม่ใช่ตัวเลขสรุป | T3, T4 | `test_gap_intervals.py` (`test_a_replacement_for_part_of_the_shift_does_not_resolve_the_case`, `test_a_pending_candidate_covers_only_their_cover_window`), `test_solver_intervals.py` (`test_the_solver_gets_the_short_slices_and_the_snapshot_keeps_them`), `tests/unit/optimization/test_solver_slices.py` (`test_a_part_timer_never_counts_for_a_slice_it_does_not_cover_whole`) |
| Solver กับข้อมูลแบบเดิมให้ผลและเวลาเท่าเดิม (`solver_baseline.jsonl`, `SOLVER_TIMING=1`) | T4 | `tests/unit/optimization/test_solver_slices.py` (`test_one_whole_shift_slice_equals_the_legacy_call_on_every_baseline_case`), `tests/unit/optimization/test_solver_baseline.py`, เวลา: `tests/perf/test_solver_timing.py` (ข้ามในชุดปกติ รันเมื่อตั้ง `SOLVER_TIMING=1`) |
| เงื่อนไขใหม่ที่เลือกครบไม่ได้ได้แผนบางส่วน ไม่ใช่ `MODEL_INVALID` หรือ `FAILED` รวมผู้สมัครที่เลือกพร้อมกันไม่ได้และครอบคนละ Skill | T4, C2 | `tests/unit/optimization/test_solver_slices.py` (`test_two_exclusive_candidates_for_two_skills_give_a_partial_plan_by_points`, `test_exclusive_candidates_in_different_slices_give_a_partial_plan`), `test_solver_intervals.py` (`test_candidates_of_one_source_shift_give_a_partial_plan`, `test_the_orchestrator_goes_on_with_a_partial_plan`), `test_transfer_planning.py` (`test_two_candidates_of_one_source_shift_give_a_partial_plan`) |
| Auto-Approval ตรวจเงื่อนไขซ้ำหลังล็อก `WARD` Job กับ Job และ Job กับคนกดไม่อนุมัติเกินกติกา (สอง Connection) | A | `test_auto_approval.py` (`test_competing_connections_serialize_the_ward_snapshot` ทั้งกรณี Job กับ Job และ Job กับคนกด) |
| Auto-Approval ไม่อนุมัติคนข้ามหอ, Float Pool และคำขอที่มีเวรต้นทาง | A | `test_auto_approval.py` (`test_manual_only_requests_count_toward_threshold_but_are_never_approved`, `test_recorded_source_prevents_auto_even_with_same_ward_source`) |
| Job ไม่ตัดสินคำขอซ้ำ และ Job Timeout ไม่ตั้งคำขอที่ตัดสินแล้วเป็นหมดเวลา | A | `test_auto_approval.py` (`test_competing_connections_serialize_the_ward_snapshot`, `test_timeout_job_never_times_out_an_automatically_decided_request`) |

## สถานะของรอบ 5

Contract ของรอบ 5 ตกลงแล้ว (PR #91) ไฟล์นี้รับเฉพาะกติกาที่ข้ามคน ส่วน Spec เต็มของรอบอยู่ที่ `docs/round5/round5-contract-draft.md` (ในไฟล์นี้เรียกว่า "ร่างรอบ 5") เลข R5-Q ที่อ้างในไฟล์นี้คือคำถามใน `docs/round5/round5-questions.md` คำตอบเป็นการตัดสินใจร่วมกันของทั้งสามคน

**รอบ 5 เสร็จแล้ว** PR ทุกตัวในตารางข้างล่างเข้า `staging` ครบ (#91 ถึง #97, #99 และ #100) โค้ดตรงกับกติกาของรอบ 5 ในไฟล์นี้ (ส่วนนี้, ข้อ 6.11, 6.23 ถึง 6.25, 7.1 และ 9.7) ไม่มีป้าย **[รอบ 5 · PR X]** เหลือ Migration head ตอนปิดรอบคือ `f6b2d8a4c0e1` (ต่อจาก `f2a7c9d4e6b8` เป็นเส้นเดียว: `a4d8e1b7c3f5` ของ N1, `e8c4b2a6f0d9` ของ H1, `f6b2d8a4c0e1` ของ H2) Test ตอนปิดรอบ: Backend 2,830 ผ่าน 14 ข้าม, Frontend 349

| PR ของรอบ 5 | ใคร | เรื่อง | ข้อของไฟล์นี้ | เริ่มได้หลัง | merge ได้หลัง | Migration | PR บน GitHub |
|---|---|---|---|---|---|---|---|
| เอกสาร | คน 1 | ร่างรอบ 5 และไฟล์คำถาม | | | | ไม่มี | [#91](https://github.com/Bobbie-CPE38/nara/pull/91) |
| 0 | คน 1 | ย้าย Contract เข้าไฟล์นี้, ค่าใหม่ใน Enum และ constants | ทุกข้อของรอบ 5 | เอกสาร | เอกสาร | ไม่มี | [#92](https://github.com/Bobbie-CPE38/nara/pull/92) |
| G | คน 1 | LangGraph | 6.23 | 0 | 0 | ไม่มี | [#94](https://github.com/Bobbie-CPE38/nara/pull/94) |
| N1 | คน 2 | `ATTENDANCE.shift_id`, Route check-in ของพยาบาล, Route จำลองการ check-in, รายการของด่าน proxy, Seed check-in | 6.24, 9.7 | 0 | 0 | มี (`ATTENDANCE`) | [#93](https://github.com/Bobbie-CPE38/nara/pull/93) |
| N2 | คน 2 | ตัวตรวจ `NO_SHOW` สองขั้น, ผลต่อ Roster, มาสาย | 6.24 | N1, H1 | N1, H1, G ถ้าแก้ Handler | ไม่มี | [#99](https://github.com/Bobbie-CPE38/nara/pull/99) |
| L5 | คน 3 | Test ตั้ง `LINE_MODE=simulation` เอง | | 0 | 0 | ไม่มี | [#95](https://github.com/Bobbie-CPE38/nara/pull/95) |
| H1 | คน 3 | ฟังก์ชันกลางที่สร้างเวรพร้อม Handover, Route อ่าน | 6.25, 9.7 | 0 | 0, G ถ้าแก้ Handler | มี (`STRUCTURED_HANDOVER.roster_assignment_id`) | [#96](https://github.com/Bobbie-CPE38/nara/pull/96) |
| H2 | คน 3 | ส่ง Handover ทาง LINE, คำสั่ง check-in ทาง LINE | 6.24, 6.25 | H1 | H1, N1, L5 | มี (สถานะการส่งของ Handover) | [#97](https://github.com/Bobbie-CPE38/nara/pull/97) |
| U5 | คน 1 | หน้าเว็บของรอบ 5 และ Route อ่าน Clock | 9.7 | N1, H1 | N2 | ไม่มี | [#100](https://github.com/Bobbie-CPE38/nara/pull/100) |

ลำดับ merge: 0 ก่อนทุกตัว, G ก่อน PR ใดที่แก้ Handler หรือ `orchestrator.py` (R5-Q3), N2 หลัง N1 และ H1, H2 หลัง H1, N1 และ L5, U5 หลัง N2 Migration ต่อจาก `f2a7c9d4e6b8` เป็นเส้นเดียวตามลำดับที่ merge จริง ตัวที่ merge ทีหลังต้อง Rebase แก้ `down_revision` ให้ต่อจาก head ของ `staging` และแก้ Test ของ Migration ตัวก่อนหน้าที่ตรวจ head (Test ของ Migration ทุกตัวตรวจ `len(get_heads()) == 1` CI จึงจับได้) รอบ 5 ไม่ใช้ Branch รวม ทุก PR เข้า `staging` ตรง (R5-Q1)

* **งานค้างจากรอบ 3 (R5-Q2):** LINE จริงผ่าน Tunnel ทีมแจ้งว่าทดสอบแล้วทำงานได้ปกติ บันทึกในตาราง "อะไรทดสอบด้วย fake และอะไรผ่านบริการจริง" ของส่วน "สถานะของรอบ 3" สิทธิ์ Bedrock คน 2 แจ้งภายในรอบ 6 Test ที่ตั้ง `LINE_MODE` เองคือ PR L5
* **เรื่องที่เปิดไว้ตอนปิดรอบ (อัปเดตตอน PR 0 ของรอบ 6):** (1) ขั้นที่ 1 ของ `NO_SHOW` ยกเว้นคนที่มีการยกเลิกเวรค้างรอ Window ด้วย ซึ่งกว้างกว่า Contract เดิม **ตกลงแล้ว (R6-Q14 ก): แก้ Contract ให้ตรงโค้ด** ข้อ 6.24 แก้แล้วใน PR 0 ของรอบ 6; (2) Cursor Pagination ของ `GET /me/handovers` ทำในรอบ 6 เป็น PR P1 (ข้อ 9.7); (3) สิทธิ์ Bedrock คน 2 แจ้งภายในรอบ 6 (R5-Q2) ยังไม่มีคำตอบ; (4) Test อนุมัติพร้อมกันได้ลำดับ `[202, 201]` **แก้แล้วโดย PR #103** (`test_simultaneous_per_candidate_approvals_create_two_assignments_once` เทียบ `sorted(staff_id)`) ไม่ต้องทำ; (5) บันทึกการลอง LINE จริงผ่าน Tunnel (2026-10-16) อยู่ที่ `docs/round5/pr-H2-handoff.md` และ PR 0 ของรอบ 6 เติมลงตาราง "อะไรทดสอบด้วย fake และอะไรผ่านบริการจริง" ของส่วน "สถานะของรอบ 3" แล้ว
* **Checklist ของ L5 (ไม่ใช่ Test):** รันชุด Test กับ `.env` ที่ตั้ง `LINE_MODE=real` จริงอย่างน้อยหนึ่งครั้งก่อน merge และบอกผลใน Description

**L5 ทำแล้ว:** `backend/tests/conftest.py::isolated_line` เป็น Autouse Fixture ตั้ง `LINE_MODE=simulation` ทั้งใน Environment และ `settings` ทุก Test โดยไม่แก้ `.env` ของผู้พัฒนา และแทน `urllib.request.urlopen` ด้วยตัวกันการเรียก HTTP ไป `line.me` หรือ Subdomain ที่ไม่ได้จำลองไว้ ใช้ `pytest.fail()` เพื่อไม่ให้ทางส่ง LINE ที่จับ `Exception` กลืนความล้มเหลว Test ที่ต้องใช้โหมดจริงเปิดเองและแทน `push`/`reply` หรือ HTTP transport ด้วยตัวปลอมได้ตามเดิม HTTP ภายในเครื่องของ Test อื่นยังทำงานตามปกติ Test ของด่านนี้อยู่ที่ `backend/tests/unit/integrations/test_line_isolation.py`

เรื่องที่ยังอยู่ในร่างรอบ 5 ไม่ได้ย้ายเข้าไฟล์นี้

| ร่างรอบ 5 | เรื่อง |
|---|---|
| ข้อ 1 | ฐานจากรอบ 4 ที่ตรวจกับโค้ดแล้ว และจำนวน Test ตั้งต้น (Backend 2,586 ผ่าน 14 ข้าม, Frontend 334) |
| ข้อ 2 | ขอบเขต และเรื่องที่ไม่อยู่ในรอบ 5 |
| ข้อ 9 | สิ่งที่ยังไม่ได้ตรวจ |

ถ้ากติกาที่ย้ายเข้าไฟล์นี้แล้วไม่ตรงกับร่างรอบ 5 ให้ยึดไฟล์นี้

**Test ของข้อกำหนดที่พังเงียบได้** PR 0 ระบุว่าข้อกำหนดข้างล่างผิดแล้วไม่มี Error และ PR ที่ทำต้องมี Test ของแต่ละข้อ ตอนปิดรอบตรวจแล้วว่าไฟล์และชื่อ Test ในคอลัมน์ขวามีอยู่จริงทุกแถว (`backend/tests/` และ `dev/line-webhook-proxy/`)

| ข้อกำหนด | PR | Test อยู่ที่ |
|---|---|---|
| ลำดับแถว `CASE_STATUS_CHANGED` ของ Golden Case และ Scenario ของรอบ 4 เท่ากับก่อนใช้ LangGraph | G | `test_orchestrator_graph_parity.py` |
| Handler ที่ล้มยังได้ `FAILED` พร้อม `WORKFLOW_FAILED` และงานของผู้เรียกก่อนรอบยังถูก Commit (D11) | G | `test_orchestrator.py` `test_failure_keeps_the_callers_earlier_work` ซึ่งไม่ได้แก้ |
| ส่ง LINE เกิดหลัง Commit เท่านั้น ไม่เกิดในรอบที่ล้ม | G | `test_orchestrator_graph_parity.py` |
| Migration ของ N1, H1 และ H2 ทำงานกับข้อมูลเดิม (Golden Case, Seed และแถว `ATTENDANCE` ที่ไม่มีเวร) และ Test ของรอบ 4 ยังผ่าน | N1, H1, H2 | `test_attendance_shift_migration.py` (`test_round_trip_keeps_shiftless_attendance`), `test_handover_migration.py` (`test_round_trip_preserves_existing_roster_and_attendance`), `test_handover_delivery_migration.py` (`test_upgrade_preserves_existing_snapshot_without_sending_it`) และ Test ของรอบ 4 ผ่านทั้งชุด |
| Route check-in ของพยาบาลบันทึกได้แค่ตัวผู้กด ไม่สนใจ `staff_id` ใน Query หรือ Body การจำลองทำได้แค่ Route ใต้ `/demo/` และทั้งสองใช้กติกาเดียวกัน | N1 | `test_attendance_check_in.py` (`test_me_records_only_the_caller`, `test_staff_id_in_the_query_is_ignored`, `test_staff_id_in_the_body_is_422_and_records_nothing`, `test_demo_route_records_the_given_staff_as_simulated_by_system`) |
| ด่าน `dev/line-webhook-proxy` ตอบ `404` กับ Route จำลอง check-in (เพิ่มใน `check_gate.py` และ `test_proxy.py`) | N1 | `dev/line-webhook-proxy/test_proxy.py` (Path `/demo/attendance/check-in`) |
| การจำลอง check-in เขียน Audit ที่บอกว่ามาจากการจำลอง | N1 | `test_attendance_check_in.py` (`test_demo_route_records_the_given_staff_as_simulated_by_system`) |
| `check_in_at` มาจาก `app.core.clock.now()` ตัวเดียวกับ Job: Demo Clock หยุดนิ่งแล้วกด check-in ได้เวลาของ Demo Clock และ Job ไม่นับคนนั้นเป็น `NO_SHOW` | N1, N2 | `test_attendance_check_in.py` (`test_check_in_at_is_the_frozen_clock_and_the_response_is_plus_seven`); `test_no_show_detection.py` |
| check-in ซ้ำ (กดสองครั้งหรือจำลองซ้ำ) ได้แถวเดียว และ OT ไม่นับซ้ำ | N1 | `test_attendance_check_in.py` (`test_repeats_from_me_then_demo_give_one_row_one_audit_and_the_same_answer`, `test_check_ins_do_not_change_weekly_overtime`) |
| check-in ครั้งแรกตรง `effective_end_at` พอดีได้ `422` ไม่เขียน `ATTENDANCE` และไม่เริ่มทางมาสาย ทั้งหน้าเว็บและ LINE รวมแถวที่ช่วงไม่เต็มเวร (`effective_end_at` ไม่เท่าเวลาจบเวร) ส่วน check-in ซ้ำหลังเวลานั้นยังคืนแถวเดิม | N1, H2 | `test_attendance_check_in.py` (`test_first_check_in_exactly_at_the_end_is_422`, `test_end_before_the_shift_end_closes_the_window_earlier`, `test_repeat_after_the_effective_end_still_returns_the_row`), `test_line_handover.py` (`test_checkin_boundaries_match_web`, `test_repeat_checkin_after_end_returns_original_attendance`) |
| `content.reason` ของ Handover คิดจาก Event ที่เปิดเคส (`payload.event_id` ของ `CASE_OPENED`) ด้วยฟังก์ชันเดียว เคสที่มีการลาซึ่งไม่ผ่าน Threshold และ `id` น้อยกว่า Event `PATIENT_SURGE` ที่เปิดเคส ได้ `PATIENT_SURGE` | H1 | `test_handover.py` (`test_reason_uses_the_threshold_passing_event_not_lowest_event_id`) |
| check-in ก่อนขอบเวลาที่ PR 0 กำหนด หรือหลังเวรจบ ถูกปฏิเสธ ทั้ง Route และ Job ใช้กติกาขอบเวลาเดียวกัน | N1, N2 | `test_attendance_check_in.py` (`test_exactly_one_hour_before_arrival_is_accepted`, `test_one_second_earlier_is_422_and_records_nothing`); `test_no_show_detection.py`, `test_late_arrival.py` |
| Job สองตัวตรวจ `NO_SHOW` พร้อมกัน (สอง Connection) ได้แถว `NO_SHOW` และ Event แค่ชุดเดียว | N2 | `test_no_show_detection.py` |
| Job สองรอบภายใน Window ที่ยังเปิด (`merge_window_seconds > 0`) ได้ Event `STAFF_UNAVAILABLE` ของคนนั้นในเวรนั้นแค่หนึ่ง Event | N2 | `test_no_show_detection.py` |
| ขั้นที่ 1 เขียนแค่ Event ไม่มีแถว `STAFF_UNAVAILABILITY` หรือ Audit `UNAVAILABILITY_CREATED` จนกว่า Window ปิด ขั้นที่ 2 เขียนทั้งสองอย่าง ผู้เขียน Audit เป็น Actor `SYSTEM` ไม่ใช่ตัวพยาบาล และ Event ของการลาเดิม (ไม่มี `payload.reason`) ยังเข้า `_apply_leave()` ตามเดิม | N2 | `test_no_show_detection.py`, `test_no_show_window.py` |
| ระหว่าง Event รอ Window แถว Roster ถูกยกเลิก หรือคนนั้นถูกย้ายออก ขั้นที่ 2 ข้ามเป็น `IGNORED` (`NO_ASSIGNED_ROSTER`) รวมการย้ายกลางเวรที่แถวต้นทางยังเป็น `ASSIGNED` แต่มีแถวปลายทางที่ลิงก์มา และไม่ยกเลิกแถวต้นทางนั้น | N2 | `test_no_show_window.py` |
| Window ปิดหลังแถวจบไปเอง (รอเพราะเวรมีเคสอื่นเดินอยู่) และไม่มี check-in: ยังบันทึก `NO_SHOW` กับ Audit แถวเดิมเป็น `CANCELLED` และไม่เปิดเคสหรือส่ง Offer ให้เวรที่จบแล้ว | N2 | `test_no_show_window.py` |
| Window ปิดหลังแถวจบไปเองและมี check-in สายระหว่างรอ: บันทึก `NO_SHOW` แล้วได้แถวใหม่ช่วง `check_in_at` ถึงเวลาจบเดิม ชั่วโมงทำงานตรงกับที่มาจริง และไม่เปิดการหาคน | N2 | `test_no_show_window.py` |
| แถว `REGULAR` จาก Seed ของเวรที่เริ่มแล้วตอน Reset ได้เส้นตาย = เวลาเริ่มเวร + 15 นาที ไม่ใช่เวลา Reset + 15 นาที | N2 | `test_no_show_detection.py` |
| check-in กับ Job ตรวจ `NO_SHOW` พร้อมกัน (สอง Connection) ได้ผลเดียวที่สอดคล้องกัน ไม่มี Event ซ้ำ ไม่ยกเลิกเวรผิดคน | N2 | `test_late_arrival_races.py` |
| คนที่แจ้งลาแล้ว หรือถูกย้ายออกจากเวรแล้ว ไม่ถูกนับเป็น `NO_SHOW` | N2 | `test_no_show_detection.py` |
| check-in ตรงเส้นตายของแถวพอดีนับว่าทัน และ Job ที่รันตอน `Backend Clock == เส้นตาย` พอดีไม่สร้าง Event ให้คนที่ยังไม่ check-in | N2 | `test_no_show_detection.py` |
| check-in หลังเส้นตายแต่ก่อน Job รอบถัดไป: Job ยังสร้าง Event และขั้นที่ 2 บันทึก `NO_SHOW` แล้วเดินทางมาสายจาก `check_in_at` นั้น ได้แถว Roster ใหม่หนึ่งแถว ส่วน check-in สายระหว่าง Event รอ Window ได้ผลเดียวกันตอนปิด Window | N1, N2 | `test_no_show_window.py` |
| คนแทนที่ได้เวรหลังเส้นตายของเวร (เวรเริ่ม 07:00 ได้เวรช่วง 08:00 ถึง 15:00) check-in ตอน 08:00 ทันที ไม่เป็น `NO_SHOW` | N2 | `test_no_show_detection.py` |
| คนแทนแบบเดียวกันที่ไม่ check-in เป็น `NO_SHOW` หลังเส้นตายของแถวตัวเอง (08:15) เท่านั้น ไม่ใช่ทันทีที่ได้เวร | N2 | `test_no_show_detection.py` |
| แถวใหม่ตอนมาสายไม่ถูกตรวจ `NO_SHOW` ซ้ำ และเส้นตายของแถวเดิมไม่ถูกคิดใหม่จาก `actual_start_at` ของการมาสาย | N2 | `test_no_show_detection.py`, `test_no_show_window.py` |
| Route ของหน้าเว็บ, คำสั่ง LINE และ Job ได้เวลาที่ต้องมาถึงและเส้นตายเท่ากันสำหรับแถวเดียวกัน | N1, N2, H2 | `test_attendance_time.py`, `test_line_handover.py` (`test_checkin_boundaries_match_web`); `test_no_show_detection.py` |
| ย้ายต่อกันสองครั้ง (check-in ที่ X แล้ว X → Y → Z): Z ไม่เป็น `NO_SHOW` เพราะ check-in ที่ทันสืบต่อตามโซ่ของการย้ายที่บันทึกไว้ ไม่มีแถว `ATTENDANCE` หรือ OT ซ้ำ | N2 | `test_no_show_detection.py` |
| ย้ายต่อกันสองครั้งแต่ไม่มี check-in ที่ทันในโซ่เลย: แถวปลายสุดถูกตรวจตามปกติและเป็น `NO_SHOW` | N2 | `test_no_show_detection.py` |
| แถวปลายทางของการย้ายถูกยกเว้นเฉพาะเมื่อแถวต้นทางที่ผูกกันมี check-in ย้ายทั้งเวรก่อนเวรต้นทางเริ่มแล้วไม่มา แถวปลายทางเป็น `NO_SHOW` | N2 | `test_no_show_detection.py` |
| มาสายแล้วเกิน: คนที่ครอบช่วงที่ยังขาดถูกเก็บไว้ก่อนคนที่ไปไกลกว่าแต่ไม่ครอบ (คำขอที่รออนุมัติครอบแค่ครึ่งแรก Offer ที่ยังไม่ตอบครอบครึ่งหลังที่ขาด) | N2 | `test_late_arrival.py`, `test_case_status_trim.py` |
| `NO_SHOW` หลายเวรติดกันได้แถวใหม่ทุกเวร | N2 | `test_no_show_window.py` |
| แจ้งลาย้อนหลังหลัง `NO_SHOW` แถวยังเป็น `NO_SHOW` ไม่เปลี่ยนเป็น `UNPLANNED_LEAVE` | N2 | `test_no_show_window.py`, `test_late_arrival.py` |
| มาสายแล้วชั่วโมงทำงานและ Gap ใช้เวลาที่มาจริง | N2 | `test_no_show_window.py`, `test_late_arrival.py` |
| มาสายหลังคนแทนได้เวรแล้ว คนแทนไม่ถูกยกเลิก ยกเลิกเฉพาะ Offer และคำขอที่เกินจำนวนที่เคสยังขาด และเคสที่ยังขาดคนยังหาคนต่อ (เคสขาดสองคน คนเดียวมาสาย) | N2 | `test_late_arrival.py` |
| สี่ทางที่สร้างเวรแทน (อนุมัติ, อนุมัติเอง, จัดเองใน `MANUAL_HANDOFF`, การย้าย) ได้ Handover หนึ่งแถวพอดีต่อแถว Roster | H1 | `test_handover.py` (`test_human_approval_and_d11_keep_handover_atomic`, `test_auto_approval_generates_one_handover_per_assignment`, `test_manual_assignment_generates_handover_with_human_actor`, `test_transfer_chain_has_new_handover_and_hides_source_at_effective_end`) |
| แถวใหม่ตอนมาสายของคนเดิมของเวรไม่มี Handover | N2 | `test_handover.py` (`test_late_arrival_seam_creates_handover_only_for_a_replacement`); `test_late_arrival.py` |
| คนแทนที่ได้ Handover แล้วเป็น `NO_SHOW` แล้ว check-in สาย: แถวใหม่มี Handover ที่ใช้งานอยู่หนึ่งแถวพอดี และ Handover ของแถวเก่ายังอยู่ในประวัติแต่ไม่ใช้งาน | N2 | `test_late_arrival.py` |
| Handover ไม่ถูกสร้างซ้ำเมื่อการจัดเวรถูกเรียกซ้ำ และไม่ถูกสร้างเมื่อการจัดเวร Rollback | H1 | `test_handover.py` (`test_missing_origin_rolls_back_assignment_and_handover`, `test_audit_failure_rolls_back_the_assignment_too`) |
| สอง Connection จัดเวรพร้อมกันได้ Handover แถวเดียวต่อแถว Roster (Unique Constraint) | H1 | `test_handover.py` (`test_two_connections_generate_one_handover_and_audit`) |
| Handover แสดงในรายการปัจจุบันเฉพาะแถว Roster ที่ `ASSIGNED` และ `Backend Clock < effective_end_at` เวรที่ยังไม่เริ่มแสดงได้ | H1 | `test_handover.py` (`test_nurse_and_case_api_share_views_and_keep_history`) |
| ย้ายซ้ำจากโซ่ (C3) ได้ Handover หนึ่งแถวต่อแถว Roster ใหม่ ส่วนของต้นทางหายจากรายการปัจจุบันเมื่อ `Backend Clock >= effective_end_at` แม้แถวยังเป็น `ASSIGNED` และยังอยู่ในประวัติ | H1 | `test_handover.py` (`test_transfer_chain_has_new_handover_and_hides_source_at_effective_end`) |
| ส่ง Handover ทาง LINE เกิดหลัง Commit เท่านั้น ส่งล้มไม่ย้อนการจัดเวรและ Handover ไม่หาย | H2 | `test_line_handover.py` (`test_intent_is_atomic_and_never_sends_before_commit`, `test_result_never_changes_assignment_or_case`) |
| ก่อนส่งและทุกครั้งที่ลองใหม่ ตรวจว่า Handover ยังใช้งานอยู่ Handover ที่ไม่ใช้งานแล้วไม่ถูกส่ง | H2 | `test_line_handover.py` (`test_recheck_before_retry_cancels_stale_messages`) |
| check-in ทาง LINE ระบุตัวคนจากบัญชีที่ผูกแล้วเท่านั้น ใช้ขอบเวลาและกติกาทัน/สายเดียวกับ Route ของหน้าเว็บ และผู้ส่งที่ไม่ได้ผูกบัญชีไม่ได้สร้างแถว | H2 | `test_line_handover.py` (`test_checkin_uses_bound_identity_and_dedups`, `test_checkin_boundaries_match_web`, `test_refused_commands_are_terminal_without_attendance`) |
| Test ผ่านเมื่อ `.env` ตั้ง `LINE_MODE=real` และ HTTP client ของ LINE ถูกแทนด้วยตัวที่ทำให้ Test ล้มถ้าถูกเรียก | L5 | `tests/conftest.py` (`isolated_line`), `test_line_isolation.py` (`test_accidental_real_mode_cannot_call_line`) |

## สถานะของรอบ 6

Contract ของรอบ 6 ตกลงแล้ว (PR #104) ไฟล์นี้รับเฉพาะกติกาที่ข้ามคน ส่วน Spec เต็มของรอบอยู่ที่ `docs/round6/round6-contract-draft.md` (ในไฟล์นี้เรียกว่า "ร่างรอบ 6") เลข R6-Q ที่อ้างในไฟล์นี้คือคำถามใน `docs/round6/round6-questions.md` คำตอบเป็นการตัดสินใจร่วมกันของทั้งสามคน (R6-Q1 ถึง R6-Q19 ตอบครบ)

**รอบ 6 กำลังทำ** กติกาของรอบ 6 ในไฟล์นี้อยู่ที่ส่วนนี้, ข้อ 6.15 (จุดเข้าคิวของคำอธิบายอันดับเปลี่ยน), 6.17 (ด่านของเครื่อง AWS), 6.24 (ข้อยกเว้นของ `NO_SHOW` แก้ให้ตรงโค้ด), 6.27 ถึง 6.31 และ 9.8 กติกาที่ยังไม่มีโค้ดมีป้าย **[รอบ 6 · PR X]** บอกว่า PR ไหนต้องทำ PR นั้นลบป้ายออกเมื่อทำแล้ว PR 0 เพิ่มแค่กติกาในไฟล์นี้, `docs/database-schema.md` และค่าใหม่ใน `enums.py`, `core/constants.py` ไม่เปลี่ยนพฤติกรรมของระบบ ฐานตอนเริ่มรอบ: `staging` ที่ `e95dfaa` (โค้ดเหมือน `de9e1ef`) Migration head `c5f8b0d3e7a1` Test: Backend 2,884 ผ่าน 14 ข้าม, Frontend 351

| PR ของรอบ 6 | ใคร | เรื่อง | ข้อของไฟล์นี้ | เริ่มได้หลัง | merge ได้หลัง | Migration | PR บน GitHub |
|---|---|---|---|---|---|---|---|
| เอกสาร | คน 1 | ร่างรอบ 6 และไฟล์คำถาม | | | | ไม่มี | [#104](https://github.com/Bobbie-CPE38/nara/pull/104) |
| 0 | คน 1 | ย้าย Contract เข้าไฟล์นี้, ค่าใหม่ใน Enum และ constants, แก้ข้อ 6.24 ให้ตรงโค้ด, เติมตาราง fake กับของจริง | ทุกข้อของรอบ 6 | เอกสาร | เอกสาร | ไม่มี | [#105](https://github.com/Bobbie-CPE38/nara/pull/105) |
| B1 | คน 2 | ที่เก็บบันทึกการเรียก LLM และตัวห่อการเรียก, ตัวนับรายวัน, แปลงตัวประมวลผลเดิม, เพดาน Input/Output, ตัวกัน Test, ตัวตรวจตัวเลข | 6.27, 6.28 | 0 | 0 | มี (`LLM_CALL_LOG` และตัวนับ) |[#108](https://github.com/Bobbie-CPE38/nara/pull/108) |
| D | คน 1 (คน 2 ส่วน Bedrock, คน 3 ส่วน LINE) | เครื่อง AWS: ไฟล์ Compose, Caddy, `check-gate.sh`, `test_gate.py` ตามกฎข้อ 6.30 เขียนโค้ดและ merge ได้ ไม่เปิดเครื่อง | 6.17, 6.30 | 0 | 0 | ไม่มี | [#107](https://github.com/Bobbie-CPE38/nara/pull/107) |
| I | คน 3 | ตอบข้อความส่วนตัวตามสี่กรณี: ยังไม่ผูกบัญชี, มีข้อเสนอรอตอบ, ตอบรับแล้วรอผลรวมตัวสำรอง, ไม่มีรายการรอดำเนินการ ไม่ใช้ LLM | 6.29 | 0 | 0 | ไม่มี | [#106](https://github.com/Bobbie-CPE38/nara/pull/106) |
| E1 | คน 2 | Backend ของผู้ใช้กดขอคำอธิบายอันดับ: เลิกเข้าคิวอัตโนมัติ, Route ขอ, สถานะและธง `can_request` | 6.15, 6.27, 9.8 | B1 | B1 | อาจมี | |
| F1 | คน 2 | Route อ่านอย่างเดียว: `GET /dashboard` และเช็ค Gap | 6.31, 9.8 | 0 | 0 | ไม่มี | |
| P1 | คน 3 | Cursor Pagination ของ `GET /me/handovers` พร้อมตัวอ่านในหน้าพยาบาล | 9.7 | 0 | 0 | ไม่มี | [#109](https://github.com/Bobbie-CPE38/nara/pull/109) |
| E2 | คน 1 | ปุ่ม "หน้าสรุปด้วย AI" และสถานะในหน้าเคส | 6.27, 9.8 | E1 | E1 | ไม่มี | |
| F2 | คน 1 | หน้า Dashboard (แทน `/`), หน้า `/gap`, เมนู | 6.31 | F1 | F1 | ไม่มี | |
| S | คน 3 | LLM สรุปสถานการณ์ของเคส: ตารางสรุปผูก Snapshot พร้อมประวัติ, Route ขอสรุป, ปุ่มและสถานะในหน้าเคส | 6.27, 9.8 | B1, E1 | B1, E1 | มี (ตารางสรุปเคส) | |
| F3 | คน 1 | เตรียมเว็บก่อน Deploy ช่วง ก (ตรวจในเครื่อง) | 6.30 | F2, D | F2 และ D | ไม่มี | |
| ขั้นที่ 6 (ไม่ใช่ PR) | ทั้งสามคน | เปิดเครื่อง AWS ตรวจช่วง ข แล้วเปิดให้ภายนอกเข้า | 6.30 | D, F3 | | | |
| B2 | คน 2 | ลอง Bedrock จริง 20 ถึง 30 เคส เลือกโมเดล ผ่านตัวห่อของ B1 | 6.28 | B1 และขั้นที่ 6 | ขั้นที่ 6 | ไม่มี | |
| W | คน 3 | ย้าย Webhook จาก Tunnel มาเครื่อง ปิด Tunnel | 6.16, 6.30 | D และขั้นที่ 6 | ขั้นที่ 6 | ไม่มี | |
| ปิดรอบ | คน 3 | เอกสารปิดรอบ แล้ว `staging` → `main` และ tag `v0.7-round6` | | ทุกตัว | ทุกตัว | ไม่มี | |

ลำดับ merge: 0 ก่อนทุกตัว, B1 ก่อน E1, S และ B2, E1 ก่อน E2 และ S, F1 ก่อน F2, F2 และ D ก่อน F3, F3 และ D ก่อนขั้นที่ 6, ขั้นที่ 6 ก่อน B2 และ W Migration ของ B1, S และ E1 (ถ้ามี) ต่อจาก `c5f8b0d3e7a1` เป็นเส้นเดียว ตัวที่ merge ทีหลัง Rebase `down_revision` และแก้ Test ของ Migration ตัวก่อนหน้าที่ตรวจ head ผู้ทำของ P1 และการให้คน 3 ปิดรอบเป็นข้อเสนอของร่างรอบ 6 ถ้าทีมเปลี่ยน แก้ตารางนี้

* **เปิด LLM ในแอปหลัง E1:** `LLM_ENABLED=true` ห้ามตั้งบนเครื่อง AWS จนกว่า E1 merge (ข้อ 6.27) B2 รันชุดทดลองผ่านตัวห่อของ B1 ได้ก่อน
* **งานค้างจากรอบ 5 (R6-Q14 ก):** ข้อยกเว้นของ `NO_SHOW` แก้ที่ข้อ 6.24 แล้วใน PR 0 (ไม่มี PR โค้ด), Pagination ของ `/me/handovers` เป็น P1, Test อนุมัติลำดับ `[202, 201]` แก้แล้วโดย PR #103 (ไม่มี PR)
* **งานค้างจากรอบ 3 และ 5:** ผลลอง LINE จริงผ่าน Tunnel (2026-10-16) บันทึกลงตาราง fake กับของจริงแล้ว สิทธิ์และเครดิต Bedrock ใน Region คน 2 ยืนยันก่อนลองจริง (ข้อ 6.28 ขั้น 1)
* **ค่าที่ PR 0 กำหนดและเก็บใน `core/constants.py`:** เพดาน 100 ครั้งต่อวัน (`LLM_DAILY_CALL_CAP`) เวลา Asia/Bangkok (`LLM_QUOTA_TIMEZONE`) งบ 20 USD ต่อเดือน (`LLM_MONTHLY_BUDGET_USD`) Input ไม่เกิน 5,000 token (`LLM_MAX_INPUT_TOKENS`) Attempt สูงสุด 4 ต่อแถวตลอดอายุ (`LLM_MAX_ATTEMPTS_PER_ROW`) และเพดานชุดทดลอง 30 เคส × 3 โมเดล × 2 Attempt = 180 ครั้ง (`LLM_TRIAL_CALL_CAP`) เพดาน Output ใช้ `LLM_MAX_OUTPUT_TOKENS` เดิม (ค่าเริ่มต้น 1,024) ค่าเหล่านี้เป็นค่าเริ่มต้น B1 อ่านเข้าค่าตั้งให้ปรับได้ ตัวเลข 4 Attempt เป็นค่าที่ PR 0 เสนอ (ร่างรอบ 6 ให้กำหนดตอนนี้) ทีมแก้ได้ใน PR นี้
* **ประมาณการค่าใช้จ่ายของเพดานเริ่มต้น (ราคาตรวจแล้วกับ AWS Price List ดูข้อ 6.28):** Amazon Nova 2 Lite แบบ Standard ใน Singapore Input 0.41 และ Output 3.39 USD ต่อล้าน token ที่ Input 5,000 และ Output ที่เพดาน 1,024 token ต่อครั้งเท่ากับ 0.00552136 USD ต่อครั้ง ครบ 100 ครั้งทุกวัน 30 วันได้ 16.56408 USD (ตรวจด้วยโค้ด) ชุดทดลองเต็ม 180 ครั้งได้ 0.9938448 USD รวมแล้วต่ำกว่า 20 USD ถ้าเลือกโมเดลที่แพงกว่า ต้องคำนวณใหม่ก่อนเริ่ม

เรื่องที่ยังอยู่ในร่างรอบ 6 ไม่ได้ย้ายเข้าไฟล์นี้

| ร่างรอบ 6 | เรื่อง |
|---|---|
| ข้อ 1 | ฐานจากรอบ 5 ที่ตรวจกับโค้ดแล้ว และจำนวน Test ตั้งต้น |
| ข้อ 2 | ขอบเขต และเรื่องที่ไม่อยู่ในรอบ 6 |
| ข้อ 7 | น้ำหนักงานของแต่ละคนและเหตุผลการจัดผู้ทำ |
| ข้อ 9 | สิ่งที่ยังไม่ได้ตรวจ |

ถ้ากติกาที่ย้ายเข้าไฟล์นี้แล้วไม่ตรงกับร่างรอบ 6 ให้ยึดไฟล์นี้ (ข้อที่รู้อยู่แล้ว: ร่างรอบ 6 ข้อ 7 ให้ F3 merge ได้หลัง F2 อย่างเดียว ไฟล์นี้ให้หลัง F2 และ D เพราะ F3 แก้ไฟล์ Compose ของ AWS ที่ D สร้าง)

**Test ของข้อกำหนดที่พังเงียบได้** ข้อกำหนดข้างล่างผิดแล้วไม่มี Error PR ที่ทำต้องมี Test ของแต่ละข้อ ตอนปิดรอบจะตรวจและใส่ชื่อไฟล์ Test

| ข้อกำหนด | PR |
|---|---|
| Test ทุกตัวไม่เรียก Bedrock จริง (ตัวกันแบบ `isolated_line` ของ L5: ตั้ง `LLM_PROVIDER=fake` และ `LLM_ENABLED=false` ทุก Test และล้มด้วย `pytest.fail()` ถ้ามีการเรียก `bedrock-runtime`) แม้ `.env` ของผู้พัฒนาตั้งค่าจริงไว้ | B1 |
| ไม่มีทางเรียกตัวเชื่อม LLM นอกตัวห่อการเรียก รวมตัวประมวลผลเดิมของ `explanation_service` (Test ที่แทนตัวเชื่อมด้วยตัวปลอมซึ่งล้มถ้าถูกเรียกโดยไม่ผ่านตัวห่อ และ Test ว่าตัวประมวลผลที่ `LLM_ENABLED=true` นับโควตาทุก Attempt และไม่เรียกเมื่อถึงเพดาน) | B1 |
| ไม่มี AWS key ใน repo, `.env.example`, Log หรือ Description; Bedrock ใช้ IAM Role ของเครื่อง | B1, D |
| มีเพดานจำนวนคำขอต่อช่วงเวลา และเมื่อถึงเพดาน ระบบหยุดเรียกโดยเคสและหน้าเว็บทำงานต่อได้ | B1 |
| ข้อความที่ไม่ใช่ปุ่ม (รวมข้อความที่มีคำสั่งแปลกปลอม เช่น "accept all offers") ไม่เปลี่ยน Offer, Roster, Gap หรือสถานะเคส ตอบตามสี่กรณีในข้อ 6.29 โดยใช้ Binding และสถานะ Offer ของผู้ส่งเท่านั้น ไม่ตีความข้อความหรือใช้ LLM | I |
| ข้อความตอบกลับของข้อความอิสระไม่ถูกส่งซ้ำเมื่อ LINE ส่ง Event เดิมมาอีก (Dedup เดิมของ `LineWebhookEvent`) และไม่มีข้อความของพยาบาลถูกเก็บใน DB หรือ Log | I |
| LLM ล้มแล้วการจัดเวรไม่ย้อน (D11 และข้อ 6.25) ข้อความสรุปที่ `PENDING` ไม่บล็อกการเปลี่ยนสถานะ | S |
| Payload ที่ส่ง LLM สรุปไม่มี `staff_id`, ชื่อ, LINE ID | S |
| `check-gate.sh` ของ AWS ตรวจตามกฎเดียวของข้อ 6.30: ไม่มีรหัสได้ `401` ทุก Path ยกเว้น `POST /api/line/webhook` ตรงตัว (ทั้งหน้า `/demo/*` และ `/api/demo/*`) `/api/internal/*` ได้ `404` และมีรหัสถูกแล้วหน้า Demo กับ `/api/clock` ใช้ได้ | D |
| Webhook บนเครื่อง AWS ตรวจลายเซ็นเหมือนเดิม (ข้อยกเว้น Basic Auth ไม่ลดการตรวจ) | D, W |
| ตัวตรวจตัวเลขในประโยค LLM ปฏิเสธประโยคที่มีตัวเลขนอกชุดของ Payload ทั้งประโยคอธิบายอันดับและสรุปสถานการณ์ และไม่แสดงประโยคนั้น (R6-Q8 ก) | B1, S |
| ขั้นตอนเลือกโมเดล (ข้อ 6.28) ไม่ลดเกณฑ์เพื่อให้ผ่าน และผลดิบของการลองเก็บไว้ให้ตรวจย้อนได้ | B2 |
| ตัวนับคำขอรายวันของ Bedrock ไม่เกินเพดานเมื่อ Worker หลายตัวเรียกพร้อมกัน (Test สอง Connection) ไม่ถูกล้างเมื่อรีสตาร์ต และเปลี่ยนวันตามเวลา Asia/Bangkok | B1 |
| ถึงเพดานรายวันแล้ว ไม่มีการเรียก Bedrock เพิ่ม ปุ่มขอคำอธิบายปิดสำหรับ Plan ที่ยังไม่มีคำอธิบาย (ข้อความตามข้อ 6.27) Plan ที่มีคำอธิบายแล้วยังอ่านได้ และการจัดเวร การอนุมัติ และ Ranking ทำงานต่อ | B1, E1, E2 |
| หลังสร้าง Plan ไม่มีแถว `rank_explanation` และไม่มีการเรียก LLM จนกว่าผู้ใช้จะขอ (Test ที่ตรวจว่า `optimize` ไม่เข้าคิวเอง) | E1 |
| ขอคำอธิบายซ้ำ รีเฟรช หรือกดพร้อมกันหลาย Connection ได้แถวเดียวและเรียก LLM ไม่เกินจำนวน Attempt ที่กำหนดต่อแถว (Test สอง Connection) | E1 |
| ขอผ่าน API ตรงตอนตัวนับถึงเพดานแล้วถูกปฏิเสธโดยไม่เรียก Bedrock และกดพร้อมกันตอนเหลือโควตา 1 ครั้งเรียกได้ครั้งเดียว | B1, E1 |
| คำอธิบายที่ล้มเหลวหรือถึงเพดานไม่ถูกเก็บเป็น `READY` และข้อความแจ้งข้อผิดพลาดไม่ถูกแสดงเป็นคำอธิบายของ AI | E1, E2 |
| ขอใหม่หลังล้มเหลว: ตัวนับ Attempt และยอดโควตาที่ใช้ไปไม่ถูกล้าง กดซ้ำเพื่อรีเซ็ต Retry ไม่ได้ และแถวที่ `READY` แล้วขอซ้ำไม่ได้ | E1 |
| สรุปเคส: ข้อมูลไม่เปลี่ยนแสดงฉบับเดิมไม่เรียก LLM ข้อมูลเปลี่ยนแสดงว่าล้าสมัยและเปิดปุ่มสร้างฉบับใหม่ ฉบับเก่ายังอยู่ในประวัติ และ Payload ของข้อมูลเดิมให้ Hash เดิมทุกครั้ง | S |
| ชุดทดลองเลือกโมเดลเรียกได้จากสคริปต์ภายในเท่านั้น API ของผู้ใช้ไม่มีตัวเลือกประเภทนี้ ถึงเพดานของชุดทดลองแล้วหยุด และ `llm_call_log` แยกประเภทครบ | B1, B2 |
| ค่าใช้จ่ายรวมทุกประเภทรวมกันอยู่ในรายงานเดียว (Dashboard แสดงยอดรวมเทียบ 20 USD) | B1, F1 |
| Plan ใหม่จากการจัดอันดับใหม่ไม่ใช้คำอธิบายของ Plan เก่า | E1 |
| Payload ที่เกินเพดาน Input ไม่ถูกส่ง LLM | B1 |
| Route อ่านอย่างเดียวของ Dashboard และหน้าเช็ค Gap ไม่เขียนฐานข้อมูล (ไม่สร้างแถว Gap, Event, Audit หรือเคส) | F1 |
| Dashboard และหน้าเช็ค Gap แสดงเฉพาะข้อมูลของหอที่ผู้ใช้ Demo เห็นได้ และ Supervisor เห็นทุกหอ | F1, F2 |
| ตัวเลข Gap ของหน้าเช็ค Gap ตรงกับ Gap ในหน้าเคสของเวรเดียวกัน เมื่อเวรมีเคสอยู่ | F1 |
| Bundle ที่ build สำหรับ AWS ไม่มี `localhost:8000` ในไฟล์ที่ไม่ใช่ `.map` และ Frontend ที่ build แล้วเปิดทุกหน้าได้ | F3 |
| ขั้นที่ 1 ของ `NO_SHOW` ข้ามคนที่มี Event ยกเลิกเวร (`ASSIGNMENT_CANCELLED`) รอ Window และคนที่ย้ายออกกลางเวร ตรงกับข้อ 6.24 ที่แก้แล้ว (Test อยู่แล้วตั้งแต่รอบ 5 ใน `test_no_show_detection.py`: `test_a_person_with_a_cancellation_waiting_for_its_window_is_not_a_no_show`, `test_a_person_moved_out_of_the_row_mid_shift_is_not_a_no_show`) | PR 0 |
| เพดานของชุดทดลองสะสมตามรหัสชุดทดลอง ไม่ถูกต่อใหม่เมื่อข้ามเที่ยงคืน Asia/Bangkok และไม่ถูกต่อใหม่เมื่อเปิด Session หรือรีสตาร์ต (Test เลื่อน Clock ข้ามเที่ยงคืนกลางชุดและสร้าง Session ใหม่ แล้วนับต่อจากเดิม) สองคำสั่งจองพร้อมกันตอนเหลือ 1 ครั้งได้ครั้งเดียว และเรียกซ้ำพร้อมเพดานที่ใหญ่กว่าไม่เปลี่ยนเพดานของชุดเดิม | B1 |
| ขอซ้ำเมื่อแถวใช้ Attempt ครบ `LLM_MAX_ATTEMPTS_PER_ROW`: ทั้งคำอธิบายและสรุปเคสได้ `409` `LLM_ATTEMPTS_EXHAUSTED` แถวไม่กลับเป็น `PENDING` Attempt ไม่เพิ่ม และตัวนับโควตาไม่เปลี่ยน; เมื่อ Attempt ครบและถึงเพดานพร้อมกันตอบ `LLM_ATTEMPTS_EXHAUSTED` ก่อน (เหตุถาวรมาก่อน) | E1, S |
| ตัวห่อการเรียก commit แถว `IN_FLIGHT` ก่อนเรียกเครือข่าย และไม่มี Transaction หรือ Lock ค้างระหว่างรอ Bedrock (Test ใช้ตัวเชื่อมปลอมที่ระหว่างถูกเรียกอ่านแถว `IN_FLIGHT` ด้วย Connection อื่นได้ และเขียน `LLM_DAILY_USAGE` ได้โดยไม่รอ) | B1 |

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
| Ratio | ผู้ป่วยต่อพยาบาลของเวรเกินค่าที่กำหนด: `patient_count > maximum_patients_per_nurse * จำนวนคนในเวร` | `SHIFT.patient_count`, Roster ที่ `ASSIGNED` หรือ `COMPLETED` (ข้อ 6.18), `HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse` |
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
| จำนวนคนในเวร | นับใหม่จาก Roster ที่ `ASSIGNED` หรือ `COMPLETED` (ข้อ 6.18) หลังวนครบทุก Event การลาของทุก Event ใน Window ถูกหักแล้ว |
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
* `current_valid_staff` = จำนวนคนในเวรที่นับตอนนี้ (Roster ที่ `ASSIGNED` หรือ `COMPLETED` ข้อ 6.18) ไม่เปลี่ยนวิธีนับ
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
  | `SHIFT_ENDED` | `NO_SHOW` ที่ลงผลเป็นประวัติอย่างเดียวเพราะเวรจบแล้วตอนปิด Window และไม่มี Event อื่นใน Window เปิดเคส (ข้อ 6.24, รอบ 5 PR N2) | เฉพาะ Event ตัวนั้น |

* แถว `EVENT_IGNORED` ของ Event ที่ Update table ไม่ได้ (`NO_ASSIGNED_ROSTER` และ `REQUIREMENT_ITEM_NOT_FOUND`) ถูกเขียนตอนถึงคิวของ Event ตัวนั้น แทนที่แถว Action ของมัน ส่วน `THRESHOLD_NOT_PASSED`, `NO_GAP` และ `SHIFT_ENDED` เขียนหลังวนครบทุก Event
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
* รอบ 3 PR R เพิ่มขั้นแรกของ `run_due_work()`: ตั้ง Roster ของเวรที่จบแล้วเป็น `COMPLETED` (ข้อ 6.18) ใน Commit ของตัวเอง ขั้นนี้ไม่เปลี่ยนการนับใด จึงอยู่ลำดับไหนก็ได้
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
| `MANUAL_HANDOFF` | ไม่เหลือผู้สมัคร ส่งต่อให้คนจัดการ Workflow อัตโนมัติหยุด | หยุดอัตโนมัติ | ✅ (หยุดที่สถานะนี้) เคสออกได้สองทาง คือ T8 และ T9 จากการกระทำของ Head Nurse หรือจากขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด (ข้อ 6.12) |
| `UNRESOLVED` | คนจัดการแล้วแต่แก้ไม่ได้ | สิ้นสุด | ✅ ปลายทางของ T9 |
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

PR T: เพิ่มแล้ว: `stage` ค่าใหม่ `APPROVAL_TIMEOUT` สำหรับผู้สมัครที่คำขออนุมัติหมดเวลา แยกจาก `APPROVAL_REJECTED` และเมื่อผู้สมัครถูกติดต่อรอบที่สอง `stage` อ่านจาก Offer ที่ `id` มากสุดของผู้สมัครคนนั้น (ข้อ 6.13)

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
| T6 | `OPTIMIZING` | `MANUAL_HANDOFF` | Solver ไม่ได้ผู้สมัครเลย Handler `optimize` บันทึก Plan `INFEASIBLE` เขียน `SOLVER_EXECUTED` และ `MANUAL_HANDOFF` (`NO_FEASIBLE_PLAN`) แล้วคืน `MANUAL_HANDOFF` (ตั้งแต่ PR 2a) ตั้งแต่รอบ 2 PR B มีอีกเหตุหนึ่ง: Solver หมดเวลาโดยยังไม่มีแผน Plan เป็น `UNKNOWN` และเหตุผลเป็น `SOLVER_TIMEOUT` (ข้อ 6.14) |
| T7 | `OUTREACH` | `WAITING_APPROVAL` | `contact_candidate` ไม่เหลือผู้สมัครที่ส่ง Offer ได้ แต่ยังมีคนรออนุมัติที่เติม Gap ได้ |

เส้นของ T2 และ T3 ยังถูกใช้อีกแบบโดย `recompute()` ตอนเคสไม่เหลือใครให้ติดต่อ: ไป `WAITING_APPROVAL` เมื่อยังมีคนรออนุมัติ และไป `WAITING_RESPONSE` เมื่อเหลือแต่ Offer ที่ถูกพัก (ข้อ 5.3 กฎข้อ 5 และ 6) และเคสที่ได้คนครบตอนอยู่ `WAITING_RESPONSE` ผ่านเส้นของ T2 ไป `EXECUTING`

เส้นเดิมที่เลิกใช้: `WAITING_RESPONSE → SAFETY_VALIDATION` และ `SAFETY_VALIDATION → WAITING_APPROVAL` เพราะ Safety ตรวจรายคนตอนตอบรับ เคสไม่หยุดที่สถานะนี้ (Q31) สองเส้นนี้ลบออกจาก `transitions.py` แล้วใน PR 3 พร้อม Handler ของสถานะนี้ ค่า `SAFETY_VALIDATION` ยังอยู่ใน Enum และเหลือเส้นไป `FAILED` เส้นเดียวเหมือนทุกสถานะที่ไม่ใช่สิ้นสุด

เส้นใหม่ของรอบ 2

รอบ 1 หยุดเคสไว้ที่ `MANUAL_HANDOFF` โดยไม่มีทางไปต่อ รอบ 2 เพิ่มสองเส้นออก ไม่มี Handler และ `recompute()` ไม่เดินเส้นนี้ ผู้เดินมีสองแบบเท่านั้น คือ Route ของ PR H ที่ Head Nurse กด และขั้นปิด Window เมื่อเคสใหม่ของเวรเดียวกันเปิด (เฉพาะ T9) เส้นทั้งสองอยู่ใน `transitions.py` ตั้งแต่ PR 0 ของรอบ 2 และผู้เดินทั้งสองแบบมีโค้ดตั้งแต่ PR H (ข้อ 6.12)

| # | จาก | ไป | เกิดเมื่อ |
|---|---|---|---|
| T8 | `MANUAL_HANDOFF` | `RESOLVED` | Head Nurse จัดคนเข้าเวรเองจนคนที่ได้เข้าเวรปิด Gap ของเคสครบทั้งจำนวนคน, Role และ Skill (ข้อ 6.12) Head Nurse ไม่ต้องกดปิดเคส Route จัดคนเองของ PR H เรียก Orchestrator ให้เดินเส้นนี้ใน Transaction เดียวกับการจัดคนที่ทำให้ Gap ถูกปิด ไม่ใช่ `recompute()` |
| T9 | `MANUAL_HANDOFF` | `UNRESOLVED` | มีสองทาง ทางแรก Head Nurse ปิดเคสโดยไม่มีคนแทนพร้อมเหตุผล ทางที่สอง**ระบบปิดเอง**: เมื่อเคสใหม่ของเวรเดียวกันเปิด ขั้นปิด Window ปิดเคสเดิมที่ยัง `MANUAL_HANDOFF` ด้วย Actor `workflow_orchestrator` (ข้อ 6.12) ทั้งสองทางเรียก Orchestrator ไม่ใช่ `recompute()` |

* ไม่มีเส้นจาก `MANUAL_HANDOFF` กลับเข้าเส้นทางอัตโนมัติ เช่น กลับไป `OPTIMIZING` หรือ `OUTREACH` Solver ยังรันครั้งเดียวต่อเคส (Q37, R2-Q8)
* `FAILED` ยังเป็นจุดจบ ไม่มีเส้นออก เคส `FAILED` แสดงในรายการของ Head Nurse แต่กดจัดการไม่ได้ (R2-Q22)
* เคสเข้า `MANUAL_HANDOFF` ทาง T6 ได้อีกเหตุหนึ่ง คือ Solver หมดเวลาโดยยังไม่มีแผน (สถานะ `UNKNOWN`) เหตุผลใน Audit คือ `SOLVER_TIMEOUT` (ข้อ 6.14 ตั้งแต่รอบ 2 PR B)

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

* เคสไม่ไป `MANUAL_HANDOFF` ตอนที่ยังมีคนรออนุมัติที่เติม Gap ได้ เพราะยังมีทางแก้ผ่าน Workflow ปกติ รอจนผู้อนุมัติตัดสิน การอนุมัติมีเส้นตายตั้งแต่ PR T (ข้อ 6.13)
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
| 5 | Safety → Approval Request | คน 2 (PR 3) | Safety ผ่าน: `safety_service` เรียกฟังก์ชันสร้างคำขอใน `approval_service` (`create_request(db, *, case, item, outreach)`) ซึ่งสร้าง `APPROVAL_REQUEST` หนึ่งแถวของผู้สมัครคนนั้น และเขียน `APPROVAL_REQUESTED` ใน Transaction ของการตอบรับ PR 3 เป็นคนย้ายโค้ดนี้ออกจาก `safety_service` และ Handler `validate_safety` (ไฟล์ `approval_service` เป็นของคน 3 แจ้งก่อนแก้) PR 4 ไม่ต้องทำส่วนนี้ `case_id` = เคสนั้น `candidate_item_id` = Item ของ Outreach ที่ตอบรับ โหลด Plan จาก `item.plan_id` แล้วตรวจ `plan.case_id == case.id` (FK สองตัวไม่ได้รับประกันข้อนี้) ตั้ง `approval_mode = MANUAL`, `required_approver_role` = `id` ของ Role ชื่อ `HEAD_NURSE` (ค้นด้วยชื่อ), `is_pending = true`, `requested_at = clock.now()` Safety ไม่ผ่าน: ไม่สร้าง Request และ Offer ของคนนั้นเป็น `CANCELLED` ผ่านฟังก์ชันเดียวใน `outreach_service` (Q8) |
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
   * เคสนี้ติดต่อไปแล้ว: Offer เป็น `REJECTED`, `CANCELLED`, `TIMEOUT` หรือยัง `SENT` / `ACCEPTED` อยู่ ข้อยกเว้นตั้งแต่ PR T: มี Offer เพียงใบเดียวและคำขอของใบนั้น is_timed_out=true ให้กลับเข้าคิวได้หนึ่งครั้ง คนที่ไม่มีสิทธิ์ retry ไม่อยู่ใน `skipped` เพราะผลอยู่ในประวัติ Offer แล้ว
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



Offer มี Timeout ตามข้อนี้ ส่วนคำขออนุมัติมีเส้นตายแยกต่างหากตั้งแต่ PR T (ข้อ 6.13) Offer ACCEPTED ไม่หมดเวลาเอง แต่ถูก CANCELLED เมื่อคำขออนุมัติหมดเวลา

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

**PR A และ S:** การตัดสินอนุมัติ (`decide()` ที่คนกด และ Job อนุมัติเอง) ล็อกแถว `WARD` ของหอปลายทางก่อน `SHIFT` ลำดับเต็มอยู่ในข้อย่อย "ตัดสินอนุมัติในรอบ 4" ข้างล่าง เส้นทางอื่นทุกเส้นยังเริ่มที่ `SHIFT` ตามเดิม

* **ตอบ Offer:** ล็อก Offer ที่ยังไม่จบของเคสทุกแถว เรียงตาม `id` (รวมของผู้ตอบเอง) → เคส → แถว `STAFF` ของผู้สมัครทั้ง Plan ของเคส ใน Query เดียวที่เรียงตาม `id` แล้วตรวจซ้ำว่าผู้ตอบไม่ได้รับของเคสอื่นค้างอยู่ (ข้อ 6.8) ผู้สมัครที่ตอบรับสองเคสพร้อมกันจึงได้ผลสำเร็จเคสเดียว
  * เหตุผลที่ล็อก Offer ทุกแถวของเคส: คำตอบนี้อาจทำให้เคสเข้า `MANUAL_HANDOFF` ซึ่งยกเลิก Offer ที่ยัง `SENT` ของคนอื่น
  * เหตุผลที่ล็อก `STAFF` ทั้ง Plan ไม่ใช่แค่ของผู้ตอบ: คำตอบนี้อาจทำให้เคสส่ง Wave ถัดไปใน Transaction เดียวกัน ซึ่งต้องล็อก `STAFF` ทั้ง Plan ถ้าถือแถวของผู้ตอบไว้ก่อนแล้วค่อยล็อกที่เหลือ สองเคสที่ใช้ผู้สมัครชุดเดียวกันจะค้างกันได้ เช่น เคส A ถือแถวของ 202 แล้วรอ 201 ส่วนเคส B ถือแถวของ 201 แล้วรอ 202
* **ตัดสินอนุมัติ:** การอนุมัติสร้าง Roster อาจเป็นคนสุดท้ายที่ทำให้ Gap ถูกปิด และต้องยกเลิก Offer ของผู้สมัครคนนั้นในเคสอื่นที่ขัดกับเวรใหม่ จึงล็อกตามลำดับ: `SHIFT` → `APPROVAL_REQUEST` → Offer ที่ยังไม่จบของเคสนี้ทุกแถว **รวมกับ** Offer ที่ยังไม่จบของผู้สมัครคนนั้นในเคสอื่น ล็อกใน Query เดียว เรียงตาม `id` → เคส → `STAFF` ของผู้สมัครทั้ง Plan ของเคส ใน Query เดียวที่เรียงตาม `id` เหตุผลที่ต้องล็อก Offer ก่อนเคสและก่อน `STAFF`: การตอบ Offer ล็อก Offer ก่อนแล้วจึงล็อก `STAFF` ถ้าการอนุมัติถือ `STAFF` ก่อนแล้วไปรอ Offer จะค้างกับผู้สมัครที่กดตอบ Offer นั้นพอดี หลังล็อกครบจึงตรวจว่า Offer ไหนขัดกับเวรใหม่ แล้วยกเลิกเฉพาะแถวนั้น **PR A และ S:** ลำดับนี้มี `WARD` นำหน้า ดูข้อย่อย "ตัดสินอนุมัติในรอบ 4"
* **ลำดับย่อยในชั้นเดียวกัน:** `APPROVAL_REQUEST` ก่อน `CANDIDATE_OUTREACH` การตอบ Offer สร้าง `APPROVAL_REQUEST` แถวใหม่ได้ แต่ไม่ล็อกแถวที่มีอยู่ จึงไม่สวนกัน
* **Offer หมดเวลา (Job):** ล็อก Offer ที่ยังไม่จบของเคสทุกแถว เรียงตาม `id` → เคส → `STAFF` ของผู้สมัครทั้ง Plan ของเคส แบบเดียวกับการตอบ Offer เพราะเคสอาจส่ง Wave ถัดไปหรือเข้า `MANUAL_HANDOFF` ได้เหมือนกัน
* **กติการวม:** ทุกเส้นทางที่เรียก `recompute()` ล็อกตามลำดับเดียวกัน: Offer ที่ยังไม่จบของเคสทุกแถว → เคส → `STAFF` ของผู้สมัครทั้ง Plan แถวของตารางเดียวกันที่ Transaction หนึ่งจะล็อก ต้องล็อกใน Query เดียวที่เรียงตาม `id` ห้ามล็อกบางแถวก่อนแล้วมาล็อกเพิ่มทีหลัง
* **เคสอื่นที่ได้รับผลกระทบ (ข้อ 5.3):** `recompute()` ของเคสอื่นทำหลัง Commit ใน Transaction ของตัวเอง จึงเริ่มล็อกจาก Offer ของเคสนั้นตามลำดับปกติ ไม่ถือ Lock ของเคสแรกค้างไว้
* **Safety ไม่ผ่าน:** ตั้ง Offer ของผู้ตอบเป็น `CANCELLED` ใน Transaction ของการตอบรับ ซึ่งถือ Lock ของแถวนั้นอยู่แล้ว
* **เลือกคนของ Wave:** `contact_candidate` ล็อกแถว `STAFF` ของทั้ง Plan เรียงตาม `id` (ข้อ 6.7) ถ้าถูกเรียกต่อจากการตอบ Offer, การอนุมัติ หรือ Job แถวพวกนี้ถูกล็อกไว้แล้วตั้งแต่ต้น Transaction จึงไม่มีการรอเพิ่ม
* **ปิด Window (ข้อ 3):** ล็อก `SHIFT` ก่อน แล้วจึงแก้ Roster ตรงลำดับเดิม
* **จัดคนเองจาก `MANUAL_HANDOFF`:** สร้าง Roster และอาจยกเลิก Offer ของคนที่ถูกเลือกในเคสอื่น จึงใช้ลำดับเดียวกับการตัดสินอนุมัติ: `SHIFT` → Offer ที่ยังไม่จบของคนนั้นในเคสอื่น → เคส → แถว `STAFF` ของคนที่ถูกเลือก ซึ่งต้องล็อกแม้เขาไม่อยู่ใน Plan แล้วตรวจ Hard Rules ซ้ำหลังได้ Lock (ข้อ 6.12) เส้นทางนี้ไม่ล็อก `WARD`
* **คำขออนุมัติหมดเวลา (Job):** ยกเลิก Offer และอาจทำให้เคสส่ง Wave ถัดไป จึงใช้ลำดับของการตัดสินอนุมัติ โดยเริ่มที่ `SHIFT` ไม่ล็อก `WARD`
* **Solver:** `create_plan()` ยังล็อก `STAFF` ของทั้ง Pool ก่อนตรวจกติกาและถือจน Commit เพดานเวลาของ Solver จำกัดเวลาค้น ไม่ได้จำกัดเวลาที่ถือ Lock นี้ (ข้อ 6.14)
* **ตัดสินอนุมัติในรอบ 4 (PR A และ S):** `with_for_update(key_share=True)` โดยไม่ตั้ง `read=True` สร้าง SQL `FOR NO KEY UPDATE` บน PostgreSQL (ไม่ใช่ `FOR KEY SHARE`) Lock นี้ขัดกับ `NO KEY UPDATE` อีกตัว จึงใช้เรียงการตัดสินของหอเดียวกันได้ ทั้ง `decide()` ที่คนกดและ Job อนุมัติเองล็อกแถว `WARD` ของหอปลายทางก่อนเสมอ แล้วจึงตามลำดับเดิมของการตัดสินอนุมัติ ลำดับเต็มคือ `WARD` → `SHIFT` → `APPROVAL_REQUEST` → Offer → เคส → `STAFF` เพื่อให้การนับคิวของ Auto-Approval กับการตัดสินของหอเดียวกันทำทีละรายการ (ข้อ 6.22) เส้นทางอื่นที่ล็อก `SHIFT` (รับ Event และปิด Merge Window, จัดคนเองและปิดเคสใน `MANUAL_HANDOFF`, Job ตั้งคำขอหมดเวลา) ไม่ล็อก `WARD` จึงไม่มีทางไหนล็อก `WARD` หลัง `SHIFT`
* **ย้ายคนจริง (C2 ทำแล้ว):** ล็อก `SHIFT` ของเวรต้นทางและเวรปลายทางใน Query เดียวเรียงตาม `id` (หลัง `WARD`) แล้วจึงตามลำดับเดิม `transfer_service.execute()` ตรวจเวรต้นทางและกฎที่ขึ้นกับเวลาซ้ำหลังได้ Lock ครบ ใน Transaction เดียวกับการแก้แถวต้นทางและสร้างแถวปลายทาง (ข้อ 6.19) ไม่มีการล็อกเพิ่มจากลำดับของ PR S การย้ายกลางเวรของ C3 (แถวต้นทางยังอยู่และจบที่เวลาย้าย) ใช้ลำดับ Lock เดียวกัน
* **N2 ทำแล้ว — check-in, ตรวจ `NO_SHOW` และมาสาย (ข้อ 6.24):** ทุกทางล็อกตามลำดับเดียวกัน และเหมือนการปิด Window ที่ล็อก `SHIFT` ก่อนแก้ Roster ฝั่งที่ได้ล็อกทีหลังอ่านข้อมูลใหม่หลังล็อก Job ขั้นที่ 1 ล็อก `SHIFT` ของแต่ละเวรแล้วล็อกแถว `ROSTER_ASSIGNMENT` ที่เป็นผู้สมัครใน Query เดียวเรียงตาม `id` ขั้นที่ 2 ล็อก `SHIFT` แล้วล็อกแถวที่ Event ระบุใน `payload.roster_assignment_id` ส่วน check-in สายหลังขั้นที่ 2 (`attendance_service._late_check_in()`) ล็อกตามลำดับนี้: `SHIFT` → หาแถว `ATTENDANCE` เดิม → แถว `ROSTER_ASSIGNMENT` ของคนนั้น (`ASSIGNED` รวมแถวที่ `NO_SHOW` ยกเลิก Query เดียวเรียงตาม `id`) → `APPROVAL_REQUEST` ที่ยังรออยู่ของเคส → `CANDIDATE_OUTREACH` ที่ยังไม่จบ (`SENT`, `ACCEPTED`) → เคส → `STAFF` ของ Plan ทั้งหมดรวมคนที่มาสาย (Query เดียวผ่าน `hard_rule_service.lock_staff`) → แถว `STAFF_UNAVAILABILITY` (ตรงกับ `update_end_at()` ที่ล็อก `STAFF` ก่อนช่วงที่หายไป) ถ้าเวรไม่มีเคสที่รออยู่ ล็อกแค่ `STAFF` ของคนที่มาสายแล้วตามด้วยแถว `STAFF_UNAVAILABILITY` **Retry:** หลังล็อกครบ ถ้ารหัส Offer ของเคส รหัสคำขอที่รออยู่ หรือเคสที่ได้เครดิตเปลี่ยนไป (มี Offer หรือคำขอใหม่ Commit ระหว่างรอ Lock) ให้ `db.rollback()` แล้วเริ่ม check-in ใหม่ทั้งหมด ไม่เขียนอะไรก่อน สูงสุด `CHECK_IN_LOCK_TRIES = 5` ครั้ง ถ้ายังเปลี่ยนอยู่ `check_in()` โยน `CheckInLockRetryError` และทั้งสอง Route ตอบ `409` (เหมือนทางเลือก Offer ของ PR 4)
* **H1 ทำแล้ว — สร้างเวรพร้อม Handover (ข้อ 6.25):** ฟังก์ชันกลางเขียน Handover ใน Transaction และหลัง Lock ของทางที่เรียกมันเสมอ ไม่ล็อกแถวเพิ่ม การกันซ้ำใช้ Unique ของ `roster_assignment_id`
* **H2 ทำแล้ว — ส่ง Handover:** Claim/Finish ล็อก `SHIFT` → `ROSTER_ASSIGNMENT` → `STRUCTURED_HANDOVER` ไม่ล็อกเคสหรือ Staff ปล่อย Transaction ก่อน LINE HTTP ตรวจความเป็นปัจจุบันอีกครั้งตอน Finish ส่งล้มไม่เดิน Workflow ของเคส
* ลำดับ Lock ในข้อนี้มี Test สอง Connection พิสูจน์ทุกเส้นทางที่ลงมือแล้ว (ใน `backend/tests/integration/`):
  * สองคนตอบรับเคสเดียวกันพร้อมกัน: `test_outreach_response.py::test_two_staff_accept_same_case_concurrently_one_is_reserve`
  * คนเดียวตอบรับสองเคสพร้อมกัน: `test_outreach_response.py::test_simultaneous_accepts_only_one_commitment`
  * ตอบรับกับอนุมัติคนสุดท้ายพร้อมกัน: `test_approval_per_candidate.py::test_accept_racing_last_approval_never_overassigns_or_deadlocks`
  * สองเคสที่ใช้ผู้สมัครชุดเดียวกันตอบ Offer แล้วส่ง Wave ถัดไปพร้อมกัน: `test_outreach_response.py::test_rejecting_shared_pool_cases_concurrently_sends_next_waves`
  * Offer หมดเวลาแข่งกับ Job อีกตัวหรือกับการตอบ: `test_offer_timeout.py::test_two_jobs_or_response_racing_expiry_never_duplicate_outcomes`
  * คำขออนุมัติหมดเวลาแข่งกับการกดตัดสิน (รอบ 2 PR T): `test_approval_timeout.py::test_two_connections_expire_once_and_never_assign_after_deadline`
  * การจัดคนเองแข่งกับการอนุมัติคนเดียวกัน และแข่งกับการเปิดเคสใหม่ของเวร (รอบ 2 PR H): `test_manual_handoff.py::test_manual_assignment_racing_an_approval_never_gives_two_shifts`, `test_manual_handoff.py::test_manual_assignment_racing_a_successor_case_ends_in_one_consistent_state`
  * การอนุมัติสองหอ/ฝั่งเดียวกันแข่งกัน และฝั่งสุดท้ายแข่งกับ Timeout: `test_approval_two_wards.py::test_two_connections_never_execute_before_both_sides_or_twice`, `test_approval_two_wards.py::test_two_connections_final_decision_racing_timeout_keeps_first_ward_history`
  * Auto-Approval Job/Job และ Job/คนกด: `test_auto_approval.py::test_competing_connections_serialize_the_ward_snapshot`
  * Solver ของ PR B ถือ Lock เดิมของ `create_plan()` ไม่มีเส้นทาง Lock ใหม่ จึงไม่มี Test สอง Connection ของตัวเอง

### 6.12 เส้นออกจาก `MANUAL_HANDOFF`

กติกาของข้อนี้มีโค้ดครบแล้วใน PR H: ตาราง `manual_assignment`, ตัวอ่านกลาง, `orchestrator.leave_handoff()`, ตัวยกเลิก Offer ที่ใช้ร่วม (`services/offer_conflict_service.py`), `services/handoff_service.py`, Route ในข้อ 9.4 และหน้า `/handoff` (`frontend/src/app/handoff/page.tsx`) Test อยู่ที่ `tests/integration/test_manual_handoff.py` และ `frontend/tests/unit/app/handoff.test.ts`

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
* Signature: `orchestrator.leave_handoff(db: Session, case_id: int, next_status: CaseStatus) -> StaffingCase` ล็อกเคส ตรวจว่าอยู่ `MANUAL_HANDOFF` และปลายทางเป็น `RESOLVED` หรือ `UNRESOLVED` เท่านั้น ไม่อย่างนั้นโยน `InvalidTransitionError` โดยไม่แตะเคส เขียน `CASE_STATUS_CHANGED` และ**ไม่ Commit** ไม่เดินรอบของ Handler ผู้เรียก Commit เอง ถ้าพังให้ Rollback เคสไม่เป็น `FAILED` เพราะ D11 ใช้กับรอบของ Workflow
* T8 เขียน Audit `CASE_RESOLVED` (`assignment_ids` คือแถว Roster ที่ปิด Gap ทั้งจากการอนุมัติและจากการจัดเอง, `cancelled_outreach_ids` ว่าง) ก่อนเปลี่ยนสถานะ เหมือนเคสที่ปิดผ่าน `EXECUTING`
* ผู้เรียกทางเข้านี้มีสามจุด: Route จัดคนเอง (T8 เมื่อ Gap ถูกปิด), Route ปิดเคสโดยไม่มีคนแทน (T9) และขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด (T9 โดยระบบ) ทุกจุดเรียกใน Transaction เดียวกับงานของตัวเอง ไม่มี Handler และไม่มีจุดอื่นเดินสองเส้นนี้
* เส้นทางจัดคนเองล็อกแถว `STAFF` ของคนที่ถูกเลือกแม้เขาไม่อยู่ใน Plan ตรวจซ้ำหลังได้ Lock และใช้ลำดับ Lock ของข้อ 6.11

### 6.13 Timeout ของการอนุมัติ

PR T ทำแล้ว: `approval_timeout_service.expire_due_approvals()` ใช้ Lock ของการตัดสินอนุมัติ ตรวจซ้ำหลังรอ Lock และ Commit ทีละคำขอ ผล timeout และ Audit อยู่นอก D11 จึงคงอยู่เมื่อ workflow ล้มเหลว รอบใหม่ใน D11 ถูก rollback และเคส FAILED; ข้อผิดพลาดก่อนบันทึก timeout ถูก rollback และลองใหม่ tick ถัดไป ไม่ขวางคำขออื่น Test อยู่ `tests/integration/test_approval_timeout.py` และ `test_approval_timeout_migration.py`

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

Expired requests disappear from `GET /approvals` immediately (`expires_at > now`), even before the job tick. Until the job records the timeout, their accepted offers still reserve coverage and pause conflicting offers. This short interval is intentional: releasing the commitment, writing `APPROVAL_TIMEOUT`, promoting reserves and enabling the retry happen together in the locked job transaction. Reads and decisions do not perform those writes.

**ผู้สมัครกลับไปต่อท้ายคิวได้หนึ่งครั้ง (R2-Q29)**

* หมดเวลาครั้งแรก คำขอนั้นจบแบบไม่อนุมัติและเคสไปหาคนถัดไป แต่ผู้สมัครไม่หลุดถาวร หมดเวลาครั้งที่สองจึงหลุดถาวรในเคสนั้น
* เขาถูกติดต่อใหม่เมื่อการเลือก Wave ครั้งนั้นไม่เหลือคนที่ไม่เคยถูกติดต่อและส่ง Offer ได้ คนที่ถูกข้ามเพราะ Hard Rules หรือเพดาน Offer ไม่ทำให้คิวนี้รอ (R2-Q48) PR T แก้ข้อ 6.6 ขั้นที่ 4 และเงื่อนไขของ T5 แล้ว
* รอบที่สองคือ Offer ใบใหม่ ผ่านการตรวจ Hard Rules และเพดาน Offer แบบเดียวกับใบแรกขณะถือ Lock ตอบรับแล้วเข้า Safety ใหม่ และได้คำขออนุมัติใหม่พร้อมเส้นตายใหม่
* ถึงคิวแล้วแต่ติดเพดานหรือไม่ผ่าน Hard Rules ยังไม่นับว่าใช้สิทธิ์ สิทธิ์หมดเมื่อ Offer ใบที่สองถูกส่งจริง (R2-Q47)

**หนึ่งรอบคือหนึ่ง Offer (R2-Q41)**

* โค้ดรอบ 1 ผูก Offer, ผล Safety และคำขออนุมัติด้วย `candidate_item_id` อย่างเดียว ซึ่งถูกเมื่อหนึ่งคนมีหนึ่งรอบต่อเคส PR T เพิ่มคอลัมน์ `outreach_id` ใน `SAFETY_VALIDATION` และ `APPROVAL_REQUEST` และให้ตัวอ่านจับคู่ด้วย Offer
* ตัวอ่านที่ต้องแก้มีอย่างน้อยสี่จุด: `case_facts_service._waiting_acceptances()`, `outreach_service.promote_reserves()`, `case_facts_service.accepted_offer_for_request()` และ `case_facts_service._has_uncontacted_candidate()` PR T แก้ทั้งตัวอ่านและสถานะ reserve/is_assigned ในรายการ Offer ให้จับคู่ attempt โดยตรง
* สิทธิ์รอบที่สองคำนวณตอนอ่าน ไม่เก็บตัวนับ: Item มีสิทธิ์เมื่อมี Offer ของเคสนี้แถวเดียว และคำขอของ Offer นั้นมี `is_timed_out = true` Item หนึ่งมี Offer ของเคสได้ไม่เกินสองแถว
* สถานะรายคนอ่านจาก Offer ที่ `id` มากสุดของ Item แถวของรอบแรกเป็นประวัติ ต้องไม่ทำให้เคสหยุดรอ ไม่นับว่าปิด Gap ไม่นับว่าถูกปฏิเสธ และไม่กันรอบที่สอง

**Migration**

* เติมเส้นตายให้**ทุกแถว**ที่มีอยู่ด้วย `requested_at` + ค่าใน Policy คอลัมน์เป็น NOT NULL (R2-Q28) เส้นตายของแถวที่ไม่ได้รออยู่จริงเป็นแค่ประวัติ
* เติม `outreach_id` ให้แถวเดิมจาก Offer ของเคสกับ Item เดียวกัน ตาราง `candidate_outreach` ไม่มี Unique Constraint Migration จึงตรวจก่อน ถ้าคู่ไหนมี Offer มากกว่าหนึ่งแถวให้หยุดพร้อมข้อความบอกสาเหตุ (R2-Q52)
* รันได้กับฐานข้อมูลที่มีข้อมูลอยู่โดยไม่ต้อง Reset คำขอที่ค้างมานานกว่า 900 วินาทีจะหมดเวลาในรอบแรกที่ Job ทำงานหลัง Migration

**เหตุที่ยกเลิกในรายการ Offer:** `outreach_service._cancellation_reasons()` คืน `APPROVAL_TIMEOUT` สำหรับ Offer ที่ถูกยกเลิกเพราะคำขอหมดเวลา ไม่ใช่ค่ากลาง `CANCELLED`

### 6.14 Solver แบบ OR-Tools

ข้อนี้ทำแล้วในรอบ 2 PR B: `app/optimization/solver.py` เลือกกลุ่มของ Wave แรกด้วยโมเดล CP-SAT ของ OR-Tools PR A (#51) ตรึงผลของ Solver รอบ 1 ไว้เป็นตัวเทียบ และผลที่บันทึกไว้ทั้ง 229 โจทย์ยังตรงทุกโจทย์ด้วยสถานะ `OPTIMAL` การออกแบบข้างในของโมเดลอยู่ร่างรอบ 2 ข้อ 4.7 เกณฑ์เสร็จอยู่ข้อ 4.5 และผลวัดเวลาของโมเดลจริงอยู่ข้อ 4.8

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
* `SOLVER_VERSION` เปลี่ยนจาก `"weighted-v1"` เป็น `"cp-sat-v1"`
* รอบ 4 PR T4 เพิ่ม `solve(..., intervals=None)` (keyword), `SolverCandidate.source_shift_id` และ `SolverResult.partial` (ค่าเริ่มต้น `false`) ความหมายอยู่ข้อ 6.20 ค่าเริ่มต้นให้โมเดลเดิม

**สถานะและผลต่อเคส (R2-Q4, R2-Q43)**

| `solver_status` | ความหมาย | เคสเป็น |
|---|---|---|
| `OPTIMAL` | พิสูจน์ครบทั้งคะแนน จำนวนคน และชุด `staff_id` | `OUTREACH` ตามปกติ |
| `FEASIBLE` | มีแผนที่ผ่านข้อบังคับ แต่หมดเวลาก่อนพิสูจน์ครบ ผลอาจไม่ซ้ำเดิมและอาจต่างจากรอบ 1 | `OUTREACH` ตามปกติ บันทึกใน Audit `SOLVER_EXECUTED` อย่างเดียว (R2-Q32) |
| `INFEASIBLE` | ไม่มีผู้สมัครผ่าน Hard Rules เลย `solve()` คืนค่านี้โดยไม่สร้างโมเดล เหมือนรอบ 1 รอบ 4 PR T4 เพิ่มกรณีแผนบางส่วนที่กลุ่มดีที่สุดไม่ครอบอะไรเลย (ข้อ 6.20) | `MANUAL_HANDOFF` ด้วยเหตุผล `NO_FEASIBLE_PLAN` (T6) |
| `UNKNOWN` | หมดเวลาโดยยังไม่มีแผนเลย เป็นผลที่เกิดได้ตามปกติ ไม่ใช่ระบบทำงานผิด Handler ไม่โยน Exception และแถว Plan ถูกเก็บ | `MANUAL_HANDOFF` ด้วยเหตุผล `SOLVER_TIMEOUT` (T6) |
| `MODEL_INVALID` | โมเดลผิดรูป หรือ OR-Tools รายงาน `INFEASIBLE` ทั้งที่มีผู้สมัคร ซึ่งเกิดไม่ได้ถ้าโมเดลถูก เพราะการเลือกทุกคนผ่านข้อบังคับเสมอ (รอบ 4 PR T4: ใช้เฉพาะเมื่อโมเดลไม่มีเงื่อนไขเลือกพร้อมกันไม่ได้ ถ้ามี `INFEASIBLE` ขั้นแรกเข้าแผนบางส่วนของข้อ 6.20) Handler โยน Exception | `FAILED` ผ่าน D11 |

* Audit `SOLVER_EXECUTED` ของ Golden Path เปลี่ยนจาก `FEASIBLE` เป็น `OPTIMAL` ไฟล์ Test ที่ต้องแก้ใน PR B อยู่ร่างรอบ 2 ข้อ 5
* แผนที่เก็บไว้จากขั้นก่อนหน้าคืนเป็น `FEASIBLE` ได้เฉพาะเมื่อขั้นหลังหมดเวลา ไม่ใช้กลบข้อผิดพลาดของโมเดล

**เพดานเวลาและการตั้งค่า**

* 3 วินาทีเป็นงบรวมของการเรียก `solve()` หนึ่งครั้ง ทุกรอบของการ Solve ใช้งบก้อนเดียวกัน (R2-Q5, R2-Q44) ผลวัดของโมเดลจริง (ร่างรอบ 2 ข้อ 4.8) ยืนยันค่านี้: ผู้สมัคร 300 คนใช้เวลาค้นไม่เกิน 0.25 วินาทีบนเครื่อง CI เหลือที่ว่างราว 16 เท่า แก้ค่านี้ได้โดยไม่แก้โค้ด
* เพดานนี้จำกัดเวลาค้นอย่างเดียว ไม่ได้จำกัดเวลาที่ถือ Lock ของ `STAFF` ทั้ง Pool (ข้อ 6.11) ซึ่งรวมการโหลดข้อมูล การสร้างโมเดล และการเขียน Plan
* ใช้ `num_workers = 1` และ `random_seed = 0` เป็นข้อตกลงกลาง ไม่ใช่ทางเลือกของผู้ทำ (R2-Q33)
* PR B เพิ่ม Dependency `ortools` หลัง merge ทุกคนต้องสร้าง container ของ Backend ใหม่ (R2-Q11)

**โค้ดและ Test ของ PR B**

* การค้นแบบตัดกิ่งของรอบ 1 ย้ายไปอยู่ที่ `tests/unit/optimization/round1_search.py` ใช้เป็นตัวเทียบใน Test เท่านั้น โค้ดใน `app/` ไม่ import
* จุดสลับ Solver ใน Test มีสองชั้น (R2-Q49): `optimization_service.solve` สำหรับ Test ว่าสถานะแต่ละค่าพาเคสไปสถานะไหน และ `solver._run_cp_sat` ซึ่งเป็นฟังก์ชันเดียวที่เรียก OR-Tools สำหรับ Test ของสามขั้นและงบเวลา
* ขั้นที่ 3 ตัดสิน `staff_id` เป็นกลุ่มละ 40 คนตามลำดับ `staff_id` กลุ่มละหนึ่งรอบ (Maximize `Σ x × 2^(ตำแหน่งจากท้ายกลุ่ม)`) ได้คำตอบเดียวกับการตัดสินทีละคน และข้ามกลุ่มที่เหลือเมื่อคนที่ตรึงเป็น 1 ครบจำนวนแล้ว หรือคนที่เหลือเท่ากับจำนวนที่ยังขาดพอดี ผู้สมัคร 300 คนใช้ราว 10 รอบแทนราว 280 รอบ
* ผลรวมของคะแนนจำนวนเต็มหลังคูณสเกลเกิน 2^60: `solve()` โยน `SolverScalingOverflowError` เคสเป็น `FAILED` ผ่าน D11 ส่วน `MODEL_INVALID`: `create_plan()` โยน `SolverModelInvalidError` ก่อนเขียนแถวใด
* วัดเวลาซ้ำได้ด้วย `SOLVER_TIMING=1 pytest tests/perf -s -q` (ชุด Test ปกติข้ามไฟล์นี้) และ Workflow `Solver timing` บน GitHub ซึ่งรันเมื่อ PR แตะไฟล์ของ Solver หรือสั่งรันเอง ไม่ใช่ Check ที่บังคับ

### 6.15 คำอธิบายอันดับ

คำอธิบายอันดับอธิบายผลที่ Solver ให้จริง ไม่คำนวณอันดับใหม่ (R3-Q2 ถึง R3-Q5, R3-Q14 ถึง R3-Q16)

**สิ่งที่ `create_plan()` เก็บเพิ่มใน `input_snapshot` (PR E)** `input_snapshot` เป็น `JSONB` การเพิ่ม key จึงไม่มี Migration

* `weights`: ค่าน้ำหนักหกตัวของ `SoftWeights` ที่ใช้วางแผนจริง แต่ละตัวเป็นข้อความ `"เศษ/ส่วน"` จาก `Fraction` และ `source_order` เป็นรายการชื่อแหล่งที่มาตามลำดับ อยู่ใน `weights` เอง รูปเป็นดังนี้ (`source_order` เป็นค่าของ `CandidateSource` ตามที่ Seed ไว้)

```json
"weights": {"candidate_count": "1000/1", "consecutive_shift": "5/1", "workload_imbalance": "1/1",
            "projected_overtime": "2/1", "roster_change": "300/1", "candidate_source": "200/1",
            "source_order": ["SAME_WARD", "..."]}
```

* ข้อความ `"เศษ/ส่วน"` เป็นรูปนี้เสมอ แม้เป็นจำนวนเต็ม (เช่น `"1005/1"`, `"1/3"`) เพื่อให้มีรูปเดียว ตัวอ่านรับเฉพาะข้อความ ไม่รับ `int` หรือ `float`
* ในแต่ละ `candidates[]`: `hours_this_week_exact`, `overtime_hours_exact` และ `penalty_exact` เป็นข้อความ `"เศษ/ส่วน"` จาก `Fraction`
* ช่องเดิม (`hours_this_week`, `overtime_hours`, `penalty`) คงไว้ตามเดิม เพราะ `display_number()` เปลี่ยนค่าที่ไม่ใช่จำนวนเต็มเป็น `float` จึงใช้แสดงผลได้อย่างเดียว

**การคำนวณตอนอ่าน**

* คำนวณรายพจน์ด้วยสูตรของ `penalties.candidate_penalty()` จาก `weights` และช่อง `_exact` ใน Snapshot เท่านั้น ห้ามอ่านค่าน้ำหนักจาก Policy เพราะ Policy ถูกแก้ทับในแถวเดิมได้ (เช่น Seed `ignore_workload()`) และห้ามใช้ช่องที่เป็น `float`
* ผลรวมรายพจน์ต้องเท่ากับ `Fraction(penalty_exact)` พอดี ไม่เท่าคือบั๊ก ไม่ปัดให้ตรง การเทียบทำใน Backend เท่านั้น Plan ที่มี `weights` ต้องมีช่อง `_exact` และ `first_wave` ครบทุกรายการ ถ้าไม่ครบ ไม่เท่า หรือผู้สมัครของเคสไม่มีรายการใน Snapshot ถือว่าเป็นบั๊ก (`ScoreMismatchError`) ห้ามถือเป็น Plan เก่า ตัวอ่านคืน `score = null` เฉพาะผู้สมัครคนนั้น บันทึก Log ระดับ Error แล้วหน้าเคสที่เหลือยังตอบ `200` ไม่ปัดให้ตรง และถ้าอ่าน `weights` ไม่ได้ ผู้สมัครทุกคนได้ `score = null` พร้อม Log เช่นกัน
* Plan ที่ไม่มีช่องใหม่ (สร้างก่อน PR E) ได้ `score = null` และหน้าแสดงอันดับตามเดิมโดยไม่มีคะแนน

**รูปใน API** ช่อง `score` ในแต่ละ `candidates[]` ของ `GET /cases/{id}` (ข้อ 9.5)

* `score = {total, terms: [{name, value, weight, points}], first_wave}` หรือ `null` `terms` เรียงตามสูตรของ `candidate_penalty()` เสมอ: `candidate_count`, `consecutive_shift`, `workload_imbalance`, `projected_overtime`, `candidate_source` ไม่เรียงตาม `points` (การเรียงเพื่อแสดงเป็นหน้าที่ของหน้าเว็บ) `first_wave` มาจากรายการใน Snapshot
* `name` คือชื่อค่าน้ำหนักใน `penalties.py`: `candidate_count`, `consecutive_shift`, `workload_imbalance`, `projected_overtime`, `candidate_source` ไม่มี `roster_change` เพราะเป็น 0 ในรอบนี้และไม่ใช่ของรายคน
* `points = weight × value` ทุกพจน์ และ `value` ของแต่ละพจน์คือตัวคูณใน `candidate_penalty()`: `candidate_count` มี `value = 1` เสมอ เพราะค่าน้ำหนักถูกบวกตรง ๆ หนึ่งครั้งต่อคน, `consecutive_shift` คือ `projected_consecutive_shifts`, `workload_imbalance` คือ `hours_this_week_exact`, `projected_overtime` คือ `overtime_hours_exact` และ `candidate_source` คือ `source_priority(source, source_order)` ซึ่งเป็นตำแหน่งของแหล่งที่มาใน `source_order` เริ่มที่ 0 (แหล่งที่ใกล้ที่สุดได้ 0) ไม่ใช่ค่าดิบ
* `total` ใช้ค่าเดียวกับ `penalty_exact` ตัวเลขใน API เป็นค่าสำหรับแสดงผล
* ไม่มีช่อง `reason_codes` เหตุผลแบบตายตัวคือข้อความคงที่ที่หน้าเว็บเขียนไว้หนึ่งข้อความต่อ `name` และหนึ่งข้อความตาม `first_wave` (กลุ่มแรก หรือตัวสำรอง) เรียงพจน์จาก `points` มากไปน้อย

**หน้าที่แสดง (PR E2)** หน้า `cases/[id]` อย่างเดียว (R3-Q5)

* `score = null` มีสองเหตุ: Plan ที่สร้างก่อน PR E และผู้สมัครที่ตัวเลขใน Snapshot ไม่ครบหรือไม่ลงกัน (มี Log ระดับ Error) API ไม่แยกสองเหตุนี้ หน้าต้องรับ `null` ได้ทั้งสองแบบโดยแสดงอันดับตามเดิมไม่มีคะแนน และไม่เดาเหตุผลหรือคำนวณคะแนนเอง
* หน้าแสดงคอลัมน์ Score (ค่า `total`) ในตารางผู้สมัคร และตารางรายพจน์ของผู้สมัครที่มีคะแนน เรียงพจน์จาก `points` มากไปน้อย พจน์ที่ `points` เท่ากันคงลำดับของ API ตัวเลขปัดแสดงไม่เกินทศนิยมสองตำแหน่งเพื่อแสดงผลอย่างเดียว ผลรวมบนหน้าจึงอาจไม่เท่า `total` พอดี Plan ที่ไม่มีคะแนนเลยไม่แสดงส่วนคำอธิบาย ข้อความบนหน้าบอกว่าคะแนนใช้เลือกกลุ่ม Wave แรก (เมื่อ `partial_plan` เป็นจริง ข้อความบอกว่าการครอบมาก่อน คะแนนตัดสินเฉพาะกลุ่มที่ครอบเท่ากัน) ส่วนอันดับในแต่ละกลุ่มเรียงตาม `ranking_key` (แหล่งที่มา, ชั่วโมงในสัปดาห์, เวรติดกัน, OT, Staff ID) คะแนนจึงอาจไม่เรียงตามอันดับ หน้าไม่คำนวณ `ranking_key` เอง

**ประโยคจาก LLM (PR X ทำแล้ว)** รายละเอียดเต็มอยู่ในคำตอบ R3-Q15

* Job สร้างประโยคครั้งเดียวต่อ Plan แล้วเก็บลงตาราง `RANK_EXPLANATION` (Migration `e1a4c7f2b9d6`) หน้าแสดงตัวเลขทันทีและแสดงประโยคเมื่อพร้อม การเปิดหน้าซ้ำหรือ Polling ไม่เรียก LLM (`GET /cases/{id}` อ่าน DB อย่างเดียว)
* เรียกผ่านตัวกลางเดียว `llm_service` ซึ่งมีตัวเชื่อม `bedrock` (Amazon Bedrock Converse แบบ On-demand) และ `fake` เลือกตัวเชื่อมจาก `LLM_PROVIDER` อย่างเดียว LLM ใช้ไม่ได้ให้แสดงตัวเลขและเหตุผลแบบตายตัว พร้อมข้อความว่า "คำอธิบายยังไม่พร้อม" ห้ามสลับไป `fake` เงียบ ๆ
* **ตารางและค่าคงที่** `RANK_EXPLANATION` หนึ่งแถวต่อ (`plan_id`, `prompt_version`) (UNIQUE) สถานะ `PENDING`, `READY`, `FAILED`, `SKIPPED` เก็บ `input_payload`/`input_hash`, `text`, `provider`, `model_id`, `attempts`, `claim`, `lease_until`, `failure_reason` (ค่าของ `LlmCallStatus` หรือ `INVALID_INPUT`, `NO_CANDIDATES`, `ATTEMPTS_EXHAUSTED` และของรอบ 6 PR B1: `QUOTA_EXHAUSTED`, `INPUT_TOO_LARGE` ไม่เก็บข้อความ Error ของ SDK) ส่วน `LLM_CALL_LOG` หนึ่งแถวต่อ Attempt (UNIQUE `explanation_id`, `attempt`) `PROMPT_VERSION = "rank-explanation-v2"` (T4 เปลี่ยนจาก `v1`) ตัวเลขใน Prompt ทุกตัวมาจาก Backend
* **เข้าคิว** `optimize.handle()` เรียก `explanation_service.enqueue()` หลังเขียน `SOLVER_EXECUTED` เมื่อ `LLM_ENABLED` เปิดและ Plan มีผู้สมัคร เพิ่มแค่แถว `PENDING` ใน Transaction เดียวกับ Plan (ใน Savepoint ของ D11 จึง rollback พร้อม Plan) ไม่สร้าง Payload และไม่เรียก Network ใน Workflow ถ้า `LLM_ENABLED=false` ไม่มีแถวและ API คืน `explanation = null` **[รอบ 6 · PR E1] เปลี่ยนเป็นผู้ใช้กดขอ (ข้อ 6.27):** `optimize.handle()` เลิกเรียก `explanation_service.enqueue()` แถว `PENDING` เกิดเมื่อผู้ใช้กด "หน้าสรุปด้วย AI" เท่านั้น ข้อความข้างบนที่ว่าเข้าคิวเองยังเป็นพฤติกรรมของโค้ดจนกว่า E1 merge
* **สร้างเฉพาะตอน Job tick** `POST /internal/merge-windows/close-due` ตั้ง `BackgroundTasks` ให้ `explanation_service.run_pending_in_new_session()` เปิด Session ใหม่หลังตอบ Ticker จึงไม่รอ LLM ประโยคจึงช้าได้ไม่เกินราว `JOB_INTERVAL_SECONDS` (ค่าเริ่มต้น 30 วินาที) บวกเวลาเรียก ไม่เพิ่มใน `job_service.run_due_work()` และ `POST /demo/clock/advance` ไม่เรียก LLM Sweep หนึ่งรอบทำไม่เกิน 3 แถว (`MAX_PER_SWEEP`) Sweep ซ้อนกันปลอดภัยด้วย `FOR UPDATE SKIP LOCKED` กับ Lease
* **Claim/Lease/Attempt** Claim ตั้ง `claim` (UUID) กับ `lease_until = clock_timestamp() + max(60, timeout × (retries+1) + 30)` วินาที โดยเวลาของ Lease และเงื่อนไข Claim อ่านจากนาฬิกาของฐานข้อมูล ไม่ใช่ `clock.now()` (ข้อยกเว้นของ D10) เพราะ Lease วัดเวลาจริงของการเรียกเครือข่าย ถ้าใช้ Demo Clock การเลื่อน Clock ระหว่างเรียกจะทำให้ Sweep ถัดไปเรียกซ้ำใน Plan เดียว และหลังรีสตาร์ต Backend แถวจะค้างเป็นชั่วโมง แล้ว Commit ก่อนเรียก ระหว่างเรียกไม่มี Transaction หรือ Lock ค้าง ก่อนเรียกทุกครั้งเพิ่ม `attempts` และเขียนแถว `LLM_CALL_LOG` สถานะ `IN_FLIGHT` แล้ว Commit (นับ Attempt ถาวร) จึงเรียกได้ไม่เกิน `1 + LLM_MAX_RETRIES` ครั้งต่อแถว แม้เครื่องล่มกลางการเรียก ลองซ้ำเฉพาะ `TIMEOUT`, `THROTTLED`, `SERVICE_ERROR` ส่วน `CONFIG_ERROR`, `TRUNCATED`, `INVALID_OUTPUT` ไม่ลองซ้ำและแถวเป็น `FAILED` ตัวเชื่อมที่ Raise ถูกบันทึกเป็น `SERVICE_ERROR` พร้อมชื่อชนิด Exception แถว `IN_FLIGHT` ที่ค้างหลังเครื่องล่มคงไว้ตามเดิม (= ไม่ทราบ Token) เมื่อ Lease หมดและ `attempts` เต็มแล้ว Claim รอบถัดไปตั้ง `FAILED` (`ATTEMPTS_EXHAUSTED`) โดยไม่เรียก ถ้า Snapshot ไม่มี `weights`, ตัวเลขไม่ลงกัน (`ScoreMismatchError`) หรือไม่มีผู้สมัคร แถวเป็น `SKIPPED` โดยไม่เรียก ถ้า `LLM_ENABLED` เปิดแต่ `bedrock` ไม่มี `LLM_MODEL_ID`/`AWS_REGION` (`llm_ready` เป็นเท็จ) Sweep บันทึก Error โดยไม่แสดงค่า ไม่เรียก และแถวคง `PENDING`
* **Payload ที่ส่ง** อ่านจาก `input_snapshot` และ `objective_score` ของ Plan เท่านั้น: `targets` (รหัสกับจำนวน), `plan_penalty` (`value` กับคำอธิบายว่าใช้เลือกกลุ่ม Wave แรก เมื่อ `partial_plan` ของ Plan เป็นจริง (รอบ 4 PR T4) คำอธิบายเป็นว่าไม่มีกลุ่มใดครอบทุกเป้าหมาย Wave แรกคือกลุ่มที่เหลือคน-นาทีที่ไม่มีคนน้อยสุด และคะแนนใช้ตัดสินเฉพาะกลุ่มที่ครอบเท่ากัน), `ranking_key` (ลำดับ `candidate_source`, `hours_this_week`, `projected_consecutive_shifts`, `overtime_hours`, `staff_id` กับคำอธิบายว่าใช้เรียงใน Plan), `candidate_count` และ `candidates` สูงสุด 10 คนแรกตามอันดับ (`rank`, `first_wave`, `total`, `terms[{name, value, weight, points}]`, ค่า `ranking_key` ของคนนั้นโดยแหล่งที่มาเป็นตำแหน่งตัวเลข) ไม่มี `staff_id`, ชื่อ, LINE ID หรือข้อความอิสระ ผู้สมัครอ้างด้วย "อันดับ N" เท่านั้น `input_hash` คือ SHA-256 ของ JSON แบบ Canonical (`sort_keys`, ไม่มีช่องว่าง) ของ Payload ที่เก็บคู่กับ `input_payload` ผลของ LLM ต้องไม่ว่าง ไม่เกิน 2,000 ตัวอักษร และไม่มีอักขระควบคุม (Unicode `Cc` รวม C1) นอกจากขึ้นบรรทัดใหม่ และไม่มีตัวควบคุมทิศทางข้อความ (bidi) ไม่อย่างนั้นเป็น `INVALID_OUTPUT` รอบ 3 ตรวจรูปแบบเท่านั้น ไม่ตรวจว่าตัวเลขในประโยคตรง Payload (เป็นตัวชี้วัดของรอบ 6)
* **บันทึกการเรียก** `LLM_CALL_LOG` เก็บ Provider, Model, Region, `input_hash`, สถานะ, ชนิด Error, Token (NULL = ไม่ทราบ ไม่ใช่ 0), เวลา, ราคาต่อล้าน Token และค่าใช้จ่ายประมาณ (คำนวณเมื่อทราบทั้ง Token และราคาเท่านั้น `fake` ราคา 0 จึงเป็น 0) ไม่บันทึก Prompt, ข้อความตอบ หรือข้อความ Error ของ SDK ใน Log หรือ DB ค่า `LLM_*_PRICE_*` ที่ว่าง (Compose ส่งค่าที่ไม่ตั้งเป็น "") ถือเป็น `None`
* **API** `GET /cases/{id}` มีช่อง `explanation` (ข้อ 9.3, 9.5) ของ Plan ล่าสุด: `null`, `PENDING`, `READY` (`text`, `provider`, `model_id`) หรือ `UNAVAILABLE` (`FAILED` และ `SKIPPED`) ไม่คืน `failure_reason`, Token หรือ Payload หน้า `cases/[id]` แสดงประโยคใน `ScoreBreakdown` หลังข้อความนำ ก่อนรายผู้สมัคร และแสดง "คำอธิบายยังไม่พร้อม" ในกรณีอื่นทั้งหมด ถ้า `provider = fake` แสดงหมายเหตุว่าเป็นข้อความทดสอบ หน้า Poll ทุก 2 วินาที เคสที่ถึงสถานะสุดท้ายแต่ `explanation` ยังเป็น `PENDING` หน้ายัง Poll ต่อ และหยุดเมื่อเป็น `READY` หรือ `UNAVAILABLE` (ไม่มีแถว `explanation` หยุดทันทีเหมือนเดิม) ปุ่มเลือกผู้สมัครของเคสที่หยุดแล้วยังปิดอยู่ **[รอบ 6 · PR E1, E2]** ช่อง `explanation` เพิ่มสถานะ `NOT_REQUESTED` และ `QUOTA_EXHAUSTED` กับธง `can_request` และเหตุที่ขอไม่ได้ และเพิ่ม `POST /cases/{id}/explanation` (ข้อ 9.8)
* ค่าตั้งเริ่มต้น `LLM_ENABLED=false`, `LLM_PROVIDER=fake`, เพดาน 1,024 token ต่อคำตอบ (`LLM_MAX_OUTPUT_TOKENS`), Timeout 15 วินาทีต่อ Attempt (`LLM_REQUEST_TIMEOUT_SECONDS`), Retry ไม่เกินหนึ่งครั้ง (`LLM_MAX_RETRIES`) โมเดลยังไม่ล็อก ต้องทดสอบ 20 ถึง 30 เคสก่อนยืนยัน `bedrock` ใช้ boto3 ปิด Retry ของ SDK (`total_max_attempts = 1`) และ `temperature = 0`
* **ขอบเขตของรอบ 3 (มติทีม 2026-10-14):** PR X ทำตัวกลางและเส้นทางทดสอบด้วย `fake` ไม่เรียก Bedrock จริงที่ใดเลย (Test ของ `bedrock` ใช้ `botocore.stub.Stubber` แบบ Offline) ตัวเชื่อม `bedrock` ใช้ credential provider chain มาตรฐานของ boto3 ไม่ฝัง Access Key ในโค้ด และอ่าน Region กับชื่อโมเดลจาก env เพื่อเปลี่ยนไปใช้บริการจริงด้วยค่าตั้งอย่างเดียว
* **เตรียมตั้งแต่รอบ 3:** คน 2 ตรวจว่าเครดิตการแข่งขันครอบคลุม Bedrock และบัญชีมีสิทธิ์ใช้โมเดลที่เลือกใน Region ที่ตกลง ถ้าต้องขอสิทธิ์ให้ขอตอนนี้ เพื่อรู้ข้อจำกัดก่อนจบ PR X
* **รอบ 6:** เชื่อมต่อและทดสอบ Bedrock จริง ทดสอบ 20 ถึง 30 เคสเพื่อเลือกโมเดล ใช้ IAM Role ของเครื่อง Deploy ตั้งเพดานคำขอ 100 ครั้งต่อวันในแอปกับ Budget Alert 20 USD ต่อเดือนก่อนเรียกจริงครั้งแรก และผู้ใช้กดขอคำอธิบายเอง ดูข้อ 6.27 และ 6.28 Handoff ของ PR X อยู่ `docs/round3/pr-X-handoff.md`

### 6.16 LINE จริง

LINE จริงอยู่คู่กับหน้าจำลอง ทุกทางที่ตอบ Offer ต้องผ่าน `outreach_service.record_response()` ตัวเดียว กติกาเส้นตาย การพัก Offer และลำดับ Lock จึงยังมีที่เดียว (R3-Q6 ถึง R3-Q11, R3-Q17, R3-Q18, R3-Q22) จุดที่มีป้าย [ตรวจกับเอกสาร LINE] ตรวจแล้วตามลิงก์ในร่างรอบ 3 ข้อ 8

**โหมดและความลับ**

* สองโหมดสลับด้วย env: โหมดจำลอง (ค่าเริ่มต้น ใช้หน้า `demo/line-sim` ตามเดิม) และโหมด LINE จริง CI ใช้โหมดจำลองเป็นค่าเริ่มต้น ส่วน Test ของโหมดจริงใช้ตัวแทน HTTP โดยไม่เรียก LINE จริง
* แอปอ่าน Channel secret และ Channel access token จาก env เท่านั้น ไฟล์ตัวอย่าง env ใส่แค่ชื่อตัวแปร ไม่มีค่าแล้วระบบอยู่โหมดจำลอง ไม่ล่ม บนเครื่อง AWS (รอบ 6) ค่าจริงอยู่ใน Parameter Store และ PR D โหลดเข้า env ตอนเริ่มเครื่อง (R3-Q21)

**ลอง LINE จริงก่อนมีเครื่อง AWS (มติทีม 2026-10-14)**

* คน 3 ดูแล Cloudflare Quick Tunnel บนเครื่องของตัวเอง ไม่ต้องมีบัญชี Cloudflare ไม่ต้องซื้อโดเมน และไม่มี Tunnel token/credentials สำหรับวิธีนี้ URL แบบ `https://<random>.trycloudflare.com` เป็น URL ชั่วคราว เปลี่ยนเมื่อเปิด Tunnel ใหม่ คน 3 ต้องแก้ Webhook URL ใน LINE Developers และ Verify ใหม่ทุกครั้ง
* เส้นทางคือ LINE → Quick Tunnel → nginx proxy สำหรับพัฒนาในเครื่อง → Backend ไม่ผ่าน Caddy ของชุด Deploy Webhook URL จึงเป็น `https://<random>.trycloudflare.com/line/webhook` ไม่มี `/api` ข้างหน้า
* Quick Tunnel ไม่ใช้ ingress ของ Named Tunnel ใช้ nginx มาตรฐานกับ config ที่ไม่มีความลับใน `dev/line-webhook-proxy/nginx.conf` และ Compose สำหรับพัฒนาแยกในโฟลเดอร์เดียวกัน คน 1 และคน 2 รีวิว config และชุดทดสอบได้ ไม่ใช้ proxy ที่เขียนเองนอก repo
* อนุญาตเฉพาะ method `POST` และ raw request URI `/line/webhook` ตรงตัว ไม่ normalize หรือ percent-decode เพื่อให้ผ่าน ใช้ `$request_uri` (ไม่ใช่ `$uri`) กับ regex แบบ case-sensitive รวม method ในเงื่อนไข Query string ไม่อนุญาต: `/line/webhook?x=1` ได้ `404` method ที่ไม่ใช่ POST ถูกปฏิเสธด้วย `404` (TRACE ได้ `405` จาก nginx ก่อนเข้า rule)
* nginx ตอบ `404` เองโดยไม่ถึง Backend สำหรับ `/line/webhook/`, `/line/webhook/anything`, `/line/webhooks`, `/line/%77ebhook`, `/line/webhook%2F`, `//line/webhook`, `/line//webhook`, `/line/webhook/..`, `/LINE/webhook`, `/line/Webhook`, `/demo/reset`, `/demo/attendance/check-in`, `/internal/merge-windows/close-due` และ `/api/line/webhook` ส่งต่อ body ดิบและ `x-line-signature` โดยไม่เปลี่ยนข้อมูล Backend ยังตรวจ signature ตามเดิม
* จำกัด body ที่ 1 MiB ทั้ง Content-Length และ chunked เกินเพดานตอบ `413` ก่อนถึง Backend Compose ของ proxy เปิด port เฉพาะ `127.0.0.1` ห้ามชี้ Quick Tunnel เข้า port ของ Backend โดยตรง ให้ชี้เข้า port 18080 ของ proxy
* CI รัน `dev/line-webhook-proxy/test_proxy.py` กับ nginx config จริงและ backend จำลองแยก ตรวจ signed POST ผ่าน, signature ผิดยังถูก Backend ปฏิเสธ, body/signature ไม่เปลี่ยน และ method/path/oversized ที่ถูกปฏิเสธไม่ถึง upstream ก่อนเปิดสาธารณะ คน 3 รันชุดทดสอบและตรวจรายการเดียวกันในเครื่อง แล้วตรวจผ่าน URL สาธารณะซ้ำ (GET, HEAD, PUT, PATCH, DELETE, OPTIONS และ TRACE ต้องถูกปฏิเสธด้วย)
* Config และขั้นตอนที่ไม่มีความลับเก็บใน repo เพื่อรีวิวได้; ค่า LINE secret/access token และค่าตั้งเฉพาะเครื่องที่มีความลับอยู่บนเครื่องคน 3 ไม่ commit ไม่ใส่ใน PR/Log ไม่เพิ่ม proxy หรือ cloudflared ใน Compose หลักหรือชุด Deploy
* คน 3 ส่งบันทึกขั้นตอนการตั้ง Tunnel ที่ไม่มีความลับให้คน 1 และคน 2 เก็บไว้ด้วย เพื่อให้ตั้งใหม่ได้ถ้าเครื่องของคน 3 ใช้ไม่ได้
* ห้ามเพิ่ม `cloudflared` ใน `docker-compose.yml` หรือชุด Deploy บน AWS ระบบบน AWS ต้องทำงานได้โดยไม่มี Tunnel ตอน Deploy คน 3 เปลี่ยน Webhook URL ไปที่เครื่อง AWS แล้วปิด Tunnel
* ถ้าผู้จัดการแข่งขันไม่อนุญาต หรือ Quick Tunnel/proxy ยังใช้งานไม่ได้หรือขาดการเชื่อมต่อระหว่างทดสอบ ให้ใช้ fake LINE API และหน้าจำลองไปจนถึงรอบ 6 และบันทึกขั้นตอนที่ผ่านจริงกับขั้นตอนที่ยังไม่เสร็จ ห้ามอ้างว่าการลองที่ Tunnel ขาดกลางทางผ่านครบ Quick Tunnel ใช้เฉพาะทดสอบ/พัฒนาและไม่มี uptime guarantee

**Webhook รับคำตอบ (PR L)**

* หนึ่ง Request อาจมีหลาย Event ตรวจลายเซ็นครั้งเดียวกับ body ทั้งก้อน แล้วประมวลทีละ Event ตามลำดับใน body แต่ละ Event มี Transaction และ Commit ของตัวเอง พร้อมแถวกันซ้ำของตัวเอง Event หนึ่งพังไม่ rollback Event อื่น ประมวลครบทุก Event แล้วจึงตอบ ถ้ามี Event ใดเจอ Error ที่ไม่คาดไว้ให้ตอบ `5xx` ไม่อย่างนั้นตอบ `200` เมื่อ LINE ส่ง body เดิมมาใหม่ Event ที่ Commit แล้วถูกกันด้วยแถวกันซ้ำ เหลือประมวลเฉพาะตัวที่พัง
* ลำดับของแต่ละ Event: Event ซ้ำ (ข้อกันซ้ำข้างล่าง) → ข้อความที่ขึ้นต้นด้วย `LINK ` ไปทางผูกบัญชี (PR K) **ก่อน**ตรวจว่าผูกบัญชีแล้วหรือยัง เพราะคนที่ส่ง `LINK` คือคนที่ยังไม่ได้ผูก → Postback ของ Offer ไปทางตอบ Offer ข้างล่าง → Event ชนิดอื่น (ข้อความอื่น, follow, unfollow) เก็บแถวกันซ้ำ แล้วตอบ `200` โดยไม่เปลี่ยนข้อมูลอื่น

* ตรวจ `x-line-signature` ก่อนทำอะไร: HMAC-SHA256 ของ body ดิบตามที่ได้รับ (ก่อน parse) ด้วย Channel secret เข้ารหัส Base64 เทียบด้วย `hmac.compare_digest` ไม่มี Header หรือไม่ตรงได้ `401` และไม่เขียน DB [ตรวจกับเอกสาร LINE]
* ตัวพนักงานมาจาก `source.userId` ของ Event ที่ผ่านลายเซ็นแล้ว ผ่านตัวอ่าน `line_uid` ตัวเดียว และต้องเป็นการผูกที่ `CONTACTS.is_active` ไม่พบการผูกให้ตอบในแชตว่ายังไม่ได้ผูกบัญชี และไม่เรียก `record_response()`
* ข้อความ Offer มีปุ่ม Postback สองปุ่ม `postback.data` มีแค่ `outreach_id` กับคำตอบ ห้ามมี `staff_id` และถ้ามีก็ห้ามเชื่อ `record_response(staff_id=..., outreach_id=...)` ตรวจอยู่แล้วว่า Offer เป็นของพนักงานคนนั้น และปฏิเสธ Offer ที่ไม่เป็น `SENT` หมดเวลา หรือเคสหยุดแล้ว (ปุ่มเก่า) ด้วย `OpenOfferConflictError`
* ตอบกลับในแชตหลังส่ง HTTP response แล้วด้วย `replyToken` ของ Event ใช้ได้ครั้งเดียวภายในประมาณหนึ่งนาที [ตรวจกับเอกสาร LINE] ใช้ไม่ได้ให้บันทึก log และไม่ส่งซ้ำ เพราะผลของการตอบอยู่ใน DB แล้ว
* ตอบหลังเส้นตายใช้กติกาเดิม `clock.now() >= expires_at` ตอบไม่ได้ และตอบในแชตว่าหมดเวลา (R3-Q11)

**กันซ้ำด้วย `webhookEventId` (PR L)** LINE ส่ง Event ซ้ำด้วย `webhookEventId` เดิม ไม่รับประกันลำดับ และ Event เดียวกันอาจมาถึงมากกว่าหนึ่งครั้ง [ตรวจกับเอกสาร LINE]

* ตารางใหม่เก็บ `webhookEventId` ที่ประมวลแล้ว มี Unique Constraint (Migration)
* แถวกันซ้ำต้องถูก Commit พร้อมผลของการตอบ `record_response()` Commit ผ่าน `orchestrator.recompute()` จึงห้าม Commit แถวกันซ้ำแยกไว้ก่อน
* ห้าม Insert แถวกันซ้ำก่อนเรียก `record_response()` เพราะ `lock_case_for_outreach()` เรียก `db.rollback()` เมื่อชุด Offer เปลี่ยนระหว่างล็อก แถวจะหายไปกับ rollback
* `record_response()` รับ callback แบบไม่บังคับหนึ่งตัว ถูกเรียกหลัง `lock_case_for_outreach()` ได้ชุดล็อกที่นิ่งแล้ว และก่อนการเขียนแรกของการตอบ Webhook ใช้ callback นี้ Insert และ flush แถวกันซ้ำ หน้าจำลองและหน้าเว็บพยาบาลไม่ส่ง callback
* Insert ชน Unique Constraint: rollback แล้วตอบ `200` โดยไม่ทำอะไร
* Error ที่ไม่คาดไว้หรือ `OutreachLockRetryError`: rollback ทั้งก้อน ไม่มีแถวกันซ้ำ ตอบ `5xx` ให้ LINE ส่งใหม่
* การปฏิเสธทางธุรกิจ (`OpenOfferConflictError`, ยังไม่ได้ผูกบัญชี): rollback ผลของการตอบ แล้ว Insert แถวกันซ้ำและ Commit แยก ตอบในแชต และตอบ `200`
* LINE ส่ง Event ซ้ำเฉพาะเมื่อเปิด "Webhook redelivery" ใน LINE Developers Console ซึ่งค่าเริ่มต้นปิด คน 3 เปิดใน Channel ที่ใช้ลอง (รอบ 3 ถึง 5 ผ่าน Tunnel รอบ 6 ในส่วน LINE ของ PR D) [ตรวจกับเอกสาร LINE]

**ผูกบัญชี LINE (PR K ทำแล้ว)** ไม่มีหน้าเว็บ (R3-Q9 แบบลดขอบเขต, R3-Q22)

* ผู้ดูแลออกรหัสและปลดการผูกผ่านคำสั่ง พนักงานส่ง `LINK <รหัส>` ในแชต รหัสสุ่ม อายุ 10 นาที ใช้ครั้งเดียว เก็บเป็น hash ในตารางใหม่ (Migration)
* Event ของ `LINK` ผ่านตารางกันซ้ำตัวเดียวกับคำตอบ Offer แถวกันซ้ำ Insert ใน Transaction ของการผูก และ Commit พร้อมการผูกและ Audit (ทางนี้ไม่เรียก `lock_case_for_outreach()` จึงไม่มีการล็อกใหม่ที่ rollback แถวทิ้ง) Event ที่ LINE ส่งซ้ำหลังผูกสำเร็จจึงถูกกันด้วยแถวกันซ้ำ ไม่ได้ข้อความว่ารหัสถูกใช้แล้ว ส่วนการปฏิเสธที่คาดไว้ (รหัสผิด, หมดอายุ, ถูกใช้แล้ว, บัญชี LINE ผูกกับคนอื่นอยู่) ใช้กติกาเดียวกับการปฏิเสธทางธุรกิจของคำตอบ Offer: rollback การผูก, Insert แถวกันซ้ำและ Commit แยก, ตอบในแชต และตอบ `200`
* ทั้งระบบอ่าน `CONTACTS.line_uid` ผ่านตัวอ่านตัวเดียว บัญชี LINE หนึ่งบัญชีผูกได้กับพนักงานคนเดียว (Unique Constraint) และห้ามเขียนทับบัญชีที่ผูกแล้วอัตโนมัติ
* การใช้รหัสทำใน Transaction เดียว: ตั้งรหัสเป็นใช้แล้วแบบมีเงื่อนไข (ยังไม่ถูกใช้และยังไม่หมดอายุ ตัวเดียวกับที่ล็อกแถว) เขียนการผูก และเขียน `LINE_ACCOUNT_LINKED` แล้ว Commit พร้อมกัน ส่วนใดพังทั้งหมด rollback และรหัสยังใช้ได้ สองคำขอที่ใช้รหัสเดียวกันพร้อมกันสำเร็จได้ตัวเดียว
* `userId` ของผู้ผูกมาจาก Event ที่ผ่านลายเซ็นแล้วเท่านั้น
* คำสั่งใน Backend container คือ `python -m app.line_accounts issue-code --staff-id 201` และ `python -m app.line_accounts unlink --staff-id 201` CLI เรียก Backend ผ่าน `POST /internal/line-accounts/{staff_id}/issue-code` และ `/unlink` ที่กันด้วย `X-Internal-Secret`/`INTERNAL_JOB_SECRET` เพื่อใช้ Clock เดียวกับ Demo ไม่มีหน้าเว็บหรือ Route ออกรหัสที่ไม่ตรวจสิทธิ์ ผลรหัสตอบ `Cache-Control: no-store` และแสดงรหัสหลัง Commit เท่านั้น
* Migration `d7f0b3c5e9a2` ต่อจาก `c6e9a2b4d8f1` เพิ่ม `LINE_ACCOUNT_LINK_CODE` (สุ่ม 192 bit, SHA-256 hash, created/expires/used/revoked timestamps) และ `uq_contacts_line_uid` ครอบทุก line_uid ที่ไม่เป็น NULL รวม Contact ที่ inactive; legacy UID ซ้ำต้องแก้โดยผู้ดูแลก่อน Migration ไม่ลบหรือโอนข้อมูลเอง PR X (`e1a4c7f2b9d6`) ต่อจาก head นี้
* คำสั่ง LINK ไม่สนตัวพิมพ์ใหญ่เล็กและรับ ASCII whitespace เช่น space/tab/newline ระหว่างคำสั่งกับรหัส ส่วนตัวรหัสยัง case-sensitive; Staff ที่ไม่มี user Actor ถูกปฏิเสธก่อนออกรหัสหรือใช้รหัส LINK ไม่ retry วนเมื่อ actor หาย
* ออกรหัสหลายใบยังแยกประวัติและไม่ทับกันตาม R3-Q22; รหัสที่ยังไม่หมดอายุใช้ได้จนมีการผูกสำเร็จหรือผู้ดูแล unlink ซึ่ง revoke รหัสที่ยังไม่ใช้ทั้งหมด ไม่ revoke ตอน issue โดยอัตโนมัติ
* รหัสหมดอายุที่ `now >= expires_at` ตาม Backend Clock เช่นเดียวกับ Offer; Demo ที่ freeze ต้องเลื่อน Clock จึงหมดอายุ Staff ต้อง active และส่ง LINK ในแชตแบบหนึ่งต่อหนึ่ง ก่อนออกรหัสให้ปลดบัญชีเดิม (รวม Contact ที่ inactive) การล็อกเรียง Staff → code → Contacts ของคนนั้น ไม่ล็อก Offer/Case
* ปลดบัญชีล้างเฉพาะ line_uid คง Contact ID/line_id/is_active และ revoke รหัสที่ยังไม่ใช้เพื่อห้ามรหัสเก่ากลับมาผูกใหม่ ต้องออกรหัสใหม่หลังปลด ปลดซ้ำไม่มี Audit เพิ่มเมื่อไม่มีบัญชีอยู่แล้ว ส่วนการปลดของ Staff inactive ทำได้
* ก่อนส่ง/Retry ของ pending intent ตัวส่งตรวจว่าบัญชีที่ใช้งานได้ปัจจุบันตรงกับผู้รับเดิม หลังปลดหรือเปลี่ยนบัญชี intent ที่ไม่ตรงเป็น `NO_CONTACT` โดย Offer ยังเป็น SENT ไม่ส่ง ไม่เขียน failure audit และไม่ recompute; ไม่เปลี่ยน payload/retry key ไปหาบัญชีใหม่ งานส่งที่อยู่ระหว่าง HTTP แล้วเรียกคืนไม่ได้ แต่คำตอบหลังปลดถูกปฏิเสธจากตัวอ่านบัญชี Existing NO_CONTACT ไม่ถูกส่งย้อนหลังหลังผูกใหม่
* ขั้นตอนใช้งาน ลำดับ Lock และผลทดสอบอยู่ `docs/round3/pr-K-handoff.md`

**ส่ง Offer (PR L)**

* แถว Offer ที่ Wave เขียนมีงานส่ง: สถานะการส่ง (รอส่ง, LINE รับแล้ว, ส่งไม่สำเร็จ, ยกเลิกการส่ง, ไม่มีบัญชี LINE: `NO_CONTACT`), จำนวนครั้งที่ส่ง และ Retry key เขียนใน Transaction เดียวกับ Wave (Migration) หลัง Commit เส้นทาง HTTP จัดคิว BackgroundTasks แล้วตอบ HTTP ก่อนส่งผ่าน Push API Session ของ Request ปิดก่อนส่ง HTTP response (`scope="function"`) ตัวส่งใช้ Session ใหม่ ไม่ใช้ Session ของ Request; Route ของ Job และ Demo ที่ใช้ `get_db` จัดคิวหลัง HTTP response เช่นกัน ส่วนการเรียก Service โดยตรงที่ไม่มีคิว BackgroundTasks จะส่งหลัง Commit ภายในคำสั่งนั้น ถ้าเครื่องล่มก่อนส่ง Job เห็นแถวที่ยังรอส่งแล้วส่งให้
* แต่ละรอบส่งไม่เกิน 20 Offer โดยอ่านงานที่ถึงเวลาส่งใหม่หลังแต่ละผลลัพธ์ จึงส่ง Wave ใหม่ที่เกิดจากการส่งล้มเหลวได้ในรอบเดียว งานที่เหลือรอ Job รอบถัดไป Reply ใช้คิวหลัง HTTP response เดียวกันและทำก่อน Push เพราะ Token อายุสั้น
* ไม่มีการผูก LINE ที่ใช้งานได้และไม่กำกวม: ตั้งเฉพาะ `delivery_status = NO_CONTACT` ไม่สร้าง payload ไม่เรียก LINE ไม่นับครั้ง ไม่เขียน `OFFER_DELIVERY_FAILED` และไม่คำนวณเคสใหม่ Offer ยังคงเป็น `SENT` ผู้สมัครตอบผ่าน Simulator หรือหน้าเว็บพยาบาลได้ หากไม่ตอบจะหมดเวลาตามกติกาเดิม
* Retry key: UUID หนึ่งค่าต่อ Offer เก็บในแถวก่อนส่งครั้งแรก ส่งใน Header `X-Line-Retry-Key` ทุกครั้ง พร้อมเนื้อหาและผู้รับเหมือนเดิม Retry key ใช้ได้ 24 ชั่วโมงนับจากครั้งแรก [ตรวจกับเอกสาร LINE]
* ผลของแต่ละครั้ง [ตรวจกับเอกสาร LINE]

| ผล | ทำอะไร | นับในสามครั้ง |
|---|---|---|
| `2xx` | LINE รับแล้ว ห้ามส่งซ้ำ | |
| `409` ของ Retry key | ครั้งก่อนถูกรับแล้ว ถือว่ารับแล้วเหมือน `2xx` | |
| Timeout, `5xx` | ส่งซ้ำในรอบถัดไปด้วย Retry key เดิม | นับ |
| `429` | ส่งซ้ำในรอบถัดไป บันทึก log พร้อมข้อความจาก LINE เพราะกรณีโควตาหมดไม่หายเอง | ไม่นับ |
| `401`, `403` | ปัญหาค่าตั้งของระบบ หยุดส่งทุก Offer ในรอบนั้น บันทึก log ระดับ Error Offer ยังรอส่ง ห้ามตั้งเป็น `FAILED` | ไม่นับ |
| `4xx` อื่น | Request ของ Offer นั้นผิด ตั้ง Offer เป็น `FAILED` ทันที | |

* ส่งไม่สำเร็จครบสามครั้ง: ตั้ง Offer เป็น `FAILED` นับเหมือน `TIMEOUT` (ถือว่าติดต่อแล้ว ไม่นับในเพดาน Offer ข้อ 6.7) เขียน `OFFER_DELIVERY_FAILED` แล้วคำนวณสถานะเคสใหม่ เคสต้องไม่เป็น `FAILED` เพราะการส่งข้อความ
* ก่อนส่งซ้ำและก่อนเขียน `FAILED`: ล็อกแถว แล้วตรวจว่า Offer ยังเป็น `SENT` ยังไม่หมดเวลา และเคสยังไม่หยุด ไม่ผ่านให้ตั้งสถานะการส่งเป็นยกเลิกการส่ง ห้ามส่ง Offer ที่ล้าสมัย และห้ามเขียนทับ Offer ที่ถูกรับ ยกเลิก หมดเวลา หรือเคสหยุดแล้วด้วย `FAILED`
* LINE รับแล้วไม่ได้แปลว่าคนได้อ่าน เช่น คนบล็อกบัญชีไว้ [ตรวจกับเอกสาร LINE] Offer แบบนั้นหมดเวลาตามกติกาเดิม
* ข้อความที่แสดงเส้นตายในแชตใช้เวลาของ Clock ของระบบ การเลื่อน Clock ใน Demo จึงทำให้เวลาในแชตไม่ตรงกับนาฬิกาบนโทรศัพท์

### 6.17 หน้าเว็บพยาบาลและตัวตนจำลอง

NTT ยืนยันแล้วว่าการแข่งขันใช้ LINE Messaging API ได้ งาน LINE จึงเดินตามข้อ 6.16 ทีมตกลงเพิ่มหน้าเว็บ "ข้อเสนอเข้าเวรของฉัน" เป็นช่องทางเสริม LINE ใช้รับการแจ้งเตือนและตอบเร็ว หน้าเว็บใช้ดูรายการ ติดตามสถานะ และตอบได้ด้วย

* **สิ่งที่หน้าแสดง:** เฉพาะ Offer ของพยาบาลผู้ใช้งาน ข้อมูลมาจาก `outreach_service.list_offers()` ที่คืน `OfferView` อยู่แล้ว: หอ วันและเวลาเวร เส้นตาย ปุ่ม Accept และ Reject (`can_accept`, `can_reject`) สถานะ เหตุที่ตอบไม่ได้ (`blocked_reason`) และเหตุที่ยกเลิก (`cancellation_reason`) "รออนุมัติ" คือ `status = ACCEPTED` และ `is_assigned = false` หน้าต้องเขียนให้ชัดว่า Accept ยังไม่ใช่การได้เข้าเวร พยาบาลได้รับมอบหมายเมื่อ Head Nurse อนุมัติและระบบ Execute สำเร็จแล้ว
* **API:** `GET /me/offers` และ `POST /me/offers/{outreach_id}/response` (ข้อ 9.5) ไม่อยู่ใต้ `/demo` อ่านผ่าน `list_offers()` และตอบผ่าน `record_response()` ไม่มีกติกาการตอบชุดที่สอง ตัวพนักงานมาจากตัวตนของ Request เท่านั้น ไม่รับ `staff_id` ใน Query หรือ Body
* **แยกจากหน้าจำลอง:** ใช้ Component ของ `demo/line-sim` ได้ แต่หน้าผู้ใช้ไม่มีตัวเลือกสลับพนักงาน และไม่เรียก API ใต้ `/demo/line-sim` เพราะ `GET /demo/line-sim/offers` รับ `staff_id` จาก Query จึงอ่าน Offer ของใครก็ได้ หน้า `demo/line-sim` เดิมใช้ทดสอบต่อตามเดิม
* **ตอบจากหลายช่องทาง:** การตอบผ่าน LINE และหน้าเว็บพร้อมกันกันด้วยกติกาและ Lock ใน `record_response()` ช่องทางที่ตอบทีหลังได้การปฏิเสธ แล้วแสดงสถานะล่าสุด
* **การอัปเดตหน้า:** อ่านรายการใหม่เป็นระยะ ไม่เพิ่มระบบแจ้งเตือนใหม่ และไม่เพิ่มฟีเจอร์จัดเวรอื่นใน PR N
* **ตัวตนจำลอง:** รอบนี้ใช้ Header `X-Demo-User` เดิม หน้าและเอกสารต้องเขียนว่าเป็นโหมด Demo และไม่อ้างว่ามีระบบ Login จริง ผู้เรียกตั้ง Header นี้เองได้อิสระ การไม่รับ `staff_id` จึงกันแค่ความผิดพลาดของหน้าเว็บ ไม่ได้กันคนที่ตั้ง Header เป็นรหัสของคนอื่น ข้อนี้เป็นจริงกับทุก Route ที่ใช้ `X-Demo-User` รวมการอนุมัติของ Head Nurse
* **หน้าที่ทำแล้ว (PR N):** หน้า `/me/offers` (ลิงก์ "My offers" ในแถบเมนู) เปิดครั้งแรกให้เลือกตัวตนจำลองหนึ่งครั้งจากพนักงาน Demo ที่ไม่ใช่ผู้อนุมัติ 900 แล้วเก็บไว้ใน `localStorage` ของ Browser นั้น ค่าที่เก็บไว้ไม่อยู่ในรายการถือว่ายังไม่ได้เข้า และถ้า Browser ไม่ให้ใช้ Storage จะจำได้จนกว่าจะโหลดหน้าใหม่ ระหว่างเข้าอยู่มีป้าย "Demo mode" กับปุ่ม Sign out แทนตัวเลือกสลับพนักงาน หน้าเรียกแค่สอง Route ข้างบน ตารางและปุ่มตอบใช้ Component `OfferList` ตัวเดียวกับหน้า `demo/line-sim` ส่วนหน้าแต่ละหน้าเป็นผู้เลือก API ที่ใช้อ่านและตอบ
* **ด่านของเครื่องทดสอบบน AWS (R6-Q4 ก ข้อ 6.30, PR D ของรอบ 6 ทำแล้ว):** เครื่องเปิดเป็น HTTPS สาธารณะ และพยาบาลที่ผูก LINE จริงจะมี Offer จริงบนเครื่องนั้น PR D จึงใส่ HTTP Basic Auth ที่ Reverse proxy (`deploy/aws/Caddyfile`) ครอบทั้งหน้าเว็บและ API ยกเว้น `POST /api/line/webhook` ตรงตัว ซึ่งกันด้วยลายเซ็นของ LINE ข้อยกเว้นผูกกับ URI ดิบและ Method ตรงตัว ไม่ใช้ Prefix และไม่ใช้ตัวจับ `path` ของ Caddy (ไม่สนตัวพิมพ์ รวม `//` และถอดรหัส `%`) รหัสเก็บใน Parameter Store ไม่มีด่านนี้ห้ามเปิดเครื่องให้เข้าจากภายนอก รหัสตัวเดียวให้ทุกคนที่เข้าได้มีสิทธิ์เท่ากัน ใช้ได้กับเครื่อง Demo เท่านั้น **ไม่กัน `/demo/` แยกจากรหัส** หน้า Demo และ `/api/demo/*` ใช้ได้เมื่อใส่รหัส รายการทดสอบอยู่ที่ข้อ 6.30 วิธีตั้งเครื่องอยู่ที่ `docs/deploy-aws.md`

### 6.18 งานค้างของ Roster และการลา

ข้อนี้ทำแล้วในรอบ 3 PR R (R3-Q1) คำตอบของคำถามระหว่างทำ PR: นับ `COMPLETED` เหมือน `ASSIGNED`, ผู้แก้วันกลับคือ Head Nurse ของหอของคนลา, การลาที่ยาวขึ้นแล้วทับเวรหรือ Offer ให้บันทึกแล้วบอกในคำตอบ ไม่แตะอะไร

**Roster ของเวรที่จบแล้วเป็น `COMPLETED`**

* `roster_completion_service.complete_ended_shifts()` เป็นขั้นแรกของ `job_service.run_due_work()` (ข้อ 3.8) ตั้งแถว `ASSIGNED` ที่ `SHIFT.end_at <= clock.now()` เป็น `COMPLETED` แล้ว Commit
* **ไม่ทับ Event ที่รับไว้แล้ว:** แถวของคนที่ยังมี Event กลุ่มพนักงาน (`STAFF_UNAVAILABLE`, `ASSIGNMENT_CANCELLED`) ค้างเป็น `RECEIVED` ในเวรนั้นจะไม่ถูกตั้งเป็น `COMPLETED` เพราะตอนปิด Window ต้องเจอแถวนั้น ไม่อย่างนั้นการลาที่รับไว้ก่อนเวรจบจะถูก `IGNORED` เป็น `NO_ASSIGNED_ROSTER` และไม่มีแถวการลา แถวนั้นจะถูกตั้งในรอบแรกหลัง Event ถูกประมวล รวมกรณีที่ Window ต้องรอเคสที่ยังเดินอยู่จนเลยเวลาจบเวร
* **กันชั้นที่สอง:** ตอนปิด Window `_assigned_roster()` รับแถว `COMPLETED` ด้วย (`lock_assigned_roster(statuses=COVERING_ROSTER_STATUSES)`) เผื่อ Job ตั้งแถวเป็น `COMPLETED` ไปก่อนในจังหวะที่ชนกันพอดี Event ที่รับไว้แล้วจึงยังยกเลิกแถวได้ ส่วนการรับ Event ใหม่ยังต้องเจอแถว `ASSIGNED` เหมือนเดิม การแจ้งลาจึงได้ `409` เมื่อแถวถูกตั้งเป็น `COMPLETED` แล้ว การรับ Event ดูสถานะของแถว ไม่ได้ดูเวลาจบเวร ช่วงหลังเวรจบแต่ Job ยังไม่มาตั้งแถว การแจ้งลายังถูกรับ แล้วถูกประมวลผลตามปกติ
* ล็อกแถวด้วย `FOR UPDATE SKIP LOCKED` แถวที่ Transaction อื่นถืออยู่ (เช่น การแจ้งลากำลังยกเลิกแถว) ถูกข้ามแล้วทำในรอบถัดไป ขั้นนี้จึงไม่รอ Lock และไม่ขัดลำดับ Lock ของการรับ Event (ข้อ 6.11)
* ไม่มี Audit เพราะไม่มี `AuditAction` ของการเปลี่ยนนี้ เวลาที่เปลี่ยนดูจาก `ROSTER_ASSIGNMENT.updated_at`
* **`COMPLETED` นับเหมือน `ASSIGNED` ทุกที่** ไม่อย่างนั้นเวรเมื่อวานจะหายจากการนับโดยไม่มี Error และคนที่เพิ่งลงเวรดึกจะผ่านกฎเวลาพัก
  * `COMMITTED_ROSTER_STATUSES` (Hard Rules ทุกข้อที่ดูเวรอื่น และชั่วโมงทำงานใน `working_time_service`) มี `COMPLETED` เพิ่ม
  * `COVERING_ROSTER_STATUSES` (ใหม่) = `ASSIGNED` และ `COMPLETED` ใช้นับคนในเวรของตัวคำนวณ Gap และ Threshold เวรที่จบระหว่างที่เคสยังเปิดจึงได้ Gap เท่าเดิม
  * ตัวอ่านที่นับ `ASSIGNED` หรือ `COMPLETED` อยู่แล้ว (`case_facts_service`, `handoff_service`, `outreach_service`, Handler `EXECUTING`) ไม่เปลี่ยน
  * ตัวที่ยังดูแค่ `ASSIGNED` โดยตั้งใจ: การรับ Event (แจ้งลาหรือยกเลิกได้เฉพาะเวรที่ยังไม่จบ) และธง `is_unavailable`

**`GET /roster?staff_id=`** Filter ใหม่ของ Route เดิม (ข้อ 9.5) ต้องส่ง `shift_id` หรือ `staff_id` อย่างใดอย่างหนึ่งพอดี คืนตัวพนักงานและทุกแถว Roster ของคนนั้นทุกสถานะ พร้อมข้อมูลเวรของแต่ละแถว เรียงตามเวลาเริ่มเวร แล้วตาม `id` อ่านสอง Statement เสมอ

**ธง `is_unavailable`** ทุกแถวของ `GET /roster` ทั้งสองแบบ เป็นจริงเมื่อแถวเป็น `ASSIGNED` และคนนั้นมี `STAFF_UNAVAILABILITY` ที่ทับเวร ใช้เงื่อนไขทับเดียวกับรหัส `UNAVAILABLE` ของ Hard Rules: ช่วงลาเริ่มก่อนเวรจบ และไม่มี `end_at` หรือ `end_at` หลังเวรเริ่ม (แตะขอบพอดีไม่นับ) กติกานี้มีที่เดียวต่อภาษา: `context.leave_overlaps_shift()` ใน Python ซึ่งกฎ `UNAVAILABLE` เรียก และ `unavailability_service.leave_overlaps_shift_sql()` ใน SQL ซึ่ง `GET /roster` และการแก้วันกลับเรียก `test_leave_overlap_rule.py` ตรวจว่าสองตัวตอบตรงกันทุกกรณีขอบ คำนวณในคำสั่งเดียวกับแถว การรับ Event ยกเลิก Roster พร้อมการลาเสมอ ธงนี้จึงเกิดเมื่อมีการลาที่ไม่ได้มาจาก Event ทับเวร เช่น การลาที่ถูกแก้ให้ยาวขึ้น หน้า `roster` แสดงป้าย "On leave" ต่อท้ายสถานะของแถวที่ธงเป็นจริง

**แก้วันกลับของการลา (`PATCH /unavailability/{id}`)**

* Body `{end_at}` ต้องมีเขตเวลา และห้ามมีช่องอื่น ตั้งกลับเป็นไม่มีวันกลับไม่ได้ ใช้กับการลาที่ `end_at` เป็น `NULL` อยู่เพื่อใส่วันกลับได้
* ลำดับ: `401` Header → `422` รูปของ Body (ไม่มี `end_at`, ไม่มีเขตเวลา, มีช่องอื่น) ซึ่ง FastAPI ตรวจก่อนเข้า Handler จึงมาก่อน `404` และ `403` → `404` ไม่มีช่วงลานั้น → `403` ไม่ใช่ Head Nurse หรือไม่ใช่ Head Nurse ของหอประจำของคนลา (`manages_ward()` เดียวกับการอนุมัติ) → `422` `end_at` ไม่หลัง `start_at`
* ล็อกแถว `STAFF` ของคนลาก่อน (`hard_rule_service.lock_staff()`) แล้วล็อกแถวการลา การวางแผนของคนเดียวกันจึงเห็นช่วงลาก่อนหรือหลังการแก้ทั้งก้อน
* เขียน `UNAVAILABILITY_UPDATED` (ข้อ 7.1) แล้ว Commit พร้อมการแก้
* ไม่แตะ Roster หรือ Offer ใด คำตอบบอกแถว Roster ที่ `ASSIGNED` และ Offer ที่ `SENT` หรือ `ACCEPTED` ของเคสที่ยังไม่หยุด ซึ่งช่วงลาใหม่ทับเวร Head Nurse ตัดสินเองว่าจะแจ้ง Event ต่อหรือไม่ แถว Roster พวกนั้นขึ้นธง `is_unavailable` ใน `GET /roster`
* ข้อจำกัดที่รู้: Offer ที่ `ACCEPTED` และผ่าน Safety แล้วยังอนุมัติได้ เพราะการอนุมัติไม่ตรวจซ้ำ (Q38) คำตอบของการแก้จึงต้องบอก Offer พวกนี้ให้ Head Nurse เห็น

---

### 6.19 Cross-Ward และการย้ายคน (C1, C2, C3 ทำแล้ว)

ดึงคนจากหออื่นมาเติม Gap ได้สองแบบ (R4-Q4 ค) ทุกหอที่ `is_active` ให้ยืมได้ ไม่มีตารางคู่หอ (R4-Q5)

* **ดึงคนว่าง (C1, ทำแล้ว):** คนจากหออื่นที่ไม่มีเวรทับช่วงเวลานั้นเข้า Pool ของ `create_plan()` เหมือนคนในหอ ไม่แตะ Roster ของหอต้นทาง และหอปลายทางอนุมัติอย่างเดียว C1 ไม่ให้คนที่อยู่เวรของหออื่นเข้า Pool คนแบบนี้เข้าได้เฉพาะเป็นการย้ายของ C2 และ C3 (ข้อย่อย "C2 ทำแล้ว" และ "C3 ทำแล้ว") กติกาของ Pool ใน `optimization_service._pool()`: คนที่หอบ้านคือหอของเวรเข้า Pool เสมอ (ไม่กรองเวรทับ คนที่มีเวรทับยังไปถึง Hard Rules และถูกตัดด้วยรหัสเหมือนเดิม) ส่วนคนของหออื่นเข้า Pool เมื่อหอบ้านของเขา `is_active` และ (เขาไม่มีแถว Roster ที่สถานะอยู่ใน `COMMITTED_ROSTER_STATUSES` ซึ่งช่วงเวลาจริง (`roster_time_service`, ข้อ 6.20) ทับ `[start_at, end_at)` ของเวรแบบครึ่งเปิด เวรที่แค่ต่อกันพอดีไม่นับว่าทับ เวรของหอไหนก็นับ รวมหอปลายทาง หรือเขาย้ายได้ตามกติกาของ C3) การกรองเวรทับเป็นการอ่านก่อนล็อก `STAFF` ถ้ามีเวรถูกจัดเพิ่มระหว่างนั้น Hard Rules ที่ตรวจหลังล็อก (`check_staff`) ยังเป็นตัวกันสุดท้าย Hard Rules ใช้กับคนข้ามหอเหมือนคนในหอ (สถานะพนักงานไม่ถูกกรองในคำสั่งดึง Pool) `source` ของแต่ละคน: `SAME_WARD` ถ้าหอบ้านคือหอของเวร ไม่อย่างนั้น `FLOAT_POOL` ถ้าหอบ้านเป็น `is_float_pool` ไม่อย่างนั้น `CROSS_WARD` ผล `source` ไปที่น้ำหนักแหล่งที่มาและ `GET /cases/{id}`
* **ย้ายคนที่อยู่เวร (C2 ทั้งเวร, C3 กลางเวร):** คนที่มีแถว `ASSIGNED` ในเวรของหออื่นที่ทับช่วงเวลานั้นเข้า Pool พร้อม**เวรต้นทาง** (`CANDIDATE_ITEMS.source_assignment_id`, ข้อ 6.20) ต้องได้อนุมัติจาก Head Nurse ของทั้งหอต้นทางและหอปลายทาง (ข้อ 6.21) ตั้งแต่ C2 และ C3 เข้าแล้ว ย้ายได้ทุกเวรที่ทับเวลา รวมเวรที่ทับบางส่วนและเวรที่เริ่มแล้ว (R4-Q26 ค, R4-Q34 ข) งานแบ่งกันแบบนี้: C2 (ทำแล้ว) ทำการย้ายที่เวลาย้ายคือเวลาเริ่มของเวรต้นทาง และเวรต้นทางมีเวลาตรงกับเวรปลายทางทั้งเวร C3 (ทำแล้ว) ทำการย้ายแบบอื่นทั้งหมดในข้อย่อย "C3 ทำแล้ว"
* **C2 เจอการย้ายกลางเวร (R4-Q43, เป็นประวัติ C3 เอาออกแล้ว):** ตัวอย่าง: เวรเช้าของหอ A และหอ B เป็น 08:00 ถึง 16:00 ทั้งคู่ 201 อยู่เวรของหอ B ตอบรับตอน 07:45 หอ A อนุมัติ 07:50 หอ B อนุมัติ 08:05 เวลาย้ายจึงเป็น 08:05 ซึ่งเป็นการย้ายกลางเวร ช่วงที่มีแค่ C2 ระบบทำแบบนี้ ตั้งแต่ C3 ไม่ทำแล้ว:
  * ตอนย้ายจริง C2 จบคำขอด้วยเหตุผล `SOURCE_SHIFT_STARTED` เมื่อเวลาที่อนุมัติครบช้ากว่าเวลาเริ่มของเวรต้นทาง แล้วเลื่อนตัวสำรองหรือส่ง Wave ถัดไป (ไม่ย้ายทั้งเวรแทน เพราะ Roster จะบอกว่า 201 อยู่หอ A ตั้งแต่ 08:00 ซึ่งไม่จริง) C3 ลบค่านี้ออกจาก `TransferFailureReason` แล้ว กรณีนี้ย้ายกลางเวรสำเร็จ (ข้อย่อย "C3 ทำแล้ว")
  * ตอนวางแผน C2 ไม่เอาคนที่เวรต้นทางเริ่มไปแล้วเข้า Pool (`_movable_rows()` ต้องการ `start_at` ของเวรต้นทางมากกว่า Backend Clock) C3 แทนที่ด้วยกติกาใหม่ในข้อย่อย "C3 ทำแล้ว" คนแบบนี้เข้า Pool ได้ตาม R4-Q34 ข
  * Test ของ C2 ในกรณีนี้ถูกเปลี่ยนเป็นการย้ายกลางเวรที่สำเร็จ
  * แถว Audit เก่าที่มี `SOURCE_SHIFT_STARTED` ยังอยู่ ทุกตัวที่อ่าน `reason` ของ `TRANSFER_CHECK_FAILED` (API และหน้าเว็บ) ต้องรับค่าที่ไม่รู้จักได้และแสดงเป็นรหัสดิบ ห้ามแปลงเป็น `TransferFailureReason` แบบเข้มงวด เพราะแถวเก่าจะทำให้ตอบ `500` (`approval_service.decision_result` และหน้าเว็บอ่านเป็นข้อความดิบอยู่แล้ว มี Test ว่าแถวเก่ายังอ่านได้)
* **C3 ทำแล้ว (ย้ายกลางเวร):** ไม่มี Migration
  * **Pool:** `optimization_service._movable(db, shift)` (เดิมชื่อ `_movable_rows()`) คืน staff ID → `Cover` คนหนึ่งย้ายได้เมื่อแถว Roster เดียวที่ทับเวรปลายทาง `D` (ช่วงจริงจาก `roster_time_service.effective_interval()` คือ `[rs, re)` ครึ่งเปิด เวลาจริงที่ไม่มีใช้เวลาของเวรแทน) เป็นแถว `ASSIGNED` ในเวรที่ `is_active` ของหอที่ `is_active` อื่น และ `max(D.start_at, rs, Backend Clock) < min(re, D.end_at)` คือยังย้ายได้จริง ข้อที่เอาออกจาก C2: เวลาเริ่มและจบต้องตรงกัน, ต้องยังไม่เริ่ม และต้องไม่มีเวลาจริงของตัวเอง ดังนั้นเวรต้นทางที่เริ่มแล้ว เวรที่ทับบางส่วน และแถวที่มี `actual_end_at` ที่ยังเลยเวลาปัจจุบัน เข้า Pool ได้ ส่วนแถวที่ช่วงจริงจบไม่เกินเวลาปัจจุบันไม่เข้า เพราะย้ายไม่ได้ `_pool()` รับ key ของผลนี้ และ `_covers()` กรองตาม Pool
  * **Cover:** `Cover(m, D.end_at, source_assignment_id)` โดยเวลาย้ายตอนวางแผน `m = max(D.start_at, rs)` ไม่รวม Backend Clock โดยตั้งใจ ถ้ารวม ทุกครั้งที่คำนวณแผนใหม่จะเกิดช่วงเล็กที่ไม่มีใครครอบ `[evaluated_from, now)` ทำให้แผนเป็นแผนบางส่วนโดยไม่มีเหตุผล ส่วนชั่วโมงรวมและกฎเวลาพักได้ผลเท่ากันไม่ว่าจะตัดที่ตำแหน่งไหน เพราะส่วนของเวรต้นทางที่ถูกตัดกับช่วงที่เสนอเป็น duty ต่อเนื่องเดียวกันตามลิงก์การย้าย เมื่อ `m = D.start_at` ค่า Cover ถูกปรับเป็น `Cover(None, None, source_assignment_id)` กรณีเท่าเวรของ C2 จึงได้ Cover เดิมทุกประการ ปลายของ Cover คือ `D.end_at` เสมอ เพราะการย้ายถาวร คนไม่กลับไปเวรต้นทาง (`_apply_cover` สมมติแบบนี้อยู่แล้ว)
  * **`GAP_TIME_MISMATCH`:** เกิดได้จริงแล้ว เมื่อ Gap ที่ยังขาดอยู่เฉพาะช่วงแรกของเวรและผู้ย้ายเริ่มทำในช่วงหลัง
  * **ย้ายจริง:** `transfer_service.execute()` ใช้ `transfer_at = max(D.start_at, rs, approval.decided_at)` ตรวจตามลำดับ `DESTINATION_WINDOW_PASSED` (`transfer_at` ไม่น้อยกว่า `min(re, D.end_at)`), `SOURCE_COVERAGE_LOST` (แถวต้นทางไม่ใช่ `ASSIGNED`), แล้วตรวจกฎซ้ำด้วย `hard_rule_service.check_items(..., move_at={item.id: transfer_at})` ซึ่ง Cover เริ่มที่ `transfer_at` จริงไม่ใช่ `cover_start_at` ที่วางแผนไว้ (ปลายคือ `cover_end_at` ของรายการหรือเวลาจบเวรปลายทาง) ได้ `SOURCE_COVERAGE_LOST` สำหรับ `SOURCE_WARD_MINIMUM_VIOLATION` ก่อน แล้วจึง `HARD_RULE_FAILED` สำหรับกฎเวลา ไม่มี `SOURCE_SHIFT_STARTED` อีกแล้ว เหตุที่ต้องตรวจที่เวลาย้ายจริง: เวรต้นทางอาจเกินคนตอนเริ่มเวรแต่ขาดคนที่ `transfer_at` เมื่อมีคนอื่นออกก่อน (เช่น `actual_end_at` ของแถวอื่น)
  * **แถวหลังย้าย:** แถวต้นทางยังเป็น `ASSIGNED` และตั้ง `actual_end_at = transfer_at` หรือเป็น `CANCELLED` เมื่อ `transfer_at` ไม่เกินเวลาเริ่มจริงของแถวนั้น แถวปลายทางตั้ง `actual_start_at = transfer_at` เมื่อมากกว่าเวลาเริ่มของเวรปลายทาง และ `transferred_from_assignment_id` ชี้แถวต้นทาง Audit เป็น `ASSIGNMENT_TRANSFERRED` (`from_status` เป็นสถานะของแถวต้นทางหลังย้าย คือ `ASSIGNED` เมื่อย้ายกลางเวร หรือ `CANCELLED` และมี `transfer_at` ในข้อมูล) `roster_service.create_transfer()` ไม่เปลี่ยนตรรกะ เส้นทางกลางเวรที่ C2 เข้าไม่ถึงคือเส้นทางของ C3 แล้ว
  * **แถวที่จบไปแล้วเป็นประวัติ:** `_movable()` นับเฉพาะแถวที่ยังทับช่วงที่ย้ายได้ คือ `[max(D.start_at, Backend Clock), D.end_at)` แถวที่จบก่อนนั้น เช่น ส่วนต้นทางที่เก็บไว้ของการย้ายครั้งก่อน ไม่กันการย้ายครั้งที่สอง ตัวอย่าง: 201 ถูกย้ายจากหอ B ไปหอ C ตอน 23:05 แล้วตอน 23:10 ย้ายต่อจากแถวของหอ C ไปหอ A ได้ แถวของหอ B ที่จบ 23:05 ยังอยู่ใน Roster และกฎความล้ายังนับเป็น duty เดียวกันทั้งสาย (`linked_duty` เริ่ม 23:00)
  * **ปิดเคสจากเวลาที่เหลือ:** `gap_service.get_case_gap()` คืน `intervals` ตั้งแต่จุดที่ `assess_shift()` จะวัดตอนนี้ (`max(Backend Clock, เวลาเริ่มเวร)` เวรที่จบแล้ววัดทั้งเวรเหมือนเดิม) ด้วย `case_status.remaining_intervals()` ช่วงที่ผ่านไปแล้วถูกตัดออก ช่วงที่เริ่มแล้วเริ่มที่ตอนนี้ ตัวเลขของแต่ละช่วงคงตามที่บันทึก (Q19) และไม่แก้แถวที่บันทึก ทั้งการปิดเคส (`case_facts_service`), Wave ถัดไป (`wave_service`) และการวางแผนใหม่ (`optimization_service`) จึงใช้ช่วงที่เหลือ ตัวอย่าง: 201 ถูกย้ายกลางเวรตอน 23:05 แถวปลายทางเริ่ม 23:05 ห้านาทีแรกผ่านไปแล้วเติมย้อนหลังไม่ได้ เคสจึงเป็น `RESOLVED` ไม่ใช่ `MANUAL_HANDOFF`
  * **Test:** `test_transfer_planning.py` (ย้ายครั้งที่สองจากสายการย้ายเดิม) และ `test_transfer_execution.py` (ย้ายกลางเวรแล้วเคสเป็น `RESOLVED`, การตรวจซ้ำเสนอเวรตั้งแต่เวลาย้ายจริงเท่านั้น: เวรของหอที่สามที่จบก่อนเวลาย้ายไม่ชนกับการย้าย ถ้าตรวจด้วย Cover ที่วางแผนไว้จะได้ `SHIFT_CONFLICT`) และ `tests/unit/domain/test_gap_intervals.py` (`remaining_intervals()`)
* **Float Pool (R4-Q6, R4-Q21, R4-Q22):** หอที่ `WARD.is_float_pool = true` พนักงานที่หอบ้านเป็นหอนี้ได้ `source = FLOAT_POOL` หอนี้ไม่มีเวรของตัวเอง ทุกที่ที่วนหอต้องกรองด้วยคอลัมน์นี้ คน Float Pool ไม่ต้องมีการอนุมัติฝั่งต้นทาง
* **`source` กับเวรต้นทางเป็นคนละเรื่อง:** `source` บอกหอบ้านของคนเทียบกับหอปลายทาง เวรต้นทางบอกว่าคนนั้นถูกย้ายออกจากเวรของหอไหน ตัวอย่าง: พยาบาลหอบ้าน A ที่อยู่เวรของหอ B ถูกย้ายกลับมาเวรของหอ A ได้ `source = SAME_WARD` แต่หอ B เสียคน การอนุมัติสองหอและการไม่อนุมัติเองดูจาก "มีเวรต้นทาง" ไม่ใช่จาก `source`
* **การเลือก (R4-Q7):** Pool เดียว Solver เดิม น้ำหนักแหล่งที่มา (200 ต่อหนึ่งลำดับ) ทำให้คนในหอถูกเลือกก่อน
* **เวรต้นทางต้องไม่ขาดคน (R4-Q24):** กฎ `SOURCE_WARD_MINIMUM_VIOLATION` ขยายจากจำนวนคนเป็นครบทั้งจำนวนคน Role และ Skill คำนวณ Gap ของเวรต้นทางแบบที่คนนั้นไม่อยู่ตั้งแต่เวลาย้าย ด้วยตัวคำนวณ Gap ตัวเดียวกับเคส (ข้อ 6.20) ถ้ามี Gap ในเรื่องใด คนนั้นย้ายไม่ได้ ตรวจตอนวางแผน ตอน Safety และตอนย้ายจริง
* **หนึ่งคนต่อเวรต้นทาง (R4-Q25, R4-Q30):** Plan หนึ่งเลือกคนจากเวรต้นทางเดียวกันได้ไม่เกินหนึ่งคน ใช้กับทุก Wave `wave_service` ข้ามผู้สมัครที่เวรต้นทางเดียวกับคนในเคสนี้ที่ยังมี Offer ค้าง คำขอรออนุมัติ หรือถูกย้ายไปแล้ว ด้วยรหัส `skipped` = `SOURCE_SHIFT_TAKEN` เป็นข้อจำกัดของการวางแผน ไม่ใช่ตัวรับประกันความปลอดภัย
* **เวลาย้าย (R4-Q34):** ค่าที่มากที่สุดระหว่าง เวลาเริ่มของเวรปลายทาง, เวลาเริ่มของเวรต้นทาง และเวลาที่อนุมัติครบ ต้องน้อยกว่าทั้งเวลาจบของเวรต้นทางและเวลาจบของเวรปลายทาง
* **ย้ายจริง:** หลังอนุมัติครบ ล็อกตามข้อ 6.11 แล้วตรวจซ้ำสองอย่างจากข้อมูลล่าสุด คือกฎเวรต้นทาง และกฎของคนที่ถูกย้ายที่ขึ้นกับเวลา (`SHIFT_CONFLICT`, `INSUFFICIENT_REST`, `DAILY_HOURS_EXCEEDED`, `WEEKLY_HOURS_EXCEEDED`, `CONSECUTIVE_SHIFTS_EXCEEDED`) จาก Roster หลังย้ายที่ใช้เวลาย้ายจริง กฎอื่นไม่ตรวจซ้ำตาม Q38 นี่คือข้อยกเว้นของ Q38 ที่เพิ่มในรอบ 4 ใช้กับการย้ายคนที่อยู่เวรเท่านั้น ถ้าผ่าน ใน Transaction เดียวกัน:
  * แถวต้นทาง: ถ้าเวลาย้ายคือเวลาเริ่มของเวรต้นทาง (ยังไม่ได้ทำส่วนใด) ตั้งเป็น `CANCELLED` ไม่อย่างนั้นยังเป็น `ASSIGNED` และตั้ง `actual_end_at` = เวลาย้าย (R4-Q20, R4-Q31) ไม่ผ่านเส้นทางรับ Event จึงไม่เปิดเคสที่หอต้นทาง
  * แถวปลายทาง: สร้างแถวใหม่ ตั้ง `transferred_from_assignment_id` = แถวต้นทาง และ `actual_start_at` = เวลาย้าย ถ้าเวลาย้ายมากกว่าเวลาเริ่มของเวรปลายทาง
  * Audit `ASSIGNMENT_TRANSFERRED` (ข้อ 7.1) ห้ามใช้ `ASSIGNMENT_CANCELLED` ซึ่งเป็นของเส้นทางรับ Event
* **ตรวจไม่ผ่านตอนย้ายจริง (R4-Q35):** Commit การจบคำขอ (`is_pending = false` และ `is_approved = true` เพราะคนอนุมัติแล้ว ไม่ใช่การปฏิเสธ, R4-Q42 ดังนั้น `is_approved = true` ไม่ได้แปลว่าคนถูกย้ายแล้ว ดูข้อ 9.6) และยกเลิก Offer พร้อม Audit `TRANSFER_CHECK_FAILED` ที่มีเหตุผลหนึ่งใน `TransferFailureReason`: `SOURCE_COVERAGE_LOST`, `DESTINATION_WINDOW_PASSED`, `HARD_RULE_FAILED` (พร้อมรหัสกฎใน `failed_rules`) (`SOURCE_SHIFT_STARTED` ถูก C3 ลบแล้ว แถวเก่าอ่านเป็นข้อความดิบ ข้อย่อย "C2 เจอการย้ายกลางเวร") ห้ามใช้เหตุผลเวรต้นทางไม่พอกับทุกกรณี API ของคนกดตอบ `200` พร้อมผล (ข้อ 9.6) แล้วคำนวณเคสใหม่เพื่อเลื่อนตัวสำรองหรือส่ง Wave ถัดไป ไม่ทำให้เคสเป็น `FAILED` คำขอสองหอ: การตรวจทำตอนการอนุมัติที่ทำให้ครบสองหอ การอนุมัติของหอแรกเก็บไว้เป็นประวัติ `cancellation_reason` ของ Offer ที่ยกเลิกแบบนี้คือ `TRANSFER_CHECK_FAILED` (`outreach_service._cancellation_reasons()` ต้องรู้จัก Action นี้)
* **C2 ทำแล้ว (ย้ายทั้งเวร):**
  * **Pool:** `optimization_service._movable_rows(db, shift)` (ของ C2) คืนคนที่ย้ายได้ (staff ID → แถวต้นทาง) คนหนึ่งย้ายได้เมื่อแถว Roster เดียวที่ทับเวรปลายทาง (ช่วงจริง ครึ่งเปิด) เป็นแถว `ASSIGNED` ที่ไม่มีเวลาจริงอื่นนอกจากเวลาของเวรนั้น อยู่ในเวรที่ `is_active` ของหอที่ `is_active` อื่น เวรนั้นมี `start_at` และ `end_at` ตรงกับเวรปลายทางพอดี และยังไม่เริ่ม (`start_at` มากกว่า Backend Clock ข้อนี้ C3 แทนที่แล้วด้วยกติกาในข้อย่อย "C3 ทำแล้ว" ซึ่งเปลี่ยนชื่อเป็น `_movable()`) `_pool()` รับคนของหออื่นที่ไม่มีเวรทับหรือย้ายได้
  * **`_covers()`:** คืน `Cover(None, None, source_assignment_id)` ให้คนที่ย้ายได้ (ช่วงทั้งเวร) รวมพยาบาลหอบ้านเดียวกับเวรที่อยู่เวรเวลาเท่ากันของหออื่น ซึ่งเป็น `source = SAME_WARD` แต่มีเวรต้นทาง จึงต้องอนุมัติสองหอตามข้อ "`source` กับเวรต้นทางเป็นคนละเรื่อง"
  * **กฎเวรต้นทาง:** `SourceShift` เป็น `(shift_id, leaves_gap)` `hard_rule_service._check()` ตั้งค่านี้เมื่อ Cover เป็นการย้าย โดย `leaves_gap` = `gap_service.gap_without(db, shift=เวรต้นทาง, staff_id, from_at=เวลาเริ่มของ Cover).has_gap` ซึ่งใช้ตัวคำนวณ Gap ตัวเดียวกับเคส วัดตั้งแต่ `max(from_at, Backend Clock)` ถึงเวลาจบเวรต้นทาง ครบจำนวนคน Role และ Skill ตอนวางแผน (`check_staff`), Safety, การเลือก Wave และการตรวจ Offer ชนกัน (`check_items`) จึงตอบตรงกัน เวรต้นทางที่ไม่มี `StaffingRequirement` โยน Error เหมือน `assess_shift()`
  * **`SOURCE_SHIFT_TAKEN` ใน `wave_service`:** ลำดับการข้าม Hard Rule, `SOURCE_SHIFT_TAKEN`, `OFFER_LIMIT_REACHED` เวรต้นทางที่ถือว่าถูกเอาไปแล้วคือเวรต้นทางของ Offer `SENT` ที่ยังไม่เลยเส้นตาย (`expires_at > Backend Clock` เหมือนข้อมูลของเคส Offer ที่เลยเส้นตายแล้วไม่ถือเวรไว้ แม้ Job หมดเวลายังไม่ได้ปิด) หรือ `ACCEPTED` ของเคสนี้ที่รายการมีเวรต้นทาง กับเวรต้นทางของการย้ายที่ทำแล้วของเคสนี้ (แถวปลายทางที่ `transferred_from_assignment_id` ชี้แถวต้นทาง สถานะ `ASSIGNED` หรือ `COMPLETED` และมีคำขอที่อนุมัติของเคสนี้ซึ่งรายการนั้นมีแถวต้นทางเดียวกัน ไม่ใช่แค่อยู่บนเวรปลายทางเดียวกัน เพราะการย้ายของเคสก่อนหน้าบนเวรเดียวกันไม่นับ) ไม่นับตัวผู้สมัครเอง ใน Wave เดียวกันเวรต้นทางหนึ่งเวรให้ได้หนึ่งคน เลือกพร้อมกับเป้าหมาย: ถ้าสองคนที่ได้เครดิตมาจากเวรต้นทางเดียวกัน เก็บคนที่ทำให้ส่วนที่ยังขาด (จำนวนคน Role Skill ทุกช่วง) เหลือน้อยที่สุด เท่ากันให้ตามลำดับอันดับ คนที่ไม่ได้เก็บถูกข้ามด้วย `SOURCE_SHIFT_TAKEN` เฉพาะ Wave นั้น เวรต้นทางของกลุ่มที่ Solver เลือกไว้ปิดไม่ให้คนอื่นเข้า
  * **ย้ายจริง (ลำดับของ C2 ที่ C3 ปรับ ดูข้อย่อย "C3 ทำแล้ว"):** `transfer_service.execute()` เรียกจาก `approval_service` ตอนอนุมัติครบสำหรับรายการที่มีเวรต้นทาง `transfer_at` = ค่าที่มากที่สุดของเวลาเริ่มเวรปลายทาง, เวลาเริ่มเวรต้นทาง และเวลาอนุมัติครบ ตรวจตามลำดับ ตัวแรกที่ตรงชนะ: `DESTINATION_WINDOW_PASSED` (`transfer_at` ไม่น้อยกว่าเวลาจบที่เร็วกว่าของสองเวร), `SOURCE_COVERAGE_LOST` (แถวต้นทางไม่ใช่ `ASSIGNED` แล้ว เช่น Event ยกเลิกหลังวางแผน เพราะ Writer ต้องไม่ลิงก์กับแถวที่ตายแล้ว), `SOURCE_COVERAGE_LOST` (`check_items()` รายงาน `SOURCE_WARD_MINIMUM_VIOLATION`), `HARD_RULE_FAILED` (กฎเวลา `SHIFT_CONFLICT`, `INSUFFICIENT_REST`, `DAILY_HOURS_EXCEEDED`, `WEEKLY_HOURS_EXCEEDED`, `CONSECUTIVE_SHIFTS_EXCEEDED` ข้อใดไม่ผ่าน) ไม่ผ่านเขียน Audit `TRANSFER_CHECK_FAILED` ยกเลิก Offer (`cancellation_reason = TRANSFER_CHECK_FAILED`) เลื่อนตัวสำรองหรือส่ง Wave ถัดไป คำขอยังเป็นอนุมัติแล้ว API ตอบ `200` ผล `TRANSFER_CANCELLED` และเคสไม่เป็น `FAILED` การตรวจไม่ผ่านไม่โยน Error เพราะ Error จะทำให้เป็น D11 ผ่านแล้ว `roster_service.create_transfer()` ตั้งแถวต้นทางเป็น `CANCELLED` และสร้างแถวปลายทาง `REPLACEMENT` ที่มี `transferred_from_assignment_id` เวลาจริงเป็น NULL ทั้งเวร Audit เป็น `ASSIGNMENT_TRANSFERRED` แทน `ASSIGNMENT_CREATED` (ข้อ 7.1) `create_replacement()` ปฏิเสธรายการที่มีเวรต้นทางด้วย `ValueError` เพื่อไม่ให้ Writer ธรรมดาทำให้คนเดียวอยู่สองเวร
  * **ผลกับ Seed:** คน Medicine ของ W4 (301, 302, 401 และ 902, 950) อยู่เวรที่เวลาเท่าเวร ICU จึงเข้า Pool ของเวร ICU แล้ว Medicine มีคนพอดีเป้าหมาย 301, 302 และ 401 ถูกข้ามด้วย `SOURCE_WARD_MINIMUM_VIOLATION` ส่วน 902 และ 950 ถูกข้ามด้วย `ROLE_MISMATCH` รายการผู้สมัครของ Golden Case ยังเป็น 201, 202, 203 และ Gap เท่าเดิม
* คนหนึ่งคนมี Offer ค้างหลายเคสได้ตามกติกาเดิม (ข้อ 6.8) สิ่งที่ห้ามคือเวรที่จัดแล้วทับกัน หรือการตอบรับที่ขัดกับกติกาเดิม

### 6.20 เวลาจริงของ Roster, Gap รายช่วง, Solver และ Safety

ตัวอย่างที่ใช้ทั้งข้อ: ตอนนี้ 02:00 เวรดึกจบ 08:00 หอ B มี 5 คน ต้องเหลือ 4 คนและ Role Skill ยังครบ หอ A ขาด 1 คน Y ทำที่หอ B มาแล้ว 00:00 ถึง 02:00 แล้วย้ายไปหอ A 02:00 ถึง 08:00

**รายชื่อผู้สมัคร (T1)** `CANDIDATE_ITEMS` เพิ่ม
* `cover_start_at`, `cover_end_at` (timestamptz NULL): ช่วงที่คนนั้นมาทำได้ ว่างทั้งคู่ = ทั้งเวร CHECK ว่างทั้งคู่หรือมีทั้งคู่ และ `cover_start_at < cover_end_at`
* `source_assignment_id` (bigint NULL, FK `ROSTER_ASSIGNMENT.id`): แถว Roster ของเวรต้นทางเมื่อเป็นการย้าย ว่าง = ไม่ใช่การย้าย
* `create_plan()` เขียนสามค่านี้ตอนเขียน Plan และเก็บใน Snapshot ด้วย Safety ห้ามคำนวณช่วงใหม่เอง

**Safety และ Hard Rules (T1)**
* `hard_rule_service._check()` สร้าง `proposed` จาก `cover_start_at`/`cover_end_at` ของรายชื่อแทนเวลาของเวร และตัดแถวของเวรต้นทาง (`source_assignment_id`) ใน Roster ที่ใช้ตรวจให้จบที่ `cover_start_at` ตอนวางแผนยังไม่มีแถวรายชื่อ จึงใช้ `check_staff(covers=...)` ส่วน Safety, การเลือก Wave และการตรวจ Offer ชนกันใช้ `check_items()` ซึ่งอ่านช่วงจากแถวรายชื่อ ทั้งสองทางสร้าง Context ใน `_check()` ตัวเดียวกันจากค่าชุดเดียวกันที่เก็บไว้ ผลจึงตรงกัน แถวต้นทางที่สถานะไม่อยู่ใน `COMMITTED_ROSTER_STATUSES` (เช่น ถูกยกเลิกหลังวางแผน) ไม่ถูกตัดและไม่เกิด `linked_duty` โดยไม่ throw เพราะ throw จะทำให้เคสล้มตาม D11 ถ้าจุดตัดอยู่ที่หรือก่อนเวลาเริ่มของแถวต้นทาง แถวนั้นถูกตัดทิ้งทั้งแถว (ย้ายทั้งเวร) ถ้าแถวต้นทางจบที่หรือก่อนเวลาเริ่มช่วงที่มาทำ หรือเริ่มที่หรือหลังเวลาจบช่วงที่มาทำ (สองช่วงไม่ทับกัน) ไม่ถือเป็นการย้าย (ไม่ได้สละเวรต้นทางส่วนใด) แถวนั้นอยู่ครบและไม่เกิด `linked_duty` เวรที่ต่อกันพอดีจึงยังถูกกฎเวลาพักตรวจ
* `CandidateContext` เพิ่ม `linked_duty` (ช่วงของเวรต้นทางที่ถูกตัด หรือว่าง) กฎเวลาพักและเวรติดกันถือว่า `linked_duty` กับ `proposed` เป็นการปฏิบัติงานครั้งเดียว ชั่วโมงรายวันและรายสัปดาห์รวมทั้งสองส่วนโดยไม่นับซ้ำ ในตัวอย่าง Y ไม่ถูกปฏิเสธด้วยเวลาพัก 0 ชั่วโมง
* ส่งก่อนได้ด้วยช่วงเต็มเวรและเวรต้นทางว่าง พฤติกรรมเดิมไม่เปลี่ยน Test ตัวอย่าง Y ด้วยข้อมูลที่ Test สร้างเอง

**Roster เวลาจริง (T2)** `ROSTER_ASSIGNMENT` เพิ่ม
* `actual_start_at`, `actual_end_at` (timestamptz NULL): ว่าง = ตามเวลาของเวร CHECK `actual_start_at < actual_end_at` เมื่อมีทั้งคู่
* `transferred_from_assignment_id` (bigint NULL, FK `ROSTER_ASSIGNMENT.id`, UNIQUE): แถวต้นทางของการย้าย ระบบรวมสองแถวเป็นการปฏิบัติงานครั้งเดียว**เฉพาะคู่ที่บันทึกไว้** ไม่รวมแถวที่ต่อกันพอดีเอง เพราะกฎเวลาพักต้องยังปฏิเสธเวรที่ต่อกันพอดีโดยไม่ได้ย้าย (เช่น 16:00 ถึง 00:00 แล้ว 00:00 ถึง 08:00)
* ตัวอ่านที่เปลี่ยนไปใช้เวลาจริง: `working_time_service`, `CandidateContext` ของ Hard Rules, การนับคนของ Gap (T3), Job ตั้ง `COMPLETED`, `GET /roster`
* **T2 ทำแล้ว:** `roster_time_service` ใช้ `coalesce(actual_start_at, SHIFT.start_at)` และปลายช่วงแบบเดียวกัน; `roster_duties` รวมเฉพาะช่วงที่ต่อกันและมีลิงก์การย้ายจริง รวมส่วนต้นทางที่ `COMPLETED` แล้ว กฎความล้าใช้ช่วงรวม แต่กฎเวรซ้อน/อยู่เวรแล้ว/เคยถูกถอดใช้แถวจริงตามเดิม การย้ายเพิ่มตาม Cover ของ T1 ตัดแถวก่อนรวม duty จึงไม่ทิ้งหรือบวกส่วนที่ทำแล้วซ้ำ วัน/สัปดาห์และประเภทเวรดึกของ duty ใช้เวรเริ่มต้น รายงานชั่วโมงโหลดส่วนที่ต่อข้ามอาทิตย์ถึงจันทร์ด้วย
* `GET /roster` ทั้งสองแบบเพิ่ม `actual_start_at`, `actual_end_at`, `transferred_from_assignment_id` ในแต่ละแถว ช่องเวลาใน `shift` ยังเป็นเวลาแผน `create_replacement()` ตรวจลำดับปลายช่วงหลัง fallback ด้วย `roster_time_service.effective_interval()` แล้วคัดลอก partial Cover ลงเวลา actual; ถ้า Cover ตรงกับทั้งเวรเก็บ NULL ทั้งคู่เพื่อใช้ fallback ต่อเมื่อเวลาเวรเปลี่ยน หน้า Roster แสดงช่วงทำงานของแต่ละแถวโดย fallback แต่ละปลายแยกกัน และแสดงเลขแถวต้นทางของการย้าย Job เปลี่ยนเป็น `COMPLETED` ที่ปลายช่วงจริง โดยยังข้ามแถวที่มี Event พนักงานค้าง การแสดง On leave และรายการเวรที่ชนกับการแก้วันลาก็ใช้ช่วงจริงด้วย

* CHECK ของ actual endpoints ตรวจเมื่อมีทั้งคู่เท่านั้น จึงไม่กันช่วงกลับด้านจากการกำหนดปลายเดียวด้วย SQL โดยตรง Writer ของการย้าย (`create_transfer()` ของ C2 และ C3 เรียกแล้ว) ต้องเรียก `effective_interval()` หลังล็อก Shift ก่อนเขียน และ writer ที่แก้เวลา Shift ต้องตรวจ overrides ที่เกี่ยวข้องด้วย
* **แถวที่ทับกันในเวรเดียวกัน (แก้ใน PR #82):** คนหนึ่งมีแถว `COMMITTED` หลายแถวในเวรเดียวกันได้ ถ้าไม่ทับกัน เช่น 08:00 ถึง 12:00 กับ 12:00 ถึง 16:00 แถวที่เหมือนกันทุกอย่างนับครั้งเดียว แต่สองแถวที่ทับกัน เช่น 08:00 ถึง 16:00 กับ 12:00 ถึง 20:00 เป็นข้อมูลผิด เพราะช่วง 12:00 ถึง 16:00 จะถูกนับชั่วโมงซ้ำ `CandidateContext` จึงโยน `ValueError("Conflicting times for shift_id=...")` เหมือนตัวตรวจเดิมก่อน T2 แต่แคบลงเฉพาะกรณีทับกัน
* **ตัวเขียนการย้าย (แก้ใน PR #82, C2 ทำแล้ว):** `roster_service.create_replacement()` สร้างแค่แถวปลายทางของรายชื่อที่ไม่ใช่การย้าย รายชื่อที่มี `source_assignment_id` ถูกปฏิเสธด้วย `ValueError("A move needs create_transfer")` (เดิมเป็น `NotImplementedError` ของ T3) เพื่อไม่ให้คนเดียวอยู่สองเวรที่ทับกันโดยไม่มีลิงก์ ตัวเขียนการย้ายคือ `roster_service.create_transfer()` (C2 ทำการย้ายทั้งเวร ตัดแถวต้นทางเป็น `CANCELLED` และเขียน `transferred_from_assignment_id`; C3 ใช้ตัวเดิมกับการย้ายกลางเวร แถวต้นทางยังเป็น `ASSIGNED` พร้อม `actual_end_at` = เวลาย้าย)
* ถ้าเวรที่เสนอเป็นสมาชิกที่ไม่ใช่ต้นทางของ duty เดิม ตัวตรวจชั่วโมงนับ duty เดิมครั้งเดียว โดย ALREADY_ON_SHIFT ยังตรวจจากแถวจริงและปฏิเสธตามเดิม; ถ้าต้นทางหายจากช่วงข้อมูลที่โหลด ปลายทางที่เหลือใช้วัน/สัปดาห์ของเวลาเริ่มตัวเอง (ข้อจำกัดของ bounded read ไม่เดาต้นทางที่ไม่ถูกโหลด)

**Gap รายช่วง (T3)**
* **นิยาม (ตกลงแล้ว):** เวรไม่ขาดคนเมื่อทุกช่วงเวลาที่ยังเหลือ ตั้งแต่ `max(Backend Clock ตอนประเมิน, เวลาเริ่มเวร)` จนถึงเวลาจบ มีคนครบทั้งจำนวนคน Role และ Skill แต่ละคนนับเฉพาะช่วงปฏิบัติงานของแถว Roster ของตัวเอง ช่วงเป็นแบบ `[start, end)` ช่วงที่ผ่านไปแล้วไม่ต้องหาคนแทนย้อนหลัง แต่ชั่วโมงที่ทำแล้วยังนับในกฎความล้า ใช้นิยามเดียวกันทั้งหอต้นทางและหอปลายทาง เวรที่ไม่มีการย้ายได้ผลเหมือนเดิม
* `STAFFING_GAP` เพิ่ม `evaluated_from` (timestamptz NULL, ค่า `max(Backend Clock ตอนประเมิน, เวลาเริ่มเวร)` ว่างสำหรับแถวก่อนรอบ 4)
* ตารางลูกใหม่สามตาราง เก็บทุกช่วงที่แบ่งตามเวลาที่มีคนเข้าหรือออกจริง (รวมช่วงที่ไม่ขาด) ไม่แบ่งรายชั่วโมง: `STAFFING_GAP_INTERVAL` (`gap_id`, `start_at`, `end_at`, `required_count`, `current_count`, `gap_count`), `STAFFING_GAP_ROLE_INTERVAL` (เพิ่ม `role_id`) และ `STAFFING_GAP_SKILL_INTERVAL` (เพิ่ม `skill_id`)
* `headcount_gap` และตัวเลขสรุปของ Role Skill คงไว้เป็นค่าที่ขาดมากที่สุดของแต่ละด้านจากทุกช่วง ห้ามบวกข้ามช่วง แถวเก่าที่ไม่มีแถวรายช่วงถือว่าขาดทั้งเวรตามตัวเลขเดิม ไม่ย้อนเติม
* **ตัวอ่านที่ต้องเปลี่ยนไปใช้ข้อมูลรายช่วง (ตัดสินผล):** `domain/workflow/case_status.py` (ปิดเคส `RESOLVED`), `case_facts_service`, `domain/staffing/wave_targets.py`, `wave_service`, `optimization_service`, `optimization/solver.py` และ `merge_window_service` (ตัดสินเปิดเคส) ผู้สร้างคือ `gap_calculator`, `gap_service` และ `assess_staffing` **ตัวอ่านที่ใช้ค่าสรุปต่อได้ (แสดงผล):** `schemas/case.py`, `schemas/handoff.py`, `case_service`, `handoff_service` และหน้าเว็บ **[ตรวจแล้ว]** มี 47 จุดใน 20 ไฟล์ (`git grep` บน `staging` ใน `backend/app` และ `frontend/src`)
* การเติมคนได้เพียงบางช่วงยังปิดเคสเป็น `RESOLVED` ไม่ได้ ถ้าช่วงอื่นยังขาด
* **T3 ทำแล้ว:**
  * `gap_service.assess_shift()` วัดตั้งแต่ `max(Backend Clock, เวลาเริ่มเวร)` ถึงเวลาจบเวร เวรที่จบไปแล้วตอนประเมินไม่มีเวลาเหลือ จึงวัดทั้งเวรเหมือนก่อนรอบ 4 (Merge Window ปิดหลังเวรจบได้ ตาม Test ของรอบ 3 PR R) `evaluated_from` จึงเป็นเวลาเริ่มเวร
  * `gap_calculator.calculate_gap(window=...)` แต่ละคนนับเฉพาะช่วงจริงของแถว Roster ของตัวเอง (`load_roster()` อ่านเวลาจาก `roster_time_service`) ตัดช่วงที่ทุกเวลาเข้าออกในหน้าต่าง แล้วรวมช่วงติดกันที่ตัวเลขทั้งสามด้านเท่ากัน เวรที่ไม่มีการย้ายจึงมีช่วงเดียวและตัวเลขเท่าเดิม ค่าสรุปคือช่วงที่มีคนน้อยที่สุดของแต่ละด้าน `has_gap` ดูจากช่วง
  * `record_gap()` เขียน `evaluated_from` และแถวรายช่วงทั้งสามตาราง `get_case_gap()` คืน `intervals` (`IntervalGap` ใน `domain/workflow/case_status.py` เฉพาะ Role Skill ที่ขาด) แถวเก่าที่ไม่มีแถวรายช่วงคืนช่วงเดียวทั้งเวรตามตัวเลขสรุป
  * การตัดสินปิด Gap ใช้ `case_status.intervals_closed()` ตัดแต่ละช่วงซ้ำที่เวลาเข้าออกของคนที่นับ ทุกชิ้นต้องผ่าน `gap_closed()` ด้วยคนที่อยู่ตลอดชิ้นนั้น `GapFiller` เพิ่ม `start_at` / `end_at` (ว่าง = ทั้งเวร) `case_facts_service` ให้คนที่ได้เวรแล้วใช้ช่วงจริงของแถว Roster `REPLACEMENT` ของเวรเคส และคนที่รออนุมัติใช้ `cover_start_at` / `cover_end_at` ของรายชื่อ
  * เคสใช้ช่วงและตัวเลขที่บันทึกตอนเปิดเคสตามเดิม (Q19) ไม่วัด Roster ใหม่ ตั้งแต่ C3 ตัวอ่าน (`get_case_gap()`) ตัดช่วงที่ผ่านไปแล้วออกตอนตัดสิน เพราะเติมย้อนหลังไม่ได้ (ข้อ 6.19 "ปิดเคสจากเวลาที่เหลือ") แถวที่บันทึกไม่เปลี่ยน
  * การเปิดเคสตอนปิด Merge Window และ `ASSESSING` ใช้ `has_gap` ของผลรายช่วง

**Solver และ Wave (T4)**
* เงื่อนไข "ผลรวมคนที่เลือก ≥ เป้าหมาย" ของจำนวนคน Role และ Skill (`_cheapest_covering_group()`) เปลี่ยนเป็นเงื่อนไขละช่วงย่อย ช่วงย่อยตัดที่ทุกขอบของช่วงที่ขาดและทุกเวลาเริ่มจบของผู้สมัคร ผู้สมัครครอบช่วงย่อยที่อยู่ในช่วงที่มาทำได้ของตัวเอง การลดเป้าหมายที่เติมไม่ได้ทำรายช่วง ตัดผู้สมัครที่ไม่ครอบช่วงที่ขาดเลยออกก่อน
* `GapFiller` และ `TargetCredit` เพิ่มช่วงเวลา ช่วงที่เลือกเก็บใน Plan และส่งต่อถึง Offer คำขออนุมัติ และ Roster ให้ตรงกัน `wave_service` เลือก Wave ถัดไปตามช่วงแบบเดียวกัน
* **ด่าน:** กับข้อมูลแบบเดิม (ช่วงย่อยเดียวทั้งเวร ไม่มีผู้สมัครจากการย้าย) ผลต้องเหมือนเดิม `solver_baseline.jsonl` ผ่านโดยไม่แก้ และเวลาไม่เกินเพดานเดิม (`SOLVER_TIMING=1`) กรณีใหม่มีผลที่คาดไว้ของตัวเอง
* **แผนบางส่วน (R4-Q37, R4-Q39):** ทำเฉพาะเมื่อแบบจำลองแบบครอบครบหาคำตอบไม่ได้ หากลุ่มที่เลือกได้จริงพร้อมกันที่ครอบได้มากที่สุดก่อน แล้วใช้ลำดับเดิม (คะแนนน้อยสุด, คนน้อยสุด, รหัสพนักงานน้อยสุด) ห้ามหาค่าสูงสุดของแต่ละเป้าหมายแยกกัน ส่วนที่ขาดนับเป็นคน-นาที เทียบจำนวนคนก่อน แล้ว Role แล้ว Skill ขั้นที่เพิ่มใช้เพดานเวลาเดิม เวลาหมดพร้อมกลุ่มในมือ: ใช้กลุ่มนั้นโดยข้ามขั้นเลือกกลุ่มที่ถูกที่สุด (Test ห้ามตรวจว่าเลือกใครตรงตัว) ไม่มีกลุ่มเลย: `SOLVER_TIMEOUT` ครอบได้มากที่สุดเป็น 0: `NO_FEASIBLE_PLAN` ทั้งคู่ไป `MANUAL_HANDOFF` ห้าม `MODEL_INVALID` หรือ `FAILED` เพราะเงื่อนไขใหม่
* **คำอธิบายอันดับ:** เมื่อใช้แผนบางส่วน ข้อความบนหน้าเคส (`ScoreBreakdown`) และข้อมูลที่ส่งให้ LLM (`explanation_service`) ต้องบอกว่าการครอบมาก่อน ไม่ใช่คะแนนอย่างเดียว
* **T4 ทำแล้ว:**
  * `solve()` รับ `intervals=` (keyword, ไม่บังคับ) เป็นช่วงที่ยังขาดของ Gap `create_plan()` ส่งเฉพาะช่วงที่ขาด (`is_short()`) `None` คือช่วงเดียวทั้งเวรตามตัวเลขสรุป ซึ่ง `solver_baseline.jsonl`, Test และ Perf ใช้และได้โมเดลเดิมทุกเงื่อนไข `SolverCandidate` เพิ่ม `source_shift_id` (ว่างสำหรับคนจาก Pool) `SolverResult` เพิ่ม `partial`
  * **Need ละช่วงย่อย:** `elementary_slices()` ตัดช่วงที่ขาดตรงเวลาเริ่มหรือจบของผู้สมัครที่อยู่ภายในช่วง ผู้สมัครนับในช่วงย่อยก็ต่อเมื่ออยู่ตลอดช่วงย่อยนั้น (`covers()` กฎเดียวกับ `intervals_closed()`) หนึ่ง Need ต่อ (ช่วงย่อย, เป้าหมายจำนวนคน/Role/Skill) เงื่อนไข `ผลรวมของคนที่ครอบ ≥ เป้าหมาย` เป้าหมายถูกลดเท่าจำนวนคนที่ครอบช่วงนั้น (ลดรายช่วง) ช่วงที่ไม่มีใครครอบจึงไม่ทำให้โมเดลไร้คำตอบ Need ที่เหมือนกันทุกอย่างข้ามช่วงถูกตัดซ้ำ
  * **เลือกพร้อมกันไม่ได้ (R4-Q25):** ผู้สมัครที่มี `source_shift_id` เดียวกันเลือกได้ไม่เกินหนึ่งคน (`sum(x) ≤ 1`) ใน T4 ไม่มีผลกับ Pool เพราะทุกคนว่าง ตั้งแต่ C2 คนที่อยู่เวรเข้า Pool แล้ว เงื่อนไขนี้จึงทำงานจริง (Test ใน `test_transfer_planning.py` รวมแผนบางส่วน) และ `SOURCE_SHIFT_TAKEN` ของ `wave_service` เป็นของ C2 (ทำแล้ว ข้อ 6.19)
  * **แผนบางส่วน:** ขั้นแรกหาคำตอบไม่ได้ (`INFEASIBLE`) และโมเดลมีเงื่อนไขเลือกพร้อมกันไม่ได้ → สร้างโมเดลใหม่ที่ให้แต่ละ Need ขาดได้ (ตัวแปรขาด) โดยนับเทียบ Gap จริงของแต่ละช่วง ไม่นับส่วนเผื่อ 10% ของเป้าหมาย Wave เพราะที่เผื่อไม่ครบต้องไม่มาก่อนที่ขาดจริง (R4-Q39) แล้วลดทีละขั้นตามลำดับ: คน-วินาทีที่ขาดของจำนวนคน, Role, Skill (วินาทีเรียงเหมือนคน-นาทีของ Contract) ตรึงแต่ละขั้นก่อนขั้นต่อไป แล้วจึงเข้าขั้นเดิม (คะแนน, จำนวนคน, `staff_id`) `SolverResult.partial = true` เฉพาะเมื่อกลุ่มที่ได้ยังขาดจาก Gap จริงอย่างน้อยหนึ่งอย่าง (ถ้าขาดแค่ส่วนเผื่อ 10% และกลุ่มปิด Gap จริงได้ ผลเป็นแผนปกติ `partial = false`) สถานะ: `OPTIMAL` เมื่อพิสูจน์ครบ `FEASIBLE` เมื่อหมดเวลาพร้อมกลุ่มในมือ (ข้ามขั้นเลือกกลุ่มที่ถูกที่สุด) `UNKNOWN` เมื่อหมดเวลาโดยไม่มีกลุ่ม `INFEASIBLE` เมื่อกลุ่มที่ดีที่สุดไม่ครอบอะไรเลย (เคสไป `MANUAL_HANDOFF` ด้วย `NO_FEASIBLE_PLAN`) ส่วน `MODEL_INVALID` ยังเกิดเมื่อขั้นแรกไร้คำตอบทั้งที่โมเดลไม่มีเงื่อนไขเลือกพร้อมกันไม่ได้
  * **`_covers(db, shift, pool)`** ใน `optimization_service` คืน `{}` ใน T4 C2 คืน `Cover(None, None, source_assignment_id)` ให้คนที่ย้ายทั้งเวรได้ ตั้งแต่ C3 คืน `Cover(m, D.end_at, source_assignment_id)` ให้คนที่ย้ายได้ ซึ่งเป็นช่วงบางส่วนเมื่อ `m` ช้ากว่าเวลาเริ่มเวร และเป็น `Cover(None, None, ...)` เมื่อ `m` คือเวลาเริ่มเวร (ข้อ 6.19) ค่าที่ได้ใช้ใน `check_staff(covers=...)`, `GapFiller.start_at/end_at`, `SolverCandidate.source_shift_id` (Query เดียวจาก `ROSTER_ASSIGNMENT`), คอลัมน์ `cover_*` กับ `source_assignment_id` ของรายชื่อ และ Snapshot
  * **`GAP_TIME_MISMATCH`:** รหัสข้ามผู้สมัครใหม่ ไม่ใช่ Hard Rule `_skip_reason()` ให้ตามลำดับ: Hard Rule, `GAP_TIME_MISMATCH` (มีช่วงที่ขาดแต่ช่วงที่ผู้สมัครมาทำได้ไม่ทับช่วงใดเลย แบบครึ่งเปิด), ไม่มีอะไรให้เติมในช่วงที่ทับ (`SKILL_MISMATCH` ถ้ามีช่วงที่ทับขาด Skill ไม่เช่นนั้น `ROLE_MISMATCH`), `OFFER_LIMIT_REACHED` กับช่วงทั้งเวรได้ผลเท่าเดิม เกิดจริงได้ตั้งแต่ C3 ซึ่งให้ช่วงที่มาทำได้บางส่วน (C2 ให้แต่ช่วงทั้งเวร) เช่น Gap ขาดแค่ช่วงแรกของเวรแต่ผู้ย้ายเริ่มทำในช่วงหลัง
  * **Wave:** `get_case_fillers()` คืนคนที่นับแล้วพร้อมช่วงเวลาเหมือน `load_case_facts()` (แถว Roster จริง, ช่วงของรายชื่อที่รออนุมัติ, ตัวสำรองที่ `ACCEPTED` ใช้ช่วงของรายชื่อตัวเอง) `select_wave()` ใช้ช่วงของรายชื่อ (`cover_*`) และให้ `fill_targets_by_slice()` เลือกทีละช่วงย่อยตามเวลา โดยหักคนที่นับแล้วที่อยู่ตลอดช่วงนั้น คนที่เลือกไว้ในช่วงก่อนนับเป็นคนที่เลือกแล้วในช่วงหลังที่เขาอยู่ ข้อมูลแบบเดิมได้ช่วงเดียวและผลเดิม
  * **ช่วงของเครดิต:** `TargetCredit` เพิ่ม `start_at`/`end_at` (ว่าง = ทั้งช่วงที่ส่งเข้า) เครดิตเดียวกันของคนเดียวข้ามหลายช่วงรวมเป็นแถวเดียว `PRIMARY` ชนะ `RESERVE` และช่วงเป็นช่วงรวมของช่วงย่อยที่ให้เครดิต `CANDIDATE_ITEM_TARGET` ไม่มีคอลัมน์เวลา ช่วงจึงอยู่ใน Snapshot ของ Plan เท่านั้น
  * **Snapshot ของ Plan** (`JSONB` ไม่มี Migration; key เดิมไม่เปลี่ยน): `intervals` (ช่วงที่ขาดแต่ละช่วงในรูปเดียวกับ `targets` บวก `start_at`/`end_at`), `partial_plan` และ `credits` ของผู้สมัครใน Wave แรก (`target_type`, `selection_type`, `role_id`, `skill_id`, `start_at`, `end_at`) ตัวอ่านคะแนน (`score_from_snapshot`, `case_service._scores`) อ่านเฉพาะ key ที่รู้จัก key ใหม่จึงไม่กระทบ
  * **คำอธิบายอันดับ:** เมื่อ `partial_plan` เป็นจริง `plan_penalty.meaning` ใน Payload เปลี่ยนเป็นข้อความว่าคะแนนใช้ตัดสินเฉพาะกลุ่มที่ครอบเท่ากัน (ไม่เพิ่ม key ระดับบน) `SYSTEM_PROMPT` ให้ LLM อ่าน `plan_penalty.meaning` และ `PROMPT_VERSION` เป็น `"rank-explanation-v2"` `GET /cases/{id}` เพิ่ม `partial_plan` (ข้อ 9.3) หน้าเคสแสดงประโยค "การครอบมาก่อน" แทนประโยคเดิมเมื่อเป็นจริง

### 6.21 ผู้อนุมัติสองหอและ Supervisor (PR S ทำแล้ว)

* **ใครอนุมัติ (R4-Q8, R4-Q15, R4-Q16, R4-Q22):** คำขอที่มีเวรต้นทาง (ข้อ 6.19) ต้องได้อนุมัติจาก Head Nurse ของหอปลายทางและหอของเวรต้นทาง กดได้พร้อมกัน ต้องอนุมัติครบสองหอจึงย้าย หอใดปฏิเสธคือปฏิเสธทั้งคำขอ ใช้เส้นตายเดียวกับคำขอปกติ คนที่ว่างจากหออื่นและคน Float Pool: หอปลายทางอนุมัติอย่างเดียว
* **การตัดสินแยกต่อหอ:** ตารางใหม่ `APPROVAL_WARD_DECISION` (`approval_request_id`, `ward_id`, `side` = `DESTINATION` หรือ `SOURCE` (`ApprovalSide`), `approver_id`, `decided_as` = `HEAD_NURSE` หรือ `SUPERVISOR` (`ApproverCapacity`), `is_approved`, `reason`, `decided_at`) UNIQUE `(approval_request_id, side)` การตัดสินของคนทุกครั้งเขียนแถวนี้ คำขอเป็นผลสุดท้าย (`is_pending = false`, `approver_id`, `is_approved`, `decided_at` ใน `APPROVAL_REQUEST`) เมื่อหอสุดท้ายที่ต้องใช้อนุมัติ หรือเมื่อหอใดปฏิเสธ การอนุมัติหอแรกของคำขอสองหอเขียน Audit `APPROVAL_WARD_APPROVED`
* **Supervisor (R4-Q9, R4-Q14, R4-Q17, R4-Q18, R4-Q23):** Role ใหม่ชื่อ `SUPERVISOR` (`core/constants.SUPERVISOR_ROLE`, แถวข้อมูลใน `ROLE` ไม่มี Migration) ดูแลทุกหอ กดอนุมัติหรือปฏิเสธแทน Head Nurse ได้ทั้งฝั่งต้นทางและปลายทางเมื่อ `now >= requested_at + APPROVAL_POLICY.supervisor_after_seconds` (คอลัมน์ใหม่ Seed 600, CHECK มากกว่า 0 และน้อยกว่า `approval_timeout_seconds`) ทุกหอเปิดให้ Supervisor เสมอ ใน `MANUAL_HANDOFF` Supervisor ทำได้ทุกหอทันที Supervisor ไม่ทำงานอื่นของ Head Nurse (แก้วันกลับของการลา และแจ้ง Event ที่ Head Nurse แจ้ง)
* **ตรวจสิทธิ์ของคนกด:** `manages_ward()` คงไว้ตามเดิม เพราะ `handoff_service` ใช้ตรวจคนที่ถูกจัดเวรด้วย เพิ่มตัวตรวจตัวเดียว `domain/staffing/ward_authority.can_decide(role, home_ward_id, ward_id, waited)` ที่การอนุมัติและเส้นออกจาก `MANUAL_HANDOFF` เรียกแทนการตรวจ Role กับ `manages_ward()` แยกกัน `required_approver_role` ยังเก็บ Role เดียว (`HEAD_NURSE`) การอนุมัติสองหอตรวจคนกดกับหอของเวรต้นทางแยกจากหอปลายทาง Supervisor ที่กดก่อนเวลาได้ `403`
* **ฝั่งที่ตัดสิน (R4-Q41):** Body ของ `POST /approvals/{id}/decision` เพิ่ม `side` (`ApprovalSide`, ไม่บังคับ) ตัวอย่าง: คำขอย้าย 201 จากเวรของหอ B ไปหอ A ยังรอทั้งสองหอ Head Nurse ของหอ A กดโดยไม่ส่ง `side` ระบบถือว่าเป็น `DESTINATION` เพราะหอ A เป็นหอปลายทาง ส่วน Supervisor ที่กดหลัง `supervisor_from` ต้องส่ง `side` เพราะกดแทนได้ทั้งสองหอ กติกา:
  * Head Nurse: ไม่ส่ง คือฝั่งของหอตัวเอง ส่งฝั่งที่ไม่ใช่หอตัวเองได้ `403`
  * Supervisor: ถ้าทั้งสองฝั่งยังรอ ต้องส่ง ไม่ส่งได้ `422` ถ้าเหลือฝั่งเดียวที่รอ ไม่ส่งคือฝั่งนั้น
  * คำขอหอเดียว: ไม่ส่ง หรือส่ง `DESTINATION` ส่ง `SOURCE` ได้ `422`
  * กดฝั่งที่ตัดสินแล้วได้ `409` แบบเดียวกับคำขอที่ตัดสินแล้ว
  * ลำดับการตรวจเหมือนเดิม: `404`, `403`, `409` แล้วจึง `422` ของ `side` และ `reason` ตัวอย่าง: Supervisor กดฝั่ง `SOURCE` ที่ Head Nurse ของหอ B อนุมัติไปแล้ว ก่อน `supervisor_from` ได้ `403` ไม่ใช่ `409` เพราะยังไม่มีสิทธิ์กด S ต้องมี Test ของกรณีนี้
  * กดหนึ่งครั้งตัดสินฝั่งเดียว และเขียน `APPROVAL_WARD_DECISION` หนึ่งแถว Supervisor ที่จะตัดสินแทนทั้งสองหอต้องกดสองครั้ง
* **การทำงานของ S:** `approval_wards` หาหอต้นทางจากเวรของ `source_assignment_id` (ไม่ใช่หอบ้าน), ตรวจสิทธิ์ก่อนสถานะค้าง แล้วจึงตรวจ `side`/`reason` หลังข้อขัดแย้งทั้งหมด การอนุมัติฝั่งแรก Commit แค่แถวการตัดสินและ Audit ไม่เรียก Execute ไม่ยืดเส้นตาย และคำขอยังอยู่ใน Pending API พร้อมสถานะของทั้งสองฝั่ง
* **Lock และ Timeout:** คนกดล็อกหอปลายทางก่อน ตามด้วย Shift ของต้นทางและปลายทางใน Query เดียวเรียง ID → Request → Offers → เคส → Staff Timeout ใช้ Shift ทั้งสองตามลำดับเดียวกันแต่ไม่ล็อก Ward และไม่ต้องมีสิทธิ์ของผู้อนุมัติ คงประวัติฝั่งที่กดไปแล้ว Auto-Approval ใช้ Batch Context เดิมและไม่เขียนแถวตัดสินของคน
* **สิทธิ์ Handoff:** `can_decide()` ตัวเดียวกันให้ Supervisor จัด/ปิดเคสและอ่านรายการได้ทุกหอทันที ส่วนผู้สมัครที่จัดยังต้องเป็นพนักงานของหอปลายทางและผ่าน Hard Rules ทุกข้อ `manages_ward()` สำหรับการคัดคนคงเดิม Supervisor ไม่ได้สิทธิ์แจ้ง Event ของ Head Nurse หรือแก้วันกลับการลา
* **ขอบเขตที่เหลือ:** S เพิ่ม Role SUPERVISOR ใน Seed แต่ผู้ใช้งานจริงของ Role นี้เป็นข้อมูล W4 หน้าควบคุมฝั่งและประวัติเต็มเป็น PR U หน้าปัจจุบันเพิ่มเพียงข้อความไม่เรียก WAITING_OTHER_WARD ว่าปฏิเสธ และยังไม่ส่ง `side` ดังนั้น Supervisor ที่รอทั้งสองฝั่งต้องใช้ API ระบุฝั่งจนกว่า PR U จะเพิ่มตัวเลือก การแจ้งผลให้พยาบาลผ่าน LINE ตาม issue #75 ยังไม่รวมใน S
* **C2 ทำแล้ว:** ตัวเขียนการย้ายจริง (`transfer_service.execute()` และ `roster_service.create_transfer()`, ข้อ 6.19) แทนตัวกันของ T3 และตัวเขียนจำลองใน Test ของ S Test ของคำขอสองหอใช้ตัวเขียนจริง การย้ายที่ผ่านได้ผล `ASSIGNED` ส่วนที่ตรวจซ้ำไม่ผ่านได้ `TRANSFER_CANCELLED` ไม่ใช่ `EXECUTION_FAILED` S ยังไม่เขียน Roster ต้นทางเอง
* Test เรื่อง `403` ของรอบ 2 และ 3 คงผลเดิม ข้อยกเว้นของ Test ที่เคยเปลี่ยน required_approver_role ให้ RN เพื่อให้กดได้: S กำหนดให้คำขอใช้ HEAD_NURSE และผู้กดเป็น Head Nurse/Supervisor เท่านั้น Test ตัวตนจึงใช้ Head Nurse อีกคนที่มีสิทธิ์ และเพิ่ม Test ว่าการเปลี่ยนคอลัมน์นั้นไม่ให้สิทธิ์ RN

### 6.22 Auto-Approval (PR A)

เป้าหมาย (มติทีม 2026-10-15): ลดภาระของคนกด ไม่ใช่วัดความวิกฤตของคนไข้

* **เพดาน (R4-Q10, R4-Q11, R4-Q19):** ค่าที่ต่ำกว่าระหว่าง `APPROVAL_POLICY.ratio` × จำนวน Head Nurse ที่ Active ของหอปลายทาง กับ `APPROVAL_POLICY.incoming_count` `ratio` (Seed 2) หมายถึงจำนวนคำขอที่ผู้อนุมัติหนึ่งคนรับไหว (เดิมเขียนว่าเป็น Ratio ผู้ป่วย) Supervisor ไม่นับเป็นผู้อนุมัติของหอ หอที่ไม่มี Head Nurse ที่ Active เพดานเป็น 0 (R4-Q27 ข)
* **คิวและการอนุมัติ (R4-Q28, R4-Q32, R4-Q33, R4-Q36):** นับทุกคำขอที่รออนุมัติของหอ ถ้าคิว**เกิน**เพดาน Job อนุมัติเองคำขอที่อนุมัติเองได้**ทั้งหมด**ของหอนั้นในรอบเดียว เรียงจากรอนานที่สุด หยุดเมื่อไม่เหลือคำขอที่อนุมัติเองได้ ไม่มีสถานะข้ามรอบ หอที่คิวเกินเพดานแค่หนึ่งรายการ คำขอที่อนุมัติเองได้ทุกรายการถูกอนุมัติโดยไม่มีคนดู
* **อนุมัติเองไม่ได้:** คนข้ามหอ (`CROSS_WARD`), คน Float Pool (`FLOAT_POOL`) และคำขอที่มีเวรต้นทาง ไม่ว่า `source` จะเป็นอะไร
* **ทางเดิน (R4-Q12):** Safety ตรวจเหมือนเดิม การตอบรับสร้างคำขอตามปกติ Job ล็อก `WARD` (ข้อ 6.11) นับคิวและตรวจเงื่อนไขซ้ำ แล้วตัดสินผ่าน `approval_service.decide_automatic()` ซึ่งใช้ `_decide()` ร่วมกับ `decide()` ของคนกด ตรวจ Batch Context ที่ส่งเข้ามาโดยตรงกับ Connection และ Transaction ที่ยังล็อกอยู่ ตั้ง `approval_mode = AUTO` Actor `system` `approver_id` ว่าง และไม่เขียน `APPROVAL_WARD_DECISION` ไม่ตัดสินใน Transaction ของการตอบรับเพราะลำดับ Lock ช่อง `role_id = None` ที่ข้ามการตรวจสิทธิ์ใช้ได้เฉพาะเมื่อตรวจเงื่อนไขผ่านใน Transaction เดียวกัน
* **การทำงานของ Job:** `auto_approval_service.approve_due_requests()` ทำหลัง Offer/Approval Timeout และก่อน Recovery/ปิด Merge Window คิวที่นับต้องยังไม่หมดเวลา เคสยังไม่หยุด และยังมี Offer ที่ `ACCEPTED` ตรงกับคำขอ คำขอ Cross-Ward/Float Pool/มีเวรต้นทางนับในคิวแต่ไม่ถูกอนุมัติเอง ค่าทศนิยมของเพดานเปรียบเทียบตรงโดยไม่ปัดเศษ
* **Snapshot และ Transaction:** หลังล็อกหอ อ่านคิวและเพดาน แล้วล็อกชุดรวมของ `SHIFT` → `APPROVAL_REQUEST` → Offer → เคส → `STAFF` เรียง ID ภายในแต่ละชนิดก่อนเริ่มตัดสิน เพื่อไม่ไปล็อก Shift ใหม่หลัง Staff ของคำขอก่อนหน้า ตัวตัดสินร่วม Commit ผ่าน Savepoint แต่ Lock ของหอและทั้งชุดอยู่จน Commit ภายนอกครบทั้งหอ คำขอที่เข้าหลัง Snapshot รอรอบถัดไป ถ้าชุด Offer เพิ่มระหว่างล็อกให้เริ่มทั้งชุดใหม่สูงสุดห้าครั้ง ถ้าเกิดข้อผิดพลาดนอก D11 Rollback ทั้งหอและลองใหม่รอบถัดไป ส่วน D11 คงคำตัดสินและเคส `FAILED` ตามเดิม การคำนวณเคสอื่นและส่ง LINE ทำหลังปล่อย Lock ทั้งชุด การคำนวณเคสอื่นเป็น best-effort: ถ้าล้มเหลว log ระบุว่าไม่มีคิว retry โดยเฉพาะ จึงอาจค้างจนมีกิจกรรมอื่นหรือผู้ดูแลเรียกใหม่ ส่วนงานส่ง Offer เก็บใน DB อยู่แล้วและ Job เรียก `dispatch_pending()` ทุก tick แต่ไม่ได้รับประกันส่งข้อความสำเร็จ
* **ผล Job:** `DueWork`, `POST /internal/merge-windows/close-due` และ `POST /demo/clock/advance` คืน `auto_approved_request_ids` และ `failed_auto_approval_ward_ids` เรียง ID ทั้งสองรายการ เพื่อให้ผู้เรียกเห็นผลอนุมัติและหอที่ต้องลองใหม่ หน้า Demo แสดงผลนี้เป็นงาน PR U
* **คนเห็น (R4-Q13):** `GET /approvals/auto` ทำแล้วใน PR A; หน้า `approvals` รายการ "ระบบอนุมัติแทน" เป็นงาน PR U และ Timeline ของหน้าเคสแสดง Audit
* Golden Case มี Head Nurse 1 คน เพดาน 2 และคิวไม่เกิน 1 รายการ (คนที่ตอบรับทีหลังเป็นตัวสำรอง) จึงไม่เกิดการอนุมัติเอง Golden Path ไม่เปลี่ยน

### 6.23 LangGraph

* LangGraph ห่อแค่การเดินจาก Handler หนึ่งไป Handler ถัดไปใน `_run_round()` หนึ่ง Node ต่อหนึ่ง Handler ใน `HANDLERS` และ Edge ตาม `ALLOWED_TRANSITIONS` (R5-Q4)
* สถานะเคสใน DB ยังเป็นความจริงเดียว (D1) ไม่ใช้ Checkpointer ของ LangGraph
* ทางเข้าทั้งสี่ (`advance()`, `resume()`, `recompute()`, `leave_handoff()`) และลายเซ็นไม่เปลี่ยน Savepoint, Commit ครั้งเดียวต่อรอบ (D4), `FAILED` พร้อม `WORKFLOW_FAILED` (D11) และการส่ง LINE หลัง Commit อยู่นอก Graph การตรวจของ `_run_step()` ยังได้ `WorkflowError` เหมือนเดิม
* `langgraph` ล็อกรุ่นตรงตัวใน `backend/pyproject.toml` (R5-Q5) หลัง merge ทุกคนต้อง Restart Backend
* พิสูจน์ว่าไม่เปลี่ยน: Test เดิมทั้งหมดผ่านโดยไม่แก้ และ Test ใหม่เทียบลำดับแถว `CASE_STATUS_CHANGED` ของ Golden Case และ Scenario ของรอบ 4 กับค่าที่บันทึกจากโค้ดก่อน G (R5-Q6)
* G เข้าก่อน PR ใดที่แก้ Handler หรือ `orchestrator.py` (R5-Q3)
* **โค้ด (PR G):** Graph สร้างครั้งเดียวตอน Import จากสถานะที่มีใน `HANDLERS` แต่ละ Node เรียก `_run_step()` ซึ่งหา Handler จาก `HANDLERS` ตอนรัน Test ที่เปลี่ยนหรือลบ Handler ด้วย `monkeypatch` จึงใช้ได้เหมือนเดิม หลังแต่ละ Node ตัวเลือกทางไปดูสถานะของเคส ถ้าเป็นจุดรอหรือสถานะที่หยุดก็จบรอบ ถ้าเป็นสถานะที่ไม่มี Node ได้ `WorkflowError` ข้อความเดียวกับ `_run_step()` `recursion_limit` = `_MAX_STEPS` และ `GraphRecursionError` ถูกแปลงเป็น `WorkflowError` ข้อความเดิม รอบที่ไม่หยุดล้มหลังเรียก Handler `_MAX_STEPS` ครั้ง เท่ากับ Loop เดิม (Test ตรวจ) **ชุด Node ตายตัวตั้งแต่ Import:** เปลี่ยนหรือลบ Handler ด้วย `monkeypatch` ได้ แต่สถานะที่เพิ่มเข้า `HANDLERS` หลัง Import ไม่มี Node และได้ `WorkflowError` "No handler" PR ที่เพิ่มสถานะอัตโนมัติใหม่ต้องใส่ Handler ของสถานะนั้นใน `HANDLERS` ในโค้ด เพราะ Graph สร้าง Node จากรายการนี้ตอน Import State ของ Graph มีแค่ตัวนับก้าวที่ไม่มีใครอ่าน เคสและ Session ส่งผ่าน `config` ของการเรียกครั้งนั้น
* **[ตรวจแล้ว]** LangGraph 1.2.15 ส่ง Exception ของ Node ออกมาเป็นตัวเดิม (`error_type` ใน `WORKFLOW_FAILED` จึงไม่เปลี่ยน) และรัน Node ใน Thread เดียวกับผู้เรียก (ทั้งสองข้อมี Test ใน `test_orchestrator_graph_parity.py`) ContextVar เห็นค่าเดิม Session จึงใช้ร่วมกันได้ Dependency ที่ติดมา: `langchain-core`, `langgraph-checkpoint`, `langgraph-prebuilt`, `langgraph-sdk`, `ormsgpack`, `xxhash`, `jsonpatch`, `tenacity`, `orjson`

### 6.24 check-in และ `NO_SHOW`

**ทาง check-in (R5-Q7, R5-Q8, R5-Q23)**

* พยาบาลกด check-in ให้ตัวเองเท่านั้น ทางหน้า `/me/offers` (Route ของ N1 ตัวตนจาก `X-Demo-User` ไม่รับ `staff_id`) หรือคำสั่ง LINE (H2 ตัวตนจากบัญชี LINE ที่ผูกแล้วเท่านั้น) ทั้งสองทางเรียกฟังก์ชันกลางของ check-in ตัวเดียว
* Demo จำลองการ check-in ของตัวละครได้ผ่าน Route ใต้ `/demo/` เท่านั้น ชื่อและข้อความบนหน้าบอกว่าเป็น "จำลองการ check-in" Route ใต้ `/demo/` ต้องเข้าไม่ได้โดยไม่มีรหัสจากช่องทางสาธารณะ ใน Tunnel ของเครื่องพัฒนา `dev/line-webhook-proxy` เปิดเฉพาะ Webhook จึงตอบ `404` N1 เพิ่ม Route นี้ในรายการที่ `dev/line-webhook-proxy/check_gate.py` และ `test_proxy.py` ตรวจ บนเครื่อง AWS (รอบ 6) กฎคือทุก Path ต้องมีรหัส Basic Auth ยกเว้น `POST /api/line/webhook` ตรงตัว Path ใต้ `/demo/` และ `/api/demo/*` ใช้ได้เมื่อใส่รหัส (ข้อ 6.30) [แก้ใน PR 0 ของรอบ 6 จากประโยคเดิมที่ว่า "ต้องกันทุก Path ใต้ `/demo/`"]
* Head Nurse ยืนยันการมาทำงานแทนพยาบาลไม่อยู่ในรอบ 5
* `ATTENDANCE.shift_id` (NULL ได้ ไม่ Backfill) Unique (`staff_id`, `shift_id`) เฉพาะแถวที่มี `shift_id` กดซ้ำได้แถวเดิม แถวที่ไม่มี `shift_id` นับ OT ตามเดิมแต่ไม่นับเป็น check-in ของเวรใด
* `check_in_at` มาจาก `app.core.clock.now()` ตัวเดียวกับ Job
* Audit `ATTENDANCE_CHECKED_IN` ใส่ `source` = `SELF` หรือ `SIMULATED` (`CheckInSource`) ข้อ 7.1
* Seed มี check-in ของทุกคนในเวรที่เริ่มแล้วตอน Reset (Seed ปัจจุบัน Clock อยู่ที่ D 21:00 และเวรที่เริ่มเร็วสุดเริ่ม D 23:00 ตอน Reset จึงยังไม่มีเวรที่เริ่ม และไม่เขียนแถวใด) check-in ของ Seed ใช้ `check_in_at` = เวลาที่ต้องมาถึง, `source` = `SIMULATED`, Actor = `SYSTEM` และเขียนแถว Audit ด้วย

**เวลาที่ต้องมาถึง เส้นตาย และขอบเวลา**

* ผูกกับแถว Roster ไม่ใช่กับเวร **เวลาที่ต้องมาถึง** ของแถว `REGULAR` (รวมแถวจาก Seed) คือเวลาเริ่มที่มีผล ของแถว `REPLACEMENT` คือ `max(เวลาเริ่มที่มีผล, created_at)` เวลาเริ่มที่มีผล = `actual_start_at` ถ้ามี ไม่งั้น `SHIFT.start_at` แถว `REGULAR` ไม่ใช้ `created_at` เพราะ Seed สร้างแถวตอน Reset
* **เส้นตาย** = เวลาที่ต้องมาถึง + `NO_SHOW_GRACE_SECONDS` (900 วินาที, R5-Q9) check-in **ทัน** เมื่อ `check_in_at <= เส้นตาย`
* รับ check-in ในช่วงครึ่งเปิด `เวลาที่ต้องมาถึง − CHECK_IN_EARLIEST_SECONDS <= check_in_at < effective_end_at` (`CHECK_IN_EARLIEST_SECONDS` = 3,600 วินาที, `effective_end_at` = `actual_end_at` ถ้ามี ไม่งั้นเวลาจบเวร) ขอบล่างรวม ขอบบนไม่รวม check-in ครั้งแรกที่ตรงเวลาจบพอดีหรือหลังนั้นได้ `422` ไม่เขียน `ATTENDANCE` และไม่เริ่มทางมาสาย เพราะทางมาสายจะได้ช่วง `[เวลาจบ, เวลาจบ)` ซึ่ง `roster_time_service.effective_interval()` ปฏิเสธ (`start >= end`) check-in ซ้ำยังคืนแถวเดิม หลังเส้นตายยังรับแต่นับเป็นมาสาย
* **ลำดับการตรวจ:** ฟังก์ชันกลางของ check-in หาแถว `ATTENDANCE` เดิมของคนนั้นในเวรนั้นก่อน ถ้ามี คืนแถวเดิมทันทีโดยไม่ตรวจขอบเวลาและไม่เขียน Audit ซ้ำ ถ้าไม่มี จึงตรวจขอบเวลาแล้วเขียน Route ของหน้าเว็บ, Route จำลองและคำสั่ง LINE เรียกฟังก์ชันนี้ จึงได้ลำดับเดียวกัน
* **คนเดียวมีหลายแถว `ASSIGNED` ในเวรเดียว** (แยกเป็นช่วงตาม T2 หรือย้ายออกแล้วกลับมา): check-in ล็อกทุกแถวนั้นแล้วเลือกแถวที่ขอบเวลารับเวลานี้ ถ้ารับหลายแถวเลือกแถวที่เวลาที่ต้องมาถึงเร็วที่สุด (ถ้าเท่ากันเลือก `id` น้อยสุด) ถ้าไม่มีแถวไหนรับได้ `422` ไม่ใช่ `500` มี `ATTENDANCE` แถวเดียวต่อ (`staff_id`, `shift_id`) จึงผูกกับแถวที่เลือกตอน check-in ครั้งแรก
* ฟังก์ชันกลางตัวเดียวคิดเวลาที่ต้องมาถึง เส้นตาย และขอบเวลา Route ของ N1, คำสั่ง LINE ของ H2 และ Job ของ N2 เรียกตัวนี้
* เส้นตายไม่เปลี่ยนตามการมาสาย แถวใหม่ตอนมาสายไม่ถูกตรวจ `NO_SHOW` อีก
* **โซ่ของการย้าย:** check-in ที่ทันของแถวใดในโซ่ที่บันทึกไว้ (ตาม `transferred_from_assignment_id` ย้อนไปจนแถวแรก) นับต่อไปถึงทุกแถวถัดไปในโซ่ ไม่สร้าง `ATTENDANCE` หรือ OT ซ้ำ ถ้าไม่มี check-in ที่ทันในโซ่เลย แถวปลายทางถูกตรวจตามปกติ

**`NO_SHOW` สองขั้น (R5-Q10, R5-Q17)**

ขั้นที่ 1 ตรวจพบ (Job เขียนแค่ Event):
* Job ตรวจแถว Roster `ASSIGNED` ที่ `Backend Clock > เส้นตาย` (ตรงเส้นตายพอดียังไม่สร้าง) และเวลาจบที่มีผลยังไม่ถึง ไม่มี check-in ที่ทันในโซ่ ไม่มีแถว `STAFF_UNAVAILABILITY` ที่ทับช่วงของแถว **ไม่มี Event `STAFF_UNAVAILABLE` หรือ `ASSIGNMENT_CANCELLED` ของคนนั้นในเวรนั้นที่ยังรอ Window** และไม่มีแถวที่ย้ายออกไปจากแถวนี้ (`transferred_from_assignment_id` = แถวนี้ รวมแถวต้นทางของการย้ายกลางเวรที่ยังเป็น `ASSIGNED`) [แก้ใน PR 0 ของรอบ 6 ให้ตรงโค้ด `no_show_service.is_no_show()` ตาม R6-Q14 ก เดิมเขียนข้ามแค่ `STAFF_UNAVAILABLE` และปล่อยกรณีย้ายออกให้ขั้นที่ 2 ข้ามเป็น `IGNORED` ผลต่อ Roster และเคสเท่ากัน ต่างที่โค้ดไม่สร้าง Event ที่รู้ว่าจะถูกข้าม]
* บันทึก Event ผ่านทางเข้าใหม่ใน `event_service` ที่ใช้ขั้นรับ Event ภายในตัวเดียวกับ `receive_event()`: `event.staff_id` = พยาบาลที่ไม่มา, `actor_id` = Actor `ActorName.SYSTEM` (ไม่มี Actor ของ Job แยก), ไม่ตรวจ Role ของผู้แจ้ง, payload ของ `STAFF_UNAVAILABLE` มี Key `reason` = `NO_SHOW` Event ของการลาไม่มี Key นี้ Event รอ Window ตามปกติ

ขั้นที่ 2 ลงผล (ปิด Window):
* `merge_window_service._apply()` แยกทางด้วย `payload.reason`: `NO_SHOW` ไปทาง apply ของ `NO_SHOW` ไม่มี Key ไป `_apply_leave()` เดิม Key นี้กันไม่ให้ `_apply_leave()` ใช้ตัวพยาบาลเป็นผู้เขียน Audit ของ `NO_SHOW`
* ข้ามเป็น `IGNORED` (`NO_ASSIGNED_ROSTER`) เมื่อแถวไม่ `ASSIGNED` หรือ `COMPLETED` แล้ว หรือมีแถวที่ย้ายออกไปจากแถวนี้ (C3 เก็บแถวต้นทางของการย้ายกลางเวรเป็น `ASSIGNED`)
* แถวที่จบไปเองระหว่างรอไม่ข้าม: ยังบันทึกประวัติครบ แต่ถ้าเวรจบแล้วตอนปิด Window ไม่เปิดเคสหรือส่ง Offer ให้เวรนั้น วิธีแยก Event นี้ออกจากการตัดสินเปิดเคส N2 ทำให้ตรงกับกติกาเดิมของเวรที่จบแล้ว (ข้อ 6.18, 6.20)
* บันทึกแถว `STAFF_UNAVAILABILITY` (`reason = NO_SHOW`, `end_at` = เวลาจบที่มีผลของแถว หรือ `check_in_at` ถ้าเดินทางมาสายต่อ) ตั้งแถว Roster เป็น `CANCELLED` และเขียน Audit `UNAVAILABILITY_CREATED` ผู้เขียนเป็น Actor `SYSTEM`
* ถ้าระหว่างรอมี check-in สาย apply ไม่ข้าม บันทึก `NO_SHOW` แล้วเดินทางมาสายต่อใน Transaction เดียวกัน
* `NO_SHOW` หลายเวรติดกันได้แถวใหม่ทุกเวร แจ้งลาย้อนหลังไม่เปลี่ยน `reason`

**มาสาย (R5-Q11, R5-Q12, R5-Q22)**

* check-in สายก่อนขั้นที่ 1 หรือระหว่าง Event รอ Window: Route บันทึก check-in อย่างเดียว ขั้นที่ 2 เดินทางมาสายต่อ check-in สายหลังขั้นที่ 2: Route เดินทางมาสายเองทันที ทั้งสามกรณีเรียกฟังก์ชันมาสายตัวเดียว
* ทางมาสายสร้างแถว Roster ใหม่ที่ `actual_start_at` = `check_in_at` ผ่านฟังก์ชันกลางของ H1 (ข้อ 6.25) N2 ห้ามสร้างแถว Roster เอง และลด `end_at` ของแถว `NO_SHOW` เป็น `check_in_at`
* แถวใหม่ได้ Handover เมื่อแถวที่ถูกยกเลิกมี Handover (คนนั้นเป็นคนแทน) คนเดิมของเวรไม่ได้
* หลัง check-in ประเมิน Gap รายช่วงที่เหลือ คนแทนที่ได้เวรแล้วไม่ถูกยกเลิก (ทั้งที่ยังไม่ check-in และ check-in แล้ว) Offer ที่ยังไม่ตอบและคำขอที่รออนุมัติถูกยกเลิกเฉพาะที่เกินจำนวนที่เคสยังขาดหลังคนที่มาสายถูกนับ เคสที่ยังขาดคนยังหาคนต่อ
* **เก็บใครไว้ก่อน:** ความครอบคลุมมาก่อน เก็บชุดคนที่ปิด Gap รายช่วงที่เหลือได้มากที่สุด (คนที่ครอบไม่เต็มช่วงไม่ได้ปิดช่วงที่ไม่ได้ครอบ) ถ้าเท่ากัน เก็บคนที่ไปไกลกว่า (คำขอที่รออนุมัติก่อน Offer ที่ยังไม่ตอบ) ถ้ายังเท่ากัน เก็บอันดับใน Plan ที่ดีกว่า ที่เหลือยกเลิกด้วย Audit `OFFER_CANCELLED_NOT_NEEDED` (ข้อ 7.1) การตัดสินว่า Gap ปิดแล้วใช้กติกาเดียวกับ `recompute()`
* เวรเกินคนได้ Head Nurse ตัดสินเองว่าจะให้ใครกลับ รอบ 5 ไม่มีปุ่มสำหรับเรื่องนี้

**N2 ทำแล้ว:** ไม่มี Migration ฟังก์ชันที่ทำตามกติกาข้างบน:

* **ขั้นที่ 1:** `no_show_service.detect_due_no_shows()` Job เรียกก่อน `close_due_windows()` ใน `job_service.run_due_work()` หา Hint ของแถว `ASSIGNED` โดยไม่ล็อก แล้วต่อเวร ล็อก `SHIFT` และแถวผู้สมัครใน Query เดียวเรียงตาม `id` และตรวจซ้ำด้วย `no_show_service.is_no_show()` ก่อนเรียก `event_service.record_no_shows()` (แยกตัวเขียน Event และปิด Window 0 วินาทีออกจาก `receive_event()` ที่พฤติกรรมไม่เปลี่ยน) เวรที่ Error ถูก Rollback บันทึก Log และข้ามไปเวรถัดไป `no_show_service.has_on_time_check_in()` เดินโซ่ `transferred_from_assignment_id` ย้อนไปแถวแรก (กัน Loop) และนับ check-in ที่ `check_in_at <= เส้นตาย` ของแถวนั้นๆ Event ทุกตัวของเวรเดียวเขียนใน Transaction เดียวแล้วปิด Window ครั้งเดียว `no_show_event_ids` ของ `DueWork` อยู่ในคำตอบทั้งสอง Route (ข้อ 9.3)
* **Key `roster_assignment_id`:** payload ของ Event ขั้นที่ 1 เป็น `{"reason": "NO_SHOW", "roster_assignment_id": <id ของแถว>}` ขั้นที่ 2 และทาง check-in หาแถวที่แน่นอนจาก Key นี้ เพราะคนเดียวมีหลายแถวในเวรเดียวได้ และ `lock_assigned_roster()` ปฏิเสธเมื่อมีมากกว่าหนึ่งแถว
* **ข้อยกเว้นของขั้นที่ 1 กว้างกว่า Contract:** Contract ระบุแค่ Event `STAFF_UNAVAILABLE` ที่รอ Window โค้ดยกเว้นแถวของคนที่มี Event `RECEIVED` ชนิดใดก็ได้ใน `STAFF_EVENT_TYPES` ในเวรนั้น คือการลาที่รออยู่ **หรือ** การยกเลิกเวรที่รออยู่ (`ASSIGNMENT_CANCELLED`) เพราะถ้าไม่ยกเว้น Event ของ `NO_SHOW` จะถูก `IGNORED` ทีหลังอยู่ดี
* **ขั้นที่ 2:** `merge_window_service._apply()` ส่ง Event ที่ `payload.reason == "NO_SHOW"` ไป `_apply_no_show()` และคืน `bool` ว่า Event นับเข้า Threshold หรือไม่ (ทุกทางเดิมคืน `True`) `_apply_no_show()` ล็อกแถวจาก `roster_assignment_id` แล้วข้ามเป็น `IGNORED` (`NO_ASSIGNED_ROSTER`) โดยไม่เขียนอะไรเมื่อแถวหาย ไม่อยู่ใน `COVERING_ROSTER_STATUSES` หรือมีแถวที่ลิงก์ย้ายออกจากมัน ไม่งั้นเขียน `STAFF_UNAVAILABILITY` (`start_at` = เวลาที่ต้องมาถึงของแถว, `end_at` = `check_in_at` ถ้ามี check-in ก่อนเวลาจบที่มีผลของแถว ไม่งั้นเวลาจบที่มีผลของแถว) ตั้งแถวเป็น `CANCELLED` และเขียน `UNAVAILABILITY_CREATED` Actor `SYSTEM` ถ้ามี check-in สายเรียก `late_arrival_service.restore()` ในรอบเดียวกัน ตอนนั้นไม่มีเคสเดิน (`_is_due` ต้องไม่มีเคส) จึงไม่มี Offer เกิน การตัดสินว่าเวรจบแล้วคืน `shift.end_at > clock.now()`
* **`NO_SHOW` ที่เป็นประวัติอย่างเดียว:** Event ที่ `_apply_no_show()` คืน `False` (เวรจบแล้ว) ไม่นับเข้า Threshold และไม่ทำให้เปิดเคส ถ้าไม่มี Event อื่นใน Window เปิดเคส Event นั้นเป็น `IGNORED` ด้วยรหัส `SHIFT_ENDED` (ข้อ 3.7) ถ้ามี Event อื่นเปิดเคส Event นั้นเป็น `PROCESSED` พร้อม `case_id` เหมือน Event ที่ไม่ผ่าน Threshold ตัวอื่น (Q42)
* **มาสาย:** `late_arrival_service.restore()` ตรวจว่าแถวเดิม `CANCELLED` และ `check_in_at` ก่อนเวลาจบที่มีผล แล้วเรียก `roster_service.restore_late_arrival()` (Actor `SYSTEM`) ไม่ Commit `late_arrival_service.arrive_after_no_show()` คือทาง check-in หลังขั้นที่ 2: ลด `end_at` ของ `STAFF_UNAVAILABILITY` เป็น `check_in_at` เรียก `restore()` เขียน `UNAVAILABILITY_UPDATED` (ข้อ 7.1) ใต้ `late_arrival_service.credited_case()` (เคสล่าสุดของเวรที่ไม่อยู่ใน `TERMINAL_CASE_STATUSES` รวม `MANUAL_HANDOFF` ถ้าไม่มีเป็น `NULL`) ถ้าเคสรออยู่ (`WAITING_CASE_STATUSES`) เรียก `orchestrator.recompute()` โดยใช้ `late_arrival_service.trim()` เป็น `prepare` ไม่งั้น Commit เฉย แล้วหลัง Commit เรียก `outreach_service.recompute_affected_cases()` ของทุกคนที่ Offer ถูกยกเลิก (จับ Exception ไว้เหมือนทางอนุมัติ) ถ้า check-in ตรงหรือหลังเวลาจบของแถว ได้ `422` และไม่เขียนอะไร
* **เคสนับคนที่มาสายอย่างไร:** Audit `UNAVAILABILITY_UPDATED` ที่ `case_id` เป็นเคสนี้และมี `roster_assignment_id` ใน payload คือสิ่งที่ทำให้เคสนับคนนั้น `case_facts_service._returned_spans()` อ่านแถวนี้ แล้วนับคนในช่วงที่มีผลของแถวใหม่ (`ASSIGNED` หรือ `COMPLETED`) เข้ากลุ่ม `assigned` ของ `load_case_facts()` (ที่ `execute_assignment` และ `recompute` ใช้) และ `get_case_fillers()` (ที่ Wave ถัดไปใช้) **ไม่นับ**ใน `assigned_staff_ids()` ของ Read Model เพราะแถว Roster ไม่มีลิงก์ไปเคส Gap ของเคสเป็น Snapshot (Q19) ที่ทำตอนแถวถูกยกเลิก จึงนับคนที่มาสายครั้งเดียว
* **`trim()` เก็บใครไว้:** `late_arrival_service.trim()` ทำใน `prepare` ของ `recompute()` ขณะได้ Lock ครบ ใช้ `case_status.interval_shortage()` (ผลรวมของ (หัวที่ขาด + Role ที่ขาด + Skill ที่ขาด) × ความยาวของแต่ละท่อนเป็นวินาที ตัดท่อนแบบเดียวกับ `intervals_closed()` คนที่ครอบแค่บางส่วนนับเฉพาะท่อนที่ครอบเต็ม) และ `case_status.choose_kept()` (Greedy เก็บคนที่ลดค่านั้นได้มากที่สุดทีละคน หยุดเมื่อไม่มีใครลดได้) จึงเลือกความครอบคลุมก่อนเสมอ ถ้าเท่ากันเลือกตามลำดับ: คำขอที่รออนุมัติพร้อม Offer `ACCEPTED` ก่อน Offer `SENT` ที่ยังไม่ตอบ แล้ว `CandidateItem.rank` ที่ดีกว่า แล้ว `id` น้อยกว่า ฐานคือคนที่ได้เวรแล้วรวมคนที่มาสาย (`case_facts_service.get_assigned_fillers()`) ผู้สมัครที่ไม่ถูกเก็บถูก `outreach_service.cancel_offer()` (คำขอคงอยู่เป็นประวัติ) พร้อม Audit `OFFER_CANCELLED_NOT_NEEDED` และ `outreach_service._cancellation_reasons()` คืน `NO_LONGER_NEEDED` ให้ `/me/offers` Offer `SENT` และคำขอที่รออนุมัติซึ่งหมดอายุแล้ว (`expires_at` ไม่เกินเวลาตอนนี้) ไม่เป็นตัวเลือก ไม่ถูกเก็บและไม่ถูกยกเลิก ปล่อยให้ Job หมดเวลาจัดการและเขียน Audit ของมันเอง คำขอที่หมดอายุจึงแย่งที่ Offer ที่ยังใช้ได้ไม่ได้ และ Offer ที่ตอบรับเป็นตัวสำรองโดยไม่มีคำขอไม่ถูกแตะ
* **check-in สายแล้วอาจไม่เปิดเคส:** check-in สายตอน Event ยังรอ Window คืนแถวทันทีตอนปิด Window ถ้าคนที่กลับมาทำให้ Threshold ไม่ผ่าน Event เป็น `IGNORED` (`THRESHOLD_NOT_PASSED`) และไม่มีเคส
* **ลำดับ Lock และ Retry** ของ check-in สายอยู่ข้อ 6.11 ชุด Offer ที่ใช้เทียบคือชุดที่ Query ล็อกได้จริง ไม่ใช่การอ่านซ้ำทีหลัง Offer ที่เกิดหลัง Query นั้นจึงทำให้เริ่มใหม่เสมอ `attendance_service.CheckInLockRetryError` (`CHECK_IN_LOCK_TRIES = 5`) ทำให้ทั้งสอง Route ตอบ `409`

### 6.25 Handover (H1 และ H2 ทำแล้ว)

* หนึ่งแถว Handover ต่อหนึ่ง `roster_assignment_id` ของคนที่ได้เวรแทน (R5-Q14) สร้างใน Transaction เดียวกับการจัดเวร เขียน Audit `HANDOVER_GENERATED` เนื้อหาเป็นข้อมูลจาก DB ล้วน ไม่ใช้ LLM (R5-Q13)
* ทุกทางที่สร้างเวรเรียกฟังก์ชันกลางตัวเดียว มีห้าทาง: อนุมัติ, อนุมัติเอง, จัดเองใน `MANUAL_HANDOFF`, การย้าย และแถวใหม่ตอนมาสาย สี่ทางแรกสร้าง Handover เสมอ ทางที่ห้าสร้างเฉพาะเมื่อแถวที่ถูกยกเลิกมี Handover
* `STRUCTURED_HANDOVER.roster_assignment_id` NOT NULL และ Unique ตารางไม่มีแถวเดิม จึงไม่ต้อง Backfill
* ย้ายกลางเวรซ้ำได้ Handover แถวใหม่ทุกครั้ง (R5-Q20) Handover เก็บไว้ไม่ลบ ไม่มีสถานะการใช้งานแยกต่างหาก (R5-Q21); `delivery_status` ของ H2 เป็นสถานะการส่งเท่านั้น
* **Handover ใช้งานอยู่** เมื่อแถว Roster เป็น `ASSIGNED` และ `Backend Clock < effective_end_at` (`actual_end_at` ถ้ามี ไม่งั้นเวลาจบเวร) ที่ไม่ใช้งานแล้วหายจากรายการปัจจุบันและหยุดส่งทาง LINE แต่ยังอยู่ในประวัติ เวรที่ยังไม่เริ่มอ่านได้เลย
* คนที่มาแทนเห็นในหน้า `/me/offers` และได้ทาง LINE Head Nurse เห็นในหน้าเคส (R5-Q15) การย้ายไม่มี Handover ฝั่งต้นทาง (R5-Q16)
* **ส่งทาง LINE (H2 ทำแล้ว, R5-Q24):** ขยาย `line_delivery_service` ให้ส่ง Handover ได้ บันทึกความตั้งใจส่งใน Transaction เดียวกับ Handover แล้ว Job ส่งต่อ ได้ Retry key ลองไม่เกิน 3 ครั้ง และการกู้หลังเครื่องล่มแบบเดียวกับ Offer ส่งหลัง Commit เท่านั้น ส่งล้มไม่ย้อนการจัดเวร ตรวจว่า Handover ยังใช้งานอยู่ซ้ำก่อนส่งและทุกครั้งที่ลองใหม่
* **รายละเอียด H2:** `delivery_*` อยู่บน `STRUCTURED_HANDOVER` (Migration `f6b2d8a4c0e1` ต่อ H1) ใช้สถานะและ Retry policy ร่วมกับ Offer แต่ส่งล้มเปลี่ยนเฉพาะสถานะส่ง ไม่แก้เคส/Roster หรือเขียน `OFFER_DELIVERY_FAILED` ไม่มี binding เป็น `NO_CONTACT` โดยไม่มี Payload/Attempt ถ้า unlink/rebind จะไม่เปลี่ยนผู้รับใน Payload เดิม ทุก Claim/Finish ล็อก `SHIFT` → `ROSTER_ASSIGNMENT` → `STRUCTURED_HANDOVER` ตรวจ `ASSIGNED` และเวลาจบจริง ปล่อย Transaction ก่อนเรียก LINE เคส `RESOLVED` ส่ง Handover ได้ รอบหนึ่งส่งไม่เกิน 20 Offer และ 20 Handover; 401/403 หยุดทั้งรอบ Job กู้ Intent ที่พลาดการส่งหลัง Commit ได้ ทางจัดเองเรียกตัวส่งหลัง Commit เช่นเดียวกับทางอนุมัติ
* **เช็กอินทาง LINE (H2 ทำแล้ว):** พิมพ์ `CHECKIN <shift_id>` (ไม่แยกตัวพิมพ์เล็กใหญ่) หรือกดปุ่มใน Handover ซึ่งส่ง `action=CHECK_IN&shift_id=<id>` รับเฉพาะสอง Key นี้อย่างละหนึ่งค่าและเลขเวรบวกในช่วง bigint ใช้ UID จาก `source.type=user` ที่ผูกและ Active เท่านั้น ไม่รับตัวตนจากข้อความ เรียก `attendance_service.check_in()` ของ N1 พร้อม Callback บันทึก Event dedup ใน Transaction เดียวกับ Attendance/Audit (`source=SELF`) ข้อผิดพลาดทางธุรกิจตอบกลับและรับ Event เป็น 200; ความผิดพลาดระบบ Rollback ทั้งชุดและตอบ 503 ให้ LINE ลองใหม่ คำตอบส่งหลัง Commit และหลัง HTTP response ผ่าน BackgroundTasks เหมือน Offer เดิม ดูวิธีทดสอบและข้อจำกัดใน `docs/round5/pr-H2-handoff.md`
* **ข้อความเช็กอิน:** ครั้งแรกตอบ “เช็กอินเวร … สำเร็จ เวลา … น. (ทันเวลา/มาสาย)” การกดซ้ำที่เป็น Event ใหม่ตอบ “คุณเช็กอินเวร … แล้ว เวลา … น. (ทันเวลา/มาสาย) ไม่ต้องเช็กอินซ้ำ” ใช้เวลาไทยและผลที่บันทึกครั้งแรก ไม่แก้ Attendance หรือสร้าง Audit ใหม่ ส่วนการส่ง Event ID เดิมซ้ำเป็น No-op ตามเดิม
* แนวทางของรอบ 6: ถ้าใช้ LLM เขียนข้อความ ให้บันทึก `PENDING` ใน Transaction นี้แล้วประมวลผลภายหลัง LLM ล้มต้องไม่ย้อนการจัดเวร

**H1 ทำแล้ว:** ทุกทางสร้างแถวผ่าน `roster_service.create_assignment()` แล้ว `handover_service.ensure()` สร้าง Snapshot และ Audit โดยไม่ Commit หรือเพิ่ม Row Lock การเรียก `ensure()` ซ้ำได้แถวเดิม Unique Constraint และ `INSERT ... ON CONFLICT` กันสอง Connection เขียนซ้ำ Migration `e8c4b2a6f0d9` ต่อจาก N1 `a4d8e1b7c3f5` ส่วน N2 ใช้ `roster_service.restore_late_arrival()` หลังยกเลิกแถวเดิมและได้ Lock ครบ (ดู `docs/round5/pr-H1-handoff.md`) H1 ไม่อ่านคอลัมน์ใหม่ของ `ATTENDANCE`; H2 เพิ่ม LINE delivery intent ใน Transaction เดียวกับ Snapshot ใหม่เมื่อเปิด real mode และมี Secrets ครบ ไม่ Backfill Snapshot เดิม

การจัดเองใน `MANUAL_HANDOFF` ที่หา Event เปิดเคสไม่ได้: Rollback งานจัดครั้งนั้น ตอบ `409` พร้อม `HANDOVER_SOURCE_UNAVAILABLE` และคงเคสไว้ให้ตรวจข้อมูล ไม่ใช่ Workflow Round ของ D11 ส่วนประวัติ `/me/handovers` ใช้ Cursor Pagination พร้อมตัวอ่านในหน้าพยาบาลแล้วในรอบ 6 PR P1 (ข้อ 9.8) ส่วน `GET /cases/{id}` คง List ของ Handover ตามเดิม

**รูปของ `content` (`HANDOVER_CONTENT_VERSION` = 1)** เวลาเป็น ISO 8601 พร้อม timezone แบบ API อื่น

| Key | ชนิด | ว่างได้ | ความหมาย |
|---|---|---|---|
| `version` | integer | ไม่ | เลขรูปข้อมูล ตอนนี้ 1 ตัวอ่านที่ไม่รู้จักเลขนี้แสดงเฉพาะ Key ที่รู้จัก |
| `shift` | object `{id, ward_id, ward_name, start_at, end_at}` | ไม่ | เวรที่มาแทน |
| `cover_start_at`, `cover_end_at` | datetime | ไม่ | ช่วงที่ต้องมาทำจริงของแถว Roster |
| `reason` | string (`HandoverReason`) | ไม่ | เหตุที่เวรขาดคนของเคส คิดจาก **Event ที่เปิดเคส** คือ Event แรกที่ผ่าน Threshold (`first_passed`) ซึ่ง **[ตรวจแล้ว]** `close_locked_window()` บันทึกไว้ใน `payload.event_id` ของ Audit `CASE_OPENED` ไม่ใช้ Event ที่ `id` น้อยที่สุด เพราะ Event ที่ไม่ผ่าน Threshold ก็ได้ `case_id` ด้วย (Q42) ค่าของ Handover จึงตรงกับแถว Audit: `STAFF_UNAVAILABLE` ที่ `payload.reason` = `NO_SHOW` → `NO_SHOW`, `STAFF_UNAVAILABLE` อื่น → `UNPLANNED_LEAVE`, Event ชนิดอื่นใช้ชื่อชนิด (`ASSIGNMENT_CANCELLED`, `PATIENT_SURGE`, `REQUIREMENT_CHANGED`) ไม่มี `PLANNED_LEAVE` เพราะไม่เปิดเคส ทุกทางที่สร้าง Handover ใช้ฟังก์ชันเดียวคิดค่านี้ เคสทุกเคสมี Event ที่เปิดเคสและตั้ง `case_id` แล้วเสมอ เพราะ **[ตรวจแล้ว]** เคสถูกเปิดตอนปิด Window เท่านั้น และ `close_locked_window()` ตั้ง `case_id` ให้ทุก Event ของ Window ใน Transaction เดียวกับที่สร้างเคส ก่อน Orchestrator เริ่มทำงาน ส่วน Handover ถูกสร้างทีหลังตอนจัดเวร ถ้าหา Event ไม่เจอ (ข้อมูลผิดปกติ) ถือเป็นความผิดพลาดของระบบตาม D11 ไม่เดาค่า |
| `patient_count` | integer | ใช่ | จำนวนผู้ป่วยของเวรตอนสร้าง |
| `requirement` | object `{roles: [{role_id, name, required_count}], skills: [{skill_id, name, required_count}]}` | ไม่ | Requirement ของเวรตอนสร้าง |
| `co_workers` | list ของ `{staff_id, name, role_name}` | ไม่ (List ว่างได้) | คนที่อยู่เวรด้วยกันตอนสร้างตามช่วงจริง ไม่รวมตัวผู้รับแทน และแถวต้นทางของคนใน Event ของเคสที่มีลิงก์ย้ายออกจริง (`transferred_from_assignment_id`) การมี Event อย่างเดียวไม่ซ่อนคนที่ยังทำงานอยู่ รวมแถวใหม่ที่กลับมาทำช่วงที่เหลือโดยไม่แสดงชื่อซ้ำ |
| `case_id` | integer | ไม่ | เคสที่ทำให้ได้เวร |

---


### 6.26 ผลสุดท้ายของข้อเสนอทาง LINE (Issue #98, หลังปิดรอบ 5)

หนึ่ง Offer (`outreach_id`) มีผลสุดท้ายได้หนึ่งรายการใน `OFFER_OUTCOME_NOTIFICATION` แยกจากการส่ง Offer เดิมและ Handover ยืนยันการได้เวร รอบ retry ของผู้สมัครเป็น Offer ใหม่จึงมีผลของตัวเอง ไม่ย้อนส่งผลของข้อมูลเก่าตอนอัปเกรด

| Audit ที่เป็นต้นเหตุ | ผลที่แจ้ง |
|---|---|
| `APPROVAL_REJECTED` | ไม่ได้รับอนุมัติ ไม่ใช้เหตุผลอิสระของหัวหน้าในข้อความ LINE |
| `APPROVAL_TIMEOUT` | หมดเวลารออนุมัติ แยกจากการปฏิเสธ |
| `OFFER_TIMEOUT` | หมดเวลาตอบรับ ทั้งผู้ตอบรับและ Job ใช้เส้นตายเดิม |
| `CASE_RESOLVED` ที่มี `cancelled_outreach_ids` | จัดคนครบ ยกเลิกเฉพาะ Offer ที่ระบุ รวมตัวสำรอง |
| `OFFER_CANCELLED_NOT_NEEDED` | ไม่ต้องการคนแทนเพิ่มเติมในช่วงนั้นแล้ว |
| `OFFER_CANCELLED_BY_ASSIGNMENT` หรือรายการยกเลิกของ Audit การจัด/ย้ายเวร | มีเวรอื่นขัดกัน |
| `TRANSFER_CHECK_FAILED` / `SAFETY_FAILED` | ย้ายไม่ได้ / ไม่ผ่านเงื่อนไขการจัดเวร |
| `MANUAL_HANDOFF` ที่มีรายการยกเลิก | หัวหน้าจะจัดคนต่อ |
| `WORKFLOW_FAILED` | คำขอที่อนุมัติครบแล้วแต่ไม่มีเวรได้ `EXECUTION_FAILED`: ยังยืนยันการจัดเวรไม่ได้; Offer อื่นที่ยังค้างได้ข้อความยกเลิกกลาง ไม่ใช่หัวหน้าปฏิเสธ |
| `CASE_CLOSED_UNRESOLVED` ที่มีรายการยกเลิก หรือเหตุผล `CANCELLED` | ข้อเสนอถูกยกเลิก ให้ติดต่อหัวหน้าหอ ไม่เดาสาเหตุ |

`audit_service.log()` เรียกตัวฉายผล `offer_outcome_service.prepare_audit()` หลัง flush Audit ใน Transaction เดียวกัน เขียนเฉพาะ Snapshot/Intent ไม่มี Network หรือ Commit ไม่เพิ่ม Workflow Lock ผู้เรียกถือ Lock ของ Offer ตามทางเดิมอยู่แล้ว Audit ที่ไม่ใช่ผลสุดท้ายไม่ทำอะไร จึงไม่ส่งเมื่ออนุมัติเพียงฝั่งเดียว และไม่ส่งซ้ำเมื่อพยาบาลปฏิเสธเอง (มี Reply เดิมแล้ว) Unique `(outreach_id, kind)` กันหลาย Audit สร้างหลายข้อความชนิดเดียวกัน การ Rollback รวม Savepoint ของ D11 ลบ Intent ในรอบที่ล้มด้วย ส่วนผลของผู้เรียกที่อยู่นอก Savepoint ยังคงอยู่

ข้อความระบุเลข Offer หอ วันและเวลาครอบคลุมจริงที่เสนอ (รวมวันที่ปลายทางข้ามคืน) และย้ำว่าไม่ได้รับมอบหมายจากข้อเสนอนี้ ไม่กล่าวว่าเวรอื่นถูกยกเลิก `CANCELLED` ใช้ข้อความกลาง ไม่เปิดเผย Error ภายในหรือเหตุผลอิสระ `EXECUTION_FAILED` ไม่กล่าวว่าหัวหน้าไม่อนุมัติ

ส่งหลัง Commit ผ่าน Background ของ Request หรือ Job เดิม แต่ละ sweep ส่งผลสุดท้ายได้สูงสุด 20 รายการ ใช้ Retry/Lease/Key เดิมของข้อ 6.16 Worker ล็อก Offer → Case → Staff ตาม helper เดิม แล้วล็อกแถว Notification; ไม่มี Lock/Transaction ค้างระหว่าง HTTP ตรวจความเหมาะสมก่อนส่ง ก่อน retry และหลังส่ง: ถ้ามี Handover ยืนยันการได้เวรของคนเดียวกันในเคสเดียวกันและช่วงทับกัน ให้หยุดข้อความล้มเหลวเป็น `CANCELLED` ไม่ใช้เกณฑ์ Handover ที่ต้อง `ASSIGNED` กับข้อความเหล่านี้ เพราะเป้าหมายคือ Offer ที่ถูกยกเลิก/หมดเวลา ไม่มี Binding ได้ `NO_CONTACT` โดยไม่มี Payload/Key/Attempt; unlink/rebind ไม่เปลี่ยนผู้รับของ Payload เดิม ไม่ Backfill เมื่อผูกบัญชีภายหลัง ส่งล้มเปลี่ยนเฉพาะ Notification ไม่เปลี่ยนเคส เวร หรือเขียน `OFFER_DELIVERY_FAILED`

`GET /me/offers` และ `/demo/line-sim/offers` เพิ่ม `final_outcome`, `final_message`, `final_delivery_status` (nullable) หน้าเว็บใช้แสดงผลได้แม้ไม่มี LINE และไม่แสดงข้อความล้มเหลวคู่กับการยืนยันได้เวร

**หมดเวลาทั้งสองทาง:** Job บันทึก `OFFER_TIMEOUT` แล้วส่งข้อความอัตโนมัติ (อาจช้าตามรอบ Job) ส่วนกด Accept หลังเส้นตายตอบทันทีว่า “ข้อเสนอนี้หมดเวลาตอบรับแล้ว จึงไม่สามารถรับข้อเสนอได้” ทั้งก่อนและหลัง Job บันทึก `TIMEOUT` โดยไม่เปลี่ยน DB ของ Offer ทางอ่าน/ตอบกลับยังไม่เขียนผลหมดเวลาเอง Dedup ของ Webhook คงเดิม

**สถานะตัวสำรอง:** เมื่อ Accept ให้บันทึก `accepted_as_reserve` จาก Gap และคำขอที่ค้างจริงใน Transaction ของคำตอบ ไม่ใช่ Target PRIMARY/RESERVE ของ Solver คำตอบทาง LINE อ่านสถานะหลัง Commit: ถ้าเป็นสำรองให้บอก “บันทึกการตอบรับแล้ว ขณะนี้คุณเป็นตัวสำรอง กรุณารอการยืนยันก่อนเข้าเวร” ถ้าเลื่อนขึ้นแล้ว Safety ผ่าน Audit `APPROVAL_REQUESTED` สร้าง Intent ชนิด `RESERVE_PROMOTED` พร้อมคำขอใน Transaction เดียวกัน ข้อความบอกกำลังรอหัวหน้าอนุมัติ ยังไม่ได้เวร Unique เปลี่ยนเป็น `(outreach_id, kind)` จึงมี Promotion หนึ่งครั้งและผล `FINAL` หนึ่งครั้งแยกกันได้ ก่อนส่ง/retry ต้องยังเป็น ACCEPTED มีคำขอ pending ที่ไม่หมดเวลา และเคสยังเดินอยู่ ได้เวรแล้ว/คำขอจบแล้ว/หมดเวลาแล้วหยุดข้อความ Promotion ไม่ส่งย้อนหลังตอน upgrade และ API ของผลสุดท้าย join เฉพาะ `kind = FINAL` เพื่อไม่ให้แถว Offer ซ้ำหรือแสดง Promotion เป็นผลล้มเหลว

**เมื่อ LINE ส่งล้ม:** บันทึกรหัสผลส่งแบบไม่เปิดเผย Payload/UID และ log เมื่อส่งจนจบเป็น FAILED หน้า Offer แสดงคำเตือนจาก `final_delivery_status` ว่า LINE ส่งไม่สำเร็จ พร้อมผลล่าสุด ไม่ปลอมว่าส่งสำเร็จ การส่งเป็น best effort ผ่าน retry เดิม 3 ครั้ง; เส้นตายใช้ Backend Clock เสมอ Demo หลัง reset เป็น frozen ต้องเลื่อนเวลา Demo การรอเวลาจริงไม่ทำให้เวลา Demo เดิน และการ retry ที่กำหนดเวลาใน Backend Clock ก็ต้องให้เวลานั้นเดินด้วย โหมดเวลาจริง Job ตรวจทุก 30 วินาที การแจ้งอัตโนมัติไม่ต้องรอผู้สมัครกดปุ่ม

Tests: `test_offer_outcome_notifications.py` (เหตุผล, ทางอนุมัติ/หมดเวลา, สองหอ, D11, Rollback, Retry, Binding, ข้อมูลเก่า, สอง Worker), `test_offer_outcome_migration.py`; `test_line_reserve_notifications.py` ทดสอบ Reply สำรอง, Promotion และเส้น HTTP Job/Demo ส่งหมดเวลาเอง (รวมส่งครั้งแรก TIMEOUT แล้ว Job retry โดยไม่มีการกดปุ่ม); frontend `lineSimRoster.test.tsx` ทดสอบผลสุดท้ายและการซ่อนข้อความเก่าเมื่อได้เวรแล้ว ต้องลอง LINE จริงแยกก่อนปิด Issue โดยใช้ด่าน Tunnel เดิม ไม่เปิด Route ใหม่


### 6.27 การเรียก LLM: ผู้ใช้กดขอ โควตา และบันทึกการเรียก [รอบ 6 · PR E1, E2, S]

รอบ 3 สร้างคำอธิบายอันดับอัตโนมัติทุก Plan (ข้อ 6.15) รอบ 6 เปลี่ยนเป็นให้ผู้ใช้กดขอ เพราะการเรียก Bedrock คิดเงินและมีเพดานรายวัน (R6-Q6, R6-Q19)

**ผู้ใช้กดขอคำอธิบายอันดับ (R6-Q19)**

1. หลัง Ranking ไม่เรียก LLM อัตโนมัติ หน้า Ranking แสดงอันดับ คะแนน และข้อมูลประกอบจากระบบตามปกติ การจัดเวรและการอนุมัติไม่รอ LLM `optimize.handle()` เลิกเรียก `explanation_service.enqueue()` (E1)
2. กด "หน้าสรุปด้วย AI" จึงสร้างคำอธิบายของ Plan นั้น ถ้ายังไม่มีผล ระบบสร้างแถว `PENDING` ให้ Job เรียก LLM แล้วบันทึกข้อความลงฐานข้อมูล Route ที่รับคำขอตอบทันที ไม่เรียก Bedrock ใน Request นั้น
3. สร้างสำเร็จครั้งเดียวต่อ Plan เคยสร้างแล้วแสดงข้อความเดิมเสมอ เปิดซ้ำ รีเฟรช หรือกดจากหลายหน้าต่างต้องไม่เรียกใหม่ กำลังสร้างอยู่แสดงสถานะกำลังดำเนินการและไม่สร้างงานซ้ำ (Unique `plan_id, prompt_version` เป็นด่านสุดท้ายเมื่อกดพร้อมกัน) Plan ใหม่จากการจัดอันดับใหม่ถือเป็นคนละรายการ ถ้า `PROMPT_VERSION` เปลี่ยนในอนาคต Plan เก่าที่มีคำอธิบายแล้วยังแสดงข้อความเดิม
4. เมื่อถึงเพดาน ปิดปุ่มสำหรับ Plan ที่ยังไม่มีคำอธิบาย พร้อมข้อความ "ใช้โควตาคำอธิบายจาก AI ครบแล้วในวันนี้ กรุณาลองใหม่ในวันถัดไป คุณยังดูอันดับและดำเนินการจัดเวรต่อได้ตามปกติ" Plan ที่มีคำอธิบายสำเร็จแล้วยังเปิดอ่านผลเดิมได้ เพราะไม่เรียก LLM และไม่ใช้โควตา
5. Backend ตรวจเพดานด้วย กันการเรียกผ่าน API และการกดพร้อมกันไม่ให้เกินเพดาน ตรวจสองจุด: ตอนรับคำขอ (ถึงเพดานแล้วปฏิเสธโดยไม่สร้างแถว) และตอนเรียกจริงของทุก Attempt (จองโควตาก่อนเรียก) นับทุก Attempt ที่เรียก Bedrock จริงรวม Retry ตามวัน Asia/Bangkok
6. ล้มเหลวแสดงสถานะตามจริง ไม่บันทึกข้อความแจ้งข้อผิดพลาดหรือข้อความถึงเพดานเป็นคำอธิบาย AI ที่สำเร็จ และไม่กระทบ Ranking การจัดเวร หรือการอนุมัติ

**ขอใหม่หลังล้มเหลวหรือถึงเพดาน (ตอบข้อค้างของ R6-Q19)** ใช้แถวเดิมของ Plan นั้นตาม Unique ที่มี ไม่สร้างแถวใหม่ เก็บประวัติ Attempt ใน `LLM_CALL_LOG` และห้ามล้างยอดโควตาหรือตัวนับ Attempt ของแถว (`LLM_MAX_ATTEMPTS_PER_ROW` ตลอดอายุของแถว)

* ถึงเพดาน: กดใหม่ได้เมื่อโควตาว่างหรือขึ้นวันใหม่ การปฏิเสธก่อนเรียก Bedrock ไม่ใช้โควตา
* ล้มเหลวชั่วคราว (`TIMEOUT`, `THROTTLED`, `SERVICE_ERROR`): ขอใหม่ได้ภายใต้เพดานรายวันและ `LLM_MAX_ATTEMPTS_PER_ROW` ห้ามกดเพื่อรีเซ็ตเพดาน Retry
* ข้อมูลหรือค่าตั้งไม่ถูกต้อง (`CONFIG_ERROR`, `INVALID_INPUT`, ไม่มี `LLM_MODEL_ID`): ต้องแก้สาเหตุก่อน ปุ่มไม่เปิด
* สร้างสำเร็จแล้ว (`READY`): อ่านผลเดิม ไม่เปิดให้สร้างซ้ำ
* **แถว `PENDING` ที่ค้างจากโค้ดเดิม:** Plan ที่สร้างก่อน E1 merge อาจมีแถว `PENDING` ที่เข้าคิวอัตโนมัติไว้แล้ว E1 ตั้งให้ผู้ใช้ต้องกดขอเอง (ข้อเสนอของร่างรอบ 6 ยังรอการยืนยันในรีวิว PR ของ E1) เพื่อให้กติกา "ไม่เรียกโดยไม่มีคนกด" ไม่มีข้อยกเว้น

**สรุปสถานการณ์ของเคส (R6-Q9 ก, R6-Q10 ก, ผู้ใช้กดขอ)** สรุปของเคสหนึ่งเคสให้ Head Nurse อ่านในหน้า `cases/[id]` อ่านอย่างเดียว ไม่ใช่ข้อความที่ส่งหาพยาบาล ไม่มีผลต่อ Gap, Wave, Safety หรือการอนุมัติ

* ใช้กติกา "ผู้ใช้กดขอ" ข้างบนทุกข้อ และเพดานรวมเดียวกับคำอธิบายอันดับ
* ผูกกับ Snapshot ของข้อมูล: `input_hash` = SHA-256 ของ JSON แบบ Canonical (`sort_keys`, ไม่มีช่องว่าง) ของ Payload ที่สรุป ตารางสรุปมี Unique `case_id, input_hash, prompt_version` ข้อมูลเดิมแสดงผลเดิมโดยไม่เรียก LLM ข้อมูลเปลี่ยนแสดงว่าฉบับนี้ล้าสมัยและเปิดปุ่มสร้างฉบับใหม่ ฉบับเก่าเก็บเป็นประวัติ ไม่ถูกเขียนทับ Payload ต้องคำนวณจาก DB ล้วนและเหมือนเดิมทุกครั้งเมื่อข้อมูลไม่เปลี่ยน ไม่มีเวลาปัจจุบันหรือเลขสุ่มปนอยู่
* Payload ไม่มี `staff_id`, ชื่อ หรือ LINE ID (กติกาเดียวกับข้อ 6.15) ผลต้องผ่านตัวตรวจรูปแบบและตัวตรวจตัวเลขของข้อ 6.28
* เก็บ `PENDING` ใน Transaction ของการขอ ประมวลผลภายหลัง ล้มแล้วเคสไม่ล้ม (ข้อ 6.25 แนวทางของรอบ 6) และบันทึกการเรียกใช้ `LLM_CALL_LOG` ที่ `work_type = CASE_SUMMARY`
* Migration ของตารางสรุปเคสอยู่ใน PR S ส่วน schema ของ `LLM_CALL_LOG` อยู่ใน B1 (ข้างล่าง)

**บันทึกการเรียกและตัวห่อการเรียก (PR B1 ทำแล้ว รูปที่ทำจริงอยู่ในหัวข้อ "ที่ B1 ทำ" ข้างล่าง)**

* `LLM_CALL_LOG.explanation_id` เป็น `NOT NULL` อ้าง `RANK_EXPLANATION` (พร้อม `case_id` และ `plan_id` ที่ `NOT NULL`) สรุปเคสและชุดทดลองจึงบันทึกด้วยโครงสร้างเดิมไม่ได้ และ `llm_service.generate_explanation()` เรียกตัวเชื่อมอย่างเดียว ไม่เขียนบันทึกและไม่จองโควตา
* Migration ของ B1: เพิ่ม `work_type` (`LlmWorkType`: `RANK_EXPLANATION`, `CASE_SUMMARY`, `MODEL_TRIAL` แถวเดิมทั้งหมดเป็น `RANK_EXPLANATION`) ทำให้ `explanation_id`, `case_id`, `plan_id` เป็น NULL ได้ เพิ่ม `subject_id` (รหัสแถวสรุปเคส ไม่มี FK) กับ `trial_run_id` และ `trial_case_key` และ CHECK ตามชนิด: `RANK_EXPLANATION` ต้องมี `explanation_id`, `case_id`, `plan_id`; `CASE_SUMMARY` ต้องมี `subject_id` และ `case_id`; `MODEL_TRIAL` ต้องมี `trial_run_id` และ `trial_case_key` และไม่มี `case_id`/`plan_id` Unique เดิม (`explanation_id, attempt`) คงไว้ และเพิ่ม Unique บางส่วนของแต่ละชนิดที่เหลือ
* ตารางตัวนับสองตาราง (รีวิว PR #105 ข้อ 1): (ก) `LLM_DAILY_USAGE` เฉพาะขอบเขต `DEMO` คีย์วัน Asia/Bangkok กับจำนวนที่ใช้ รีเซ็ตเองเมื่อขึ้นวันใหม่เพราะเป็นแถวใหม่ (ข) `LLM_TRIAL_USAGE` เฉพาะขอบเขต `TRIAL` คีย์ `trial_run_id` อย่างเดียว **ไม่มีวันในคีย์** เก็บ `cap` ที่ตั้งตอนสร้างชุดทดลอง (จากสูตร `LLM_TRIAL_CALL_CAP`) และ `used` สะสมตลอดชุดทดลอง จึงไม่ถูกต่อเพดานใหม่เมื่อข้ามเที่ยงคืนหรือรีสตาร์ต และเรียกซ้ำพร้อมเพดานที่ใหญ่กว่าก็แก้เพดานของชุดที่สร้างไปแล้วไม่ได้ ทั้งสองจองด้วยคำสั่งเดียวที่ตรวจเพดานในเงื่อนไข: ของ `DEMO` แบบ `INSERT ... ON CONFLICT DO UPDATE SET used = used + 1 WHERE used < :cap RETURNING used` ของ `TRIAL` แบบ `UPDATE LLM_TRIAL_USAGE SET used = used + 1 WHERE trial_run_id = :id AND used < cap RETURNING used` เพื่อไม่ให้ Worker พร้อมกันเกินเพดาน
* ตัวห่อการเรียกตัวเดียว (ชื่อชั่วคราว `llm_gateway.call()`): (ก) จองโควตาของขอบเขตนั้น (`LLM_DAILY_USAGE` หรือ `LLM_TRIAL_USAGE`) และ commit (ถ้าจองไม่ได้ คืนผล "ถึงเพดาน" โดยไม่เรียกตัวเชื่อมและไม่ใช้โควตา) (ข) เขียนแถวบันทึก `IN_FLIGHT` และ **commit ก่อนเรียกเครือข่าย** (ค) เรียก `llm_service.generate_explanation()` **โดยไม่มี Transaction หรือ Lock ค้างของฐานข้อมูลระหว่างรอ Bedrock** (Session ปิดหรืออยู่ในสถานะไม่มี Transaction ก่อนเรียก เหมือน `_process_one` ที่ `db.rollback()` และ commit ใน `_start_attempt` ก่อน `_call` อยู่แล้ว) (ง) เปิด Transaction ใหม่ อัปเดตแถวด้วยผล token และค่าใช้จ่าย ถ้าเครื่องล่มหลัง (ข) แถว `IN_FLIGHT` ค้างและยอดโควตาที่จองไว้ยังนับ (ไม่คืน) ทุก Attempt ผ่านตัวห่อนี้ รวม Retry ผู้เรียกถือหน้าที่ลองซ้ำเอง
* ขอบเขตของชุดทดลอง: ตัวห่อรับขอบเขต `DEMO` จากโค้ดของ Route ผู้ใช้เท่านั้น ขอบเขต `TRIAL` กำหนดได้จากสคริปต์ภายในที่ส่งรหัสชุดทดลอง เพดานของชุดตั้งตอนสร้างแถวใน `LLM_TRIAL_USAGE` ครั้งเดียว ไม่มี Route หรือพารามิเตอร์ของผู้ใช้ที่เลือกขอบเขตหรือเพดานได้
* ค่าใช้จ่ายรวม: ผลรวม `estimated_cost_usd` ทุก `work_type` ในเดือนเดียวกัน เทียบ `LLM_MONTHLY_BUDGET_USD` (Dashboard แสดง ข้อ 6.31)

**ตัวประมวลผลเดิมและ `LLM_ENABLED` (รีวิวรอบสองของ PR #104)**

* ตัวประมวลผลเดิมของ `explanation_service` (`run_pending`, `_process_one`, `_start_attempt`, `_call`, `_record`) เรียกตัวเชื่อมและเขียน `LLM_CALL_LOG` เอง ไม่ผ่านตัวนับ และเริ่มทำงานทันทีเมื่อ `LLM_ENABLED=true` (`run_pending` ตรวจแค่ `llm_enabled` กับ `llm_ready`) B1 แปลงให้เรียกผ่านตัวห่อ เพื่อไม่ให้มีทางเรียกตัวเชื่อม LLM นอกตัวห่อตั้งแต่ B1 merge เมื่อถึงเพดาน แถวที่ถึงตาประมวลผลไม่ถูกเรียกและไม่ใช้โควตา (ข้อเสนอ: ตั้งเป็น `SKIPPED` เหตุ `QUOTA_EXHAUSTED` ซึ่ง E1 ใช้เป็นสถานะ "ถึงเพดาน")
* `LLM_ENABLED=true` ห้ามตั้งบนเครื่อง AWS จนกว่า E1 merge เพราะก่อนหน้านั้นการเข้าคิวยังเป็นอัตโนมัติ ขัดกับกติกาข้างบน แม้จะผ่านตัวห่อและมีเพดานแล้ว ชุดทดลอง (B2) เรียกจากสคริปต์ภายในผ่านตัวห่อ ไม่ต้องตั้ง `LLM_ENABLED`

**ที่ B1 ทำ (โค้ดเป็นหลักถ้าไม่ตรงกับข้อความข้างบน)**

* **ตัวห่อ** `app/services/llm_gateway.py` เป็นที่เดียวที่เรียก `llm_service.generate_explanation()` (Test อ่านโค้ดทั้ง `app/` ด้วย AST) แบ่งสองขั้น: `start(db, request, subject)` ใน Transaction ของผู้เรียก ตรวจเหตุปฏิเสธ จองโควตาด้วยคำสั่งเดียว และเพิ่มแถว `IN_FLIGHT` ผู้เรียก commit เอง จึงล็อกแถวของตัวเอง (เช่น `RANK_EXPLANATION`) และนับ Attempt ใน Transaction เดียวกับการจองได้ `send(db, ticket)` ปฏิเสธถ้า Session ยังมี Transaction ค้าง เรียกตัวเชื่อม แล้วบันทึกผลใน Transaction ใหม่และ commit ส่วน `call()` ทำสองขั้นต่อกันสำหรับผู้เรียกที่ไม่มีแถวของตัวเอง (สคริปต์ชุดทดลอง) การจองกับแถว `IN_FLIGHT` อยู่ใน Transaction เดียวกัน จึงไม่มีโควตาที่ถูกจองโดยไม่มีแถวบันทึก
* **ขอบเขตตาม `work_type`** ผู้เรียกไม่เลือกขอบเขตหรือเพดานเอง: `MODEL_TRIAL` ใช้ `LLM_TRIAL_USAGE` ของรหัสชุดนั้น ชนิดอื่นใช้ `LLM_DAILY_USAGE` สร้าง `Subject` ด้วย `rank_explanation()`, `case_summary()` หรือ `model_trial()` `trial_case_key` ระบุคู่เคสกับโมเดลหนึ่งคู่ในชุด (เช่น `case-07/nova-lite`) ชุดทดลองสร้างตัวนับด้วย `create_trial_run(db, run_id, cap)` ครั้งเดียว เรียกซ้ำได้แถวเดิมโดยเพดานไม่เปลี่ยน และเพดานเกิน `LLM_TRIAL_CALL_CAP` ไม่ได้ รหัสชุดที่ไม่ได้สร้างไว้ถือว่าไม่มีโควตา
* **เหตุปฏิเสธ** (`LlmRefusal` ไม่เรียก ไม่เขียนบันทึก ไม่ใช้โควตา): `DISABLED` (งานขอบเขต `DEMO` ขณะ `LLM_ENABLED=false`), `NOT_CONFIGURED` (`bedrock` ไม่มี `LLM_MODEL_ID` หรือ `AWS_REGION`), `INPUT_TOO_LARGE`, `QUOTA_EXHAUSTED` ตัวประมวลผลคำอธิบายตั้งแถวเป็น `SKIPPED` พร้อมเหตุ `QUOTA_EXHAUSTED` หรือ `INPUT_TOO_LARGE` และปล่อยแถวไว้ `PENDING` ให้รอบถัดไปถ้าเป็นสองเหตุแรก (ค่าตั้งเปลี่ยนกลาง Sweep)
* **วันของโควตา DEMO** คิดจากเวลาจริงของฐานข้อมูล (`clock_timestamp()`) ใน `LLM_QUOTA_TIMEZONE` ไม่ใช่ Demo Clock เป็นข้อยกเว้นของ D10 แบบเดียวกับ Lease ในข้อ 6.15 เพราะถ้าตาม Demo Clock การเลื่อนนาฬิกา Demo จะต่อโควตาและใช้เงินเพิ่มได้ `demo_quota_left(db)` อ่านโควตาที่เหลือ (ไม่จอง) ให้ E1 ใช้ตอนรับคำขอ
* **นับทุก Attempt ที่ส่งผ่านตัวห่อ รวม `fake`** เพื่อให้เพดานทำงานเหมือนกันตอนทดสอบโดยไม่มี Bedrock
* **เพดาน Input** ยังไม่ได้นับ token จริงก่อนส่ง ใช้ค่าประมาณ 1 token ต่อ 3 byte ของ UTF-8 (System + Prompt) ซึ่งนับเกินสำหรับ JSON และอังกฤษ และนับอักษรไทยหนึ่งตัวเป็นหนึ่ง token Prompt ของ Plan ที่มีผู้สมัคร 10 คนยาวราว 5,700 byte หรือราว 1,900 token ตามค่าประมาณ จำนวนจริงอยู่ใน `input_tokens` ให้ B2 ตรวจค่าประมาณกับของจริง **เพดาน Output** ตัวห่อลด `max_output_tokens` ของทุกคำขอให้ไม่เกิน `LLM_MAX_OUTPUT_TOKENS`
* **ค่าใช้จ่ายรวม** `spend(db, start_at=, end_at=)` รวม `estimated_cost_usd` ทุก `work_type` ในช่วงเวลา และนับแถวที่ไม่ทราบค่าใช้จ่ายแยก F1 เลือกขอบเขตของเดือนเอง
* **Demo reset ไม่ล้างบัญชีการเรียก LLM** (รีวิว PR #108 ข้อ 1) `reset_demo()` เก็บ `LLM_DAILY_USAGE`, `LLM_TRIAL_USAGE` และ `LLM_CALL_LOG` ไว้ในตารางชั่วคราวก่อนลบ Schema แล้วใส่คืนหลังโหลด Golden Case ทั้งหมดใน Transaction เดียว (Alembic รันบน Connection เดียวกัน) โควตาที่ใช้ไปของวันจริงและเพดานของชุดทดลองจึงไม่ถูกต่อใหม่ และค่าใช้จ่ายไม่หาย แถวบันทึกของคำอธิบายอันดับและสรุปเคสเสียตัวอ้างอิง (`explanation_id`, `case_id`, `plan_id`, `subject_id` เป็น NULL เพราะเลขรหัสเริ่มใหม่หลัง reset) และได้ `detached_at` เป็นเวลาที่ reset ครั้งแรก แถวชุดทดลองคงเดิม `id` ของแถวคงเดิมและ sequence ต่อจากค่าสูงสุด reset ที่ล้มกลางทาง rollback ทั้งหมด DB เดิมไม่เปลี่ยน **ล็อกตารางบัญชีตลอด reset** (รีวิว PR #108 รอบสอง): `LOCK TABLE` แบบ `ACCESS EXCLUSIVE` บน `LLM_DAILY_USAGE`, `LLM_TRIAL_USAGE`, `LLM_CALL_LOG` (ลำดับเดียวกับที่ตัวห่อล็อก) ก่อนคัดลอกและถือจนจบ Transaction การเขียนที่ค้างอยู่จึงอยู่ในสำเนา การเขียนที่มาระหว่าง reset รอแล้วลงตารางใหม่ ไม่ถูกสำเนาทับ ผลของ Attempt ที่ส่งไปแล้วและบันทึกหลัง reset ลงแถวเดิมได้เพราะ `id` คงเดิม ถ้าการเขียนที่ถือล็อกตารางอื่นอยู่ชนกับ `DROP` จน PostgreSQL ยุติฝั่งใดฝั่งหนึ่ง (deadlock) reset เริ่มใหม่ไม่เกิน 3 ครั้ง **ฐานข้อมูลก่อน B1:** ถ้า reset ตอน Migration ยังเป็น `c5f8b0d3e7a1` แถวบันทึกเดิมทุกแถวถือเป็น `RANK_EXPLANATION` และถูก `detached_at` เหมือนกัน ตัวนับไม่มีของเดิมให้เก็บ จึงไม่นับ Attempt เก่าเข้าโควตาของวัน
* **`LLM_QUOTA_TIMEZONE` ตรวจตอนเริ่มระบบ** ด้วย `zoneinfo` (รีวิว PR #108) ชื่อเขตเวลาที่ไม่รู้จักทำให้โหลดค่าตั้งไม่ผ่าน แทนที่จะล้มตอนจองโควตาครั้งแรก Backend พึ่งแพ็กเกจ `tzdata` จึงไม่ต้องมีไฟล์เขตเวลาของระบบปฏิบัติการ
* **ค่าตั้ง** `settings.llm_daily_call_cap`, `llm_quota_timezone`, `llm_monthly_budget_usd`, `llm_max_input_tokens`, `llm_max_attempts_per_row`, `llm_trial_call_cap` อ่านจาก Environment ชื่อเดียวกับค่าคงที่ ค่าว่างใช้ค่าเริ่มต้นใน `core/constants.py` ตัวประมวลผลคำอธิบายจำกัด Attempt ของแถวที่ `min(1 + LLM_MAX_RETRIES, LLM_MAX_ATTEMPTS_PER_ROW)` E1 แยกสองค่านี้เมื่อเปิดให้ขอใหม่

**ค่าเริ่มต้น** ใน `core/constants.py`: `LLM_DAILY_CALL_CAP` = 100, `LLM_QUOTA_TIMEZONE` = `Asia/Bangkok`, `LLM_MONTHLY_BUDGET_USD` = 20, `LLM_MAX_INPUT_TOKENS` = 5,000, `LLM_MAX_ATTEMPTS_PER_ROW` = 4, `LLM_TRIAL_CALL_CAP` = 180 B1 อ่านเข้าค่าตั้งให้ปรับได้โดยไม่ต้อง release

### 6.28 Bedrock จริงและการเลือกโมเดล [รอบ 6 · PR B2]

* **เพดานสองชั้น (R6-Q6 ก):** (1) เพดานในแอป `LLM_DAILY_CALL_CAP` ต่อวันรวมทั้งทีม นับทุก Attempt ที่เรียก Bedrock จริงรวม Retry ใช้วัน Asia/Bangkok เก็บตัวนับในฐานข้อมูล (ข้อ 6.27) (2) AWS Budget Alert เฉพาะ Bedrock 20 USD ต่อเดือน Budget Alert ของผู้จัดการแข่งขันครอบคลุมงบเฉพาะ Bedrock และทีมได้รับแจ้งเตือน (ทีมยืนยันแล้ว) Budget Alert เป็นการเตือน ไม่ตัดการเรียกทันที
* **บัญชีและวงเงิน (R6-Q5):** บัญชี AWS ผู้จัดการแข่งขันจัดให้เป็นของทีม วงเงิน 350 USD เป็นเครดิตรวมตลอดโครงการ เปิดเครื่องเฉพาะช่วงทดสอบและ Demo
* **ที่มาของตัวเลข:** ราคา **ตรวจแล้ว 2026-10-17 กับ AWS Price List ของ Bedrock (ข้อมูลเผยแพร่ 2026-10-16 21:08 UTC, Region Asia Pacific (Singapore), ระดับ Standard)** Amazon Nova 2 Lite: Input 0.00041 USD ต่อ 1,000 token (0.41 ต่อล้าน) และ Output 0.00339 USD ต่อ 1,000 token (3.39 ต่อล้าน) ตรงกับตัวเลขที่ทีมให้มา 100 ครั้งมาจากสมมติฐานสามคน คนละ 15 เคสต่อวัน เคสละสองครั้งรวม Retry = 90 ปัดเป็น 100 (ไม่ใช่ปริมาณที่วัดได้) ราคาต่อครั้งที่ Input 5,000 และ Output 1,024 token ของโมเดลอื่นใน Singapore (Standard, ตรวจด้วยโค้ด): Nova Micro 0.00042751, Nova Lite 0.00073678, Nova 2 Omni (ข้อความ) 0.0054816, Nova 2 Lite 0.00552136, Nova Pro 0.00982368 และ Nova 2 Pro (ข้อความ) 0.02233544 USD ถ้ามี reasoning ต้องนับ token ที่คิดเงินส่วนนั้นเพิ่ม (ยังไม่ได้ตรวจว่า Price List นับ reasoning เป็น Output อย่างไร หน้าราคาของ AWS ระบุเฉพาะตัวอย่าง DeepSeek-R1 ว่านับรวมใน Output) หลังลองจริงต้องตรวจจำนวน token ค่าใช้จ่าย และความเพียงพอของโควตา แล้วปรับก่อน Demo
* **ขนาดต่อคำขอ:** จำนวนคำขออย่างเดียวจำกัดค่าใช้จ่ายไม่ได้ จึงมีเพดาน Input `LLM_MAX_INPUT_TOKENS` (Payload ที่เกินไม่ถูกส่ง) และเพดาน Output `LLM_MAX_OUTPUT_TOKENS` (ค่าเริ่มต้น 1,024) ถ้าโมเดลที่เลือกใช้ reasoning ต้องนับ token ที่คิดเงินส่วนนั้นในการประเมินด้วย
* **ตัวตรวจตัวเลขในประโยค (R6-Q8 ก):** ทุกตัวเลขในประโยค (ทั้งคำอธิบายอันดับและสรุปเคส) ต้องอยู่ในชุดตัวเลขของ Payload รวมเลขอันดับใน "อันดับ N" ไม่ตรงบันทึกเป็น `INVALID_OUTPUT` และไม่แสดงประโยค ห้าม LLM คำนวณผลรวมหรือค่าใหม่ ตัวตรวจต้องจัดการเลขไทย ทศนิยม และเครื่องหมายคั่น หน้าเว็บแสดงตัวเลขจริงจาก DB ตามปกติ B1 ทำที่ `app/domain/llm_numbers.py` และเรียกใน `llm_service.generate_explanation()` จึงตรวจทุก `work_type` ชุดตัวเลขของ Payload คือตัวเลขในค่าทุกตัว (รวมตัวเลขในข้อความ ไม่อ่านชื่อ key) ไม่สนเครื่องหมายลบ (ขีดใน "อันดับ 1-3" ไม่ใช่ลบ) ทศนิยมในประโยคตรงได้ถ้าเท่ากับค่าใน Payload ที่ปัดเป็นจำนวนตำแหน่งที่เขียน (0.33 ตรงกับ 0.333...) จำนวนเต็มต้องตรงพอดี (3 ไม่แทน 2.5) อ่านตัวเลขทั้งก้อน ไม่แยกเป็นชิ้น (รีวิว PR #108 ข้อ 2): รูปที่ตรวจไม่ได้นับว่าไม่ตรงเสมอ ได้แก่ `.5`, `1e3`, `5k`, `1/2`, `1,2`, `1.2.5` และอักขระตัวเลขที่ไม่ใช่หลัก (`½`, `²`) จุดหรือจุลภาคท้ายตัวเลขถือเป็นเครื่องหมายจบประโยคหรือคั่นรายการ แถวบันทึกมี `error_type = UNVERIFIED_NUMBER` เพื่อแยกจากรูปแบบผิด
* **เกณฑ์เลือกโมเดล (R6-Q7 ก) ตายตัวก่อนลอง:** ผ่านครบสี่ข้อ (1) ตัวตรวจรูปแบบทุกเคส (2) ตัวเลขตรง Payload ทุกเคส (3) ไม่อ้างชื่อหรือรหัสบุคคล เรียกคนว่า "อันดับ N" เท่านั้น (4) ค่าใช้จ่ายต่อครั้งที่ Input เต็มเพดาน (5,000 token) และ Output เต็มเพดาน (1,024 token) ต้องไม่เกิน (`LLM_MONTHLY_BUDGET_USD` − เพดานค่าใช้จ่ายของชุดทดลอง) ÷ (`LLM_DAILY_CALL_CAP` × 30) เพื่อให้ใช้โควตา Demo เต็มทุกวันทั้งเดือนแล้วยังอยู่ในงบ ที่ชุดทดลองราว 0.99 USD ได้ราว 0.00634 USD ต่อครั้ง (ตรวจด้วยโค้ด) ตามนี้ Nova Pro (0.00982) และ Nova 2 Pro (0.02234) ตกข้อ 4 ทันทีที่ใช้โควตาเต็ม เลือกตัวที่ถูกสุดที่ผ่านครบ ถ้าไม่มีตัวไหนผ่าน ห้ามลดเกณฑ์ ให้แก้ Prompt เป็นเวอร์ชันใหม่แล้วรันทั้งชุดใหม่ หรือใช้ `fake` ต่อ
* **ตัวกัน Test (R6-Q15 ก):** B1 เพิ่มตัวกัน `isolated_llm` ใน `tests/conftest.py` แบบเดียวกับ `isolated_line` ของ L5: ตั้ง `LLM_PROVIDER=fake` และ `LLM_ENABLED=false` ทุก Test และ `pytest.fail()` เมื่อ botocore ส่งคำขอไปที่ Endpoint ของ Bedrock (`Endpoint.make_request`) แม้ `.env` ของผู้พัฒนาตั้งค่าจริง `Stubber` ตอบก่อนถึงจุดนั้น Test ของ `bedrock` adapter จึงไม่ต้องปิดตัวกัน (เข้มกว่าที่ร่างเขียนไว้: ตัวกันเปิดอยู่ทุก Test)

**ขั้นตอนเลือกโมเดล (B1 แล้ว B2)**

1. เตรียมก่อนเรียกจริงครั้งแรก: คน 2 แจ้งว่าเครดิตและสิทธิ์โมเดลใน Region ใช้ได้ (ค้างจาก R5-Q2) ตั้ง Budget Alert และเพดานในแอป ใส่ตัวกัน Test เครื่อง AWS ผ่านขั้นที่ 6 (ข้อ 6.30) แล้ว คน 2 จึงลองด้วย IAM Role ของเครื่อง (อนุญาต `bedrock:InvokeModel` เฉพาะโมเดลที่เลือก) **ข้อสังเกตจาก Price List (ยังไม่ได้ยืนยันกับเอกสาร Bedrock):** ใน Singapore SKU ของตระกูล Nova 2 (Lite, Omni, Pro) มีคำว่า `cross-region-global` ส่วน Nova Micro, Lite และ Pro รุ่นแรกไม่มี หมายความว่า Nova 2 ใน Singapore น่าจะเรียกผ่าน inference profile แบบข้าม Region ซึ่งทำให้ (ก) ชื่อโมเดลที่ตั้งใน `LLM_MODEL_ID` เป็นรหัส inference profile (ข) IAM Role ต้องอนุญาตทั้ง inference profile และโมเดลใน Region ปลายทางที่โปรไฟล์ใช้ และ (ค) ข้อมูลอาจถูกประมวลผลนอก Singapore คน 2 ยืนยันสามข้อนี้กับเอกสาร Bedrock ก่อนเขียนนโยบาย IAM
2. เขียนเกณฑ์ลงเอกสารก่อนลอง: เกณฑ์สี่ข้อ ชื่อโมเดล 2 ถึง 3 ตัวที่เปิดสิทธิ์แล้ว งบรวมของการลอง และเพดานค่าใช้จ่ายต่อ Plan เขียนก่อนเห็นผล (ในไฟล์นี้หรือ Description ของ B2 ก่อนลอง)
3. ทำชุดเคส 20 ถึง 30 เคสแล้วตรึงไว้: สร้าง Payload จาก `explanation_service.build_payload()` เก็บเป็นไฟล์เดียวพร้อม `input_hash` ทุกโมเดลได้ข้อมูลเข้าเหมือนกัน ให้หลากหลาย: Plan ปกติ, `partial_plan`, ผู้สมัครเกิน 10 คน, ผู้สมัครคนเดียว, คะแนนเท่ากันจนต้องดู `ranking_key` ถ้า Seed ไม่ครบทุกแบบให้สร้างเคสสังเคราะห์เพิ่ม
4. สคริปต์รันและบันทึกผล: ต่อโมเดลต่อเคส ใช้ `render_prompt()` แล้วเรียกผ่านตัวห่อของ B1 (ขอบเขต `TRIAL`) เก็บสถานะ ข้อความ token และเวลาตอบ เก็บผลดิบไว้นอก repo สรุปลง Description ของ PR
5. วัดด้วยโค้ดทั้งหมด: ข้อ 1 นับ `SUCCEEDED` เทียบ `INVALID_OUTPUT`; ข้อ 2 ดึงตัวเลขด้วย regex เทียบกับชุดตัวเลขของ Payload; ข้อ 3 ค้นชื่อ รหัสพนักงาน หรือ LINE ID ของคนในเคสนั้น; ข้อ 4 คำนวณจาก `LLM_CALL_LOG` ด้วยราคา `LLM_INPUT_PRICE_PER_MTOK_USD` และ `LLM_OUTPUT_PRICE_PER_MTOK_USD` วัดเพิ่มแต่ไม่ใช่เกณฑ์ตัดสิน: เวลาตอบเทียบ timeout 15 วินาที
6. เพดานของชุดทดลอง: แยกโควตาจากผู้ใช้ Demo แต่มีเพดานของตัวเอง `LLM_TRIAL_CALL_CAP` (เคส × โมเดล × Attempt เริ่มต้น 30 × 3 × 2 = 180) **เป็นเพดานสะสมของทั้งชุดทดลอง ไม่ใช่ต่อวัน** เก็บใน `LLM_TRIAL_USAGE` ตาม `trial_run_id` (ข้อ 6.27) ชุดที่ทำข้ามเที่ยงคืนหรือรีสตาร์ตกลางทางจึงใช้เพดานเดิมต่อ เขียนเป็นสูตรก่อนเริ่ม ค่าใช้จ่ายรวมในงบ 20 USD เดียวกัน (เครดิต AWS ก้อนเดียวกัน) เต็มโควตา Demo ทั้งเดือน 16.56 USD เหลือให้ชุดทดลองราว 3.44 USD ที่ราคาข้างบน ถ้าผลรวมเกิน ต้องปรับเพดาน Demo หรือเพิ่มงบก่อนเริ่ม
7. ตัดสิน: ทำตารางโมเดลคูณเกณฑ์ ตัดตัวที่ตกข้อใดข้อหนึ่ง เลือกตัวที่ถูกสุดที่เหลือ
8. ตั้งค่าและบันทึก: ตั้ง `LLM_MODEL_ID`, `AWS_REGION` และราคาบนเครื่องเท่านั้น ไม่ใส่ใน repo เขียนผลและค่าใช้จ่ายจริงลง Description ของ B2 และตาราง fake กับของจริง Test ยังใช้ `fake` ส่วน `LLM_ENABLED=true` ตั้งหลัง E1 merge

20 ถึง 30 เคสคัดตัวที่พลาดบ่อยออกได้ แต่พิสูจน์ไม่ได้ว่าโมเดลไม่เคยพลาด ความเสี่ยงที่เหลือกันด้วยตัวตรวจตัวเลขในโค้ดซึ่งทำงานทุกครั้งที่ระบบเรียกจริง ไม่มี AWS key ใน repo, `.env.example`, Log หรือ Description Bedrock ใช้ IAM Role ของเครื่อง

### 6.29 ข้อความอิสระของพยาบาลใน LINE (PR I ทำแล้ว)

ข้อตกลง R6-Q11 ค และ R6-Q12: **ไม่ใช้ LLM** งาน "LLM ตีความคำตอบอิสระ" ของแผนเดิมเหลือเป็นตัวตอบกลับแบบกำหนดไว้

* ข้อความส่วนตัว LINE ที่ไม่ใช่ `LINK`, `CHECKIN` หรือปุ่ม (รวมรูปภาพและสติกเกอร์) ตอบตามสถานะของผู้ส่ง โดยไม่ตีความข้อความ (ทีมปรับขอบเขต PR I):
  1. ยังไม่มี Binding ที่ใช้งานได้: “สวัสดีค่ะ กรุณาผูกบัญชี LINE กับ Nara ก่อนใช้งาน โดยขอรหัสผูกบัญชีจากผู้ดูแล แล้วส่งข้อความ LINK <รหัสที่ได้รับ> มาที่แชตนี้ค่ะ”
  2. มี Offer ที่ `can_accept` หรือ `can_reject` เป็นจริงตาม `outreach_service.list_offers()`: “หากต้องการตอบข้อเสนอเข้าเวร กรุณากดปุ่มในข้อความข้อเสนอที่ยังตอบได้ เพื่อบันทึกคำตอบ การพิมพ์แชตยังไม่ถือเป็นการตอบข้อเสนอค่ะ” ไม่บอกให้รับข้อเสนอที่ถูกพักเพราะรอเคสอื่น
  3. ไม่มี Offer ที่ตอบได้ แต่มี Offer ACCEPTED ของเคสที่ยังเดินอยู่ ยังไม่ได้เวรและไม่มีผลสุดท้าย (รวมตัวสำรอง): “ระบบบันทึกการตอบรับของคุณแล้ว ขณะนี้อยู่ระหว่างรอผล กรุณารอการแจ้งยืนยันก่อนเข้าเวรค่ะ”
  4. ไม่มีรายการข้างต้น: “สวัสดีค่ะ นี่คือระบบแจ้งเตือนเวรของ Nara ขณะนี้คุณไม่มีข้อเสนอเข้าเวรที่รอดำเนินการ หากต้องการความช่วยเหลือ กรุณาติดต่อหัวหน้าหอค่ะ” ไม่กล่าวว่าไม่มีเวรที่ได้รับมอบหมาย
* ใช้ Binding ของผู้ส่งเท่านั้น ไม่เปิดเผยข้อมูลของพยาบาลคนอื่น อ่านสถานะก่อน Commit Dedup แล้วตอบหลัง Commit ไม่มี Transaction ค้างระหว่าง Reply
* ไม่เปลี่ยน Offer, Roster, Gap หรือสถานะเคสจากข้อความอิสระ ทางเดียวที่เปลี่ยน Offer ยังคือ `outreach_service.record_response()` ผ่านปุ่ม Race, Safety, Lock และ Audit ของรอบ 1 ถึง 5 จึงไม่เปลี่ยน
* ไม่เก็บข้อความของพยาบาลใน DB หรือ Log นอกจากรหัส Event ที่ `LineWebhookEvent` เก็บอยู่แล้วเพื่อกันซ้ำ และไม่ส่งข้อความเข้า LLM ดังนั้นข้อกังวลเรื่อง prompt injection จากข้อความของพยาบาลไม่เกิดในรอบนี้ ถ้ารอบหลังจะให้ LLM อ่านข้อความอิสระ ต้องเปิดคำถามใหม่และกำหนดกติกาจำกัดค่าที่ LLM คืนได้และให้คนกดยืนยัน
* ข้อความแนะนำไม่ตอบซ้ำเมื่อ LINE ส่ง Event เดิมมาอีก (รวมสอง Connection): Commit `LineWebhookEvent` ก่อนส่งผ่านตัวตอบเดิมหลัง Commit ไม่ตอบในกลุ่ม/ห้องหรือเมื่อไม่มี user ID ไม่ตอบ Event ที่ไม่ใช่ message ไม่มี reply token ไม่ส่ง Reply ส่งล้มเป็น best effort ไม่ย้อน Dedup และไม่ส่งซ้ำในการ Redelivery ส่วน LINK, CHECKIN และ Offer postback ใช้ทางเดิม
* Test: `tests/integration/test_line_message_guidance.py` ตรวจข้อมูลธุรกิจทุกตารางไม่เปลี่ยน ไม่มีการเรียก LLM/record_response, ข้อความไม่เข้า Log, กลุ่ม/ห้อง, ผู้ใช้ไม่ผูกบัญชี, Dedup หลัง Commit และสอง Connection; Regression ของคำสั่งและปุ่มอยู่ใน `test_line_messaging.py`, `test_line_account_linking.py`, `test_line_handover.py`

### 6.30 เครื่อง AWS และเกณฑ์เว็บพร้อมก่อน Deploy [รอบ 6 · PR F3, W]

**ลำดับ (มติทีม 2026-10-14 และ R6-Q3, R6-Q13):** เครื่องขึ้นและผ่านด่านก่อน จากนั้นคน 2 ลอง Bedrock ด้วย IAM Role ของเครื่อง และคน 3 ย้าย Webhook จาก Tunnel มาที่เครื่องแล้วปิด Tunnel (ถ้าเครื่องล่มกลับไปใช้ Tunnel ได้ เพราะไฟล์ใน `dev/line-webhook-proxy/` ยังอยู่) ย้ายหลังเครื่องผ่านด่านและ Offer, ปุ่ม, ผูกบัญชีผ่านเครื่องจริงอย่างน้อยหนึ่งรอบ

**PR D (R6-Q4 ก, ทำแล้ว):** เอาเฉพาะไฟล์ใหม่ใน `deploy/aws/` และ `docs/deploy-aws.md` จาก branch `feat/aws-test-environment` (merge-base `21448d5` ก่อนรอบ 3) ไปใส่ branch ใหม่ที่แตกจาก `staging` แล้วตรวจกับ Compose ปัจจุบัน (`postgres`, `redis`, `backend`, `job`, `frontend` และ Backend ต้องติดตั้ง `langgraph`) ไม่ Merge branch เก่าทั้งก้อน ส่วนแก้ `workflow.md` เขียนใหม่ใน PR 0 D ไม่เปิดเครื่อง ความลับ (Channel secret, Channel access token, รหัส Basic Auth) อยู่ใน Parameter Store และ `load-env.sh` โหลดเข้า env ตอนเริ่มเครื่อง ไม่อยู่ใน repo, Log หรือ Description ผลของ D: `Caddyfile` (ข้อยกเว้นของ Webhook จับจาก `{http.request.orig_uri}`), `docker-compose.aws.yml` (ตรึง `LLM_ENABLED=false` จน E1 ลบ), `check-gate.sh` ตามรายการข้างล่าง, `test_gate.py` และ job `AWS test machine gate (Caddy)` ใน CI

**กฎ `/demo/` ของเครื่อง AWS (รีวิวรอบแรกของ PR #104):** กฎเดียวคือ **ทุก Path ต้องมีรหัส Basic Auth ของเครื่อง ยกเว้น `POST /api/line/webhook` ตรงตัว (ข้อ 6.17) ไม่มีการกัน `/demo/` แยกต่างหาก** ผู้ที่ใส่รหัสแล้วใช้หน้า Demo และเรียก `/api/demo/*` ได้ เพราะหน้า Demo control เรียก API เหล่านี้จากเบราว์เซอร์ และรหัสตัวเดียวให้ทุกคนที่เข้าได้มีสิทธิ์เท่ากัน "เข้าไม่ได้จากช่องทางสาธารณะ" ในข้อ 6.24 จึงหมายถึงเข้าไม่ได้โดยไม่มีรหัส ไม่ได้หมายถึงบล็อกทั้งหมด

* ชื่อ Path แยกสองชนิด: หน้าเว็บ (ไม่มี `/api`): `/demo/control`, `/demo/line-sim` API (มี `/api` นำหน้าเพราะ Caddy ตัดคำนำหน้านี้ก่อนส่งให้ Backend): `/api/demo/reset`, `/api/demo/clock/advance`, `/api/demo/attendance/check-in`, `/api/clock` ฝั่ง Backend เองไม่เห็นคำนำหน้า (`/demo/reset`)
* Tunnel ในเครื่องพัฒนาเป็นอีกกฎหนึ่ง: `dev/line-webhook-proxy` เปิดเฉพาะ `POST /line/webhook` Path อื่นรวม `/demo/*` ได้ `404` และไม่มีรหัส ใช้จนกว่าจะย้ายมาเครื่อง AWS
* `/clock` อยู่หลังรหัสเหมือนทุก Path ในเครื่อง AWS
* `check-gate.sh` ฝั่ง AWS ตรวจ (ทำแล้วใน PR D): ไม่มีรหัสได้ `401` ทุก Path นี้: `GET /`, `GET /demo/control`, `GET /demo/line-sim`, `GET /api/health`, `GET /api/docs`, `GET /api/clock`, `POST /api/demo/reset`, `POST /api/demo/clock/advance`, `POST /api/demo/attendance/check-in`, `GET /api/line/webhook`, `POST /api/line/webhook/x`, `POST /api/line/webhooks`, `POST /api/line/webhook/`, `POST /line/webhook` (ไม่มี `/api`) และรูปที่ Caddy จับ `path` ผิดได้: `?x=1`, `/API/line/webhook`, `/api/LINE/webhook`, `/api//line/webhook`, `/api/%6Cine/webhook`, `/api/line/webhook%2F`, `/api/line/webhook/../health` `/api/internal/*` ได้ `404` ทั้งมีและไม่มีรหัส (รวมตัวพิมพ์ใหญ่) ส่วน `POST /api/line/webhook` ตรงตัวไม่ติดด่านรหัส (ได้ `401` หรือ `503` จากลายเซ็นของ LINE ไม่ใช่จากด่านรหัส) และมีรหัสถูก: `GET /`, `GET /demo/control`, `GET /api/health` และ `GET /api/clock` ได้ `200` เพื่อพิสูจน์ว่า Demo ใช้งานได้หลังใส่รหัส รหัสผิดได้ `401` Webhook บนเครื่องตรวจลายเซ็นเหมือนเดิม (ข้อยกเว้นของรหัสไม่ลดการตรวจ)

**เกณฑ์ "เว็บพร้อมก่อน Deploy" แยกสองช่วง (R6-Q18 ก, รีวิวรอบแรกของ PR #104)**

ช่วง ก ตรวจในเครื่องของผู้พัฒนาก่อนเปิดเครื่อง AWS (PR F3 บันทึกผลใน Description):

1. มีไฟล์ Compose ของ AWS ที่ทับคำสั่งของ Frontend เป็น `next build` + `next start` และไม่ bind mount โค้ดเข้า Container (ไฟล์อยู่ใน repo จาก D และ F3) รันไฟล์นี้บนเครื่องผู้พัฒนาแล้วยืนยันว่า Container ใช้ production mode (ดูคำสั่งที่รันจริงด้วย `docker inspect`)
2. `tsc --noEmit`, `vitest run` และ `next build` ผ่าน
3. ทุกหน้า (เดิมและใหม่) ตรวจจริงในเบราว์เซอร์ด้วย skill browser-automation กับ production build ที่รันในเครื่อง (`next start`) ทั้งจอ Desktop และจอแคบแบบโทรศัพท์ ตรวจสถานะกำลังโหลด ว่าง Error ของ API และไม่มี Error ใน Console
4. Bundle ที่ build ด้วย `NEXT_PUBLIC_API_BASE_URL` แบบ AWS (`https://<โดเมน>/api`) ไม่มี `localhost:8000` ในไฟล์ที่ไม่ใช่ `.map` (ไม่ใช่ค้นคำว่า `localhost` เฉยๆ เพราะโค้ดแยก URL ของ Next มีคำนี้อยู่)
5. เมนูมีหน้าใหม่ครบ และเปลี่ยนมุมมองผู้ใช้ Demo (`X-Demo-User`) ได้ในทุกหน้าที่ต้องใช้
6. ไม่มีความลับในโค้ดฝั่งเบราว์เซอร์ (มีแค่ `NEXT_PUBLIC_API_BASE_URL`)
7. ไม่เปลี่ยนพฤติกรรมของหน้าเดิม: Test Frontend เดิมทั้งหมดผ่าน
8. `check-gate.sh` ฉบับที่อัปเดตตามกฎข้างบนผ่านกับ Caddy ที่รันในเครื่อง

ช่วง ข ตรวจบนเครื่อง AWS ก่อนเปิดให้ภายนอกเข้า (ขั้นที่ 6 ไม่ใช่ PR ทั้งสามคนทำ บันทึกผลในตาราง fake กับของจริงและใน Description ของ PR แรกที่ใช้เครื่อง คือ B2 หรือ W):

1. Container ของ Frontend บนเครื่องรัน production mode จริง (ตรวจ `docker inspect` บนเครื่อง)
2. `check-gate.sh` ผ่านบนเครื่อง AWS จริง ตามกฎข้างบน
3. เปิดหน้าหลักผ่าน Caddy ด้วยรหัส Basic Auth (`/`, `/gap`, หน้าเคส, `/demo/control`) และเรียก API ผ่าน `/api` ได้โดยไม่มี Error ใน Console และ Bundle ที่เครื่องส่งให้ไม่มี `localhost:8000` และเบราว์เซอร์ไม่ถามรหัสซ้ำหลัง API ตอบ `401` ของ Backend (Header `WWW-Authenticate: X-Demo-User` คนละ Scheme กับ Basic ของด่าน ดู `docs/deploy-aws.md`)
4. ข้อเสนอที่ยังไม่ตกลง: ระหว่างตรวจจำกัด Security Group ให้ IP ของทีมเท่านั้น และเปลี่ยน Webhook ของ LINE (W) หลังเปิดแล้วเท่านั้น

**เกณฑ์ปิดรอบ 6 (R6-Q3 ก):** (1) เครื่อง AWS ผ่าน `check-gate.sh` (2) LINE ส่ง Offer และรับคำตอบผ่านเครื่อง AWS จริงอย่างน้อยหนึ่งเส้นทาง (3) Bedrock สร้างประโยคอธิบายอันดับจริงอย่างน้อยหนึ่งเคสพร้อมบันทึกค่าใช้จ่าย (4) ตาราง fake กับของจริงทุกแถวมีวันที่หรือเหตุผลที่ยังใช้ fake

### 6.31 Dashboard และหน้าเช็ค Gap [รอบ 6 · PR F1, F2]

ฐานตอนเริ่มรอบ: หน้าแรกเป็นแค่ "System check" ไม่มีหน้ารายการเคสทุกสถานะ (`GET /cases` ต้องระบุ `status` และใช้กับรายการของ Head Nurse) Gap ดูได้เฉพาะในหน้าเคสหลังมี Event แล้ว

* **ขอบเขตตามหอ (R6-Q16 ก):** เห็นเฉพาะหอของผู้ใช้ Demo (`X-Demo-User`) Supervisor (950) เห็นทุกหอ
* **Dashboard (แทนหน้า `/` เก็บสถานะ API/ฐานข้อมูลไว้เป็นแถบเล็ก):** เวลา Backend Clock และโหมดที่ใช้อยู่ (`LINE_MODE`, `LLM_PROVIDER`) จำนวนเคสแยกตามสถานะพร้อมลิงก์ (เน้น `MANUAL_HANDOFF` และ `FAILED`) เวรที่ขาดคนตอนนี้ คำขออนุมัติที่รอแยกตามหอ Offer ที่ส่งแล้วรอคำตอบ Event `NO_SHOW` ล่าสุด และการใช้ LLM วันนี้เทียบเพดานกับค่าใช้จ่ายรวมของเดือนเทียบ 20 USD (แสดงเมื่อ `LLM_ENABLED` เท่านั้น) ข้อมูลมาจาก `GET /dashboard` (ข้อ 9.8) อ่านอย่างเดียว
* **Gap ตามเวลา:** Dashboard คิด Gap เฉพาะเวรของหอที่เห็นในหน้าต่างเวลาจำกัด (ตั้งแต่ Backend Clock ถึง 24 ชั่วโมงข้างหน้า และเวรที่กำลังดำเนินอยู่) ไม่คิดทุกเวรของระบบ ตรวจแล้ว: `assess_shift()` 4 เวรใช้ 0.018 วินาที (ราว 4.5 มิลลิวินาทีต่อเวร) ที่ Demo scale พอ ถ้ามีเวรเป็นพันจะราว 4.5 วินาทีต่อรอบ (ประเมิน ไม่ได้วัด) จึงต้องจำกัดหน้าต่างเวลา `staffing_cases.status`, `staffing_events.status` และ `shift(ward_id, start_at)` ไม่มี Index ไม่ต้องเพิ่มในรอบนี้
* **หน้า `/gap` (R6-Q17 ก อ่านอย่างเดียว):** เลือกหอ วันที่ และเวร แล้วแสดงรายช่วงเวลา (จาก, ถึง, จำนวนที่ต้องมี, จำนวนที่มี, ขาดกี่คน, ขาด Role/Skill ใด) ใช้ตารางรูปเดียวกับ `GapTable.tsx` และแสดงรายชื่อคนใน Roster ของเวรนั้นพร้อมสถานะ (รวมคนลาและคนที่ check-in แล้ว) ถ้าเวรมีเคสที่เดินอยู่ มีลิงก์ไปหน้าเคส ไม่มีปุ่มสร้าง Event หรือเคสในหน้านี้ ต้องผ่าน Demo control เหมือนเดิม
* Route อ่านเรียก `assess_shift()` ไม่ผ่าน `record_gap()` จึงไม่สร้างแถว Gap, Event, Audit หรือเคส เวลาใช้ Backend Clock เหมือนหน้าเคส ตัวเลข Gap ของเวรที่มีเคสต้องตรงกับหน้าเคส
* โหลดข้อมูลซ้ำเป็นระยะเหมือนหน้าอนุมัติ (ทุก 2 วินาที) หรือกดรีเฟรช ตัดสินตอนทำ F2
* PR #103 (การแจ้งผลข้อเสนอทาง LINE) merge เข้า `staging` หลังเริ่มเขียนร่างรอบ 6 ผู้ทำ F1 และ S อ่าน `docs/issue-98-line-outcomes.md` ก่อนกำหนดรูปข้อมูล เพราะร่างรอบ 6 ไม่ได้ตรวจว่ากระทบ Payload ของสรุปเคสหรือ Dashboard อย่างไร

## 7. Audit

PR 4 ตรวจชุด Offer ซ้ำหลังล็อก Staff ถ้ามี Offer ใหม่ Commit ระหว่างรอ Lock ให้ Rollback ก่อนเขียนคำตัดสิน แล้วเริ่มล็อกใหม่ตามลำดับเดิม (สูงสุด 5 ครั้ง ถ้ายังเปลี่ยนตอบ 409 ให้ลองใหม่) ไม่ล็อก Offer เพิ่มภายหลังเคส/Staff เพื่อกัน Deadlock

### 7.1 Action ที่ใช้

| Action | ใครเขียน | Actor | entity_type | payload ขั้นต่ำ |
|---|---|---|---|---|
| `EVENT_RECEIVED` | `event_service` ตอนรับ Event (PART A) | user (ผู้แจ้ง) หรือ system (Event `NO_SHOW` ที่ Job บันทึก ข้อ 6.24) | STAFFING_EVENTS | `event_type`, `shift_id`, `staff_id` |
| `UNAVAILABILITY_CREATED` | `merge_window_service` ตอน Window ปิด (PART B) | user (คนที่ลา) หรือ system (`NO_SHOW` ข้อ 6.24) | STAFF_UNAVAILABILITY | `unavailability_id`, `staff_id`, `reason`, `start_at`, `end_at` |
| `ATTENDANCE_CHECKED_IN` | ฟังก์ชันกลางของ check-in (ข้อ 6.24) | user (พยาบาลที่กด) หรือ system (การจำลอง) | ATTENDANCE | `attendance_id`, `staff_id`, `shift_id`, `roster_assignment_id`, `check_in_at`, `on_time` (boolean), `source` (`SELF` หรือ `SIMULATED`) |
| `OFFER_CANCELLED_NOT_NEEDED` | `late_arrival_service.trim()` ทางมาสาย (ข้อ 6.24) หนึ่งแถวต่อ Offer ที่ยกเลิก (คำขอที่รออนุมัติยกเลิกผ่าน Offer `ACCEPTED` ของมัน) | system | CANDIDATE_OUTREACH | `cancelled_outreach_id`, `approval_request_id` (ว่างได้), `staff_id`, `late_staff_id`, `reason` = `NO_LONGER_NEEDED` แถวนี้มี `case_id` = เคสที่ยกเลิก `_cancellation_reasons()` อ่าน `cancelled_outreach_id` คู่กับ Action นี้เท่านั้น |
| `HANDOVER_GENERATED` | ฟังก์ชันกลางที่สร้างเวร (ข้อ 6.25) | ผู้กระทำของการจัดนั้น | STRUCTURED_HANDOVER | `handover_id`, `roster_assignment_id`, `staff_id`, `shift_id`, `case_id` |
| `UNAVAILABILITY_UPDATED` | `unavailability_service.update_end_at()` (รอบ 3 PR R) หรือ `late_arrival_service.arrive_after_no_show()` (ข้อ 6.24, รอบ 5 PR N2) | user (Head Nurse ที่แก้) หรือ system (มาสายหลังขั้นที่ 2) | STAFF_UNAVAILABILITY | `unavailability_id`, `staff_id`, `previous_end_at` (`null` ได้), `end_at` เวลาเป็น `+07:00` แถวของ `update_end_at()` มี `case_id = NULL` และ `event_id = NULL` แถวของทางมาสายมี `event_id = NULL`, `case_id` = เคสที่ได้เครดิต (`late_arrival_service.credited_case()`) หรือ `NULL` ถ้าไม่มี และ payload เพิ่ม `roster_assignment_id` (= แถวใหม่ที่ `restore()` สร้าง) กับ `late_arrival: true` แถวนี้ทำให้เคสนับคนที่มาสาย (`case_facts_service._returned_spans()`) |
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
| `APPROVAL_TIMEOUT` (PR T) | `approval_timeout_service` เรียกจาก Job | `workflow_orchestrator` | APPROVAL_REQUEST | `approval_id`, `staff_id` (ผู้สมัคร), `outreach_id` (Offer ที่ถูกยกเลิก), `reason` (ข้อความตายตัว) |
| `MANUAL_ASSIGNMENT_CREATED` | เส้นทางจัดคนเอง | user (Head Nurse) | ROSTER_ASSIGNMENT | `assignment_id`, `manual_assignment_id`, `staff_id`, `assignment_type`, `reason` (ว่างได้), `cancelled_outreach_ids` (Offer ของเคสอื่นที่ขัดกับเวรใหม่ ว่างได้) |
| `CASE_CLOSED_UNRESOLVED` | เส้นทางปิดเคสโดยไม่มีคนแทน หรือขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด | user (Head Nurse) หรือ `workflow_orchestrator` เมื่อระบบปิด | STAFFING_CASES | `reason`, `closed_by` (`HEAD_NURSE`, `SUPERVISOR` หรือ `SUCCESSOR_CASE`), `successor_case_id` (มีเมื่อระบบปิด) |
| `OFFER_CANCELLED_BY_ASSIGNMENT` | ตัวยกเลิก Offer ที่ขัดกับเวรใหม่ เขียนใน**เคสที่เสีย Offer** หนึ่งแถวต่อ Offer | ผู้กระทำของการจัดนั้น | CANDIDATE_OUTREACH | `cancelled_outreach_id` (เอกพจน์), `staff_id`, `by_case_id` (เคสที่เอาคนไป), `assignment_id` (Roster ที่ทำให้ขัด), `source` (`MANUAL_ASSIGNMENT` หรือ `APPROVAL`) |
| `OFFER_DELIVERY_FAILED` | ตัวส่ง Offer ของ LINE เมื่อตั้ง Offer เป็น `FAILED` (ข้อ 6.16) | `outreach_agent` | CANDIDATE_OUTREACH | `outreach_id`, `staff_id`, `attempts` (จำนวนครั้งที่นับ), `last_result` (รหัส HTTP เป็นข้อความ หรือ `TIMEOUT`) |
| `LINE_ACCOUNT_LINKED` | Webhook เมื่อรับ `LINK <รหัส>` ที่ใช้ได้ ใน Transaction เดียวกับการผูก | user (พนักงานที่ผูก) | CONTACTS | `contact_id`, `staff_id` |
| `LINE_ACCOUNT_UNLINKED` | คำสั่งปลดการผูกของผู้ดูแล | `system` | CONTACTS | `contact_id`, `staff_id` |
| `ASSIGNMENT_TRANSFERRED` | การย้ายคนจริง เขียนแทน `ASSIGNMENT_CREATED` ของรายการที่มีเวรต้นทาง ใน Transaction เดียวกับการแก้แถวต้นทางและสร้างแถวปลายทาง (ข้อ 6.19) | `workflow_orchestrator` | ROSTER_ASSIGNMENT (แถวปลายทาง) | `assignment_id`, `from_assignment_id`, `staff_id`, `from_shift_id`, `to_shift_id`, `transfer_at`, `from_status` (`RosterStatus` ของแถวต้นทางหลังย้าย: `CANCELLED` เมื่อย้ายตั้งแต่เวลาเริ่มของเวรต้นทาง หรือ `ASSIGNED` เมื่อแถวต้นทางยังอยู่และจบที่ `transfer_at`, R4-Q40; C2 เขียนแต่ `CANCELLED`), `cancelled_outreach_ids` (Offer ของเคสอื่นที่ขัดกับเวรใหม่ ว่างได้ เหมือน `ASSIGNMENT_CREATED`) |
| `TRANSFER_CHECK_FAILED` | การตรวจตอนย้ายจริงไม่ผ่าน คำขอจบและ Offer ถูกยกเลิก (ข้อ 6.19) | `workflow_orchestrator` | APPROVAL_REQUEST | `approval_id`, `outreach_id`, `staff_id`, `reason` (`TransferFailureReason`), `failed_rules` (ว่างได้) |
| `APPROVAL_WARD_APPROVED` (PR S) | Head Nurse หรือ Supervisor อนุมัติฝั่งหนึ่งของคำขอสองหอ ขณะอีกฝั่งยังไม่ตัดสิน (ข้อ 6.21) | user (คนกด) | APPROVAL_REQUEST | `approval_id`, `ward_id`, `side`, `decided_as` |

* `ASSIGNMENT_CANCELLED`, `PATIENT_COUNT_UPDATED`, `REQUIREMENT_UPDATED` เพิ่มใน `AuditAction` แล้ว และ `SHIFT`, `STAFFING_REQUIREMENTS` เพิ่มใน `EntityType` แล้ว (PR 0) และ PART B เขียนแถวพวกนี้ตั้งแต่ PR M
* Actor ของ `OFFER_TIMEOUT` คือ `outreach_agent` และผู้เขียนคือ `offer_timeout_service` (PR O); Actor และชื่อ Key ใน payload ของ Action สามตัวของ Event ชนิดใหม่ และ Key `reason` ของ `EVENT_IGNORED` กำหนดแล้วใน PR M ตามตารางข้างบน
* `EVENT_RECEIVED`: `staff_id` ใน payload คือคนที่ Event พูดถึง (`STAFFING_EVENTS.staff_id`) จึงเป็น `null` สำหรับ `PATIENT_SURGE` และ `REQUIREMENT_CHANGED` ผู้แจ้งดูจาก Actor ของแถว
* หกแถวแรกของตารางเป็นแถวของ Event: มี `event_id` และ `case_id = NULL` เสมอ ส่วน `CASE_OPENED` เป็นแถวของเคส: มี `case_id` และ `event_id = NULL` โดยบอก Event ไว้ใน payload

รหัส `reason` ของ `MANUAL_HANDOFF`: `NO_CANDIDATE_LEFT` (T5), `NO_FEASIBLE_PLAN` (T6) และ `SOLVER_TIMEOUT` (T6 เมื่อ Solver หมดเวลาโดยยังไม่มีแผน ข้อ 6.14 ตั้งแต่รอบ 2 PR B)

* Action ที่เพิ่มในรอบ 2 มีผู้เขียนครบแล้ว `APPROVAL_TIMEOUT` เขียนโดย PR T ส่วน `MANUAL_ASSIGNMENT_CREATED`, `CASE_CLOSED_UNRESOLVED` และ `OFFER_CANCELLED_BY_ASSIGNMENT` เขียนโดย PR H
* ชื่อช่องของ `OFFER_CANCELLED_BY_ASSIGNMENT` ต้องเป็น `cancelled_outreach_id` ห้ามใช้ `cancelled_outreach_ids` หรือ `outreach_id` เพราะ `outreach_service._cancellation_reasons()` ใช้สองชื่อนั้นหาเหตุที่ยกเลิก และแถว Audit ล่าสุดชนะ ถ้าใช้ชื่อซ้ำ `cancellation_reason` ของรายการ Offer จะเปลี่ยนจาก `CONFLICTING_ASSIGNMENT` เป็น `CANCELLED` โดยไม่มี Error
* `MANUAL_ASSIGNMENT_CREATED` ใช้ `cancelled_outreach_ids` เหมือน `ASSIGNMENT_CREATED` และ PR H ต้องเพิ่ม Action นี้ในตารางของ `_cancellation_reasons()` ให้ได้ `CONFLICTING_ASSIGNMENT`
* `APPROVAL_TIMEOUT` มี `outreach_id` และ PR T ให้ `_cancellation_reasons()` คืน `APPROVAL_TIMEOUT` สำหรับ Offer นั้น
* `OFFER_DELIVERY_FAILED` เขียนโดย `line_delivery_service` (PR L); `LINE_ACCOUNT_LINKED` และ `LINE_ACCOUNT_UNLINKED` เขียนโดย `line_account_service` (PR K)
* `OFFER_DELIVERY_FAILED` มี `case_id` ของ Offer และใช้ช่อง `outreach_id` ซึ่ง `_cancellation_reasons()` อ่านด้วย แต่ไม่กระทบ เพราะ Offer ที่ `FAILED` ไม่ใช่ `CANCELLED` และไม่เปลี่ยนเป็น `CANCELLED` ภายหลัง ถ้า PR L เปลี่ยนข้อนี้ต้องเพิ่ม Action นี้ในตารางของ `_cancellation_reasons()`
* **[รอบ 4]** `APPROVAL_APPROVED` ของการอนุมัติเอง (PR A) มี `approval_mode = AUTO` และเพิ่ม `pending_count`, `approver_count`, `cap` ใน payload ส่วนการตัดสินสุดท้ายของคำขอสองหอเขียน `APPROVAL_APPROVED` หรือ `APPROVAL_REJECTED` ตามเดิม และ `TRANSFER_CHECK_FAILED` มี `outreach_id` ซึ่ง `outreach_service._cancellation_reasons()` แปลงเป็น `cancellation_reason = TRANSFER_CHECK_FAILED` (PR C2 ทำแล้ว) และ `ASSIGNMENT_TRANSFERRED` ใช้ `cancelled_outreach_ids` เหมือน `ASSIGNMENT_CREATED` `_cancellation_reasons()` แปลง Offer ที่ถูกยกเลิกเพราะการย้ายเป็น `CONFLICTING_ASSIGNMENT` ลำดับ Audit ของผู้สมัครที่เป็นการย้ายเหมือนลำดับด้านล่างแต่ `ASSIGNMENT_TRANSFERRED` อยู่แทน `ASSIGNMENT_CREATED` ถ้าตรวจซ้ำตอนย้ายจริงไม่ผ่าน มี `TRANSFER_CHECK_FAILED` ต่อจาก `APPROVAL_APPROVED` และไม่มี Roster
* `LINE_ACCOUNT_LINKED` และ `LINE_ACCOUNT_UNLINKED` ไม่ใช่เรื่องของเคสหรือ Event จึงมี `case_id = NULL` และ `event_id = NULL` และไม่เก็บ `line_uid` ใน payload

* `MANUAL_HANDOFF` ของ T6 เขียนโดย Handler `optimize` ด้วย Actor `constraint_fair_scheduling_agent` ต่อจาก `SOLVER_EXECUTED` ในรอบเดียวกัน `cancelled_outreach_ids` ว่างเสมอ และ `skipped` คือทุกคนใน Pool ที่ Solver ตัดออก เรียงตาม `staff_id` รหัสของแต่ละคนคือเหตุผลแรกตามลำดับ: Hard Rules (ลำดับตารางในร่างรอบ 1 ข้อ 7.2), ปิด Gap ไม่ได้สักอย่าง, เพดาน Offer ค่าของ `reason` อยู่ใน `ManualHandoffReason` ของ `domain/enums.py`

payload ที่เปลี่ยนจาก Skeleton เพราะ Wave

* `OFFER_SENT`: ยังเป็นหนึ่งแถวต่อคน เรียงตาม `rank` payload เดิม (`outreach_id`, `staff_id`, `channel`) เพิ่ม `wave` (เลข Wave ของเคส เริ่มที่ 1) แถวแรกของ Wave มี `skipped` (Q5)
* `OFFER_ACCEPTED`: ไม่เพิ่ม `cancelled_outreach_ids` เพราะการตอบรับไม่ยกเลิก Offer ของคนอื่นทันที (ข้อ 6.8)
* `CASE_RESOLVED`: เพิ่ม `cancelled_outreach_ids` = Offer ของเคสที่ถูกยกเลิกตอนได้คนครบ ทั้งที่ยัง `SENT` และของสำรอง (Q28)
* `ASSIGNMENT_CREATED`: เพิ่ม `cancelled_outreach_ids` = Offer ของเคสอื่นที่ขัดกับเวรใหม่ของผู้สมัคร (ข้อ 6.8) ว่างได้
* `WORKFLOW_FAILED`: ไม่เปลี่ยนความหมาย ยังแปลว่าเคส `FAILED` ตาม D11 เท่านั้น ไม่มีกรณีจัดเวรรายคนไม่ผ่าน เพราะไม่มีการตรวจซ้ำตอนจัดเวร (Q38)

### 7.2 กติกา

* `CASE_STATUS_CHANGED` ยังเขียนโดย Orchestrator เท่านั้น ทุกเส้นใหม่จะมีแถวนี้เอง
* ไม่เพิ่ม Action สำหรับการตั้ง Offer เป็น `CANCELLED` ให้ `outreach_id` ใน payload ของ `SAFETY_FAILED` / `APPROVAL_REJECTED` / `APPROVAL_TIMEOUT` บอกแทน ส่วน Offer ที่ถูกยกเลิกเพราะเคสได้คนครบ, เพราะเคสเข้า `MANUAL_HANDOFF` หรือเพราะขัดกับเวรใหม่ของผู้สมัคร ให้ `cancelled_outreach_ids` ของ Action ในจังหวะนั้นบอก (ข้อ 7.1, Q28)
  * ข้อยกเว้นหนึ่งข้อ: Offer ที่ถูกยกเลิกเพราะเคสอื่นเอาคนไป ได้แถว `OFFER_CANCELLED_BY_ASSIGNMENT` ในเคสของ Offer นั้นด้วย เพราะ `cancelled_outreach_ids` อยู่ในเคสที่ได้คนไป คนที่เปิดเคสที่เสีย Offer จึงไม่เห็นเหตุ (R2-Q56) ช่อง `cancelled_outreach_ids` ในเคสที่ได้คนไปคงไว้ตามเดิม
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
ถ้า Solver หมดเวลาโดยยังไม่มีแผน ลำดับเหมือนกัน แต่ `solver_status` ใน `SOLVER_EXECUTED` เป็น `UNKNOWN` และเหตุผลเป็น `SOLVER_TIMEOUT` (ข้อ 6.14)

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
| Solver | ของจริงตั้งแต่ PR 2a: `optimization_service.create_plan()` ทำตามร่างรอบ 1 ข้อ 8.3 (1) Pool = พนักงานทุกคนที่ `home_ward_id` ตรงกับหอของเวรของเคส และตั้งแต่รอบ 4 PR C1 รวมคนว่างของหออื่นกับ Float Pool ตามข้อ 6.19 โดย `source` คิดตามข้อ 6.19 (Seed รอบ 1 มีหอเดียว จึงเป็น `SAME_WARD` ทุกคน) (2) ล็อกแถว `STAFF` ของทั้ง Pool (`FOR NO KEY UPDATE` เรียงตาม `id`) จนรอบนั้น Commit (3) ตัดคนออกพร้อมรหัสเหตุผลหนึ่งรหัสต่อคน ใช้เหตุผลแรกตามลำดับนี้: ไม่ผ่าน Hard Rules (`hard_rule_service.check_staff()` รหัส = ข้อแรกที่ไม่ผ่านตามลำดับตารางในร่างรอบ 1 ข้อ 7.2), ปิด Gap ไม่ได้สักอย่าง (เกิดเมื่อ `headcount_gap = 0`: รหัส `SKILL_MISMATCH` ถ้าเคสขาด Skill ไม่งั้น `ROLE_MISMATCH`), เต็มเพดาน Offer (`availability_service.staff_at_offer_limit()` รหัส `OFFER_LIMIT_REACHED` ข้อ 6.7) (4) `working_time_service.capture()` เขียน `STAFF_WORKING_TIME_SNAPSHOT` ของคนที่เหลือ (Seam 14) (5) `optimization/solver.py` คิด Target = `ceil(gap * 11 / 10)` แล้วเลือกกลุ่มของ Wave แรกที่ปิด Target ครบและ `plan_penalty` ต่ำสุด ด้วยโมเดล CP-SAT ของ OR-Tools ตั้งแต่รอบ 2 PR B ภายในเพดานเวลา `SOFT_CONSTRAINT_POLICY.solver_time_limit_seconds` (ข้อ 6.14) คะแนนเท่ากันเลือกกลุ่มที่คนน้อยกว่า แล้ว `staff_id` น้อยกว่า Target ที่ผู้สมัครมีไม่พอถูกลดลงเท่าจำนวนคนที่ตรง (6) บันทึก Plan ที่มีทุกคนที่เหลือ ไม่ใช่เฉพาะกลุ่มของ Wave แรก `rank` = กลุ่มของ Wave แรกเรียงตาม `ranking_key` แล้วตามด้วยคนที่เหลือเรียงตาม `ranking_key` ไม่ข้ามเลข พร้อม `working_time_snapshot_id` ของแต่ละคน และแถว `CANDIDATE_ITEM_TARGET` ของกลุ่ม Wave แรก (Seam 13) `solver_status` = สถานะที่ Solver รายงาน (`OPTIMAL` เมื่อพิสูจน์ครบ, `FEASIBLE` เมื่อหมดเวลาก่อนพิสูจน์ครบ ข้อ 6.14), `solver_version = "cp-sat-v1"`, `objective_score` = `plan_penalty` ของกลุ่ม `input_snapshot` เก็บ `captured_at`, วันและต้นสัปดาห์ที่ใช้, Target, ค่าที่ใช้คิดของแต่ละคน และคนที่ถูกตัดพร้อมรหัส ถ้าไม่เหลือใครเลย: บันทึก Plan `INFEASIBLE` ไม่มี Item, Handler เขียน `SOLVER_EXECUTED` และ `MANUAL_HANDOFF` (`NO_FEASIBLE_PLAN`) แล้วเคสไป `MANUAL_HANDOFF` (T6) ไม่เป็น `FAILED` ถ้า Solver หมดเวลาโดยยังไม่มีแผน: บันทึก Plan `UNKNOWN` ไม่มี Item แล้วเคสไป `MANUAL_HANDOFF` ด้วยเหตุผล `SOLVER_TIMEOUT` เคสที่ไม่มีแถว Gap ยังเป็น `FAILED` ตาม D11 (`GapNotFoundError`) PR 2b ลบกฎ Offer ค้างเดิมแล้ว Solver ตัดด้วย `OFFER_LIMIT_REACHED` เฉพาะคนที่เต็มเพดาน Offer ตามข้อ 6.7 คนที่มีแถว Roster `CANCELLED` บนเวรของเคสไม่ผ่าน `UNAVAILABLE` จึงไม่ถูกเสนอเวรเดิมอีก การค้นแบบตัดกิ่งของรอบ 1 ถูกแทนด้วยโมเดล CP-SAT แล้ว ผลเท่ากับการลองทุกกลุ่มเมื่อสถานะเป็น `OPTIMAL` | CANDIDATE_PLANS, CANDIDATE_ITEMS, CANDIDATE_ITEM_TARGET, STAFF_WORKING_TIME_SNAPSHOT |
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
| GET | `/roster?shift_id=` หรือ `?staff_id=` | ตารางเวรของเวรนั้น หรือของพนักงานหนึ่งคน (`staff_id` จากรอบ 3 PR R) | คน 3, `staff_id` คน 1 |
| PATCH | `/unavailability/{id}` | แก้วันกลับของการลา (รอบ 3 PR R) | คน 1 |
| POST | `/demo/reset` | ล้าง DB โหลด Golden Case ตั้ง Clock ใหม่ ยกเว้นบัญชีการเรียก LLM (`LLM_DAILY_USAGE`, `LLM_TRIAL_USAGE`, `LLM_CALL_LOG` ข้อ 6.27) ทำใน Transaction เดียว ล้มแล้ว DB เดิมไม่เปลี่ยน | คน 1 |
| POST | `/demo/clock/advance` | เลื่อน Clock ของ Demo แล้วปิด Offer ที่หมดเวลา เก็บตกเคสที่ค้าง และปิด Window ที่ถึงเวลา | คน 1 |
| POST | `/line/webhook` | Webhook ของ LINE กันด้วยลายเซ็น ไม่ใช้ `X-Demo-User` | คน 3 |
| GET | `/me/offers` | Offer ของพนักงานใน Header (รอบ 3 PR N) | คน 1 |
| POST | `/me/offers/{outreach_id}/response` | พนักงานใน Header ตอบ `ACCEPT` / `REJECT` (รอบ 3 PR N) | คน 1 |
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
| `api/routes/internal.py` | `/internal` (Job และคำสั่งผู้ดูแลผูก/ปลด LINE ของ PR K กันด้วย Internal Secret) |

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
  "no_show_event_ids": [],
  "timed_out_outreach_ids": [],
  "timed_out_approval_request_ids": [],
  "recovered_case_ids": []
}
```

* `timed_out_approval_request_ids` คือคำขอที่ Job ตั้ง is_timed_out ในคำขอนี้ (ข้อ 6.13)
* `timed_out_outreach_ids` คือ Offer ที่คำขอนี้ตั้งเป็น `TIMEOUT` (ข้อ 6.9) และ `recovered_case_ids` คือเคสที่รออยู่ซึ่งรอบเก็บตกคำนวณสถานะใหม่ให้ (ข้อ 5.3) ทั้งสองเรียงตาม ID และเป็น `[]` เมื่อไม่มี หน้า `demo/control` ใช้แสดงว่าการเลื่อน Clock ทำให้ Offer ไหนหมดเวลา Route ของ Job ไม่คืนสองค่านี้
* `no_show_event_ids` คือ Event `NO_SHOW` ที่ Job ขั้นที่ 1 เขียนในคำขอนี้ (ข้อ 6.24) เรียงตาม ID และเป็น `[]` เมื่อไม่มี Event เหล่านี้เป็น `RECEIVED` ตอนเขียน ถ้า Window ของเวรเป็น 0 วินาที Window ปิดทันทีในขั้นเขียนเดียวกันนี้ (ข้อ 6.24) ซึ่ง `closed_windows` ของคำขอนี้ไม่แสดง เพราะรายการนั้นแสดงเฉพาะ Window ที่ Job ปิดทีหลังขั้นนี้
* `closed_windows` มีหนึ่งรายการต่อเวรที่ปิด Window ในคำขอนี้ เรียงตาม `shift_id` Window ที่ไม่เปิดเคสมี `case_id` และ `case_status` เป็น `null` (Event ของมันเป็น `IGNORED`)
* `event_ids` คือ Event ทุกตัวของ Window นั้น รวมตัวที่ `IGNORED` ตาม Q44 ซึ่งไม่ได้ Link เข้าเคส

**`POST /me/attendance/check-in`** (คน 2) ต้องมี `X-Demo-User` ของ Staff ที่ Active และมี Actor (ไม่ผ่าน → `401`) Body `{"shift_id": 1}` ฟิลด์เกินจากนี้ → `422` จึงส่ง `staff_id` ใน Body ไม่ได้ ส่วน `staff_id` ใน Query ไม่ถูกอ่าน ตัวตนมาจาก Header เท่านั้น

**`POST /demo/attendance/check-in`** (คน 2) ไม่ต้องมี `X-Demo-User` Body `{"staff_id": 101, "shift_id": 1}` จำลองการ check-in ของ Staff คนนั้น

```json
{
  "attendance_id": 1,
  "shift_id": 1,
  "check_in_at": "2026-10-09T23:05:00+07:00",
  "on_time": true,
  "deadline": "2026-10-09T23:15:00+07:00"
}
```

* ทั้งสอง Route ตอบ `200` ทั้ง check-in ครั้งแรกและ check-in ซ้ำ ใช้ฟังก์ชัน `attendance_service.check_in()` ตัวเดียว (ข้อ 6.24)
* `404` เมื่อไม่มีเวรนั้น, ไม่มีแถว `ROSTER_ASSIGNMENT` ที่ `ASSIGNED` ของ Staff คนนั้นในเวรนั้น (นับแถวที่ `NO_SHOW` ยกเลิกไปด้วย เพราะ check-in สายใช้ได้) หรือ (เฉพาะ `/demo/`) ไม่มี Staff ID นั้น
* `422` เมื่อ check-in ครั้งแรกอยู่นอกช่วง `[เวลาที่ต้องมาถึง − CHECK_IN_EARLIEST_SECONDS, effective_end_at)` ไม่เขียนแถวใด ยกเว้น check-in ซ้ำ ซึ่งคืนแถวเดิมเสมอ
* `409` เมื่อ check-in สายหลังขั้นที่ 2 ล็อกชุด Offer ของเคสไม่นิ่งครบ `CHECK_IN_LOCK_TRIES` = 5 ครั้ง (`CheckInLockRetryError`, ข้อ 6.11) ไม่เขียนแถวใด ลองกดใหม่ได้ ทั้ง `/me/attendance/check-in` และ `/demo/attendance/check-in`
* check-in ซ้ำคืน `check_in_at` ของแถวเดิม ส่วน `deadline` และ `on_time` คิดจากแถว Roster ที่บันทึกไว้ในแถว Audit `ATTENDANCE_CHECKED_IN` ของแถวนั้น
* Audit `source` = `SELF` และ Actor คือพยาบาลที่กด (`/me`) หรือ `SIMULATED` และ Actor `SYSTEM` (`/demo`)

**คำสั่งผู้ดูแล LINE (PR K)** `POST /internal/line-accounts/{staff_id}/issue-code` ไม่มี Body ตอบ `{code, expires_at}` หลัง Commit พร้อม `Cache-Control: no-store`; `/unlink` ตอบ `{unlinked_contacts}` ใช้ Header `X-Internal-Secret` เหมือน Job (401/503 ตามค่าตั้ง) Staff ไม่มีหรือไม่พร้อมตอนออกรหัสได้ 404 และบัญชีที่ผูกแล้วได้ 409; ID ต้องเป็น bigint บวก ไม่ใช่ Route หน้าเว็บ และไม่ยกเว้น Basic Auth บน AWS ตัว CLI เรียก loopback ของ Backend เท่านั้น ดูขั้นตอนใน `docs/round3/pr-K-handoff.md`

**`POST /internal/merge-windows/close-due`** (คน 1) Header `X-Internal-Secret` ไม่มี Body ตอบ `{"closed_windows": [...], "no_show_event_ids": [...], ...}` รูปเดียวกับข้างบน (`no_show_event_ids` ความหมายเดียวกัน) `401` เมื่อ Secret ไม่มีหรือไม่ตรง `503` เมื่อ Backend ไม่ได้ตั้ง `INTERNAL_JOB_SECRET` (ข้อ 3.8)

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
    "skills": [{"id": 1, "name": "ICU", "required_count": 2, "current_count": 2, "gap_count": 0}],
    "evaluated_from": "2026-10-09T23:00:00+07:00",
    "intervals": [
      {"start_at": "2026-10-09T23:00:00+07:00", "end_at": "2026-10-10T07:00:00+07:00",
       "headcount": {"required_count": 5, "current_count": 4, "gap_count": 1},
       "roles": [{"id": 1, "name": "RN", "required_count": 5, "current_count": 4, "gap_count": 1}],
       "skills": [{"id": 1, "name": "ICU", "required_count": 2, "current_count": 2, "gap_count": 0}]}
    ]
  },
  "assigned_count": 0,
  "candidates": [
    {"candidate_item_id": 1, "rank": 1, "staff_id": 201, "first_name": "Arunee", "last_name": "Demo",
     "source": "SAME_WARD", "home_ward_id": 1, "home_ward_name": "ICU",
     "outreach_status": "SENT", "stage": "OFFER_SENT",
     "score": {"total": 1005, "first_wave": true, "terms": [
       {"name": "candidate_count", "value": 1, "weight": 1000, "points": 1000},
       {"name": "consecutive_shift", "value": 1, "weight": 5, "points": 5},
       {"name": "workload_imbalance", "value": 0, "weight": 1, "points": 0},
       {"name": "projected_overtime", "value": 0, "weight": 2, "points": 0},
       {"name": "candidate_source", "value": 0, "weight": 200, "points": 0}]},
     "cover_start_at": null, "cover_end_at": null, "source_assignment": null}
  ],
  "explanation": {"status": "READY", "text": "[fake] ...", "provider": "fake", "model_id": null},
  "partial_plan": false,
  "handovers": []
}
```

* `event_ids` คือ Event ทุกตัวของเคส อ่านจาก `STAFFING_EVENTS.case_id` เรียงตาม `id` แทน `event_id` ตัวเดียวของ Skeleton (Q36, PR M)
* `gap.effective_minimum` คือเป้าหมายจำนวนคนที่ใช้คิด Gap แถวนั้น (ข้อ 3.6) ไม่คืน `required_staff` กับ `minimum_staff`
  เพราะ Requirement ถูก UPDATE ในแถวเดิม ค่าที่อ่านได้อาจไม่ใช่ค่าตอนคิด (Q20)
* `gap` เป็น `null` จนกว่าขั้น `ASSESSING` จะบันทึก `STAFFING_GAP` ถ้ามีหลายแถวใช้แถวที่ `id` มากสุด
  ใน `roles` / `skills` ฟิลด์ `id` คือ Role ID / Skill ID
* `gap.intervals` (รอบ 4 PR T3) คือทุกช่วงของ Gap เรียงตามเวลา รวมช่วงที่ไม่ขาด แต่ละช่วงเป็น `[start_at, end_at)` มี `headcount` และ `roles` / `skills` ของช่วงนั้น `gap.evaluated_from` คือจุดเริ่มของช่วงที่วัด ตัวอย่าง: Gap ข้างบนวัดตอน 21:00 ก่อนเวรเริ่ม จึงเริ่มที่ 23:00 และทุกคนทำทั้งเวรจึงมีช่วงเดียว ถ้า 104 ถูกย้ายออกตอน 03:00 จะมีสองช่วง คือ 23:00 ถึง 03:00 ขาด 1 คน และ 03:00 ถึง 07:00 ขาด 2 คน ส่วน `headcount_gap` เป็น 2 Gap ที่บันทึกก่อนรอบ 4 มี `evaluated_from` เป็น `null` และ `intervals` เป็น `[]` ซึ่งหมายถึงขาดทั้งเวรตามตัวเลขสรุป
* `assigned_count` คือจำนวนคนที่เคสนี้จัดเข้าเวรแล้ว นับแบบเดียวกับ "ได้เข้าเวรแล้ว" ของข้อ 5.3 (`case_facts_service.assigned_staff_ids()`) เคสยังขาดคนอีก `max(gap.headcount_gap - assigned_count, 0)` หน้า `approvals` ใช้ค่านี้บอกว่าเคสของแต่ละคำขอยังขาดกี่คน (PR 5) ค่านี้นับเฉพาะจำนวนคน เคสที่ได้ 0 ยังรออนุมัติอยู่ได้เมื่อยังขาด Role หรือ Skill
* `candidates` เป็น `[]` จนกว่า Solver จะบันทึก Plan ใช้ Plan ที่ `id` มากสุดของเคส (Seam 1) เรียงตาม `rank`
* `outreach_status` เป็น `null` จนกว่าจะมี Outreach ของผู้สมัครคนนั้น ถ้ามีหลายแถวใช้แถวที่ `id` มากสุด
* `score` คือคะแนนรายพจน์ของผู้สมัคร คำนวณตอนอ่านจาก Snapshot ของ Plan ล่าสุดเท่านั้น (ข้อ 6.15) เป็น `null` สำหรับ Plan ที่สร้างก่อน PR E และสำหรับผู้สมัครที่ตัวเลขใน Snapshot ไม่ครบหรือไม่ลงกัน (บันทึก Log ระดับ Error ไม่ทำให้ทั้งหน้าล้ม)
* `home_ward_id`, `home_ward_name` คือหอบ้านของผู้สมัคร (`STAFF.home_ward_id` กับชื่อของ `WARD` ในคำสั่งเดียวกับชื่อพนักงาน) เทียบกับ `shift.ward_id` เพื่อดูว่ามาจากหออื่นหรือไม่ ส่งทุกคนตั้งแต่ PR C1 (ข้อ 6.19)
* `cover_start_at`, `cover_end_at` คือช่วงที่ผู้สมัครมาทำได้ อ่านจาก `CANDIDATE_ITEMS` ตรง ๆ (ข้อ 6.20) ว่างทั้งคู่ = ทั้งเวร `source_assignment` เป็น `null` เมื่อ `source_assignment_id` ว่าง (ไม่ใช่การย้าย) ไม่เช่นนั้นเป็น `{assignment_id, shift_id, ward_id, ward_name}` ของแถว Roster ต้นทาง (หอของเวรนั้น) อ่านด้วย Query เดียวสำหรับทุกผู้สมัคร (PR T1; `create_plan()` เขียนค่าจาก `_covers()` ซึ่งตั้งแต่ PR C2 ให้ `source_assignment_id` กับคนที่ย้ายทั้งเวร (`cover_*` ว่าง) และตั้งแต่ PR C3 ให้ `cover_start_at` และ `cover_end_at` ด้วยเมื่อย้ายบางส่วนของเวร (เริ่มกลางเวรปลายทาง) ว่างทั้งสามช่องสำหรับคนอื่น PR T4)
* `explanation` คือประโยคจาก LLM ของ Plan ล่าสุด (ข้อ 6.15) อ่านจากแถวล่าสุดของ `RANK_EXPLANATION` ของ Plan นั้น (ไม่เรียก LLM) เป็น `null` เมื่อไม่มี Plan หรือ Plan นั้นไม่มีแถว (`LLM_ENABLED` ปิด, Plan เก่า) `status` เป็น `PENDING` (รอ Job), `READY` (มี `text`, `provider` เป็น `fake` หรือ `bedrock`, `model_id` เป็น `null` ของ `fake`) หรือ `UNAVAILABLE` (`FAILED` หรือ `SKIPPED`) `text`, `provider` และ `model_id` เป็น `null` เมื่อไม่ใช่ `READY` ไม่คืนเหตุผลที่ล้มเหลว, Token หรือ Payload
* `partial_plan` (รอบ 4 PR T4) เป็น `true` เมื่อ Wave แรกของ Plan ล่าสุดมาจากแผนบางส่วน (ไม่มีกลุ่มใดครอบทุกเป้าหมาย ข้อ 6.20) อ่านจาก `input_snapshot.partial_plan` ของ Plan นั้น เป็น `false` เมื่อไม่มี Plan หรือ Plan เก่าที่ไม่มี key นี้
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
  `required_approver_role` (อาจเป็น `null`), `approval_mode`, `is_pending` และ `requested_at`, `expires_at` (ISO 8601, `+07:00`)
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
      "actual_start_at": null,
      "actual_end_at": null,
      "transferred_from_assignment_id": null,
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
* `shift_id` (หรือ `staff_id` ตั้งแต่รอบ 3 ข้อ 9.5 อย่างใดอย่างหนึ่ง) เป็นจำนวนเต็มในช่วง `bigint` (1 ถึง 9223372036854775807) ไม่ส่งหรือค่าไม่ถูกต้อง → `422`
* ไม่มี Shift ID นั้น → `404` เวรที่มีอยู่แต่ไม่มีแถว Roster ตอบ `200` พร้อม `assignments: []`
  ตรวจตามลำดับ `401` → `422` → `404`
* เวรที่ `is_active = false` ยังตอบ `200` พร้อมแถวของมัน ดูจาก `shift.is_active`
* `assignments` คือ**แถว** `ROSTER_ASSIGNMENT` ไม่ใช่รายชื่อคน คืนทุกสถานะตามที่เก็บ (`CANCELLED`, `PENDING_APPROVAL`,
  `COMPLETED` ด้วย) ไม่กรองและไม่รวมแถวซ้ำ คนเดียวกันมีได้หลายแถวในเวรเดียว เพราะตารางไม่มี UNIQUE ที่
  (`staff_id`, `shift_id`) เรียงด้วย `id` จากน้อยไปมาก
* Route ไม่นับ Coverage: คนที่นับได้คือคนไม่ซ้ำที่มีแถว `ASSIGNED` หรือ `COMPLETED` (ข้อ 3, 6.18) `PENDING_APPROVAL` ไม่นับ
  ตัวเลข Gap ดูจาก `GET /cases/{id}`
* `status` คือค่าที่เก็บใน DB ไม่คำนวณจากเวลา Job ตั้งเวรที่จบแล้วเป็น `COMPLETED` ทุกรอบ (ข้อ 6.18) เวรที่เพิ่งจบจึงยังเป็น
  `ASSIGNED` ได้จนถึงรอบถัดไป ใช้ `shift.end_at` ดูว่าเวรจบแล้วหรือยัง
* `candidate_source` เป็น `null` สำหรับแถว `REGULAR`
* `staff_status` คือ `STAFF.status` คนที่ `INACTIVE` ยังอยู่ในรายการถ้ายังมีแถว Roster
  (Coverage ไม่กรอง `STAFF.status` ซ้ำ ตาม `database-schema.md`)
* `home_ward_id` / `home_ward_name` คือหอประจำของพนักงาน เทียบกับ `shift.ward_id` เพื่อดูว่ามาจากหออื่น
* ไม่ส่ง `email` / `password_hash` และยังไม่บอกว่าคนที่ `ASSIGNED` มี `STAFF_UNAVAILABILITY` ชนเวรหรือไม่ (ข้อ 12)
* ค่า `status` ที่ไม่อยู่ใน `RosterStatus` (คอลัมน์ไม่มี CHECK ตาม D8) ทำให้ตอบ `500` ไม่ซ่อนแถวนั้นเงียบ ๆ
* Route / `roster_service.get_shift_roster()` ไม่เขียน DB, Audit, Commit, Explicit Flush และไม่ล็อกแถว จึงไม่ขวางการรับ Event
  อ่านได้เฉพาะข้อมูลที่ Commit แล้ว แถวของผู้มาแทนจึงปรากฏพร้อมกับเคสเป็น `RESOLVED`

### 9.4 API และหน้าเว็บที่รอบ 2 เปลี่ยน

ทุกแถวทำแล้วในรอบ 2 (PR W, T, T2 และ H) ข้อนี้เก็บไว้เป็นรายการว่ารอบ 2 เปลี่ยน API และหน้าเว็บตรงไหนบ้าง

| Route หรือหน้า | สิ่งที่เปลี่ยน | PR |
|---|---|---|
| `GET /cases?status=MANUAL_HANDOFF,FAILED` (ใหม่, ต้องมี `X-Demo-User`) | คืน List ของ `{id, status, shift_id, ward_id, required_replacement_time, created_at, headcount_gap, assigned_count, can_manage}` เรียงตาม `id` เฉพาะเคสของหอที่ผู้เรียกเป็น Head Nurse `headcount_gap` เป็น `null` เมื่อเคสยังไม่มีแถว Gap `can_manage` เป็นจริงเฉพาะ `MANUAL_HANDOFF` `status` เป็นค่าบังคับ รับทั้งแบบคั่นจุลภาคและแบบส่งซ้ำ ไม่ส่งหรือค่าที่ไม่ใช่ `CaseStatus` ได้ `422` ผู้เรียกที่ไม่ใช่ Head Nurse ได้ `403` Head Nurse ของหออื่นได้ List ว่าง | H (ทำแล้ว) |
| `GET /cases/{id}/handoff/candidates` (ใหม่) | พนักงาน Active ของหอของเวร `{staff_id, first_name, last_name, role_id, role_name, blocking_rules, other_case_ids}` `blocking_rules` คือรหัส Hard Rules ที่ไม่ผ่านตอนอ่าน (ไม่ล็อก) `other_case_ids` คือเคสที่กำลังเดินซึ่งคนนั้นมี Offer ที่ยังมีผล `404` / `403` ตามลำดับ | H (ทำแล้ว) |
| `POST /cases/{id}/handoff/assignments` (ใหม่) | Body `{staff_id, reason?, confirm_conflicts?}` คืน `{manual_assignment_id, assignment_id, staff_id, case_id, case_status, cancelled_outreach_ids}` ลำดับ Error: `404` เคสไม่มี → `403` Role หรือหอ → `409` เคสไม่อยู่ `MANUAL_HANDOFF` → `422` คนที่ไม่ใช่พนักงาน Active ของหอ → `409` ไม่ผ่าน Hard Rules (`detail = {code: "HARD_RULES_FAILED", message, failed_rules}`) → `422` เหตุผลยาวเกิน 500 → `409` มี Offer ในเคสอื่นที่ขัดและยังไม่ส่ง `confirm_conflicts: true` (`detail = {code: "CONFLICTING_OFFERS", message, case_ids}`) | H (ทำแล้ว) |
| `POST /cases/{id}/handoff/close` (ใหม่) | Body `{reason}` คืน `{case_id, case_status}` ลำดับ Error: `404` → `403` → `409` เคสไม่อยู่ `MANUAL_HANDOFF` → `422` เหตุผลว่างหรือยาวเกิน 500 | H (ทำแล้ว) |
| หน้า `/handoff` (ใหม่) | ทำในชื่อ Head Nurse 900 รายการเคสจาก `GET /cases?status=MANUAL_HANDOFF,FAILED` เคส `FAILED` แสดงว่าจัดการไม่ได้ กด Manage แล้วเห็นพนักงานของหอพร้อมเหตุที่จัดไม่ได้ (รหัสกฎแปลเป็นข้อความ) ปุ่ม Assign ของคนที่ติดกฎกดไม่ได้ ช่องหมายเหตุไม่บังคับ เมื่อได้ `CONFLICTING_OFFERS` แสดงคำเตือนพร้อมเลขเคสและปุ่มยืนยันที่ส่ง `confirm_conflicts: true` เมื่อได้ `HARD_RULES_FAILED` แสดงกฎที่ติด ช่องเหตุผลของการปิดเคสบังคับ ไม่เกิน 500 ตัวอักษร ส่งค่าที่ตัดช่องว่างแล้ว ลิงก์ "Handoff" อยู่ในแถบเมนู | H (ทำแล้ว) |
| `POST /approvals/{id}/decision` | ผู้กดที่ไม่ใช่ Head Nurse ของหอเดียวกับเวรได้ `403` พร้อม `detail` บอกเหตุ | W (ทำแล้ว) |
| `POST /approvals/{id}/decision` | กดเมื่อ `clock.now() >= expires_at` ได้ `409` | T |
| `GET /approvals` | เพิ่มเส้นตายของคำขอ (`expires_at`) | T |
| หน้า `approvals` | คอลัมน์ "Decide by" แสดง `expires_at` ของคำขอเป็นเวลา Bangkok หน้าเว็บไม่รู้ Clock ของ Backend จึงไม่ปิดปุ่มเองเมื่อเลยเส้นตาย คำขอที่เลยเส้นตายหายจากรายการในรอบอ่านถัดไป และถ้ากดทันก่อนนั้น API ตอบ `409` ซึ่งหน้าแสดงข้อความ | T2 (ทำแล้ว) |
| `POST /demo/clock/advance` และหน้า `demo/control` | เพิ่ม `timed_out_approval_request_ids` | T |
| `GET /cases/{id}` และหน้า `cases/[id]` | `candidates[].stage` มีค่าใหม่ `APPROVAL_TIMEOUT` และอ่านจากรอบล่าสุดของผู้สมัคร คนที่ได้เข้าเวรจากการจัดเองถูกนับใน `assigned_count` | T และ H |
| รายการ Offer ของหน้า `line-sim` | `cancellation_reason` มีค่าใหม่ `APPROVAL_TIMEOUT` และยังเป็น `CONFLICTING_ASSIGNMENT` เมื่อเสียให้การจัดคนเอง | T และ H |

### 9.5 API และหน้าเว็บที่รอบ 3 เปลี่ยน

| Route หรือหน้า | สิ่งที่เปลี่ยน | PR |
|---|---|---|
| `GET /cases/{id}` | แต่ละ `candidates[]` มีช่อง `score` ตามข้อ 6.15 (`null` สำหรับ Plan ที่สร้างก่อน PR E) และช่อง `explanation` ระดับบนสุด (`null`, `PENDING`, `READY`, `UNAVAILABLE`) | E (ทำแล้ว), X (ทำแล้ว) |
| หน้า `cases/[id]` | แสดงคะแนนรายพจน์ เหตุผลแบบตายตัว และประโยคจาก LLM เมื่อพร้อม | E2 (ทำแล้ว ตัวเลขและเหตุผลแบบตายตัว), X (ทำแล้ว) |
| `POST /line/webhook` (ใหม่) | Webhook ของ LINE ไม่ใช้ `X-Demo-User` กันด้วยลายเซ็น ลำดับ: ลายเซ็นไม่ผ่าน `401` (ไม่เขียน DB) → ประมวลทีละ Event ในแต่ละ Transaction ของตัวเองตามข้อ 6.16: Event ซ้ำข้าม, `LINK <รหัส>` ไปทางผูกบัญชีก่อนตรวจการผูก, Postback ไปทางตอบ Offer → ตอบ `5xx` ถ้ามี Event ใดเจอ Error ที่ไม่คาดไว้ ไม่อย่างนั้น `200` (รวมการปฏิเสธทางธุรกิจ) | L (ทำแล้ว), K (ทำแล้ว ทาง `LINK`) |
| `GET /me/offers` (ใหม่, ต้องมี `X-Demo-User`) | คืน List ของ `OfferView` แบบเดียวกับ `GET /demo/line-sim/offers` ของพนักงานใน Header เท่านั้น ไม่รับ `staff_id` (ส่ง `staff_id` มาใน Query ถูกข้าม) | N (ทำแล้ว) |
| `POST /me/offers/{outreach_id}/response` (ใหม่, ต้องมี `X-Demo-User`) | Body `{response}` (`ACCEPT` หรือ `REJECT`) Body ห้ามมีช่องอื่น คืน `{outreach_id, outreach_status, case_id, case_status}` แบบเดียวกับ `POST /demo/line-sim/respond` Error: `401` Header, `409` เมื่อ `record_response()` ปฏิเสธ (`OpenOfferConflictError`), `503` พร้อม `Retry-After: 1` เมื่อล็อกไม่นิ่ง (`OutreachLockRetryError`), `422` เมื่อ Body มีช่องอื่นหรือ `outreach_id` ไม่ใช่ bigint บวก | N (ทำแล้ว) |
| หน้า `/me/offers` "ข้อเสนอเข้าเวรของฉัน" (ใหม่) | ตามข้อ 6.17 | N (ทำแล้ว) |
| `GET /roster` | ต้องส่ง `shift_id` หรือ `staff_id` อย่างใดอย่างหนึ่งพอดี ไม่ส่งหรือส่งทั้งคู่ได้ `422` (`detail` เป็นข้อความ) ทุกแถวมี `is_unavailable` (ข้อ 6.18) | R (ทำแล้ว) |
| `GET /roster?staff_id=` (ใหม่) | คืน `{staff: {id, first_name, last_name, staff_status, role_id, role_name, home_ward_id, home_ward_name}, assignments: [{id, status, assignment_type, candidate_source, actual_start_at, actual_end_at, transferred_from_assignment_id, shift: {id, ward_id, ward_name, shift_type, start_at, end_at, is_active}, is_unavailable, created_at, updated_at}]}` เรียงตามเวลาเริ่มจริง (ว่างใช้เวลาเริ่มเวร) แล้ว `id` ไม่มีพนักงาน ID นั้น `404` ไม่มีแถว `200` พร้อม List ว่าง | R (ทำแล้ว) |
| หน้า `roster` | แถวที่ `is_unavailable` เป็นจริงมีป้าย "On leave" ต่อท้ายสถานะ | R (ทำแล้ว) |
| `PATCH /unavailability/{id}` (ใหม่, ต้องมี `X-Demo-User`) | Body `{end_at}` คืน `{unavailability_id, staff_id, start_at, end_at, previous_end_at, overlapping_assignment_ids, overlapping_offers: [{outreach_id, case_id, status}]}` ลำดับ Error ตามข้อ 6.18 | R (ทำแล้ว) |

Path ของ `/me/offers` และ `/line/webhook` ตกลงใน PR 0 และไม่เปลี่ยนตลอดรอบ 3 ทุกแถวทำแล้ว ข้อนี้เก็บไว้เป็นรายการว่ารอบ 3 เปลี่ยน API และหน้าเว็บตรงไหนบ้าง

---

### 9.6 API และหน้าเว็บที่รอบ 4 เปลี่ยน

| Route หรือหน้า | สิ่งที่เปลี่ยน | PR |
|---|---|---|
| `GET /cases/{id}` | `gap` เพิ่ม `evaluated_from` (ว่างได้) และ `intervals` = List ของ `{start_at, end_at, headcount: {required_count, current_count, gap_count}, roles: [GapCount], skills: [GapCount]}` เรียงตามเวลา (List ว่างสำหรับ Gap ก่อนรอบ 4) ตัวเลขสรุปเดิมเป็นค่าที่ขาดมากที่สุด รูปคำตอบอยู่ข้อ 9.3 | T3 (ทำแล้ว) |
| `GET /cases/{id}` | แต่ละ `candidates[]` เพิ่ม `home_ward_id`, `home_ward_name`, `cover_start_at`, `cover_end_at` (ว่าง = ทั้งเวร) และ `source_assignment` = `{assignment_id, shift_id, ward_id, ward_name}` หรือ `null` (T1 ส่ง `cover_start_at`, `cover_end_at` และ `source_assignment` ซึ่งเป็น `null` จนกว่า C2 จะสร้างผู้สมัครจากการย้าย ส่วน C1 ส่ง `home_ward_id`, `home_ward_name` แล้ว C2 ทำให้ `source_assignment` มีค่าสำหรับผู้สมัครที่ย้ายทั้งเวร) | T1, C1, C2 (ทำแล้ว) |
| `GET /cases/{id}` | เพิ่ม `partial_plan` (boolean) เป็น `true` เมื่อ Wave แรกของ Plan ล่าสุดมาจากแผนบางส่วน (ข้อ 6.20) `false` เมื่อไม่มี Plan รูปคำตอบอยู่ข้อ 9.3 | T4 (ทำแล้ว) |
| `GET /approvals?pending=true` | แต่ละรายการเพิ่ม `home_ward_id`, `source_ward_id` (ว่างเมื่อไม่ใช่การย้าย), `wards` = List ของ `{ward_id, side, status}` (`status` = `PENDING` หรือ `APPROVED`) และ `supervisor_from` (เวลาที่ Supervisor เริ่มกดได้) | S |
| `GET /approvals/auto` (ใหม่, ต้องมี `X-Demo-User` ของ Head Nurse หรือ Supervisor) | คำขอที่ระบบอนุมัติเอง (`approval_mode = AUTO`) ของหอที่ผู้เรียกดูแล ใหม่สุดก่อน ไม่เกิน 50 รายการ รูปเดียวกับรายการของ `GET /approvals` บวก `decided_at` Head Nurse เห็นหอตัวเอง Supervisor เห็นทุกหอ ประวัติเป็นผลอนุมัติ รวมกรณี Execute ล้มเหลวตาม D11 จึงต้องดูสถานะเคสประกอบ | A (ทำแล้ว) |
| `POST /approvals/{id}/decision` | Body เพิ่ม `side` (ไม่บังคับ ตามข้อ 6.21) ผู้กดเป็น Supervisor ได้ตามข้อ 6.21 (`403` ถ้ากดก่อน `supervisor_from`) คำตอบเพิ่ม `outcome` = `ASSIGNED`, `WAITING_OTHER_WARD`, `REJECTED`, `TRANSFER_CANCELLED` หรือ `EXECUTION_FAILED` และ `reason` (`TransferFailureReason` หรือ `null`) และ `failed_rules` (List) ทุกผลตอบ `200` (R4-Q35, R4-Q42) `EXECUTION_FAILED` คือทางของ D11: อนุมัติแล้วแต่สร้าง Roster ไม่สำเร็จ และ `case_status` = `FAILED` `is_approved` ในคำตอบเปลี่ยนเป็น `bool` หรือ `null` และเท่ากับ `APPROVAL_REQUEST.is_approved` เสมอ: `WAITING_OTHER_WARD` เป็น `null` เพราะคำขอยังรอ, `REJECTED` เป็น `false`, `ASSIGNED` `TRANSFER_CANCELLED` และ `EXECUTION_FAILED` เป็น `true` **`is_approved = true` บอกแค่ว่าคนอนุมัติแล้ว ไม่ได้บอกว่าคนถูกจัดเวรหรือถูกย้ายแล้ว** ตัวอย่าง: คำขอย้าย 201 ที่อนุมัติครบแต่ตรวจเวรต้นทางไม่ผ่านมี `is_approved = true` แต่ 201 ยังอยู่หอ B ตัวอ่านที่ต้องรู้ว่าจัดเวรสำเร็จหรือไม่ (เช่น รายการประวัติของหน้า `approvals` และข้อความใน Timeline ของ U) ต้องอ่าน `outcome` และ `reason` หรือ Audit Action (`ASSIGNMENT_TRANSFERRED`, `TRANSFER_CHECK_FAILED`, `WORKFLOW_FAILED`) ห้ามอ่าน `is_approved` อย่างเดียว | S, C2 (ทำแล้ว) |
| หน้า `cases/[id]` | แสดง Gap รายช่วงเมื่อไม่ได้ขาดทั้งเวร, หอบ้านและเวรต้นทางของผู้สมัคร, ข้อความอธิบายอันดับเมื่อใช้แผนบางส่วน | T3, T4, U (ทำแล้ว) |
| หน้า `approvals` | หอบ้าน หอต้นทาง, สถานะของแต่ละหอ, เวลาที่ Supervisor เริ่มกดได้, รายการ "ระบบอนุมัติแทน", ผลยกเลิกตอนย้ายจริงพร้อมเหตุผล | U (ทำแล้ว) |
| หน้า `demo/control` | เลือกหอและเวรได้ | U (ทำแล้ว) |

ชื่อช่องในตารางนี้ตกลงใน PR 0 PR ที่ทำต้องเติมรูปของคำตอบลงข้อ 9.3 ใน PR เดียวกัน

### 9.7 API และหน้าเว็บที่รอบ 5 เปลี่ยน

| Route หรือหน้า | สิ่งที่เปลี่ยน | PR |
|---|---|---|
| `POST /me/attendance/check-in` (ใหม่) | Body `{shift_id}` ตัวตนจาก `X-Demo-User` ไม่รับ `staff_id` คืน `{attendance_id, shift_id, check_in_at, on_time, deadline}` `404` เมื่อไม่มีแถว Roster ของคนนั้นในเวรนั้น `422` เมื่ออยู่นอกขอบเวลา **ยกเว้น check-in ซ้ำ ซึ่งคืนแถวเดิมเสมอ** (หาแถวเดิมก่อนตรวจขอบเวลา ข้อ 6.24) | N1 (ทำแล้ว) |
| `POST /demo/attendance/check-in` (ใหม่) | Body `{staff_id, shift_id}` จำลองการ check-in คำตอบและ Error เหมือน Route ข้างบน รวมข้อยกเว้นของ check-in ซ้ำที่คืนแถวเดิม Audit `source = SIMULATED` | N1 (ทำแล้ว) |
| `POST /me/attendance/check-in` และ `POST /demo/attendance/check-in` (ต่อ) | check-in สายหลังขั้นที่ 2 ได้ `200` ตามเดิมแล้วคืนแถวใหม่ให้เคส ตอบ `409` เมื่อล็อกไม่นิ่งครบ 5 ครั้ง (ข้อ 6.11) ทั้งสอง Route | N2 (ทำแล้ว) |
| `POST /internal/merge-windows/close-due` และ `POST /demo/clock/advance` | คำตอบเพิ่ม `no_show_event_ids` (Event `NO_SHOW` ที่ Job เขียนในรอบนั้น) | N2 (ทำแล้ว) |
| `GET /me/offers` | `cancellation_reason` มีค่าใหม่ `NO_LONGER_NEEDED` สำหรับ Offer ที่คนมาสายทำให้เกิน | N2 (ทำแล้ว) |
| คำสั่ง check-in ทาง LINE | `CHECKIN <shift_id>` หรือปุ่ม `action=CHECK_IN&shift_id=<id>` ตัวตนจากบัญชีที่ผูกแล้ว กติกาเดียวกับ `POST /me/attendance/check-in` | H2 ทำแล้ว |
| `GET /me/handovers` (ใหม่) | Handover ของผู้เรียกจาก `X-Demo-User` เท่านั้น (ไม่สนใจ `staff_id` ใน Query) ใช้งานอยู่ก่อน แล้วตามด้วยประวัติ ล่าสุดก่อน แต่ละรายการ `{handover_id, roster_assignment_id, active, generated_at, content}` (`generated_at` เป็น `+07:00`) | H1 (ทำแล้ว) |
| `GET /cases/{id}` | เพิ่ม `handovers` = List ของรายการแบบเดียวกับข้างบน กติกาการอ่านเคสเดิมไม่เปลี่ยน | H1 (ทำแล้ว) |
| `GET /me/handovers` (ต่อ) | Cursor Pagination ของประวัติทำแล้วใน PR P1 ของรอบ 6 รูป API และปุ่มโหลดเพิ่มอยู่ข้อ 9.8 | P1 (ทำแล้ว) |
| `GET /clock` (ใหม่) | คืน `{now, frozen}` จาก `app.core.clock` อ่านอย่างเดียว ไม่ต้องมี `X-Demo-User` | U5 (ทำแล้ว) |
| หน้า `/me/offers` | ปุ่ม check-in ส่ง `POST /me/attendance/check-in` เวรให้เลือกคือเวรใน Seed ที่มีชื่อคนนั้นรวมกับเวรของ Handover ของคนนั้น ผลบอกทันหรือสายพร้อมเส้นตาย `404`, `422` และ `409` แสดงเป็นข้อความ และรายการ Handover จาก `/me/handovers` ที่ใช้งานอยู่ก่อนแล้วตามด้วยประวัติ | U5 (ทำแล้ว) |
| หน้า `demo/control` | ปุ่ม "Simulate check-in (demo)" ใช้หอ เวร และคนที่เลือกในกล่องเดียวกับการแจ้งลา ส่ง `POST /demo/attendance/check-in`; ผลของการเลื่อน Clock แสดง `no_show_event_ids` | U5 (ทำแล้ว) |
| หน้า `cases/[id]` | ส่วน "Handovers" แสดง `handovers` ของเคส | U5 (ทำแล้ว) |
| แถบเมนู | Demo Clock จาก `GET /clock` อ่านทุก 2 วินาที บอกว่าหยุดนิ่ง (Demo) หรือตามเวลาจริง | U5 (ทำแล้ว) |

ชื่อช่องในตารางนี้ตกลงใน PR 0 PR ที่ทำต้องเติมรูปของคำตอบลงข้อ 9.3 ใน PR เดียวกัน

### 9.8 API และหน้าเว็บที่รอบ 6 เปลี่ยน

| Route หรือหน้า | สิ่งที่เปลี่ยน | PR |
|---|---|---|
| `GET /dashboard` (ใหม่) | อ่านอย่างเดียว ตัวตนจาก `X-Demo-User` ขอบเขตตามหอของผู้ใช้ Supervisor เห็นทุกหอ คืน `{now, modes: {line_mode, llm_provider, llm_enabled}, wards: [ward_id], cases_by_status: [{status, count}], shortages: [{shift_id, ward_id, start_at, end_at, headcount_gap, role_gaps: [{name, gap_count}], skill_gaps: [{name, gap_count}], case_id}] (เวรที่ยังขาดในหน้าต่างเวลาข้อ 6.31 เรียงตาม `start_at` สูงสุด 20 `case_id` เป็น null ได้), pending_approvals: [{ward_id, count}], open_offers: {count}, recent_no_show: [{event_id, shift_id, staff_id, created_at}] (สูงสุด 10), llm_usage: null หรือ {date, used, cap, month_cost_usd, budget_usd}}` `llm_usage` เป็น null เมื่อ `LLM_ENABLED=false` ไม่เขียนฐานข้อมูล | F1 |
| `GET /gap/shifts` (ใหม่) | Query `ward_id` และ `date` (วันของ `start_at` ตามเวลา Asia/Bangkok) คืน List ของ `{shift_id, ward_id, start_at, end_at, required_staff, rostered_count, headcount_gap, case_id}` เฉพาะหอที่ผู้ใช้เห็นได้ `403` เมื่อขอหอที่ไม่เห็น `422` เมื่อขาด Query อ่านอย่างเดียว | F1 |
| `GET /gap/shifts/{shift_id}` (ใหม่) | `{shift_id, ward_id, start_at, end_at, evaluated_from, intervals, roster, case_id}` `intervals` รูปเดียวกับ Gap รายช่วงใน `GET /cases/{id}` (ข้อ 9.6) `roster` = `[{roster_assignment_id, staff_id, name, status, effective_start_at, effective_end_at, on_leave, checked_in}]` เรียก `assess_shift()` ไม่เขียนแถว Gap, Event, Audit หรือเคส `404` เมื่อไม่มีเวร | F1 |
| `GET /cases/{id}` | ช่อง `explanation` เมื่อมี Plan ที่มีผู้สมัคร: `{status, text, provider, model_id, can_request, request_blocked_reason}` โดย `status` เป็น `NOT_REQUESTED`, `PENDING`, `READY`, `UNAVAILABLE` (`FAILED`) หรือ `QUOTA_EXHAUSTED` (`SKIPPED` เหตุถึงเพดาน) และ `request_blocked_reason` เป็น null หรือ `QUOTA_EXHAUSTED`, `NOT_CONFIGURED`, `ALREADY_READY`, `PENDING`, `INVALID_INPUT`, `ATTEMPTS_EXHAUSTED` ยังเป็น null เมื่อไม่มี Plan หรือไม่มีผู้สมัคร ไม่คืน `failure_reason`, token หรือ Payload (กติกาข้อ 6.15 เดิม) | E1 |
| `POST /cases/{id}/explanation` (ใหม่) | ไม่มี Body ขอคำอธิบายของ Plan ล่าสุด คืนช่อง `explanation` ข้างบน **ผลตอบ:** `200` ถ้าแถวมีอยู่แล้วและเป็น `PENDING` หรือ `READY` คืนแถวเดิมโดยไม่เปลี่ยนอะไร; `200` ถ้ายังไม่มีแถวหรือแถวเป็น `FAILED`/`SKIPPED` ที่ขอใหม่ได้ ตั้งเป็น `PENDING` ไม่เรียก Bedrock ใน Request นี้ **ปฏิเสธ** (Error ใช้รูป `{"detail": {"code": ..., "message": ...}}` เหมือน `HANDOVER_SOURCE_UNAVAILABLE`) ตรวจตามลำดับนี้ โดยเหตุถาวรมาก่อนเหตุชั่วคราว เพื่อไม่บอกให้ลองพรุ่งนี้ในสิ่งที่พรุ่งนี้ก็ไม่สำเร็จ: `404` `CASE_NOT_FOUND` เมื่อไม่มีเคสหรือ Plan; `409` `LLM_UNAVAILABLE` เมื่อ `LLM_ENABLED=false` ค่าตั้งไม่พร้อม หรือข้อมูลไม่ถูกต้อง; `409` `LLM_ATTEMPTS_EXHAUSTED` เมื่อแถวใช้ Attempt ครบ `LLM_MAX_ATTEMPTS_PER_ROW` แล้ว (แถวคงเป็น `FAILED` และ `GET` ได้ `can_request` เท็จกับ `request_blocked_reason = ATTEMPTS_EXHAUSTED`); `429` `LLM_QUOTA_EXHAUSTED` เมื่อถึงเพดานรายวัน **คำขอที่ถูกปฏิเสธทุกแบบไม่ตั้งแถวเป็น `PENDING` ไม่เพิ่ม Attempt ไม่สร้างแถวใหม่ และไม่ใช้โควตา** | E1 |
| `GET /cases/{id}` (ต่อ) | ช่อง `summary` (สรุปเคส): null หรือ `{current: {summary_id, status, text, generated_at, stale, can_request, request_blocked_reason}, history: [{summary_id, text, generated_at}]}` `stale` เป็นจริงเมื่อ Snapshot ของข้อมูลเปลี่ยนจากตอนสรุป | S |
| `POST /cases/{id}/summary` (ใหม่) | ขอสรุปของ Snapshot ปัจจุบัน ผลตอบและ Error เดียวกับ `POST /cases/{id}/explanation` ทุกข้อ (`200`; `404` `CASE_NOT_FOUND`; `409` `LLM_UNAVAILABLE`; `409` `LLM_ATTEMPTS_EXHAUSTED` เมื่อแถวของ Snapshot นี้ใช้ Attempt ครบ; `429` `LLM_QUOTA_EXHAUSTED`) และคำขอที่ถูกปฏิเสธไม่เปลี่ยนแถว ไม่เพิ่ม Attempt ไม่ใช้โควตา ถ้า Snapshot เดิมมีสรุป `READY` แล้ว คืนฉบับเดิมไม่เรียกใหม่ ถ้าข้อมูลเปลี่ยน Snapshot ใหม่ได้แถวใหม่ที่มี Attempt นับใหม่ และฉบับเก่าไปอยู่ใน `history` | S |
| `GET /me/handovers` (ต่อ) | `limit` ค่าเริ่มต้น 20 ช่วง 1–100 และ `cursor` ยาวไม่เกิน 512 ตัวอักษร คืน `{active: HandoverView[], history: HandoverView[], next_cursor: string หรือ null}`; active = Roster `ASSIGNED` และยังไม่ถึงเวลาจบจริง แสดงครบทุกหน้า history อ่านสูงสุด limit + 1 แล้วคืนไม่เกิน limit เรียง `generated_at DESC, handover_id DESC` Cursor Base64 ของ `{v:1, staff, at, id}` ผูกกับผู้ใช้และ boundary (ไม่ใช่สิทธิ์เข้าถึง) ผิดรูปแบบ/คนอื่น/ขอบ Query ผิดตอบ 422 ตัวตนมาจาก `X-Demo-User` เท่านั้น ไม่สน `staff_id` ใน Query ไม่เขียนข้อมูล หน้าเว็บโหลดประวัติเพิ่มเมื่อกด “Load more history” และ polling อ่าน prefix ที่โหลดแล้วใหม่จากหน้าแรกเพื่อไม่ค้างสถานะเก่า เมื่ออ่านล้มเก็บชุดเดิมพร้อมคำเตือน; เปลี่ยนผู้ใช้หรือออกจากหน้าจะยกเลิกคำขอและล้างข้อมูลเดิม; API หน้าเคสไม่เปลี่ยน | P1 |
| คำตอบของ LINE ต่อข้อความที่ไม่ใช่ปุ่ม | ข้อความแยกสี่กรณีตาม Binding และสถานะ Offer ของผู้ส่ง ไม่เปลี่ยน Offer (ข้อ 6.29) | I |
| หน้า `/` | เปลี่ยนจาก System check เป็น Dashboard จาก `GET /dashboard` เก็บสถานะ API/ฐานข้อมูลไว้เป็นแถบเล็ก | F2 |
| หน้า `/gap` (ใหม่) | เลือกหอ วันที่ และเวร แสดง Gap รายช่วงและ Roster อ่านอย่างเดียว ไม่มีปุ่มสร้าง Event | F2 |
| หน้า `cases/[id]` | ปุ่ม "หน้าสรุปด้วย AI" ปิดเมื่อ `can_request` เป็นเท็จ ถึงเพดานแสดงข้อความตามข้อ 6.27 ส่วนสรุปเคสกับประวัติและป้ายล้าสมัย | E2, S |
| แถบเมนู | ลิงก์ไป Dashboard และ `/gap` | F2 |

ชื่อช่องในตารางนี้ตกลงใน PR 0 ผู้ทำ E1, S และ F1 ยืนยันรูปละเอียดในรีวิว PR ของตัวเอง แต่ห้ามเปลี่ยนความหมายของช่องที่ระบุ และต้องเติมรูปของคำตอบลงข้อ 9.3 ใน PR เดียวกัน

---

## 10. Golden Case

### 10.1 สถานการณ์

พยาบาล RN ในหอ ICU แจ้งลาป่วยกะทันหันก่อนเวรดึก 2 ชั่วโมง ทำให้กำลังคนต่ำกว่าที่ต้องการ 1 คน ทักษะ ICU ยังครบ ระบบส่ง Offer ให้ผู้สมัครจากหอเดียวกันสองคนใน Wave แรก และได้คนแทนจากคนแรกที่ตอบรับ

### 10.2 ข้อมูล Seed

**เวลา** Clock ของ Demo = `D 21:00 +07:00` (D = วันที่ Demo)

**Master Data**

| ตาราง | ข้อมูล |
|---|---|
| WARD | 1 = ICU, 2 = Medicine, 3 = Float Pool (`is_float_pool = true`, ไม่มีเวรของตัวเอง) (2 และ 3 จากรอบ 4 PR W4) |
| ROLE | 1 = RN, 2 = HEAD_NURSE, 3 = SUPERVISOR (รอบ 4 PR S) |
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

**STAFF ของหออื่น** (รอบ 4 PR W4, ทั้งหมด `ACTIVE`, ไฟล์ `seed/scenarios/multi_ward.py`)

| id | ชื่อ | role | หอบ้าน | skill |
|---|---|---|---|---|
| 301 | Niran | RN | Medicine | ICU, BLS |
| 302 | Kanya | RN | Medicine | BLS |
| 401 | Somchai | RN | Float Pool | ICU, BLS |
| 902 | Ratana | HEAD_NURSE | Medicine | — |
| 950 | Prasert | SUPERVISOR | Medicine | — |

ทั้งห้าคนอยู่เวร 21 และ 22 ของ Medicine ซึ่งเวลาตรงกับเวร 1 และ 2 จึงไม่เข้า Pool ของเวร ICU ตั้งแต่ PR C1 (ข้อ 6.19) แต่ตั้งแต่ PR C2 ที่ให้ย้ายทั้งเวรได้ ทั้งห้าคนเข้า Pool ของเวร ICU เพราะเวลาเท่ากัน Medicine มีคนพอดีเป้าหมาย 301, 302 และ 401 ถูกข้ามด้วย `SOURCE_WARD_MINIMUM_VIOLATION` ส่วน 902 และ 950 ถูกข้ามด้วย `ROLE_MISMATCH` รายการผู้สมัครของ Golden Case เท่าเดิม (201, 202, 203) และ Gap เท่าเดิม เพิ่มเฉพาะรายการ `skipped` C3 ไม่เพิ่มสถานการณ์ Demo ใหม่ Medicine ยังมีแถวที่เวลาเท่าเวร ICU จึงยังถูกข้ามเหมือนเดิม และกติกาย้ายกลางเวรของ C3 ทดสอบด้วยข้อมูลใน Test

**SHIFT**
* 1 = ICU, `NIGHT`, `D 23:00` – `D+1 07:00`, `patient_count = 10`
* 2 = ICU, `DAY`, `D+2 07:00` – `D+2 15:00`, `patient_count = 2` (ใช้กับ Test ข้อ 10.4 เท่านั้น)
* 21 = Medicine, `NIGHT` และ 22 = Medicine, `DAY` เวลาเดียวกับเวร 1 และ 2, `patient_count = 10` (รอบ 4 PR W4, ID สูงเพื่อไม่ชนกับเวรที่ Scenario และ Test สร้าง)
* ทุกเวรตั้ง `merge_window_seconds = 0` Event จึงถูกตัดสินใน Request ที่แจ้ง (ข้อ 3.2) เวรที่มี Window อยู่ใน Scenario ของ Test เท่านั้น (ข้อ 3.10)

**STAFFING_REQUIREMENTS**
* 1 = shift 1, `required_staff = 5`, `minimum_staff = 4`, ROLE: RN = 5, SKILL: ICU = 2
* 2 = shift 2, `required_staff = 1`, `minimum_staff = 1`, ROLE: RN = 1, ไม่มี SKILL
* 21, 22 = shift 21, 22, `required_staff = 5`, `minimum_staff = 4`, ROLE: RN = 3, ไม่มี SKILL (ไม่มี Gap)

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
* 301, 302, 401, 902, 950 ในเวร 21 และ 22: `ASSIGNED`, `REGULAR`

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
| Solver | Plan มี 201, 202, 203 ตามลำดับ กลุ่มของ Wave แรกคือ 201 กับ 202 (`plan_penalty` = 2023 เท่ากับกลุ่ม 201 กับ 203 จึงเลือก `staff_id` น้อยกว่า) 201 ได้แถว `ROLE` กับ `HEADCOUNT` แบบ `PRIMARY` และ 202 แบบ `RESERVE` `solver_status` = `OPTIMAL` |
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
| สิทธิ์อ่าน Roster ตาม Ward | Skeleton ให้ Staff ที่ Active ทุกคนอ่าน `GET /roster` ได้ทุกเวร การจำกัด เช่น Head Nurse อ่านได้เฉพาะหอของตัวเอง รอ Login จริง แล้วตอบ `403` |
| `NO_SHOW` | ย้ายไปรอบ 5 ข้อ 6.24 (PR N1, N2) เส้นตายผูกกับแถว Roster และ `NO_SHOW` มีสองขั้น (Event ก่อน แล้วลงผลตอนปิด Window) |
| Auto-Approval | ย้ายไปรอบ 4 ข้อ 6.22 (PR A) ความหมายของ `ratio` และ `incoming_count` เปลี่ยนเป็นภาระของคนกด ไม่ใช่ Ratio ผู้ป่วย |
| รูปแบบ `required_approver_role` | ยังเก็บ `ROLE.id` ของ HEAD_NURSE รอบ 4 ไม่เปลี่ยนคอลัมน์นี้ Supervisor ผ่านตัวตรวจสิทธิ์ตัวใหม่ (ข้อ 6.21) |
| LangGraph | ย้ายไปรอบ 5 ข้อ 6.23 (PR G) ห่อแค่การเดินระหว่าง Handler ไม่ใช้ Checkpointer เอกสาร "ทางเลือก" ที่เคยอ้างไม่มีใน repo ร่างรอบ 5 เป็นที่ตกลงแทน |

เรื่องที่ย้ายออกเพราะรอบ 3 ทำแล้ว

| เรื่อง | ทำใน | ตอนนี้อยู่ข้อ |
|---|---|---|
| การตั้ง Roster เป็น `COMPLETED` | รอบ 3 PR R | 6.18 |
| ธง "อยู่เวรแต่ไม่พร้อม" ใน `GET /roster` | รอบ 3 PR R | 6.18 |
| `GET /roster?staff_id=` | รอบ 3 PR R | 6.18, 9.5 |
| แก้ `end_at` ของ `STAFF_UNAVAILABILITY` | รอบ 3 PR R | 6.18, 9.5 |

เรื่องที่ย้ายออกเพราะรอบ 2 ทำแล้ว

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
| 2026-10-13 | รอบ 2 PR 0: ย้าย Contract ของรอบ 2 เข้าไฟล์นี้ตามร่างรอบ 2 (PR #50): เพิ่มส่วน "สถานะของรอบ 2", เส้น T8 (`MANUAL_HANDOFF` → `RESOLVED`) และ T9 (`MANUAL_HANDOFF` → `UNRESOLVED`) ในข้อ 5.1 และใน `transitions.py` พร้อม Test, ข้อ 6.12 เส้นออกจาก `MANUAL_HANDOFF`, ข้อ 6.13 Timeout ของการอนุมัติ, ข้อ 6.14 Solver แบบ OR-Tools, ข้อ 9.4 API ที่จะเปลี่ยน, Audit Action ใหม่สี่ตัว (`APPROVAL_TIMEOUT`, `MANUAL_ASSIGNMENT_CREATED`, `CASE_CLOSED_UNRESOLVED`, `OFFER_CANCELLED_BY_ASSIGNMENT`) และเหตุผล `SOLVER_TIMEOUT` ใน `enums.py`; ข้อ 12 ย้ายสามเรื่องออก; กติกาที่มีป้าย **[รอบ 2]** ยังรอ PR ที่ระบุ; ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-13 | ตามรีวิว PR 0 ของรอบ 2: แก้ข้อ 4, 5.1, 5.2, 5.3 และ 6.12 ที่เขียนว่า T8 กับ T9 เป็นของ Head Nurse อย่างเดียว ให้ตรงกับข้อ 6.12 และแถว `CASE_CLOSED_UNRESOLVED` ของข้อ 7.1: T9 เดินได้โดยขั้นปิด Window เมื่อเคสใหม่ของเวรเปิด และ T8 เดินโดย Route จัดคนเองที่เรียก Orchestrator ใน Transaction เดียวกัน Handler กับ `recompute()` ยังไม่เดินสองเส้นนี้; เพิ่มตารางข้อกำหนดที่ยังไม่มี Test พร้อม PR ที่ต้องมี Test ในส่วน "สถานะของรอบ 2"; ใส่เลข PR #52; เอาเส้นคั่นระหว่างข้อ 9.3 กับ 9.4 ออก; ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-13 | รอบ 2 PR T: approval timeout 900 วินาที, เส้นตาย snapshot และ offer-specific outreach_id ใน Safety/Approval (migration b7d2f8a1c6e4); Job ตามลำดับ Offer → Approval → Recovery → Window; one retry หลัง first contacts ที่ส่งได้, Safety/Approval ใหม่ทุก attempt, หมดเวลาครั้งที่สองไม่ส่งครั้งที่สาม; API 409 ที่ now >= deadline ไม่เขียน timeout, stage/cancellation_reason APPROVAL_TIMEOUT และ demo result timed_out_approval_request_ids | คน 3 |
| 2026-10-13 | รอบ 2 PR W: การอนุมัติจำกัดหอ (R2-Q21, R2-Q53) `approval_service.decide()` รับ `home_ward_id` ของผู้กด เทียบกับ `ward_id` ของเวรด้วย `domain/staffing/ward_authority.manages_ward()` ถ้าไม่ตรงตอบ `403` ก่อนการตรวจ `409`; ข้อ 6.12, 9.2 และ 9.4 แก้ตาม; `GET /approvals` ไม่เปลี่ยน; ข้อมูล Seed มีหอเดียว ผลของ Test เดิมจึงไม่เปลี่ยน | คน 1 |
| 2026-10-13 | ตามรีวิว PR W: การอ่าน `SHIFT` ใน `_lock_decision()` ใช้ `populate_existing` เหมือนการอ่านตัวอื่นในฟังก์ชัน เพื่อไม่ให้ได้ `ward_id` ค่าเก่าจาก Session; เพิ่ม Test ว่าหน้า `approvals` แสดงข้อความของ `403` เมื่อ Head Nurse ต่างหอกด; ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-14 | รอบ 2 PR T2: หน้า `approvals` เพิ่มคอลัมน์ "Decide by" แสดงเส้นตายของคำขอ (`expires_at` จาก `GET /approvals` ของ PR T) (R2-Q30); ข้อ 9.4 แก้ตาม; ไม่แตะ Backend | คน 1 |
| 2026-10-14 | รอบ 2 PR B: Solver เลือกกลุ่มของ Wave แรกด้วยโมเดล CP-SAT ของ OR-Tools แทนการค้นแบบตัดกิ่ง (ข้อ 6.14) สามขั้น คือคะแนนต่ำสุด จำนวนคนน้อยสุด แล้วชุด `staff_id` น้อยสุด คะแนนคูณสเกลด้วย LCM ของตัวส่วน ไม่ปัดเศษ; `solve()` รับ `time_limit_seconds` และ `SolverResult` มี `status`; เพิ่ม `SOFT_CONSTRAINT_POLICY.solver_time_limit_seconds` (Seed = 3, Migration `c9e4a7b2d5f8` ต่อจาก `b7d2f8a1c6e4`); `CANDIDATE_PLANS.solver_status` มาจาก Solver (Golden Path เป็น `OPTIMAL`), `UNKNOWN` พาเคสไป `MANUAL_HANDOFF` ด้วยเหตุผล `SOLVER_TIMEOUT`, `MODEL_INVALID` และตัวเลขที่ใหญ่เกินทำให้เคสเป็น `FAILED`; `SOLVER_VERSION` = `"cp-sat-v1"`; การค้นของรอบ 1 ย้ายไปเป็นตัวเทียบใน Test และผลที่ PR A บันทึกไว้ยังตรงครบ 229 โจทย์; เพิ่ม `tests/perf` และ Workflow `Solver timing` สำหรับวัดเวลา ผลวัดอยู่ร่างรอบ 2 ข้อ 4.8; เพิ่ม Dependency `ortools` ทุกคนต้องสร้าง container ของ Backend ใหม่ | คน 2 |
| 2026-10-14 | รอบ 2 PR H: ตาราง `manual_assignment` (Migration `b7d3e5a1c9f2` ต่อจากของ PR B), ตัวอ่านกลางนับคนที่จัดเอง, `orchestrator.leave_handoff()` สำหรับ T8 และ T9, ตัวยกเลิก Offer ที่ใช้ร่วมกับการอนุมัติ (ไม่แตะ Offer `SENT` ที่เลยเส้นตาย และเขียน `OFFER_CANCELLED_BY_ASSIGNMENT` ในเคสที่เสีย Offer), Route สี่ตัวในข้อ 9.4, เคสใหม่ของเวรปิดเคสเดิมที่ `MANUAL_HANDOFF`, หน้า `/handoff` และลิงก์ในแถบเมนู; ข้อ 6.12, 7.1 และ 9.4 แก้ตาม | คน 1 |
| 2026-10-14 | ตามรีวิว PR H: การจัดคนเองตอบผลที่ Commit แล้วแม้การแจ้งเคสอื่นหลัง Commit จะพัง (บันทึกใน log แล้วให้ Job เก็บตก เหมือน PR T); รายการเคสอ่านจำนวนคนที่ได้เข้าเวรและ Gap ของทุกเคสในจำนวนคำสั่งคงที่ ผ่าน `case_facts_service.assigned_staff_ids_by_case()` ซึ่งเป็นตัวอ่านตัวเดียวกับ `assigned_staff_ids()`; หน้า `/handoff` ไม่แสดงรายชื่อของเคสที่ตอบช้ากว่าเคสที่เลือกอยู่, อ่านข้อความของ Error แบบ List และแจ้งเมื่อเคสที่จัดการอยู่ถูกคนอื่นจัดหรือปิดไปแล้ว | คน 1 |
| 2026-10-14 | ปิดรอบ 2: ส่วน "สถานะของรอบ 2" บอกว่าเสร็จแล้ว และตารางข้อกำหนดที่เคยยังไม่มี Test เปลี่ยนเป็นตารางที่ชี้ไฟล์ Test ของแต่ละข้อ (ตรวจแล้วว่ามีครบ); ลบป้าย "[รอบ 2 · PR X]" ที่แปลว่ายังไม่มีโค้ดออกทั้งหมด ที่มาของแต่ละกติกาดูจากตาราง "สถานะของรอบ 2"; ข้อ 4 แถว `UNRESOLVED`, ข้อ 7.1, ข้อ 9.4 และข้อ 12 แก้ตาม; ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-14 | ตามรีวิว PR ปิดรอบ 2: วันที่อัปเดตบนสุดเป็น 2026-10-14; หัวข้อ 9.4 เป็นอดีต; หมายเหตุลำดับ Lock ในข้อ 6.11 ที่เขียนว่ายังไม่มี Test เปลี่ยนเป็นรายการ Test สอง Connection ของแต่ละกรณี ทั้งของรอบ 1 และรอบ 2; ตาราง Test ของ PR H ระบุชื่อฟังก์ชัน | คน 1 |
| 2026-10-14 | รอบ 3 PR 0: ส่วน "สถานะของรอบ 3" พร้อมตาราง PR, ลำดับ merge และ Test ของข้อกำหนดที่พังเงียบได้; ข้อ 6.15 คำอธิบายอันดับ, 6.16 LINE จริง, 6.17 หน้าเว็บพยาบาลและตัวตนจำลอง; ข้อ 7.1 เพิ่ม `OFFER_DELIVERY_FAILED`, `LINE_ACCOUNT_LINKED`, `LINE_ACCOUNT_UNLINKED`; ข้อ 9 และ 9.5 เพิ่ม `POST /line/webhook`, `GET /me/offers`, `POST /me/offers/{outreach_id}/response`; `enums.py` เพิ่มสาม Action และ `EntityType.CONTACTS` ยังไม่มีผู้เขียน ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-14 | ตามรีวิว PR 0 ของรอบ 3 (#61): ข้อ 6.15 กำหนด `value` ของทุกพจน์ (`candidate_count` เป็น 1, `candidate_source` เป็นตำแหน่งใน `source_order` เริ่มที่ 0); ข้อ 6.16 และ 9.5 กำหนดว่าแต่ละ Event ใน body มี Transaction และแถวกันซ้ำของตัวเอง, `LINK <รหัส>` ถูกประมวลก่อนตรวจการผูก และผ่านตารางกันซ้ำใน Transaction ของการผูก; ตารางสถานะของรอบ 3 ใส่ #61 | คน 1 |
| 2026-10-14 | รอบ 3 PR L (#62): โหมด LINE จริง, Webhook ตรวจลายเซ็นและเจ้าของ Offer, กันซ้ำหลังได้ Lock ที่นิ่ง, งานส่งในแถว Offer กับ Retry key/lease, ส่งหลัง Commit และ Job เก็บตก, `OFFER_DELIVERY_FAILED` ผ่าน Orchestrator; Migration `c6e9a2b4d8f1`; Setup และขอบเขตใน `docs/round3/pr-L-handoff.md` | คน 3 |
| 2026-10-14 | รอบ 3 PR E: `create_plan()` เก็บ `weights` (รวม `source_order`) และ `hours_this_week_exact`, `overtime_hours_exact`, `penalty_exact` เป็นข้อความ `"เศษ/ส่วน"` ใน `input_snapshot` (ไม่มี Migration); `penalties.candidate_penalty_terms()` เป็นสูตรเดียวของรายพจน์ และ `candidate_penalty()` เป็นผลรวมของมัน; `GET /cases/{id}` เพิ่ม `score` ในแต่ละ `candidates[]` คำนวณตอนอ่านจาก Snapshot ด้วย `Fraction` (`null` สำหรับ Plan ก่อน PR E; ผู้สมัครที่ Snapshot ไม่ครบหรือไม่ลงกันได้ `null` พร้อม Log ระดับ Error ไม่ทำให้ทั้งหน้าล้ม); ข้อ 6.15 เติมรูป Snapshot จริงและลำดับ `terms`, ข้อ 9.3 เพิ่มตัวอย่าง `score`, ข้อ 9.5 แถว E ทำแล้ว | คน 2 |
| 2026-10-14 | รอบ 3 PR R: Job ตั้ง Roster ของเวรที่จบแล้วเป็น `COMPLETED` (`roster_completion_service` ขั้นแรกของ `run_due_work()`); `COMPLETED` นับเหมือน `ASSIGNED` ใน `COMMITTED_ROSTER_STATUSES` และ `COVERING_ROSTER_STATUSES` (ใหม่ ใช้ใน Gap และ Threshold); `GET /roster?staff_id=` และธง `is_unavailable` พร้อมป้าย "On leave" ในหน้า `roster`; `PATCH /unavailability/{id}` แก้วันกลับพร้อม `UNAVAILABILITY_UPDATED` และบอกเวรกับ Offer ที่ทับ; ข้อ 3.4, 3.6, 3.8, 6.18 (ใหม่), 7.1, 9, 9.3, 9.5 และ 12 แก้ตาม | คน 1 |
| 2026-10-14 | ตามรีวิว PR R (#64): การตั้ง `COMPLETED` ข้ามแถวที่ยังมี Event กลุ่มพนักงานค้าง และการปิด Window รับแถว `COMPLETED` ด้วย การลาที่รับไว้ก่อนเวรจบจึงไม่ถูก `IGNORED`; เงื่อนไขทับของการลากับเวรเหลือหนึ่งตัวใน Python และหนึ่งตัวใน SQL พร้อม Test ที่เทียบกัน; ลำดับ Error ของ `PATCH /unavailability/{id}` ระบุว่า `422` ของรูป Body มาก่อน `404` และ `403`; ข้อ 6.18 ระบุว่า `409` ของการแจ้งลาเกิดเมื่อแถวเป็น `COMPLETED` แล้ว ไม่ใช่เมื่อเวรจบ | คน 1 |
| 2026-10-14 | มติทีมเรื่องการลองของจริงและ Deploy: PR D เลื่อนไปรอบ 6 (งานเดิมเก็บใน branch `feat/aws-test-environment`) และไม่เป็นเงื่อนไขของรอบ 3 อีก; LINE จริงในรอบ 3 ถึง 5 ลองผ่าน Named Cloudflare Tunnel บนเครื่องคน 3 เข้า `/line/webhook` ตรงตัว ไม่อยู่ใน repo และไม่อยู่ในชุด Deploy (ข้อ 6.16); PR X ใช้ `fake` ในรอบ 3 คน 2 ตรวจเครดิตและสิทธิ์โมเดลตอนนี้ Bedrock จริง IAM และ Budget ทำในรอบ 6 (ข้อ 6.15); ลำดับในรอบ 6 และเกณฑ์ปิดรอบ 3 อยู่ใน "สถานะของรอบ 3"; แถว D ในตาราง Test เป็นของรอบ 6 ลำดับ merge ของ PR อื่นไม่เปลี่ยน | คน 1 |
| 2026-10-14 | เปลี่ยนวิธีทดสอบ LINE จาก Named Tunnel เป็น Cloudflare Quick Tunnel เพราะไม่มีโดเมน: ไม่ต้องซื้อโดเมนหรือมี Tunnel credentials; URL ชั่วคราวต้องตั้งใหม่ใน LINE Developers เมื่อเปิดใหม่; ใช้ตัวกรอง HTTP ในเครื่องเปิดเฉพาะ `/line/webhook` แทน ingress ของ cloudflared ห้ามชี้ Tunnel เข้า Backend โดยตรง; เงื่อนไขผู้จัดและการเลื่อน AWS/Bedrock ไปรอบ 6 คงตามมติเดิม | คน 3 |
| 2026-10-14 | ตามรีวิว Quick Tunnel: ใช้ nginx config และชุดทดสอบที่รีวิวได้ใน `dev/line-webhook-proxy` เปิดเฉพาะ POST กับ raw URI `/line/webhook` ไม่อนุญาต query string/encoding/case/path variants; body limit 1 MiB; CI ตรวจ config จริงกับ fake upstream; บันทึกผลที่ยังไม่ครบเมื่อ Tunnel ขาดระหว่างทดสอบ | คน 3 |
| 2026-10-14 | รอบ 3 PR E2: หน้า `cases/[id]` แสดงคอลัมน์ Score และตารางรายพจน์ (`ScoreBreakdown`) ของผู้สมัครที่มี `score` เรียงพจน์จาก `points` มากไปน้อย เหตุผลแบบตายตัวต่อชื่อพจน์และต่อ `first_wave` อยู่ใน `SCORE_TERM_INFO` และ `FIRST_WAVE_INFO`; `score = null` แสดงอันดับตามเดิมไม่มีคะแนนและไม่เดาเหตุผล; หน้าไม่คำนวณคะแนนเอง `loadCase()` ตรวจรูปของ `score` | คน 2 |
| 2026-10-14 | ตามรีวิว PR E2 (#67): `loadCase()` ตรวจทุกพจน์ของ `score` (`name` เป็นข้อความ, `value`, `weight`, `points` เป็นตัวเลขจำกัด) ชื่อพจน์ที่ไม่รู้จักยังแสดงตามเดิม; เหตุผลของ `workload_imbalance` เป็นชั่วโมงตาม Roster ที่ Commit แล้วในสัปดาห์ ณ ตอนวางแผน (รวมเวรที่ยังไม่เริ่ม); หัวข้อเป็น "Score breakdown" และบอกว่าคะแนนเลือกกลุ่ม Wave แรก อันดับในกลุ่มเรียงตาม `ranking_key` | คน 2 |
| 2026-10-14 | รอบ 3 PR K: รหัส LINK อายุ 10 นาที เก็บ SHA-256 hash, ใช้/revoke ครั้งเดียวตาม Backend Clock, unique LINE UID; CLI เรียก Route ภายในที่ตรวจ Internal Secret; LINK ผ่าน dedup พร้อม Contact/Code/Audit ใน Transaction เดียว; unlink รักษาประวัติและ revoke รหัสเก่า; pending send ตรวจบัญชีเดิมก่อน retry; Migration `d7f0b3c5e9a2` ต่อจาก PR L, tests สอง Connection และ Handoff ใน `docs/round3/pr-K-handoff.md` | คน 3 |
| 2026-10-15 | รอบ 3 PR X: ประโยคอธิบายอันดับจาก LLM ผ่าน `llm_service` (ตัวเชื่อม `fake` และ `bedrock` ทดสอบแบบ Offline) เข้าคิวด้วยแถว `PENDING` ใน Transaction ของ Plan สร้างเฉพาะตอน Job tick ผ่าน Background Task ของ Route ภายใน (Claim/Lease, `attempts` ถาวรไม่เกิน `1 + LLM_MAX_RETRIES`, `LLM_CALL_LOG` ทุก Attempt); Payload มีแต่ตัวเลขและอันดับ; `GET /cases/{id}` เพิ่มช่อง `explanation` และหน้า `cases/[id]` แสดงประโยค; ตาราง `RANK_EXPLANATION` และ `LLM_CALL_LOG` กับ Enum `ExplanationStatus`, `LlmCallStatus` (Migration `e1a4c7f2b9d6` ต่อจาก PR K); Test ของข้อกำหนดที่พังเงียบได้ 6 ข้อ; Handoff ใน `docs/round3/pr-X-handoff.md` | คน 2 |
| 2026-10-15 | ตามรีวิว PR X (#70): Lease ของ Job อ่านเวลาจากนาฬิกาฐานข้อมูล ไม่ใช้ Demo Clock (ข้อยกเว้นของ D10 ในข้อ 6.15), ตรวจข้อความจาก LLM ปฏิเสธอักขระควบคุมทุกตัว (Unicode `Cc` ยกเว้นขึ้นบรรทัดใหม่) และตัวควบคุมทิศทางข้อความ, หน้า `cases/[id]` Poll ต่อเมื่อเคสสุดท้ายแล้วแต่ประโยคยัง `PENDING` | คน 2 |
| 2026-10-15 | รอบ 3 PR N: `GET /me/offers` และ `POST /me/offers/{outreach_id}/response` ใน `api/routes/me.py` อ่านด้วย `list_offers()` และตอบด้วย `record_response()` ผ่านตัวเดียวกับหน้าจำลอง (`api/offer_responses.answer_offer()`) ไม่รับ `staff_id` (Query ถูกข้าม Body ที่มีช่องอื่นได้ `422`); หน้า `/me/offers` เข้าด้วยตัวตนจำลองที่เก็บใน `localStorage` มีป้าย Demo mode และ Sign out ไม่มีตัวเลือกสลับพนักงาน เขียนชัดว่า Accept ยังไม่ใช่การได้เข้าเวร; ตาราง Offer ย้ายเป็น `components/outreach/OfferList.tsx` ใช้ร่วมกับ `demo/line-sim` ไม่มี Migration | คน 1 |
| 2026-10-15 | ปิดรอบ 3: PR ทุกตัวยกเว้น D เข้า `staging` ครบ (#60 ถึง #64 และ #67 ถึง #70 รวม #65, #66 ของมติเรื่อง D และ Tunnel); ส่วน "สถานะของรอบ 3" บอกว่าเสร็จแล้ว ใส่ #64 ในแถว R และเพิ่มตารางว่าอะไรทดสอบด้วย fake และอะไรผ่านบริการจริง (LINE จริงและ Bedrock จริงยังไม่ได้ลอง); ตาราง Test ของข้อกำหนดที่พังเงียบได้ชี้ไฟล์และชื่อ Test ที่ตรวจแล้วว่ามีจริง; ป้ายที่เหลือเป็น **[รอบ 6 · PR D]** ที่ข้อย่อยด่านของเครื่อง AWS ในข้อ 6.17 (ส่วนหน้าเว็บพยาบาลของข้อนั้นทำแล้วใน PR N); ข้อ 9.5 บอกว่าทุกแถวทำแล้ว ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-15 | รอบ 4 PR 0: ส่วน "สถานะของรอบ 4" พร้อมตาราง PR, ลำดับ merge และ Test ของข้อกำหนดที่พังเงียบได้; ข้อ 6.11 ลำดับ Lock ที่เพิ่ม (`WARD` ก่อน, สอง `SHIFT` ของการย้าย); ข้อ 6.19 Cross-Ward และการย้ายคน, 6.20 เวลาจริงของ Roster Gap รายช่วง Solver และ Safety พร้อมชื่อคอลัมน์, 6.21 ผู้อนุมัติสองหอและ Supervisor, 6.22 Auto-Approval; ข้อ 6.19 กติกาของ C2 เมื่ออนุมัติครบหลังเวรต้นทางเริ่ม (`SOURCE_SHIFT_STARTED` ที่ C3 ลบ); ข้อ 7.1 เพิ่ม `ASSIGNMENT_TRANSFERRED` (`from_status` เป็น `RosterStatus`), `TRANSFER_CHECK_FAILED`, `APPROVAL_WARD_APPROVED`; ข้อ 9.6 รวม `side` ใน Body ของการตัดสิน, `outcome` = `EXECUTION_FAILED` และความหมายของ `is_approved` ในคำตอบ; A รอ T1; ข้อ 12 Auto-Approval ย้ายมารอบ 4; `enums.py` เพิ่มสาม Action, `TransferFailureReason`, `ApprovalSide`, `ApproverCapacity`, `codes.py` เพิ่ม `SOURCE_SHIFT_TAKEN`, `constants.py` เพิ่ม `SUPERVISOR_ROLE` ยังไม่มีผู้เขียน ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-15 | รอบ 4 PR T1: `CANDIDATE_ITEMS` เพิ่ม `cover_start_at`, `cover_end_at`, `source_assignment_id` (CHECK ว่างทั้งคู่หรือมีทั้งคู่ และ start < end, revision `a9c3e7f1b5d2`); `CandidateContext.linked_duty` และ `hard_rule_service` (`Cover`, `check_staff(covers=...)`, `check_items()` ใช้ `_check()` เดียวกัน, ตัดแถวต้นทางที่ `cover_start_at`); `create_plan()` เขียนค่าว่างและเก็บใน Snapshot; `GET /cases/{id}` เพิ่ม `cover_start_at`, `cover_end_at`, `source_assignment` (ข้อ 6.20, 9.3, 9.6) | คน 2 |
| 2026-10-15 | รอบ 4 PR T2: เวลาจริงและ UNIQUE self-FK ของ Roster (migration `b8d4f1a6c2e9` ต่อจาก T1); ตัวอ่านเวลาร่วม, duty จากลิงก์การย้าย, Hard Rules ใช้แถวจริงควบคู่ duty และ Cover ของ T1, Snapshot/Job ปิดเวร/API/หน้า Roster ใช้เวลาจริง พร้อม tests ของส่วนที่ทำแล้ว การย้ายต่อ ข้ามสัปดาห์ และ migration round trip; ยังไม่เปิดการย้ายจริง (C2/C3) | คน 3 |
| 2026-10-15 | รอบ 4 PR A: Job อนุมัติอัตโนมัติเมื่อคิวเกิน `min(ratio × active Head Nurses, incoming_count)` ล็อก Ward และชุดรวมของคำขอก่อนตัดสินผ่าน `decide()` ใน Transaction เดียวของหอ; Cross-Ward, Float Pool และคนมีเวรต้นทางนับคิวแต่ไม่อนุมัติเอง; Audit Actor `system`, `approval_mode = AUTO`, `approver_id = NULL` พร้อมจำนวนคิว/ผู้อนุมัติ/เพดาน; `GET /approvals/auto` ประวัติ 50 รายการล่าสุดตามสิทธิ์หอ; ไม่มี Migration; Handoff `docs/round4/pr-A-handoff.md` | คน 3 |
| 2026-10-15 | ตามรีวิว PR A (#80): แยก `decide_automatic()` และส่ง Batch Context/รายการงานหลัง Commit โดยตรง ใช้ตัวตัดสินร่วมกับคนกด; ยืนยัน PostgreSQL `FOR NO KEY UPDATE`; ผล Job/Clock เพิ่มรายการ AUTO และหอที่ล้มเหลว; Test อนุมัติ AUTO แล้วไม่ถูก Timeout; ระบุ foreign-case recompute เป็น best-effort ไม่มีคิว retry โดยเฉพาะ และป้องกันการนับ failure ข้าม Thread | คน 3 |
| 2026-10-15 | รอบ 4 PR C1: `WARD.is_float_pool` (boolean, NOT NULL, default false, revision `c4e8a2f6d1b3` ต่อจาก `b8d4f1a6c2e9`); `create_plan()` ดึง Pool ผ่าน `_pool()`: คนหอเดียวกับเวรเสมอ บวกคนของหออื่นที่ `is_active` และไม่มีเวรที่ทับ `[start_at, end_at)` แบบครึ่งเปิดตามเวลาจริงของ Roster (เป็นการกรองก่อนล็อก ส่วน Hard Rules หลังล็อกเป็นตัวกันสุดท้าย); `source` = `SAME_WARD` / `FLOAT_POOL` / `CROSS_WARD` ตามหอบ้าน; `GET /cases/{id}` เพิ่ม `candidates[].home_ward_id`, `home_ward_name` (ข้อ 6.19, 9.3, 9.6); Test ของข้อกำหนดที่พังเงียบได้ของ C1: `test_cross_ward_pool.py` (`source` ไม่ใช่ `SAME_WARD` และคะแนนแหล่งที่มาไม่เป็น 0, คนที่อยู่เวรของหออื่นไม่เข้า Pool), `test_cross_ward_approval_race.py` (สองเคสต่างหอ สอง Connection), `test_ward_float_pool_migration.py`; ไม่ย้ายคนที่อยู่เวร (C2) | คน 2 |
| 2026-10-15 | รอบ 4 PR T3: Gap รายช่วง Migration `c6e2b9f4a1d7` ต่อจาก C1 (`c4e8a2f6d1b3`) (`STAFFING_GAP.evaluated_from` และ `STAFFING_GAP_INTERVAL`, `STAFFING_GAP_ROLE_INTERVAL`, `STAFFING_GAP_SKILL_INTERVAL` ไม่ Backfill); `calculate_gap(window=...)` วัดตั้งแต่ `max(Backend Clock, เวลาเริ่มเวร)` นับแต่ละคนตามช่วงจริงของ Roster เวรที่จบแล้ววัดทั้งเวร; ค่าสรุปคือช่วงที่ขาดมากที่สุด; `get_case_gap().intervals` และ `case_status.intervals_closed()` ตัดสินปิด Gap รายช่วง (`GapFiller` มีช่วงเวลา); `GET /cases/{id}` เพิ่ม `gap.evaluated_from` และ `gap.intervals` (ข้อ 6.20, 9.3, 9.6) Solver และ Wave ยังใช้ค่าสรุปจนกว่า T4 | คน 1 |
| 2026-10-15 | ตามรีวิว PR T3 (#82) แก้งานเก่าของ T1, T2 และ A ที่ merge แล้ว: `CandidateContext` ปฏิเสธแถว `COMMITTED` ของเวรเดียวกันที่ทับกัน; `create_replacement()` ปฏิเสธรายชื่อที่มี `source_assignment_id` จนกว่า C2 จะเขียนการย้าย; `_apply_cover()` บอกว่าการตัดแถวต้นทางเป็นการย้ายถาวรตามข้อ 6.19 และหาช่วงทำงานด้วย dict; Auto-Approval อ้างมติ R4-Q33 R4-Q36 ตรงที่อนุมัติทั้งหมด; `approval_service.actionable_pending()` และ `lock_ward_row()` ใช้ร่วมกับ Auto-Approval; `other_duties()` รวม `committed_duties()` เข้าด้วยกัน | คน 1 |
| 2026-10-16 | รอบ 4 PR S: APPROVAL_WARD_DECISION แยก SOURCE/DESTINATION และ Supervisor หลัง 600 วินาที; can_decide ร่วมกับ Handoff; API Pending เพิ่มหอและเวลาของ Supervisor, Decision แยกผลอนุมัติกับ outcome; ล็อก Shift ต้นทาง/ปลายทางเรียง ID; Migration f2a7c9d4e6b8 ต่อจาก T3; ไม่รวมการย้ายจริงของ C2/C3 และ LINE issue #75; Handoff docs/round4/pr-S-handoff.md | คน 3 |
| 2026-10-16 | รอบ 4 PR T4: Solver และการเลือก Wave ตามช่วง ไม่มี Migration; `solve(intervals=...)` ทำ Need ละช่วงย่อยพร้อมลดเป้าหมายรายช่วง, `SolverCandidate.source_shift_id` กับเงื่อนไขเลือกพร้อมกันไม่ได้ (R4-Q25), แผนบางส่วน (R4-Q37 R4-Q39) และ `SolverResult.partial`; `wave_targets` เพิ่ม `Slice`, `elementary_slices()`, `fill_targets_by_slice()` และ `TargetCredit.start_at/end_at`; `optimization_service._covers()` (ว่างจนกว่า C2/C3), `GAP_TIME_MISMATCH` ใน `codes.py`, Snapshot เพิ่ม `intervals`, `partial_plan`, `credits`; `get_case_fillers()` คืนคนพร้อมช่วงเวลา และ `select_wave()` เลือกตามช่วง; `PROMPT_VERSION` เป็น `rank-explanation-v2` และ Payload กับหน้าเคสบอกว่าการครอบมาก่อนเมื่อใช้แผนบางส่วน; `GET /cases/{id}` เพิ่ม `partial_plan` (ข้อ 6.14, 6.15, 6.20, 9.3, 9.6) ผลกับข้อมูลแบบเดิมเท่าเดิม (`solver_baseline.jsonl` ไม่ถูกแก้, `SOLVER_TIMING=1`) | คน 2 |
| 2026-10-16 | รอบ 4 PR C2: ย้ายทั้งเวร ไม่มี Migration; `optimization_service._movable_rows()` ให้คนที่อยู่เวรของหออื่นที่เวรต้นทางมีเวลาตรงกับเวรปลายทางและยังไม่เริ่มเข้า Pool, `_covers()` คืน `Cover(None, None, source_assignment_id)`; `SourceShift(shift_id, leaves_gap)` กับ `gap_service.gap_without()` ทำให้ `SOURCE_WARD_MINIMUM_VIOLATION` ตรวจจำนวนคน Role และ Skill ด้วยตัวคำนวณ Gap ตัวเดียวกับเคส; `wave_service` ข้ามด้วย `SOURCE_SHIFT_TAKEN` (ลำดับ Hard Rule, `SOURCE_SHIFT_TAKEN`, `OFFER_LIMIT_REACHED`); `transfer_service.execute()` และ `roster_service.create_transfer()` ตรวจซ้ำตอนย้ายจริงตามลำดับ `DESTINATION_WINDOW_PASSED`, `SOURCE_SHIFT_STARTED`, `SOURCE_COVERAGE_LOST` (แถวต้นทางไม่ใช่ `ASSIGNED` และ Gap), `HARD_RULE_FAILED` ไม่ผ่านได้ Audit `TRANSFER_CHECK_FAILED` ยกเลิก Offer ตอบ `TRANSFER_CANCELLED` และเคสไม่ `FAILED` ผ่านแล้วเขียน `ASSIGNMENT_TRANSFERRED` แทน `ASSIGNMENT_CREATED` (เพิ่ม `cancelled_outreach_ids`, `_cancellation_reasons()` แปลงเป็น `CONFLICTING_ASSIGNMENT`); `create_replacement()` ปฏิเสธรายการที่มีเวรต้นทางด้วย `ValueError`; ใน Seed คน Medicine ของ W4 เข้า Pool ของ ICU แล้วถูกข้าม (`SOURCE_WARD_MINIMUM_VIOLATION`, `ROLE_MISMATCH`) ผลของ Golden Case เท่าเดิม (ข้อ 6.11, 6.19, 7.1, 9.6); Test: `test_transfer_planning.py`, `test_transfer_execution.py`, `test_approval_two_wards.py` (ตัวเขียนจริง) | คน 2 |
| 2026-10-16 | รอบ 4 PR C3: ย้ายกลางเวร ไม่มี Migration; `optimization_service._movable_rows()` เปลี่ยนเป็น `_movable()` คืน staff ID → `Cover` คนที่เวรต้นทางเริ่มแล้วหรือทับบางส่วนเข้า Pool เมื่อ `max(เริ่มเวรปลายทาง, เริ่มเวรต้นทาง, Backend Clock) < min(จบเวรต้นทาง, จบเวรปลายทาง)`; Cover เริ่มที่ `max(เริ่มเวรปลายทาง, เริ่มเวรต้นทาง)` ไม่ใช้ Backend Clock (กันช่วงเล็กที่ไม่มีใครครอบทำให้แผนเป็นบางส่วน ชั่วโมงรวมและกฎเวลาพักไม่เปลี่ยนตามตำแหน่งที่ตัด เพราะเป็น duty เดียวกันตามลิงก์) และจบที่เวลาจบเวรปลายทาง; `GAP_TIME_MISMATCH` เกิดได้จริง; `hard_rule_service.check_items(move_at=...)` ตรวจซ้ำโดยให้ Cover เริ่มที่เวลาย้ายจริง; `transfer_service.execute()` ใช้ `transfer_at = max(เริ่มเวรปลายทาง, เริ่มเวรต้นทาง, เวลาอนุมัติครบ)` ตรวจ `DESTINATION_WINDOW_PASSED`, `SOURCE_COVERAGE_LOST`, `HARD_RULE_FAILED`; ลบ `SOURCE_SHIFT_STARTED` ออกจาก `TransferFailureReason` (แถว Audit เก่าอ่านเป็นข้อความดิบ); แถวต้นทางยังเป็น `ASSIGNED` พร้อม `actual_end_at` (หรือ `CANCELLED` เมื่อเวลาย้ายไม่เกินเวลาเริ่ม) แถวปลายทางตั้ง `actual_start_at`; แถวที่จบก่อนช่วงที่ย้ายได้เป็นประวัติ (ย้ายต่อจากสายการย้ายเดิมได้); `get_case_gap()` ตัดช่วงที่ผ่านไปแล้วออกด้วย `remaining_intervals()` เคสที่ย้ายกลางเวรจึงปิดเป็น `RESOLVED`; ผลกับ Seed และ Golden Case เท่าเดิม (ข้อ 6.11, 6.19, 6.20); Test: `test_transfer_planning.py`, `test_transfer_execution.py`, `test_gap_intervals.py` | คน 2 |
| 2026-10-16 | รอบ 4 PR U: หน้า `cases/[id]` แสดง Gap รายช่วงเมื่อมีมากกว่าหนึ่งช่วง (ตาราง "Gap by time") และผู้สมัครมีคอลัมน์หอบ้าน ช่วงที่มาทำได้ (ว่าง = ทั้งเวร) และเวรต้นทาง; หน้า `approvals` เลือกผู้กดได้ (900, 902, 950 ตาม Seed ของ W4) แสดงหอบ้าน หอต้นทาง สถานะของแต่ละหอ และ `supervisor_from` Supervisor เลือก `side` เมื่อรอมากกว่าหนึ่งหอ ส่วน Head Nurse ไม่ส่ง `side`; ข้อความผลอ่าน `outcome` (`WAITING_OTHER_WARD` คงแถวไว้, `TRANSFER_CANCELLED` พร้อม `reason` และ `failed_rules`, `EXECUTION_FAILED` เป็นข้อความล้มเหลว); รายการ "Approved by the system" จาก `GET /approvals/auto` ตามผู้กด; หน้า `demo/control` แจ้งลาโดยเลือกหอ เวร และคนได้; `/roster` เลือกเวร 21, 22 ได้ และหน้า `me/offers` ไม่นับผู้อนุมัติเป็นพยาบาล; ไม่มี Migration | คน 1 |
| 2026-10-16 | ปิดรอบ 4: PR ทุกตัวของรอบ 4 เข้า `staging` ครบ; ส่วน "สถานะของรอบ 4" บอกว่าเสร็จแล้ว ใส่ #83, #84 และ #88 ในแถว S, T4 และ C3 และบอกว่า head ของ Migration ตอนปิดรอบคือ `f2a7c9d4e6b8`; งานค้างจากรอบ 3 (R4-Q3) ยังไม่มีบันทึกใน repo; ตาราง Test ของข้อกำหนดที่พังเงียบได้ชี้ไฟล์และชื่อ Test ที่ตรวจแล้วว่ามีจริง; ไม่เหลือป้าย **[รอบ 4 · PR X]**; ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-16 | รอบ 5 PR 0: ย้าย Contract ของรอบ 5 เข้าไฟล์นี้ตามร่างรอบ 5 (PR #91): เพิ่มส่วน "สถานะของรอบ 5" (ตาราง PR, ลำดับ merge, Test ของข้อกำหนดที่พังเงียบได้), ข้อ 6.23 LangGraph, 6.24 check-in และ `NO_SHOW`, 6.25 Handover พร้อมรูปของ `content`, ลำดับ Lock ของ check-in และ Handover ในข้อ 6.11, Action ใหม่ `ATTENDANCE_CHECKED_IN`, `OFFER_CANCELLED_NOT_NEEDED` และแถวของ `HANDOVER_GENERATED` ในข้อ 7.1, ข้อ 9.7 API ที่จะเปลี่ยน; `enums.py` เพิ่ม `CheckInSource`, `HandoverReason` (คิดจาก Event ที่เปิดเคส), `EntityType.ATTENDANCE` และ Action สองตัว; ขอบเวลาของ check-in เป็นช่วงครึ่งเปิด (ขอบบนไม่รวม) และหาแถวเดิมก่อนตรวจขอบเวลา (check-in ซ้ำคืนแถวเดิมเสมอ ข้อ 9.7 ตรงกัน); ลบสี่แถวซ้ำในข้อ 9.6 ที่ต่างกันแค่ป้าย "(ทำแล้ว)" เก็บแถวที่มีป้าย; `core/constants.py` เพิ่ม `NO_SHOW_GRACE_SECONDS`, `CHECK_IN_EARLIEST_SECONDS`, `HANDOVER_CONTENT_VERSION`; `database-schema.md` เพิ่มคอลัมน์ที่ N1, H1 และ H2 จะทำ; บันทึกผล LINE จริงผ่าน Tunnel (R5-Q2); ข้อ 12 ย้าย LangGraph และ `NO_SHOW` ไปรอบ 5; กติกาที่มีป้าย **[รอบ 5 · PR X]** ยังรอ PR ที่ระบุ; ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-16 | รอบ 5 PR G: การเดินระหว่าง Handler ใน `_run_round()` เป็น Graph ของ LangGraph (ข้อ 6.23) หนึ่ง Node ต่อหนึ่งสถานะใน `HANDLERS` Edge ตาม `ALLOWED_TRANSITIONS` ไม่ใช้ Checkpointer; Savepoint, Commit, D11 และการส่ง LINE อยู่นอก Graph เหมือนเดิม; ล็อก `langgraph==1.2.15` และประกาศ `langchain-core>=1.4.7,<2` ที่ `orchestrator.py` Import ตรง; Test ใหม่เทียบลำดับ `CASE_STATUS_CHANGED` ของหก Scenario กับค่าที่บันทึกก่อน G และตรวจว่าการส่ง LINE เกิดหลัง Commit; ทุกคน Restart Backend หลัง merge | คน 1 |
| 2026-10-16 | รอบ 5 PR N1: check-in, Migration `a4d8e1b7c3f5` เพิ่ม `ATTENDANCE.shift_id` (NULL ได้ ไม่ Backfill) กับ Partial Unique Index `uq_attendance_staff_shift` บน (`staff_id`, `shift_id`) เฉพาะแถวที่มี `shift_id`; `attendance_service` มี `required_arrival_at()`, `deadline_at()`, `effective_end_at()`, `accepts_check_in()`, `is_on_time()` และ `check_in()` ที่ล็อก `SHIFT` → `ROSTER_ASSIGNMENT` และหาแถวเดิมก่อนตรวจขอบเวลา check-in ซ้ำจึงคืนแถวเดิมเสมอ; Route `POST /me/attendance/check-in` และ `POST /demo/attendance/check-in`; Audit `ATTENDANCE_CHECKED_IN` ใส่ `source` (`SELF` หรือ `SIMULATED`); เพิ่ม `/demo/attendance/check-in` ในรายการของ `dev/line-webhook-proxy/check_gate.py` และ `test_proxy.py`; ขั้น Seed `seed/check_ins.py` (Seed ปัจจุบันได้ 0 แถว เพราะตอน Reset ยังไม่มีเวรที่เริ่ม); แก้ข้อ 6.11, 6.24, 7.1, 9.3, 9.7 และ `database-schema.md` ข้อ 19; Test: `test_attendance_check_in.py`, `test_attendance_shift_migration.py`, `tests/unit/services/test_attendance_time.py` | คน 2 |
| 2026-10-16 | รอบ 5 PR L5: Test ตั้งโหมด LINE เองด้วย Autouse Fixture (Environment และ settings เป็น simulation); กัน HTTP ที่ไม่ได้จำลองไป LINE ด้วย pytest.fail เพื่อไม่ให้ส่งจริงหรือถูกจับเป็นการส่งที่รอลองใหม่; Test ของโหมดจริงยังใช้ตัวปลอมได้; เพิ่ม Test ของค่าเริ่มต้นและด่าน push/reply รวมทางตอบกลับที่จับ Exception; ไม่เปลี่ยนโค้ดของระบบหรือ Migration | คน 3 |
| 2026-10-16 | รอบ 5 PR H1: เพิ่ม `STRUCTURED_HANDOVER.roster_assignment_id` NOT NULL และ Unique (Migration `e8c4b2a6f0d9` ต่อ N1); รวมตัวสร้าง Roster ใน `roster_service.create_assignment()` พร้อม Snapshot จาก DB และ Audit `HANDOVER_GENERATED`; เหตุจาก Event ที่เปิดเคสใน `CASE_OPENED`; ทางอนุมัติ จัดเอง และย้ายใช้ตัวกลาง พร้อม seam สำหรับ N2 ตอนมาสาย; API `/me/handovers` และ `handovers` ในหน้าเคสรวมปัจจุบันกับประวัติ; สร้างซ้ำและสอง Connection ได้แถวเดียว; Golden Path เพิ่ม Audit ของ Handover ก่อน `ASSIGNMENT_CREATED` โดยลำดับสถานะเดิมไม่เปลี่ยน; Frontend `CaseDetail` และ Fixture มี `handovers`; `co_workers` แยกแถวต้นทางที่มีลิงก์ย้ายออกจริงจากคนที่มี Event แต่ยังทำงานอยู่ และไม่ซ่อนแถวใหม่ที่กลับมาทำช่วงที่เหลือ; จัดเองที่ต้นทางเคสผิดปกติ Rollback และตอบ `409 HANDOVER_SOURCE_UNAVAILABLE`; ระบุข้อจำกัดของแถวก่อน H1, TODO Pagination ของ U5 และวิธีเตรียมข้อมูลก่อน Migration; ยังไม่ส่ง LINE (H2) | คน 3 |
| 2026-10-16 | รอบ 5 PR H2: Durable Handover delivery intent ใน Transaction ของ Snapshot, Retry/Lease/Recovery ผ่านตัวส่งเดิม ส่งหลัง Commit และตรวจ Roster ก่อนทุกครั้ง ส่งล้มไม่เปลี่ยนผลจัดเวร; เพิ่มข้อความ Handover พร้อมปุ่มเช็กอินและคำสั่ง `CHECKIN <shift_id>` ใช้ตัวตนจาก binding และกติกา N1, Event dedup/Attendance/Audit Commit พร้อมกัน; Migration `f6b2d8a4c0e1` ต่อ H1 ไม่ Backfill ข้อความเดิม; ทดสอบ LINE ด้วยตัวปลอม รวมสอง Connection ไม่เปลี่ยนเครื่อง Demo | คน 3 |
| 2026-10-16 | รอบ 5 PR N2: `NO_SHOW` สองขั้นและมาสาย ไม่มี Migration; ขั้นที่ 1 `no_show_service.detect_due_no_shows()` (Job เรียกก่อนปิด Window, ต่อเวร ล็อก `SHIFT` แล้วแถวใน Query เดียว, ตรวจซ้ำด้วย `is_no_show()` และ `has_on_time_check_in()` ที่เดินโซ่การย้าย) เขียน Event `STAFF_UNAVAILABLE` ที่ `payload` = `{reason: NO_SHOW, roster_assignment_id}` ผ่าน `event_service.record_no_shows()` Actor `SYSTEM`; ยกเว้นคนที่มีการลาหรือการยกเลิกเวรรอ Window ทุกชนิดใน `STAFF_EVENT_TYPES` (กว้างกว่า Contract ที่ระบุแค่ `STAFF_UNAVAILABLE`); ขั้นที่ 2 `merge_window_service._apply_no_show()` (`_apply()` คืน `bool` ว่านับเข้า Threshold) บันทึก `STAFF_UNAVAILABILITY(NO_SHOW)` ยกเลิกแถว เขียน `UNAVAILABILITY_CREATED` และเดินทางมาสายต่อถ้ามี check-in; `EventIgnoredReason.SHIFT_ENDED` ของ `NO_SHOW` ที่เป็นประวัติอย่างเดียว; `late_arrival_service` (`restore()`, `arrive_after_no_show()`, `trim()`, `credited_case()`) และ `case_status.interval_shortage()`, `choose_kept()` เก็บความครอบคลุมก่อน; Audit `UNAVAILABILITY_UPDATED` ของทางมาสายที่ `case_facts_service._returned_spans()` ใช้นับคนที่มาสาย (ไม่อยู่ใน `assigned_staff_ids()`); `OFFER_CANCELLED_NOT_NEEDED` และ `cancellation_reason` = `NO_LONGER_NEEDED`; `attendance_service.check_in()` ล็อกแถวที่ `NO_SHOW` ยกเลิกรวมด้วย ลำดับล็อกของทางมาสายและ Retry สูงสุด `CHECK_IN_LOCK_TRIES` = 5 แล้ว `CheckInLockRetryError` ตอบ `409` ทั้งสอง Route; `no_show_event_ids` ในคำตอบของ `close-due` และ `clock/advance`; แก้ข้อ 3.7, 6.11, 6.24, 7.1, 9.3, 9.7 และ `database-schema.md`; Test: `test_no_show_detection.py`, `test_no_show_window.py`, `test_late_arrival.py`, `test_late_arrival_races.py`, `tests/unit/domain/test_case_status_trim.py` | คน 1 |
| 2026-10-16 | รอบ 5 PR U5: `GET /clock` คืน `{now, frozen}` ไม่มี Migration; แถบเมนูแสดง Clock ของ Backend; หน้า `/me/offers` มีปุ่ม check-in และรายการ Handover ของตัวเอง; หน้า `demo/control` มีปุ่มจำลองการ check-in และแสดง `no_show_event_ids`; หน้าเคสมีส่วน Handover; ตัวแสดง Handover อ่านเฉพาะ Key ของ `version` 1 และข้ามรายการที่ไม่ใช่ Handover | คน 1 |
| 2026-10-16 | ปิดรอบ 5: PR ทุกตัวของรอบ 5 เข้า `staging` ครบ (#91 ถึง #97, #99, #100); ส่วน "สถานะของรอบ 5" บอกว่าเสร็จแล้ว ใส่ #93 และ #99 ในแถว N1 และ N2 บันทึก Migration head `f6b2d8a4c0e1` และจำนวน Test ตอนปิดรอบ; ตาราง Test ของข้อกำหนดที่พังเงียบได้มีคอลัมน์ "Test อยู่ที่" ที่ตรวจแล้วว่ามีอยู่จริงทุกแถว; รวบรวมเรื่องที่เปิดไว้ (ข้อยกเว้นของการยกเลิกที่ค้าง, Pagination, Bedrock, Test ลำดับการอนุมัติ) ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-17 | Issue #98 หลังปิดรอบ 5: ผลสุดท้ายของข้อเสนอและ LINE outbox แยกต่อ outreach_id, ส่งหลัง Commit ด้วย retry เดิม, ปุ่มหมดเวลาได้คำตอบทั้งก่อน/หลัง Job, หน้า Offer อ่าน final_outcome/final_message ได้แม้ไม่มี LINE; Migration b4e7a9c2d6f0 ต่อ f6b2d8a4c0e1 และ c5f8b0d3e7a1 แยก Promotion/FINAL กับธงรับเป็นสำรอง ไม่มี backfill ข้อความ; แก้ assertion ของ test อนุมัติพร้อมกันให้ตรวจคนครบ/ไม่ซ้ำโดยไม่บังคับลำดับ ID ของสอง Thread | คน 3 |
| 2026-10-17 | รอบ 6 PR 0: ย้าย Contract รอบ 6 เข้าไฟล์นี้ (PR #104): ส่วน "สถานะของรอบ 6" พร้อมตาราง PR 15 ตัว ลำดับ merge ค่าเริ่มต้นของเพดาน LLM และตาราง Test ของข้อกำหนดที่พังเงียบได้; ข้อ 6.27 ผู้ใช้กดขอคำอธิบายอันดับและสรุปเคส (ผูก Snapshot) ขอใหม่หลังล้มเหลวหรือถึงเพดาน บันทึกการเรียกและตัวห่อการเรียกที่ B1 เป็นเจ้าของ (schema ของ `LLM_CALL_LOG`, ตัวนับรายวัน, แปลงตัวประมวลผลเดิม) และ `LLM_ENABLED=true` ห้ามตั้งก่อน E1 merge; ข้อ 6.28 Bedrock จริง เพดานสองชั้น 100 ครั้งต่อวันกับ 20 USD ต่อเดือน ตัวตรวจตัวเลข เกณฑ์และขั้นตอนเลือกโมเดล เพดานชุดทดลอง; ข้อ 6.29 ข้อความอิสระของพยาบาลไม่ใช้ LLM; ข้อ 6.30 กฎ `/demo/` ของเครื่อง AWS (ทุก Path ต้องมีรหัสยกเว้น webhook) เกณฑ์เว็บพร้อมแยกสองช่วง ขั้นที่ 6 และเกณฑ์ปิดรอบ; ข้อ 6.31 Dashboard และหน้าเช็ค Gap; ข้อ 9.8 API; แก้ข้อ 6.15, 6.17 และ 6.24 (ข้อยกเว้นของ `NO_SHOW` ให้ตรงโค้ดตาม R6-Q14 ก และประโยคเรื่อง `/demo/`); เติมตาราง fake กับของจริงด้วยผลลอง LINE จริง 2026-10-16; ปรับสถานะเรื่องที่เปิดไว้ตอนปิดรอบ 5; ค่าใหม่ใน `enums.py` (`LlmWorkType`, `LlmQuotaScope`) และ `constants.py`; ไม่เปลี่ยนพฤติกรรมของระบบ | คน 1 |
| 2026-10-17 | รอบ 6 PR I: ข้อความส่วนตัวที่ไม่ใช่คำสั่งหรือปุ่มได้ข้อความแยกสี่กรณี: ยังไม่ผูก, รอตอบ, รอผลรวมสำรอง, ไม่มีรายการ ไม่ตีความหรือเก็บข้อความ ไม่ใช้ LLM ไม่เปลี่ยนข้อมูลธุรกิจ Dedup ก่อนตอบและไม่ตอบในกลุ่ม/ห้อง ไม่มี Migration | คน 3 |
| 2026-10-17 | รอบ 6 PR B1 (#108): ตัวห่อการเรียก LLM `app/services/llm_gateway.py` เป็นทางเดียวไปถึงผู้ให้บริการ (จองโควตาและเขียนแถว `IN_FLIGHT` ใน Transaction ของผู้เรียก, เรียกโดยไม่มี Transaction ค้าง); Migration `d2a6f9c1e4b7` (`LLM_CALL_LOG.work_type`, คอลัมน์อ้างอิงตามชนิด, `detached_at`, CHECK และ Unique บางส่วน, ตาราง `LLM_DAILY_USAGE` และ `LLM_TRIAL_USAGE`); ตัวประมวลผลคำอธิบายเดิมเรียกผ่านตัวห่อ ถึงเพดานหรือ Payload เกินเพดาน Input เป็น `SKIPPED`; ตัวตรวจตัวเลขในประโยค; ค่าตั้งเพดานอ่านจาก Environment และตรวจเขตเวลาตอนเริ่มระบบ; Demo reset เก็บบัญชีการเรียก LLM และทำใน Transaction เดียว; ตัวกัน Test `isolated_llm` | คน 2 |
| 2026-10-17 | รอบ 6 PR D: ไฟล์ของเครื่องทดสอบบน AWS ใน `deploy/aws/` (`Caddyfile`, `docker-compose.aws.yml`, `check-gate.sh`, `load-env.sh`, `nara.service`, `iam-parameter-read-policy.json`) และ `docs/deploy-aws.md` เอามาจาก branch `feat/aws-test-environment` เฉพาะไฟล์ใหม่แล้วปรับกับ Compose ปัจจุบัน ไม่เปิดเครื่อง; กฎ `/demo/` ตามข้อ 6.30 (ทุก Path ต้องมีรหัสยกเว้น `POST /api/line/webhook`); ข้อยกเว้นของ Webhook จับจาก URI ดิบ (`{http.request.orig_uri}`) เพราะตัวจับ `path` ของ Caddy 2.10.2 ไม่สนตัวพิมพ์ รวม `//` และถอดรหัส `%6C` ทำให้ `/API/line/webhook`, `/api//line/webhook`, `/api/%6Cine/webhook` และ `?x=1` หลุดด่านในแบบเดิม; `check-gate.sh` ขยายเป็น 30 ข้อ; `test_gate.py` กับ job `AWS test machine gate (Caddy)` ใน CI รัน Caddyfile จริงกับ Upstream ปลอมและตรวจว่าคำขอที่ติดด่านไม่ถึง Upstream; `docker-compose.aws.yml` ตรึง `LLM_ENABLED=false` จน E1 ลบ; Region ของ Parameter Store แยกเป็น `NARA_PARAMETER_REGION` (ไม่ใช้ `AWS_REGION` ซึ่งเป็น Region ของ Bedrock ที่แอปอ่าน) และ `nara.service` เรียก `docker compose` ผ่าน `env -u AWS_REGION` พร้อม `test_region.py` ใน CI (รีวิว PR #107); เพิ่ม `.gitattributes` ให้ `*.sh`, `Caddyfile` และ `nara.service` เป็น LF; แก้ `docs/repo-structure.md`; ไม่เปลี่ยนพฤติกรรมของแอป | คน 1 |
| 2026-10-17 | รอบ 6 PR P1: `/me/handovers` คืน active ครบและแบ่งประวัติด้วย Cursor (`limit` 20 สูงสุด 100, key เวลา/ID และตรวจเจ้าของ); หน้าพยาบาลมีปุ่มโหลดประวัติเพิ่มและ polling prefix ที่อ่านแล้ว เก็บข้อมูลเดิมเมื่ออ่านล้ม ไม่มี Migration และ API หน้าเคสไม่เปลี่ยน | คน 3 |
