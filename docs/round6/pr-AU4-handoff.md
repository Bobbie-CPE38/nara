# AU4 — เปลี่ยนด่าน AWS เป็น session

สถานะ: **code and automated checks only; not production acceptance** — deploy แล้ว แต่ live acceptance ยังไม่ครบ ไม่ใช้ผลขั้น 6/W ก่อนเปลี่ยนด่านมาปิด AU4 ไม่มี migration ใน PR นี้ แต่เครื่องต้องมี AU1/AU2/AU3/AU3b/AU5 ครบ

## พฤติกรรมหลังเปลี่ยน

- หน้าเว็บทั่วไป/login/register ไม่ถาม Basic Auth; business API ต้องมี session ที่ Backend ตรวจทุกครั้ง
- Basic Auth ครอบ `/demo`, `/demo/*`, `/api/demo`, `/api/demo/*` เป็นด่านเพิ่มจาก session ของ simulator และ manager session ของ Demo events; reset/นาฬิกายังไม่ใช้ตัวตนตาม contract อย่าเปิด Backend โดยตรง
- `/api/internal` และลูกทุก path, API docs/redoc/openapi เป็น 404 จาก Caddy ทั้งมีและไม่มี login; webhook เฉพาะ POST `/api/line/webhook` URI ดิบตรงตัว ไม่ใช้ Basic/session แต่ตรวจลายเซ็น LINE; รูปดัดแปลงถูกปฏิเสธ ไม่ normalize ให้เป็นข้อยกเว้น
- overlay ตรึง APP_ENV=aws, AUTH_MODE=session, Secure cookie, Uvicorn หนึ่ง serving worker ไม่มี reload และไม่มี host port ของ Backend/DB/Redis
- Caddy แทน X-Forwarded-For/Proto ที่มาจากผู้เรียกด้วย peer/scheme จริง และ Uvicorn เชื่อเฉพาะ Caddy `172.30.64.2` ใน compose network `172.30.64.0/24` (dynamic pool `172.30.64.128/25` แยกจาก IP Caddy ป้องกันชนตอนเริ่มเครื่อง) ห้ามเปิด trusted proxies เป็น `*` หรือตีพิมพ์พอร์ต Backend
- limiter ยัง in-memory: หนึ่ง Backend replica/worker เท่านั้น, restart ล้าง counter, คนหลายคนหลัง NAT ยังแชร์เพดาน IP (login 10/min, register 5/min) อย่าอ้างว่าใช้ป้องกัน DoS หรือเป็น quota ต่อพนักงานอย่างเดียว

## ขอบเขตสิทธิ์ของ Demo controls ที่ยังเปิดอยู่

`/api/demo/reset` และ `/api/demo/clock/*` ยังไม่มี session/role check ที่ Backend. บน AWS ด่านอนุญาตคือ Demo Basic Auth ของ Caddy (พร้อม Origin guard ใน session mode ซึ่งไม่ใช่หลักฐานตัวตน). การมี session ของ staff ไม่ใช่เงื่อนไขของ routes เหล่านี้ ผู้รู้รหัส Basic จึงสามารถ reset/เปลี่ยนนาฬิกาได้แม้ไม่ได้ login เว็บ.

ตาม contract 6.33.5 ปัจจุบัน **ยังไม่มี PR/ขั้นที่กำหนดไว้เพื่อเพิ่ม supervisor session ให้ reset/clock**; AU4 ไม่ได้ปิดช่องนี้ และ #138 เป็นเพียงข้อมูลจำลอง ไม่ใช่งานปิดสิทธิ์ดังกล่าว. หากต้องการเปลี่ยนต้องทำ Backend role guard และปรับ contract/tests ในงานถัดไปโดยระบุขอบเขตใหม่อย่างชัดเจน.

