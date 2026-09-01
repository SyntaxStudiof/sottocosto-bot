import re
import json
import html as html_module
import requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, AUTO_APPROVAL_ENABLED
from sheet_client import get_state, set_state, delete_state, get_state_json, set_state_json, append_product_row, get_all_rows
from auto_approval import arricchisci_dati, valida_offerta, prodotti_recenti_dal_foglio

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
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


def _immagine_alta_qualita(url):
    if not url:
        return url
    return re.sub(r'\._[A-Za-z0-9_,]+_\.', '.', url)


def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    if parse_mode:
        data["parse_mode"] = parse_mode
    return requests.post(f"{API_URL}/sendMessage", data=data, timeout=15)


def answer_callback(callback_id, text=""):
    requests.post(f"{API_URL}/answerCallbackQuery", data={
        "callback_query_id": callback_id,
        "text": text,
    }, timeout=15)


def edit_message(chat_id, message_id, text):
    requests.post(f"{API_URL}/editMessageText", data={
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }, timeout=15)


def delete_message(chat_id, message_id):
    try:
        requests.post(f"{API_URL}/deleteMessage", data={
            "chat_id": chat_id,
            "message_id": message_id,
        }, timeout=10)
    except Exception:
        pass


def resolve_and_extract_asin(link):
    resp = requests.get(link, allow_redirects=True, timeout=20, headers=HEADERS)
    final_url = resp.url
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", final_url)
    asin = match.group(1) if match else ""
    return asin, resp.text, final_url


def extract_title(html):
    soup = BeautifulSoup(html, 'html.parser')

    if soup.find('form', {'action': '/errors/validateCaptcha'}):
        return ""

    titolo = ""
    h1_tag = soup.find('h1', id='title')
    if h1_tag:
        titolo = h1_tag.get_text(strip=True)
        titolo = re.sub(r'\s*[–|-]\s*Amazon\.(it|com|co\.uk)$', '', titolo, flags=re.IGNORECASE)
        return titolo.strip()

    og_title = soup.find('meta', property='og:title')
    if og_title and og_title.get('content'):
        titolo = og_title['content']
        titolo = re.sub(r'\s*[–|-]\s*Amazon\.(it|com|co\.uk)$', '', titolo, flags=re.IGNORECASE)
        return titolo.strip()

    tw_title = soup.find('meta', attrs={'name': 'twitter:title'})
    if tw_title and tw_title.get('content'):
        titolo = tw_title['content']
        titolo = re.sub(r'\s*[–|-]\s*Amazon\.(it|com|co\.uk)$', '', titolo, flags=re.IGNORECASE)
        return titolo.strip()

    title_tag = soup.find('title')
    if title_tag:
        titolo = title_tag.get_text(strip=True)
        titolo = re.sub(r'\s*:\s*Amazon\.it$', '', titolo, flags=re.IGNORECASE)
        titolo = re.sub(r'\s*[–|-]\s*Amazon\.(it|com|co\.uk)$', '', titolo, flags=re.IGNORECASE)
        return titolo.strip()

    return ""


def extract_image(html):
    soup = BeautifulSoup(html, 'html.parser')

    if soup.find('form', {'action': '/errors/validateCaptcha'}):
        return ""

    main_img = soup.find('img', id='landingImage')
    if main_img and main_img.get('src'):
        return _immagine_alta_qualita(main_img['src'])

    old_hires = soup.find('img', attrs={'data-old-hires': True})
    if old_hires and old_hires.get('data-old-hires'):
        return _immagine_alta_qualita(old_hires['data-old-hires'])

    dynamic_img = soup.find('img', attrs={'data-a-dynamic-image': True})
    if dynamic_img:
        raw = dynamic_img['data-a-dynamic-image']
        try:
            data = json.loads(html_module.unescape(raw))
            if data:
                return _immagine_alta_qualita(list(data.keys())[0])
        except Exception:
            pass

    og_image = soup.find('meta', property='og:image')
    if og_image and og_image.get('content'):
        return _immagine_alta_qualita(og_image['content'])

    tw_image = soup.find('meta', attrs={'name': 'twitter:image'})
    if tw_image and tw_image.get('content'):
        return _immagine_alta_qualita(tw_image['content'])

    return ""


def extract_price(html):
    match = re.search(r'<span class="a-price-whole">(\d+[.,]?\d*)</span>', html)
    if match:
        return match.group(1).replace(".", ",")
    return None


