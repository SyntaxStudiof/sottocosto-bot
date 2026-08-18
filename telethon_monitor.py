import os
import re
import json
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from utils import clean_title, split_multiple_offers  # <--- HO AGGIUNTO split_multiple_offers
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

# Regex per trovare link Amazon e prezzi
AMAZON_URL_RE = re.compile(r'https?://(?:www\.)?(?:amazon\.[a-z.]+|amzn\.to|amzn\.eu)/\S+')
PRICE_RE = re.compile(r'(\d+[.,]\d{2})\s*€')

PRIME_KEYWORDS = ["tryprime", "gp/prime", "primevideo", "amazonprime", "primeday", "gp/video"]


def find_product_link(text):
    """Trova tra tutti i link Amazon nel testo quello che sembra un vero prodotto, escludendo link Prime/promo."""
    all_links = AMAZON_URL_RE.findall(text)
    for link in all_links:
        link_lower = link.lower()
        if any(keyword in link_lower for keyword in PRIME_KEYWORDS):
            continue
        if "/dp/" in link_lower or "amzn.to" in link_lower or "amzn.eu" in link_lower or "gp/product" in link_lower:
            return link
    return None


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
        
        # Dividiamo il messaggio in più offerte (se il messaggio ne contiene più di una)
        text_parts = split_multiple_offers(text)
        
        for single_offer_text in text_parts:

            product_link = find_product_link(single_offer_text)
            if not product_link:
                continue

            # Estraiamo i prezzi solo da questa singola offerta
            prezzi = PRICE_RE.findall(single_offer_text) 

            # Puliamo il titolo solo da questa singola offerta
            title_cleaned = clean_title(single_offer_text)

            # Uso un piccolo trucco per rendere l'ID univoco e senza caratteri strani
            # che potrebbero rompere i pulsanti di approvazione
            candidate_id = f"{channel_username}_{message.id}_{abs(hash(single_offer_text))}"
            
            # Salviamo nei dati del foglio Google
            set_state(f"pending_candidate_link_{candidate_id}", product_link)
            set_state(f"pending_candidate_testo_{candidate_id}", title_cleaned)  
            set_state(f"pending_candidate_prezzi_{candidate_id}", ",".join(prezzi))

            # Mandiamo l'anteprima al proprietario
            send_proposal(candidate_id, title_cleaned, product_link, prezzi)

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