ข้อกำหนดการใช้งานเครื่องนี้: แจก Demo Basic credential เฉพาะผู้ได้รับอนุญาตให้ reset เครื่องและเปลี่ยนนาฬิกาเท่านั้น ไม่แจกให้ผู้ทดลอง/พยาบาลทั่วไป. **ผู้ดูแลยืนยันเมื่อ 2026-10-23 (Bangkok) ว่ารหัสนี้ให้เฉพาะผู้ดูแลที่ได้รับอนุญาตให้ Reset/เปลี่ยนนาฬิกา**. เป็นคำยืนยันจากผู้ดูแล ไม่ใช่การตรวจรายชื่อผู้ถือรหัสอย่างอิสระ และไม่ทำให้ routes มี session/role check เพิ่ม. หากการแจกเปลี่ยนในภายหลังต้องทบทวนสิทธิ์และเปลี่ยนรหัสเมื่อจำเป็น.

## Automated checks ของ PR (ไม่ใช่ AWS acceptance)

- Caddy 2.10 จริงกับ fake upstream: 10 tests รวม private/Demo URI bypass, signed-webhook double, forwarded header replacement, auth cookie/logout replay และ preflight ที่ต้อง fail เมื่อ mode=demo/มี Basic challenge บน webhook/503 ใน strict mode
- Render Compose: 3 tests โหมด/cookie ถูกตรึงแม้ process env เป็น demo/insecure, หนึ่ง worker/exact proxy trust และ host ports เฉพาะ Caddy
- Backend integration กับ PostgreSQL แยก: 172 tests รวม route permissions/self-leave/review regressions และ Uvicorn ProxyHeadersMiddleware + login limiter (2 tests ใหม่: IP ผ่าน Caddy แยก bucket; peer อื่นปลอม XFF หนีเพดานไม่ได้)
- Region 5 tests และ manual-env 8 tests ผ่าน ไม่เปลี่ยนวิธีอ่าน env
- ทดลอง Docker IPAM จริงแบบแยก: dynamic container ได้ `172.30.64.129` และ static `172.30.64.2` ยังจองได้ภายหลัง ไม่ใช่หลักฐาน subnet overlap ของ EC2

## ผลตรวจ subnet ก่อนและหลัง deploy (operator-reported, 2026-10-23 Bangkok)

ก่อนเปลี่ยน network ผู้ deploy ส่ง Docker network inspect: `bridge 172.17.0.0/16`, `nara_staffing_net 172.20.0.0/16`, และ `host`/`none` ไม่มี subnet. Host `ip -4 route` แสดง default ผ่าน `172.31.16.1`, connected `172.31.16.0/20`, Docker `172.17.0.0/16`/`172.20.0.0/16`, และเส้นทาง host ของ `172.31.0.2`/`172.31.16.1`. ไม่มี explicit route เหล่านี้ทับ `172.30.64.0/24`; default route ไม่ใช่หลักฐานว่า subnet ไม่ทับเครือข่ายอื่น.

หลัง deploy ผู้ดูแลรันจาก CloudShell: หา VPC ของ EC2 ด้วย `describe-instances` แล้ว `describe-route-tables` กรองทุก table ของ VPC นั้น. Output ที่ส่งมาแสดง 1 table: route `172.31.0.0/16 -> local` และ `0.0.0.0/0 -> Internet Gateway`, ทั้งคู่ active. ไม่มี route target แบบ peering, Transit Gateway หรือ VPN ในผลนี้. ผู้ดูแลรายงานว่าไม่ได้ตั้งการเชื่อมเครือข่ายเพิ่มเติมเอง.

เมื่อรวม Docker networks, host explicit routes และ VPC routes ที่รายงาน **ไม่พบ subnet ทับกับ `172.30.64.0/24` ใน configuration ที่ตรวจ**. Default route ไป Internet Gateway ไม่ใช่ subnet collision. ผลเป็น operator-reported output ไม่ใช่ independent AWS rerun หรือหลักฐานว่าไม่มีเครือข่ายอื่นนอก configuration นี้. ตรวจใหม่หากเพิ่ม VPN/peering/TGW หรือเปลี่ยน routes; ถ้าพบทับให้เปลี่ยน subnet/Caddy IP/trusted IP/tests พร้อมกัน. Operator output ภายหลังแสดง service start สำเร็จ แต่การตรวจ route ข้างต้นเป็นหลักฐานแยกจาก startup และไม่ปิด live acceptance ข้ออื่น.

