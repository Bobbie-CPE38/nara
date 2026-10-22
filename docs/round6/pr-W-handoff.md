# PR W — ย้าย LINE Webhook จาก Tunnel ไป AWS

สถานะ: live smoke ของ W ผ่านตามผล ภาพ และการยืนยันที่ผู้ Deploy ส่งเมื่อ 2026-10-21 พร้อมให้ทีมรีวิว PR #121 ผู้บันทึกไม่ได้เชื่อม EC2 หรือรันทดสอบ live ซ้ำเอง ไม่ใช้ผล Quick Tunnel ของรอบ 5 แทน และไม่ประกาศปิดรอบ 6 หรือข้อค้างช่วง ข จากรายงาน W นี้

## ขอบเขตและจุดเริ่ม

หลังขั้นที่ 6 ตาม workflow ข้อ 6.30 ให้ใช้ `https://<SITE_DOMAIN>/api/line/webhook` ของเครื่อง AWS โดยคง Basic Auth ตาม PR D และการตรวจลายเซ็นใน Backend เดิม ไม่มี migration และไม่ใช้ Bedrock ไม่เพิ่ม cloudflared ใน Compose ไม่รวมงานล็อกอิน AU0–AU5

ผู้ Deploy รายงานก่อนเริ่ม W: Git HEAD `514babd56968c84f6fed37106ff63270b668e1a2`, `LINE_MODE=simulation`, `REAL_LINE_CONFIGURED=False` (2026-10-21) เป็นผลตรวจค่าตั้ง ไม่ใช่ผล cutover

**เครื่องที่โหลด mock data ชุดใหญ่:** พนักงานใหม่เข้าร่วม candidate pool จริง การสร้างเหตุ/เดินนาฬิกาอาจส่ง LINE ให้ผู้ที่ผูกบัญชีและเรียก LLM ตามค่าตั้ง อ่าน [Demo runbook](../demo-runbook.md) ก่อนเริ่ม; ห้ามถือว่าชุดข้อมูลจำลองแยกจาก real outreach

## 1. เตรียมเครื่องและ Channel

- ยืนยันขั้นที่ 6 กับทีม เก็บ HEAD/image ID และผล Gate/Frontend ที่ตรงกับรุ่นที่รัน หากรุ่นเปลี่ยนให้ตรวจใหม่
- ตกลงผู้ใช้ LINE สำหรับทดสอบจริงและช่วงเวลาที่ทีมไม่กด Demo พร้อมกัน จด Webhook URL เดิมแบบส่วนตัวสำหรับ rollback และเก็บ proxy/Tunnel เดิมไว้ก่อน
- ทำตามหัวข้อ "ตรวจคิวก่อนเปิด real" ด้านล่างก่อนเปลี่ยนค่าและ restart ตรวจคิว Offer/Handover/Outcome ของฐาน AWS ก่อนเปิด `real`: คิวค้างอาจเริ่มส่งทันทีหลัง restart อย่าสร้างเคสใหม่หรือ reset ระหว่างเปลี่ยนระบบ ไม่ใช้ DB ของ Tunnel สลับกับ AWS โดยสมมติว่า bindings เหมือนกัน
- สำหรับ manual env แก้ `/etc/nara/nara.env` บนเครื่องด้วย `sudo nano` ให้ `LINE_MODE='real'` และใส่ Channel secret/access token ล่าสุดของ Channel เดียวกัน ห้ามส่งค่า secret ลงแชท/PR/Log; สำหรับ Parameter Store เปลี่ยนที่แหล่งค่าตั้งของเครื่องนั้น ไม่ source ไฟล์ env เป็น shell
- `sudo systemctl restart nara` แล้วตรวจแบบไม่พิมพ์ความลับ:

```bash
sudo docker exec nara-staffing-backend python -c 'from app.core.config import settings; print("LINE_MODE=", settings.line_mode); print("REAL_LINE_CONFIGURED=", settings.real_line_enabled)'
```

