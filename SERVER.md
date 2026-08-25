# Botni serverga qo‘yish — qadamma-qadam

Bot polling usulida ishlaydi. Maxsus domen, HTTPS yoki ochiq port shart emas.
Faqat internet va `BOT_TOKEN` kerak.

**Muhim:** bir xil token bilan botni 2 joyda (kompyuter + server) birga ishlatmang.

---

## 0) Telegram bot token

1. Telegramda [@BotFather](https://t.me/BotFather) ni oching.
2. `/newbot` yozing.
3. Bot nomi va username bering (username `...bot` bilan tugashi kerak).
4. Berilgan tokenni saqlang. Namuna: `7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

---

## 1-usul: Ubuntu / Debian VPS (tavsiya)

Kerak: Ubuntu 22.04 yoki 24.04, root yoki `sudo` huquqi.

### 1. Serverga ulaning

Windows PowerShell:

```bash
ssh root@SERVER_IP
```

### 2. Fayllarni yuklang

Kompyuterdagi `bot.muzika` papkasini serverga ko‘chiring. Misol (Windows PowerShell):

```powershell
scp -r "C:\Users\2024\Desktop\bot.muzika" root@SERVER_IP:/root/bot.muzika
```

Yoki serverda:

```bash
apt update
apt install -y git
# agar loyiha gitda bo'lsa:
# git clone YOUR_REPO_URL /root/bot.muzika
```

### 3. Token yozing

```bash
cd /root/bot.muzika
cp .env.example .env
nano .env
```

Ichiga faqat shu qator:

```
BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Saqlash: `Ctrl+O`, Enter, chiqish: `Ctrl+X`.

### 4. O‘rnatish va avto-start

```bash
chmod +x install.sh
sudo bash install.sh
```

Skript o‘zi qiladi:

- Python, ffmpeg o‘rnatadi
- `/opt/muzika-bot` ga nusxa ko‘chiradi
- `bot` foydalanuvchisini yaratadi
- systemd xizmatini yoqadi (`restart=always`)

### 5. Tekshirish

```bash
systemctl status muzika-bot
journalctl -u muzika-bot -f
```

`Bot starting` chiqsa — ishlayapti. Telegramda botga `/start` yozing.

### Foydali buyruqlar

| Vazifa | Buyruq |
|---|---|
| Holat | `systemctl status muzika-bot` |
| Log | `journalctl -u muzika-bot -f` |
| Qayta ishga tushirish | `systemctl restart muzika-bot` |
| To‘xtatish | `systemctl stop muzika-bot` |
| Yoqish (rebootdan keyin) | `systemctl enable muzika-bot` |
| Kodni yangilash | fayllarni `/opt/muzika-bot` ga ko‘chirib `systemctl restart muzika-bot` |

Kodni yangilaganda:

```bash
sudo cp bot.py config.py i18n.py media.py /opt/muzika-bot/
sudo systemctl restart muzika-bot
```

`yt-dlp` ni yangilash (YouTube/Instagram buzilsa):

```bash
sudo /opt/muzika-bot/.venv/bin/pip install -U yt-dlp
sudo systemctl restart muzika-bot
```

---

## 2-usul: Docker (osonroq, lekin Docker o‘rnatilgan bo‘lishi kerak)

```bash
cd /root/bot.muzika
cp .env.example .env
nano .env          # BOT_TOKEN ni yozing

apt install -y docker.io docker-compose-v2
docker compose up -d --build
docker compose logs -f
```

To‘xtatish:

```bash
docker compose down
```

Qayta yig‘ish:

```bash
docker compose up -d --build
```

---

## 3-usul: screen (tez sinash, rebootda o‘chadi)

```bash
apt update
apt install -y python3 python3-venv python3-pip ffmpeg screen
cd /root/bot.muzika
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env

screen -S muzika
python bot.py
```

Chiqish (bot ishlab turadi): `Ctrl+A`, keyin `D`.

Qaytish: `screen -r muzika`

---

## 4-usul: Windows server / o‘z kompyuteringiz

1. `.env` yarating, ichiga `BOT_TOKEN=...` yozing.
2. `run.bat` ni ikki marta bosing.
3. Doim ishlashi uchun kompyuter o‘chmasligi kerak. Barqaror ish uchun Linux VPS yaxshiroq.

---

## Xatoliklar

**`Conflict: terminated by other getUpdates`**  
Token allaqachon boshqa joyda ishlatilmoqda. Kompyuterdagi `python bot.py` / `run.bat` ni yoping, faqat serverda qoldiring.

**Bot javob bermaydi**  
`journalctl -u muzika-bot -n 50 --no-pager` ni oching. Token to‘g‘riligini tekshiring. `@BotFather` da `/token` orqali qayta oling.

**Video/Instagram yuklanmaydi**  
Ba’zi havolalar login talab qiladi. Avval YouTube havolasini sinab ko‘ring. `yt-dlp` ni yangilang.

**`BOT_TOKEN` topilmadi**  
`.env` fayl bot papkasida bo‘lishi kerak. systemd uchun: `/opt/muzika-bot/.env`.

---

## Xavfsizlik

- `.env` ni hech kimga yubormang, GitHub ga qo‘ymang.
- Serverda: `chmod 600 /opt/muzika-bot/.env`
- Firewall ochiq port shart emas (polling chiqishga ulanadi).
- Token oqib ketgan bo‘lsa, BotFather da `/revoke` qiling va yangi token yozing.
