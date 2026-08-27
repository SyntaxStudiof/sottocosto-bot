import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Bot

from amazon_products import pick_next_product
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from telegram_poster import post_product, format_message
from sheet_client import mark_row, now_iso, get_state, set_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("amazon_bot")

# --- REGOLE DI PUBBLICAZIONE (usate sia da Render che da GitHub Actions) ---
ULTIMA_PUBBLICAZIONE_KEY = "ultima_pubblicazione"
INTERVALLO_MINIMO = timedelta(minutes=55)  # un po' meno di un'ora, per tolleranza
ORA_INIZIO = 8   # 08:00 ora italiana
ORA_FINE = 22    # 22:00 ora italiana


def _dentro_fascia_oraria():
    """Usa il fuso orario 'Europe/Rome': si aggiusta da solo con l'ora legale/solare,
    niente più bisogno di cambiare il cron a ottobre/marzo."""
    ora_italia = datetime.now(ZoneInfo("Europe/Rome"))
    return ORA_INIZIO <= ora_italia.hour < ORA_FINE


def _tempo_trascorso_abbastanza():
    ultima = get_state(ULTIMA_PUBBLICAZIONE_KEY, "")
    if not ultima:
        return True
    try:
        ultima_dt = datetime.fromisoformat(ultima)
        if ultima_dt.tzinfo is None:
            ultima_dt = ultima_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - ultima_dt >= INTERVALLO_MINIMO


async def pubblica_prodotto():
    """Pubblica il prossimo prodotto disponibile, ma SOLO se è il momento giusto
    (dentro l'orario 08-22 e non troppo a ridosso dell'ultima pubblicazione).
    Ritorna True se ha pubblicato, False se ha saltato."""

    if not _dentro_fascia_oraria():
        log.info("Fuori fascia oraria (08-22 Italia), salto.")
        return False

    if not _tempo_trascorso_abbastanza():
        log.info("Pubblicato troppo di recente, salto.")
        return False

    product, sheet_ref = pick_next_product()
    if product is None:
        log.warning("Nessun prodotto disponibile che rispetti i criteri.")
        return False

    # --- GESTIONE DELLA PUBBLICAZIONE ---
    if product.get("image_url"):
        await post_product(product)
        log.info("✅ Pubblicato (con immagine): %s", product["title"])
    else:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        testo = format_message(product)
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=testo,
            parse_mode="HTML"
        )
        log.warning("⚠️ Pubblicato (SENZA immagine, campo vuoto nel foglio): %s", product["title"])

    # --- AGGIORNAMENTO DEL FOGLIO ---
    if sheet_ref:
        ws, row_number = sheet_ref
        mark_row(ws, row_number, stato="PUBBLICATO", extra_updates={"pubblicato_il": now_iso()})

    # --- SEGNA CHE ABBIAMO PUBBLICATO ADESSO (evita doppioni ravvicinati) ---
    set_state(ULTIMA_PUBBLICAZIONE_KEY, now_iso())
    return True


async def main():
    await pubblica_prodotto()


if __name__ == "__main__":
    asyncio.run(main())