ต้องได้ `real` และ `True` ค่านี้บอกว่าค่าตั้งครบ ยังไม่ยืนยัน token ใช้ได้จริง

### ตรวจคิวก่อนเปิด real (สำหรับ cutover ครั้งถัดไป)

ให้ทีมงดสร้าง/เปลี่ยนเคส งดกด Demo และหยุด Job ชั่วคราว **ขณะยังเป็น simulation** เพื่อไม่ให้มี intent ใหม่ระหว่างตรวจ:

```bash
sudo docker stop nara-staffing-job
sudo docker exec -i nara-staffing-postgres psql -v ON_ERROR_STOP=1 -U staffing -d staffing <<'SQL'
SELECT 'offer' AS queue, count(*) AS pending
FROM candidate_outreach WHERE delivery_status = 'PENDING'
UNION ALL
SELECT 'handover', count(*) FROM structured_handover WHERE delivery_status = 'PENDING'
UNION ALL
SELECT 'outcome', count(*) FROM offer_outcome_notification WHERE delivery_status = 'PENDING';
SQL
```

**ผ่านเมื่อคำสั่ง SQL สำเร็จและ pending = 0 ทั้งสามแถว** นับ PENDING ทั้งหมด รวมรายการ retry ที่ยังไม่ถึงเวลาและรายการที่มี lease ไม่ดูเฉพาะที่พร้อมส่ง หากคำสั่งล้ม/ตารางหายหรือมีค่าเกิน 0 ให้หยุด cutover คง simulation และให้ทีมจัดการคิวด้วย workflow ที่รองรับแล้วตรวจใหม่ ห้ามลบหรือเปลี่ยนสถานะ SQL เพื่อให้ผ่าน หลังคิวว่างและค่าตั้งพร้อมจึง restart nara ตามข้อ 1 ซึ่งจะเริ่ม Job กลับด้วย; ถ้ายกเลิก cutover ให้เริ่ม Job กลับด้วย `sudo docker start nara-staffing-job` โดยคง simulation ไว้ ขั้นนี้ไม่แทนการตรวจ token หรือปลายทางผู้รับ

คิวเป็น snapshot จึงต้องงดกิจกรรมสร้าง intent ต่อจน restart เสร็จ ใน live run ที่รายงานข้างล่าง **ไม่ได้เก็บ SQL ก่อนเปิด real** จึงไม่มีหลักฐานย้อนหลังว่าคิวว่าง ไม่ใช้ SQL ที่รันภายหลังมาอ้างแทน

## 2. ตรวจด่านและเปลี่ยน URL

บนเครื่องภายนอก EC2 ใช้สคริปต์จาก PR นี้ (ไม่จำเป็นต้องเปลี่ยน checkout ของแอปที่รันเพียงเพื่อใช้สคริปต์) อ่านรหัส Basic Auth แบบไม่ echo แล้วรัน:

```bash
# bash: สำหรับ zsh บน Mac ใช้ read -s 'NARA_GATE_PASSWORD?รหัสเข้าเว็บ: '
read -r -s -p 'รหัสเข้าเว็บ: ' NARA_GATE_PASSWORD
printf '\n'
bash deploy/aws/check-gate.sh 'https://<SITE_DOMAIN>' nara "$NARA_GATE_PASSWORD" --require-real-line
unset NARA_GATE_PASSWORD
```

W ต้องได้ 401 จาก webhook ที่ไม่มีลายเซ็น **โดยไม่มี Basic challenge** ถ้าได้ 503 ต้องหยุดแก้ค่าตั้ง; ตัวเลือกเดิมที่ไม่มี flag ยังรับ 401/503 เพื่อทดสอบขั้นเตรียมเครื่องได้ตามเดิม ทั้งสองโหมดไม่ยืนยันว่า LINE ใช้งานจริงได้

