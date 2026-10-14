# เครื่องทดสอบบน AWS (รอบ 3 PR D)

> เครื่องนี้มีไว้ลอง LINE จริงและ Bedrock จริงร่วมกัน ไม่ใช่ระบบใช้งานจริง ข้อตกลงอยู่ใน `docs/workflow.md` ข้อ 6.16 และ 6.17 และร่างรอบ 3 ข้อ 2.1.1 (R3-Q12, R3-Q19 ถึง R3-Q21)

## ภาพรวม

```text
อินเทอร์เน็ต ── 443 / 80 ──> Caddy (HTTPS, Basic Auth)
                                ├── /api/line/webhook (POST เท่านั้น ไม่ผ่านด่าน) ──> backend
                                ├── /api/internal/*   ตอบ 404 เสมอ
                                ├── /api/*            ผ่านด่าน ตัด /api ออก ──> backend
                                └── อื่น ๆ             ผ่านด่าน ──> frontend
```

* เครื่อง EC2 หนึ่งเครื่องรัน `docker compose` ชุดเดียวกับเครื่องพัฒนา โดยซ้อนไฟล์ `deploy/aws/docker-compose.aws.yml` ไว้ข้างบน ไฟล์นี้ปิด Port ของทุก Service แล้วเปิดเฉพาะ Caddy ที่ Port 80 และ 443
* หน้าเว็บและ API อยู่ใน Domain เดียวกัน API อยู่ใต้ `/api` เบราว์เซอร์จึงส่งรหัส Basic Auth ที่กรอกตอนเปิดหน้าเว็บไปกับคำขอ API เองโดยไม่ต้องแก้โค้ด Frontend และไม่ติด CORS
* Caddy ขอใบรับรอง HTTPS จาก Let's Encrypt เอง Domain จึงต้องชี้มาที่เครื่องก่อนเริ่มครั้งแรก
* `/api/internal/*` ตอบ `404` จากภายนอกเสมอ เพราะมีแค่ Job ที่เรียก และเรียกผ่าน Network ภายในของ compose

## ด่าน Basic Auth

* ด่านครอบทุก Path รวม API, `/api/docs` และ `/api/demo/*` ข้อยกเว้นมีหนึ่งเดียวคือ `POST /api/line/webhook` ตรงตัว ซึ่ง Backend กันด้วยลายเซ็นของ LINE (`workflow.md` ข้อ 6.16) ด่านนี้เป็นข้อกำหนดของข้อ 6.17
* Method อื่นของ Path นั้น, Path ที่ต่อท้าย (`/api/line/webhook/x`, `/api/line/webhooks`, `/api/line/webhook/`) และ `/line/webhook` ที่ไม่มี `/api` ต้องผ่านด่านทั้งหมด
* `X-Demo-User` ตั้งเองได้ ใครผ่านด่านได้ก็ทำแทนพยาบาลหรือ Head Nurse คนไหนก็ได้ รหัสจึงต้องเก็บในทีม ห้ามเปิดเครื่องให้เข้าจากภายนอกถ้าด่านยังไม่ผ่าน `check-gate.sh`
* ลองด่านจากเครื่องไหนก็ได้ที่มี `bash` และ `curl`:

  ```bash
  bash deploy/aws/check-gate.sh https://<SITE_DOMAIN> <user> <password>
  ```

  สคริปต์แยก `401` ของด่านกับ `401` ของ Webhook จาก Header `WWW-Authenticate: Basic` ซึ่งมีเฉพาะของด่าน ต้องรันทุกครั้งที่แก้ `Caddyfile` และหลังตั้งเครื่องใหม่

## ความลับและค่าตั้ง (Parameter Store)

ทุกค่าอยู่ใต้ Path `/nara/test` (เปลี่ยนได้ด้วย `NARA_PARAMETER_PATH`) ตอนเครื่องเริ่ม `load-env.sh` อ่านทุกค่าใต้ Path นั้นแล้วเขียนเป็น `/etc/nara/nara.env` (สิทธิ์ `600` อยู่นอก repo) ชื่อสุดท้ายของ Parameter กลายเป็นชื่อตัวแปร แอปอ่านจาก env อย่างเดียว ไม่รู้จัก Parameter Store

