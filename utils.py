import re

def clean_title(raw_text):
    text = raw_text
    
    # 1. Rimuovi la formattazione di Telegram (doppi asterischi, doppi underscore)
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'__', '', text)
    
    # 2. Rimuovi TUTTE le etichette di prezzo
    text = re.sub(r'[Pp]rezzo\s*[a-zA-Z\s]*?[:.]?\s*\d+[.,]?\d*\s?[€€]\s*', '', text)
    
    # 3. Rimuovi TUTTI gli URL (link Amazon, ecc.)
    text = re.sub(r'https?://\S+', '', text)
    
    # 4. Rimuovi TUTTE le parentesi e TUTTO il loro contenuto (es: "[VAI ALL']", "(Disclamer)")
    text = re.sub(r'\[.*?\]', '', text)  # Rimuove le parentesi quadre e ciò che c'è dentro
    text = re.sub(r'\(.*?\)', '', text)  # Rimuove le parentesi tonde e ciò che c'è dentro
    
    # 5. Rimuovi eventuali parole chiave rimaste come "VAI ALL'OFFERTA" o simili
    text = re.sub(r'VAI ALL\'OFFERTA', '', text, flags=re.IGNORECASE)
    text = re.sub(r'VAI ALL\'', '', text, flags=re.IGNORECASE)
    
    # 6. Rimuovi hashtag o tag rimasti
    text = re.sub(r'#\w+', '', text)
    
    # 7. Pulisci gli spazi extra
    text = ' '.join(text.split())
    
    return text.strip()


def split_multiple_offers(text):
    separators = [r'\n-+\n', r'\n\s*\n', r'✅', r'❌', r'🔹', r'🔸', r'⬇️']
    for sep in separators:
        parts = re.split(sep, text)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]
    return [text.strip()]
