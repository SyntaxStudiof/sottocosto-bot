import re

def clean_title(raw_text):
    text = re.sub(r'https?://\S+', '', raw_text)
    text = re.sub(r'\b\d+[.,]?\d*\s?[€€€€€]\b', '', text)
    text = re.sub(r'[Pp]rezzo\s*[:.]?\s*\d+[.,]?\d*\s?[€€]', '', text)
    text = re.sub(r'\b(Offerta|Sconto|Amazon|Prime|Link|Acquista)\b', '', text, flags=re.IGNORECASE)
    text = ' '.join(text.split())
    return text.strip()

def split_multiple_offers(text):
    """
    Questa funzione divide un messaggio in più offerte.
    Cerca separatori comuni come ✅, ❌, 🔹, doppi a capo, ecc.
    """
    # Lista di simboli che spesso separano le offerte nei canali Telegram
    separators = [r'\n-+\n', r'\n\s*\n', r'✅', r'❌', r'🔹', r'🔸', r'⬇️']
    
    for sep in separators:
        # Cerca di dividere il testo usando questi simboli
        parts = re.split(sep, text)
        # Se è stato trovato più di un pezzo, restituisci tutti i pezzi
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]
            
    # Se non trova separatori, significa che è una singola offerta. Restituiscila così com'è.
    return [text.strip()]
