# ขั้นที่ 6: ผลตรวจเครื่อง AWS วันที่ 2026-10-21

บันทึกจากผลคำสั่ง ภาพหน้าจอ และการยืนยันการใช้งานที่คน 3 ส่งระหว่าง Deploy ไม่ใช่ผลการรันทดสอบจากเครื่องของผู้รีวิว และไม่ใช่ผล LINE/Bedrock integration ของ W/B2

เครื่องทดสอบอยู่ใน `ap-southeast-1` ใช้ `https://narastaffing.com` และไฟล์ `/etc/nara/nara.env` เจ้าของ root สิทธิ์ 600 พร้อม manual-env drop-in ตาม PR #118 ไม่มีความลับในบันทึกนี้

**สถานะ:** คน 3 ตรวจเครื่องจริงและหน้าเว็บแล้วตามผลด้านล่าง หลักฐานนี้ให้ทีมรีวิวความพร้อมก่อน W/B2 ไม่ใช่การอ้างว่าผู้ร่วมทีมทั้งสามรันคำสั่งซ้ำแล้ว

| รายการ | ผลที่ยืนยันแล้ว |
|---|---|
| เริ่มบริการ | `systemctl restart nara` สำเร็จ; `active (exited)` และ ExecStart status 0 สำหรับบริการ oneshot |
| Container | Backend, Frontend, PostgreSQL และ Redis healthy; Job และ Caddy running |
| พอร์ต | Compose ps แสดงเฉพาะ Caddy publish TCP 80/443; พอร์ตของ Frontend/DB/Redis ไม่ publish บน host |
| HTTPS และด่าน | `curl https://narastaffing.com/` โดยไม่ส่งรหัสได้ 401 โดยไม่ข้ามการตรวจ TLS |
| Frontend | Config.Cmd เป็น next start, Mounts = 0, NODE_ENV = production |
| Gate จากภายนอก | คน 3 รัน `deploy/aws/check-gate.sh` จาก Mac: All checks passed |
| รายละเอียด Gate | หน้าและ API ไม่มีรหัส/รหัสผิดได้ 401 Basic; มีรหัสได้ 200; internal routes ได้ 404 ทั้งมีและไม่มีรหัส; URI/Method ที่ไม่ตรง Webhook ยังติดด่าน |
| Webhook ณ วันที่ตรวจ | POST /api/line/webhook ได้ 503 passed ใน LINE simulation เป็นการผ่าน proxy gate ไม่ใช่หลักฐาน LINE จริง |
| ฐานข้อมูลและเว็บ | ก่อนเตรียม Demo ตาราง public = 0; ภาพ Dashboard หลังเตรียมระบบแสดง API/DB ok, หอ ICU และ Demo clock; ผู้ใช้ยืนยันว่า Dashboard, Gap, Demo และหน้าเคสทำงานปกติ ไม่ได้แนบผล stdout ของ seed |
| Browser Console | ภาพ Console ของ Dashboard, Gap, Demo control และ `/cases/1` ไม่แสดง Error; หน้าเคสแสดง Gap ขาด 1 RN และ Offer ของ 201/202 ในโหมดจำลอง |
| API บน Origin เดียวกัน | ภาพ Network ของหน้าเคสมีคำขอ case/audit/clock ได้ 200; ผู้ใช้คัดลอก Request URL จริงเป็น `https://narastaffing.com/api/cases/1/audit` |
| Browser bundle | สแกน `/app/.next/static` ทุกไฟล์ยกเว้น `.map` ด้วย Node ใน Container ได้ `PASS: ไม่พบ localhost:8000` |
| การใช้งานหลังผ่าน Basic Auth | ผู้ใช้รายงานว่าหน้าเว็บทำงานปกติระหว่างเปลี่ยนหน้า ไม่ได้รายงานปัญหาถามรหัสซ้ำ ทั้งนี้ไม่ได้จำลอง Backend 401 ทุกชนิด |

## วิธีตรวจซ้ำที่ไม่ล้างข้อมูล

ตรวจ Frontend บน EC2:

```bash
sudo docker inspect nara-staffing-frontend --format '{{json .Config.Cmd}}'
sudo docker inspect nara-staffing-frontend --format '{{len .Mounts}}'
sudo docker exec nara-staffing-frontend printenv NODE_ENV
```

สแกน Bundle ด้วย Node ที่มีอยู่ใน image (BusyBox grep บนเครื่องจริงไม่รองรับ `--exclude`):

```bash
sudo docker exec -i nara-staffing-frontend node <<'JS'
const fs = require('fs');
const path = require('path');
let matches = 0;
function scan(dir) {
  for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, item.name);
    if (item.isDirectory()) scan(file);
    else if (!file.endsWith('.map') &&
             fs.readFileSync(file).includes(Buffer.from('localhost:8000'))) {
      console.log('พบใน:', file);
      matches++;
    }
  }
}
scan('/app/.next/static');
console.log(matches === 0 ? 'PASS: ไม่พบ localhost:8000' : 'FAIL: พบ localhost:8000');
process.exitCode = matches ? 1 : 0;
JS
```

Gate ต้องรันจากเครื่องภายนอก EC2 ตามคู่มือ ใช้รหัส Basic Auth ต้นฉบับ ไม่ใช่ Hash และไม่บันทึกรหัสลง repo/Log ส่วนการตรวจเว็บต้องเปิด DevTools บนโดเมน AWS ไม่ใช่ localhost ตรวจ Console พร้อม Network และดู Request URL จริง ผลการโหลดหน้า HTML 200 อย่างเดียวไม่ยืนยันว่า API ใช้ได้

## ปัญหาติดตั้งที่พบและแก้แล้ว

Compose ล้มด้วย `compose build requires buildx 0.17.0 or later` หลังติดตั้ง Buildx เพิ่ม บริการเริ่มและ Frontend healthy แล้ว คู่มือ Deploy เพิ่มขั้นติดตั้งและตรวจ Buildx สำหรับเครื่องใหม่ ต้องตรวจเวอร์ชันจริงก่อน build ไม่ถือว่าเพียงติดตั้ง Docker Engine/Compose ครบแล้ว

## งานถัดไป

อ้างบันทึกนี้ใน Description ของ PR แรกที่ใช้เครื่อง (W หรือ B2) ตาม workflow.md 6.30 ให้ทีมตรวจหลักฐานและดำเนินงานถัดไปได้ ตอนนี้ LINE simulation, LLM disabled; ห้ามอ้างว่าผ่าน live integration แล้วจากผล Gate

- W: ตั้ง LINE จริงและ Webhook `/api/line/webhook` ทดสอบผูกบัญชี Offer/ปุ่ม และเช็กอินผ่าน AWS ก่อนปิด Tunnel บันทึกผลจริงแยกจากการตรวจด่าน
- B2: เตรียมสิทธิ์ AWS ของแอปและชุดทดลองผ่าน B1 การที่ Console เรียกโมเดลได้ไม่ได้ยืนยันสิทธิ์ของ EC2
- การทดสอบเชื่อมต่อบริการจริงและการปิดรอบ 6 ยังไม่เสร็จจากหลักฐานขั้นที่ 6 นี้
