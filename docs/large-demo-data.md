# ข้อมูล Demo ชุดใหญ่: 500 คน / 20 หอ / 30 วัน

เพิ่มจาก Golden Case เดิม ไม่ลบหรือเปลี่ยนบัญชี, staff subject, LINE binding หรือ quota เดิม ข้อมูลทุกแถวใน profile เป็นเรื่องสมมติ ใช้ทดสอบหน้าจอ/ปริมาณข้อมูล ไม่ใช่ประวัติที่พยาบาลจริงทำงาน หรือผลตรวจ Hard Rules/Solver/approval จริง

- เพิ่ม staff 500 คน: RN 480 + หัวหน้า 20 คน มีชื่อไทยนามสกุล “จำลอง…” และ email `example.invalid` ไม่มีรหัสผ่านสำเร็จรูป/บัญชีเว็บ/LINE contact ของคนใหม่
- เพิ่มหอ 20 หอ, 30 วัน วันละ 2 เวร 12 ชั่วโมง รวม 1,200 เวร ตารางหมุน 4 ทีม มีทั้งเวรเต็มและเวรขาดคน
- ตารางเวรพื้นฐาน 7,200 แถว พร้อมประวัติเข้าเวร/สาย, การลาแบบวางแผนและฉุกเฉิน, เคสประวัติ RESOLVED/UNRESOLVED/FAILED, Gap และ Handover ของการทดแทน รายการเสริมขึ้นกับเวลาที่สร้าง
- ช่วงข้อมูล 14 วันก่อนวันที่ Backend Clock ถึง 15 วันหลังวันนั้น ไม่เปลี่ยนเวลา Backend ใช้ `/clock` ของ Backend ที่กำลังรันเป็นเวลาอ้างอิง จึงตรงกับหน้าเว็บแม้ clock frozen
- ไม่มีเคสรอที่กระตุ้น Job, ไม่มี CandidateOutreach, LINE delivery intent หรือ LLM row ที่ generator สร้าง ประวัติทำเครื่องหมาย `source=SIMULATED`, `dataset=large-500-20-30-v1`, `synthetic_history=true` โดย SYSTEM ไม่แอบอ้างผู้ใช้จริง ข้อมูลประวัติไม่มี CandidatePlan/คะแนน/Safety ที่แต่งให้ดูเหมือนผ่านบริการจริง
- เป็นการเพิ่ม **500 คน/20 หอ** จึงมี 514 คน/23 หอเมื่อรวม Golden Case เดิมที่ยังไม่แก้

## การมองเห็น

900 ยังคงเป็นหัวหน้า ICU เดิม จึงไม่เห็นหอใหม่ทั้งหมด อย่าเปลี่ยน role/ward ของ 900 เพื่อให้เห็นข้อมูล ใช้บัญชี supervisor ของ staff 950 ที่มี role นี้อยู่เดิม ถ้ายังไม่มี account ให้สร้างด้วย CLI (ไม่ใช่ demo-accounts บน AWS) และเปลี่ยนรหัสเมื่อ login ครั้งแรก:

```bash
sudo docker exec -it nara-staffing-backend python -m app.auth_accounts create --staff-id 950
```

IDs ของชุดนี้: หอ 10001–10020, staff 100001–100500, shifts 2000001–2001200 หัวหน้าแต่ละหอคือ staff 100025, 100050, …, 100500 หน้า Gap ใช้รายชื่อหอจาก Dashboard; dictionary มีชื่อของหอใหม่ครบ 20 หอแล้ว (revision เดิมที่ deploy ก่อน review follow-up ยังแสดง fallback เช่น `Ward 10001`) ปุ่ม Demo control เดิมยังเป็นตัวละคร Golden Case ไม่ได้เพิ่มปุ่มสร้างเหตุของทั้ง 20 หอ สามารถเปิด Gap/roster/detail และสร้างบัญชีรายคนเพื่อทดลอง `/me/unavailability` ได้ตามสิทธิ์

