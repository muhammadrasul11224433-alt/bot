import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

TELEGRAM_MAX_FILE = 49 * 1024 * 1024
MAX_AUDIO_SECONDS = 15 * 60
MAX_VIDEO_SECONDS = 8 * 60
ROUND_SECONDS = 60
SEARCH_COUNT = 10
