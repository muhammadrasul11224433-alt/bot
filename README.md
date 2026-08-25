# Navo Orbit — Telegram musiqa va video bot

Qo‘shiq qidiradi, 8D / Echo / Bass effektlarini qo‘yadi, YouTube, Instagram,
TikTok va boshqa platformalardan video yuklaydi, yumaloq video (кружок) yasaydi.
Ruscha, tojikcha va inglizcha ishlaydi.

## Imkoniyatlar

- Qo‘shiq nomini yozsangiz — 10 ta namuna, raqamli tugmalar bilan
- Raqamni bosish — musiqa keladi; `🎚 Effektlar` — 8D, Echo, Bass
- Havola tashlash — video keladi, `🎵 To‘liq qo‘shiq` bilan to‘liq versiyani topadi
- Qo‘shiq va videoni fayl sifatida yuklab olish
- `/round` — yumaloq video (video note)
- Kesh: bir marta yuborilgan fayl ikkinchi marta darhol keladi

## Buyruqlar

| Buyruq | Vazifa |
|---|---|
| `/start` | Botni ishga tushirish |
| `/round` | Yumaloq video yasash |
| `/help` | Yordam |

## O‘rnatish (lokal)

Kerak: Python 3.10+ va internet. `ffmpeg` `imageio-ffmpeg` orqali avtomatik keladi.

```bash
pip install -r requirements.txt
cp .env.example .env      # Windows: copy .env.example .env
```

`.env` ichiga [@BotFather](https://t.me/BotFather) dan olingan tokenni yozing:

```
BOT_TOKEN=1234567890:AA...
```

Ishga tushirish:

```bash
python bot.py
```

Windows’da `run.bat` ni ikki marta bosish ham yetarli.

## Serverga qo‘yish

Railway, Render, Fly.io, VPS va Docker usullari `DEPLOY.md` da yozilgan.
Eng oson yo‘l — Railway: GitHub repozitoriyni ulab, `BOT_TOKEN` ni qo‘shish.

VPS uchun bitta buyruq:

```bash
curl -fsSL https://raw.githubusercontent.com/muhammadrasul11224433-alt/bot/main/deploy.sh \
  | sudo bash -s YOUR_TOKEN
```

## Fayllar

| Fayl | Vazifa |
|---|---|
| `bot.py` | Telegram handlerlari va tugmalar |
| `media.py` | Yuklab olish, effektlar, ffmpeg |
| `i18n.py` | Ruscha / tojikcha / inglizcha matnlar |
| `config.py` | Token va cheklovlar |
| `install.sh`, `muzika-bot.service` | systemd o‘rnatish |
| `Dockerfile`, `docker-compose.yml` | Docker |

## Eslatma

- `.env` ni GitHub ga qo‘ymang, token o‘g‘irlanishi mumkin.
- Bitta tokenni bir vaqtda ikki joyda ishlatmang, `Conflict` xatosi chiqadi.
- YouTube o‘zgarganda: `pip install -U yt-dlp`.
