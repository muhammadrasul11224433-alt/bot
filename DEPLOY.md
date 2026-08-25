# Serverga qo‘yish — eng qisqa yo‘llar

Token: [@BotFather](https://t.me/BotFather) → `/newbot` → tokenni nusxalang.

**Muhim:** serverga qo‘yganda kompyuterdagi botni yoping, aks holda `Conflict` chiqadi.

---

## 1) VPS (Ubuntu / Debian) — bir buyruq

Serverga ulanib shu buyruqni yozing (tokenni o‘zingizniga almashtiring):

```bash
curl -fsSL https://raw.githubusercontent.com/muhammadrasul11224433-alt/bot/main/deploy.sh \
  | sudo bash -s 1234567890:AA...
```

Skript o‘zi: git, Python, ffmpeg o‘rnatadi, kodni klonlaydi, `systemd` xizmati
yaratadi va botni ishga tushiradi. Server o‘chib-yonsa ham avtomatik ishlaydi.

Tekshirish:

```bash
systemctl status muzika-bot
journalctl -u muzika-bot -f
```

Yangilash:

```bash
cd /opt/muzika-src && sudo git pull && sudo bash install.sh
```

VPS qayerdan olish: Hetzner, Contabo, Aeza, PS.kz, Timeweb (eng arzon tarif ham yetadi:
1 CPU, 1–2 GB RAM).

---

## 2) Railway — brauzerdan, eng oson

Repozitoriyda `railway.json` bor, Railway `Dockerfile` bilan o‘zi yig‘adi.

1. [railway.com](https://railway.com) ga GitHub bilan kiring
2. **New Project → Deploy from GitHub repo** → `muhammadrasul11224433-alt/bot`
3. Loyiha ochilgach **Variables** bo‘limiga o‘tib qo‘shing:
   - nomi: `BOT_TOKEN`
   - qiymati: BotFather bergan token
4. **Deploy** bosing. Logda `Run polling for bot` chiqsa — bot ishlayapti.

Muhim: Railway’da **Public Networking / port kerak emas** — bot polling
usulida ishlaydi, tashqi port ochilmaydi. Agar Railway port so‘rasa,
e’tibor bermang.

CLI orqali xohlasangiz:

```bash
npm i -g @railway/cli
railway login
railway init
railway variables --set "BOT_TOKEN=1234567890:AA..."
railway up
```

Eslatma: Railway’da bepul kredit tugagach xizmat to‘xtaydi, oyiga ~5$ tarif kifoya.

### Nega Vercel va Neon bo‘lmaydi

- **Vercel** — faqat qisqa (serverless) funksiyalar uchun. Telegram boti doim
  ishlab turishi kerak, ffmpeg ham kerak. Vercel’da bunday bot ishlamaydi.
- **Neon** — bu PostgreSQL ma’lumotlar bazasi xizmati, bot ishga tushiradigan
  joy emas. Bizning botga baza ham kerak emas.

---

## 3) Render.com — brauzerdan, kartasiz boshlash

1. [render.com](https://render.com) ga GitHub bilan kiring
2. **New → Blueprint**, repozitoriyni tanlang: `muhammadrasul11224433-alt/bot`
3. Render `render.yaml` ni o‘zi o‘qiydi
4. `BOT_TOKEN` maydoniga tokenni yozing → **Apply**

Bepul tarifda worker uzoq ishlamaydi, shuning uchun `starter` tarif tanlangan.

---

## 4) Fly.io

```bash
fly auth login
fly launch --copy-config --no-deploy
fly secrets set BOT_TOKEN=1234567890:AA...
fly volumes create navo_downloads --size 1
fly deploy
```

---

## 5) Docker (har qanday serverda)

```bash
git clone https://github.com/muhammadrasul11224433-alt/bot.git && cd bot
cp .env.example .env && nano .env
docker compose up -d --build
docker compose logs -f
```

---

## Xatoliklar

| Xato | Yechim |
|---|---|
| `Conflict: terminated by other getUpdates` | Bot ikki joyda ishlayapti, birini o‘chiring |
| Bot javob bermaydi | `journalctl -u muzika-bot -n 50 --no-pager` |
| YouTube/Instagram ishlamaydi | `sudo /opt/muzika-bot/.venv/bin/pip install -U yt-dlp && sudo systemctl restart muzika-bot` |
