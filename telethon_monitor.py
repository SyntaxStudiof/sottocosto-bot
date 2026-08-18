import os
import re
import json
import requests
import html as html_module
import time
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from utils import clean_title, split_multiple_offers
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
PRIME_KEYWORDS = ["tryprime", "gp/prime", "primevideo", "amazonprime", "primeday", "gp/video"]

# --- FUNZIONI PER LO SCRAPING DI EMERGENZA ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def resolve_and_extract_asin(link):
    try:
        resp = requests.get(link, allow_redirects=True, timeout=10, headers=HEADERS)
        final_url = resp.url
        match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", final_url)
        asin = match.group(1) if match else ""
        return asin, resp.text, final_url
    except:
        return "", "", link

def extract_title(html):
    match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if match:
        return match.group(1)
    match = re.search(r"<title>([^<]+)</title>", html)
    if match:
        return match.group(1).replace(" : Amazon.it", "").strip()
    return ""

def extract_price(html):
    match = re.search(r'<span class="a-price-whole">(\d+[.,]?\d*)</span>', html)
    if match:
        return match.group(1).replace(".", ",")
    return None
# --- FINE FUNZIONI SCRAPING ---

def find_product_link(text):
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

    # --- NUOVA LOGICA ANTI-DUPLICATI ---
    # Carichiamo la lista degli ultimi messaggi già inviati per questo canale
    processed_key = f"processed_ids_{channel_username}"
    processed_ids_str = get_state(processed_key, "")
    processed_ids = processed_ids_str.split(",") if processed_ids_str else []
    
    # Se la lista diventa troppo lunga (oltre 50), teniamo solo gli ultimi 30 per non appesantire il foglio
    if len(processed_ids) > 50:
        processed_ids = processed_ids[-30:]

    for message in client.iter_messages(channel_username, min_id=last_id, limit=20):
        if message.id > max_id_seen:
            max_id_seen = message.id

        text = message.text or ""
        text_parts = split_multiple_offers(text)
        
        for single_offer_text in text_parts:
            product_link = find_product_link(single_offer_text)
            if not product_link:
                continue

            # --- CONTROLLO DUPLICATO ---
            # Generiamo un ID univoco per questa offerta
            candidate_id = f"{channel_username}_{message.id}_{abs(hash(single_offer_text))}"
            
            # Se questo ID è già nella lista dei processati, saltiamo tutto!
            if candidate_id in processed_ids:
                continue

            prezzi_scontati = re.findall(r'[Pp]rezzo\s*in\s*offerta\s*[:.]?\s*(\d+[.,]\d{2})', single_offer_text)
            prezzi_originali = re.findall(r'[Pp]rezzo\s*consigliato\s*[:.]?\s*(\d+[.,]\d{2})', single_offer_text)

            prezzo_scontato = None
            prezzo_originale = None

            if prezzi_scontati:
                prezzo_scontato = prezzi_scontati[0]
            else:
                all_prices = PRICE_RE.findall(single_offer_text)
                if all_prices:
                    float_prices = sorted([float(p.replace(',', '.')) for p in all_prices])
                    prezzo_scontato = str(float_prices[0]).replace('.', ',')
                    if len(float_prices) > 1:
                        prezzo_originale = str(float_prices[-1]).replace('.', ',')

            if prezzi_originali:
                prezzo_originale = prezzi_originali[0]

            title_cleaned = clean_title(single_offer_text)
            
            # --- FALLBACK DI EMERGENZA PER I PREZZI ---
            if prezzo_scontato is None:
                try:
                    _, html_page, _ = resolve_and_extract_asin(product_link)
                    scraped_price = extract_price(html_page)
                    if scraped_price:
                        prezzo_scontato = scraped_price
                        prezzo_originale = None
                except:
                    pass
            
            # Salviamo i dati
            set_state(f"pending_candidate_link_{candidate_id}", product_link)
            set_state(f"pending_candidate_testo_{candidate_id}", title_cleaned)  
            set_state(f"pending_candidate_prezzo_scontato_{candidate_id}", prezzo_scontato)
            set_state(f"pending_candidate_prezzo_originale_{candidate_id}", prezzo_originale)

            # Mandiamo l'anteprima
            send_proposal(candidate_id, title_cleaned, product_link, prezzo_scontato, prezzo_originale)

            # --- SALVIAMO L'ID COME "GIÀ PROCESSATO" ---
            processed_ids.append(candidate_id)
            # Salviamo la lista aggiornata nel foglio (mantenendo solo gli ultimi 30 per non farlo diventare enorme)
            if len(processed_ids) > 30:
                processed_ids = processed_ids[-30:]
            set_state(processed_key, ",".join(processed_ids))

    # Aggiorniamo l'ultimo ID visitato (per le prossime esecuzioni)
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