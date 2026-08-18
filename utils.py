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
    
    # 5. Rimuovi TUTTI i simboli di parentesi tonde, quadre e graffe
    text = re.sub(r'[\(\)\[\]\{\}]', '', text)
    
    # 6. Pulisci gli spazi extra
    text = ' '.join(text.split())
    
    # --- FALLBACK INTELLIGENTE (SENZA SCRAPING) ---
    # Se dopo tutta la pulizia il testo è troppo corto (es. è rimasto vuoto),
    # allora usiamo il testo originale, gli togliamo solo le cose minime (link e VAI ALL'OFFERTA)
    # e prendiamo i primi 150 caratteri per avere un titolo!
    if len(text.strip()) < 5:
        fallback = raw_text
        fallback = re.sub(r'https?://\S+', '', fallback)
        fallback = re.sub(r'VAI ALL\'OFFERTA', '', fallback, flags=re.IGNORECASE)
        fallback = re.sub(r'#\w+', '', fallback)
        fallback = ' '.join(fallback.split())
        if len(fallback) > 150:
            fallback = fallback[:147] + "..."
        
        if fallback.strip():
            return fallback.strip()
        else:
            return "Prodotto Amazon (controlla)"
    
    return text.strip()


def split_multiple_offers(text):
    separators = [r'\n-+\n', r'\n\s*\n', r'✅', r'❌', r'🔹', r'🔸', r'⬇️']
    for sep in separators:
        parts = re.split(sep, text)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]
    return [text.strip()]