| Parameter | ชนิด | ใครใส่ | ค่า |
| --- | --- | --- | --- |
| `SITE_DOMAIN` | String | คน 1 | Domain ของเครื่อง เช่น `nara-test.<domain ของทีม>` ไม่มี `https://` |
| `ACME_EMAIL` | String | คน 1 | อีเมลที่ Let's Encrypt ใช้แจ้งเรื่องใบรับรอง |
| `BASIC_AUTH_USER` | String | คน 1 | ชื่อผู้ใช้ของด่าน |
| `BASIC_AUTH_HASH` | SecureString | คน 1 | Hash ของรหัส สร้างด้วย `docker run --rm caddy:2.10-alpine caddy hash-password --plaintext '<รหัส>'` รหัสจริงส่งกันในทีม ไม่เก็บใน repo |
| `POSTGRES_PASSWORD` | SecureString | คน 1 | สร้างด้วย `openssl rand -hex 24` (ใช้ตัวอักษรฐาน 16 เพราะค่านี้อยู่ใน `DATABASE_URL`) มีผลแค่ตอนสร้าง Volume ของฐานข้อมูลครั้งแรก |
| `INTERNAL_JOB_SECRET` | SecureString | คน 1 | สร้างด้วย `openssl rand -hex 24` |
| `LINE_MODE` | String | คน 3 | `real` เมื่อพร้อมลอง LINE จริง ไม่ใส่ = `simulation` |
| `LINE_CHANNEL_SECRET` | SecureString | คน 3 | จาก LINE Developers Console |
| `LINE_CHANNEL_ACCESS_TOKEN` | SecureString | คน 3 | จาก LINE Developers Console |

* หกค่าแรกต้องมี ถ้าขาด `load-env.sh` หยุดและ Stack ไม่เริ่ม
* ค่าห้ามมี `'` หรือขึ้นบรรทัดใหม่ เพราะไฟล์ env เก็บค่าในเครื่องหมาย `'` ซึ่งทำให้ `$` ใน Hash ไม่ถูกอ่านเป็นตัวแปร
* ตัวแปรใหม่ (เช่นของ Bedrock ใน PR X) ต้องมีทั้ง Parameter และชื่อในส่วน `environment` ของ Service ใน `docker-compose.yml` เพราะไฟล์ env ใช้แทนค่าใน compose เท่านั้น ไม่ได้ส่งเข้า Container เอง
* เปลี่ยนค่าแล้วให้ `sudo systemctl restart nara` ค่าใหม่ถูกอ่านทุกครั้งที่เริ่ม

## ตั้งเครื่องครั้งแรก (คน 1)

