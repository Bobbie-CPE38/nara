# ขั้นที่ 6: หลักฐานที่ผู้ Deploy รายงาน วันที่ 2026-10-21 (ยังไม่ปิดช่วง ข)

บันทึกจากผลคำสั่ง ภาพหน้าจอ และการยืนยันการใช้งานที่คน 3 ส่งระหว่าง Deploy ไม่ใช่ผลการรันทดสอบจากเครื่องของผู้รีวิว และไม่ใช่ผล LINE/Bedrock integration ของ W/B2

ใช้เครื่องทดสอบของทีมใน Region ที่ผู้จัดอนุญาต พร้อม manual-env drop-in ตาม PR #118 ไฟล์ค่าตั้งเป็นของ root สิทธิ์ 600 บันทึกสาธารณะนี้ไม่ใส่ชื่อโดเมน IP บัญชี หรือข้อมูลผู้ติดต่อจริง; hostname และ URL ในหลักฐานใช้ `<SITE_DOMAIN>` แทน วิธีติดตั้งและโครงสร้าง path ทั่วไปยังอยู่ในคู่มือ Deploy

**สถานะ: PARTIAL / USER-REPORTED EVIDENCE.** ผู้ Deploy (คน 3) ส่ง stdout ภาพหน้าจอ และรายงานการใช้งานผ่านแชท ผู้บันทึกไม่ได้เชื่อมต่อ EC2 หรือรันซ้ำเอง และไม่อ้างว่าผู้ร่วมทีมทั้งสามตรวจซ้ำแล้ว ผล Gate สคริปต์ผ่านไม่เท่ากับการปิดช่วง ข ทุกข้อ ยังมีช่องว่างในหัวข้อท้ายไฟล์

## รุ่นที่ผู้ Deploy ยืนยัน

- Git HEAD บน EC2: `514babd56968c84f6fed37106ff63270b668e1a2` จาก `sudo git -C /opt/nara rev-parse HEAD`
- Frontend Docker image ID: `sha256:bfcf3997afd0db07b612dfec762c2a6c19ac4efafd97aa8c09539d786cb72aa4` จาก `sudo docker inspect nara-staffing-frontend --format '{{.Image}}'` เป็น local image content ID ไม่ใช่ registry RepoDigest
- สองค่านี้เป็นผลรายงานเพิ่มเติมหลังเก็บภาพ/ผลทดสอบ ไม่ใช่ build attestation หรือหลักฐานว่า checkout ไม่มีไฟล์แก้ค้าง ต้องเก็บใหม่เมื่อ Deploy เปลี่ยน ไม่ใช้ SHA ของ PR เอกสารนี้แทนรุ่นแอปที่ Deploy


