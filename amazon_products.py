import re
import random
from datetime import datetime, timezone

from config import MIN_DISCOUNT_PERCENT
from sheet_client import get_all_rows, mark_row, now_iso


def _immagine_alta_qualita(url):
    """Toglie il codice di 'dimensione piccola' che Amazon mette nei link
    delle immagini (es. "._AC_SX300_"), così Telegram carica la versione
    grande e nitida invece di quella sgranata. Fatto anche qui come rete
    di sicurezza, nel caso nel foglio ci sia già un link piccolo salvato."""
    if not url:
        return url
    return re.sub(r'\._[A-Za-z0-9_,]+_\.', '.', url)


def _is_valid(row):
    stato = row.get("stato", "").strip().upper()
    if stato not in ("NUOVO", "APPROVATO"):
        return False
    scade_il = row.get("scade_il", "").strip()
    if scade_il:
        try:
            scadenza = datetime.fromisoformat(scade_il)
            if scadenza.tzinfo is None:
                scadenza = scadenza.replace(tzinfo=timezone.utc)
            if scadenza < datetime.now(timezone.utc):
                return False
        except ValueError:
            pass  # se il formato data non è valido, non blocchiamo
    return True


def _data_aggiunta(row):
    """Legge la colonna 'aggiunto_il' e la trasforma in una data leggibile
    da Python, così possiamo ordinare i prodotti dal più vecchio al più nuovo.
    Se la data manca o è scritta male, la mettiamo in fondo alla lista
    (così non blocca la pubblicazione degli altri prodotti)."""
    valore = row.get("aggiunto_il", "").strip()
    if not valore:
        return datetime.max.replace(tzinfo=timezone.utc)
    try:
        data = datetime.fromisoformat(valore)
        if data.tzinfo is None:
            data = data.replace(tzinfo=timezone.utc)
        return data
    except ValueError:
        return datetime.max.replace(tzinfo=timezone.utc)


def pick_next_product(min_discount=MIN_DISCOUNT_PERCENT):
    rows, ws = get_all_rows()
    candidates = []
    for row in rows:
        if not row.get("titolo"):
            continue

        # --- CONTROLLO FONDAMENTALE: Salta le offerte senza immagine ---
        if not row.get("immagine_url", "").strip():
            continue

        try:
            sconto = int(row.get("sconto_percento", 0))
        except ValueError:
            sconto = 0

        if sconto < min_discount:
            continue
        if not _is_valid(row):
            continue

        candidates.append(row)

    if not candidates:
        return None, None

    # --- SCELTA DEL PRODOTTO: il più vecchio (aggiunto_il) va pubblicato per primo ---
    candidates.sort(key=_data_aggiunta)
    chosen = candidates[0]

    product = {
        "title": chosen.get("titolo", "").strip(),
        "price": float(str(chosen.get("prezzo", 0)).replace(",", ".")),
        "old_price": float(str(chosen.get("prezzo_originale", 0)).replace(",", ".")),
        "discount_percent": int(chosen.get("sconto_percento", 0)),
        "image_url": _immagine_alta_qualita(chosen.get("immagine_url", "").strip()),
        "affiliate_link": chosen.get("link_affiliato", "").strip(),
    }
    return product, (ws, chosen["_row_number"])
