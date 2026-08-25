@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .env (
  echo Create .env file with BOT_TOKEN=your_token from @BotFather
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
python bot.py
pause
