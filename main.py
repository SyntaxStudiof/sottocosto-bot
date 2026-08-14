import asyncio
import logging

from amazon_products import pick_next_product
from telegram_poster import post_product

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("amazon_bot")


async def main():
    product = pick_next_product()
    if product is None:
        log.warning("Nessun prodotto disponibile che rispetti i criteri.")
        return

    await post_product(product)
    log.info("Pubblicato: %s (%d%% sconto)", product["title"], product["discount_percent"])


if __name__ == "__main__":
    asyncio.run(main())
