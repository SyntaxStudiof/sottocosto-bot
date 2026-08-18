import re

def clean_title(raw_text):
    text = raw_text
    
    # 1. Rimuovi la formattazione di Telegram (doppi asterischi, doppi underscore)
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'__', '', text)
    
    # 2. Rimuovi TUTTE le etichette di prezzo
    text = re.sub(r'[Pp]rezzo\s*[a-zA-Z\s]*?[:.]?\s*\d+[.,]?\d*\s?[€€]\s*', '', text)
    text = re.sub(r'\b\d+[.,]?\d*\s?[€€]\b', '', text)
    
    # 3. Rimuovi tutti gli URL (link Amazon, ecc.)
    text = re.sub(r'https?://\S+', '', text)
    
    # 4. Rimuovi frasi comuni lasciate dai canali
    text = re.sub(r'VAI ALL\'OFFERTA', '', text, flags=re.IGNORECASE)
    text = re.sub(r'VAI ALL\'', '', text, flags=re.IGNORECASE)
    text = re.sub(r'#\w+', '', text)
    
    # 5. IL TRUCCO FINALE: Cancella TUTTI i simboli di parentesi tonde, quadre e graffe
    # Questa riga elimina la ( anche se è rimasta da sola, senza cercare la sua compagna )
    text = re.sub(r'[\(\)\[\]\{\}]', '', text)
    
    # 6. Pulisci gli spazi extra
    text = ' '.join(text.split())
    
    return text.strip()


def split_multiple_offers(text):
    separators = [r'\n-+\n', r'\n\s*\n', r'✅', r'❌', r'🔹', r'🔸', r'⬇️']
    for sep in separators:
        parts = re.split(sep, text)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]
    return [text.strip()]