## Preview / Apply

Migration `f2c9a1d6e8b4` ต่อ `b8f3d5a0c2e4` เพิ่มเพียงตาราง `demo_dataset` เก็บชื่อ profile และเวลาอ้างอิง ไม่สร้างข้อมูลโดยอัตโนมัติตอน deploy/startup

```bash
sudo docker exec nara-staffing-backend python -m app.mock_data
sudo docker exec nara-staffing-backend python -m app.mock_data --apply
```

Preview แสดง `reference_at` ที่บันทึกไว้ของ profile ที่โหลดแล้ว; apply ซ้ำใช้เวลาอ้างอิงเดิมโดยไม่ต้องเรียก `/clock`. ถ้าโหลดครั้งแรกอ่าน clock ไม่ได้จะปฏิเสธพร้อมข้อความให้รอ backend healthy โดยไม่เขียนชุดข้อมูล. Preview ไม่เขียนข้อมูล Apply เพิ่มทั้งชุดใน transaction เดียว; รันซ้ำ profile เดิมไม่เพิ่มแถวและไม่เขียนทับการเปลี่ยนแปลงจากการทดสอบ หาก ID namespace มีข้อมูลอื่นอยู่แต่ไม่มี marker ของชุดนี้ จะปฏิเสธก่อนเขียน ห้ามแก้ marker/ID ด้วย SQL เพื่อบังคับให้ผ่าน ไม่ลบ/replace ชุดเดิมผ่าน CLI นี้

ก่อน apply บน AWS ให้เก็บ SQL backup สิทธิ์ 600 ที่ต่างจาก backup AU4 เดิม หยุด Job/traffic ชั่วคราวตามขั้นตอนด้านล่าง แม้ generator ไม่ส่งข้อความเอง ข้อมูลใหม่นี้เข้าร่วม candidate pool ของงานจริงหลังโหลด: การสร้างเหตุ/เดินนาฬิกาในภายหลังอาจกระตุ้นการติดต่อ/LLM ตามค่าตั้งของระบบได้ อย่าตีความว่าเปิด Demo จริงแล้วไม่มีค่าใช้จ่ายเสมอ

## Deploy บน AWS ที่รัน AU4 แล้ว

ใช้ revision ที่ผ่าน CI และรวม AU4 อยู่ด้วย ไม่ checkout staging เก่าทับ AU4 ตรวจ working tree ว่าง/backup ก่อนหยุด service ไม่มี `seed` และไม่มี `down -v`:

```bash
sudo sh -c 'umask 077; docker exec nara-staffing-postgres pg_dump -U staffing -d staffing > /etc/nara/before-large-demo.sql'
sudo test -s /etc/nara/before-large-demo.sql
```

จากนั้นหยุด `nara` ก่อนเปลี่ยน checkout เพราะ Backend mount source แม้ไม่มี reload ตัวอย่างใน root shell (ใส่ immutable SHA ของ PR นี้ที่ผ่าน CI):

```bash
cd /opt/nara
systemctl stop nara
git fetch origin
git checkout --detach <reviewed-large-data-SHA>
dc() {
  env -u AWS_REGION docker compose --env-file /etc/nara/nara.env \
    -f /opt/nara/docker-compose.yml -f /opt/nara/deploy/aws/docker-compose.aws.yml "$@"
}
dc up -d --wait postgres redis
dc run --rm -T --interactive=false --no-deps backend sh -c 'pip install --no-cache-dir -e ".[dev]" && alembic upgrade head' < /dev/null
dc up -d --wait backend
# Caddy/Job ยังไม่เริ่ม ไม่มี traffic เข้าหรือ due work ระหว่างโหลด
dc exec -T --interactive=false backend python -m app.mock_data < /dev/null
dc exec -T --interactive=false backend python -m app.mock_data --apply < /dev/null
systemctl start nara
dc ps
```