| รายการ | ผลที่ผู้ Deploy รายงาน |
|---|---|
| เริ่มบริการ | `systemctl restart nara` สำเร็จ; `active (exited)` และ ExecStart status 0 สำหรับบริการ oneshot |
| Container | Backend, Frontend, PostgreSQL และ Redis healthy; Job และ Caddy running |
| พอร์ต | Compose ps แสดงเฉพาะ Caddy publish TCP 80/443; พอร์ตของ Frontend/DB/Redis ไม่ publish บน host |
| HTTPS และด่าน | `curl https://<SITE_DOMAIN>/` โดยไม่ส่งรหัสได้ 401 โดยไม่ข้ามการตรวจ TLS |
| Frontend | Config.Cmd เป็น next start, Mounts = 0, NODE_ENV = production |
| Gate จากภายนอก | คน 3 รัน `deploy/aws/check-gate.sh` จาก Mac: All checks passed |
| รายละเอียด Gate | ผ่านรายการทดสอบของ `deploy/aws/check-gate.sh` ที่ commit ข้างต้น: หน้า/API อยู่หลังด่านรหัส และเส้นทางภายในถูกปิด ผลและ expected status ของแต่ละ probe ดูสคริปต์ ไม่ใส่ mapping URL ของเครื่องจริงเพิ่มในบันทึกนี้ |
| Webhook ณ วันที่ตรวจ | ในโหมด simulation/unconfigured คาดว่า Backend ตอบ **503 โดยไม่มี Basic challenge**; stdout ได้ `503 passed` ตรง expected นี้ คำว่า passed หมายถึง proxy ยกเว้นด่านรหัสให้ request ตรงรูปแบบแล้วส่งถึง Backend เท่านั้น โหมดนี้ยังไม่ให้บริการ LINE จริง ไม่ได้ทดสอบลายเซ็นที่ถูกต้อง Reply หรือ Push |
| ฐานข้อมูลและเว็บ | ก่อนเตรียม Demo ตาราง public = 0; ภาพ Dashboard หลังเตรียมระบบแสดง API/DB ok, หอ ICU และ Demo clock; ผู้ใช้ยืนยันว่า Dashboard, Gap, Demo และหน้าเคสทำงานปกติ ไม่ได้แนบผล stdout ของ seed |
| Browser Console | ภาพ Console ของ Dashboard, Gap, Demo control และ `/cases/1` ไม่แสดง Error; หน้าเคสแสดง Gap ขาด 1 RN และ Offer ของ 201/202 ในโหมดจำลอง |
| API บน Origin เดียวกัน | ภาพ Network ของหน้าเคสมีคำขอ case/audit/clock ได้ 200; ผู้ใช้คัดลอก Request URL จริงเป็น `https://<SITE_DOMAIN>/api/cases/1/audit` |
| Browser bundle (ขอบเขตจำกัด) | สแกน `/app/.next/static` ทุกไฟล์ยกเว้น `.map` ด้วย Node ใน Container ได้ `PASS: ไม่พบ localhost:8000`; ตรวจเฉพาะ literal นี้ ไม่ใช่การยืนยันว่าไม่มี URL ภายในทุกชนิด |
| การใช้งานหลังผ่าน Basic Auth | ผู้ใช้รายงานว่าหน้าเว็บทำงานปกติระหว่างเปลี่ยนหน้า ไม่ได้รายงานปัญหาถามรหัสซ้ำ ทั้งนี้ไม่ได้จำลอง Backend 401 ทุกชนิด |

## วิธีตรวจซ้ำที่ไม่ล้างข้อมูล

ตรวจ Frontend บน EC2:

```bash
sudo docker inspect nara-staffing-frontend --format '{{json .Config.Cmd}}'
sudo docker inspect nara-staffing-frontend --format '{{len .Mounts}}'
sudo docker exec nara-staffing-frontend printenv NODE_ENV
```

สแกน Bundle ด้วย Node ที่มีอยู่ใน image (BusyBox grep บนเครื่องจริงไม่รองรับ `--exclude`): ผล PASS ครอบคลุมเฉพาะ bytes `localhost:8000` ในไฟล์ static ที่ไม่ใช่ `.map` ไม่ครอบคลุม `127.0.0.1:8000`, `backend:8000`, port อื่น, string ที่ต่อกันตอน runtime, `.map` หรือ `.next/server` จึงใช้คู่กับ Network ของเบราว์เซอร์ ไม่ใช่การตรวจ secrets หรือ URL ทั้ง image ฝั่ง `.next/server` อาจมี URL ภายในที่ใช้ server-to-server ได้ตามการออกแบบ ต้องประเมินแยก ไม่อนุมานว่าผ่านจาก scanner นี้

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

### ตรวจไฟล์ Buildx สำหรับแก้คู่มือ (แยกจากเครื่อง Deploy)

