# เครื่องทดสอบบน AWS (รอบ 6 PR D)

> เครื่องนี้มีไว้ลอง LINE จริงและ Bedrock จริงร่วมกัน ไม่ใช่ระบบใช้งานจริง ข้อตกลงอยู่ใน `docs/workflow.md` ข้อ 6.16, 6.17, 6.27, 6.28 และ 6.30 (R3-Q12, R3-Q19 ถึง R3-Q21, R6-Q3 ถึง R6-Q6, R6-Q13) PR D เขียนไฟล์ชุดนี้และไม่เปิดเครื่อง การเปิดเครื่องและตรวจบนเครื่องจริงเป็น "ขั้นที่ 6" ของรอบ 6 (ข้อ 6.30)

## ภาพรวม

```text
อินเทอร์เน็ต ── 443 / 80 ──> Caddy (HTTPS, Basic Auth)
                                ├── POST /api/line/webhook ตรงตัว (ไม่ผ่านด่าน) ──> backend
                                ├── /api/internal/*        ตอบ 404 เสมอ
                                ├── /api/*                 ผ่านด่าน ตัด /api ออก ──> backend
                                └── อื่น ๆ                  ผ่านด่าน ──> frontend
```

* เครื่อง EC2 หนึ่งเครื่องรัน `docker compose` ชุดเดียวกับเครื่องพัฒนา โดยซ้อนไฟล์ `deploy/aws/docker-compose.aws.yml` ไว้ข้างบน ไฟล์นี้ปิด Port ของทุก Service แล้วเปิดเฉพาะ Caddy ที่ Port 80 และ 443
* หน้าเว็บและ API อยู่ใน Domain เดียวกัน API อยู่ใต้ `/api` เบราว์เซอร์จึงส่งรหัส Basic Auth ที่กรอกตอนเปิดหน้าเว็บไปกับคำขอ API เองโดยไม่ต้องแก้โค้ด Frontend และไม่ติด CORS
* Caddy ขอใบรับรอง HTTPS จาก Let's Encrypt เอง Domain จึงต้องชี้มาที่เครื่องก่อนเริ่มครั้งแรก ใบรับรองเก็บใน Volume `caddy_data` เปิดปิดเครื่องแล้วไม่ต้องขอใหม่
* `/api/internal/*` ตอบ `404` จากภายนอกเสมอ ทั้งมีและไม่มีรหัส เพราะมีแค่ Job ที่เรียก และเรียกผ่าน Network ภายในของ compose
* Frontend เป็น production image (`deploy/aws/frontend.Dockerfile`, PR F3): `next build` ทำตอนสร้าง image และ `next start` ให้บริการ ไม่มี bind mount โค้ดเข้า Container ที่อยู่นอก image ใช้ RAM ตอนว่างราว 45 ถึง 120 MiB (Dev server เคยวัดได้ 424 MiB) Backend ยังเป็น Dev server เหมือนเครื่องพัฒนา **ห้ามเปิดให้ภายนอกเข้าก่อนผ่านช่วง ข**

## ด่าน Basic Auth

กฎเดียว (ข้อ 6.30): **ทุก Path ต้องมีรหัสของเครื่อง ยกเว้น `POST /api/line/webhook` ตรงตัว** ไม่มีการกัน `/demo/` แยกต่างหาก ใครใส่รหัสแล้วใช้หน้า Demo และเรียก `/api/demo/*` ได้ เพราะหน้า Demo control เรียก API เหล่านั้นจากเบราว์เซอร์ รหัสตัวเดียวให้ทุกคนที่เข้าได้มีสิทธิ์เท่ากัน (ข้อ 6.17) ใครรู้รหัสก็รีเซ็ตข้อมูล Demo ได้