def extract_price_pieno(html):
    patterns = [
        r'<span class="a-price a-text-price"[^>]*>\s*<span class="a-offscreen">[^€]*€\s*(\d+[.,]\d{2})',
        r'(?:Prezzo consigliato|Prezzo precedente|List price|Prezzo pieno)[:\s]*€?\s*(\d+[.,]\d{2})',
        r'a-text-price[^>]*>€\s*(\d+[.,]\d{2})<',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return m.group(1).replace(".", ",")
    return None


def _pending_key(chat_id):
    return f"pending_{chat_id}"


# ================= MENU CON PULSANTI =================

def handle_start(chat_id):
    keyboard = {
        "inline_keyboard": [[
            {"text": "➕ Aggiungi offerta", "callback_data": "menu_aggiungi"},
            {"text": "📋 Coda pubblicazioni", "callback_data": "menu_recap"},
        ]]
    }
    send_message(chat_id, "👋 Cosa vuoi fare?", reply_markup=json.dumps(keyboard))


def _ora_italiana(dt_utc):
    return dt_utc + timedelta(hours=2)


def show_recap(chat_id):
    try:
        righe, _ = get_all_rows()
        now = datetime.now(timezone.utc)

        coda = []
        for r in righe:
            stato = (r.get("stato") or "").strip().upper()
            if stato not in ("NUOVO", "APPROVATO"):
                continue
            scade = (r.get("scade_il") or "").strip()
            if scade:
                try:
                    if datetime.fromisoformat(scade.replace("Z", "+00:00")) < now:
                        continue
                except Exception:
                    pass
            coda.append(r)

        keyboard = {
            "inline_keyboard": [[
                {"text": "🔄 Aggiorna", "callback_data": "menu_refresh"},
                {"text": "🔙 Menu", "callback_data": "menu_back"},
            ]]
        }

        if not coda:
            send_message(
                chat_id,
                "📭 <b>Coda vuota</b>\nNessuna offerta in attesa di pubblicazione.",
                reply_markup=json.dumps(keyboard),
                parse_mode="HTML",
            )
            return

        def sort_key(r):
            try:
                return datetime.fromisoformat((r.get("aggiunto_il") or "").replace("Z", "+00:00"))
            except Exception:
                return datetime.max.replace(tzinfo=timezone.utc)

        coda.sort(key=sort_key)

        approvate = sum(1 for r in coda if (r.get("stato") or "").strip().upper() == "APPROVATO")
        nuove = len(coda) - approvate

        parti = []
        parti.append("📋 <b>CODA PUBBLICAZIONI</b>")
        parti.append("")
        parti.append(f"✅ Pronte: <b>{len(coda)}</b>   (approvate {approvate} · nuove {nuove})")
        parti.append("")
        parti.append("⏭ <b>Prossime uscite:</b>")

        for i, r in enumerate(coda[:5], 1):
            titolo = html_module.escape((r.get("titolo") or "Senza titolo").strip()[:70])
            prezzo = html_module.escape(str(r.get("prezzo", "?")))
            sconto = html_module.escape(str(r.get("sconto_percento", "?")))
            try:
                scade_it = _ora_italiana(
                    datetime.fromisoformat((r.get("scade_il") or "").replace("Z", "+00:00"))
                )
                scade_fmt = scade_it.strftime("%d/%m ore %H:%M")
            except Exception:
                scade_fmt = "—"
            parti.append("")
            parti.append(f"<b>{i}.</b> {titolo}")
            parti.append(f"💰 {prezzo} € · −{sconto}% · ⏰ {scade_fmt}")

        if len(coda) > 5:
            parti.append("")
            parti.append(f"<i>…e altre {len(coda) - 5} in coda.</i>")

        send_message(
            chat_id,
            "\n".join(parti),
            reply_markup=json.dumps(keyboard),
            parse_mode="HTML",
        )

    except Exception as e:
        send_message(chat_id, f"❌ Errore nel recupero della coda: {str(e)[:100]}")


def handle_menu_aggiungi(chat_id):
    set_state_json(_pending_key(chat_id), {"waiting_for_link": True})
    send_message(chat_id, "🔗 Mandami il link Amazon dell'offerta:")


def handle_pending_link(chat_id, text):
    state = get_state_json(_pending_key(chat_id))
    if state.get("waiting_for_link"):
        delete_state(_pending_key(chat_id))
        handle_aggiungi(chat_id, text)
        return True
    return False


# ================= FINE MENU =================


def ask_next(chat_id):
    state = get_state_json(_pending_key(chat_id))
    queue = state.get("queue", [])
    if not queue:
        finalize(chat_id)
        return
    next_field = queue[0]
    send_message(chat_id, PROMPTS[next_field])


def finalize(chat_id):
    state = get_state_json(_pending_key(chat_id))
    link = state.get("link", "")
    titolo = state.get("titolo", "")
    immagine = state.get("immagine", "")
    asin = state.get("asin", "")
    prezzo_scontato = state.get("prezzo_scontato", "")
    prezzo_pieno = state.get("prezzo_pieno", "")

    try:
        prezzo_scontato_f = float(str(prezzo_scontato).replace(",", "."))
        prezzo_pieno_f = float(str(prezzo_pieno).replace(",", "."))
    except ValueError:
        send_message(chat_id, "❌ Errore nei prezzi salvati. Riprova da capo con /aggiungi.")
        delete_state(_pending_key(chat_id))
        return

    loading_msg = send_message(chat_id, "⏳ Salvataggio su Google Sheets in corso... attendi qualche secondo.")

    loading_msg_id = None
    if loading_msg is not None and loading_msg.status_code == 200:
        try:
            loading_msg_id = loading_msg.json()["result"]["message_id"]
        except Exception:
            pass

    try:
        sconto_percento = round((1 - prezzo_scontato_f / prezzo_pieno_f) * 100)
        now = datetime.now(timezone.utc)

        append_product_row({
            "titolo": titolo,
            "prezzo": str(prezzo_scontato_f).replace(".", ","),
            "prezzo_originale": str(prezzo_pieno_f).replace(".", ","),
            "sconto_percento": sconto_percento,
            "link_affiliato": link,
            "immagine_url": _immagine_alta_qualita(immagine),
            "ASIN": asin,
            "fonte": "manuale",
            "stato": "APPROVATO",
            "aggiunto_il": now.isoformat(),
            "scade_il": (now + timedelta(hours=6)).isoformat(),
            "pubblicato_il": "",
        })

        success_text = f"✅ Aggiunto e approvato: {titolo}\nSconto: {sconto_percento}%"
        if loading_msg_id:
            edit_message(chat_id, loading_msg_id, success_text)
        else:
            send_message(chat_id, success_text)

    except Exception as e:
        error_text = f"❌ ERRORE nel salvataggio su Google Sheets:\n\n{str(e)}\n\nControlla le colonne del foglio."
        if loading_msg_id:
            edit_message(chat_id, loading_msg_id, error_text)
        else:
            send_message(chat_id, error_text)

    finally:
        delete_state(_pending_key(chat_id))


def handle_aggiungi(chat_id, args):
    link = args.strip()
    if not link.startswith("http"):
        send_message(chat_id, "Mandami un link Amazon valido dopo /aggiungi")
        return

    asin, html, final_url = resolve_and_extract_asin(link)
    titolo = extract_title(html)
    immagine = extract_image(html)
    prezzo_scontato = extract_price(html)
    prezzo_pieno = extract_price_pieno(html)
    link_con_tag = add_affiliate_tag(final_url)

    # --- Tentativo di auto-completamento e approvazione ---
    if AUTO_APPROVAL_ENABLED and asin:
        try:
            dati = {
                "titolo": titolo or None,
                "prezzo_scontato": float(str(prezzo_scontato).replace(",", ".")) if prezzo_scontato else None,
                "prezzo_pieno": float(str(prezzo_pieno).replace(",", ".")) if prezzo_pieno else None,
                "sconto_percent": None,
                "asin": asin,
                "immagine_url": immagine or None,
                "link_originale": final_url,
            }
            dati = arricchisci_dati(dati)
            righe, _ = get_all_rows()
            ok, motivi = valida_offerta(dati, prodotti_recenti_dal_foglio(righe))
            if ok:
                now = datetime.now(timezone.utc)
                append_product_row({
                    "titolo": dati["titolo"],
                    "prezzo": dati["prezzo_scontato_eur"],
                    "prezzo_originale": dati["prezzo_pieno_eur"],
                    "sconto_percento": dati["sconto_percent"],
                    "link_affiliato": dati["link_affiliato"],
                    "immagine_url": _immagine_alta_qualita(dati["immagine_url"]),
                    "ASIN": dati["asin"],
                    "fonte": "manuale",
                    "stato": "APPROVATO",
                    "aggiunto_il": now.isoformat(),
                    "scade_il": (now + timedelta(hours=6)).isoformat(),
                    "pubblicato_il": "",
                })
                send_message(chat_id, f"🤖 Aggiunto automaticamente: {dati['titolo']}\n💰 {dati['prezzo_scontato_eur']}€ invece di {dati['prezzo_pieno_eur']}€ (−{dati['sconto_percent']}%)")
                return
            else:
                send_message(chat_id, "ℹ️ Dati incompleti, procedo con le domande: " + "; ".join(motivi))
        except Exception as e:
            send_message(chat_id, f"⚠️ Auto-completamento non riuscito, procedo con le domande.")

    # --- Flusso interattivo esistente (fallback) ---
    queue = []
    if not titolo:
        queue.append("titolo")
    if not immagine:
        queue.append("immagine")
    queue.append("prezzo_scontato")
    queue.append("prezzo_pieno")

    state = {
        "link": link_con_tag,
        "titolo": titolo,
        "immagine": immagine,
        "asin": asin,
        "prezzo_scontato": "",
        "prezzo_pieno": "",
        "queue": queue,
    }
    set_state_json(_pending_key(chat_id), state)

    trovati = []
    if titolo:
        trovati.append(f"📦 {titolo}")
    if immagine:
        trovati.append("🖼 immagine trovata")
    if trovati:
        send_message(chat_id, "\n".join(trovati))

    ask_next(chat_id)


def handle_pending_reply(chat_id, text):
    state = get_state_json(_pending_key(chat_id))
    queue = state.get("queue", [])
    if not queue:
        return False

    current_field = queue[0]
    value = text.strip()

    if current_field in ("prezzo_scontato", "prezzo_pieno"):
        try:
            float(value.replace(",", "."))
        except ValueError:
            send_message(chat_id, "Deve essere un numero, es: 23.14. Riprova:")
            return True

    state[current_field] = value
    state["queue"] = queue[1:]
    set_state_json(_pending_key(chat_id), state)

    if state["queue"]:
        ask_next(chat_id)
    else:
        finalize(chat_id)

    return True


def handle_callback_query(callback_query):
    callback_id = callback_query["id"]
    data = callback_query.get("data", "")
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]

    # --- PULSANTI MENU ---
    if data == "menu_aggiungi":
        answer_callback(callback_id)
        handle_menu_aggiungi(chat_id)
        return

    if data == "menu_recap":
        answer_callback(callback_id)
        show_recap(chat_id)
        return

    if data == "menu_refresh":
        answer_callback(callback_id)
        delete_message(chat_id, message_id)
        show_recap(chat_id)
        return

    if data == "menu_back":
        answer_callback(callback_id)
        delete_message(chat_id, message_id)
        handle_start(chat_id)
        return

    # --- FLUSSO ESISTENTE: Approva/Scarta offerte monitorate ---
    if data.startswith("approva_"):
        candidate_id = data[len("approva_"):]
        link = get_state(f"pending_candidate_link_{candidate_id}", "")
        titolo = get_state(f"pending_candidate_testo_{candidate_id}", "")
        prezzo_scontato_str = get_state(f"pending_candidate_prezzo_scontato_{candidate_id}", "")
        prezzo_pieno_str = get_state(f"pending_candidate_prezzo_originale_{candidate_id}", "")

        if not link:
            answer_callback(callback_id, "Candidato non trovato o già gestito.")
            return

        prezzo_scontato = None
        prezzo_pieno = None
        try:
            if prezzo_scontato_str:
                prezzo_scontato = float(prezzo_scontato_str.replace(",", "."))
            if prezzo_pieno_str:
                prezzo_pieno = float(prezzo_pieno_str.replace(",", "."))
        except ValueError:
            answer_callback(callback_id, "Errore nel formato dei prezzi.")
            return

        if prezzo_scontato is None:
            answer_callback(callback_id, "Prezzo scontato mancante, approvazione annullata.")
            return
        if prezzo_pieno is None:
            prezzo_pieno = prezzo_scontato

        asin, html_page, final_url = resolve_and_extract_asin(link)
        link_con_tag = add_affiliate_tag(final_url)
        titolo_finale = titolo if titolo else "Prodotto Amazon"
        immagine_url = extract_image(html_page)

        sconto_percento = 0
        if prezzo_pieno > 0:
            sconto_percento = round((1 - prezzo_scontato / prezzo_pieno) * 100)

        now = datetime.now(timezone.utc)

        try:
            append_product_row({
                "titolo": titolo_finale,
                "prezzo": str(prezzo_scontato).replace(".", ","),
                "prezzo_originale": str(prezzo_pieno).replace(".", ","),
                "sconto_percento": sconto_percento,
                "link_affiliato": link_con_tag,
                "immagine_url": immagine_url,
                "ASIN": asin,
                "fonte": "canale_terzo",
                "stato": "APPROVATO",
                "aggiunto_il": now.isoformat(),
                "scade_il": (now + timedelta(hours=6)).isoformat(),
                "pubblicato_il": "",
            })
            answer_callback(callback_id, "Aggiunto!")
            edit_message(chat_id, message_id, "✅ Approvato e aggiunto alla coda.")
        except Exception as e:
            answer_callback(callback_id, f"❌ Errore salvataggio: {str(e)[:50]}...")
            edit_message(chat_id, message_id, f"❌ ERRORE nell'approvazione:\n{str(e)}")

        for campo in ["link", "testo", "prezzo_scontato", "prezzo_originale"]:
            delete_state(f"pending_candidate_{campo}_{candidate_id}")

    elif data.startswith("scarta_"):
        candidate_id = data[len("scarta_"):]
        for campo in ["link", "testo", "prezzo_scontato", "prezzo_originale"]:
            delete_state(f"pending_candidate_{campo}_{candidate_id}")
        answer_callback(callback_id, "Scartato.")
        edit_message(chat_id, message_id, "❌ Scartato.")
