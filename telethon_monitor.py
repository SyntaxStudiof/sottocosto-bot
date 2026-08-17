import os
import re
import json
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import requests

from sheet_client import get_state, set_state

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION_STRING = os.environ["TELEGRAM_SESSION_STRING"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_CHAT_ID = os.environ["TELEGRAM_OWNER_CHAT_ID"]

BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

CHANNELS = [
    "lapaginadegliscontiDEALS",
    "mister_affare",
    "lapaginadegliscontiMODA",
    "RisparmioGaming",
    "passioneapple",
    "RisparmiareSulWeb",
]

AMAZON_URL_RE = re.compile(r'https?://(?:www\.)?(?:amazon\.[a-z.]+|amzn\.to|amzn\.eu)/\S+')
PRICE_RE = re.compile(r'(\d+[.,]\d{2})\s*€')


def send_proposal(candidate_id, testo_originale, link, prezzi):
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approva", "callback_data": f"approva_{candidate_id}"},
            {"text": "❌ Scarta", "callback_data": f"scarta_{candidate_id}"},
        ]]
    }
    testo = (
        f"🆕 Offerta trovata:\n\n{testo_originale[:400]}\n\n"
        f"🔗 {link}\n"
        f"💰 Prezzi trovati: {', '.join(prezzi) if prezzi else 'nessuno, controlla a mano'}"
    )
    requests.post(f"{BOT_API_URL}/sendMessage", data={
        "chat_id": OWNER_CHAT_ID,
        "text": testo,
        "reply_markup": json.dumps(keyboard),
    })


def process_channel(client, channel_username):
    last_id_key = f"monitor_lastid_{channel_username}"
    last_id = int(get_state(last_id_key, "0") or "0")
    max_id_seen = last_id

    for message in client.iter_messages(channel_username, min_id=last_id, limit=20):
        if message.id > max_id_seen:
            max_id_seen = message.id

        text = message.text or ""
        amazon_match = AMAZON_URL_RE.search(text)
        if not amazon_match:
            continue

        prezzi = PRICE_RE.findall(text)

        candidate_id = f"{channel_username}_{message.id}"
        set_state(f"pending_candidate_link_{candidate_id}", amazon_match.group(0))
        set_state(f"pending_candidate_testo_{candidate_id}", text[:500])
        set_state(f"pending_candidate_prezzi_{candidate_id}", ",".join(prezzi))

        send_proposal(candidate_id, text, amazon_match.group(0), prezzi)

    if max_id_seen > last_id:
        set_state(last_id_key, str(max_id_seen))


def main():
    with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        for channel in CHANNELS:
            try:
                process_channel(client, channel)
            except Exception as e:
                print(f"Errore su {channel}: {e}")


if __name__ == "__main__":
    main()