## ก่อน deploy บน EC2

1. เก็บ `git rev-parse HEAD`, frontend image ID, `alembic current`, เฉพาะค่า APP_ENV/AUTH_MODE/LINE_MODE และ process command ไม่ dump env/token/hash เอกสารนี้เก็บเฉพาะผลที่ผู้ deploy ส่งให้ ไม่ใช่ independent rerun
2. ต้องมี staff account ของ head nurse/supervisor ที่ ACTIVE และไม่ disabled ก่อนเปิด session ใช้ CLI รายบัญชี ไม่ใช้ `demo-accounts` (CLI นั้นใช้ได้เฉพาะ local demo):

   ```bash
   sudo docker exec -it nara-staffing-backend python -m app.auth_accounts create --staff-id 900
   ```

   ใช้เฉพาะเมื่อยังไม่มีบัญชี ตั้งรหัสผ่านใน prompt ไม่ส่งเป็น argument/แชท; บัญชีใหม่ต้องเปลี่ยนรหัสในหน้า `/change-password` ก่อนทำงาน ถ้ามีบัญชีเดิมอย่าสร้างทับ/ตั้งรหัสใหม่โดยไม่จำเป็น
3. ตรวจ subnet ของทุก Docker network และเส้นทาง VPC/VPN/host ว่า `172.30.64.0/24` ไม่ชน หากชนให้หยุด deploy และแก้ subnet, Caddy IP, trusted IP และเทสต์ให้ตรงกันก่อน ไม่เลือก subnet เองบนเครื่อง
4. สำรองฐานข้อมูลและ revision บนเครื่องเท่านั้น ไฟล์ backup อาจมีข้อมูลส่วนบุคคลและความลับ ไม่แนบ PR:

   ```bash
   sudo git -C /opt/nara rev-parse HEAD | sudo tee /etc/nara/au4-before.commit
   sudo sh -c 'umask 077; docker exec nara-staffing-postgres pg_dump -U staffing -d staffing > /etc/nara/au4-before.sql'
   sudo test -s /etc/nara/au4-before.sql
   ```

5. ตกลงช่วงหยุดสั้นกับทีม/หยุดสร้าง Demo events รอ delivery queue เคลียร์ตามคู่มือ W อย่า reset/seed ล้างบัญชีหรือผูก LINE เพื่อเตรียม AU4

## Deploy รุ่นที่รีวิวแล้ว

**หยุดบริการก่อนเปลี่ยน checkout** เพราะ Backend เดิม mount source และใช้ reload การ checkout ขณะรันจะเปลี่ยนโค้ดกลางงาน ขั้นตอนนี้ต้อง down/up network เดิมเพื่อใช้ IPAM ใหม่ ห้าม `down -v` และอย่าลบ postgres/caddy volumes

```bash
cd /opt/nara
sudo systemctl stop nara
sudo git fetch origin
sudo git checkout --detach <reviewed-AU4-commit-SHA>
alias dc='sudo env -u AWS_REGION docker compose --env-file /etc/nara/nara.env -f /opt/nara/docker-compose.yml -f /opt/nara/deploy/aws/docker-compose.aws.yml'
dc down
dc up -d postgres redis
dc run --rm -T --interactive=false --no-deps backend sh -c 'pip install --no-cache-dir -e ".[dev]" && alembic upgrade head' < /dev/null
sudo systemctl start nara
dc ps
```

