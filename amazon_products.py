import random
from datetime import datetime, timezone

from config import MIN_DISCOUNT_PERCENT
from sheet_client import get_all_rows, mark_row, now_iso


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


def pick_next_product(min_discount=MIN_DISCOUNT_PERCENT):
    rows, ws = get_all_rows()
    candidates = []
    for row in rows:
        if not row.get("titolo"):
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

    chosen = random.choice(candidates)
    product = {
        "title": chosen.get("titolo", "").strip(),
        "price": float(str(chosen.get("prezzo", 0)).replace(",", ".")),
        "old_price": float(str(chosen.get("prezzo_originale", 0)).replace(",", ".")),
        "discount_percent": int(chosen.get("sconto_percento", 0)),
        "image_url": chosen.get("immagine_url", "").strip(),
        "affiliate_link": chosen.get("link_affiliato", "").strip(),
    }
    return product, (ws, chosen["_row_number"])