ใน LINE Developers ของ Channel เดียวกัน: Messaging API → Webhook URL → ใส่ URL AWS → Update → Verify ต้องสำเร็จ เปิด Use webhook และ Webhook redelivery บันทึกเวลาและผลเท่านั้น ไม่แนบ Channel secret, token, LINE user ID หรือโค้ด LINK อย่าปิด Tunnel จนกว่าข้อ 3 ผ่าน Verify เป็น signed empty callback จึงไม่ยืนยัน Offer/Reply/Push

## 3. ทดสอบกับบัญชี LINE ของทีมบน AWS

ทำทีละขั้นและเก็บผลบน DB AWS (ไม่ใช้หลักฐานจาก localhost/Tunnel):

1. ถ้าจะ reset Demo ต้องได้รับการตกลงให้ล้างสถานการณ์และ bindings ก่อน และทำ **ก่อน** ออกโค้ด LINK จากนั้น freeze เวลาที่ใช้สาธิต อย่า reset หลังผูกหรือรับ Offer เพียงเพื่อสร้าง Log
2. ออกโค้ดให้ staff ทดสอบที่ยังไม่ผูก (ตัวอย่าง 201) ด้วยคำสั่งด้านล่าง ส่งโค้ดให้เจ้าของบัญชีส่วนตัว แล้วพิมพ์ข้อความ LINK ในแชตจริงตามผลคำสั่ง โค้ดแสดงครั้งนี้เท่านั้นและห้ามแนบเป็นหลักฐาน ถ้าแจ้งว่าผูกอยู่แล้ว ให้ตรวจว่าเป็นบัญชีทดสอบที่ถูกต้อง ไม่ unlink ผู้ใช้โดยอัตโนมัติ

```bash
sudo docker exec nara-staffing-backend python -m app.line_accounts issue-code --staff-id 201
```

3. ใช้หน้า Demo สร้างกรณี 105 แจ้งลา (เวร 1) ตาม Golden Case ที่ตรงกับรุ่นที่รัน ตรวจ Offer ถึง LINE ของ 201 จริง กดรับจากปุ่มใน LINE แล้วตรวจเคส/หน้า Approvals ของ 900 ว่าบันทึกคำตอบและมีคำขอที่ควรอนุมัติ ไม่กดตอบแทนจาก simulator
4. อนุมัติจากหน้าเว็บของ 900 ตรวจ Roster/Handover และข้อความยืนยันที่ส่งมาถึง LINE จริง แยกผลส่ง Offer, Reply, Handover ออกจากกัน
5. ใช้ปุ่ม check-in หรือ `CHECKIN <shift_id>` ในเวลาที่ระบบอนุญาต (ดูเวลาเปิด/ปิดบนข้อความ) ตรวจ Attendance และ Audit เป็น staff ที่ผูกไว้และ source SELF ส่งคำสั่งซ้ำแล้วต้องได้ผลเดิม ไม่เพิ่ม Attendance ซ้ำ ไม่เร่ง Demo clock จน Offer หมดอายุระหว่างรอผู้ทดสอบ
6. ทดสอบข้อความทั่วไปตาม PR I ถ้าอยู่ในขอบเขตที่ทีมตรวจรับด้วย บันทึกว่าเป็น deterministic guidance ไม่เรียก LLM
7. เมื่อผ่านครบ เปลี่ยน URL แล้วและยืนยัน LINE ใช้ AWS อยู่ จึงหยุด process/container Tunnel เดิมที่ระบุไว้ **เฉพาะตัวที่ทีมใช้** ไม่ใช้ kill กว้าง แล้วส่งคำสั่ง LINE ใหม่อีกครั้งยืนยันว่า AWS ตอบได้โดยไม่มี Tunnel บันทึกผลก่อนปิด W

ไม่ replay payload ที่เดา LINE user ID หรือสร้าง postback ให้ผู้ใช้เอง ผล redelivery/concurrency/retry อ้างเฉพาะ automated tests หากไม่ได้ทดสอบ live แยก อย่าอ้างว่าเปิด redelivery เท่ากับได้ทดสอบ dedup แล้ว

## 4. ถอยกลับเมื่อ AWS ใช้ไม่ได้

