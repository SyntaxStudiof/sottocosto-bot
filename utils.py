import re

def clean_title(raw_text):
    # 1. Rimuovi tutti gli URL (http/https)
    text = re.sub(r'https?://\S+', '', raw_text)
    
    # 2. Rimuovi i pattern di prezzo (es. 12,99€, 12.99 €, 120€, Prezzo: 15€)
    text = re.sub(r'\b\d+[.,]?\d*\s?[€€€€€]\b', '', text)
    text = re.sub(r'[Pp]rezzo\s*[:.]?\s*\d+[.,]?\d*\s?[€€]', '', text)
    
    # 3. Rimuovi parole inutili come "Offerta", "Sconto", "Amazon"
    text = re.sub(r'\b(Offerta|Sconto|Amazon|Prime|Link|Acquista)\b', '', text, flags=re.IGNORECASE)
    
    # 4. Pulisci spazi multipli e ritorni a capo
    text = ' '.join(text.split())
    
    return text.strip()
