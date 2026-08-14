from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID


def format_message(product: dict) -> str:
    risparmio = product["old_price"] - product["price"]
    return (
        f"🔥 *OFFERTA IMPERDIBILE* 🔥\n\n"
        f"*{product['title']}*\n\n"
        f"~~{product['old_price']:.2f}€~~  ➜  *{product['price']:.2f}€*\n"
        f"💥 Sconto del {product['discount_percent']}% (risparmi {risparmio:.2f}€)\n\n"
        f"👉 [Acquista ora]({product['affiliate_link']})\n\n"
        f"_Link affiliato Amazon: potremmo ricevere una piccola commissione, "
        f"senza costi aggiuntivi per te._"
    )


async def post_product(product: dict):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN o TELEGRAM_CHANNEL_ID non configurati."
        )

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    testo = format_message(product)

    await bot.send_photo(
        chat_id=TELEGRAM_CHANNEL_ID,
        photo=product["image_url"],
        caption=testo,
        parse_mode="Markdown",
    )
