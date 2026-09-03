# ARCH BRAIN STORMING — Hugging Face par 24/7 (PC band pe bhi, AI-read ke saath)

Free hai, card nahi lagta. Ek baar setup — phir PC band karo, software chalta rahega.

---

## Step 1 — Account (2 min)
1. https://huggingface.co/join par email se account banao (card nahi maangta).
2. Email verify karo.

## Step 2 — Space banao
1. https://huggingface.co/new-space kholo.
2. **Space name**: `arch-brain-storming` (jo chaho)
3. **SDK**: **Docker** chuno (template: Blank).
4. **Visibility**: **Private** rakho (zaroori — credentials secret hai).
5. **Create Space** dabao.

## Step 3 — Logins ko restart-proof banao (FREE tarika)
Seedhi baat: HF ka `/data` persistent storage **paid** hai ($5/mahina) — free
me container restart par files reset hoti hain. Iska free hal:

- Jab bhi aap admin panel me clients bana/badla karo, PC par apni local
  `users.json` bhi waisi hi rakho (ya cloud wali ka content copy kar lo), aur
  uska pura content Space ke **Secret** me daal do:
  - Name: `USERS_JSON`
  - Value: users.json ka pura content (JSON)
- Restart par server isi secret se user-list wapas bana leta hai.
- (Chaho to baad me $5/mo storage lekar ye jhanjhat hata sakte ho — tab
  `/data` अपने आप use hoga.)

Note: exports (out/) bhi restart par saaf ho jate hain — DXF download karke
apne paas rakh lena hi kaafi hai.

## Step 4 — Claude ka login-token daalo (AI-read ke liye)
1. Apne PC par is folder me **`GET-CLAUDE-SECRET.bat`** double-click karo —
   token clipboard me aa jayega.
2. Space ke **Settings → Variables and secrets → New secret**:
   - Name: `CLAUDE_CREDENTIALS`
   - Value: **Ctrl+V** (paste)
3. Save.

> Token 1–2 mahine me expire ho sakta hai. AI-read "sign-in expired" bole to:
> PC par CLI me `/login` karo → phir `GET-CLAUDE-SECRET.bat` dobara chala kar
> naya token secret me paste kar do. Bas.

## Step 5 — Code upload karo
Space banne par HF ek git URL deta hai. Is SketchToPlan folder se:

```bash
git init
git add .
git commit -m "deploy"
git remote add hf https://huggingface.co/spaces/<APKA-USERNAME>/arch-brain-storming
git push hf main --force
```

(Push par HF username + **Access Token** maangega — token yahan banta hai:
https://huggingface.co/settings/tokens → New token → type **Write**.)

`.dockerignore` already NBC/, exe, dwg, users.json, out/, work/ ko bahar
rakhta hai — repo chhota rahega.

## Step 6 — Build + test
- Space page par build ~5–8 min chalega, phir app khul jayegi.
- URL: `https://<APKA-USERNAME>-arch-brain-storming.hf.space`
- Login: `admin` / `sara@admin` (pehli baar) → admin panel se clients banao,
  aur admin ka password badal lo.
- **Read Sketch (AI)** test karo — Claude cloud se hi padhega, PC band rakho.

## Step 7 — saradigitalstudios.com se jodna (URL bar me domain hi rahega)
HF free me custom domain nahi deta, isliye Cloudflare ka free **Worker** beech me
proxy banega (Space **Private** hi rah sakta hai):

1. Cloudflare dashboard → **Workers & Pages → Create → Create Worker** → naam
   `archbrain` → Deploy.
2. **Edit code** → is folder ki `cloudflare-worker.js` ka pura content paste →
   Deploy.
3. Worker → **Settings → Variables and Secrets**:
   - `SPACE_HOST` (Text) = `<APKA-USERNAME>-arch-brain-storming.hf.space`
   - `HF_TOKEN` (Secret) = HF access token (Read) — sirf Private Space ke liye
4. Worker → **Settings → Domains & Routes → Add → Custom domain** →
   `saradigitalstudios.com` daalo, phir `www.saradigitalstudios.com` bhi.
   (Purana cloudflared tunnel wala DNS record Cloudflare khud hata/badal dega —
   pooche to "replace" karo.)
5. 2–5 min me https://saradigitalstudios.com Space se chalne lagega — PC band.

Worker free limit: 1,00,000 requests/din — bahut kaafi.

---

## Yaad rakhne wali cheezein
- **48 ghante** tak koi visitor na aaye to Space so jata hai — agla visitor
  ~1–2 min me use jaga leta hai. Roz use ho raha ho to kabhi nahi sota.
- Clients ke AI-reads **aapke Claude account ki limit** se khinchte hain.
- NBC rulebook folder cloud par nahi hai (bahut bada) — rulebook-checks wahan
  limited rahenge; baaki sab features poore.
- PC wala setup (START-DOMAIN.bat) jaisa tha waisa hi hai — dono saath chal
  sakte hain.
