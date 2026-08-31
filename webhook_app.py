import os
import asyncio
import traceback

import requests
from flask import Flask, request

from config import TELEGRAM_BOT_TOKEN
from telegram_commands import (
    handle_aggiungi,
    handle_pending_reply,
    handle_callback_query,
    handle_start,
    handle_pending_link,
)
from main import pubblica_prodotto

app = Flask(__name__)

OWNER_CHAT_ID = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")


def _notify_owner_error(err_text):
    """Manda l'errore in chat invece di lasciarlo sparire nei log di Render."""
    if not OWNER_CHAT_ID or not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": OWNER_CHAT_ID, "text": f"⚠️ Errore nel webhook:\n{err_text[:1500]}"},
            timeout=5,
        )
    except Exception:
        pass


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True) or {}

    try:
        if "callback_query" in update:
            handle_callback_query(update["callback_query"])
        else:
            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = message.get("chat", {}).get("id")

            if text == "/start":
                handle_start(chat_id)
            elif text.startswith("/aggiungi"):
                args = text[len("/aggiungi"):].strip()
                handle_aggiungi(chat_id, args)
            elif chat_id:
                # Prima prova se è un link mandato dopo aver cliccato "Aggiungi offerta"
                if not handle_pending_link(chat_id, text):
                    # Altrimenti è una risposta al flusso interattivo
                    handle_pending_reply(chat_id, text)

    except Exception:
        err = traceback.format_exc()
        print(err)
        _notify_owner_error(err)

    # IMPORTANTE: rispondere sempre 200, subito, qualunque cosa succeda.
    return "", 200


@app.route("/")
def health():
    # UptimeRobot pinga questo indirizzo ogni 5 minuti per tenere sveglio Render.
    # Ne approfittiamo per controllare se è ora di pubblicare il prossimo prodotto.
    try:
        asyncio.run(pubblica_prodotto())
    except Exception:
        err = traceback.format_exc()
        print(err)
        _notify_owner_error(err)

    return "Bot attivo", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