ถ้ามี error ให้หยุด ไม่รัน seed/ลบข้อมูลเพื่อแก้ การ apply ล้ม rollback ข้อมูลเพิ่มทั้งชุด แต่ migration ตาราง marker ยังคงอยู่ การ rollback code ก่อน profile นี้หลัง apply ทำให้ Reset รุ่นเก่าไม่รู้จักหอใหม่ จึงอย่า rollback ข้าม feature นี้/ลบ marker ขณะเก็บ staff ของ profile ไว้ ถ้าต้อง recovery ใช้ backup ใน maintenance window ที่ทีมตกลง โดยไม่ทับข้อมูลใหม่เงียบ ๆ

## Reset

ปุ่ม Demo Reset รักษา marker ของ profile ที่รู้จักไว้แล้วสร้างชุดใหญ่ใหม่ภายใน transaction ของ reset ก่อนคืน identity/account เดิม ใช้ auth reset gate เช่นเดียวกับ auth write และ CLI import; CLI มี dataset advisory lock เพิ่มเพื่อกัน apply สองตัวพร้อมกัน Staff ID และ auth subject เดิมจึงยังเป็นคนเดิม บัญชี/รหัส/role/ward/disabled คงเดิม Session/code เก่าถูกยกเลิก และ LINE binding ใช้กติกา reset เดิม (อาจต้อง LINK ใหม่) ไม่อ้างว่าข้อมูลสถานการณ์หรือ LINE binding คงอยู่หลัง reset

หากพบ profile ที่ไม่รู้จัก Reset จะ rollback แทนล้างข้อมูลเงียบ ๆ เครื่องที่ไม่เคย apply ยังคง reset Golden Case ปกติ จำนวน staff/ward ของ profile ไม่ทำให้ใครได้ role supervisor โดยอัตโนมัติ

## ตรวจผล

ตรวจ preview หลัง apply ต้อง `already_loaded=true`, namespace `{staff:500, wards:20, shifts:1200}` รัน apply ซ้ำจำนวนเดิม ใช้ supervisor 950 ดู Dashboard/Gap และประวัติเคส เลือก RN ของหอใหม่เพื่อทดลองแจ้งลาตัวเองตาม flow จริงได้ ห้ามใช้ประวัติ synthetic เป็นหลักฐานว่า LINE/LLM/Solver จริงผ่าน AU4 ยังต้องตรวจตาม live checklist เดิม

## AWS import evidence (operator-reported, 2026-10-23 Bangkok)

ผู้ใช้ส่ง terminal output จาก EC2 ไม่ใช่ผลที่ผู้เขียนเอกสารรันบน AWS เอง:

- Checkout แสดง `c28e46756f39d7e72f4d5701b2236803ba7d63b4`; migration แสดง `b8f3d5a0c2e4 -> f2c9a1d6e8b4`.
- ก่อน import: `already_loaded=false`, namespace ทั้งสามเป็น 0.
- Apply: `loaded={staff:500, wards:20, shifts:1200}` และ preview หลัง start service แสดง `already_loaded=true` พร้อมจำนวนเดิม.
- Compose แสดง Backend/Frontend/PostgreSQL/Redis healthy; Caddy และ Job Up หลัง `systemctl start nara`.
- Backup ก่อน deploy ขนาด 161 KB สิทธิ์ 600; ผู้ใช้รายงานว่าสร้างและ login supervisor 950 ได้ก่อน import.

ภาพหน้าจอจากผู้ใช้หลัง import ยืนยัน supervisor 950 บน AWS:

- Dashboard แสดงหอใหม่ 10001–10020, ประวัติ RESOLVED 47 / UNRESOLVED 47 / FAILED 46 และเวรชุดใหม่ที่มี Gap. จำนวนประวัติเหล่านี้เป็น synthetic ตามเวลาอ้างอิง ไม่ใช่ผล workflow จริง.
- หน้า Gap เลือก Ward 10001 วันที่ 23/10/2026 แสดงเวร 2000029 เวลา 07:00–19:00 ต้องมี 7 / มี 6 / ขาด 1 และเวร 2000030 เวลา 19:00–07:00 วันถัดไป ต้องมี 6 / มี 6 / ครบ.

