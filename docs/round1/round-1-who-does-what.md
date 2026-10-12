# รอบ 1 ใครทำอะไร

สรุปจากข้อ 10 ของ `round1-contract-draft.md` ถ้าไฟล์นี้กับร่างไม่ตรงกัน ให้ยึดร่าง ส่วนกติกาของข้อ 2, 3, 4, 5, 6.1 และ 8.2 ย้ายเข้า `docs/workflow.md` แล้วใน PR 0

## แต่ละข้อของร่างเกี่ยวกับใคร

| ข้อ | เนื้อหา | ใครต้องอ่าน |
| :-- | :-- | :-- |
| **0, 1** สรุปและขอบเขต | อะไรอยู่ในรอบ 1 | ทั้งสามคน |
| **2.1 ถึง 2.4** Transition | 7 เส้นใหม่ และฟังก์ชันคำนวณสถานะเคส | ทั้งสามคน คน 1 ลงมือ |
| **2.5** Merge Gap | Window, Threshold, Event สี่ชนิด, Job | คน 1 ลงมือ คน 3 อ่านเพราะ Job ใช้ร่วมกับ Timeout ของ Offer |
| **2.6, 2.7** เคสรับหลายคน, Timeout ของ Offer | สถานะรายคน, หลาย Offer ต่อคน | ทั้งสามคน คน 3 ลงมือเป็นหลัก |
| **3** กติกาของ Wave | เลือกคน, เพดาน Offer | คน 3 ลงมือ คน 2 อ่านเพราะ Solver ใช้เพดานเดียวกัน |
| **4** แถวที่เขียนและ Lock | กติกากลาง | ทั้งสามคน |
| **5** Audit | ลำดับที่ Test ต้องตรวจ | ทั้งสามคน |
| **6** API และหน้าเว็บ | คำตอบที่เปลี่ยน | เจ้าของหน้า: คน 1 (`demo/control`, `approvals`), คน 2 (`cases/[id]`), คน 3 (`line-sim`) |
| **7** Hard Rules | รหัสและ Interface | คน 2 ลงมือ คน 3 เรียกใช้ตอนเลือกคนของ Wave |
| **8** Coverage และ Solver | Gap, Target, สูตรจัดอันดับ | คน 1 (Coverage), คน 2 (Solver), คน 3 (เติม Target ของ Wave ถัดไป) |
| **9** Scenario และ Test | เจ้าของไฟล์ Scenario | ตามตารางในข้อนั้น |
| **10** ลำดับ PR | งานจริง | ตามตารางข้างล่าง |
| **11** ไฟล์กลาง | ไฟล์ที่หลายคนแตะ | ทั้งสามคน |
| **12** คำถามและคำตอบ | Q1 ถึง Q56 ตอบครบแล้ว | ใช้ค้นว่าเรื่องไหนตกลงว่าอะไร |
| **13** สิ่งที่ยังไม่ได้ตรวจ | ข้อจำกัดของร่าง | ทั้งสามคน |

---

## งานจริง แยกตามคน

### คน 1 (5 PR)

| PR | งาน |
| :-- | :-- |
| **0** Contract | ย้ายร่างเข้า `workflow.md`, เพิ่ม T1 ถึง T7 ใน `transitions.py` + Test, เพิ่มค่าใน `enums.py` ไม่เปลี่ยนพฤติกรรม |
| **1b** Coverage | `calculate_gap()` Signature ใหม่, `effective_minimum`, Migration ของ `STAFFING_GAP`, ฟังก์ชันอ่าน Gap ให้ Solver |
| **M** Merge Gap | Migration, แยกการรับ Event กับการปิด Window, Threshold, Event สี่ชนิด, Job, Route เลื่อน Clock, หน้า `demo/control` |
| **S** สถานะเคส | `decide_status()` กับ `recompute()` และ `stub_handlers` ใหม่ |
| **5** หน้า `approvals` | Reject ใช้งานจริง มีช่อง `reason` และหลายแถวต่อเคส |

### คน 2 (4 PR)

| PR | งาน |
| :-- | :-- |
| **1a** Hard Rules | ตัวตรวจและรหัสใน `domain/constraints/` + Unit Test |
| **2a** Solver | ใช้ Hard Rules กับ Gap, สูตร `plan_penalty`, `ranking_key`, `CANDIDATE_ITEM_TARGET`, `working_time_service`, เรียกฟังก์ชันเพดาน Offer, กรณี Solver ไม่ได้ใคร |
| **3** Safety รายคน | ตรวจตอนตอบรับ บันทึกผลไม่ผ่าน ย้ายการสร้าง `APPROVAL_REQUEST` ไปเป็นฟังก์ชันใน `approval_service` ลบ `assert_available()` กับ `unavailable_staff()` รวมบรรทัดที่เรียกใน `roster_service` ของคน 3 และลบสองเส้นของ `SAFETY_VALIDATION` |
| **6** หน้า `cases/[id]` | สถานะรายคน, เหตุผลที่ข้าม, `event_ids`, `effective_minimum` |

### คน 3 (4 PR)

| PR | งาน |
| :-- | :-- |
| **1c** เพดาน Offer | ตาราง `OUTREACH_POLICY` + Seed และฟังก์ชันเพดาน |
| **2b** Wave + ตอบ Offer | `contact_candidate`, ส่งหลายคน, Reject, สำรอง, หลาย Offer ต่อคน, หน้า `line-sim`, แก้ `GOLDEN_PATH_AUDIT_ACTIONS` + E2E |
| **4** อนุมัติและจัดเวรรายคน | ไม่อนุมัติ, `reason`, จัดเวรใน Transaction ของการอนุมัติ, ปิดเคสใน `EXECUTING` |
| **O** Timeout ของ Offer | `offer_timeout_seconds`, `expires_at`, ปิด Offer ที่หมดเวลา ต่อเข้ากับ Job ร่วมกับคน 1 |

---

## ลำดับที่ต้องเกิด

1. ทีมรีวิว PR เอกสารของ branch `docs/round1-contract` (เสร็จแล้ว PR #32)
2. คน 1 เปิด PR 0 ต้องเข้าก่อนทุกตัว
3. PR 1a, 1b, 1c ทำขนานกันได้
4. PR M (หลัง 0 และ 1b) และ PR S ต้องเข้าก่อน 2b
5. PR 2a (หลัง 1a, 1b, 1c) ต้องเข้าก่อน 2b
6. PR 2b แล้ว PR 3 แล้ว PR 4 ตามลำดับ ทั้งสามตัวเข้า Branch รวมหนึ่ง Branch ที่แตกจาก `staging` แล้ว merge Branch รวมเข้า `staging` ครั้งเดียว เพราะหลัง PR 2b ระบบส่ง Offer เป็น Wave แล้ว แต่ Safety กับการอนุมัติยังเป็นโค้ดเก่าจนกว่า PR 3 และ 4 จะเข้า
7. PR O หลัง M, 1c และหลัง Branch รวมเข้า `staging`
8. PR 5 และ PR 6 หลัง Branch รวมเข้า `staging`

จุดที่รวมแล้วพังเงียบได้อยู่ท้ายข้อ 10 ของร่าง อ่านก่อนเปิด PR ของตัวเอง