**หยุด cutover / rollback เมื่อเกิดข้อใดข้อหนึ่ง:**
- strict Gate ล้ม, webhook ถูก Basic challenge หรือ unsigned webhook ยังตอบ 503
- Channel Verify ไม่ขึ้น Success (เช่น TLS, timeout, 401/5xx): อย่าปิด Tunnel และอย่าสร้าง Offer เพิ่ม ตรวจ URL/path, DNS/TLS และ Channel secret ของ Channel เดียวกันโดยไม่พิมพ์ค่า ถ้าแก้ไม่ได้ในช่วงทดสอบที่ตกลง ให้คืน URL ไปปลายทางที่ตรวจรับแล้วตามขั้นตอนด้านล่าง จากนั้น Verify ปลายทางนั้นใหม่ก่อนใช้
- LINK ไม่สำเร็จ/ผูกผิดคน, Offer ไม่ถึงบัญชีทดสอบที่ถูกต้อง, กดตอบแล้ว state ไม่ตรง, อนุมัติแล้วไม่ได้ Handover หรือ check-in/Audit ไม่ผ่าน
- เมื่อไม่มี Tunnel แล้ว LINE ใช้งานไม่ได้ หรือ Backend/Job หยุดทำงาน: หยุดทดสอบใหม่และให้คนรับผิดชอบตรวจคิวก่อน retry เพื่อไม่ส่งซ้ำเอง

ขณะตัดสินใจ rollback ให้ทีมงดกิจกรรมสร้างเคส/ข้อความใหม่และหยุด Job AWS ชั่วคราว เมื่อเลือกกลับไป Tunnel ให้เปลี่ยน AWS เป็น simulation และ restart nara ตามข้อ 1 ก่อนเริ่มกิจกรรมใหม่ที่ปลายทาง เพื่อไม่ให้สองฐานส่งข้อความพร้อมกัน ค่าในฐาน AWS ไม่ถูกคัดลอกไปฐาน Tunnel โดยอัตโนมัติ ถ้าไม่มีปลายทางที่พร้อมใช้งาน ให้หยุดทดสอบไว้และรายงานว่า cutover ล้ม ไม่ฝืนเปิด URL ที่หมดอายุ

เปิด proxy/Tunnel ที่ตรวจด่านไว้ ถ้า URL เดิมยังใช้ได้ให้เปลี่ยน Webhook กลับ URL นั้น แต่ถ้า Quick Tunnel เดิมหมดอายุ ต้องสร้าง Tunnel ใหม่ที่ชี้เฉพาะ proxy เดิม ตรวจด่านตาม `dev/line-webhook-proxy` ก่อน แล้วเปลี่ยน Webhook URL เป็น URL ใหม่ ตรวจโหมด LINE และ credentials ของ Backend ปลายทางนั้น แล้ว Verify และทดสอบกับบัญชีที่ผูกใน **DB ของปลายทางนั้น** อีกครั้ง คืนค่าตั้งเครื่อง AWS ตามที่ตกลง (simulation หากหยุดใช้ LINE ที่ AWS) เพื่อกันการส่งข้อความจากสอง DB อย่ารัน reset/ย้าย DB หรือคัดลอก binding โดยเดาว่า staff ID คือคนเดียวกัน บันทึกช่วงเวลาและผล cutover ที่ไม่สำเร็จไว้ W ยังไม่เสร็จ

## หลักฐานตรวจรับ W (user-reported, 2026-10-21)

