import re

def clean_title(raw_text):
    text = raw_text
    
    # 1. Rimuovi la formattazione di Telegram (doppi asterischi, doppi underscore)
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'__', '', text)
    
    # 2. Rimuovi TUTTE le etichette di prezzo, anche se attaccate a spazi e simboli
    text = re.sub(r'[Pp]rezzo\s*[a-zA-Z\s]*?[:.]?\s*\d+[.,]?\d*\s?[€€]\s*', '', text)
    
    # 3. Rimuovi tutti gli URL (link Amazon, ecc.)
    text = re.sub(r'https?://\S+', '', text)
    
    # 4. Rimuovi tutte le parentesi tonde ( ), quadre [ ] e graffe { } rimaste
    text = re.sub(r'[\(\)\[\]\{\}]', '', text)
    
    # 5. Rimuovi hashtag o tag rimasti
    text = re.sub(r'#\w+', '', text)
    
    # 6. Pulisci gli spazi extra (trasforma spazi multipli in uno singolo)
    text = ' '.join(text.split())
    
    return text.strip()


def split_multiple_offers(text):
    separators = [r'\n-+\n', r'\n\s*\n', r'✅', r'❌', r'🔹', r'🔸', r'⬇️']
    for sep in separators:
        parts = re.split(sep, text)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]
    return [text.strip()]