ยังไม่แนบ image ID และยังไม่ได้ทำ live Reset ของชุดใหญ่ ไม่ใช้ข้อมูลนี้ปิด AU4 acceptance หรืออ้างว่า workflow จริงผ่าน.

## Review follow-up: ข้อมูลที่โหลดแล้ว

Generator รุ่นปรับปรุงหมุนประวัติทุก 5 เวรแทนทุก 4 เวร จึงครอบคลุมทั้ง 4 ทีม สลับผู้ลาที่ถูกยกเลิก และมีทั้ง ICU/BLS skill gaps. ใช้กับ import ครั้งแรกหรือ Reset ครั้งถัดไปเท่านั้น; apply ซ้ำไม่แก้ประวัติ AWS ที่โหลดแล้วและไม่ได้ Reset เครื่องโดยอัตโนมัติ. ตัวเลข/ภาพหลักฐานข้างต้นยังเป็นของ revision c28e467.

การทดสอบ `test_reset_replays_large_profile_preserving_old_and_new_accounts_and_subjects` โหลด profile, สร้างบัญชีเดิม 900 และบัญชีใหม่ 100001, Reset แล้วเทียบ subjects/password hashes/จำนวน 500–20–1200, ยืนยัน session เก่าใช้ไม่ได้และ login ใหม่ได้. เป็น integration test ในฐานแยก ไม่ใช่ผล live Reset บน AWS.

## Golden Case หลัง import (automated, ไม่ใช่ AWS live)

`test_large_demo_golden.py::test_golden_candidates_and_complete_flow` รันสองกรณีด้วย real HTTP routes/handlers/Solver บน PostgreSQL แยก: Golden seed เดิม และ seed + import ชุดใหญ่. เวลาอ้างอิงคงที่ `2026-10-09T21:00:00+07:00`, LINE simulation และไม่เปิด LLM จริง.

| ผล | ก่อน import | หลัง import |
|---|---:|---:|
| `_pool()` ก่อนแจ้งลา 105 | 14 | 514 (ใหม่ 500) |
| ผู้สมัครที่มี CandidateItem หลัง Hard Rules/Solver | 3 | 123 (ใหม่ 120) |
| อันดับ 1–3 | 201, 202, 203 | 201, 202, 203 |
| First wave | 201, 202 | 201, 202 |
| Solver / objective | OPTIMAL / 2023 | OPTIMAL / 2023 |

หลัง import อันดับ 4–9 เป็น 100019–100024, อันดับ 10 เป็น 100044 (CROSS_WARD); ไม่อ้างว่า candidate list ทั้งหมดคงเดิม. ทั้งสองกรณี 201 ตอบรับ → หัวหน้า 900 อนุมัติ → RESOLVED พร้อม Handover ของ 201 และเช็กอินด้วย 201 ที่เวลาเริ่มเวร +7 นาทีได้ on_time. Golden transitions ตรง baseline. เทสต์ล็อกจำนวน pool/ranked และสามอันดับแรก/first wave เพื่อจับ regression.

ผลนี้รองรับการคง flow หลักของ Golden Case ณ fixture นี้; การมี 120 ตัวสำรองใหม่เป็นผลข้างเคียงที่ยอมรับตามการตัดสินใจคง pool ไม่ใช่การรับรอง ranking ทุกวันที่/สถานการณ์. หากผู้สมัครเดิมปฏิเสธ หมดเวลา หรือไม่มีสิทธิ์ รายชื่อใหม่อาจถูกใช้ใน wave ถัดไป และอาจเกิดการอนุมัติข้ามหอ ต้องทำตาม Demo runbook. ไม่ได้รัน Golden Case ซ้ำบน AWS จริงหรือส่ง LINE/LLM เพื่อเก็บผลนี้.
