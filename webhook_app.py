import os
from flask import Flask, request

from telegram_commands import handle_aggiungi, handle_pending_reply, handle_callback_query

app = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True) or {}

    if "callback_query" in update:
        handle_callback_query(update["callback_query"])
        return "", 200

    message = update.get("message", {})
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")

    if text.startswith("/aggiungi"):
        args = text[len("/aggiungi"):].strip()
        handle_aggiungi(chat_id, args)
    elif chat_id:
        handle_pending_reply(chat_id, text)

    return "", 200


@app.route("/")
def health():
    return "Bot attivo", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