* ชื่อ Path มีสองชนิด: หน้าเว็บไม่มี `/api` (`/demo/control`, `/demo/line-sim`) ส่วน API มี `/api` นำหน้า (`/api/demo/reset`, `/api/demo/clock/advance`, `/api/demo/attendance/check-in`, `/api/clock`) Caddy ตัด `/api` ออกก่อนส่งให้ Backend ฝั่ง Backend จึงเห็น `/demo/reset`
* ข้อยกเว้นของ Webhook จับจาก **URI ดิบของคำขอ** (`{http.request.orig_uri}`) ไม่ใช้ตัวจับ `path` ของ Caddy เพราะตัวนั้นไม่สนตัวพิมพ์เล็กใหญ่ รวม `//` และถอดรหัส `%6C` ทำให้ `/API/line/webhook`, `/api//line/webhook` และ `/api/%6Cine/webhook` หลุดด่านได้ (ตรวจแล้วกับ Caddy 2.10.2 ด้วยตัวจับเดิมของ PR D รอบ 3)
* Method อื่นของ Path นั้น, Path ที่ต่อท้าย (`/api/line/webhook/x`, `/api/line/webhooks`, `/api/line/webhook/`), Query (`?x=1`) และ `/line/webhook` ที่ไม่มี `/api` ต้องผ่านด่านทั้งหมด
* Tunnel ในเครื่องพัฒนา (`dev/line-webhook-proxy`) เป็นอีกกฎหนึ่ง: เปิดเฉพาะ `POST /line/webhook` Path อื่นรวม `/demo/*` ได้ `404` ไม่มีรหัส ใช้จนกว่าจะย้าย Webhook มาเครื่องนี้ (W)
* `X-Demo-User` ตั้งเองได้ ใครผ่านด่านได้ก็ทำแทนพยาบาลหรือ Head Nurse คนไหนก็ได้ รหัสจึงต้องเก็บในทีม ห้ามเปิดเครื่องให้เข้าจากภายนอกถ้าด่านยังไม่ผ่าน `check-gate.sh`
* ลองด่านจากเครื่องไหนก็ได้ที่มี `bash` และ `curl`:

  ```bash
  bash deploy/aws/check-gate.sh https://<SITE_DOMAIN> <user> <password>
  ```

  สคริปต์แยก `401` ของด่านกับ `401` ของ Webhook จาก Header `WWW-Authenticate: Basic` ซึ่งมีเฉพาะของด่าน ไม่มีรหัสต้องได้ `401` ทุก Path ของหน้าเว็บและ API (รวมหน้า `/demo/*` และ `/api/demo/*`) ได้ `404` ที่ `/api/internal/*` และ Path ที่คล้าย Webhook ทุกแบบ (ตัวพิมพ์ใหญ่ `//` `%6C` `%2F` `?x=1` `/../`) ได้ `401` ของด่าน มีรหัสถูกแล้วต้องได้ `200` ที่ `/`, `/demo/control`, `/api/health` และ `/api/clock` รหัสผิดได้ `401` ต้องรันทุกครั้งที่แก้ `Caddyfile` และหลังตั้งเครื่องใหม่
* ทดสอบอัตโนมัติโดยไม่ต้องมีเครื่อง AWS: `python3 deploy/aws/test_gate.py` เริ่ม Caddy ด้วย `Caddyfile` จริงบน Docker (HTTP ธรรมดา ไม่มีใบรับรอง) กับ Upstream ปลอม สองตัว แล้วรัน `check-gate.sh` ใส่ผลเข้า CI (job "AWS test machine gate (Caddy)") Test ยังตรวจด้วยว่าคำขอที่ติดด่านไม่ไปถึง Upstream เลย: ที่ถึง Backend มีแค่ `POST /line/webhook`, `GET /health` และ `GET /clock` ส่วน Frontend มีแค่ `GET /` กับ `GET /demo/control`

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
| `LLM_PROVIDER`, `LLM_MODEL_ID`, `AWS_REGION` | String | คน 2 | ใส่หลังเลือกโมเดล (ข้อ 6.28 ขั้น 8) `AWS_REGION` ตรงนี้คือ Region ที่แอปเรียก Bedrock ไม่ใช่ Region ของ Parameter Store (ดูหมายเหตุข้างล่าง) เครื่องที่ไม่มี IAM Role ใช้ `LLM_PROVIDER=lambda` (หัวข้อส่วนของคน 2) ซึ่งโมเดลและ Region เป็นของ Lambda; สองค่านี้เป็นแค่ค่าสำรองที่บันทึกถ้า Lambda ไม่ตอบชื่อโมเดลกลับมา |
| `LLM_LAMBDA_URL` | String | คน 2 | เฉพาะ `LLM_PROVIDER=lambda`: Invoke URL ของ API Gateway (`https://` เท่านั้น) |
| `LLM_LAMBDA_API_KEY` | SecureString | คน 2 | เฉพาะ `LLM_PROVIDER=lambda`: API key ของ usage plan ห้ามอยู่ใน repo, Log หรือ Description |
| `LLM_INPUT_PRICE_PER_MTOK_USD`, `LLM_OUTPUT_PRICE_PER_MTOK_USD` | String | คน 2 | ราคาต่อล้าน token ของโมเดลที่เลือก (Nova 2 Lite ใน Singapore ตรวจแล้ว: 0.41 และ 3.39) |

