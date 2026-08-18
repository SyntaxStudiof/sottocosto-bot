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


def send_proposal(candidate_id, testo_originale, link, prezzo_scontato, prezzo_originale):
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approva", "callback_data": f"approva_{candidate_id}"},
            {"text": "❌ Scarta", "callback_data": f"scarta_{candidate_id}"},
        ]]
    }
    # Costruisci il testo del messaggio di anteprima con i prezzi ben separati
    testo = f"🆕 Offerta trovata:\n\n{testo_originale[:400]}\n\n"
    testo += f"🔗 {link}\n"
    if prezzo_scontato:
        testo += f"💰 Prezzo scontato: {prezzo_scontato}€\n"
    if prezzo_originale:
        testo += f"💰 Prezzo originale: {prezzo_originale}€\n"
    
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
        text_parts = split_multiple_offers(text)
        
        for single_offer_text in text_parts:
            product_link = find_product_link(single_offer_text)
            if not product_link:
                continue

            # --- NUOVA LOGICA PER I PREZZI ---
            # Cerca prima il prezzo in offerta e quello consigliato leggendo le etichette nel testo
            prezzi_scontati = re.findall(r'[Pp]rezzo\s*in\s*offerta\s*[:.]?\s*(\d+[.,]\d{2})', single_offer_text)
            prezzi_originali = re.findall(r'[Pp]rezzo\s*consigliato\s*[:.]?\s*(\d+[.,]\d{2})', single_offer_text)

            prezzo_scontato = None
            prezzo_originale = None

            if prezzi_scontati:
                prezzo_scontato = prezzi_scontati[0]
            else:
                # Fallback: Se non trova la scritta "in offerta", prende il numero più basso trovato
                all_prices = PRICE_RE.findall(single_offer_text)
                if all_prices:
                    # Converte in float per capire il più piccolo (per lo sconto) e il più grande (per l'originale)
                    float_prices = sorted([float(p.replace(',', '.')) for p in all_prices])
                    prezzo_scontato = str(float_prices[0]).replace('.', ',')
                    if len(float_prices) > 1:
                        prezzo_originale = str(float_prices[-1]).replace('.', ',')

            if prezzi_originali:
                prezzo_originale = prezzi_originali[0]

            title_cleaned = clean_title(single_offer_text)
            candidate_id = f"{channel_username}_{message.id}_{abs(hash(single_offer_text))}"
            
            # Salviamo i prezzi separatamente in due campi distinti
            set_state(f"pending_candidate_link_{candidate_id}", product_link)
            set_state(f"pending_candidate_testo_{candidate_id}", title_cleaned)  
            set_state(f"pending_candidate_prezzo_scontato_{candidate_id}", prezzo_scontato)
            set_state(f"pending_candidate_prezzo_originale_{candidate_id}", prezzo_originale)

            # Inviamo l'anteprima (passiamo entrambi i prezzi, anche se manca uno dei due)
            send_proposal(candidate_id, title_cleaned, product_link, prezzo_scontato, prezzo_originale)

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
