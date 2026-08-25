#!/bin/bash
# Ubuntu/Debian serverda botni bir buyruq bilan o'rnatadi.
#   curl -fsSL https://raw.githubusercontent.com/muhammadrasul11224433-alt/bot/main/deploy.sh | sudo bash -s TOKEN
set -euo pipefail

REPO="https://github.com/muhammadrasul11224433-alt/bot.git"
SRC_DIR="/opt/muzika-src"
TOKEN="${1:-${BOT_TOKEN:-}}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Root kerak: sudo bash deploy.sh <TOKEN>"
  exit 1
fi

if [[ -z "$TOKEN" ]]; then
  echo "Token kerak. Misol:"
  echo "  sudo bash deploy.sh 1234567890:AA..."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git python3 python3-venv python3-pip ffmpeg ca-certificates

if [[ -d "$SRC_DIR/.git" ]]; then
  git -C "$SRC_DIR" pull --ff-only
else
  rm -rf "$SRC_DIR"
  git clone --depth 1 "$REPO" "$SRC_DIR"
fi

cd "$SRC_DIR"
printf 'BOT_TOKEN=%s\n' "$TOKEN" > .env
chmod 600 .env

chmod +x install.sh
bash install.sh