| เรื่อง | ผล / เวลา / รุ่นที่รัน |
|---|---|
| AWS Git HEAD และ Frontend image ID ตอนตรวจรับ | ผู้ Deploy ส่ง HEAD `514babd56968c84f6fed37106ff63270b668e1a2` และ local image ID `sha256:44ce976dd5db64106a235e4af178aec5416372bdde98eee0eefd26c5651506e5` หลังทดสอบ W เป็นข้อมูลตอนตรวจ ไม่ใช่ build attestation; image ID ต่างจากตอนขั้นที่ 6 จึงไม่ใช้ image เดิมแทนหลักฐานรอบนี้ |
| real-line config และ Gate แบบ strict จากภายนอก | ผู้ Deploy ส่ง `LINE_MODE=real`, `REAL_LINE_CONFIGURED=True` หลัง restart; รัน `check-gate.sh --require-real-line` จาก Mac ได้ `All checks passed`: unsigned webhook ตอบ backend 401 ไม่มี Basic challenge, หน้า/API อยู่หลัง gate, internal routes ถูกปิด, login ถูกผ่านและรหัสผิดถูกปฏิเสธ (user-reported stdout) |
| URL AWS Verify / Use webhook / redelivery | ภาพ LINE Developers แสดง Verify Success บน URL AWS และเปิดทั้ง Use webhook กับ redelivery (2026-10-21); ไม่ใช่ผลทดสอบ redelivery/dedup |
| LINK staff ทดสอบผ่าน AWS | ผู้ Deploy ออกรหัสให้ 201 จาก Backend บน EC2; ภาพ LINE ตอบว่าผูกบัญชีสำเร็จ เวลา 23:47 ไทย ไม่เก็บโค้ดที่ใช้แล้วหรือ LINE UID ในเอกสาร |
| Offer จริงและการตอบผ่านปุ่ม LINE | ภาพ LINE มี Offer ICU เวรข้ามคืนพร้อมปุ่มรับ/ปฏิเสธ และภาพหน้า Approvals มี staff 201 รออนุมัติ (เคส 3, request 1) ผู้ Deploy รายงานว่าใช้งานปกติ ไม่ได้แนบ webhook/audit trace ของการกดปุ่ม |
| Approval → Roster → Handover จริง | ภาพ LINE แสดงข้อความยืนยันจัดเวรและ Handover #1 หอ ICU เหตุ NO_SHOW พร้อมปุ่ม check-in เวลา 23:50 ไทย; ยังไม่ได้แนบผลอ่าน Roster/Audit โดยตรง |
| Check-in และคำสั่งซ้ำ / Attendance / Audit | ภาพ LINE ตอบเช็กอินเวร 1 สำเร็จ เวลา 23:50 (ทันเวลา); ผู้ Deploy รายงานว่าส่งคำสั่งเช็กอินซ้ำแล้วตอบว่าไม่ต้องเช็กซ้ำ; ผล SQL บน PostgreSQL ของ AWS ยืนยัน staff 201 / shift 1 มี Attendance 1 แถว และ ATTENDANCE_CHECKED_IN Audit 1 แถว actor staff 201, source SELF (user-reported stdout) ไม่ใช่ผล replay webhookEventId เดิม |
| ไม่มี Tunnel เดิมแล้ว LINE ยังทำงานผ่าน AWS | ผู้ Deploy ยืนยันว่า Quick Tunnel timeout ไปหลายวันก่อนทดสอบ W และ LINE ยังตอบคำสั่ง check-in ซ้ำว่าไม่ต้องเช็กซ้ำ จึงไม่ต้องหยุด Tunnel ที่หมดอายุแล้ว ไม่ได้ทดสอบ rollback ไป Tunnel ใหม่ในรอบนี้ |

หลักฐานข้างต้นมาจากผู้ Deploy ผ่านแชทและภาพ ไม่ใช่ independent rerun แถว W และแถว LINE/ผูกบัญชีใน workflow อ้างผลตามขอบเขตนี้ automated Caddy tests 5 ข้อใช้ fake upstream เท่านั้น ไม่ได้เรียก LINE จริง ไม่ได้ทดสอบ live crash/retry/concurrency, webhookEventId redelivery หรือ rollback; การเช็กอินซ้ำเป็นคำสั่งใหม่ จึงไม่ใช่ผล dedup ของ Event เดิม ถ้า AU4 เปลี่ยนกติกา auth ภายหลัง ต้องรัน Gate ที่ปรับตามกติกาใหม่และ LINE smoke ซ้ำ