* หกค่าแรกต้องมี ถ้าขาด `load-env.sh` หยุดและ Stack ไม่เริ่ม
* ค่าห้ามมี `'` หรือขึ้นบรรทัดใหม่ เพราะไฟล์ env เก็บค่าในเครื่องหมาย `'` ซึ่งทำให้ `$` ใน Hash ไม่ถูกอ่านเป็นตัวแปร
* ตัวแปรใหม่ต้องมีทั้ง Parameter และชื่อในส่วน `environment` ของ Service ใน `docker-compose.yml` เพราะไฟล์ env ใช้แทนค่าใน compose เท่านั้น ไม่ได้ส่งเข้า Container เอง ตัวแปร `LLM_*` กับ `AWS_REGION` มีใน `docker-compose.yml` แล้ว
* **สอง Region แยกกันด้วยสองชื่อ (รีวิว PR #107):** `NARA_PARAMETER_REGION` ใน `/etc/nara/aws.conf` (ไฟล์ของ systemd) คือ Region ที่ `load-env.sh` อ่าน Parameter Store ส่วน `AWS_REGION` ที่เป็น Parameter ลงในไฟล์ env คือ Region ที่แอปเรียก Bedrock สองค่านี้ต่างกันได้ **อย่าใส่ `AWS_REGION` ใน `aws.conf`** เพราะ systemd ส่งทุกอย่างในไฟล์นั้นเข้า `docker compose` และ Compose เลือกตัวแปรของ Process ก่อน `--env-file` ทำให้ Region ของ Parameter Store ทับ Region ของ Bedrock เงียบๆ (และผลจะขึ้นกับว่าใครรัน `up` ล่าสุด เพราะ `dc` ที่รันด้วย `sudo` ไม่ส่ง Environment ต่อ) จึงมีสามชั้น: `load-env.sh` ไม่อ่าน `AWS_REGION` และปฏิเสธพร้อมบอกให้เปลี่ยนชื่อถ้าเจอชื่อเก่า, `nara.service` เรียก `docker compose` ผ่าน `env -u AWS_REGION` และ `deploy/aws/test_region.py` (ใน CI) ตรวจด้วยค่าสองค่าที่ต่างกัน
* **`LLM_ENABLED` มาจาก Parameter** (ค่าเริ่มต้น `false` ของ `docker-compose.yml`) PR D เคยตรึงเป็น `false` ใน `docker-compose.aws.yml` จนกว่าคำอธิบายจะสร้างเมื่อผู้ใช้ขอเท่านั้น PR E1 ทำแล้วจึงลบการตรึงออก (ข้อ 6.27) ตั้ง Parameter `LLM_ENABLED=true` แล้ว restart จึงเปิดปุ่มขอคำอธิบาย ชุดทดลองเลือกโมเดล (B2) ไม่ต้องใช้ค่านี้
* เปลี่ยนค่าแล้วให้ `sudo systemctl restart nara` ค่าใหม่ถูกอ่านทุกครั้งที่เริ่ม

## ทางเลือก: ตั้งค่าบน EC2 ด้วยมือ

หากยังไม่มี IAM instance profile สำหรับ Parameter Store ใช้ไฟล์ `/etc/nara/nara.env` ที่ดูแลเองได้ เว็บ ฐานข้อมูล และ LINE ไม่ต้องใช้ IAM Role แต่ Bedrock จริงยังต้องมี AWS credentials ที่ได้รับอนุญาต (แนะนำ instance role) การใช้ไฟล์นี้ไม่ได้เพิ่มสิทธิ์ Bedrock

ทำหลังติดตั้ง Docker/Compose และ clone โค้ดเป็น `/opt/nara` แล้ว วิธีนี้แทนขั้น IAM, Parameter Store และการติดตั้งบริการในหัวข้อถัดไป ส่วน Elastic IP/DNS, ฐานข้อมูล และการตรวจช่วง ข ยังต้องทำตามเดิม

1. สร้างไฟล์เฉพาะครั้งแรก (อย่าคัดลอกตัวอย่างทับไฟล์ที่กรอกแล้ว):

   ```bash
   sudo install -d -m 700 /etc/nara
   if ! sudo test -e /etc/nara/nara.env; then
     sudo install -o root -g root -m 600 /opt/nara/deploy/aws/manual.env.example /etc/nara/nara.env
   fi
   sudo nano /etc/nara/nara.env
   ```

   กรอกทุกค่า `REPLACE_WITH_...` นอก repo ห้าม commit ไฟล์จริง หากมีไฟล์อยู่แล้ว ตรวจเจ้าของ `root:root` และสิทธิ์ `600` ด้วย `sudo ls -l /etc/nara/nara.env` ห้ามส่งภาพเนื้อหาไฟล์หรือใช้ `compose config` โดยไม่มี `--quiet` เพราะจะแสดงความลับ
2. `SITE_DOMAIN` ต้องเป็นโดเมนที่ทีมมีสิทธิ์ใช้ ไม่มี scheme หรือ path และ DNS ต้องชี้มายังเครื่องก่อนเปิด HTTPS ใส่ `ACME_EMAIL` ของทีม
3. สร้างรหัสฐานข้อมูลและ job secret คนละค่าด้วย `openssl rand -hex 24` ตัวตรวจรับ `POSTGRES_PASSWORD` เฉพาะตัวอักษรอังกฤษ ASCII และตัวเลข เพราะ Compose ใส่ลง `DATABASE_URL` โดยไม่ encode อักขระพิเศษ ส่วน Basic Auth hash ใช้ `sudo docker run --rm -it caddy:2.10-alpine caddy hash-password` แล้วกรอกรหัสผ่านตาม prompt เพื่อไม่ใส่รหัสผ่านใน command history เก็บ hash ในเครื่องหมาย single quote ตามตัวอย่าง
4. ติดตั้งบริการและ drop-in ก่อนเริ่มระบบ:

   ```bash
   sudo install -m 644 /opt/nara/deploy/aws/nara.service /etc/systemd/system/nara.service
   sudo install -d -m 755 /etc/systemd/system/nara.service.d
   sudo install -m 644 /opt/nara/deploy/aws/manual-env.conf /etc/systemd/system/nara.service.d/manual-env.conf
   sudo systemctl daemon-reload
   sudo systemctl cat nara --no-pager
   ```

   Drop-in นี้ล้าง `EnvironmentFile` ของ Parameter Store และ `ExecStartPre` เดิม จึงไม่ต้องสร้าง `aws.conf` และไม่เรียก `load-env.sh` ใช้ไฟล์ env เดิมเมื่อ reboot หรือ restart ตรวจท้ายผลว่ามี `manual-env.conf` การติดตั้งนี้ยังไม่เริ่มบริการ ทุกครั้งก่อนเริ่ม `validate-manual-env.py` จะปฏิเสธ placeholder `REPLACE_WITH_` และหกค่าจำเป็นที่ขาด ว่าง ซ้ำ หรือไม่ได้เขียนเป็นค่า single quote บรรทัดเดียว โดยไม่แสดงค่าความลับและไม่ execute เนื้อหาไฟล์
5. ตรวจ Compose โดยไม่พิมพ์ความลับ:

   ```bash
   sudo python3 /opt/nara/deploy/aws/validate-manual-env.py /etc/nara/nara.env
   sudo env -u AWS_REGION docker compose --env-file /etc/nara/nara.env -f /opt/nara/docker-compose.yml -f /opt/nara/deploy/aws/docker-compose.aws.yml config --quiet
   ```

   ทั้งสองคำสั่งต้องผ่าน ตัวตรวจไฟล์ปฏิเสธ placeholder และค่าจำเป็นที่ไม่ครบ ส่วน Compose ตรวจโครงสร้าง แต่ยังไม่ยืนยันว่า DNS และสิทธิ์บริการจริงใช้ได้ เมื่อกรอกครบ โดเมนและด่าน Basic Auth พร้อม จึงรัน `sudo systemctl enable --now nara` เตรียมฐานข้อมูลและตรวจช่วง ข ตามหัวข้อเดิม

คง `LINE_MODE=simulation` และ `LLM_ENABLED=false` จนพร้อมทดสอบบริการจริง เปลี่ยนไฟล์แล้ว `sudo systemctl restart nara` ห้ามรัน `load-env.sh` ในโหมดนี้เพราะจะเขียนไฟล์ทับ การเปลี่ยน `POSTGRES_PASSWORD` หลังฐานข้อมูลถูกสร้างแล้วไม่ได้เปลี่ยนรหัสของผู้ใช้ในฐานข้อมูลให้อัตโนมัติ ค่า `SITE_DOMAIN` ถูกใช้ตอน build Frontend จึงต้อง build ใหม่เมื่อเปลี่ยน (restart บริการใช้ `--build` อยู่แล้ว) คงข้อกำหนด Basic Auth, การไม่เปิดพอร์ตภายใน และเกณฑ์ตรวจช่วง ข เดิมทั้งหมด

เมื่อต้องการกลับไปใช้ Parameter Store ให้เตรียม IAM/Parameters และตั้ง `NARA_PARAMETER_REGION=ap-southeast-1` (หรือ Region ของ Parameter Store ที่ใช้จริง) ใน `/etc/nara/aws.conf` ให้ครบก่อน **สำรอง `/etc/nara/nara.env` ก่อน restart** เพราะ loader จะเขียนไฟล์ทับจาก Parameter Store เก็บสำเนาไว้นอก repo เจ้าของ `root` สิทธิ์ `600` เช่น `sudo cp -p /etc/nara/nara.env /etc/nara/nara.env.manual-backup` (อย่าเขียนทับสำเนาเก่าที่ยังต้องใช้) แล้วลบเฉพาะ `/etc/systemd/system/nara.service.d/manual-env.conf` ตามด้วย daemon-reload และ restart บริการ

การเปิดระบบครั้งแรกด้วยทางเลือกนี้และการตรวจช่วง ข บนเครื่องจริงยังรอทำเมื่อโดเมนพร้อม ไม่ถือว่าการตรวจ Compose หรือ `systemctl cat` เป็นผลทดสอบเปิดระบบจริง

## ตั้งเครื่องครั้งแรก (คน 1)

1. **EC2:** Amazon Linux 2023 ซึ่งมี AWS CLI v2 และ `python3` มาให้ ซึ่ง `load-env.sh` ใช้ RAM อย่างน้อย 4 GB เพราะ `pip install` ของ Backend และ `npm ci` กับ `next build` ตอนสร้าง image ของ Frontend ใช้มากกว่าตอนรันปกติ (บนเครื่องพัฒนาทุก Service รวมกันใช้ราว 1 GB ตอนว่าง) Disk 30 GB
2. **Security Group:** SSH 22 เปิดเฉพาะ IP ของทีม ส่วน 80 และ 443 ในช่วงตรวจช่วง ข (ข้อ 6.30 ข้อเสนอที่ยังไม่ตกลง) จำกัดให้ IP ของทีมได้ แต่การออกใบรับรองครั้งแรกต้องให้ Let's Encrypt เข้า Port 80 หรือ 443 ได้ (ตรวจจาก IP ที่เปลี่ยนไปมา) จึงเปิดสองพอร์ตนี้ให้ทุกที่ชั่วคราวตอนออกใบรับรอง โดยยังมีด่าน Basic Auth ครอบทุก Path ยกเว้น Webhook หรือออกใบรับรองก่อนแล้วค่อยจำกัด IP หลังผ่านช่วง ข ทีมตกลงแล้วจึงเปิด 80 และ 443 ให้ทุกที่ (LINE ต้องเข้า Webhook ได้)
3. **Elastic IP และ DNS:** ผูก Elastic IP กับเครื่อง แล้วตั้ง Record `A` ของ `SITE_DOMAIN` ให้ชี้ไปที่ IP นั้นก่อนเริ่ม Stack ครั้งแรก เมื่อใช้ Elastic IP การหยุดแล้วเริ่มเครื่องใหม่ (R6-Q5 เปิดเฉพาะช่วงทดสอบและ Demo) ไม่เปลี่ยน IP จึงไม่ต้องแก้ URL ของ Webhook ใน LINE Developers
4. **IAM Role ของเครื่อง:** สร้าง Role ให้ EC2 แนบ Policy จาก `deploy/aws/iam-parameter-read-policy.json` (แทน `REGION` และ `ACCOUNT_ID`) Policy นี้อ่านได้แค่ Path `/nara/test` ใช้ Key `aws/ssm` ที่ AWS สร้างให้ ถ้าเปลี่ยนเป็น Key ของทีมเองต้องเพิ่ม `kms:Decrypt` ของ Key นั้น สิทธิ์ Bedrock เพิ่มทีหลังโดยคน 2 (หัวข้อข้างล่าง) ไม่ใส่ในไฟล์นี้
5. **ใส่ Parameter:** ตามตารางข้างบน ใน Region เดียวกับเครื่อง
6. **ติดตั้ง Docker และ Compose:**

   ```bash
   sudo dnf install -y docker git
   sudo systemctl enable --now docker
   sudo mkdir -p /usr/local/lib/docker/cli-plugins
   sudo curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose \
     https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)
   sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
   docker compose version   # ต้องเป็น 2.24.4 ขึ้นไป เพราะไฟล์ซ้อนใช้ !reset และ !override
   ```

   **Buildx ต้องมีด้วย:** บนเครื่องจริงพบ `compose build requires buildx 0.17.0 or later` ตรวจด้วย `sudo docker buildx version` ก่อนเริ่มบริการ Release [v0.38.1 ของ Docker](https://github.com/docker/buildx/releases/tag/v0.38.1) มีอยู่จริง; การตรวจ checksum และการรัน binary แยกจากหลักฐานเครื่องจริง ดู `docs/round6/step6-live-checks.md` ตัวอย่างต่อไปสำหรับ x86_64 ดาวน์โหลดในโฟลเดอร์ส่วนตัวของ root เทียบ published SHA-256 ก่อนติดตั้ง และหยุดทันทีหากขั้นใดล้ม:

   ```bash
   sudo bash <<'BASH'
   set -euo pipefail
   [ "$(uname -m)" = x86_64 ] || { echo 'ERROR: this recipe requires x86_64; no plugin installed' >&2; exit 1; }
   umask 077
   buildx_dir=$(mktemp -d /root/nara-buildx.XXXXXX)
   trap 'rm -rf -- "$buildx_dir"' EXIT
   cd "$buildx_dir"
   asset=buildx-v0.38.1.linux-amd64
   release=https://github.com/docker/buildx/releases/download/v0.38.1
   curl -fL "$release/$asset" -o "$asset"
   curl -fL "$release/checksums.txt" -o checksums.txt
   # Pin the digest checked against Docker's published checksums and release metadata.
   expected=e25d5cd675092bb5d1d03632fdc46cdf3fede7b514dc5f023a105e00d3ce5ad4
   awk -v asset="$asset" -v expected="$expected" \
     '{ name=$2; sub(/^\*/, "", name); sub(/^\.\//, "", name) }
      name == asset && $1 == expected { print expected "  " asset; found=1 }
      END { if (!found) { print "ERROR: no matching pinned checksum for " asset > "/dev/stderr"; exit 1 } }' \
     checksums.txt > selected-checksum.txt
   sha256sum --check selected-checksum.txt
   install -D -m 755 "$asset" /usr/local/lib/docker/cli-plugins/docker-buildx
   docker buildx version
   BASH
   ```

   Checksum ตรวจความสมบูรณ์ของ binary และ pin digest ไว้ในคู่มือ ไม่ได้อ้างว่าได้ตรวจลายเซ็น release แบบอิสระ สำหรับ ARM ต้องเลือก binary และ checksum ของ linux-arm64 ให้ตรงกัน ห้ามใช้ digest ของ amd64 ถ้าติดตั้งแบบ manual ต้องดูแลอัปเดตเอง

7. **โค้ดและบริการ:**

   ```bash
   sudo git clone --branch staging https://github.com/Bobbie-CPE38/nara.git /opt/nara
   sudo mkdir -p /etc/nara
   echo 'NARA_PARAMETER_REGION=<region ของ Parameter Store>' | sudo tee /etc/nara/aws.conf
   sudo cp /opt/nara/deploy/aws/nara.service /etc/systemd/system/nara.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now nara
   ```

   ครั้งแรกใช้เวลาหลายนาทีเพราะต้องติดตั้ง Package ของ Python และ npm ดูความคืบหน้าด้วย `sudo journalctl -u nara -f` และคำสั่ง `ps` ข้างล่าง

8. **ฐานข้อมูลและข้อมูล Demo:** เมื่อทุก Service healthy แล้ว รัน `seed` ตามข้างล่างหนึ่งครั้ง ก่อน `seed` ฐานข้อมูลยังไม่มีตาราง Job จะได้ `500` จาก `/internal/merge-windows/close-due` หนึ่งครั้ง (`relation "roster_assignment" does not exist`) เป็นเรื่องปกติและหายหลัง `seed` (ตรวจแล้วบน Stack จริงในเครื่องผู้พัฒนา)
9. **ตรวจช่วง ข (ข้อ 6.30):** ทั้งสามคนทำ ต้องผ่านทุกข้อก่อนเปิดให้ภายนอกเข้า ดูหัวข้อถัดไป

คำสั่ง compose บนเครื่องนี้ต้องมีไฟล์ซ้อนและไฟล์ env ทุกครั้ง:

```bash
cd /opt/nara
alias dc='sudo docker compose --env-file /etc/nara/nara.env -f docker-compose.yml -f deploy/aws/docker-compose.aws.yml'
dc ps                                    # สถานะ
dc logs -f backend                       # Log
dc exec -T backend python -m app.seed    # ลบ Schema, Migrate ถึง head แล้วโหลด Demo (เหมือน make reset)
```

## ตรวจช่วง ข ก่อนเปิดให้ภายนอกเข้า (ขั้นที่ 6)

ช่วง ก (ตรวจในเครื่องผู้พัฒนา) เป็นของ PR F3 ช่วงนี้ตรวจบนเครื่องจริง ผลบันทึกในตาราง "อะไรทดสอบด้วย fake และอะไรผ่านบริการจริง" ของ `workflow.md` และใน Description ของ PR แรกที่ใช้เครื่อง (B2 หรือ W) ผลตรวจของคน 3 วันที่ 2026-10-21 อยู่ใน `docs/round6/step6-live-checks.md`

1. Container ของ Frontend รัน production mode จริง: `dc ps` แล้ว `sudo docker inspect nara-staffing-frontend --format '{{.Config.Cmd}}'` ต้องเป็น `next start` ไม่มี `npm run dev` และ `sudo docker inspect nara-staffing-frontend --format '{{len .Mounts}}'` ต้องเป็น `0` (F3 ตรวจเรื่องนี้กับ Compose ในเครื่องแล้วด้วย `deploy/aws/test_frontend.py` ข้อนี้ตรวจซ้ำบนเครื่องจริง)
2. `bash deploy/aws/check-gate.sh https://<SITE_DOMAIN> <user> <password>` ผ่านทุกข้อจากเครื่องของตัวเอง ไม่ใช่จากตัวเครื่อง
3. เปิด `/`, `/gap`, หน้าเคส และ `/demo/control` ผ่าน Caddy ด้วยรหัส เรียก API ผ่าน `/api` ได้ ไม่มี Error ใน Console และ Bundle ที่เครื่องส่งให้ไม่มี `localhost:8000` และดูว่าเบราว์เซอร์ไม่ถามรหัสซ้ำ: Backend ตอบ `401` ด้วย Header `WWW-Authenticate: X-Demo-User` (`app/api/dependencies.py`) ซึ่งเป็นคนละ Scheme กับ Basic ของด่าน เบราว์เซอร์บางตัวอาจทิ้งรหัสที่จำไว้เมื่อ Origin เดียวกันตอบ `401` ด้วย Scheme อื่น ถ้าเจอ ให้ตัด Header นั้นที่ Caddy (`header_down -WWW-Authenticate` ใน `handle_path /api/*`) ใน PR แยก ยังไม่ได้ทำเพราะยังไม่ทราบว่าเกิดจริงไหม
4. ถ้าผ่านทั้งหมด จึงเปิด Security Group ให้ภายนอกเข้า แล้วคน 3 เปลี่ยน Webhook (W)

## Deploy โค้ดใหม่

```bash
cd /opt/nara
sudo git pull
sudo systemctl restart nara
```

Backend เป็น Dev server ที่อ่านโค้ดจาก Volume เหมือนเครื่องพัฒนา (R3-Q20 ใช้ `docker compose` ชุดเดิม) ส่วน Frontend เป็น image ที่ build ไว้แล้ว `nara.service` สั่ง `up -d --build` ดังนั้น Restart จะสร้าง image ของ Frontend ใหม่เมื่อโค้ดของ Frontend เปลี่ยน (ใช้เวลาตามความแรงของเครื่อง ยังไม่ได้วัดบนเครื่อง AWS ถ้าไม่เปลี่ยนใช้ Cache) และ `NEXT_PUBLIC_API_BASE_URL` ถูกเขียนลง Bundle ตอน build จึงเปลี่ยนโดเมนแล้วต้อง build ใหม่ Restart ทำให้อ่าน Parameter Store ใหม่ด้วย ถ้า PR ที่เข้ามามี Migration ให้รัน `seed` ใหม่ ซึ่งล้างข้อมูลบนเครื่อง ใครเป็นคน Deploy และ Deploy เมื่อไรให้ตกลงในทีม

## เปิดและปิดเครื่อง (R6-Q5)

เปิดเฉพาะช่วงทดสอบและ Demo เพื่อคุมค่าใช้จ่าย (บัญชีเป็นของทีมที่ผู้จัดการแข่งขันให้ วงเงิน 350 USD เป็นเครดิตรวม)

* หยุดเครื่อง (Stop) ไม่ใช่ลบ (Terminate): Volume และ Elastic IP ยังอยู่ ข้อมูลฐานข้อมูลและใบรับรองไม่หาย เมื่อเริ่มใหม่ `nara.service` ยกชุดเดิมขึ้นเอง
* ตรวจราคาของ Elastic IP (IPv4 สาธารณะ) จากหน้า Pricing ของ AWS ก่อนเปิดครั้งแรก เพราะ IP ที่จองไว้อาจมีค่าใช้จ่ายแม้เครื่องหยุด แล้วตัดสินว่าจะเก็บไว้หรือคืนทุกครั้ง (คืนแล้ว IP เปลี่ยน ต้องแก้ Record `A` และ URL ของ Webhook)
* ตั้ง AWS Budget Alert ก่อนเปิดครั้งแรก (ข้อ 6.28) ผู้จัดการแข่งขันตั้งให้แล้วถ้าครอบคลุมงบเฉพาะ Bedrock และทีมได้รับแจ้งเตือน

## ส่วนของคน 2 (Bedrock ผ่าน Lambda, round 6 PR B3)

บัญชีทีมสร้าง instance profile ของ EC2 ไม่ได้ (`iam:CreateInstanceProfile` ถูกปฏิเสธ) Backend จึงเรียก Bedrock ผ่าน API Gateway และ Lambda (`deploy/aws/lambda/bedrock_proxy.py`) แทน IAM Role ของเครื่อง ไม่ต้องตั้ง Hop limit ของ Metadata ทุกขั้นทำใน Console ของ Region `ap-southeast-1` โดยบัญชีทีม

**ลำดับการคุมค่าใช้จ่าย:** ตัวคุมหลักคือของแอป (B1): จองโควตารายวัน DEMO/TRIAL แบบ atomic ก่อนเรียกทุกครั้ง และเพดาน input/output ต่อคำขอ Lambda บังคับโมเดล ขนาดคำขอ และความยาวคำตอบของตัวเองซ้ำ โควตาและ throttling ของ usage plan เป็นตัวจำกัดเพิ่ม **แบบ best effort ไม่ใช่เพดานที่รับประกัน** ([AWS: Usage plans and API keys](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html)) Budget Alert เฉพาะ Bedrock (`nara-bedrock-20usd`) แจ้งเตือนทางอีเมลอย่างเดียว ไม่หยุดการเรียก **ห้ามเปิด Lambda Function URL** เพราะข้าม API key และโควตา (บัญชีนี้ตั้ง reserved concurrency ไม่ได้)

1. **Role ของ Lambda:** IAM → Roles → Create role → AWS service → Lambda → แนบ `AWSLambdaBasicExecutionRole` (เขียน CloudWatch Logs) → ชื่อ `nara-bedrock-lambda` แล้วเพิ่ม inline policy จาก `deploy/aws/lambda/iam-bedrock-invoke-policy.json` (แทน `REGION` และ `ACCOUNT_ID`) ชื่อ `nara-bedrock-nova-lite` อนุญาตเฉพาะ `bedrock:InvokeModel` ของ Nova 2 Lite ผ่าน global inference profile ซึ่งข้อมูลอาจถูกประมวลผลนอก Singapore
2. **Function:** Lambda → Create function → Author from scratch, ชื่อ `nara-bedrock`, Python 3.13, Execution role = `nara-bedrock-lambda` (Additional settings → Custom execution role); ไม่เปิด Function URL, Durable execution หรือ EC2 capacity provider
3. **โค้ด:** วางเนื้อหาของ `deploy/aws/lambda/bedrock_proxy.py` เป็นไฟล์ `bedrock_proxy.py` แล้วตั้ง Handler เป็น `bedrock_proxy.handler` → Deploy
4. **ค่าตั้ง:** Configuration → General: Timeout **12 วินาที** (สั้นกว่า timeout ของแอป 15 วินาที), Memory **256 MB**; Environment variables: `MODEL_ID=global.amazon.nova-2-lite-v1:0`, `MAX_INPUT_BYTES=32000`, `MAX_OUTPUT_TOKENS=1024`, `BEDROCK_TIMEOUT_SECONDS=10`
5. **Log:** หลังเรียกครั้งแรก CloudWatch → Log groups → `/aws/lambda/nara-bedrock` → ตั้ง Retention **2 สัปดาห์** Log มีแค่ request ID, ผลลัพธ์, จำนวน token และเวลา
6. **API:** API Gateway → REST API → Build → New API ชื่อ `nara-bedrock-api` → Create method `POST` ที่ `/` → Lambda function `nara-bedrock` เปิด Lambda proxy integration → Method request → **API key required** → Deploy API stage ชื่อ `prod` แล้วจด Invoke URL
7. **Usage plan:** Usage plans → Create: ชื่อ `nara-bedrock-plan`, Throttling rate 2 burst 5, Quota **200 ต่อวัน** (เพดานแอป 100 ต่อวันบวกชุดทดลอง 60) → Associated stages: `nara-bedrock-api` / `prod` → Associated API keys: Create new key `nara-bedrock-key` แล้ว Show เพื่อคัดลอกค่า ห้ามวางใน chat, repo หรือ Description
8. **ตั้งค่าบนเครื่อง:** ใส่ใน `/etc/nara/nara.env` (manual env) หรือ Parameter Store: `LLM_PROVIDER='lambda'`, `LLM_LAMBDA_URL='<Invoke URL ของ stage prod>'`, `LLM_LAMBDA_API_KEY='<API key>'`, ราคา `LLM_INPUT_PRICE_PER_MTOK_USD='0.41'` และ `LLM_OUTPUT_PRICE_PER_MTOK_USD='3.39'` **ยังคง `LLM_ENABLED='false'`** แล้ว `sudo systemctl restart nara`
9. **ลองหนึ่งครั้งจากเครื่อง (ยังไม่เปิดปุ่มในแอป):** รันชุดทดลองผ่านตัวห่อของแอปด้วยเคสเดียวหรือชุดเต็ม (`python -m app.trial.run` ตาม `docs/workflow.md` 6.28) ภายใน Container Backend ไฟล์ผลต้องอยู่นอก `/app` เช่น `/tmp` `--model` ต้องเป็นรหัสโมเดลเดียวกับ `MODEL_ID` ของ Lambda ไม่งั้นเครื่องมือหยุด
10. **เปิดใช้:** เมื่อการลองสำเร็จและบันทึกผลแล้ว ตั้ง `LLM_ENABLED='true'` แล้ว restart ปุ่ม "สรุปด้วย AI" ของคำอธิบายอันดับ (E1, E2) และสรุปเคส (S) เปิดพร้อมกัน ตรวจหนึ่งเคสว่าแถวใน `llm_call_log` มี `provider=lambda` และค่าใช้จ่าย

**ถอยกลับ:** ตั้ง `LLM_ENABLED='false'` แล้ว restart ปุ่มปิดทันทีโดยไม่ต้องแตะ AWS ถ้าคีย์รั่ว: API Gateway → API keys → ลบหรือปิด `nara-bedrock-key` แล้วสร้างใหม่ใส่ในเครื่อง

## ส่วนของคน 3 (LINE)

ขั้นตอน cutover, strict preflight, หลักฐาน live และ rollback อยู่ใน `docs/round6/pr-W-handoff.md` W ยังไม่ผ่านจากการตรวจ Gate อย่างเดียว

* URL ของ Webhook: `https://<SITE_DOMAIN>/api/line/webhook`
* ใส่ `LINE_MODE=real`, `LINE_CHANNEL_SECRET` และ `LINE_CHANNEL_ACCESS_TOKEN` ในแหล่งค่าตั้งที่เครื่องใช้: Parameter Store หรือ manual env ตาม PR #118 แล้ว `sudo systemctl restart nara` ตรวจคิวค้างก่อนเปิด real เพราะอาจเริ่มส่งข้อความทันที
* เปิด "Webhook redelivery" ใน LINE Developers Console (ค่าเริ่มต้นปิด `workflow.md` ข้อ 6.16)
* ย้าย Webhook จาก Tunnel มาเครื่องนี้ (W) หลังเครื่องผ่านช่วง ข และ Offer, ปุ่ม, ผูกบัญชีผ่านเครื่องจริงอย่างน้อยหนึ่งรอบ เก็บ `dev/line-webhook-proxy` ไว้ถอยกลับถ้าเครื่องล่ม
* ลองรับ Webhook จริงหนึ่งรอบ
