import asyncio
import logging

from telegram import Bot

from amazon_products import pick_next_product
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from telegram_poster import post_product, format_message
from sheet_client import mark_row, now_iso

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("amazon_bot")


async def main():
    product, sheet_ref = pick_next_product()
    if product is None:
        log.warning("Nessun prodotto disponibile che rispetti i criteri.")
        return

    # --- GESTIONE DELLA PUBBLICAZIONE ---
    # Se l'immagine è presente, pubblica con foto.
    # Se l'immagine è vuota (es. link rotto o non disponibile), pubblica solo il testo.
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


if __name__ == "__main__":
    asyncio.run(main())