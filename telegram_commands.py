import re
import json
import html as html_module
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

AFFILIATE_TAG = "sottocostoclub21"  # verifica sia il tuo tag esatto su Amazon Associates


def add_affiliate_tag(url):
    if "tag=" in url:
        url = re.sub(r"tag=[^&]+", f"tag={AFFILIATE_TAG}", url)
    else:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}tag={AFFILIATE_TAG}"
    return url


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
    return asin, resp.text, final_url


def extract_title(html):
    match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if match:
        return match.group(1)
    match = re.search(r"<title>([^<]+)</title>", html)
    if match:
        return match.group(1).replace(" : Amazon.it", "").strip()
    return ""


def extract_image(html):
    match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    if match:
        return match.group(1)

    match = re.search(r'data-old-hires="([^"]+)"', html)
    if match and match.group(1):
        return match.group(1)

    match = re.search(r'data-a-dynamic-image="([^"]+)"', html)
    if match:
        try:
            raw = html_module.unescape(match.group(1))
            data = json.loads(raw)
            if data:
                return list(data.keys())[0]
        except (json.JSONDecodeError, IndexError):
            pass

    return ""


def handle_aggiungi(chat_id, args):
    link = args.strip()
    if not link.startswith("http"):
        send_message(chat_id, "Mandami un link Amazon valido dopo /aggiungi")
        return

    asin, html, final_url = resolve_and_extract_asin(link)
    titolo = extract_title(html)
    immagine = extract_image(html)
    link_con_tag = add_affiliate_tag(final_url)

    set_state(f"pending_link_{chat_id}", link_con_tag)
    set_state(f"pending_titolo_{chat_id}", titolo)
    set_state(f"pending_immagine_{chat_id}", immagine)
    set_state(f"pending_asin_{chat_id}", asin)

    if titolo and not immagine:
        send_message(chat_id, f"📦 {titolo}\n\n⚠️ Non trovo l'immagine.\nMandami: prezzo_scontato prezzo_pieno link_immagine")
    elif titolo:
        send_message(chat_id, f"📦 {titolo}\n🖼 {immagine[:60]}...\n\nOra mandami i prezzi così:\nprezzo_scontato prezzo_pieno\n(es: 23.14 29.99)")
    else:
        send_message(chat_id, "⚠️ Non sono riuscito a leggere il titolo. Mandami comunque i prezzi, poi il titolo lo scrivi tu.")


def handle_prezzi(chat_id, text):
    pending_link = get_state(f"pending_link_{chat_id}", "")
    if not pending_link:
        return False

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

    if not immagine and len(parts) > 2 and parts[2].startswith("http"):
        immagine = parts[2]

    if not titolo:
        titolo_parts = [p for p in parts[2:] if not p.startswith("http")]
        titolo = " ".join(titolo_parts) if titolo_parts else "(titolo da completare)"

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

    set_state(f"pending_link_{chat_id}", "")

    nota = "" if immagine else "\n⚠️ Manca ancora l'immagine — aggiungila a mano sul foglio."
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