ระหว่างแก้รีวิว 2026-10-21 ผู้บันทึกตรวจ [release v0.38.1](https://github.com/docker/buildx/releases/tag/v0.38.1) ผ่าน GitHub API และดาวน์โหลด binary `buildx-v0.38.1.linux-amd64` เทียบกับ [checksums.txt](https://github.com/docker/buildx/releases/download/v0.38.1/checksums.txt) และ digest metadata ของ asset ได้ SHA-256 ตรงกัน:

```text
e25d5cd675092bb5d1d03632fdc46cdf3fede7b514dc5f023a105e00d3ce5ad4
```

รัน binary ที่ตรวจแล้วใน Container Linux amd64 แยก ได้ `github.com/docker/buildx v0.38.1 0dbe87f36ed472fe36b6796c3f70b4210a731fc5` จึงยืนยันว่า release มีอยู่และไฟล์ทำงานสำหรับคำสั่ง version ได้ ไม่ใช่ผลการทดสอบ version บน EC2 ไม่ได้ทดสอบ build แอปใหม่ด้วย binary นี้ และไม่ได้ตรวจลายเซ็น release แบบอิสระ

ทดสอบ recipe ใน Container แยกด้วย assets ที่ดาวน์โหลดจริง โดยจำลอง curl เป็นการคัดลอก assets: parent plugin directory ที่ยังไม่มีถูกสร้างด้วย `install -D` และ binary ที่แก้ bytes ให้ checksum ไม่ตรงถูกปฏิเสธก่อนติดตั้ง การ replay นี้ไม่ได้ติดตั้งลง EC2 หรือยืนยันการตั้งค่าเครื่องจริงเพิ่มเติม

## ช่องว่างและเงื่อนไขก่อนปิดช่วง ข

- ยังไม่มีผู้รีวิวรันซ้ำ หลักฐานทั้งหมดเป็น user-reported; ทีมต้องตรวจรับ ไม่ใช้ไฟล์นี้เป็นการอนุมัติให้ข้าม dependency ของ W/B2 อัตโนมัติ
- ไม่ได้แนบ stdout ของ seed; UI/DB health ยืนยันว่าอ่านข้อมูลได้ แต่ไม่ยืนยันขั้นตอน migrate/seed ทุกขั้นหรือ migration head บนเครื่อง ต้องเก็บผล migration head/ความสอดคล้อง schema เพิ่มก่อนปิดช่วง ข โดยไม่รัน seed ซ้ำเพียงเพื่อสร้าง Log เพราะล้างข้อมูล
- พฤติกรรม Backend 401 (`WWW-Authenticate: X-Demo-User`) ยังไม่ได้จำลอง; รายงานว่าใช้งานปกติและภาพไม่เห็น prompt ซ้ำ ไม่ได้แทนการทดสอบกรณีนี้ ต้องทดสอบและบันทึกผลก่อนปิดช่วง ข
- Bundle scan มีขอบเขตตามที่ระบุข้างบน; Network แสดงตัวอย่าง request บน origin เดียวกัน ไม่ได้ยืนยันทุกเส้นทางหรือทุก browser
- ต้องเก็บหลักฐานเพิ่มผูกกับ revision/image เดิม หรือรัน Gate/Frontend/browser ใหม่หากเปลี่ยนรุ่นระหว่างเก็บผล

## งานถัดไป

อ้างไฟล์นี้เป็น **หลักฐานบางส่วนที่ผู้ Deploy รายงาน** ใน Description ของ W/B2 พร้อมรายการช่องว่าง ไม่ใช่การประกาศปิดขั้นที่ 6 ทีมต้องตรวจและปิดข้อค้างข้างบนตาม workflow.md 6.30 ก่อนเริ่มงานที่ต้องรอขั้นนี้ ตอนนี้ LINE simulation, LLM disabled; ห้ามอ้างว่าผ่าน live integration จาก Gate

- W: เมื่อเครื่องผ่านการตรวจรับครบแล้ว จึงทดสอบ LINE จริงและผูกบัญชี Offer/ปุ่ม และเช็กอินผ่าน AWS ก่อนปิด Tunnel บันทึกผลจริงแยกจากการตรวจด่าน
- B2: เตรียมสิทธิ์ AWS ของแอปและชุดทดลองผ่าน B1 การที่ Console เรียกโมเดลได้ไม่ได้ยืนยันสิทธิ์ของ EC2
- การทดสอบเชื่อมต่อบริการจริงและการปิดรอบ 6 ยังไม่เสร็จจากหลักฐานนี้
