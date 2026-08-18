import re

def clean_title(raw_text):
    text = raw_text
    
    # 1. Rimuovi formattazione Telegram e parole dei prezzi
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'__', '', text)
    text = re.sub(r'[Pp]rezzo\s*[a-zA-Z\s]*?[:.]?\s*\d+[.,]?\d*\s?[€€]\s*', '', text)
    text = re.sub(r'\b\d+[.,]?\d*\s?[€€]\b', '', text)
    
    # 2. Rimuovi link, frasi comuni, hashtag e parentesi
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'VAI ALL\'OFFERTA', '', text, flags=re.IGNORECASE)
    text = re.sub(r'#\w+', '', text)
    text = re.sub(r'[\(\)\[\]\{\}]', '', text)
    
    # 3. Pulisci gli spazi
    text = ' '.join(text.split())
    
    # --- FALLBACK DEFINITIVO (ANTI-TITOLO VUOTO) ---
    # Se il titolo è troppo corto (es. è rimasto vuoto), usiamo il testo originale
    if len(text.strip()) < 5:
        fallback = raw_text
        # Togliamo solo i link e le parole davvero inutili
        fallback = re.sub(r'https?://\S+', '', fallback)
        fallback = re.sub(r'#\w+', '', fallback)
        fallback = re.sub(r'[\(\)\[\]\{\}]', '', fallback)
        fallback = ' '.join(fallback.split())
        
        if fallback.strip():
            # Se il testo c'è, taglialo a max 100 caratteri
            if len(fallback) > 100:
                return fallback[:97] + "..."
            return fallback.strip()
        else:
            # Fallback assoluto nel caso sia tutto spazzatura
            return "Prodotto Amazon (controlla anteprima)"
    
    # 4. Se è molto lungo, accorcialo per il foglio Google
    if len(text) > 100:
        return text[:97] + "..."
        
    return text.strip()


def split_multiple_offers(text):
    separators = [r'\n-+\n', r'\n\s*\n', r'✅', r'❌', r'🔹', r'🔸', r'⬇️']
    for sep in separators:
        parts = re.split(sep, text)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]
    return [text.strip()]
