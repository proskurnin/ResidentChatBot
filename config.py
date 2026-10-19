"""Centralized configuration for ResidentChatBot."""

import os

from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOTENV_FILE = os.path.join(BASE_DIR, ".env")

# Load local configuration when present; systemd EnvironmentFile values remain intact.
load_dotenv(DOTENV_FILE, override=False)

DB_FILE = os.path.join(BASE_DIR, "database.db")

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
BOT_NAME = os.getenv("BOT_NAME")
LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
TELEGRAM_PROXY = (
    os.getenv("HTTPS_PROXY")
    or os.getenv("HTTP_PROXY")
    or os.getenv("https_proxy")
    or os.getenv("http_proxy")
)
WEB_BASE_PATH = os.getenv("WEB_BASE_PATH", "/residentchatbot").rstrip("/") or "/residentchatbot"
WEB_BIND_HOST = os.getenv("WEB_BIND_HOST", "0.0.0.0")
WEB_BIND_PORT = int(os.getenv("WEB_BIND_PORT", "8080"))
WEB_SERVICE_NAME = os.getenv("WEB_SERVICE_NAME", "residentchatbot.service")
WEB_ADMIN_USER = os.getenv("WEB_ADMIN_USER", "residentchatbot")
WEB_ADMIN_PASSWORD = os.getenv("WEB_ADMIN_PASSWORD", "")

if not API_TOKEN or not ADMIN_ID_RAW:
    raise ValueError("API_TOKEN и ADMIN_ID должны быть указаны в .env")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError as exc:
    raise ValueError("ADMIN_ID должен быть целым числом") from exc
