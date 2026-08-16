import re
import requests
from datetime import datetime, timedelta, timezone

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from sheet_client import get_state, set_state, append_product_row

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def get_updates(offset):
    resp = requests.get(f"{API_URL}/getUpdates", params={"offset": offset, "timeout": 0})
    resp.raise_for_status()
    return resp.json().get("result", [])


def send_message(chat_id, text):
    requests.post(f"{API_URL}/sendMessage", data={"chat_id": chat_id, "text": text})


def resolve_and_extract_asin(link):
    resp = requests.get(link, allow_redirects=True, timeout=10, headers=HEADERS)
    final_url = resp.url
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", final_url)
    asin = match.group(1) if match else ""
    return asin, resp.text


def extract_meta(html, prop):
    match = re.search(rf'<meta property="{prop}" content="([^"]+)"', html)
    if match:
        return match.group(1)
    if prop == "og:title":
        match = re.search(r"<title>([^<]+)</title>", html)
        if match:
            return match.group(1).replace(" : Amazon.it", "").strip()
    return ""


def handle_aggiungi(chat_id, args):
    link = args.strip()
    if not link.startswith("http"):
        send_message(chat_id, "Mandami un link Amazon valido dopo /aggiungi")
        return

    asin, html = resolve_and_extract_asin(link)
    titolo = extract_meta(html, "og:title")
    immagine = extract_meta(html, "og:image")

    # salva lo stato "in attesa di prezzi" per questa chat
    set_state(f"pending_link_{chat_id}", link)
    set_state(f"pending_titolo_{chat_id}", titolo)
    set_state(f"pending_immagine_{chat_id}", immagine)
    set_state(f"pending_asin_{chat_id}", asin)

    if titolo:
        send_message(chat_id, f"📦 {titolo}\n\nOra mandami i prezzi così:\nprezzo_scontato prezzo_pieno\n(es: 23.14 29.99)")
    else:
        send_message(chat_id, "⚠️ Non sono riuscito a leggere il titolo. Mandami comunque i prezzi, poi il titolo lo scrivi tu.")


def handle_prezzi(chat_id, text):
    pending_link = get_state(f"pending_link_{chat_id}", "")
    if not pending_link:
        return False  # non c'è nessuna richiesta in sospeso, ignora

    parts = text.split()
    if len(parts) < 2:
        return False

    try:
        prezzo_scontato = float(parts[0].replace(",", "."))
        prezzo_pieno = float(parts[1].replace(",", "."))
    except ValueError:
        return False

    titolo = get_state(f"pending_titolo_{chat_id}", "")
    immagine = get_state(f"pending_immagine_{chat_id}", "")
    asin = get_state(f"pending_asin_{chat_id}", "")

    if not titolo:
        titolo = " ".join(parts[2:]) if len(parts) > 2 else "(titolo da completare)"

    sconto_percento = round((1 - prezzo_scontato / prezzo_pieno) * 100)
    now = datetime.now(timezone.utc)

    append_product_row({
        "titolo": titolo,
        "prezzo": str(prezzo_scontato).replace(".", ","),
        "prezzo_originale": str(prezzo_pieno).replace(".", ","),
        "sconto_percento": sconto_percento,
        "link_affiliato": pending_link,
        "immagine_url": immagine,
        "ASIN": asin,
        "fonte": "manuale",
        "stato": "NUOVO",
        "aggiunto_il": now.isoformat(),
        "scade_il": (now + timedelta(hours=4)).isoformat(),
        "pubblicato_il": "",
    })

    # pulisce lo stato in sospeso
    set_state(f"pending_link_{chat_id}", "")

    nota = "" if immagine else "\n⚠️ Manca l'immagine — aggiungila a mano sul foglio."
    send_message(chat_id, f"✅ Aggiunto: {titolo}\nSconto: {sconto_percento}%{nota}")
    return True


def main():
    last_id = get_state("last_update_id", "0")
    offset = int(last_id) + 1 if last_id else 0

    updates = get_updates(offset)
    for update in updates:
        update_id = update["update_id"]
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id")

        if text.startswith("/aggiungi"):
            args = text[len("/aggiungi"):].strip()
            handle_aggiungi(chat_id, args)
        elif chat_id:
            handle_prezzi(chat_id, text)

        set_state("last_update_id", str(update_id))


if __name__ == "__main__":
    main()