1. **EC2:** Amazon Linux 2023 ซึ่งมี AWS CLI v2 และ `python3` มาให้ ซึ่ง `load-env.sh` ใช้ RAM อย่างน้อย 4 GB เพราะ `npm ci` และ `next dev` ตอน Compile ใช้มากกว่าตอนรันปกติ (บนเครื่องพัฒนาทุก Service รวมกันใช้ราว 1 GB ตอนว่าง) Disk 30 GB
2. **Security Group:** เปิด 80 และ 443 ให้ทุกที่ (Let's Encrypt และ LINE ต้องเข้าถึง) SSH 22 เปิดเฉพาะ IP ของทีม
3. **Elastic IP และ DNS:** ผูก Elastic IP กับเครื่อง แล้วตั้ง Record `A` ของ `SITE_DOMAIN` ให้ชี้ไปที่ IP นั้นก่อนเริ่ม Stack ครั้งแรก
4. **IAM Role ของเครื่อง:** สร้าง Role ให้ EC2 แนบ Policy จาก `deploy/aws/iam-parameter-read-policy.json` (แทน `REGION` และ `ACCOUNT_ID`) Policy นี้อ่านได้แค่ Path `/nara/test` ใช้ Key `aws/ssm` ที่ AWS สร้างให้ ถ้าเปลี่ยนเป็น Key ของทีมเองต้องเพิ่ม `kms:Decrypt` ของ Key นั้น
5. **ใส่ Parameter:** ตามตารางข้างบน ใน Region เดียวกับเครื่อง
6. **ติดตั้ง Docker และ Compose:**

   ```bash
   sudo dnf install -y docker git
   sudo systemctl enable --now docker
   sudo mkdir -p /usr/local/lib/docker/cli-plugins
   sudo curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose \
     https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)
   sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
   docker compose version   # ต้องเป็น 2.24 ขึ้นไป เพราะไฟล์ซ้อนใช้ !reset
   ```

7. **โค้ดและบริการ:**

   ```bash
   sudo git clone --branch staging https://github.com/Bobbie-CPE38/nara.git /opt/nara
   sudo mkdir -p /etc/nara
   echo 'AWS_REGION=<region ของเครื่อง>' | sudo tee /etc/nara/aws.conf
   sudo cp /opt/nara/deploy/aws/nara.service /etc/systemd/system/nara.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now nara
   ```

   ครั้งแรกใช้เวลาหลายนาทีเพราะต้องติดตั้ง Package ของ Python และ npm ดูความคืบหน้าด้วย `sudo journalctl -u nara -f` และคำสั่ง `ps` ข้างล่าง

8. **ฐานข้อมูลและข้อมูล Demo:** เมื่อทุก Service healthy แล้ว รัน `seed` ตามข้างล่างหนึ่งครั้ง
9. **ลองด่าน:** รัน `check-gate.sh` จากเครื่องของตัวเอง ต้องผ่านทุกข้อก่อนส่ง URL ให้คนอื่น

คำสั่ง compose บนเครื่องนี้ต้องมีไฟล์ซ้อนและไฟล์ env ทุกครั้ง:

```bash
cd /opt/nara
alias dc='sudo docker compose --env-file /etc/nara/nara.env -f docker-compose.yml -f deploy/aws/docker-compose.aws.yml'
dc ps                                    # สถานะ
dc logs -f backend                       # Log
dc exec -T backend python -m app.seed    # ลบ Schema, Migrate ถึง head แล้วโหลด Demo (เหมือน make reset)
```

## Deploy โค้ดใหม่

```bash
cd /opt/nara
sudo git pull
sudo systemctl restart nara
```

Backend และ Frontend เป็น Dev server ที่อ่านโค้ดจาก Volume เหมือนเครื่องพัฒนา (R3-Q20 ใช้ `docker compose` ชุดเดิม) Restart ทำให้อ่าน Parameter Store ใหม่ด้วย ถ้า PR ที่เข้ามามี Migration ให้รัน `seed` ใหม่ ซึ่งล้างข้อมูลบนเครื่อง ใครเป็นคน Deploy และ Deploy เมื่อไรให้ตกลงในทีม

## ส่วนของคน 2 (Bedrock)

* เพิ่มสิทธิ์เรียกเฉพาะโมเดลที่ใช้ลงใน IAM Role ของเครื่อง (Role เดียวกับข้อ 4)
* Backend อยู่ใน Container จึงขอ Credential ของ Role ผ่าน IMDSv2 ข้าม Network ของ Docker หนึ่งชั้น ต้องตั้ง Hop limit ของ Metadata ของเครื่องเป็น 2 ขึ้นไป ถ้าเป็น 1 Container จะได้ Credential ไม่ได้
* AWS Budget สำหรับแจ้งเตือน และตรวจว่าเครดิต AWS ครอบคลุม Bedrock
* ตัวแปรของ LLM ใส่เป็น Parameter และเพิ่มชื่อใน `docker-compose.yml` ตามหัวข้อความลับ

## ส่วนของคน 3 (LINE)

* URL ของ Webhook: `https://<SITE_DOMAIN>/api/line/webhook`
* ใส่ `LINE_MODE`, `LINE_CHANNEL_SECRET` และ `LINE_CHANNEL_ACCESS_TOKEN` ลง Parameter Store แล้ว `sudo systemctl restart nara`
* เปิด "Webhook redelivery" ใน LINE Developers Console (ค่าเริ่มต้นปิด `workflow.md` ข้อ 6.16)
* ลองรับ Webhook จริงหนึ่งรอบ
