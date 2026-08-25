#!/bin/bash
set -euo pipefail

APP_DIR="/opt/muzika-bot"
SERVICE_USER="bot"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Root kerak. Ishga tushiring: sudo bash install.sh"
  exit 1
fi

if [[ ! -f .env ]] || ! grep -qE '^BOT_TOKEN=.+:.+' .env; then
  echo ".env faylida haqiqiy BOT_TOKEN yoq."
  echo "Avval .env yarating:  cp .env.example .env  va tokenni yozing."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip ffmpeg ca-certificates

id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"

mkdir -p "$APP_DIR/downloads"
cp -f bot.py config.py i18n.py media.py requirements.txt "$APP_DIR/"
cp -f .env "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

cp -f muzika-bot.service /etc/systemd/system/muzika-bot.service
systemctl daemon-reload
systemctl enable --now muzika-bot

echo
echo "Bot ishga tushdi."
echo "Holat:   systemctl status muzika-bot"
echo "Log:     journalctl -u muzika-bot -f"
echo "Toxtatish: systemctl stop muzika-bot"
echo "Qayta:   systemctl restart muzika-bot"
