import os
import re
import json
import asyncio
import requests
import html as html_module
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from utils import clean_title, split_multiple_offers
from sheet_client import get_state, set_state, get_all_rows, append_product_row
from config import AUTO_APPROVAL_ENABLED
from ai_offer_parser import parse_offerta_da_testo
from auto_approval import arricchisci_dati, valida_offerta, asin_recenti_dal_foglio

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
    "occasionissimaoffertesconti",
]

AMAZON_URL_RE = re.compile(r'https?://(?:www\.)?(?:amazon\.[a-z.]+|amzn\.to|amzn\.eu)/\S+')
PRICE_RE = re.compile(r'(\d+[.,]\d{2})\s*€')
PRIME_KEYWORDS = ["tryprime", "gp/prime", "primevideo", "amazonprime", "primeday", "gp/video"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_executor = ThreadPoolExecutor(max_workers=1)


def _run_async(coro, timeout=90):
    """Esegue una coroutine in un thread separato (compatibile con telethon.sync)."""
    return _executor.submit(asyncio.run, coro).result(timeout=timeout)


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


def process_channel(client, channel_username, righe):
    last_id_key = f"monitor_lastid_{channel_username}"
    last_id = int(get_state(last_id_key, "0") or "0")
    max_id_seen = last_id

    processed_asin_key = f"processed_asins_{channel_username}"
    processed_asins_str = get_state(processed_asin_key, "")
    processed_asins = processed_asins_str.split(",") if processed_asins_str else []
    if len(processed_asins) > 100:
        processed_asins = processed_asins[-50:]

    offers_found_here = 0
    now = datetime.now(timezone.utc)

    try:
        for message in client.iter_messages(channel_username, min_id=last_id, limit=20):
            if message.id > max_id_seen:
                max_id_seen = message.id

            message_date = message.date.replace(tzinfo=timezone.utc)
            if message_date < now - timedelta(hours=24):
                continue

            text = message.text or ""
            text_parts = split_multiple_offers(text)

            for single_offer_text in text_parts:
                product_link = find_product_link(single_offer_text)
                if not product_link:
                    continue

                asin, _, _ = resolve_and_extract_asin(product_link)
                if asin:
                    candidate_id = f"{channel_username}_{asin}"
                else:
                    candidate_id = f"{channel_username}_{message.id}"

                if candidate_id in processed_asins:
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

                if prezzo_scontato is None:
                    try:
                        _, html_page, _ = resolve_and_extract_asin(product_link)
                        scraped_price = extract_price(html_page)
                        if scraped_price:
                            prezzo_scontato = scraped_price
                            prezzo_originale = None
                    except:
                        pass

                # --- NUOVO: tentativo di approvazione automatica ---
                auto_done = False
                if AUTO_APPROVAL_ENABLED:
                    try:
                        dati = _run_async(parse_offerta_da_testo(single_offer_text))
                        if not dati.get("prezzo_scontato") and prezzo_scontato:
                            dati["prezzo_scontato"] = float(str(prezzo_scontato).replace(",", "."))
                        if not dati.get("prezzo_pieno") and prezzo_originale:
                            dati["prezzo_pieno"] = float(str(prezzo_originale).replace(",", "."))
                        if not dati.get("titolo"):
                            dati["titolo"] = title_cleaned
                        if not dati.get("asin") and asin:
                            dati["asin"] = asin
                        if not dati.get("link_originale"):
                            dati["link_originale"] = product_link
                        dati = arricchisci_dati(dati)
                        ok, motivi = valida_offerta(dati, asin_recenti_dal_foglio(righe))
                        if ok:
                            now_auto = datetime.now(timezone.utc)
                            append_product_row({
                                "titolo": dati["titolo"],
                                "prezzo": dati["prezzo_scontato_eur"],
                                "prezzo_originale": dati["prezzo_pieno_eur"],
                                "sconto_percento": dati["sconto_percent"],
                                "link_affiliato": dati["link_affiliato"],
                                "immagine_url": dati["immagine_url"],
                                "ASIN": dati["asin"],
                                "fonte": "canale_terzo",
                                "stato": "APPROVATO",
                                "aggiunto_il": now_auto.isoformat(),
                                "scade_il": (now_auto + timedelta(hours=6)).isoformat(),
                                "pubblicato_il": "",
                            })
                            requests.post(f"{BOT_API_URL}/sendMessage", data={
                                "chat_id": OWNER_CHAT_ID,
                                "text": f"🤖 Auto-approvata: {dati['titolo']}\n💰 {dati['prezzo_scontato_eur']}€ invece di {dati['prezzo_pieno_eur']}€ (−{dati['sconto_percent']}%)",
                            })
                            auto_done = True
                        else:
                            print(f"[auto] Non approvata ({candidate_id}): {motivi}")
                    except Exception as e:
                        print(f"[auto] Errore pipeline, uso flusso manuale: {e}")

                if auto_done:
                    processed_asins.append(candidate_id)
                    if len(processed_asins) > 50:
                        processed_asins = processed_asins[-50:]
                    set_state(processed_asin_key, ",".join(processed_asins))
                    offers_found_here += 1
                    continue

                # --- Flusso manuale esistente (fallback) ---
                set_state(f"pending_candidate_link_{candidate_id}", product_link)
                set_state(f"pending_candidate_testo_{candidate_id}", title_cleaned)
                set_state(f"pending_candidate_prezzo_scontato_{candidate_id}", prezzo_scontato)
                set_state(f"pending_candidate_prezzo_originale_{candidate_id}", prezzo_originale)

                send_proposal(candidate_id, title_cleaned, product_link, prezzo_scontato, prezzo_originale)

                processed_asins.append(candidate_id)
                if len(processed_asins) > 50:
                    processed_asins = processed_asins[-50:]
                set_state(processed_asin_key, ",".join(processed_asins))

                offers_found_here += 1

    finally:
        if max_id_seen > last_id:
            set_state(last_id_key, str(max_id_seen))

    return offers_found_here


def main():
    total_offers_found = 0

    try:
        righe, _ = get_all_rows()
    except Exception as e:
        print(f"Errore lettura foglio per anti-duplicato: {e}")
        righe = []

    with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        for channel in CHANNELS:
            try:
                offers_found = process_channel(client, channel, righe)
                total_offers_found += offers_found
            except Exception as e:
                print(f"Errore su {channel}: {e}")

    if total_offers_found == 0:
        requests.post(f"{BOT_API_URL}/sendMessage", data={
            "chat_id": OWNER_CHAT_ID,
            "text": "🔍 Scansione completata: nessuna nuova offerta trovata in tutti i canali."
        })


if __name__ == "__main__":
    main()