ปิด stdin ของ migration container โดยตั้ง `--interactive=false` และ redirect จาก `/dev/null` เสมอ โดยเฉพาะเมื่อวางคำสั่งใน heredoc ไม่เช่นนั้น Compose run (interactive เป็นค่าเริ่มต้น) อาจรับคำสั่งถัดไปเป็น stdin ของ container ทำให้ shell ไม่รัน `systemctl start nara` ที่ตามมา

`nara.service` ยังอ่าน env ผ่านวิธีเดิมของเครื่อง (manual-env.conf หรือ Parameter Store) AU4 ไม่สลับวิธีอ่าน env, ไม่เปลี่ยน LINE_MODE/LLM_ENABLED และไม่เพิ่ม AWS keys/สิทธิ์ Bedrock หากมี migration ใหม่จาก PR อื่น ต้องรีวิววิธี upgrade/rollback ของ migration นั้นก่อน

ตรวจเฉพาะค่าที่ปลอดภัย:

```bash
sudo docker exec nara-staffing-backend python -c 'from app.core.config import settings; print(settings.app_env, settings.auth_mode, settings.auth_cookie_secure, settings.line_mode)'
sudo docker top nara-staffing-backend -eo pid,ppid,args
sudo docker inspect nara-staffing-frontend --format '{{.Image}}'
sudo git -C /opt/nara rev-parse HEAD
```

ต้องได้ aws/session/True และ LINE mode เดิม, หนึ่ง serving worker ไม่มี reload, ไม่มี host ports นอกจาก Caddy ตรวจบัญชีแรกด้วย browser เปลี่ยนรหัสชั่วคราวให้เสร็จ

## Automated preflight จากเครื่องภายนอก

รันจาก checkout ของ AU4 รุ่นเดียวกับเครื่อง ห้ามแปะ password/cookie ในแชทหรือผล PR:

```bash
bash deploy/aws/check-gate.sh https://<SITE_DOMAIN> nara --require-real-line
bash deploy/aws/check-gate.sh https://<SITE_DOMAIN> nara --require-real-line --staff-id 900
```

ทั้งสองคำสั่งถามรหัส Demo Basic แบบไม่ echo และไม่ใส่ argv; รูปแบบเก่าที่รับ password เป็น argument ยังใช้ได้กับ test เท่านั้น ไม่แนะนำบนเครื่องจริง คำสั่งที่สองถามรหัสเว็บต่างหากใน prompt และ logout session ที่สร้างเมื่อจบ ใช้บัญชีที่เปลี่ยนรหัสครั้งแรกแล้ว รันซ้ำด้วยบัญชี staff เพื่อเช็ก role denial ด้วย คำสั่งไม่ส่ง reset/Offer/check-in/LLM; POST `/events` เป็น negative probe ซึ่งต้อง 403 โดยไม่เกิด Event ถ้าพบไม่ใช่ session ให้หยุด ไม่ใช้งานเว็บไซต์ต่อ

สคริปต์ตรวจ anonymous/X-Demo-User-only 401, Basic อย่างเดียวไม่ใช่ session, Demo Basic, simulator ต้องสองด่าน, internal/docs 404, webhook unsigned 401 **ไม่มี Basic challenge**, รูป URI ที่ดัดแปลง 404 และ auth/config=session การใส่ `--require-real-line` จะปฏิเสธ 503 เสมอ ผลผ่านเป็นเพียง preflight ไม่ใช่ signed LINE หรือ full production acceptance

## Live checklist — ต้องมีหลักฐานก่อนปิด AU4

เก็บวันที่ ผู้ตรวจ deployed SHA/frontend image ID และผลโดยไม่ใส่ secret/UID/code/token (ไม่เปิด LLM เพื่อทดสอบ auth)

