# ARCH BRAIN STORMING — Render par 24/7 (PC band, AI-read ke saath, free, card nahi)

Hugging Face ne Docker Spaces paid kar diye (July 2026), isliye wahi Dockerfile
ab **Render** ke free Docker plan par chalta hai: 512 MB RAM, 750 hrs/mahina
(poore mahine ke liye kaafi), custom domain free.

## Step 1 — Naya service (Blueprint)
1. https://dashboard.render.com → **New + → Blueprint** → repo
   `hermosaproject847-rgb/Archbrainstroming` connect → Render `render.yaml`
   padh kar service **archbrain** (Docker, Free) banayega → **Apply**.
2. Build me Node + Claude CLI install hota hai — pehli build ~8–10 min.

## Step 2 — Secrets (Environment tab)
Service **archbrain → Environment**:
- `CLAUDE_CREDENTIALS` ← PC par `GET-CLAUDE-SECRET.bat` double-click → Ctrl+V
- `USERS_JSON`         ← PC par `GET-USERS-SECRET.bat` double-click → Ctrl+V
Save → service khud restart hoga.

> Claude token 1–2 mahine me expire ho sakta hai: AI-read "sign-in expired"
> bole to PC par CLI me `/login`, phir `GET-CLAUDE-SECRET.bat` se naya token
> secret me paste.

## Step 3 — Domain
1. archbrain → **Settings → Custom Domains → Add**: `saradigitalstudios.com`
   aur `www.saradigitalstudios.com`. Render batayega kis host par CNAME karna hai
   (`archbrain.onrender.com`).
2. Cloudflare → DNS → purane tunnel wale CNAME hatao → naye:
   - `@`   CNAME `archbrain.onrender.com`  (Proxy: DNS only, grey cloud)
   - `www` CNAME `archbrain.onrender.com`  (DNS only)
3. 5–10 min me certificate ban jata hai.

## Step 4 — Kabhi na soye (keep-alive)
Free service 15 min idle par so jata hai. Cloudflare Worker (free) har 10 min
ping karega:
Workers & Pages → Create Worker `keepalive` → Edit code → `cloudflare-keepalive.js`
paste → Deploy → **Settings → Triggers → Cron Triggers → Add** `*/10 * * * *`.

## Step 5 — Purana service
Pehla `sketchtoplan` (Python, AI-read off) ab zaroorat nahi — Settings →
Delete, warna dono 750 hrs share karenge.

## Limits
- 512 MB RAM / shared CPU: AI-read chalega par bhari sketch par 1–2 min lag
  sakta hai; edits theek hain (server side gzip + cache hai).
- Disk ephemeral: clients admin panel se banao to `USERS_JSON` secret bhi
  update rakho (GET-USERS-SECRET.bat), warna restart par wo user gayab.
- Zyada speed chahiye to Render Starter ($7/mo) ya Oracle Always-Free 24 GB
  (card verify, ₹0).
