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

AFFILIATE_TAG = "sottocostoclu-21"

PROMPTS = {
    "titolo": "Non sono riuscito a recuperare il titolo, potresti scriverlo?",
    "immagine": "Non sono riuscito a recuperare l'immagine, puoi mandarmi il link?",
    "prezzo_scontato": "Qual è il prezzo scontato? (es: 23.14)",
    "prezzo_pieno": "Qual è il prezzo pieno originale? (es: 29.99)",
}


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


def ask_next(chat_id):
    """Guarda la coda dei campi mancanti e fa la prossima domanda, oppure salva se non ne restano."""
    queue_str = get_state(f"pending_queue_{chat_id}", "")
    if not queue_str:
        finalize(chat_id)
        return

    queue = queue_str.split(",")
    next_field = queue[0]
    send_message(chat_id, PROMPTS[next_field])


def finalize(chat_id):
    link = get_state(f"pending_link_{chat_id}", "")
    titolo = get_state(f"pending_titolo_{chat_id}", "")
    immagine = get_state(f"pending_immagine_{chat_id}", "")
    asin = get_state(f"pending_asin_{chat_id}", "")
    prezzo_scontato = get_state(f"pending_prezzo_scontato_{chat_id}", "")
    prezzo_pieno = get_state(f"pending_prezzo_pieno_{chat_id}", "")

    try:
        prezzo_scontato_f = float(prezzo_scontato.replace(",", "."))
        prezzo_pieno_f = float(prezzo_pieno.replace(",", "."))
    except ValueError:
        send_message(chat_id, "Errore nei prezzi salvati, riprova da capo con /aggiungi")
        return

    sconto_percento = round((1 - prezzo_scontato_f / prezzo_pieno_f) * 100)
    now = datetime.now(timezone.utc)

    append_product_row({
        "titolo": titolo,
        "prezzo": str(prezzo_scontato_f).replace(".", ","),
        "prezzo_originale": str(prezzo_pieno_f).replace(".", ","),
        "sconto_percento": sconto_percento,
        "link_affiliato": link,
        "immagine_url": immagine,
        "ASIN": asin,
        "fonte": "manuale",
        "stato": "NUOVO",
        "aggiunto_il": now.isoformat(),
        "scade_il": (now + timedelta(hours=4)).isoformat(),
        "pubblicato_il": "",
    })

    set_state(f"pending_queue_{chat_id}", "")
    send_message(chat_id, f"✅ Aggiunto: {titolo}\nSconto: {sconto_percento}%")


def handle_aggiungi(chat_id, args):
    link = args.strip()
    if not link.startswith("http"):
        send_message(chat_id, "Mandami un link Amazon valido dopo /aggiungi")
        return

    asin, html, final_url = resolve_and_extract_asin(link)
    titolo = extract_title(html)
    immagine = extract_image(html)
    link_con_tag = add_affiliate_tag(final_url)

    queue = []
    if not titolo:
        queue.append("titolo")
    if not immagine:
        queue.append("immagine")
    queue.append("prezzo_scontato")
    queue.append("prezzo_pieno")

    set_state(f"pending_link_{chat_id}", link_con_tag)
    set_state(f"pending_titolo_{chat_id}", titolo)
    set_state(f"pending_immagine_{chat_id}", immagine)
    set_state(f"pending_asin_{chat_id}", asin)
    set_state(f"pending_prezzo_scontato_{chat_id}", "")
    set_state(f"pending_prezzo_pieno_{chat_id}", "")
    set_state(f"pending_queue_{chat_id}", ",".join(queue))

    trovati = []
    if titolo:
        trovati.append(f"📦 {titolo}")
    if immagine:
        trovati.append("🖼 immagine trovata")
    if trovati:
        send_message(chat_id, "\n".join(trovati))

    ask_next(chat_id)


def handle_pending_reply(chat_id, text):
    queue_str = get_state(f"pending_queue_{chat_id}", "")
    if not queue_str:
        return False

    queue = queue_str.split(",")
    current_field = queue[0]
    value = text.strip()

    if current_field in ("prezzo_scontato", "prezzo_pieno"):
        try:
            float(value.replace(",", "."))
        except ValueError:
            send_message(chat_id, "Deve essere un numero, es: 23.14. Riprova:")
            return True

    set_state(f"pending_{current_field}_{chat_id}", value)

    remaining = queue[1:]
    set_state(f"pending_queue_{chat_id}", ",".join(remaining))

    if remaining:
        ask_next(chat_id)
    else:
        finalize(chat_id)

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
            handle_pending_reply(chat_id, text)

        set_state("last_update_id", str(update_id))


if __name__ == "__main__":
    main()
