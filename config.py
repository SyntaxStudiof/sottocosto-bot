"""Configurazione centralizzata del bot.

Tutti i valori sensibili sono letti da variabili d'ambiente per sicurezza.
Non commitare mai valori hardcoded su GitHub.
"""

import os

# === Telegram Bot ===
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_OWNER_CHAT_ID = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")

# === Telethon (monitor canali terzi) ===
TELEGRAM_API_ID = os.environ.get("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION_STRING = os.environ.get("TELEGRAM_SESSION_STRING", "")

# === Google Sheet ===
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# === Web Server (Render) ===
PORT = int(os.environ.get("PORT", 5000))

# === Regole di business ===
MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", 20))
AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG", "sottocostoclu-21")

# === Auto-approvazione AI ===
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
AUTO_APPROVAL_ENABLED = os.environ.get("AUTO_APPROVAL_ENABLED", "true").lower() == "true"
DEDUP_ORE = int(os.environ.get("DEDUP_ORE", 48))