| ตรวจบน AWS หลัง AU4 | ผล/หลักฐาน |
|---|---|
| Revision/image + migration + aws/session/Secure + หนึ่ง worker/replica ไม่มี host port รั่ว | PENDING |
| external preflight แบบ real LINE, browser login/change-password/logout TH/EN ที่ desktop และ 390px | PENDING |
| staff ข้ามคน/หอ/เคสไม่ได้ (403/404), manager scope และ fake identity/actor ใช้ไม่ได้; Demo ต้อง Basic; simulator ต้อง Basic+session ของตัวเอง | PENDING |
| per-client IP: IP จริงสองแหล่งไม่รวม bucket; X-Forwarded-For ปลอมสลับ IP แล้วไม่หนีเพดาน; คนหลัง NAT ทดสอบ/เว้นช่วงตาม Retry-After | PENDING |
| LINE Channel Verify และ LINK/Offer/buttons → approval/Handover/check-in หลังเปลี่ยนด่าน บัญชีเดิมยังผูกถูกคน | PENDING |
| REGISTER ผ่าน LINE → สมัคร → login ได้ staff/role/ward ถูกต้อง; code เดิมใช้ซ้ำไม่ได้ | PENDING |
| self-leave ของตนทำงานทันทีตาม flow เดิม; ปฏิเสธคนอื่นไม่สร้าง Event | PENDING |
| reset ครั้งสุดท้ายในช่วงทดสอบที่ตกลง: บัญชี/subject/role/ward/disabled คงเดิม; session/code เก่าใช้ไม่ได้; login ใหม่ได้; LINE binding ใช้กติกา reset เดิม (อาจต้อง LINK ใหม่) | PENDING |

ก่อน reset แจ้งทีม/จบ LINE smoke และเก็บหลักฐานไว้ เพราะ reset เปลี่ยนสถานการณ์และอาจล้าง LINE bindings ใช้ปุ่ม reset ที่รองรับ auth เท่านั้น ไม่ใช้ `python -m app.seed` บนเครื่องที่มีบัญชี

### Baseline ที่ผู้ deploy รายงานก่อน AU4 (2026-10-22)

SHA `2983a6b1917672dde7a9dff46ae10cfd6a4c4adc`, migration `b8f3d5a0c2e4 (head)`, APP_ENV=dev, AUTH_MODE=demo, LINE_MODE=real ไม่มีบัญชี head/supervisor จาก query ที่ผู้ deploy ส่งมา Baseline นี้ **ไม่ใช่** หลักฐานว่า AU4 ผ่าน และไม่ใช่ build attestation

## Rollback triggers และวิธี

หยุดตรวจ/จำกัดการเข้าถึงทันทีถ้า auth/config ไม่ใช่ session, anonymous business API ผ่าน, Demo ข้าม Basic ได้, ข้อมูลคนอื่นหลุด, cookie ไม่ Secure, migration/startup ผิดพลาด หรือ Channel Verify/LINE flow ที่เคยผ่านกลับล้มหลังเปลี่ยนด่าน

1. บันทึกเฉพาะ status/error ที่ไม่ใส่ secret และหยุด `nara` ก่อนเปลี่ยน source
2. checkout SHA ใน `/etc/nara/au4-before.commit`; ใช้ compose ของ revision นั้น `down` (ไม่ `-v`) แล้ว `sudo systemctl start nara` ให้กลับไปด่าน Basic ครอบทั้งหมดเดิม ตรวจ Gate **จาก checkout เดิม** และ Channel Verify ซ้ำ
3. AU4 ไม่มี migration จึงไม่ downgrade หรือล้าง DB บัญชีที่สร้างไว้คงอยู่ ถ้า rollback revision เก่าไม่มี guard auth ห้ามเปิดด่าน Basic ออก
4. ไม่ restore SQL backup ทับงานใหม่โดยอัตโนมัติ ใช้เฉพาะ recovery ที่ตกลงกับทีม ถ้า migration ของ PR อื่นล้มให้ใช้แผนของ migration นั้น
5. ถ้า LINE Verify ยังล้มหลัง rollback ให้คง/ปิด Use webhook ตามการวิเคราะห์และรายงานทีม อย่าสลับกลับ tunnel ที่หมดอายุหรือเปิด proxy เพิ่มเอง
